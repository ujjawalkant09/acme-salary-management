"""Seed 10,000 deterministic employees, their salary history and the two demo logins.

    uv run python -m scripts.seed            # refuses if employees already exist
    uv run python -m scripts.seed --reset    # wipes employees, history, files rows first
    uv run python -m scripts.seed --if-empty # seeds only a fresh database (used on every deploy)

The same seed and date always give the same people and salaries. Exchange rates come from a
fixed snapshot so the seed never needs the network; the worker refreshes them daily.
"""

import argparse
import random
import time as timer
import unicodedata
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.core import cache
from app.core.auth import hash_password
from app.core.clock import now, today
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import (
    Department,
    Employee,
    EmployeeDocument,
    FxRate,
    IdempotencyKey,
    ImportJob,
    ImportRow,
    SalaryRecord,
    User,
)

RNG_SEED = 20261014
BATCH = 1000

FX_SNAPSHOT = {  # USD per unit
    "USD": Decimal("1"),
    "INR": Decimal("0.0119"),
    "CAD": Decimal("0.7300"),
    "SGD": Decimal("0.7700"),
    "BRL": Decimal("0.1800"),
    "AUD": Decimal("0.6600"),
}

# code: (currency, headcount weight, pay factor vs US, rounding step, cities)
COUNTRIES = {
    "IN": ("INR", 40, 0.25, 10_000, ["Bengaluru", "Hyderabad", "Pune", "Mumbai", "Gurugram"]),
    "US": ("USD", 22, 1.00, 500, ["New York", "San Francisco", "Austin", "Seattle", "Chicago"]),
    "CA": ("CAD", 10, 0.78, 500, ["Toronto", "Vancouver", "Montreal"]),
    "SG": ("SGD", 8, 0.75, 500, ["Singapore"]),
    "BR": ("BRL", 10, 0.30, 1_000, ["São Paulo", "Rio de Janeiro", "Belo Horizonte"]),
    "AU": ("AUD", 10, 0.82, 500, ["Sydney", "Melbourne", "Brisbane"]),
}

# department: [(title, US yearly base at level 1, weight)]
DEPARTMENTS = {
    "Engineering": [
        ("Software Engineer", 95_000, 10),
        ("QA Engineer", 78_000, 3),
        ("DevOps Engineer", 92_000, 2),
        ("Data Engineer", 98_000, 2),
        ("Engineering Manager", 150_000, 1),
    ],
    "Product": [("Product Manager", 110_000, 1)],
    "Design": [("Product Designer", 88_000, 1)],
    "Sales": [("Account Executive", 70_000, 3), ("Sales Development Rep", 52_000, 2)],
    "Marketing": [("Marketing Specialist", 62_000, 1)],
    "Customer Support": [("Support Specialist", 45_000, 1)],
    "Finance": [("Financial Analyst", 72_000, 1), ("Accountant", 64_000, 1)],
    "People": [("HR Business Partner", 75_000, 1), ("Recruiter", 60_000, 1)],
    "Operations": [("Operations Analyst", 58_000, 1)],
    "Legal": [("Legal Counsel", 120_000, 1)],
}
DEPARTMENT_WEIGHTS = {
    "Engineering": 35, "Product": 6, "Design": 4, "Sales": 14, "Marketing": 6,
    "Customer Support": 14, "Finance": 6, "People": 5, "Operations": 7, "Legal": 3,
}  # fmt: skip
LEVEL_FACTOR = [1.0, 1.25, 1.55, 1.9, 2.35, 2.9]
LEVEL_WEIGHTS = [22, 28, 24, 14, 8, 4]

