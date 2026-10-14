"""Employee business rules: create, edit, leave/reactivate and salary changes.

Every write runs in one transaction: the change, the audit fields (who/when) and the
data-version bump are committed together at the end, or not at all.
"""

import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import cache
from app.core.clock import now, today
from app.core.errors import Conflict, InvalidInput, NotFound, VersionConflict
from app.core.storage import signed_url
from app.models import Country, Employee, SalaryRecord, User
from app.repositories import employees as repo
from app.schemas import (
    EmployeeCreate,
    EmployeeFilters,
    EmployeeListItem,
    EmployeeListParams,
    EmployeeOut,
    EmployeeUpdate,
    Facets,
    MarkLeftIn,
    Page,
    PeerStats,
    ReactivateIn,
    RecentSalaryChange,
    SalaryChangeIn,
    SalaryRecordOut,
    UpcomingSalary,
)
from app.services import fx, insights
from app.services.stats import pct_diff, spread

# Salary changes can be planned up to a year ahead.
MAX_FUTURE = timedelta(days=366)


# ---------- reading ----------
def get_or_404(db: Session, employee_id: int) -> Employee:
    employee = repo.get(db, employee_id)
    if employee is None:
        raise NotFound("Employee not found.")
    return employee


def _list_fields(e: Employee) -> dict:
    return {
        "id": e.id,
        "employee_code": e.employee_code,
        "first_name": e.first_name,
        "last_name": e.last_name,
        "email": e.email,
        "job_title": e.job_title,
        "job_level": e.job_level,
        "department_id": e.department_id,
        "department": e.department.name,
        "country_code": e.country_code,
        "city": e.city,
        "employment_type": e.employment_type,
        "fte": e.fte,
        "status": e.status,
        "current_salary": e.current_salary,
        "current_currency": e.current_currency,
        "current_salary_usd": e.current_salary_usd,
    }


def _outlier_ids(db: Session, filters: EmployeeFilters) -> list[int] | None:
    return insights.outlier_ids(db) if filters.outliers_only else None


def list_employees(db: Session, params: EmployeeListParams) -> Page[EmployeeListItem]:
    rows, total = repo.list_page(db, params, _outlier_ids(db, params))
    items = [EmployeeListItem(**_list_fields(e)) for e in rows]
    return Page.of(items, total, params.page, params.page_size)


def facets(db: Session, filters: EmployeeFilters) -> Facets:
    ids = _outlier_ids(db, filters)
    return Facets(
        status=repo.facet_counts(db, filters, Employee.status, "status", ids),
        country=repo.facet_counts(db, filters, Employee.country_code, "country", ids),
        department_id=repo.facet_counts(db, filters, Employee.department_id, "department_id", ids),
        level=repo.facet_counts(db, filters, Employee.job_level, "level", ids),
        employment_type=repo.facet_counts(
            db, filters, Employee.employment_type, "employment_type", ids
        ),
    )


def _peer_stats(db: Session, employee: Employee) -> PeerStats | None:
    if employee.status != "active":
        return None
    values = repo.peer_salaries(db, employee)
    if len(values) < 2:
        return None
    peers = spread(values)
    own = employee.current_salary / employee.fte
    return PeerStats(
        count=peers.count,
        currency=employee.current_currency,
        min=peers.min,
        p25=peers.p25,
        median=peers.median,
        p75=peers.p75,
        max=peers.max,
        employee_value=own,
        diff_from_median_pct=pct_diff(own, peers.median),
        is_outlier=peers.is_outlier(own),
    )


