"""Pay insights. Counts and sums are simple; medians and percentiles are computed in Python
over sorted values (portable between SQLite and Postgres, and fast at 10,000 rows).

Comparisons use full-time-equivalent pay (salary / FTE); costs use actual pay.
Across countries amounts are in USD; within one country, in that country's currency.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.core.clock import today
from app.models import Country, Department, Employee
from app.repositories import employees as repo
from app.schemas import (
    DistributionOut,
    GroupStats,
    GroupStatsOut,
    HistogramBin,
    OutlierOut,
    Page,
    Summary,
)
from app.services import fx
from app.services.stats import CENT, Spread, histogram, median, pct_diff, spread


@dataclass(frozen=True)
class Row:
    id: int
    code: str
    name: str
    job_title: str
    job_level: int
    country_code: str
    department: str
    currency: str
    salary: Decimal
    fte_salary: Decimal
    salary_usd: Decimal
    fte_salary_usd: Decimal

    @property
    def peer_key(self) -> tuple:
        return (self.country_code, self.job_title, self.job_level, self.currency)


@dataclass(frozen=True)
class Outlier:
    row: Row
    peers: Spread


async def _active_rows(db: AsyncSession) -> list[Row]:
    query = (
        select(
            Employee.id,
            Employee.employee_code,
            Employee.first_name,
            Employee.last_name,
            Employee.job_title,
            Employee.job_level,
            Employee.country_code,
            Department.name,
            Employee.current_currency,
            Employee.current_salary,
            Employee.fte,
            Employee.current_salary_usd,
        )
        .join(Department, Department.id == Employee.department_id)
        .where(Employee.status == "active")
    )
    return [
        Row(
            id=r[0],
            code=r[1],
            name=f"{r[2]} {r[3]}",
            job_title=r[4],
            job_level=r[5],
            country_code=r[6],
            department=r[7],
            currency=r[8],
            salary=r[9],
            fte_salary=r[9] / r[10],
            salary_usd=r[11],
            fte_salary_usd=r[11] / r[10],
        )
        for r in await db.execute(query)
    ]


async def outliers(db: AsyncSession) -> dict[int, Outlier]:
    """Everyone paid outside 1.5 × IQR of their peers (same role, level, country, currency)."""

    async def build() -> dict[int, Outlier]:
        groups: dict[tuple, list[Row]] = defaultdict(list)
        for row in await _active_rows(db):
            groups[row.peer_key].append(row)
        found = {}
        for rows in groups.values():
            peers = spread([r.fte_salary for r in rows])
            for row in rows:
                if peers.is_outlier(row.fte_salary):
                    found[row.id] = Outlier(row, peers)
        return found

    return await cache.get_or_build(db, "outliers", {}, build)


async def outlier_ids(db: AsyncSession, country: str | None = None) -> list[int]:
    found = await outliers(db)
    return [i for i, o in found.items() if country is None or o.row.country_code == country]


async def summary(db: AsyncSession) -> Summary:
    rows = await _active_rows(db)
    start = today()
    return Summary(
        headcount=len(rows),
        payroll_usd=sum((r.salary_usd for r in rows), Decimal(0)),
        median_salary_usd=median([r.fte_salary_usd for r in rows]) if rows else Decimal(0),
        rates_date=(await fx.rates_in_use(db)).rates_date,
        outlier_count=len(await outliers(db)),
        upcoming_changes_7d=await repo.count_upcoming_changes(db, start, start + timedelta(days=7)),
        countries=len({r.country_code for r in rows}),
    )


def _group(key: str, label: str, values: list[Decimal], costs: list[Decimal], currency: str):
    s = spread(values)
    return GroupStats(
        key=key,
        label=label,
        people=s.count,
        currency=currency,
        cost=sum(costs, Decimal(0)).quantize(CENT),
        min=s.min,
        p25=s.p25,
        median=s.median,
        p75=s.p75,
        max=s.max,
    )


async def by_country(db: AsyncSession) -> GroupStatsOut:
    """Per country in its own currency (people paid in another currency are converted
    through USD), plus the median and cost in USD for comparison."""
    rates = await fx.rates_in_use(db)
    countries = {c.code: c for c in await db.scalars(select(Country))}
    grouped: dict[str, list[Row]] = defaultdict(list)
    for row in await _active_rows(db):
        grouped[row.country_code].append(row)
    groups = []
    for code, rows in sorted(grouped.items()):
        country = countries[code]
        rate = rates.usd_per_unit[country.currency]
        group = _group(
            code,
            country.name,
            [r.fte_salary_usd / rate for r in rows],
            [r.salary_usd / rate for r in rows],
            country.currency,
        )
        group.median_usd = median([r.fte_salary_usd for r in rows])
        group.cost_usd = sum((r.salary_usd for r in rows), Decimal(0))
        groups.append(group)
    return GroupStatsOut(rates_date=rates.rates_date, groups=groups)


async def by_department(db: AsyncSession) -> GroupStatsOut:
    grouped: dict[str, list[Row]] = defaultdict(list)
    for row in await _active_rows(db):
        grouped[row.department].append(row)
    groups = [
        _group(
            name,
            name,
            [r.fte_salary_usd for r in rows],
            [r.salary_usd for r in rows],
            "USD",
        )
        for name, rows in sorted(grouped.items())
    ]
    return GroupStatsOut(rates_date=(await fx.rates_in_use(db)).rates_date, groups=groups)


async def by_role(db: AsyncSession, country_code: str) -> GroupStatsOut:
    """Each role and level within one country, in that country's currency."""
    rates = await fx.rates_in_use(db)
    country = await db.get(Country, country_code)
    rate = rates.usd_per_unit[country.currency]
    flagged = await outliers(db)
    grouped: dict[tuple[str, int], list[Row]] = defaultdict(list)
    for row in await _active_rows(db):
        if row.country_code == country_code:
            grouped[(row.job_title, row.job_level)].append(row)
    groups = []
    for (title, level), rows in sorted(grouped.items()):
        group = _group(
            f"{title}|{level}",
            title,
            [r.fte_salary_usd / rate for r in rows],
            [r.salary_usd / rate for r in rows],
            country.currency,
        )
        group.job_level = level
        group.outliers = sum(1 for r in rows if r.id in flagged)
        groups.append(group)
    return GroupStatsOut(rates_date=rates.rates_date, groups=groups)


