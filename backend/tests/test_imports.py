import csv
import io
import uuid
from datetime import timedelta

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy.dialects import postgresql

from app.core.clock import as_utc
from app.models import Employee, ImportJob, SalaryRecord
from app.services import imports as service
from app.services.import_file import COLUMNS, template_xlsx
from app.worker.tasks import process_next_job

API = "/api/v1/imports"
HEADER = ",".join(COLUMNS)


def row(**values) -> dict:
    base = {
        "employee_code": "ACM-100001", "first_name": "Asha", "last_name": "Verma",
        "email": "asha@acme.example", "job_title": "Software Engineer", "job_level": "3",
        "department": "Engineering", "country_code": "IN", "city": "Pune",
        "employment_type": "full_time", "fte": "", "hire_date": "2025-04-01", "gender": "",
        "salary": "1840000", "currency": "", "salary_effective_date": "", "salary_reason": "",
        "salary_note": "",
    }  # fmt: skip
    base.update(values)
    return base


def csv_file(*rows: dict) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


def start(client, data: bytes, name="people.csv", key=None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(API, files={"file": (name, data)}, headers=headers)


def run_worker(session_factory, storage):
    with session_factory() as db:
        while process_next_job(db, storage):
            pass


@pytest.fixture
def ctx(db):
    return lambda: service.load_context(db)


# ---------- row checks (no worker) ----------
def test_valid_new_row_is_a_create(ctx):
    action, payload, errors = service.check_row(row(), ctx())
    assert (action, errors) == ("create", [])
    assert payload["salary"] == {"amount": "1840000.00", "currency": "INR", "effective_date": "2025-04-01",
                                 "reason": "hire", "note": None}  # fmt: skip
    assert payload["values"]["fte"] == "1.000"


def test_every_problem_in_a_row_is_reported(ctx):
    action, _, errors = service.check_row(
        row(email="nope", job_level="9", department="Space", country_code="FR", salary="-1",
            hire_date="01/04/2025", employment_type="intern", fte="2"),
        ctx(),
    )  # fmt: skip
    assert action == "error"
    assert {e["field"] for e in errors} == {
        "email", "job_level", "department", "country_code", "salary", "hire_date",
        "employment_type", "fte",
    }  # fmt: skip


def test_missing_required_values(ctx):
    _, _, errors = service.check_row(row(first_name="", salary="", employee_code=""), ctx())
    assert {(e["field"], e["message"]) for e in errors} >= {
        ("first_name", "Required"), ("salary", "Required"), ("employee_code", "Required"),
    }  # fmt: skip


def test_duplicates_inside_the_file(ctx):
    context = ctx()
    assert service.check_row(row(), context)[0] == "create"
    action, _, errors = service.check_row(row(), context)
    assert action == "error"
    assert {e["field"] for e in errors} == {"employee_code", "email"}


def test_existing_employee_rows(ctx, make_employee):
    e = make_employee(country_code="IN", salary="1840000", email="asha@acme.example",
                      first_name="Asha", last_name="Verma", city="Pune", hire_date="2025-04-01")  # fmt: skip
    same = row(employee_code=e.employee_code)
    assert service.check_row(same, ctx())[0] == "unchanged"
    # Blank optional cells leave stored values alone.
    assert service.check_row({**same, "city": ""}, ctx())[0] == "unchanged"

    action, payload, _ = service.check_row({**same, "job_level": "4", "salary": "2000000"}, ctx())
    assert action == "update"
    assert payload["values"] == {"job_level": 4}
    assert payload["salary"]["effective_date"] == "2026-10-14"  # default: today
    assert payload["salary"]["reason"] == "other"
    assert payload["version"] == e.version


def test_blank_currency_keeps_the_employees_currency(ctx, make_employee):
    # Paid in USD while living in India: a blank currency cell must not mean INR.
    e = make_employee(country_code="IN", salary="100000", currency="USD", email="asha@acme.example",
                      first_name="Asha", last_name="Verma", city="Pune", hire_date="2025-04-01")  # fmt: skip
    same = row(employee_code=e.employee_code, salary="100000")
    assert service.check_row(same, ctx())[0] == "unchanged"
    action, payload, _ = service.check_row({**same, "salary": "110000"}, ctx())
    assert action == "update"
    assert payload["salary"]["currency"] == "USD"


def test_someone_not_started_yet_can_be_reimported(ctx, make_employee):
    e = make_employee(country_code="IN", salary="1840000", email="asha@acme.example",
                      first_name="Asha", last_name="Verma", city="Pune", hire_date="2026-11-01")  # fmt: skip
    same = row(employee_code=e.employee_code, hire_date="2026-11-01")
    assert service.check_row(same, ctx()) == ("unchanged", {"raw": same}, [])
    # A new salary without a date starts on their first day, not today.
    action, payload, _ = service.check_row({**same, "salary": "1900000"}, ctx())
    assert action == "update"
    assert payload["salary"]["effective_date"] == "2026-11-01"


def test_email_owned_by_someone_else(ctx, make_employee):
    make_employee(email="asha@acme.example")
    _, _, errors = service.check_row(row(), ctx())
    assert errors == [{"field": "email", "message": "Already used by another employee"}]


def test_dates_must_be_sensible(ctx):
    _, _, errors = service.check_row(row(salary_effective_date="2024-01-01"), ctx())
    assert errors[0]["field"] == "salary_effective_date"
    _, _, errors = service.check_row(row(hire_date="2028-01-01"), ctx())
    assert {e["field"] for e in errors} == {"hire_date", "salary_effective_date"}


def test_template_has_columns_example_and_help():
    workbook = load_workbook(io.BytesIO(template_xlsx()))
    sheet = workbook["Employees"]
    assert [c.value for c in sheet[1]] == COLUMNS
    assert sheet["A2"].value == "ACM-010001"
    assert workbook["How to fill"].max_row == len(COLUMNS) + 1


# ---------- full lifecycle through the API and the worker ----------
def test_import_lifecycle_creates_and_updates(
    admin_client, make_employee, session_factory, storage, db
):
    existing = make_employee(country_code="IN", salary="1500000", email="old@acme.example",
                             first_name="Old", last_name="Timer", hire_date="2020-01-01")  # fmt: skip
    untouched = make_employee()
    data = csv_file(
        row(),
        row(employee_code=existing.employee_code, email="old@acme.example", first_name="Old",
            last_name="Timer", hire_date="2020-01-01", salary="1650000",
            salary_effective_date="2026-10-01", salary_reason="merit"),
    )  # fmt: skip
    job = start(admin_client, data).json()
    assert job["status"] == "queued"

    run_worker(session_factory, storage)
    job = admin_client.get(f"{API}/{job['id']}").json()
    assert job["status"] == "validated"
    assert (job["total_rows"], job["processed_rows"], job["create_count"], job["update_count"]) == (
        2,
        2,
        1,
        1,
    )
    rows = admin_client.get(f"{API}/{job['id']}/rows").json()
    assert [r["action"] for r in rows["items"]] == ["create", "update"]
    assert not list(storage.root.glob("imports/*"))  # raw file removed after checking

    assert (
        admin_client.post(f"{API}/{job['id']}/commit", json={}).json()["status"] == "commit_queued"
    )
    run_worker(session_factory, storage)
    job = admin_client.get(f"{API}/{job['id']}").json()
    assert (job["status"], job["created_count"], job["updated_count"]) == ("completed", 1, 1)

    db.expire_all()
    new = db.query(Employee).filter_by(employee_code="ACM-100001").one()
    assert (new.current_salary, new.current_currency, str(new.current_salary_usd)) == (
        1840000,
        "INR",
        "22080.00",
    )
    assert db.get(Employee, existing.id).current_salary == 1650000
    record = db.query(SalaryRecord).filter_by(employee_id=existing.id, reason="merit").one()
    assert record.import_job_id == job["id"]
    assert db.get(Employee, untouched.id).version == 1  # people missing from the file never change


def test_problems_block_all_or_nothing_but_correct_rows_can_be_saved(
    admin_client, session_factory, storage, db
):
    data = csv_file(row(), row(employee_code="ACM-100002", email="b@acme.example", salary="abc"))
    job_id = start(admin_client, data).json()["id"]
    run_worker(session_factory, storage)
    assert admin_client.get(f"{API}/{job_id}").json()["error_count"] == 1

    blocked = admin_client.post(f"{API}/{job_id}/commit", json={"mode": "all_or_nothing"})
    assert blocked.status_code == 409

    report = list(csv.DictReader(io.StringIO(admin_client.get(f"{API}/{job_id}/errors.csv").text)))
    assert [(r["row"], r["salary"], r["problems"]) for r in report] == [
        ("3", "abc", "salary: Must be a number")
    ]
    errors = admin_client.get(f"{API}/{job_id}/rows", params={"action": "error"}).json()
    assert errors["total"] == 1 and errors["items"][0]["row_number"] == 3

    admin_client.post(f"{API}/{job_id}/commit", json={"mode": "valid_rows_only"})
    run_worker(session_factory, storage)
    assert admin_client.get(f"{API}/{job_id}").json()["created_count"] == 1
    assert db.query(Employee).count() == 1


def test_only_one_import_at_a_time_and_cancel(admin_client, session_factory, storage):
    first = start(admin_client, csv_file(row())).json()
    busy = start(admin_client, csv_file(row(employee_code="ACM-2")))
    assert busy.status_code == 409
    assert busy.json()["error"]["details"]["import_id"] == first["id"]
    cancelled = admin_client.post(f"{API}/{first['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert admin_client.post(f"{API}/{first['id']}/cancel").status_code == 409
    assert admin_client.post(f"{API}/{first['id']}/commit", json={}).status_code == 409
    assert start(admin_client, csv_file(row(employee_code="ACM-2"))).status_code == 202


def test_same_upload_twice_starts_one_job(admin_client, db):
    key = str(uuid.uuid4())
    first, second = (
        start(admin_client, csv_file(row()), key=key),
        start(admin_client, csv_file(row()), key=key),
    )
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert db.query(ImportJob).count() == 1


def test_commit_twice_with_same_key_queues_once(admin_client, session_factory, storage):
    job_id = start(admin_client, csv_file(row())).json()["id"]
    run_worker(session_factory, storage)
    key = str(uuid.uuid4())
    first = admin_client.post(f"{API}/{job_id}/commit", json={}, headers={"Idempotency-Key": key})
    second = admin_client.post(f"{API}/{job_id}/commit", json={}, headers={"Idempotency-Key": key})
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_reimporting_the_same_file_is_flagged(admin_client, session_factory, storage):
    data = csv_file(row())
    job_id = start(admin_client, data).json()["id"]
    run_worker(session_factory, storage)
    admin_client.post(f"{API}/{job_id}/commit", json={})
    run_worker(session_factory, storage)
    again = start(admin_client, data).json()
    assert again["already_imported_at"] is not None
    run_worker(session_factory, storage)
    assert admin_client.get(f"{API}/{again['id']}").json()["unchanged_count"] == 1


def test_employee_changed_after_check_stops_all_or_nothing(
    admin_client, make_employee, session_factory, storage, db
):
    e = make_employee(email="x@acme.example", first_name="X", last_name="Y", country_code="IN",
                      salary="1000000", hire_date="2024-01-01")  # fmt: skip
    data = csv_file(row(), row(employee_code=e.employee_code, email="x@acme.example", first_name="X",
                               last_name="Y", hire_date="2024-01-01", salary="1100000"))  # fmt: skip
    job_id = start(admin_client, data).json()["id"]
    run_worker(session_factory, storage)
    admin_client.patch(f"/api/v1/employees/{e.id}", json={"version": 1, "city": "Goa"})
    admin_client.post(f"{API}/{job_id}/commit", json={})
    run_worker(session_factory, storage)

    job = admin_client.get(f"{API}/{job_id}").json()
    assert (
        job["status"] == "failed" and "The employee changed after the check" in job["error_message"]
    )
    db.expire_all()
    assert db.query(Employee).count() == 1  # the new row was rolled back too
    assert db.get(Employee, e.id).current_salary == 1000000


def test_code_or_email_taken_after_the_check(
    admin_client, make_employee, session_factory, storage, db
):
    data = csv_file(
        row(employee_code="ACM-000001"),
        row(employee_code="ACM-100002", email="b@acme.example"),
        row(employee_code="ACM-100003", email="c@acme.example"),
    )
    job_id = start(admin_client, data).json()["id"]
    run_worker(session_factory, storage)
    assert admin_client.get(f"{API}/{job_id}").json()["create_count"] == 3
    # While the import waits for review, the UI adds ACM-000001 and someone with b@.
    make_employee()
    make_employee(email="b@acme.example")

    admin_client.post(f"{API}/{job_id}/commit", json={"mode": "valid_rows_only"})
    run_worker(session_factory, storage)
    job = admin_client.get(f"{API}/{job_id}").json()
    assert (job["status"], job["created_count"], job["error_count"]) == ("completed", 1, 2)
    errors = admin_client.get(f"{API}/{job_id}/rows", params={"action": "error"}).json()
    assert [(r["row_number"], r["errors"][0]["field"]) for r in errors["items"]] == [
        (2, "employee_code"),
        (3, "email"),
    ]
    db.expire_all()
    assert db.query(Employee).filter_by(employee_code="ACM-100003").count() == 1


def test_code_taken_after_the_check_stops_all_or_nothing(
    admin_client, make_employee, session_factory, storage, db
):
    job_id = start(admin_client, csv_file(row(employee_code="ACM-000001"))).json()["id"]
    run_worker(session_factory, storage)
    make_employee()
    admin_client.post(f"{API}/{job_id}/commit", json={"mode": "all_or_nothing"})
    run_worker(session_factory, storage)
    job = admin_client.get(f"{API}/{job_id}").json()
    assert job["status"] == "failed"
    assert job["error_message"].startswith("Row 2, employee_code: Taken by an employee")
    db.expire_all()
    assert db.query(Employee).count() == 1


def test_failure_in_the_middle_of_apply_saves_nothing(
    admin_client, session_factory, storage, db, monkeypatch
):
    data = csv_file(row(), row(employee_code="ACM-100002", email="b@acme.example"))
    job_id = start(admin_client, data).json()["id"]
    run_worker(session_factory, storage)
    admin_client.post(f"{API}/{job_id}/commit", json={})

    real_create = service._create_from_row
    calls = []

    def create_then_fail(*args):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("disk full")
        return real_create(*args)

    monkeypatch.setattr(service, "_create_from_row", create_then_fail)
    run_worker(session_factory, storage)
    job = admin_client.get(f"{API}/{job_id}").json()
    assert job["status"] == "failed"
    assert db.query(Employee).count() == 0


@pytest.mark.parametrize(
    ("name", "data", "message"),
    [
        ("people.csv", b"first_name\nAsha\n", "Missing columns"),
        ("people.csv", HEADER.encode() + b"\n", "no data rows"),
    ],
)
def test_bad_files_fail_with_a_clear_message(
    admin_client, session_factory, storage, name, data, message
):
    job_id = start(admin_client, data, name=name).json()["id"]
    run_worker(session_factory, storage)
    job = admin_client.get(f"{API}/{job_id}").json()
    assert job["status"] == "failed" and message in job["error_message"]
    assert not (storage.root / "imports" / job_id).exists()  # a failed job's file is not kept


def test_row_limit(admin_client, session_factory, storage, monkeypatch):
    monkeypatch.setattr(service.get_settings(), "max_import_rows", 1)
    job_id = start(
        admin_client, csv_file(row(), row(employee_code="ACM-2", email="b@acme.example"))
    ).json()["id"]
    run_worker(session_factory, storage)
    assert "limit is 1" in admin_client.get(f"{API}/{job_id}").json()["error_message"]


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("macro.xlsm", b"PK\x03\x04..."),
        ("binary.csv", b"\x00\x01\x02\xff\xfe"),
        ("old.xls", b"\xd0\xcf"),
    ],
)
def test_wrong_file_types_are_refused_at_upload(admin_client, name, data):
    assert start(admin_client, data, name=name).status_code == 422