def profile(db: Session, employee: Employee) -> EmployeeOut:
    upcoming = repo.next_future_record(
        db, employee.id, max(today(), employee.salary_effective_date)
    )
    return EmployeeOut(
        **_list_fields(employee),
        gender=employee.gender,
        hire_date=employee.hire_date,
        left_on=employee.left_on,
        salary_effective_date=employee.salary_effective_date,
        version=employee.version,
        photo_url=(
            signed_url(employee.photo_key, "photo.webp", "image/webp", inline=True)
            if employee.photo_key
            else None
        ),
        created_at=employee.created_at,
        updated_at=employee.updated_at,
        updated_by_name=repo.user_name(db, employee.updated_by),
        rates_date=fx.rates_in_use(db).rates_date,
        upcoming_salary=(
            UpcomingSalary(
                amount=upcoming.amount,
                currency=upcoming.currency,
                effective_date=upcoming.effective_date,
            )
            if upcoming
            else None
        ),
        peers=_peer_stats(db, employee),
    )


def salary_history(db: Session, employee_id: int) -> list[SalaryRecordOut]:
    get_or_404(db, employee_id)
    records = repo.salary_records(db, employee_id)
    history = []
    for index, record in enumerate(records):
        previous = records[index + 1] if index + 1 < len(records) else None
        change = (
            pct_diff(record.amount, previous.amount)
            if previous and previous.currency == record.currency
            else None
        )
        history.append(
            SalaryRecordOut(
                id=record.id,
                amount=record.amount,
                currency=record.currency,
                effective_date=record.effective_date,
                reason=record.reason,
                note=record.note,
                change_pct=change,
                created_by_name=record.creator.name if record.creator else None,
                created_at=record.created_at,
                from_import=record.import_job_id is not None,
                is_future=record.effective_date > today(),
            )
        )
    return history


def recent_changes(db: Session, limit: int) -> list[RecentSalaryChange]:
    changes = []
    for record in repo.recent_salary_changes(db, limit):
        employee = db.get(Employee, record.employee_id)
        changes.append(
            RecentSalaryChange(
                id=record.id,
                employee_id=employee.id,
                employee_name=f"{employee.first_name} {employee.last_name}",
                employee_code=employee.employee_code,
                amount=record.amount,
                currency=record.currency,
                effective_date=record.effective_date,
                reason=record.reason,
                created_by_name=record.creator.name if record.creator else None,
                created_at=record.created_at,
            )
        )
    return changes


# ---------- validation helpers ----------
def _check_country(db: Session, code: str) -> Country:
    country = db.get(Country, code)
    if country is None:
        raise InvalidInput("Unknown country.", {"fields": {"country_code": "Unknown country"}})
    return country


def _check_department(db: Session, department_id: int) -> None:
    if not repo.department_exists(db, department_id):
        raise InvalidInput(
            "Unknown department.", {"fields": {"department_id": "Unknown department"}}
        )


def _check_email_free(db: Session, email: str, exclude_id: int | None = None) -> None:
    if repo.email_taken(db, email, exclude_id):
        raise Conflict(
            "Another employee already uses this email.",
            {"fields": {"email": "Already used by another employee"}},
        )


def _check_currency(db: Session, currency: str) -> None:
    if currency not in fx.supported_currencies(db):
        raise InvalidInput(
            f"{currency} is not a supported currency.",
            {"fields": {"currency": "Not a supported currency"}},
        )


def _check_salary_date(effective_date: date, hire_date: date) -> None:
    if effective_date < hire_date:
        raise InvalidInput(
            "The start date can't be before the employee joined.",
            {"fields": {"effective_date": "Before the hire date"}},
        )
    if effective_date > today() + MAX_FUTURE:
        raise InvalidInput(
            "The start date can be at most a year ahead.",
            {"fields": {"effective_date": "More than a year ahead"}},
        )


def _check_version(employee: Employee, version: int) -> None:
    if employee.version != version:
        raise VersionConflict()


