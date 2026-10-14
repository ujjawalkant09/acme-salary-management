"""Exchange rates: daily ECB reference rates (via Frankfurter), stored by date.

The newest stored date is "the rates in use". If a fetch fails, the last good rates stay.
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import cache
from app.core.clock import today
from app.core.config import get_settings
from app.models import AppState, Country, Employee, FxRate
from app.services.stats import CENT

log = logging.getLogger(__name__)

SOURCE = "ECB via Frankfurter"


@dataclass(frozen=True)
class Rates:
    rates_date: date | None
    usd_per_unit: dict[str, Decimal]
    source: str | None

    def to_usd(self, amount: Decimal, currency: str) -> Decimal:
        rate = self.usd_per_unit.get(currency)
        if rate is None:
            raise ValueError(f"No exchange rate for {currency}")
        return (amount * rate).quantize(CENT)


def rates_in_use(db: Session) -> Rates:
    """The latest stored rate for each currency."""
    latest = (
        select(FxRate.currency, func.max(FxRate.rate_date).label("rate_date"))
        .group_by(FxRate.currency)
        .subquery()
    )
    rows = db.execute(
        select(FxRate).join(
            latest,
            (FxRate.currency == latest.c.currency) & (FxRate.rate_date == latest.c.rate_date),
        )
    ).scalars()
    rates = {row.currency: row for row in rows}
    if not rates:
        return Rates(None, {}, None)
    newest = max(rates.values(), key=lambda r: r.rate_date)
    return Rates(
        rates_date=newest.rate_date,
        usd_per_unit={code: r.usd_per_unit for code, r in rates.items()},
        source=newest.source,
    )


def supported_currencies(db: Session) -> list[str]:
    return sorted(set(db.scalars(select(Country.currency))))


def fetch_ecb_rates(client: httpx.Client, currencies: list[str]) -> tuple[date, dict[str, Decimal]]:
    """Ask Frankfurter for 1 USD in each currency and invert to USD per unit."""
    symbols = [c for c in currencies if c != "USD"]
    response = client.get(
        get_settings().fx_api_url, params={"base": "USD", "symbols": ",".join(symbols)}
    )
    response.raise_for_status()
    data = response.json()
    per_usd = {code: Decimal(str(value)) for code, value in data["rates"].items()}
    usd_per_unit = {
        code: (Decimal(1) / rate).quantize(Decimal("1e-10")) for code, rate in per_usd.items()
    }
    usd_per_unit["USD"] = Decimal(1)
    return date.fromisoformat(data["date"]), usd_per_unit


def store_rates(
    db: Session, rate_date: date, usd_per_unit: dict[str, Decimal], source: str
) -> None:
    """Upsert rates for one date and refresh every employee's USD salary, in one transaction."""
    for currency, rate in usd_per_unit.items():
        db.merge(FxRate(currency=currency, rate_date=rate_date, usd_per_unit=rate, source=source))
    db.flush()
    refresh_usd_salaries(db)
    cache.bump_data_version(db)


def refresh_usd_salaries(db: Session) -> None:
    rates = rates_in_use(db)
    for currency, rate in rates.usd_per_unit.items():
        db.execute(
            update(Employee)
            .where(Employee.current_currency == currency)
            .values(current_salary_usd=func.round(Employee.current_salary * rate, 2))
            .execution_options(synchronize_session=False)
        )


def refresh_daily_rates(db: Session, client: httpx.Client) -> bool:
    """Fetch today's rates once a day. Returns True when new rates were stored.

    On any failure the previous rates stay in use and a warning is logged.
    """
    state = db.get(AppState, 1)
    if state.fx_checked_on == today():
        return False
    try:
        rate_date, usd_per_unit = fetch_ecb_rates(client, supported_currencies(db))
    except (httpx.HTTPError, KeyError, ValueError, ArithmeticError) as exc:
        log.warning(
            "fx fetch failed; keeping the last good rates", extra={"fields": {"error": str(exc)}}
        )
        return False
    missing = set(supported_currencies(db)) - set(usd_per_unit)
    if missing:
        log.warning("fx fetch missing currencies", extra={"fields": {"missing": sorted(missing)}})
    store_rates(db, rate_date, usd_per_unit, SOURCE)
    state.fx_checked_on = today()
    db.commit()
    return True
