"""Exchange rates: daily ECB reference rates (via Frankfurter), stored by date.

The newest stored date is "the rates in use". If a fetch fails, the last good rates stay.
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import httpx
from sqlalchemy import bindparam, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

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


async def rates_in_use(db: AsyncSession) -> Rates:
    """The latest stored rate for each currency."""
    latest = (
        select(FxRate.currency, func.max(FxRate.rate_date).label("rate_date"))
        .group_by(FxRate.currency)
        .subquery()
    )
    rows = await db.scalars(
        select(FxRate).join(
            latest,
            (FxRate.currency == latest.c.currency) & (FxRate.rate_date == latest.c.rate_date),
        )
    )
    rates = {row.currency: row for row in rows}
    if not rates:
        return Rates(None, {}, None)
    newest = max(rates.values(), key=lambda r: r.rate_date)
    return Rates(
        rates_date=newest.rate_date,
        usd_per_unit={code: r.usd_per_unit for code, r in rates.items()},
        source=newest.source,
    )


async def supported_currencies(db: AsyncSession) -> list[str]:
    return sorted(set(await db.scalars(select(Country.currency))))


async def fetch_ecb_rates(
    client: httpx.AsyncClient, currencies: list[str]
) -> tuple[date, dict[str, Decimal]]:
    """Ask Frankfurter for 1 USD in each currency and invert to USD per unit."""
    symbols = [c for c in currencies if c != "USD"]
    response = await client.get(
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


async def store_rates(
    db: AsyncSession, rate_date: date, usd_per_unit: dict[str, Decimal], source: str
) -> None:
    """Upsert rates for one date and refresh every employee's USD salary, in one transaction."""
    for currency, rate in usd_per_unit.items():
        await db.merge(
            FxRate(currency=currency, rate_date=rate_date, usd_per_unit=rate, source=source)
        )
    await db.flush()
    await refresh_usd_salaries(db)
    await cache.bump_data_version(db)


async def refresh_usd_salaries(db: AsyncSession) -> None:
    """Recompute every USD salary with the same rounding as `Rates.to_usd`. Written to the
    table directly, so `updated_at` and `version` stay as the last real edit left them."""
    rates = await rates_in_use(db)
    people = await db.execute(
        select(Employee.id, Employee.current_salary, Employee.current_currency)
    )
    values = [
        {"row_id": employee_id, "usd": rates.to_usd(amount, currency)}
        for employee_id, amount, currency in people
        if currency in rates.usd_per_unit
    ]
    if not values:
        return
    table = Employee.__table__
    await db.execute(
        update(table)
        .where(table.c.id == bindparam("row_id"))
        .values(current_salary_usd=bindparam("usd"), updated_at=table.c.updated_at),
        values,
    )


async def refresh_daily_rates(db: AsyncSession, client: httpx.AsyncClient) -> bool:
    """Fetch today's rates once a day. Returns True when new rates were stored.

    On any failure the previous rates stay in use and a warning is logged.
    """
    state = await db.get(AppState, 1)
    if state.fx_checked_on == today():
        return False
    try:
        rate_date, usd_per_unit = await fetch_ecb_rates(client, await supported_currencies(db))
    except (httpx.HTTPError, KeyError, ValueError, ArithmeticError) as exc:
        log.warning(
            "fx fetch failed; keeping the last good rates", extra={"fields": {"error": str(exc)}}
        )
        return False
    missing = set(await supported_currencies(db)) - set(usd_per_unit)
    if missing:
        log.warning("fx fetch missing currencies", extra={"fields": {"missing": sorted(missing)}})
    await store_rates(db, rate_date, usd_per_unit, SOURCE)
    state.fx_checked_on = today()
    await db.commit()
    return True