# ---------- current salary ----------
def sync_current_salary(db: Session, employee: Employee, rates: fx.Rates) -> None:
    """Point the denormalized current salary at the latest entry that has taken effect
    (or, for someone who hasn't started yet, their first entry)."""
    record = repo.latest_effective_record(db, employee.id, today()) or repo.next_future_record(
        db, employee.id, date.min
    )
    employee.current_salary = record.amount
    employee.current_currency = record.currency
    employee.current_salary_usd = rates.to_usd(record.amount, record.currency)
    employee.salary_effective_date = record.effective_date


def apply_salary_record(employee: Employee, record: SalaryRecord, rates: fx.Rates) -> None:
    """Make a newly added entry the current salary if it is now the latest one in effect.

    Same rule as `sync_current_salary`, without a query (used for bulk imports).
    """
    if employee.salary_effective_date <= today():
        takes_over = employee.salary_effective_date <= record.effective_date <= today()
    else:  # hasn't started yet: the earliest entry is current, the newest one on a tie
        takes_over = record.effective_date <= employee.salary_effective_date
    if takes_over:
        employee.current_salary = record.amount
        employee.current_currency = record.currency
        employee.current_salary_usd = rates.to_usd(record.amount, record.currency)
        employee.salary_effective_date = record.effective_date


def promote_due_salaries(db: Session) -> int:
    """Make future-dated salary entries current once their date arrives. Safe to re-run."""
    ids = repo.employees_with_due_salary(db, today())
    if not ids:
        return 0
    rates = fx.rates_in_use(db)
    for employee_id in ids:
        sync_current_salary(db, db.get(Employee, employee_id), rates)
    cache.bump_data_version(db)
    db.commit()
    return len(ids)


# ---------- writes ----------
def create(db: Session, user: User, data: EmployeeCreate) -> EmployeeOut:
    country = _check_country(db, data.country_code)
    _check_department(db, data.department_id)
    email = data.email.lower()
    _check_email_free(db, email)
    currency = data.salary.currency or country.currency
    _check_currency(db, currency)
    effective_date = data.salary.effective_date or data.hire_date
    _check_salary_date(effective_date, data.hire_date)

    rates = fx.rates_in_use(db)
    employee = Employee(
        employee_code=repo.next_employee_code(db),
        first_name=data.first_name,
        last_name=data.last_name,
        email=email,
        job_title=data.job_title,
        job_level=data.job_level,
        department_id=data.department_id,
        country_code=data.country_code,
        city=data.city,
        gender=data.gender,
        employment_type=data.employment_type,
        fte=data.fte,
        hire_date=data.hire_date,
        current_salary=data.salary.amount,
        current_currency=currency,
        current_salary_usd=rates.to_usd(data.salary.amount, currency),
        salary_effective_date=effective_date,
        updated_by=user.id,
    )
    db.add(employee)
    db.flush()
    db.add(
        SalaryRecord(
            employee_id=employee.id,
            amount=data.salary.amount,
            currency=currency,
            effective_date=effective_date,
            reason="hire",
            note=data.salary.note,
            created_by=user.id,
        )
    )
    cache.bump_data_version(db)
    db.commit()
    return profile(db, employee)


def update(db: Session, user: User, employee_id: int, data: EmployeeUpdate) -> EmployeeOut:
    employee = get_or_404(db, employee_id)
    _check_version(employee, data.version)
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    for field in (
        "first_name",
        "last_name",
        "email",
        "job_title",
        "job_level",
        "department_id",
        "country_code",
        "employment_type",
        "fte",
        "hire_date",
    ):
        if field in changes and changes[field] is None:
            raise InvalidInput(
                "Some fields are not valid.", {"fields": {field: "This field can't be empty"}}
            )
    if "email" in changes:
        changes["email"] = changes["email"].lower()
        _check_email_free(db, changes["email"], employee.id)
    if "country_code" in changes:
        _check_country(db, changes["country_code"])
    if "department_id" in changes:
        _check_department(db, changes["department_id"])
    if "hire_date" in changes:
        first_salary = min(r.effective_date for r in repo.salary_records(db, employee.id))
        if changes["hire_date"] > first_salary:
            raise InvalidInput(
                "The hire date can't be after the first salary entry.",
                {"fields": {"hire_date": "After the first salary entry"}},
            )
    if not changes:
        return profile(db, employee)

    for field, value in changes.items():
        setattr(employee, field, value)
    employee.updated_by = user.id
    cache.bump_data_version(db)
    db.commit()
    return profile(db, employee)


