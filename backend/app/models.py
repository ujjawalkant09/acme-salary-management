from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now
from app.core.db import Base

Money = Numeric(14, 2)

ROLES = ("hr_admin", "hr_viewer")
GENDERS = ("female", "male", "non_binary", "undisclosed")
EMPLOYMENT_TYPES = ("full_time", "part_time", "contractor")
EMPLOYEE_STATUSES = ("active", "left")
SALARY_REASONS = ("hire", "promotion", "merit", "market_adjustment", "correction", "other")
IMPORT_STATUSES = (
    "queued",
    "validating",
    "validated",
    "commit_queued",
    "committing",
    "completed",
    "failed",
    "cancelled",
)
# An import in one of these is still open; only one may be open at a time.
OPEN_IMPORT_STATUSES = ("queued", "validating", "validated", "commit_queued", "committing")
IMPORT_MODES = ("all_or_nothing", "valid_rows_only")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Country(Base):
    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3))


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", ROLES), name="ck_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stored lower-cased, so a plain unique index is case-insensitive.
    email: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=now)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # Copied into the session at sign-in; bumping it signs the user out everywhere.
    session_version: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def is_admin(self) -> bool:
        return self.role == "hr_admin"


class FxRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (Index("ix_fx_rates_rate_date", "rate_date"),)

    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    rate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    usd_per_unit: Mapped[Decimal] = mapped_column(Numeric(18, 10))
    source: Mapped[str] = mapped_column(Text)


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("job_level BETWEEN 1 AND 6", name="ck_employees_level"),
        CheckConstraint(_in("employment_type", EMPLOYMENT_TYPES), name="ck_employees_type"),
        CheckConstraint(_in("status", EMPLOYEE_STATUSES), name="ck_employees_status"),
        CheckConstraint("fte > 0 AND fte <= 1", name="ck_employees_fte"),
        Index("ix_employees_status_country_title", "status", "country_code", "job_title"),
        Index("ix_employees_department", "department_id"),
        Index("ix_employees_name", "last_name", "first_name"),
        Index("ix_employees_salary_usd", "current_salary_usd"),
        # The job-title filter matches case-insensitively.
        Index("ix_employees_job_title_lower", text("lower(job_title)")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(20), unique=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)
    job_title: Mapped[str] = mapped_column(Text)
    job_level: Mapped[int] = mapped_column(SmallInteger)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    city: Mapped[str | None] = mapped_column(Text)
    gender: Mapped[str | None] = mapped_column(String(16))
    employment_type: Mapped[str] = mapped_column(String(16))
    fte: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("1.000"))
    hire_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(8), default="active")
    left_on: Mapped[date | None] = mapped_column(Date)
    photo_key: Mapped[str | None] = mapped_column(Text)

    # Denormalized from the latest effective salary record (kept in the same transaction).
    current_salary: Mapped[Decimal] = mapped_column(Money)
    current_currency: Mapped[str] = mapped_column(String(3))
    current_salary_usd: Mapped[Decimal] = mapped_column(Money)
    salary_effective_date: Mapped[date] = mapped_column(Date)

    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    department: Mapped[Department] = relationship(lazy="joined")
    country: Mapped[Country] = relationship(lazy="joined")

    __mapper_args__ = {"version_id_col": version}


class SalaryRecord(Base):
    """Append-only: rows are never updated or deleted. Mistakes get a `correction` entry."""

    __tablename__ = "salary_records"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_salary_amount_positive"),
        CheckConstraint(_in("reason", SALARY_REASONS), name="ck_salary_reason"),
        Index("ix_salary_records_employee_date", "employee_id", "effective_date"),
        # "Recent salary changes" reads the newest entries first.
        Index("ix_salary_records_created", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    effective_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    import_job_id: Mapped[str | None] = mapped_column(ForeignKey("import_jobs.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    creator: Mapped[User | None] = relationship(lazy="joined")


class EmployeeDocument(Base):
    __tablename__ = "employee_documents"
    __table_args__ = (Index("ix_documents_employee", "employee_id", "deleted_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    file_name: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(Text)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    uploader: Mapped[User] = relationship(lazy="joined")


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text)
    request_hash: Mapped[str] = mapped_column(String(64))
    # Null until the response is stored (the key is written in the same transaction as the work).
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict | list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AppState(Base):
    """A single row. `data_version` is bumped by every write so caches are never stale."""

    __tablename__ = "app_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    data_version: Mapped[int] = mapped_column(Integer, default=1)
    fx_checked_on: Mapped[date | None] = mapped_column(Date)


class ImportJob(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        CheckConstraint(_in("status", IMPORT_STATUSES), name="ck_import_status"),
        CheckConstraint(_in("mode", IMPORT_MODES), name="ck_import_mode"),
        Index("ix_import_jobs_status", "status"),
        # Backs the service's "one open import" check when two uploads arrive at once.
        Index(
            "uq_import_jobs_one_open",
            text("(1)"),
            unique=True,
            postgresql_where=text(_in("status", OPEN_IMPORT_STATUSES)),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    mode: Mapped[str] = mapped_column(String(16), default="all_or_nothing")
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0)
    create_count: Mapped[int] = mapped_column(Integer, default=0)
    update_count: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set by the worker while it processes the job; a job that goes quiet is queued again.
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    creator: Mapped[User] = relationship(lazy="joined")


class ImportRow(Base):
    __tablename__ = "import_rows"
    __table_args__ = (
        UniqueConstraint("job_id", "row_number", name="uq_import_rows_job_row"),
        Index("ix_import_rows_job_action", "job_id", "action"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("import_jobs.id"))
    row_number: Mapped[int] = mapped_column(Integer)
    employee_code: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(10))
    payload: Mapped[dict] = mapped_column(JSON)
    errors: Mapped[list] = mapped_column(JSON, default=list)
