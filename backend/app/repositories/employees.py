"""Employee queries: filters, sort, pagination and facet counts."""

from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Department, Employee, SalaryRecord, User
from app.schemas import EmployeeFilters, EmployeeListParams

SORT_COLUMNS = {
    "name": (Employee.last_name, Employee.first_name),
    "salary": (Employee.current_salary_usd,),
    "hire_date": (Employee.hire_date,),
    "country": (Employee.country_code,),
    "job_title": (Employee.job_title, Employee.job_level),
    "code": (Employee.employee_code,),
}

# Salary normalized to full time, used for every peer comparison (part-timers compared at
# the full-time rate).
FTE_SALARY = Employee.current_salary / Employee.fte


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def apply_filters(
    query: Select, filters: EmployeeFilters, skip: str | None = None, outlier_ids=None
) -> Select:
    """Add WHERE clauses for every active filter. `skip` leaves one facet's own filter out,
    so its option counts show what each choice would match."""
    if filters.status != "all" and skip != "status":
        query = query.where(Employee.status == filters.status)
    if filters.q:
        term = f"%{_escape_like(filters.q.lower())}%"
        full_name = func.lower(Employee.first_name + " " + Employee.last_name)
        query = query.where(
            or_(
                full_name.like(term, escape="\\"),
                func.lower(Employee.email).like(term, escape="\\"),
                func.lower(Employee.employee_code).like(term, escape="\\"),
            )
        )
    if filters.country and skip != "country":
        query = query.where(Employee.country_code.in_(filters.country))
    if filters.department_id and skip != "department_id":
        query = query.where(Employee.department_id.in_(filters.department_id))
    if filters.level and skip != "level":
        query = query.where(Employee.job_level.in_(filters.level))
    if filters.employment_type and skip != "employment_type":
        query = query.where(Employee.employment_type.in_(filters.employment_type))
    if filters.job_title:
        query = query.where(func.lower(Employee.job_title) == filters.job_title.strip().lower())
    if filters.min_salary_usd is not None:
        query = query.where(Employee.current_salary_usd >= filters.min_salary_usd)
    if filters.max_salary_usd is not None:
        query = query.where(Employee.current_salary_usd <= filters.max_salary_usd)
    if outlier_ids is not None:
        query = query.where(Employee.id.in_(outlier_ids))
    return query


async def list_page(
    db: AsyncSession, params: EmployeeListParams, outlier_ids=None
) -> tuple[list[Employee], int]:
    base = apply_filters(select(Employee), params, outlier_ids=outlier_ids)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    columns = SORT_COLUMNS[params.sort]
    order = [c.desc() if params.order == "desc" else c.asc() for c in columns]
    order.append(Employee.id.desc() if params.order == "desc" else Employee.id.asc())
    rows = await db.scalars(
        base.order_by(*order).offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    return list(rows), total


async def iter_filtered(
    db: AsyncSession, filters: EmployeeFilters, outlier_ids=None
) -> AsyncIterator[Employee]:
    query = apply_filters(select(Employee), filters, outlier_ids=outlier_ids)
    query = query.order_by(Employee.last_name, Employee.first_name, Employee.id)
    async for employee in await db.stream_scalars(query.execution_options(yield_per=1000)):
        yield employee


async def facet_counts(
    db: AsyncSession, filters: EmployeeFilters, column, skip: str, outlier_ids=None
) -> dict:
    query = apply_filters(
        select(column, func.count()).select_from(Employee), filters, skip, outlier_ids
    )
    return {key: count for key, count in await db.execute(query.group_by(column))}


async def get(db: AsyncSession, employee_id: int) -> Employee | None:
    return await db.get(Employee, employee_id)


async def email_taken(db: AsyncSession, email: str, exclude_id: int | None = None) -> bool:
    query = select(Employee.id).where(Employee.email == email)
    if exclude_id is not None:
        query = query.where(Employee.id != exclude_id)
    return await db.scalar(query) is not None


async def next_employee_code(db: AsyncSession) -> str:
    codes = await db.scalars(
        select(Employee.employee_code).where(Employee.employee_code.like("ACM-%"))
    )
    highest = max((int(c[4:]) for c in codes if c[4:].isdigit()), default=0)
    return f"ACM-{highest + 1:06d}"


async def peer_salaries(db: AsyncSession, employee: Employee) -> list[Decimal]:
    """Full-time-equivalent salaries of active people with the same role, level and country,
    in the employee's currency."""
    return list(
        await db.scalars(
            select(FTE_SALARY).where(
                Employee.status == "active",
                Employee.country_code == employee.country_code,
                Employee.job_title == employee.job_title,
                Employee.job_level == employee.job_level,
                Employee.current_currency == employee.current_currency,
            )
        )
    )


async def salary_records(db: AsyncSession, employee_id: int) -> list[SalaryRecord]:
    """Newest first; ties broken by the order they were recorded."""
    return list(
        await db.scalars(
            select(SalaryRecord)
            .where(SalaryRecord.employee_id == employee_id)
            .order_by(SalaryRecord.effective_date.desc(), SalaryRecord.id.desc())
        )
    )


async def latest_effective_record(
    db: AsyncSession, employee_id: int, on: date
) -> SalaryRecord | None:
    return await db.scalar(
        select(SalaryRecord)
        .where(SalaryRecord.employee_id == employee_id, SalaryRecord.effective_date <= on)
        .order_by(SalaryRecord.effective_date.desc(), SalaryRecord.id.desc())
        .limit(1)
    )


async def next_future_record(
    db: AsyncSession, employee_id: int, after: date
) -> SalaryRecord | None:
    return await db.scalar(
        select(SalaryRecord)
        .where(SalaryRecord.employee_id == employee_id, SalaryRecord.effective_date > after)
        .order_by(SalaryRecord.effective_date.asc(), SalaryRecord.id.desc())
        .limit(1)
    )


async def employees_with_due_salary(db: AsyncSession, on: date) -> list[int]:
    """Employees with a salary entry that has taken effect but is not yet their current one."""
    return list(
        await db.scalars(
            select(Employee.id)
            .join(SalaryRecord, SalaryRecord.employee_id == Employee.id)
            .where(
                SalaryRecord.effective_date <= on,
                SalaryRecord.effective_date > Employee.salary_effective_date,
            )
            .distinct()
        )
    )


async def recent_salary_changes(db: AsyncSession, limit: int) -> list[SalaryRecord]:
    return list(
        await db.scalars(
            select(SalaryRecord)
            .options(joinedload(SalaryRecord.creator))
            .order_by(SalaryRecord.created_at.desc(), SalaryRecord.id.desc())
            .limit(limit)
        )
    )


async def count_upcoming_changes(db: AsyncSession, start: date, end: date) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(SalaryRecord)
        .join(Employee, Employee.id == SalaryRecord.employee_id)
        .where(
            Employee.status == "active",
            SalaryRecord.effective_date > start,
            SalaryRecord.effective_date <= end,
        )
    )


async def user_name(db: AsyncSession, user_id: int | None) -> str | None:
    return await db.scalar(select(User.name).where(User.id == user_id)) if user_id else None


async def department_exists(db: AsyncSession, department_id: int) -> bool:
    return await db.get(Department, department_id) is not None
