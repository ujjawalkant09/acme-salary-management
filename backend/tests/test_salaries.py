import uuid
from datetime import UTC, datetime

import pytest

from app.core import cache
from app.models import Employee, SalaryRecord
from app.services import employees as service

API = "/api/v1/employees"


def change(client, employee_id, key=None, **body):
    payload = {"version": 1, "amount": "110000", "effective_date": "2026-10-01", "reason": "merit"}
    payload.update(body)
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(f"{API}/{employee_id}/salaries", json=payload, headers=headers)


def test_raise_effective_today_becomes_current(admin_client, make_employee):
    e = make_employee(salary="100000")
    response = change(admin_client, e.id, effective_date="2026-10-14")
    assert response.status_code == 201
    body = response.json()
    assert (body["current_salary"], body["salary_effective_date"]) == ("110000.00", "2026-10-14")
    assert body["current_salary_usd"] == "110000.00"
    assert body["version"] == 2


def test_history_is_newest_first_with_change_and_author(admin_client, make_employee):
    e = make_employee(salary="100000")
    change(admin_client, e.id, amount="110000", effective_date="2026-01-01")
    history = admin_client.get(f"{API}/{e.id}/salaries").json()
    assert [(h["amount"], h["reason"], h["change_pct"]) for h in history] == [
        ("110000.00", "merit", "10.0"),
        ("100000.00", "hire", None),
    ]
    assert history[0]["created_by_name"] == "Priya Admin"
    assert history[0]["is_future"] is False
    assert admin_client.get(f"{API}/999/salaries").status_code == 404


def test_future_raise_is_upcoming_until_its_date(admin_client, make_employee, db, frozen_clock):
    e = make_employee(salary="100000")
    body = change(admin_client, e.id, amount="120000", effective_date="2026-11-01").json()
    assert body["current_salary"] == "100000.00"
    assert body["upcoming_salary"] == {
        "amount": "120000.00",
        "currency": "USD",
        "effective_date": "2026-11-01",
    }
    assert body["version"] == 2  # still a new version, so other open edits are stale

    frozen_clock.set(datetime(2026, 11, 1, 1, tzinfo=UTC))
    db.expire_all()  # the API changed the row in another session
    assert service.promote_due_salaries(db) == 1
    assert service.promote_due_salaries(db) == 0  # safe to re-run
    db.refresh(e)
    assert (e.current_salary, str(e.salary_effective_date)) == (120000, "2026-11-01")


def test_backdated_correction_only_changes_history(admin_client, make_employee):
    e = make_employee(salary="100000", hire_date="2022-01-10")
    change(admin_client, e.id, amount="110000", effective_date="2025-01-01")
    body = change(
        admin_client,
        e.id,
        version=2,
        amount="105000",
        effective_date="2024-01-01",
        reason="correction",
    ).json()
    assert body["current_salary"] == "110000.00"


def test_same_day_correction_replaces_current(admin_client, make_employee):
    e = make_employee(salary="100000")
    change(admin_client, e.id, amount="110000", effective_date="2026-10-01")
    body = change(
        admin_client,
        e.id,
        version=2,
        amount="111000",
        effective_date="2026-10-01",
        reason="correction",
    ).json()
    assert body["current_salary"] == "111000.00"


def test_same_day_correction_before_the_start_date(admin_client, make_employee, db, frozen_clock):
    e = make_employee(salary="80000", hire_date="2026-11-01")
    body = change(
        admin_client, e.id, amount="85000", effective_date="2026-11-01", reason="correction"
    ).json()
    assert (body["current_salary"], body["upcoming_salary"]) == ("85000.00", None)

    frozen_clock.set(datetime(2026, 11, 2, 1, tzinfo=UTC))
    db.expire_all()
    service.promote_due_salaries(db)
    db.refresh(e)
    assert e.current_salary == 85000


def test_earlier_start_salary_before_the_start_date(admin_client, make_employee):
    e = make_employee(salary="80000", hire_date="2026-10-20")
    change(admin_client, e.id, amount="82000", effective_date="2026-12-01")
    body = change(
        admin_client, e.id, version=2, amount="81000", effective_date="2026-10-20",
        reason="correction",
    ).json()  # fmt: skip
    # The first day's salary is current; the December raise is still upcoming.
    assert body["current_salary"] == "81000.00"
    assert body["upcoming_salary"]["amount"] == "82000.00"


def test_salary_in_another_currency_is_converted(admin_client, make_employee):
    e = make_employee(country_code="IN", salary="1000000")
    body = change(admin_client, e.id, amount="20000", currency="USD").json()
    assert (body["current_currency"], body["current_salary_usd"]) == ("USD", "20000.00")


