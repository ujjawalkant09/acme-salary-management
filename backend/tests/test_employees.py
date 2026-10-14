import csv
import io
import uuid
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core import idempotency
from app.core.clock import now
from app.core.errors import Conflict
from app.models import Employee, IdempotencyKey, SalaryRecord
from app.services import employees as service

API = "/api/v1/employees"

NEW_EMPLOYEE = {
    "first_name": "Asha",
    "last_name": "Verma",
    "email": "Asha.Verma@acme.example",
    "job_title": "Software Engineer",
    "job_level": 3,
    "department_id": 1,
    "country_code": "IN",
    "employment_type": "full_time",
    "hire_date": "2025-04-01",
    "gender": "female",
    "salary": {"amount": "1840000"},
}


# ---------- list, search, filters ----------
def test_list_is_paginated_with_envelope(admin_client, make_employee):
    for _ in range(3):
        make_employee()
    body = admin_client.get(API, params={"page_size": 2}).json()
    assert (body["total"], body["pages"], body["page"], len(body["items"])) == (3, 2, 1, 2)
    assert admin_client.get(API, params={"page": 2, "page_size": 2}).json()["items"][0]
    assert admin_client.get(API, params={"page": 9}).json()["items"] == []


def test_list_items_never_include_gender(admin_client, make_employee):
    make_employee(gender="female")
    item = admin_client.get(API).json()["items"][0]
    assert "gender" not in item
    assert item["current_salary"] == "100000.00"  # money is a string


