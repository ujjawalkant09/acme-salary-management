from sqlalchemy import select
from sqlalchemy.orm import Session

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


def fx_rates(db: Session) -> FxRatesOut:
    rates = fx.rates_in_use(db)
    return FxRatesOut(
        rates_date=rates.rates_date, source=rates.source, usd_per_unit=rates.usd_per_unit
    )


def meta(db: Session) -> MetaOut:
    return MetaOut(
        countries=[
            CountryOut.model_validate(c) for c in db.scalars(select(Country).order_by(Country.name))
        ],
        departments=[
            DepartmentOut.model_validate(d)
            for d in db.scalars(select(Department).order_by(Department.name))
        ],
        job_titles=all_job_titles(db),
        levels=list(range(1, 7)),
        employment_types=list(EMPLOYMENT_TYPES),
        genders=list(GENDERS),
        salary_reasons=list(SALARY_REASONS),
        fx=fx_rates(db),
        data_version=get_data_version(db),
    )