def test_same_request_twice_records_one_change(admin_client, make_employee, db):
    e = make_employee()
    key = str(uuid.uuid4())
    first = change(admin_client, e.id, key=key)
    second = change(admin_client, e.id, key=key)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert db.query(SalaryRecord).filter_by(employee_id=e.id).count() == 2  # hire + one raise


def test_key_reused_for_another_employee_is_rejected(admin_client, make_employee):
    a, b = make_employee(), make_employee()
    key = str(uuid.uuid4())
    change(admin_client, a.id, key=key)
    assert change(admin_client, b.id, key=key).status_code == 409


def test_stale_version_is_rejected(admin_client, make_employee, db):
    e = make_employee()
    assert change(admin_client, e.id).status_code == 201
    stale = change(admin_client, e.id, amount="999999")
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    assert db.query(SalaryRecord).filter_by(employee_id=e.id).count() == 2


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"amount": "0"}, "amount"),
        ({"amount": "-100"}, "amount"),
        ({"amount": "12.345"}, "amount"),
        ({"amount": "1000000000000"}, "amount"),
        ({"reason": "hire"}, "reason"),
        ({"effective_date": "2021-12-31"}, "effective_date"),  # before hire
        ({"effective_date": "2027-10-16"}, "effective_date"),  # more than a year ahead
        ({"currency": "EUR"}, "currency"),
        ({"note": "x" * 501}, "note"),
    ],
)
def test_salary_change_validation(admin_client, make_employee, body, field):
    e = make_employee(hire_date="2022-01-10")
    response = change(admin_client, e.id, **body)
    assert response.status_code == 422, response.text
    assert field in response.json()["error"]["details"]["fields"]


def test_one_year_ahead_is_the_limit(admin_client, make_employee):
    e = make_employee()
    assert change(admin_client, e.id, effective_date="2027-10-15").status_code == 201


def test_no_salary_changes_for_people_who_left(admin_client, make_employee):
    e = make_employee()
    admin_client.post(f"{API}/{e.id}/mark-left", json={"version": 1, "left_on": "2026-10-01"})
    response = change(admin_client, e.id, version=2)
    assert response.status_code == 409


def test_failure_mid_change_saves_nothing(make_employee, admin, db, monkeypatch):
    """Force an error after the history row is added: the whole change must roll back."""
    e = make_employee(salary="100000")
    version_before = cache.get_data_version(db)

    def boom(_db):
        raise RuntimeError("database went away")

    monkeypatch.setattr(service.cache, "bump_data_version", boom)
    data = service.SalaryChangeIn(
        version=1, amount="150000", effective_date="2026-10-01", reason="merit"
    )
    with pytest.raises(RuntimeError):
        service.change_salary(db, admin, e.id, data)
    db.rollback()

    db.expire_all()
    fresh = db.get(Employee, e.id)
    assert fresh.current_salary == 100000
    assert fresh.version == 1
    assert db.query(SalaryRecord).filter_by(employee_id=e.id).count() == 1
    assert cache.get_data_version(db) == version_before


def test_current_salary_matches_latest_effective_record(admin_client, make_employee, db):
    """The denormalized current salary must equal the latest entry in effect."""
    e = make_employee(salary="100000", hire_date="2022-01-10")
    change(admin_client, e.id, amount="105000", effective_date="2024-01-01")
    change(
        admin_client,
        e.id,
        version=2,
        amount="103000",
        effective_date="2023-01-01",
        reason="correction",
    )
    change(
        admin_client,
        e.id,
        version=3,
        amount="130000",
        effective_date="2026-12-01",
        reason="promotion",
    )
    db.expire_all()
    fresh = db.get(Employee, e.id)
    latest = service.repo.latest_effective_record(db, e.id, fresh.salary_effective_date)
    assert (fresh.current_salary, fresh.salary_effective_date) == (
        latest.amount,
        latest.effective_date,
    )
    assert fresh.current_salary == 105000


def test_recent_changes_feed(admin_client, make_employee):
    e = make_employee(first_name="Mira", last_name="Rao")
    change(admin_client, e.id)
    feed = admin_client.get("/api/v1/salary-changes/recent", params={"limit": 1}).json()
    assert len(feed) == 1
    assert (feed[0]["employee_name"], feed[0]["amount"]) == ("Mira Rao", "110000.00")
    assert admin_client.get("/api/v1/salary-changes/recent", params={"limit": 0}).status_code == 422