def test_xlsx_files_are_read(admin_client, session_factory, storage):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(COLUMNS)
    sheet.append([row()[c] for c in COLUMNS])
    out = io.BytesIO()
    workbook.save(out)
    job_id = start(admin_client, out.getvalue(), name="people.xlsx").json()["id"]
    run_worker(session_factory, storage)
    assert admin_client.get(f"{API}/{job_id}").json()["create_count"] == 1


def test_interrupted_jobs_are_requeued(db, admin, frozen_clock):
    quiet = frozen_clock.current - timedelta(minutes=16)
    db.add_all([
        ImportJob(id="a", filename="a.csv", file_sha256="1", status="validating", created_by=admin.id,
                  heartbeat_at=quiet),
        ImportJob(id="b", filename="b.csv", file_sha256="2", status="committing", created_by=admin.id),
        # Another worker is still on this one.
        ImportJob(id="c", filename="c.csv", file_sha256="3", status="committing", created_by=admin.id,
                  heartbeat_at=frozen_clock.current - timedelta(minutes=1)),
    ])  # fmt: skip
    db.commit()
    service.reset_stuck_jobs(db)
    service.reset_stuck_jobs(db)  # safe to re-run
    statuses = [db.get(ImportJob, i).status for i in ("a", "b", "c")]
    assert statuses == ["queued", "commit_queued", "committing"]


