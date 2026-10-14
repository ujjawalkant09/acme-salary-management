from datetime import UTC, date, datetime
from decimal import Decimal

import httpx

from app.core import cache
from app.models import AppState, Employee, FxRate
from app.services import fx


def fake_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def ecb_response(rate_date="2026-10-14", inr=80):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["base"] == "USD"
        assert "USD" not in request.url.params["symbols"].split(",")
        return httpx.Response(200, json={
            "base": "USD", "date": rate_date,
            "rates": {"INR": inr, "CAD": 1.25, "SGD": 1.25, "BRL": 5, "AUD": 1.6},
        })  # fmt: skip

    return handler


def test_daily_refresh_stores_rates_and_updates_usd_salaries(db, make_employee):
    e = make_employee(country_code="IN", salary="1000000")
    version = cache.get_data_version(db)
    assert fx.refresh_daily_rates(db, fake_client(ecb_response(inr=80)))
    db.refresh(e)
    assert e.current_salary_usd == Decimal("12500.00")  # 1,000,000 / 80
    rates = fx.rates_in_use(db)
    assert rates.usd_per_unit["INR"] == Decimal("0.0125000000")
    assert rates.source == fx.SOURCE
    assert cache.get_data_version(db) > version


def test_refresh_runs_once_a_day(db):
    calls = []

    def handler(request):
        calls.append(request)
        return ecb_response()(request)

    client = fake_client(handler)
    assert fx.refresh_daily_rates(db, client)
    assert not fx.refresh_daily_rates(db, client)
    assert len(calls) == 1


def test_failed_fetch_keeps_last_good_rates(db, make_employee):
    e = make_employee(country_code="IN", salary="1000000")
    client = fake_client(lambda request: httpx.Response(503))
    assert not fx.refresh_daily_rates(db, client)
    db.refresh(e)
    assert e.current_salary_usd == Decimal("12000.00")
    assert db.get(AppState, 1).fx_checked_on is None  # tries again on the next run


def test_garbage_response_is_a_failed_fetch(db):
    assert not fx.refresh_daily_rates(
        db, fake_client(lambda r: httpx.Response(200, json={"oops": 1}))
    )


def test_storing_the_same_date_twice_upserts(db, frozen_clock):
    client = fake_client(ecb_response(inr=80))
    fx.refresh_daily_rates(db, client)
    frozen_clock.set(datetime(2026, 10, 15, 17, tzinfo=UTC))  # next day, ECB has no new date yet
    fx.refresh_daily_rates(db, fake_client(ecb_response(inr=82)))
    rows = db.query(FxRate).filter_by(currency="INR", rate_date=date(2026, 10, 14)).all()
    assert len(rows) == 1
    assert rows[0].usd_per_unit == Decimal("0.0121951220")  # 1 / 82, the newer value


def test_missing_currency_keeps_its_previous_rate(db, make_employee):
    e = make_employee(country_code="BR", salary="100000")

    def handler(request):
        return httpx.Response(200, json={"date": "2026-10-15", "rates": {"INR": 80}})

    fx.refresh_daily_rates(db, fake_client(handler))
    db.refresh(e)
    assert fx.rates_in_use(db).usd_per_unit["BRL"] == Decimal("0.1800000000")
    assert e.current_salary_usd == Decimal("18000.00")
    assert fx.rates_in_use(db).rates_date == date(2026, 10, 15)


def test_to_usd_rounds_to_cents_and_rejects_unknown_currency():
    rates = fx.Rates(date(2026, 1, 1), {"INR": Decimal("0.0119")}, "x")
    assert rates.to_usd(Decimal("1234567"), "INR") == Decimal("14691.35")
    try:
        rates.to_usd(Decimal(1), "EUR")
    except ValueError as exc:
        assert "EUR" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_fx_rates_endpoint(admin_client):
    body = admin_client.get("/api/v1/fx-rates").json()
    assert body["rates_date"] == "2026-10-14"
    assert body["usd_per_unit"]["USD"] == "1.0000000000"


def test_no_employee_usd_drift_after_refresh(db, make_employee):
    for country, amount in (("IN", "2500000"), ("US", "90000"), ("AU", "120000")):
        make_employee(country_code=country, salary=amount)
    fx.refresh_daily_rates(db, fake_client(ecb_response()))
    rates = fx.rates_in_use(db)
    for e in db.query(Employee):
        db.refresh(e)
        assert e.current_salary_usd == rates.to_usd(e.current_salary, e.current_currency)


def test_refresh_leaves_who_and_when_alone(db, make_employee, frozen_clock):
    e = make_employee(country_code="IN", salary="2500000")
    edited_at, version = e.updated_at, e.version
    frozen_clock.set(datetime(2026, 10, 20, 17, tzinfo=UTC))
    fx.refresh_daily_rates(db, fake_client(ecb_response()))
    db.refresh(e)
    assert e.current_salary_usd == Decimal("31250.00")
    assert (e.updated_at, e.version) == (edited_at, version)


def test_refresh_rounds_half_cents_like_the_app(db, make_employee):
    e = make_employee(country_code="IN", salary="100.04")
    fx.store_rates(db, date(2026, 10, 15), {"INR": Decimal("0.125")}, "test")
    db.commit()
    db.refresh(e)
    assert e.current_salary_usd == Decimal("12.50")  # 12.505, half to even
    assert e.current_salary_usd == fx.rates_in_use(db).to_usd(e.current_salary, "INR")
