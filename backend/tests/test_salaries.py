import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import event

from app.core import cache
from app.models import SalaryRecord
from app.services import employees as service
from tests.conftest import count

API = "/api/v1/employees"


def change(client, employee_id, key=None, **body):
    payload = {"version": 1, "amount": "110000", "effective_date": "2026-10-01", "reason": "merit"}
    payload.update(body)
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(f"{API}/{employee_id}/salaries", json=payload, headers=headers)


async def test_raise_effective_today_becomes_current(admin_client, make_employee):
    e = await make_employee(salary="100000")
    response = change(admin_client, e.id, effective_date="2026-10-14")
    assert response.status_code == 201
    body = response.json()
    assert (body["current_salary"], body["salary_effective_date"]) == ("110000.00", "2026-10-14")
    assert body["current_salary_usd"] == "110000.00"
    assert body["version"] == 2


async def test_history_is_newest_first_with_change_and_author(admin_client, make_employee):
    e = await make_employee(salary="100000")
    change(admin_client, e.id, amount="110000", effective_date="2026-01-01")
    history = admin_client.get(f"{API}/{e.id}/salaries").json()
    assert [(h["amount"], h["reason"], h["change_pct"]) for h in history] == [
        ("110000.00", "merit", "10.0"),
        ("100000.00", "hire", None),
    ]
    assert history[0]["created_by_name"] == "Priya Admin"
    assert history[0]["is_future"] is False
    assert admin_client.get(f"{API}/999/salaries").status_code == 404


async def test_future_raise_is_upcoming_until_its_date(
    admin_client, make_employee, db, frozen_clock
):
    e = await make_employee(salary="100000")
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
    assert await service.promote_due_salaries(db) == 1
    assert await service.promote_due_salaries(db) == 0  # safe to re-run
    await db.refresh(e)
    assert (e.current_salary, str(e.salary_effective_date)) == (120000, "2026-11-01")


async def test_backdated_correction_only_changes_history(admin_client, make_employee):
    e = await make_employee(salary="100000", hire_date="2022-01-10")
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


async def test_same_day_correction_replaces_current(admin_client, make_employee):
    e = await make_employee(salary="100000")
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


async def test_same_day_correction_before_the_start_date(
    admin_client, make_employee, db, frozen_clock
):
    e = await make_employee(salary="80000", hire_date="2026-11-01")
    body = change(
        admin_client, e.id, amount="85000", effective_date="2026-11-01", reason="correction"
    ).json()
    assert (body["current_salary"], body["upcoming_salary"]) == ("85000.00", None)

    frozen_clock.set(datetime(2026, 11, 2, 1, tzinfo=UTC))
    db.expire_all()
    await service.promote_due_salaries(db)
    await db.refresh(e)
    assert e.current_salary == 85000


async def test_earlier_start_salary_before_the_start_date(admin_client, make_employee):
    e = await make_employee(salary="80000", hire_date="2026-10-20")
    change(admin_client, e.id, amount="82000", effective_date="2026-12-01")
    body = change(
        admin_client, e.id, version=2, amount="81000", effective_date="2026-10-20",
        reason="correction",
    ).json()  # fmt: skip
    # The first day's salary is current; the December raise is still upcoming.
    assert body["current_salary"] == "81000.00"
    assert body["upcoming_salary"]["amount"] == "82000.00"


async def test_salary_in_another_currency_is_converted(admin_client, make_employee):
    e = await make_employee(country_code="IN", salary="1000000")
    body = change(admin_client, e.id, amount="20000", currency="USD").json()
    assert (body["current_currency"], body["current_salary_usd"]) == ("USD", "20000.00")


async def test_same_request_twice_records_one_change(admin_client, make_employee, db):
    e = await make_employee()
    key = str(uuid.uuid4())
    first = change(admin_client, e.id, key=key)
    second = change(admin_client, e.id, key=key)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert await count(db, SalaryRecord, employee_id=e.id) == 2  # hire + one raise


async def test_key_reused_for_another_employee_is_rejected(admin_client, make_employee):
    a, b = await make_employee(), await make_employee()
    key = str(uuid.uuid4())
    change(admin_client, a.id, key=key)
    assert change(admin_client, b.id, key=key).status_code == 409


async def test_stale_version_is_rejected(admin_client, make_employee, db):
    e = await make_employee()
    assert change(admin_client, e.id).status_code == 201
    stale = change(admin_client, e.id, amount="999999")
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    assert await count(db, SalaryRecord, employee_id=e.id) == 2


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
async def test_salary_change_validation(admin_client, make_employee, body, field):
    e = await make_employee(hire_date="2022-01-10")
    response = change(admin_client, e.id, **body)
    assert response.status_code == 422, response.text
    assert field in response.json()["error"]["details"]["fields"]