def mark_left(db: Session, user: User, employee_id: int, data: MarkLeftIn) -> EmployeeOut:
    employee = get_or_404(db, employee_id)
    _check_version(employee, data.version)
    if employee.status == "left":
        raise Conflict("This employee is already marked as left.")
    if data.left_on < employee.hire_date:
        raise InvalidInput(
            "The leaving date can't be before the employee joined.",
            {"fields": {"left_on": "Before the hire date"}},
        )
    employee.status = "left"
    employee.left_on = data.left_on
    employee.updated_by = user.id
    cache.bump_data_version(db)
    db.commit()
    return profile(db, employee)


def reactivate(db: Session, user: User, employee_id: int, data: ReactivateIn) -> EmployeeOut:
    employee = get_or_404(db, employee_id)
    _check_version(employee, data.version)
    if employee.status == "active":
        raise Conflict("This employee is already current.")
    employee.status = "active"
    employee.left_on = None
    employee.updated_by = user.id
    cache.bump_data_version(db)
    db.commit()
    return profile(db, employee)


def change_salary(db: Session, user: User, employee_id: int, data: SalaryChangeIn) -> EmployeeOut:
    """New history entry + current salary + who/when + cache version, in one transaction."""
    employee = get_or_404(db, employee_id)
    _check_version(employee, data.version)
    if employee.status != "active":
        raise Conflict("Salary changes can only be recorded for current employees.")
    currency = data.currency or employee.country.currency
    _check_currency(db, currency)
    _check_salary_date(data.effective_date, employee.hire_date)

    record = SalaryRecord(
        employee_id=employee.id,
        amount=data.amount,
        currency=currency,
        effective_date=data.effective_date,
        reason=data.reason,
        note=data.note,
        created_by=user.id,
    )
    db.add(record)
    apply_salary_record(employee, record, fx.rates_in_use(db))
    employee.updated_by = user.id
    employee.updated_at = now()  # always a new version, even for a future-dated change
    cache.bump_data_version(db)
    db.commit()
    return profile(db, employee)


# ---------- export ----------
EXPORT_COLUMNS = [
    "employee_code", "first_name", "last_name", "email", "job_title", "job_level",
    "department", "country_code", "city", "employment_type", "fte", "hire_date", "status",
    "left_on", "salary", "currency", "salary_usd", "salary_effective_date",
]  # fmt: skip


def _safe_cell(value) -> str:
    """Stop spreadsheet formula injection: text starting with = + - @ gets a leading '."""
    text = "" if value is None else str(value)
    if text and text[0] in "=+-@\t\r" and not _is_number(text):
        return "'" + text
    return text


def _is_number(text: str) -> bool:
    try:
        Decimal(text)
    except ArithmeticError:
        return False
    return True


def export_csv(db: Session, filters: EmployeeFilters) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    for e in repo.iter_filtered(db, filters, _outlier_ids(db, filters)):
        writer.writerow(
            _safe_cell(v)
            for v in (
                e.employee_code, e.first_name, e.last_name, e.email, e.job_title, e.job_level,
                e.department.name, e.country_code, e.city, e.employment_type, e.fte,
                e.hire_date, e.status, e.left_on, e.current_salary, e.current_currency,
                e.current_salary_usd, e.salary_effective_date,
            )
        )  # fmt: skip
    return buffer.getvalue()


def all_job_titles(db: Session) -> list[str]:
    return list(db.scalars(select(Employee.job_title).distinct().order_by(Employee.job_title)))