@pytest.mark.parametrize(
    "params",
    [{"page_size": 101}, {"page_size": 0}, {"page": 0}, {"sort": "password"}, {"level": 7}],
)
def test_list_rejects_bad_parameters(admin_client, params):
    response = admin_client.get(API, params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid"


def test_search_matches_name_email_and_code(admin_client, make_employee):
    make_employee(first_name="Zara", last_name="Khan")
    other = make_employee()
    assert [
        e["first_name"] for e in admin_client.get(API, params={"q": "zara k"}).json()["items"]
    ] == ["Zara"]
    assert admin_client.get(API, params={"q": other.employee_code}).json()["total"] == 1
    assert admin_client.get(API, params={"q": "person2@"}).json()["total"] == 1
    # LIKE wildcards are matched literally
    assert admin_client.get(API, params={"q": "%"}).json()["total"] == 0


def test_filters_combine(admin_client, make_employee):
    make_employee(country_code="IN", salary="1000000", job_level=2)
    make_employee(country_code="IN", salary="3000000", job_level=4)
    make_employee(country_code="US", salary="150000", job_level=4, department_id=2,
                  employment_type="contractor", job_title="Data Engineer")  # fmt: skip
    get = lambda **p: admin_client.get(API, params=p).json()["total"]  # noqa: E731
    assert get(country="IN") == 2
    assert get(country=["IN", "US"]) == 3
    assert get(level=4) == 2
    assert get(country="IN", level=4) == 1
    assert get(min_salary_usd="20000") == 2  # 1,000,000 INR = 12,000 USD
    assert get(max_salary_usd="12000") == 1
    assert get(department_id=2) == 1
    assert get(department_id=[1, 2]) == 3
    assert get(employment_type="contractor") == 1
    assert get(job_title="  data ENGINEER ") == 1  # case and spaces don't matter


def test_sort_by_salary_desc_with_stable_ties(admin_client, make_employee):
    a = make_employee(salary="50000")
    b = make_employee(salary="90000")
    c = make_employee(salary="90000")
    ids = [
        e["id"]
        for e in admin_client.get(API, params={"sort": "salary", "order": "desc"}).json()["items"]
    ]
    assert ids == [c.id, b.id, a.id]


def test_status_filter_defaults_to_current(admin_client, make_employee, admin, db):
    make_employee()
    gone = make_employee()
    gone.status = "left"
    db.commit()
    assert admin_client.get(API).json()["total"] == 1
    assert admin_client.get(API, params={"status": "left"}).json()["total"] == 1
    assert admin_client.get(API, params={"status": "all"}).json()["total"] == 2


def test_facets_count_each_option_given_the_other_filters(admin_client, make_employee):
    make_employee(country_code="IN", job_level=2)
    make_employee(country_code="IN", job_level=4)
    make_employee(country_code="US", job_level=4)
    facets = admin_client.get(f"{API}/facets", params={"country": "IN"}).json()
    # The country facet ignores its own filter, so other countries still show counts.
    assert facets["country"] == {"IN": 2, "US": 1}
    assert facets["level"] == {"2": 1, "4": 1}
    assert facets["status"] == {"active": 2}


def test_empty_database_gives_empty_results(admin_client):
    assert admin_client.get(API).json() == {
        "items": [],
        "page": 1,
        "page_size": 20,
        "total": 0,
        "pages": 1,
    }
    assert admin_client.get(f"{API}/facets").json()["country"] == {}


# ---------- profile ----------
def test_profile_and_not_found(admin_client, make_employee):
    e = make_employee(gender="male")
    body = admin_client.get(f"{API}/{e.id}").json()
    assert body["gender"] == "male"
    assert body["version"] == 1
    assert body["updated_by_name"] == "Priya Admin"
    assert body["rates_date"] == "2026-10-14"
    missing = admin_client.get(f"{API}/99999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_profile_compares_with_peers(admin_client, make_employee):
    for salary in ("90000", "100000", "110000", "120000"):
        make_employee(salary=salary)
    target = make_employee(salary="200000")
    peers = admin_client.get(f"{API}/{target.id}").json()["peers"]
    assert peers["count"] == 5
    assert peers["median"] == "110000.00"
    assert peers["diff_from_median_pct"] == "81.8"
    assert peers["is_outlier"] is True


def test_part_timers_are_compared_at_full_time_rate(admin_client, make_employee):
    make_employee(salary="100000")
    half = make_employee(salary="50000", employment_type="part_time", fte="0.5")
    peers = admin_client.get(f"{API}/{half.id}").json()["peers"]
    assert peers["employee_value"] == "100000.00"
    assert peers["diff_from_median_pct"] == "0.0"


# ---------- create ----------
def test_create_employee_with_first_salary(admin_client, db):
    response = admin_client.post(
        API, json=NEW_EMPLOYEE, headers={"Idempotency-Key": str(uuid.uuid4())}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["employee_code"] == "ACM-000001"
    assert body["email"] == "asha.verma@acme.example"
    assert (body["current_salary"], body["current_currency"]) == ("1840000.00", "INR")
    assert body["current_salary_usd"] == "22080.00"
    records = db.query(SalaryRecord).filter_by(employee_id=body["id"]).all()
    assert [(r.reason, str(r.effective_date)) for r in records] == [("hire", "2025-04-01")]


def test_create_twice_with_same_key_creates_one_employee(admin_client, db):
    key = str(uuid.uuid4())
    first = admin_client.post(API, json=NEW_EMPLOYEE, headers={"Idempotency-Key": key})
    second = admin_client.post(API, json=NEW_EMPLOYEE, headers={"Idempotency-Key": key})
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert db.query(Employee).count() == 1


def test_same_key_with_different_body_is_rejected(admin_client):
    key = str(uuid.uuid4())
    admin_client.post(API, json=NEW_EMPLOYEE, headers={"Idempotency-Key": key})
    changed = {**NEW_EMPLOYEE, "first_name": "Someone else"}
    response = admin_client.post(API, json=changed, headers={"Idempotency-Key": key})
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == "idempotency_key_reused"


def test_lost_stored_response_never_repeats_the_work(db, admin, monkeypatch):
    calls = []

    def work():
        calls.append(1)
        db.commit()  # the service's own commit saves the work and the key together
        return {"ok": True}

    real_commit = db.commit
    commits = []

    def lose_the_second_commit():
        commits.append(1)
        if len(commits) == 2:  # the one that stores the response
            raise OperationalError("COMMIT", {}, Exception("connection lost"))
        real_commit()

    monkeypatch.setattr(db, "commit", lose_the_second_commit)
    response = idempotency.run(db, admin, "k1", "test", {"a": 1}, work, status_code=201)
    assert (response.status_code, response.body) == (201, b'{"ok":true}')

    monkeypatch.setattr(db, "commit", real_commit)
    with pytest.raises(Conflict) as retry:
        idempotency.run(db, admin, "k1", "test", {"a": 1}, work, status_code=201)
    assert retry.value.details["reason"] == "idempotency_in_progress"
    assert calls == [1]


def test_blank_idempotency_key_is_rejected(admin_client, db):
    response = admin_client.post(API, json=NEW_EMPLOYEE, headers={"Idempotency-Key": ""})
    assert response.status_code == 422
    assert db.query(Employee).count() == 0


def test_same_key_racing_another_request_gets_its_response(db, admin, session_factory):
    def work():
        # Another request with the same key commits first...
        with session_factory() as other:
            other.add(IdempotencyKey(key="k1", user_id=admin.id, endpoint="test",
                                     request_hash=idempotency.request_hash({"a": 1}),
                                     status_code=201, response_body={"id": 7},
                                     expires_at=now() + timedelta(hours=1)))  # fmt: skip
            other.commit()
        db.commit()  # ...so saving our copy of the key fails, and our work with it
        return {"id": 8}

    response = idempotency.run(db, admin, "k1", "test", {"a": 1}, work, status_code=201)
    assert (response.status_code, response.body) == (201, b'{"id":7}')


def test_other_integrity_errors_are_not_taken_for_a_replay(db, admin):
    def work():
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: employees.email"))

    with pytest.raises(IntegrityError):
        idempotency.run(db, admin, "k2", "test", {}, work)
    assert db.get(IdempotencyKey, ("k2", admin.id)) is None


def test_failed_create_does_not_burn_the_key(admin_client, db):
    key = str(uuid.uuid4())
    bad = {**NEW_EMPLOYEE, "department_id": 999}
    assert admin_client.post(API, json=bad, headers={"Idempotency-Key": key}).status_code == 422
    # The key wasn't stored, so the corrected request with a new body is not a replay.
    good = admin_client.post(API, json=NEW_EMPLOYEE, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert good.status_code == 201


def test_expired_key_can_be_used_again(admin_client, frozen_clock, db):
    from datetime import timedelta

    key = str(uuid.uuid4())
    admin_client.post(API, json=NEW_EMPLOYEE, headers={"Idempotency-Key": key})
    frozen_clock.set(frozen_clock.current + timedelta(hours=25))
    again = {**NEW_EMPLOYEE, "email": "other@acme.example"}
    assert admin_client.post(API, json=again, headers={"Idempotency-Key": key}).status_code == 201
    assert db.query(Employee).count() == 2


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"department_id": 999}, "department_id"),
        ({"country_code": "FR"}, "country_code"),
        ({"job_level": 0}, "job_level"),
        ({"fte": "1.5"}, "fte"),
        ({"salary": {"amount": "0"}}, "salary.amount"),
        ({"salary": {"amount": "-5"}}, "salary.amount"),
        ({"salary": {"amount": "100", "currency": "EUR"}}, "currency"),
        ({"salary": {"amount": "100", "effective_date": "2025-01-01"}}, "effective_date"),
        ({"first_name": "  "}, "first_name"),
    ],
)
def test_create_validation(admin_client, change, field):
    response = admin_client.post(API, json={**NEW_EMPLOYEE, **change})
    assert response.status_code == 422, response.text
    assert field in response.json()["error"]["details"]["fields"]


