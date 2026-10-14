from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.core import cache
from app.core.auth import DB, CurrentUser
from app.core.clock import today
from app.core.errors import NotFound
from app.core.rate_limit import INSIGHTS, limiter
from app.models import Country
from app.schemas import DistributionOut, GroupStatsOut, OutlierOut, Page, Summary
from app.services import insights as service

router = APIRouter(prefix="/insights", tags=["insights"])

CountryParam = Annotated[str | None, Query(pattern=r"^[A-Z]{2}$")]


def _check_country(db: DB, code: str | None) -> None:
    if code is not None and db.get(Country, code) is None:
        raise NotFound("Unknown country.")


@router.get("/summary", response_model=Summary)
@limiter.limit(INSIGHTS)
def summary(request: Request, response: Response, db: DB, _user: CurrentUser):
    # "Next 7 days" depends on the date, so the date is part of the cache key.
    return cache.cached_json(
        request, response, db, "summary", {"today": today()}, lambda: service.summary(db)
    )


@router.get("/by-country", response_model=GroupStatsOut)
@limiter.limit(INSIGHTS)
def by_country(request: Request, response: Response, db: DB, _user: CurrentUser):
    return cache.cached_json(
        request, response, db, "by-country", {}, lambda: service.by_country(db)
    )


@router.get("/by-department", response_model=GroupStatsOut)
@limiter.limit(INSIGHTS)
def by_department(request: Request, response: Response, db: DB, _user: CurrentUser):
    return cache.cached_json(
        request, response, db, "by-department", {}, lambda: service.by_department(db)
    )


@router.get("/by-role", response_model=GroupStatsOut)
@limiter.limit(INSIGHTS)
def by_role(
    request: Request,
    response: Response,
    db: DB,
    _user: CurrentUser,
    country: Annotated[str, Query(pattern=r"^[A-Z]{2}$")],
):
    _check_country(db, country)
    return cache.cached_json(
        request, response, db, "by-role", {"country": country}, lambda: service.by_role(db, country)
    )


@router.get("/distribution", response_model=DistributionOut)
@limiter.limit(INSIGHTS)
def distribution(
    request: Request,
    response: Response,
    db: DB,
    _user: CurrentUser,
    country: CountryParam = None,
    bins: Annotated[int, Query(ge=2, le=50)] = 20,
):
    _check_country(db, country)
    params = {"country": country, "bins": bins}
    return cache.cached_json(
        request, response, db, "distribution", params,
        lambda: service.distribution(db, country, bins),
    )  # fmt: skip


@router.get("/outliers", response_model=Page[OutlierOut])
@limiter.limit(INSIGHTS)
def outliers(
    request: Request,
    response: Response,
    db: DB,
    _user: CurrentUser,
    country: CountryParam = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    _check_country(db, country)
    params = {"country": country, "page": page, "page_size": page_size}
    return cache.cached_json(
        request, response, db, "outliers", params,
        lambda: service.outlier_page(db, country, page, page_size),
    )  # fmt: skip