def test_claiming_and_checking_keep_the_heartbeat_fresh(
    admin_client, session_factory, storage, db, frozen_clock
):
    job_id = start(admin_client, csv_file(row())).json()["id"]
    run_worker(session_factory, storage)
    db.expire_all()
    assert as_utc(db.get(ImportJob, job_id).heartbeat_at) == frozen_clock.current


def test_viewers_cannot_import_but_can_see_history(viewer_client, admin_client):
    assert start(viewer_client, csv_file(row())).status_code == 403
    job_id = start(admin_client, csv_file(row())).json()["id"]
    assert viewer_client.post(f"{API}/{job_id}/commit", json={}).status_code == 403
    assert viewer_client.post(f"{API}/{job_id}/cancel").status_code == 403
    assert viewer_client.get(API).json()["total"] == 1
    assert viewer_client.get(f"{API}/template.xlsx").status_code == 200


def test_unknown_import_is_404(admin_client):
    for path in ("/nope", "/nope/rows", "/nope/errors.csv"):
        assert admin_client.get(API + path).status_code == 404


def test_job_claim_locks_only_the_job_row_on_postgres():
    """Tests run on SQLite, which ignores FOR UPDATE; Postgres rejects it on the outer join
    that loads the job's creator, so the lock must name the job table only."""
    sql = str(service.next_job_query().compile(dialect=postgresql.dialect()))
    assert "LEFT OUTER JOIN users" in sql
    assert sql.endswith("FOR UPDATE OF import_jobs SKIP LOCKED")