def test_create_with_duplicate_email_conflicts(admin_client, make_employee):
    make_employee(email="asha.verma@acme.example")
    response = admin_client.post(API, json=NEW_EMPLOYEE)
    assert response.status_code == 409
    assert "email" in response.json()["error"]["details"]["fields"]


def test_duplicate_email_slipping_past_the_check_is_a_conflict(
    admin_client, make_employee, monkeypatch, db
):
    make_employee(email="asha.verma@acme.example")
    # Two requests at once: both pass the check, the database's unique index stops the second.
    monkeypatch.setattr(service, "_check_email_free", lambda *args: None)
    response = admin_client.post(API, json=NEW_EMPLOYEE)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert db.query(Employee).count() == 1


def test_future_joiner_has_salary_from_first_entry(admin_client):
    body = admin_client.post(API, json={**NEW_EMPLOYEE, "hire_date": "2026-12-01"}).json()
    assert body["salary_effective_date"] == "2026-12-01"
    assert body["current_salary"] == "1840000.00"


# ---------- roles ----------
def test_viewers_cannot_change_anything(viewer_client, make_employee, db):
    e = make_employee()
    attempts = [
        viewer_client.post(API, json=NEW_EMPLOYEE),
        viewer_client.patch(f"{API}/{e.id}", json={"version": 1, "city": "X"}),
        viewer_client.post(f"{API}/{e.id}/mark-left", json={"version": 1, "left_on": "2026-10-01"}),
        viewer_client.post(f"{API}/{e.id}/reactivate", json={"version": 1}),
        viewer_client.post(f"{API}/{e.id}/salaries", json={"version": 1, "amount": "1", "effective_date": "2026-10-01", "reason": "merit"}),
        viewer_client.put(f"{API}/{e.id}/photo", files={"file": ("a.png", b"x")}),
        viewer_client.delete(f"{API}/{e.id}/photo"),
        viewer_client.post(f"{API}/{e.id}/documents", files={"file": ("a.pdf", b"%PDF-1")}),
        viewer_client.delete(f"{API}/{e.id}/documents/1"),
    ]  # fmt: skip
    for response in attempts:
        assert response.status_code == 403, response.request.url
        assert response.json()["error"]["code"] == "forbidden"
    db.refresh(e)
    assert e.version == 1