async def test_one_year_ahead_is_the_limit(admin_client, make_employee):
    e = await make_employee()
    assert change(admin_client, e.id, effective_date="2027-10-15").status_code == 201


async def test_no_salary_changes_for_people_who_left(admin_client, make_employee):
    e = await make_employee()
    admin_client.post(f"{API}/{e.id}/mark-left", json={"version": 1, "left_on": "2026-10-01"})
    response = change(admin_client, e.id, version=2)
    assert response.status_code == 409


async def test_failure_mid_change_saves_nothing(make_employee, admin, db, monkeypatch):
    """Force an error after the history row is added: the whole change must roll back."""
    e = await make_employee(salary="100000")
    version_before = await cache.get_data_version(db)

    async def boom(_db):
        raise RuntimeError("database went away")

    monkeypatch.setattr(service.cache, "bump_data_version", boom)
    data = service.SalaryChangeIn(
        version=1, amount="150000", effective_date="2026-10-01", reason="merit"
    )
    with pytest.raises(RuntimeError):
        await service.change_salary(db, admin, e.id, data)
    await db.rollback()

    await db.refresh(e)
    assert e.current_salary == 100000
    assert e.version == 1
    assert await count(db, SalaryRecord, employee_id=e.id) == 1
    assert await cache.get_data_version(db) == version_before


async def test_current_salary_matches_latest_effective_record(admin_client, make_employee, db):
    """The denormalized current salary must equal the latest entry in effect."""
    e = await make_employee(salary="100000", hire_date="2022-01-10")
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
    await db.refresh(e)  # the API changed the row in another session
    latest = await service.repo.latest_effective_record(db, e.id, e.salary_effective_date)
    assert (e.current_salary, e.salary_effective_date) == (
        latest.amount,
        latest.effective_date,
    )
    assert e.current_salary == 105000


async def test_recent_changes_load_their_employees_in_one_query(make_employee, db):
    for first in ("Asha", "Ben", "Chen"):
        await make_employee(first_name=first, last_name="Lee")
    db.expunge_all()  # nothing cached, so a lookup per entry would show up as a query
    queries = []
    event.listen(db.bind.sync_engine, "before_cursor_execute", lambda *a: queries.append(a[2]))

    feed = await service.recent_changes(db, limit=3)

    assert [c.employee_name for c in feed] == ["Chen Lee", "Ben Lee", "Asha Lee"]
    assert len(queries) == 1


async def test_recent_changes_feed(admin_client, make_employee):
    e = await make_employee(first_name="Mira", last_name="Rao")
    change(admin_client, e.id)
    feed = admin_client.get("/api/v1/salary-changes/recent", params={"limit": 1}).json()
    assert len(feed) == 1
    assert (feed[0]["employee_name"], feed[0]["amount"]) == ("Mira Rao", "110000.00")
    assert admin_client.get("/api/v1/salary-changes/recent", params={"limit": 0}).status_code == 422


async def test_salary_changes_are_paged_newest_first(viewer_client, make_employee):
    for first in ("Asha", "Ben", "Chen"):
        await make_employee(first_name=first, last_name="Lee")

    first = viewer_client.get("/api/v1/salary-changes", params={"page_size": 2}).json()
    assert (first["total"], first["pages"], first["page"]) == (3, 2, 1)
    assert [c["employee_name"] for c in first["items"]] == ["Chen Lee", "Ben Lee"]

    second = viewer_client.get("/api/v1/salary-changes", params={"page": 2, "page_size": 2}).json()
    assert [c["employee_name"] for c in second["items"]] == ["Asha Lee"]

    past_end = viewer_client.get(
        "/api/v1/salary-changes", params={"page": 3, "page_size": 2}
    ).json()
    assert (past_end["items"], past_end["total"]) == ([], 3)


async def test_salary_changes_empty_and_invalid_paging(admin_client, anon_client):
    empty = admin_client.get("/api/v1/salary-changes").json()
    assert (empty["items"], empty["total"], empty["pages"], empty["page_size"]) == ([], 0, 1, 50)
    for params in ({"page": 0}, {"page_size": 0}, {"page_size": 101}):
        assert admin_client.get("/api/v1/salary-changes", params=params).status_code == 422
    assert anon_client.get("/api/v1/salary-changes").status_code == 401