async def distribution(db: AsyncSession, country_code: str | None, bins: int) -> DistributionOut:
    rows = [r for r in await _active_rows(db) if country_code in (None, r.country_code)]
    if country_code is None:
        values, currency = [r.fte_salary_usd for r in rows], "USD"
    else:
        currency = (await db.get(Country, country_code)).currency
        rate = (await fx.rates_in_use(db)).usd_per_unit[currency]
        values = [r.fte_salary_usd / rate for r in rows]
    return DistributionOut(
        currency=currency,
        bins=[HistogramBin(start=s, end=e, count=c) for s, e, c in histogram(values, bins)],
    )


async def outlier_page(
    db: AsyncSession, country_code: str | None, page: int, page_size: int
) -> Page[OutlierOut]:
    items = []
    for o in (await outliers(db)).values():
        if country_code not in (None, o.row.country_code):
            continue
        diff = pct_diff(o.row.fte_salary, o.peers.median)
        items.append(
            OutlierOut(
                employee_id=o.row.id,
                employee_code=o.row.code,
                name=o.row.name,
                job_title=o.row.job_title,
                job_level=o.row.job_level,
                country_code=o.row.country_code,
                department=o.row.department,
                salary=o.row.salary,
                currency=o.row.currency,
                peer_median=o.peers.median,
                peer_count=o.peers.count,
                diff_from_median_pct=diff,
                direction="above" if diff > 0 else "below",
            )
        )
    items.sort(key=lambda item: (-abs(item.diff_from_median_pct), item.employee_id))
    start = (page - 1) * page_size
    return Page.of(items[start : start + page_size], len(items), page, page_size)