def test_viewers_can_read(viewer_client, make_employee):
    e = make_employee()
    assert viewer_client.get(API).status_code == 200
    assert viewer_client.get(f"{API}/{e.id}").status_code == 200
    assert viewer_client.get(f"{API}/{e.id}/salaries").status_code == 200


# ---------- edit, leave, reactivate ----------
def test_edit_changes_only_sent_fields_and_bumps_version(admin_client, make_employee):
    e = make_employee(city="Austin")
    body = admin_client.patch(
        f"{API}/{e.id}", json={"version": 1, "job_level": 4, "country_code": "CA"}
    ).json()
    assert (body["job_level"], body["country_code"], body["city"], body["version"]) == (
        4, "CA", "Austin", 2,
    )  # fmt: skip


def test_edit_with_nothing_to_change_keeps_the_version(admin_client, make_employee):
    e = make_employee()
    assert admin_client.patch(f"{API}/{e.id}", json={"version": 1}).json()["version"] == 1


def test_edit_racing_another_save_returns_409(
    admin_client, make_employee, session_factory, db, monkeypatch
):
    e = make_employee()
    real_bump = service.cache.bump_data_version

    def someone_saves_first(session):
        with session_factory() as other:
            other.get(Employee, e.id).city = "Theirs"
            other.commit()
        real_bump(session)

    monkeypatch.setattr(service.cache, "bump_data_version", someone_saves_first)
    response = admin_client.patch(f"{API}/{e.id}", json={"version": 1, "city": "Mine"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_conflict"
    db.refresh(e)
    assert e.city == "Theirs"


def test_stale_edit_returns_409_and_changes_nothing(admin_client, make_employee, db):
    e = make_employee()
    assert admin_client.patch(f"{API}/{e.id}", json={"version": 1, "city": "A"}).status_code == 200
    stale = admin_client.patch(f"{API}/{e.id}", json={"version": 1, "city": "B"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    db.refresh(e)
    assert e.city == "A"


def test_edit_validation(admin_client, make_employee):
    a = make_employee()
    make_employee(email="taken@acme.example")
    cases = [
        ({"version": 1, "email": "TAKEN@acme.example"}, 409),
        ({"version": 1, "first_name": None}, 422),
        ({"version": 1, "department_id": 999}, 422),
        ({"version": 1, "country_code": "FR"}, 422),  # not a country the app uses
        ({"version": 1, "hire_date": "2023-01-01"}, 422),  # after the first salary entry
        ({"city": "x"}, 422),  # version is required
    ]
    for body, status in cases:
        assert admin_client.patch(f"{API}/{a.id}", json=body).status_code == status, body
    assert admin_client.patch(f"{API}/99999", json={"version": 1}).status_code == 404


def test_edit_can_clear_optional_fields(admin_client, make_employee):
    e = make_employee(city="Austin", gender="male")
    body = admin_client.patch(
        f"{API}/{e.id}", json={"version": 1, "city": None, "gender": None}
    ).json()
    assert body["city"] is None and body["gender"] is None


def test_mark_left_and_reactivate(admin_client, make_employee):
    e = make_employee()
    left = admin_client.post(
        f"{API}/{e.id}/mark-left", json={"version": 1, "left_on": "2026-09-30"}
    )
    assert left.json()["status"] == "left" and left.json()["left_on"] == "2026-09-30"
    again = admin_client.post(
        f"{API}/{e.id}/mark-left", json={"version": 2, "left_on": "2026-09-30"}
    )
    assert again.status_code == 409
    back = admin_client.post(f"{API}/{e.id}/reactivate", json={"version": 2})
    assert back.json()["status"] == "active" and back.json()["left_on"] is None
    assert admin_client.post(f"{API}/{e.id}/reactivate", json={"version": 3}).status_code == 409


def test_cannot_leave_before_joining(admin_client, make_employee):
    e = make_employee(hire_date="2022-01-10")
    response = admin_client.post(
        f"{API}/{e.id}/mark-left", json={"version": 1, "left_on": "2021-12-31"}
    )
    assert response.status_code == 422


def test_marking_left_twice_with_same_version_is_safe(admin_client, make_employee):
    e = make_employee()
    body = {"version": 1, "left_on": "2026-09-30"}
    assert admin_client.post(f"{API}/{e.id}/mark-left", json=body).status_code == 200
    assert admin_client.post(f"{API}/{e.id}/mark-left", json=body).status_code == 409


# ---------- export ----------
def test_export_csv_uses_filters_and_leaves_out_gender(admin_client, make_employee):
    make_employee(country_code="IN", gender="female", salary="900000")
    make_employee(country_code="US")
    response = admin_client.get(f"{API}/export.csv", params={"country": "IN"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1
    assert "gender" not in rows[0]
    assert rows[0]["salary"] == "900000.00" and rows[0]["currency"] == "INR"


def test_export_blocks_spreadsheet_formulas(admin_client, make_employee):
    make_employee(first_name="=HYPERLINK(1)", last_name="+cmd", city="-1+1", job_title="-12.5")
    row = next(csv.DictReader(io.StringIO(admin_client.get(f"{API}/export.csv").text)))
    assert row["first_name"] == "'=HYPERLINK(1)"
    assert row["last_name"] == "'+cmd"
    assert row["city"] == "'-1+1"
    assert row["job_title"] == "-12.5"  # a plain number is not a formula and stays as it is


def test_meta_lists_reference_data(admin_client, make_employee):
    make_employee(job_title="Data Engineer")
    body = admin_client.get("/api/v1/meta").json()
    assert [c["code"] for c in body["countries"]] == ["AU", "BR", "CA", "IN", "SG", "US"]
    assert body["job_titles"] == ["Data Engineer"]
    assert body["fx"]["usd_per_unit"]["INR"] == "0.0120000000"
    assert body["levels"] == [1, 2, 3, 4, 5, 6]