FIRST_NAMES = {
    "IN": ["Aarav", "Priya", "Rohan", "Ananya", "Vikram", "Sneha", "Arjun", "Kavya", "Rahul",
           "Isha", "Aditya", "Meera", "Karan", "Divya", "Nikhil", "Pooja", "Siddharth", "Riya"],
    "US": ["James", "Emily", "Michael", "Olivia", "David", "Sophia", "Daniel", "Ava", "Ethan",
           "Mia", "Ryan", "Chloe", "Tyler", "Grace", "Jacob", "Hannah"],
    "CA": ["Liam", "Emma", "Noah", "Charlotte", "Lucas", "Amelia", "Owen", "Zoe", "Nathan",
           "Claire"],
    "SG": ["Wei", "Hui Min", "Jun Jie", "Mei Ling", "Darren", "Shu Fen", "Kelvin", "Jia Hui"],
    "BR": ["João", "Maria", "Pedro", "Ana", "Lucas", "Beatriz", "Gabriel", "Juliana", "Rafael",
           "Larissa"],
    "AU": ["Jack", "Ruby", "William", "Isla", "Thomas", "Matilda", "Harry", "Sienna", "Cooper",
           "Evie"],
}  # fmt: skip
LAST_NAMES = {
    "IN": ["Sharma", "Patel", "Iyer", "Reddy", "Gupta", "Nair", "Mehta", "Singh", "Rao", "Kumar",
           "Joshi", "Menon", "Das", "Kapoor", "Verma", "Chopra"],
    "US": ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
           "Wilson", "Anderson", "Taylor", "Moore"],
    "CA": ["Tremblay", "Roy", "Gagnon", "Martin", "MacDonald", "Campbell", "Wong", "Leblanc"],
    "SG": ["Tan", "Lim", "Lee", "Ng", "Ong", "Wong", "Goh", "Chua"],
    "BR": ["Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Costa", "Almeida"],
    "AU": ["Smith", "Jones", "Williams", "Brown", "Wilson", "Taylor", "Nguyen", "Kelly"],
}  # fmt: skip

DEMO_USERS = [
    ("priya.sharma@acme.example", "Priya Sharma", "hr_admin", "demo_admin_password"),
    ("arjun.mehta@acme.example", "Arjun Mehta", "hr_viewer", "demo_viewer_password"),
]


