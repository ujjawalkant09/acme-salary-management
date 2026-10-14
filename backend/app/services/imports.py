"""Bulk import: upload → check (worker) → review → apply (worker) → done.

The upload request only stores the file and queues a job. The worker checks every row
(all problems are collected, not just the first) and later applies the import in ONE
transaction. People missing from the file are never changed.
"""

import csv
import hashlib
import io
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core import cache
from app.core.clock import now, today
from app.core.config import get_settings
from app.core.errors import Conflict, InvalidInput, NotFound
from app.core.storage import LocalStorage
from app.models import (
    EMPLOYMENT_TYPES,
    GENDERS,
    Country,
    Department,
    Employee,
    ImportJob,
    ImportRow,
    SalaryRecord,
    User,
)
from app.schemas import ImportJobOut, ImportRowOut, Page
from app.services import fx
from app.services.employees import MAX_FUTURE, apply_salary_record
from app.services.import_file import COLUMNS, file_kind, read_rows

log = logging.getLogger(__name__)

ACTIVE_STATUSES = ("queued", "validating", "validated", "commit_queued", "committing")
CHUNK = 500
# Longer than any single step without a heartbeat (applying the largest file allowed).
STUCK_AFTER = timedelta(minutes=15)
UPDATE_REASONS = ("promotion", "merit", "market_adjustment", "correction", "other")
# Detail fields an import can change on an existing employee.
DETAIL_FIELDS = (
    "first_name", "last_name", "email", "job_title", "job_level", "department_id",
    "country_code", "city", "employment_type", "fte", "hire_date", "gender",
)  # fmt: skip


# ---------- job views ----------
def job_out(db: Session, job: ImportJob) -> ImportJobOut:
    earlier = db.scalar(
        select(func.max(ImportJob.finished_at)).where(
            ImportJob.file_sha256 == job.file_sha256,
            ImportJob.status == "completed",
            ImportJob.id != job.id,
        )
    )
    return ImportJobOut(
        id=job.id,
        filename=job.filename,
        status=job.status,
        mode=job.mode,
        total_rows=job.total_rows,
        processed_rows=job.processed_rows,
        create_count=job.create_count,
        update_count=job.update_count,
        unchanged_count=job.unchanged_count,
        error_count=job.error_count,
        created_count=job.created_count,
        updated_count=job.updated_count,
        error_message=job.error_message,
        created_by_name=job.creator.name,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        already_imported_at=earlier,
    )


def get_job(db: Session, job_id: str) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise NotFound("Import not found.")
    return job


