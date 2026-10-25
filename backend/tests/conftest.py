"""Shared fixtures: an isolated Postgres database per test (built once by the real Alembic
migration, then cloned as a template), a frozen clock, demo users and an employee factory.

Needs the local Postgres (`docker compose up -d --wait db`) or `TEST_DATABASE_URL`."""

import os
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="acme-tests-"))
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://acme:acme@localhost:5432/acme_test"
)
os.environ.update(
    SECRET_KEY="test-secret-key-0123456789",
    DATABASE_URL=TEST_DATABASE_URL,
    SESSION_COOKIE_SECURE="false",
    RATE_LIMIT_ENABLED="false",
    STORAGE_DIR=str(_tmp / "storage"),
    FRONTEND_DIST=str(_tmp / "no-frontend"),
    DEMO_ADMIN_PASSWORD="admin-pass",
    DEMO_VIEWER_PASSWORD="viewer-pass",
)

import bcrypt  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func, make_url, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core import cache, clock  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.core.storage import get_storage  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Department, FxRate, User  # noqa: E402
from app.schemas import EmployeeCreate  # noqa: E402
from app.services import employees as employee_service  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 14)
RATES = {
    "USD": Decimal("1"),
    "INR": Decimal("0.0120"),
    "CAD": Decimal("0.7300"),
    "SGD": Decimal("0.7700"),
    "BRL": Decimal("0.1800"),
    "AUD": Decimal("0.6600"),
}
ADMIN_EMAIL, VIEWER_EMAIL = "admin@acme.example", "viewer@acme.example"
# bcrypt is slow on purpose; tests use the cheapest cost so logins are fast.
ADMIN_HASH = bcrypt.hashpw(b"admin-pass", bcrypt.gensalt(rounds=4)).decode()
VIEWER_HASH = bcrypt.hashpw(b"viewer-pass", bcrypt.gensalt(rounds=4)).decode()


def recreate_database(admin, name: str, template: str = "template0") -> None:
    admin.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    # FILE_COPY clones a small database in a few milliseconds.
    admin.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{template}" STRATEGY FILE_COPY'))


@pytest.fixture(scope="session")
def admin_connection():
    """Connected to the server's `postgres` database, to create and drop the test ones."""
    url = make_url(TEST_DATABASE_URL).set(database="postgres")
    engine = create_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with engine.connect() as connection:
        yield connection
    engine.dispose()


@pytest.fixture(scope="session")
def template_db(admin_connection) -> str:
    """The URL of a database migrated to head; each test gets a fresh clone of it."""
    url = make_url(TEST_DATABASE_URL)
    url = url.set(database=f"{url.database}_template")
    recreate_database(admin_connection, url.database)
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    command.upgrade(config, "head")
    return url.render_as_string(hide_password=False)


class FrozenClock:
    """Replaces `datetime` inside app.core.clock, so every now()/today() call is fixed."""

    def __init__(self, monkeypatch):
        self.current = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
        frozen = self

        class _Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return frozen.current

        monkeypatch.setattr(clock, "datetime", _Frozen)

    def set(self, value: datetime) -> None:
        self.current = value


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch) -> FrozenClock:
    return FrozenClock(monkeypatch)


@pytest.fixture
async def session_factory(template_db, admin_connection) -> async_sessionmaker:
    name = make_url(TEST_DATABASE_URL).database
    recreate_database(admin_connection, name, template=make_url(template_db).database)
    # Not pooled: the test client runs the app on an event loop of its own, and an async
    # connection belongs to the loop that opened it.
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    async with factory() as db:
        db.add_all(Department(name=name) for name in ("Engineering", "Sales", "Finance"))
        db.add_all(
            FxRate(currency=c, rate_date=TODAY, usd_per_unit=r, source="test")
            for c, r in RATES.items()
        )
        db.add_all(
            [
                User(email=ADMIN_EMAIL, name="Priya Admin", role="hr_admin",
                     password_hash=ADMIN_HASH),
                User(email=VIEWER_EMAIL, name="Arjun Viewer", role="hr_viewer",
                     password_hash=VIEWER_HASH),
            ]
        )  # fmt: skip
        await db.commit()
    yield factory
    await engine.dispose()


@pytest.fixture
async def db(session_factory) -> AsyncSession:
    async with session_factory() as session:
        yield session


async def count(db: AsyncSession, model, **filters) -> int:
    """How many rows of `model` match `filters` (column=value)."""
    return await db.scalar(select(func.count()).select_from(model).filter_by(**filters))


@pytest.fixture(autouse=True)
def _fresh_state():
    cache.clear()
    limiter.reset()


@pytest.fixture
def storage():
    return get_storage()


@pytest.fixture
async def admin(db) -> User:
    return await db.scalar(select(User).filter_by(email=ADMIN_EMAIL))


@pytest.fixture
async def viewer(db) -> User:
    return await db.scalar(select(User).filter_by(email=VIEWER_EMAIL))


def _client(session_factory, email: str | None, password: str | None) -> TestClient:
    async def override():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    if email:
        response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
    return client


@pytest.fixture
def anon_client(session_factory):
    yield _client(session_factory, None, None)
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(session_factory):
    yield _client(session_factory, ADMIN_EMAIL, "admin-pass")
    app.dependency_overrides.clear()


@pytest.fixture
def viewer_client(session_factory):
    yield _client(session_factory, VIEWER_EMAIL, "viewer-pass")
    app.dependency_overrides.clear()


@pytest.fixture
def make_employee(db, admin):
    """Create an employee through the real service (so the first salary entry exists)."""
    counter = iter(range(1, 10_000))

    async def make(**overrides):
        n = next(counter)
        salary = {"amount": overrides.pop("salary", "100000")}
        if "currency" in overrides:
            salary["currency"] = overrides.pop("currency")
        data = {
            "first_name": f"First{n}",
            "last_name": f"Last{n}",
            "email": f"person{n}@acme.example",
            "job_title": "Software Engineer",
            "job_level": 3,
            "department_id": 1,
            "country_code": "US",
            "employment_type": "full_time",
            "hire_date": "2022-01-10",
            "salary": salary,
        }
        data.update(overrides)
        out = await employee_service.create(db, admin, EmployeeCreate.model_validate(data))
        return await employee_service.get_or_404(db, out.id)

    return make