def _ascii(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return plain.lower().replace(" ", "")


def _round_to(amount: float, step: int) -> Decimal:
    return (Decimal(amount) / step).quantize(Decimal(1), ROUND_HALF_UP) * step


def _pick(rng: random.Random, weights: dict):
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def generate(count: int, as_of: date, rng: random.Random) -> tuple[list[dict], list[dict]]:
    """Return (employee rows, salary record rows) ready for bulk insert. Pure: no database."""
    employees, records = [], []
    country_weights = {code: c[1] for code, c in COUNTRIES.items()}
    first_hire = date(2012, 1, 1)
    hire_span = (as_of - timedelta(days=60) - first_hire).days

    for number in range(1, count + 1):
        country = _pick(rng, country_weights)
        currency, _, factor, step, cities = COUNTRIES[country]
        department = _pick(rng, DEPARTMENT_WEIGHTS)
        titles = DEPARTMENTS[department]
        title, base, _ = rng.choices(titles, weights=[t[2] for t in titles])[0]
        level = rng.choices(range(1, 7), weights=LEVEL_WEIGHTS)[0]
        first = rng.choice(FIRST_NAMES[country])
        last = rng.choice(LAST_NAMES[country])
        kind = rng.choices(["full_time", "part_time", "contractor"], weights=[88, 8, 4])[0]
        fte = Decimal(rng.choice(["0.5", "0.6", "0.8"])) if kind == "part_time" else Decimal(1)
        hire_date = first_hire + timedelta(days=rng.randrange(hire_span))

        # Full-time-equivalent USD pay for this role, level and country, with some noise.
        usd = base * LEVEL_FACTOR[level - 1] * factor * rng.gauss(1, 0.06)
        if rng.random() < 0.006:  # a few deliberate outliers for the Insights page
            usd *= rng.choice([0.55, 1.7])
        final = _round_to(usd * float(fte) / float(FX_SNAPSHOT[currency]), step)

        left = rng.random() < 0.04
        left_on = None
        if left:
            left_on = max(as_of - timedelta(days=rng.randrange(1, 700)),
                          hire_date + timedelta(days=30))  # fmt: skip

        # History: hire salary, then yearly raises on the work anniversary up to today
        # (or the leaving date).
        anniversaries = []
        year = hire_date.year + 1
        while len(anniversaries) < 3:
            day = hire_date.replace(year=year, day=min(hire_date.day, 28))
            if day > (left_on or as_of):
                break
            anniversaries.append(day)
            year += rng.choice([1, 2])
        raises = [Decimal(str(round(rng.uniform(1.03, 1.12), 3))) for _ in anniversaries]
        amounts = [final]
        for factor_up in reversed(raises):
            amounts.insert(0, _round_to(float(amounts[0] / factor_up), step))
        dates = [hire_date, *anniversaries]
        reasons = ["hire", *(rng.choice(["merit", "merit", "promotion", "market_adjustment"])
                             for _ in anniversaries)]  # fmt: skip
        for amount, effective, reason in zip(amounts, dates, reasons, strict=True):
            records.append(
                {"employee_id": number, "amount": amount, "currency": currency,
                 "effective_date": effective, "reason": reason}
            )  # fmt: skip

        employees.append(
            {
                "id": number,
                "employee_code": f"ACM-{number:06d}",
                "first_name": first,
                "last_name": last,
                "email": f"{_ascii(first)}.{_ascii(last)}.{number}@acme.example",
                "job_title": title,
                "job_level": level,
                "department": department,
                "country_code": country,
                "city": rng.choice(cities),
                "gender": rng.choices(
                    ["female", "male", "non_binary", "undisclosed", None],
                    weights=[45, 45, 2, 3, 5],
                )[0],
                "employment_type": kind,
                "fte": fte,
                "hire_date": hire_date,
                "status": "left" if left else "active",
                "left_on": left_on,
                "current_salary": final,
                "current_currency": currency,
                "current_salary_usd": (final * FX_SNAPSHOT[currency]).quantize(Decimal("0.01")),
                "salary_effective_date": dates[-1],
            }
        )
        # About 1% have an approved raise starting in the next few weeks.
        if not left and rng.random() < 0.01:
            starts = as_of + timedelta(days=rng.randrange(2, 30))
            records.append(
                {"employee_id": number, "amount": _round_to(float(final) * 1.08, step),
                 "currency": currency, "effective_date": starts, "reason": "promotion"}
            )  # fmt: skip
    return employees, records


def _reset(db: Session) -> None:
    for model in (ImportRow, SalaryRecord, ImportJob, EmployeeDocument, Employee,
                  IdempotencyKey, Department, FxRate, User):  # fmt: skip
        db.execute(delete(model))


def _batched(rows: list[dict]):
    for start in range(0, len(rows), BATCH):
        yield rows[start : start + BATCH]


def seed(db: Session, count: int, as_of: date, reset: bool = False,
         if_empty: bool = False) -> bool:  # fmt: skip
    """Returns False when `if_empty` is set and the database already has employees."""
    settings = get_settings()
    if reset:
        _reset(db)
    elif db.scalar(select(func.count()).select_from(Employee)):
        if if_empty:
            return False
        raise SystemExit("Employees already exist. Use --reset to replace them.")

    for currency, rate in FX_SNAPSHOT.items():
        db.add(FxRate(currency=currency, rate_date=as_of, usd_per_unit=rate,
                      source="Seed snapshot"))  # fmt: skip
    for email, name, role, secret in DEMO_USERS:
        password = getattr(settings, secret)
        if not password:
            raise SystemExit(f"Set {secret.upper()} before seeding.")
        db.add(User(email=email, name=name, role=role, password_hash=hash_password(password)))
    for name in DEPARTMENTS:
        db.add(Department(name=name))
    db.flush()

    admin_id = db.scalar(select(User.id).where(User.role == "hr_admin"))
    department_ids = dict(db.execute(select(Department.name, Department.id)).all())
    employees, records = generate(count, as_of, random.Random(RNG_SEED))
    stamp = now()
    for batch in _batched(employees):
        for row in batch:
            row["department_id"] = department_ids[row.pop("department")]
            row.update(version=1, created_at=stamp, updated_at=stamp, updated_by=admin_id)
        db.execute(insert(Employee), batch)
    for batch in _batched(records):
        for row in batch:
            # History is recorded on its start date (future raises: today), so "recent
            # changes" shows the latest entries rather than the whole history at once.
            recorded = datetime.combine(row["effective_date"], time(9), UTC)
            row.update(created_by=admin_id, created_at=min(recorded, stamp))
        db.execute(insert(SalaryRecord), batch)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT setval(pg_get_serial_sequence('employees', 'id'), "
                        "(SELECT max(id) FROM employees))"))  # fmt: skip
    cache.bump_data_version(db)
    db.commit()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10_000)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--reset", action="store_true")
    mode.add_argument("--if-empty", action="store_true")
    args = parser.parse_args()
    started = timer.perf_counter()
    with SessionLocal() as db:
        seeded = seed(db, args.count, today(), args.reset, args.if_empty)
    if seeded:
        print(f"Seeded {args.count:,} employees in {timer.perf_counter() - started:.1f}s")
    else:
        print("Employees already exist; nothing seeded.")


if __name__ == "__main__":
    main()