def list_jobs(db: Session, page: int, page_size: int) -> Page[ImportJobOut]:
    total = db.scalar(select(func.count()).select_from(ImportJob))
    jobs = db.scalars(
        select(ImportJob)
        .order_by(ImportJob.created_at.desc(), ImportJob.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page.of([job_out(db, j) for j in jobs], total, page, page_size)


def list_rows(
    db: Session, job_id: str, action: str | None, page: int, page_size: int
) -> Page[ImportRowOut]:
    get_job(db, job_id)
    query = select(ImportRow).where(ImportRow.job_id == job_id)
    if action:
        query = query.where(ImportRow.action == action)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(ImportRow.row_number).offset((page - 1) * page_size).limit(page_size)
    )
    return Page.of([ImportRowOut.model_validate(r) for r in rows], total, page, page_size)


def errors_csv(db: Session, job_id: str) -> str:
    """The problem rows exactly as uploaded, plus a column explaining what to fix."""
    get_job(db, job_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["row", *COLUMNS, "problems"])
    rows = db.scalars(
        select(ImportRow)
        .where(ImportRow.job_id == job_id, ImportRow.action == "error")
        .order_by(ImportRow.row_number)
    )
    for row in rows:
        raw = row.payload.get("raw", {})
        problems = "; ".join(f"{e['field']}: {e['message']}" for e in row.errors)
        writer.writerow([row.row_number, *(raw.get(c, "") for c in COLUMNS), problems])
    return buffer.getvalue()


# ---------- upload, commit, cancel (API side) ----------
def start(
    db: Session, storage: LocalStorage, user: User, file_name: str | None, data: bytes
) -> ImportJobOut:
    kind = file_kind(file_name, data)
    running = db.scalar(select(ImportJob).where(ImportJob.status.in_(ACTIVE_STATUSES)))
    if running is not None:
        raise Conflict(
            f"Another import ({running.filename}) is still open. Apply or cancel it first.",
            {"import_id": running.id},
        )
    job = ImportJob(
        id=str(uuid.uuid4()),
        filename=(file_name or f"import.{kind}")[:200],
        file_sha256=hashlib.sha256(data).hexdigest(),
        created_by=user.id,
    )
    key = _file_key(job.id)
    storage.put(key, data)
    try:
        db.add(job)
        db.commit()
    except Exception:
        storage.delete(key)
        raise
    return job_out(db, job)


def request_commit(db: Session, job_id: str, mode: str) -> ImportJobOut:
    job = get_job(db, job_id)
    if job.status != "validated":
        raise Conflict("This import can't be applied in its current state.")
    if mode == "all_or_nothing" and job.error_count:
        raise Conflict(
            "The file has problems. Fix them and upload again, or save only the correct rows.",
            {"error_count": job.error_count},
        )
    job.mode = mode
    job.status = "commit_queued"
    db.commit()
    return job_out(db, job)


def cancel(db: Session, storage: LocalStorage, job_id: str) -> ImportJobOut:
    job = get_job(db, job_id)
    if job.status not in ("queued", "validated", "failed"):
        raise Conflict("This import can't be cancelled now.")
    job.status = "cancelled"
    job.finished_at = now()
    db.commit()
    storage.delete(_file_key(job.id))
    return job_out(db, job)


def _file_key(job_id: str) -> str:
    return f"imports/{job_id}"


# ---------- checking rows (worker) ----------
@dataclass
class Context:
    """Everything a row check needs, loaded once per job instead of once per row."""

    countries: dict[str, str]  # code -> currency
    departments: dict[str, int]  # lower-case name -> id
    currencies: set[str]
    existing: dict[str, Employee]  # employee_code -> employee
    email_owner: dict[str, str]  # email -> employee_code
    seen_codes: set[str] = field(default_factory=set)
    seen_emails: set[str] = field(default_factory=set)


def load_context(db: Session) -> Context:
    employees = list(db.scalars(select(Employee)))
    return Context(
        countries={c.code: c.currency for c in db.scalars(select(Country))},
        departments={d.name.lower(): d.id for d in db.scalars(select(Department))},
        currencies=set(fx.supported_currencies(db)),
        existing={e.employee_code: e for e in employees},
        email_owner={e.email: e.employee_code for e in employees},
    )


class _Row:
    """Collects every problem in one row instead of stopping at the first."""

    def __init__(self, raw: dict[str, str]):
        self.raw = raw
        self.errors: list[dict[str, str]] = []

    def error(self, column: str, message: str) -> None:
        self.errors.append({"field": column, "message": message})

    def text(self, column: str, required: bool = True, max_length: int = 100) -> str | None:
        value = self.raw.get(column, "").strip()
        if not value:
            if required:
                self.error(column, "Required")
            return None
        if len(value) > max_length:
            self.error(column, f"At most {max_length} characters")
            return None
        return value

    def choice(self, column: str, options: tuple[str, ...], required: bool = True) -> str | None:
        value = self.text(column, required)
        if value is None:
            return None
        normalized = value.lower().replace("-", "_").replace(" ", "_")
        if normalized not in options:
            self.error(column, f"Must be one of: {', '.join(options)}")
            return None
        return normalized

    def number(self, column: str, required: bool = True) -> Decimal | None:
        value = self.text(column, required)
        if value is None:
            return None
        try:
            number = Decimal(value.replace(",", ""))
        except InvalidOperation:
            self.error(column, "Must be a number")
            return None
        if not number.is_finite():
            self.error(column, "Must be a number")
            return None
        return number

    def day(self, column: str, required: bool = True) -> date | None:
        value = self.text(column, required)
        if value is None:
            return None
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            self.error(column, "Must be a date like 2025-04-01")
            return None


def check_row(raw: dict[str, str], ctx: Context) -> tuple[str, dict, list[dict]]:
    """Return (action, payload, errors) for one row. Action is create, update, unchanged
    or error."""
    row = _Row(raw)
    code = (row.text("employee_code", max_length=20) or "").upper()
    existing = ctx.existing.get(code) if code else None
    values: dict = {
        "first_name": row.text("first_name"),
        "last_name": row.text("last_name"),
        "job_title": row.text("job_title"),
        "city": row.text("city", required=False),
        "employment_type": row.choice("employment_type", EMPLOYMENT_TYPES),
        "gender": row.choice("gender", GENDERS, required=False),
        "hire_date": row.day("hire_date"),
    }

    email = row.text("email", max_length=200)
    if email:
        try:
            email = validate_email(email, check_deliverability=False).normalized.lower()
        except EmailNotValidError:
            row.error("email", "Not a valid email address")
            email = None
    values["email"] = email

    level = row.number("job_level")
    if level is not None and (level != level.to_integral_value() or not 1 <= level <= 6):
        row.error("job_level", "Must be a whole number from 1 to 6")
        level = None
    values["job_level"] = int(level) if level is not None else None

    fte = row.number("fte", required=False)
    if fte is None and not row.raw.get("fte"):
        fte = Decimal(1)
    elif fte is not None and not Decimal(0) < fte <= 1:
        row.error("fte", "Must be more than 0 and at most 1")
        fte = None
    values["fte"] = fte.quantize(Decimal("0.001")) if fte is not None else None

    department = row.text("department")
    values["department_id"] = ctx.departments.get(department.lower()) if department else None
    if department and values["department_id"] is None:
        row.error("department", "Unknown department")

    country = (row.text("country_code") or "").upper() or None
    if country and country not in ctx.countries:
        row.error("country_code", "Unknown country")
        country = None
    values["country_code"] = country

    salary = row.number("salary")
    if salary is not None and (salary <= 0 or salary >= Decimal("1e12")):
        row.error("salary", "Must be more than 0 and less than 1,000,000,000,000")
        salary = None
    currency = (row.text("currency", required=False) or "").upper()
    if not currency:
        # Blank: an existing employee keeps their currency; a new one gets the country's.
        currency = existing.current_currency if existing else ctx.countries.get(country)
    if currency and currency not in ctx.currencies:
        row.error("currency", "Not a supported currency")
        currency = None
    effective = row.day("salary_effective_date", required=False)
    reason = row.choice("salary_reason", UPDATE_REASONS, required=False)
    note = row.text("salary_note", required=False, max_length=500)

    # Duplicates inside the file.
    if code:
        if code in ctx.seen_codes:
            row.error("employee_code", "Appears more than once in the file")
        ctx.seen_codes.add(code)
    if email:
        if email in ctx.seen_emails:
            row.error("email", "Appears more than once in the file")
        ctx.seen_emails.add(email)

    if email and ctx.email_owner.get(email, code) != code:
        row.error("email", "Already used by another employee")

    hire_date = values["hire_date"]
    # Default: the hire date for new people; for others today, or the start date of
    # someone who hasn't started yet.
    effective = effective or (hire_date if existing is None else max(today(), hire_date or today()))
    if effective and hire_date and effective < hire_date:
        row.error("salary_effective_date", "Before the hire date")
    if effective and effective > today() + MAX_FUTURE:
        row.error("salary_effective_date", "More than a year ahead")
    if hire_date and hire_date > today() + MAX_FUTURE:
        row.error("hire_date", "More than a year ahead")

    payload: dict = {"raw": raw}
    if row.errors:
        return "error", payload, row.errors

    salary_value = {
        "amount": str(salary.quantize(Decimal("0.01"))),
        "currency": currency,
        "effective_date": effective.isoformat(),
        "reason": reason,
        "note": note,
    }
    if existing is None:
        salary_value["reason"] = "hire"
        payload.update(employee_code=code, values=_jsonable(values), salary=salary_value)
        return "create", payload, []

    # Blank optional cells (city, gender) leave the stored value alone.
    changes = {
        name: value
        for name, value in values.items()
        if value is not None and _differs(getattr(existing, name), value)
    }
    salary_changed = salary != existing.current_salary or currency != existing.current_currency
    if salary_changed and existing.status != "active":
        row.error("salary", "This employee has left; salary changes aren't allowed")
        return "error", payload, row.errors
    if not changes and not salary_changed:
        return "unchanged", payload, []
    salary_value["reason"] = reason or "other"
    payload.update(
        employee_code=code,
        employee_id=existing.id,
        version=existing.version,
        values=_jsonable(changes),
        salary=salary_value if salary_changed else None,
    )
    return "update", payload, []


def _differs(current, new) -> bool:
    if isinstance(current, Decimal) and isinstance(new, Decimal):
        return current.compare(new) != 0
    return current != new


def _jsonable(values: dict) -> dict:
    return {
        k: v.isoformat() if isinstance(v, date) else str(v) if isinstance(v, Decimal) else v
        for k, v in values.items()
    }


def validate_job(db: Session, storage: LocalStorage, job: ImportJob) -> None:
    """Check every row and store the results in chunks, so progress is visible. Re-running
    starts over and gives the same result."""
    db.execute(delete(ImportRow).where(ImportRow.job_id == job.id))
    job.processed_rows = job.total_rows = 0
    job.create_count = job.update_count = job.unchanged_count = job.error_count = 0
    db.commit()

    data = storage.get(_file_key(job.id))
    _, rows = read_rows(file_kind(job.filename, data), data)
    rows = list(rows)
    limit = get_settings().max_import_rows
    if len(rows) > limit:
        raise InvalidInput(f"The file has {len(rows):,} rows; the limit is {limit:,}.")
    if not rows:
        raise InvalidInput("The file has no data rows.")
    job.total_rows = len(rows)
    db.commit()

    ctx = load_context(db)
    counts = {"create": 0, "update": 0, "unchanged": 0, "error": 0}
    for start in range(0, len(rows), CHUNK):
        for number, raw in rows[start : start + CHUNK]:
            action, payload, errors = check_row(raw, ctx)
            counts[action] += 1
            db.add(
                ImportRow(
                    job_id=job.id,
                    row_number=number,
                    employee_code=raw.get("employee_code") or None,
                    action=action,
                    payload=payload,
                    errors=errors,
                )
            )
        job.processed_rows = min(start + CHUNK, len(rows))
        job.heartbeat_at = now()
        db.commit()

    job.create_count, job.update_count = counts["create"], counts["update"]
    job.unchanged_count, job.error_count = counts["unchanged"], counts["error"]
    job.status = "validated"
    db.commit()
    # Raw files are not kept after checking (less personal data lying around).
    storage.delete(_file_key(job.id))


# ---------- applying (worker) ----------
class StaleRows(Exception):
    pass


def apply_job(db: Session, job: ImportJob) -> None:
    """Apply every create/update row in ONE transaction. Rows that no longer fit (the
    employee changed, or a code or email was taken after the check) stop the whole import
    with `all_or_nothing`; with `valid_rows_only` they are marked as problems and skipped."""
    rates = fx.rates_in_use(db)
    codes = set(db.scalars(select(Employee.employee_code)))
    email_owner = dict(db.execute(select(Employee.email, Employee.id)).all())
    rows = list(
        db.scalars(
            select(ImportRow)
            .where(ImportRow.job_id == job.id, ImportRow.action.in_(("create", "update")))
            .order_by(ImportRow.row_number)
        )
    )
    created = updated = 0
    for row in rows:
        payload = row.payload
        employee = db.get(Employee, payload["employee_id"]) if row.action == "update" else None
        problem = _changed_since_check(row, payload, employee, codes, email_owner)
        if problem:
            column, message = problem
            if job.mode == "all_or_nothing":
                raise StaleRows(
                    f"Row {row.row_number}, {column}: {message}. Upload the file again."
                )
            row.action = "error"
            row.errors = [{"field": column, "message": message}]
            job.error_count += 1
            continue
        if employee is None:
            employee = _create_from_row(db, job, payload, rates)
            codes.add(employee.employee_code)
            created += 1
        else:
            email_owner.pop(employee.email)
            _update_from_row(db, job, employee, payload, rates)
            updated += 1
        email_owner[employee.email] = employee.id

    job.created_count, job.updated_count = created, updated
    job.status = "completed"
    job.finished_at = now()
    cache.bump_data_version(db)
    db.commit()


def _changed_since_check(
    row: ImportRow,
    payload: dict,
    employee: Employee | None,
    codes: set[str],
    email_owner: dict[str, int],
) -> tuple[str, str] | None:
    """The (column, message) of what changed in the database since the row was checked."""
    email = payload["values"].get("email")
    if row.action == "create":
        if payload["employee_code"] in codes:
            return "employee_code", "Taken by an employee added after the check"
        if email in email_owner:
            return "email", "Taken by an employee added after the check"
        return None
    if employee is None or employee.version != payload["version"]:
        return "employee_code", "The employee changed after the check"
    if email and email_owner.get(email, employee.id) != employee.id:
        return "email", "Taken by another employee after the check"
    return None


def _salary_record(job: ImportJob, employee_id: int, salary: dict) -> SalaryRecord:
    return SalaryRecord(
        employee_id=employee_id,
        amount=Decimal(salary["amount"]),
        currency=salary["currency"],
        effective_date=date.fromisoformat(salary["effective_date"]),
        reason=salary["reason"],
        note=salary["note"],
        import_job_id=job.id,
        created_by=job.created_by,
    )


def _typed(values: dict) -> dict:
    typed = dict(values)
    if typed.get("hire_date"):
        typed["hire_date"] = date.fromisoformat(typed["hire_date"])
    if typed.get("fte"):
        typed["fte"] = Decimal(typed["fte"])
    return typed


def _create_from_row(db: Session, job: ImportJob, payload: dict, rates: fx.Rates) -> Employee:
    salary = payload["salary"]
    amount = Decimal(salary["amount"])
    employee = Employee(
        employee_code=payload["employee_code"],
        **_typed(payload["values"]),
        current_salary=amount,
        current_currency=salary["currency"],
        current_salary_usd=rates.to_usd(amount, salary["currency"]),
        salary_effective_date=date.fromisoformat(salary["effective_date"]),
        updated_by=job.created_by,
    )
    db.add(employee)
    db.flush()
    db.add(_salary_record(job, employee.id, salary))
    return employee


def _update_from_row(
    db: Session, job: ImportJob, employee: Employee, payload: dict, rates: fx.Rates
) -> None:
    for name, value in _typed(payload["values"]).items():
        setattr(employee, name, value)
    if payload["salary"]:
        record = _salary_record(job, employee.id, payload["salary"])
        db.add(record)
        apply_salary_record(employee, record, rates)
    employee.updated_by = job.created_by
    employee.updated_at = now()


# ---------- worker loop pieces ----------
def next_job_query():
    """The oldest queued job. `SKIP LOCKED` lets several workers share the queue safely.
    `of=ImportJob` locks only the job row: Postgres refuses FOR UPDATE on the outer join
    that loads the job's creator."""
    return (
        select(ImportJob)
        .where(ImportJob.status.in_(("queued", "commit_queued")))
        .order_by(ImportJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True, of=ImportJob)
    )


def claim_next_job(db: Session) -> ImportJob | None:
    """Claim one queued job."""
    job = db.scalar(next_job_query())
    if job is None:
        return None
    job.status = "validating" if job.status == "queued" else "committing"
    job.started_at = job.started_at or now()
    job.heartbeat_at = now()
    db.commit()
    return job


def run_job(db: Session, storage: LocalStorage, job: ImportJob) -> None:
    step: Callable[[], None] = (
        (lambda: validate_job(db, storage, job))
        if job.status == "validating"
        else (lambda: apply_job(db, job))
    )
    job_id = job.id
    try:
        step()
    except (InvalidInput, StaleRows) as exc:
        _fail(db, storage, job_id, str(exc))
    except Exception:
        log.exception("import job failed", extra={"fields": {"job_id": job_id}})
        _fail(db, storage, job_id, "Something went wrong while processing the file. Try again.")


def _fail(db: Session, storage: LocalStorage, job_id: str, message: str) -> None:
    db.rollback()
    job = db.get(ImportJob, job_id)
    job.status = "failed"
    job.error_message = message
    job.finished_at = now()
    db.commit()
    # A failed job is never retried (a new upload starts a new job), so drop its file.
    storage.delete(_file_key(job_id))


def reset_stuck_jobs(db: Session) -> None:
    """Queue again the jobs whose worker went quiet (it stopped or crashed): checking
    starts over, and an interrupted apply never committed (it is one transaction). Jobs
    a live worker is still on have a recent heartbeat and are left alone."""
    for job in db.scalars(
        select(ImportJob).where(
            ImportJob.status.in_(("validating", "committing")),
            or_(ImportJob.heartbeat_at.is_(None), ImportJob.heartbeat_at < now() - STUCK_AFTER),
        )
    ):
        job.status = "queued" if job.status == "validating" else "commit_queued"
    db.commit()


def purge_old_rows(db: Session, older_than: timedelta = timedelta(days=30)) -> None:
    old_jobs = select(ImportJob.id).where(ImportJob.finished_at < now() - older_than)
    db.execute(delete(ImportRow).where(ImportRow.job_id.in_(old_jobs)))
    db.commit()
