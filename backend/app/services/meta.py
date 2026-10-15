from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_data_version
from app.models import (
    EMPLOYMENT_TYPES,
    GENDERS,
    SALARY_REASONS,
    Country,
    Department,
)
from app.schemas import CountryOut, DepartmentOut, FxRatesOut, MetaOut
from app.services import fx
from app.services.employees import all_job_titles


async def fx_rates(db: AsyncSession) -> FxRatesOut:
    rates = await fx.rates_in_use(db)
    return FxRatesOut(
        rates_date=rates.rates_date, source=rates.source, usd_per_unit=rates.usd_per_unit
    )


async def meta(db: AsyncSession) -> MetaOut:
    countries = await db.scalars(select(Country).order_by(Country.name))
    departments = await db.scalars(select(Department).order_by(Department.name))
    return MetaOut(
        countries=[CountryOut.model_validate(c) for c in countries],
        departments=[DepartmentOut.model_validate(d) for d in departments],
        job_titles=await all_job_titles(db),
        levels=list(range(1, 7)),
        employment_types=list(EMPLOYMENT_TYPES),
        genders=list(GENDERS),
        salary_reasons=list(SALARY_REASONS),
        fx=await fx_rates(db),
        data_version=await get_data_version(db),
    )
