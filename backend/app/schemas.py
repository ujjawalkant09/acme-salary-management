"""Request and response shapes. Money is a Decimal in Python and a "123.45" string in JSON."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    PlainSerializer,
    StringConstraints,
)

Money = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.2f}", return_type=str)]
PositiveMoney = Annotated[
    Decimal,
    Field(gt=0, max_digits=14, decimal_places=2),
    PlainSerializer(lambda v: f"{v:.2f}", return_type=str),
]
Fte = Annotated[
    Decimal,
    Field(gt=0, le=1, max_digits=4, decimal_places=3),
    PlainSerializer(lambda v: f"{v:.3f}", return_type=str),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
Level = Annotated[int, Field(ge=1, le=6)]

Role = Literal["hr_admin", "hr_viewer"]
Gender = Literal["female", "male", "non_binary", "undisclosed"]
EmploymentType = Literal["full_time", "part_time", "contractor"]
Status = Literal["active", "left"]
SalaryReason = Literal["hire", "promotion", "merit", "market_adjustment", "correction", "other"]
ImportMode = Literal["all_or_nothing", "valid_rows_only"]
Password = Annotated[str, StringConstraints(min_length=8, max_length=200)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int
    pages: int

    @classmethod
    def of(cls, items: list, total: int, page: int, page_size: int) -> "Page":
        pages = max(1, -(-total // page_size))
        return cls(items=items, page=page, page_size=page_size, total=total, pages=pages)


# ---------- auth ----------
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserOut(ORM):
    id: int
    email: str
    name: str
    role: Role


# ---------- reference data ----------
class CountryOut(ORM):
    code: str
    name: str
    currency: str


class DepartmentOut(ORM):
    id: int
    name: str


class FxRatesOut(BaseModel):
    rates_date: date | None
    source: str | None
    usd_per_unit: dict[str, Annotated[Decimal, PlainSerializer(str, return_type=str)]]


class MetaOut(BaseModel):
    countries: list[CountryOut]
    departments: list[DepartmentOut]
    job_titles: list[str]
    levels: list[int]
    employment_types: list[str]
    genders: list[str]
    salary_reasons: list[str]
    fx: FxRatesOut
    data_version: int


# ---------- employees ----------
class EmployeeFilters(BaseModel):
    """Query parameters shared by the list, the facet counts and the CSV export."""

    q: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=100)] = None
    status: Literal["active", "left", "all"] = "active"
    country: list[CountryCode] = []
    department_id: list[int] = []
    level: list[Level] = []
    employment_type: list[EmploymentType] = []
    job_title: str | None = None
    min_salary_usd: Annotated[Decimal | None, Field(ge=0)] = None
    max_salary_usd: Annotated[Decimal | None, Field(ge=0)] = None
    # Show only people paid outside the usual range for their peer group.
    outliers_only: bool = False


class EmployeeListParams(EmployeeFilters):
    sort: Literal["name", "salary", "hire_date", "country", "job_title", "code"] = "name"
    order: Literal["asc", "desc"] = "asc"
    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 20


class EmployeeListItem(ORM):
    id: int
    employee_code: str
    first_name: str
    last_name: str
    email: str
    job_title: str
    job_level: int
    department_id: int
    department: str
    country_code: str
    city: str | None
    employment_type: EmploymentType
    fte: Fte
    status: Status
    current_salary: Money
    current_currency: str
    current_salary_usd: Money


class Facets(BaseModel):
    """How many people each filter option would match, given the other active filters."""

    status: dict[str, int]
    country: dict[str, int]
    department_id: dict[int, int]
    level: dict[int, int]
    employment_type: dict[str, int]


class PeerStats(BaseModel):
    """Pay of the same role, level and country (full-time equivalent, local currency)."""

    count: int
    currency: str
    min: Money
    p25: Money
    median: Money
    p75: Money
    max: Money
    employee_value: Money
    diff_from_median_pct: Decimal
    is_outlier: bool


class UpcomingSalary(BaseModel):
    amount: Money
    currency: str
    effective_date: date


class EmployeeOut(EmployeeListItem):
    gender: Gender | None
    hire_date: date
    left_on: date | None
    salary_effective_date: date
    version: int
    photo_url: str | None
    created_at: datetime
    updated_at: datetime
    updated_by_name: str | None
    rates_date: date | None
    upcoming_salary: UpcomingSalary | None
    peers: PeerStats | None


class InitialSalaryIn(BaseModel):
    amount: PositiveMoney
    currency: Currency | None = None  # default: the country's currency
    effective_date: date | None = None  # default: the hire date
    note: Annotated[str | None, StringConstraints(max_length=500)] = None


class EmployeeCreate(BaseModel):
    first_name: Name
    last_name: Name
    email: EmailStr
    job_title: Name
    job_level: Level
    department_id: int
    country_code: CountryCode
    city: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=100)] = None
    gender: Gender | None = None
    employment_type: EmploymentType
    fte: Fte = Decimal("1.000")
    hire_date: date
    salary: InitialSalaryIn


class EmployeeUpdate(BaseModel):
    """Only the fields that are sent are changed. `version` must be the one last read."""

    version: int
    first_name: Name | None = None
    last_name: Name | None = None
    email: EmailStr | None = None
    job_title: Name | None = None
    job_level: Level | None = None
    department_id: int | None = None
    country_code: CountryCode | None = None
    city: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=100)] = None
    gender: Gender | None = None
    employment_type: EmploymentType | None = None
    fte: Fte | None = None
    hire_date: date | None = None


class MarkLeftIn(BaseModel):
    version: int
    left_on: date


class ReactivateIn(BaseModel):
    version: int


# ---------- salaries ----------
class SalaryChangeIn(BaseModel):
    version: int
    amount: PositiveMoney
    currency: Currency | None = None
    effective_date: date
    reason: Literal["promotion", "merit", "market_adjustment", "correction", "other"]
    note: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=500)] = None


class SalaryRecordOut(BaseModel):
    id: int
    amount: Money
    currency: str
    effective_date: date
    reason: SalaryReason
    note: str | None
    change_pct: Decimal | None  # versus the previous entry in the same currency
    created_by_name: str | None
    created_at: datetime
    from_import: bool
    is_future: bool


class RecentSalaryChange(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    employee_code: str
    amount: Money
    currency: str
    effective_date: date
    reason: SalaryReason
    created_by_name: str | None
    created_at: datetime


# ---------- documents ----------
class DocumentOut(BaseModel):
    id: int
    file_name: str
    content_type: str
    size_bytes: int
    uploaded_by_name: str
    uploaded_at: datetime


class LinkOut(BaseModel):
    url: str


class PhotoOut(BaseModel):
    photo_url: str


# ---------- insights ----------
class Summary(BaseModel):
    headcount: int
    payroll_usd: Money
    median_salary_usd: Money
    rates_date: date | None
    outlier_count: int
    upcoming_changes_7d: int
    countries: int


class GroupStats(BaseModel):
    """One row of a pay table: a country, department or role."""

    key: str
    label: str
    people: int
    currency: str
    cost: Money
    min: Money
    p25: Money
    median: Money
    p75: Money
    max: Money
    median_usd: Money | None = None
    cost_usd: Money | None = None
    job_level: int | None = None
    outliers: int = 0


class GroupStatsOut(BaseModel):
    rates_date: date | None
    groups: list[GroupStats]


class HistogramBin(BaseModel):
    start: Money
    end: Money
    count: int


class DistributionOut(BaseModel):
    currency: str
    bins: list[HistogramBin]


class OutlierOut(BaseModel):
    employee_id: int
    employee_code: str
    name: str
    job_title: str
    job_level: int
    country_code: str
    department: str
    salary: Money
    currency: str
    peer_median: Money
    peer_count: int
    diff_from_median_pct: Decimal
    direction: Literal["above", "below"]


# ---------- imports ----------
class ImportJobOut(BaseModel):
    id: str
    filename: str
    status: str
    mode: ImportMode
    total_rows: int
    processed_rows: int
    create_count: int
    update_count: int
    unchanged_count: int
    error_count: int
    created_count: int
    updated_count: int
    error_message: str | None
    created_by_name: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    already_imported_at: datetime | None


class ImportRowOut(ORM):
    row_number: int
    employee_code: str | None
    action: Literal["create", "update", "unchanged", "error"]
    payload: dict
    errors: list[dict]


class ImportCommitIn(BaseModel):
    mode: ImportMode = "all_or_nothing"


class UserCreate(BaseModel):
    name: Name
    email: EmailStr
    role: Role
    password: Password


class UserRoleIn(BaseModel):
    role: Role


class UserActiveIn(BaseModel):
    active: bool


class PasswordIn(BaseModel):
    password: Password


class UserAdminOut(ORM):
    id: int
    email: str
    name: str
    role: Role
    active: bool
    last_login_at: datetime | None
    created_at: datetime | None
