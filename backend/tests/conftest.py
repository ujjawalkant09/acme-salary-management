"""Shared fixtures: an isolated SQLite database per test (built once by the real Alembic
migration, then copied), a frozen clock, demo users and an employee factory."""

import os
import shutil
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="acme-tests-"))
os.environ.update(
    SECRET_KEY="test-secret-key-0123456789",
    DATABASE_URL=f"sqlite:///{_tmp / 'unused.db'}",
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
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.core import cache, clock  # noqa: E402
from app.core.db import get_db, make_engine  # noqa: E402
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


@pytest.fixture(scope="session")
def template_db() -> Path:
    path = _tmp / "template.db"
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(config, "head")
    return path


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
def session_factory(template_db, tmp_path) -> sessionmaker:
    db_path = tmp_path / "test.db"
    shutil.copy(template_db, db_path)
    engine = make_engine(f"sqlite:///{db_path}")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
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
        db.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def db(session_factory) -> Session:
    with session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
def _fresh_state():
    cache.clear()
    limiter.reset()


@pytest.fixture
def storage():
    return get_storage()


@pytest.fixture
def admin(db) -> User:
    return db.query(User).filter_by(email=ADMIN_EMAIL).one()


@pytest.fixture
def viewer(db) -> User:
    return db.query(User).filter_by(email=VIEWER_EMAIL).one()


def _client(session_factory, email: str | None, password: str | None) -> TestClient:
    def override():
        with session_factory() as session:
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

    def make(**overrides):
        n = next(counter)
        salary = overrides.pop("salary", "100000")
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
            "salary": {"amount": salary},
        }
        data.update(overrides)
        out = employee_service.create(db, admin, EmployeeCreate.model_validate(data))
        return employee_service.get_or_404(db, out.id)

    return make
