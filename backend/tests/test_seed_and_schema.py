import random
import time
from datetime import date

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import Department, Employee, FxRate, SalaryRecord, User
from app.repositories import employees as repo
from scripts import seed as seed_script
from tests.conftest import BACKEND

AS_OF = date(2026, 10, 14)


def test_generate_is_deterministic():
    first = seed_script.generate(200, AS_OF, random.Random(seed_script.RNG_SEED))
    second = seed_script.generate(200, AS_OF, random.Random(seed_script.RNG_SEED))
    assert first == second


def test_generated_data_is_consistent():
    employees, records = seed_script.generate(2000, AS_OF, random.Random(seed_script.RNG_SEED))
    assert len({e["email"] for e in employees}) == len(employees)
    by_employee: dict[int, list[dict]] = {}
    for r in records:
        by_employee.setdefault(r["employee_id"], []).append(r)
    for e in employees:
        history = by_employee[e["id"]]
        assert history[0]["reason"] == "hire" and history[0]["effective_date"] == e["hire_date"]
        in_effect = [r for r in history if r["effective_date"] <= AS_OF]
        assert in_effect[-1]["amount"] == e["current_salary"]
        assert all(r["amount"] > 0 for r in history)
        if e["status"] == "left":
            assert e["hire_date"] < e["left_on"] <= AS_OF
            assert all(r["effective_date"] <= e["left_on"] for r in history)
    countries = {e["country_code"] for e in employees}
    assert countries == {"IN", "US", "CA", "SG", "BR", "AU"}


def test_seed_into_database(session_factory, monkeypatch):
    with session_factory() as db:
        # The test fixture already added departments, rates and users; start from empty.
        seed_script._reset(db)
        started = time.perf_counter()
        seed_script.seed(db, 1000, AS_OF)
        assert time.perf_counter() - started < 10
        assert db.scalar(select(func.count()).select_from(Employee)) == 1000
        assert db.scalar(select(func.count()).select_from(User)) == 2
        assert db.scalar(select(func.count()).select_from(Department)) == len(
            seed_script.DEPARTMENTS
        )
        assert db.scalar(select(func.count()).select_from(FxRate)) == 6
        employee = db.get(Employee, 1)
        latest = repo.latest_effective_record(db, 1, AS_OF)
        assert employee.current_salary == latest.amount
        assert db.scalar(select(func.count()).select_from(SalaryRecord)) > 1000
        # Each entry is recorded on its start date, never in the future.
        hire = db.scalars(select(SalaryRecord).where(SalaryRecord.reason == "hire")).first()
        assert hire.created_at.date() == hire.effective_date


def test_seed_refuses_to_run_twice_without_reset(session_factory):
    with session_factory() as db:
        seed_script._reset(db)
        seed_script.seed(db, 10, AS_OF)
        try:
            seed_script.seed(db, 10, AS_OF)
        except SystemExit as exc:
            assert "--reset" in str(exc)
        else:
            raise AssertionError("expected SystemExit")
        seed_script.seed(db, 10, AS_OF, reset=True)
        assert db.scalar(select(func.count()).select_from(Employee)) == 10


def test_seed_if_empty_leaves_existing_data_alone(session_factory):
    with session_factory() as db:
        seed_script._reset(db)
        assert seed_script.seed(db, 10, AS_OF, if_empty=True) is True
        first_name = db.get(Employee, 1).first_name
        assert seed_script.seed(db, 20, AS_OF, if_empty=True) is False
        assert db.scalar(select(func.count()).select_from(Employee)) == 10
        assert db.scalar(select(func.count()).select_from(User)) == 2
        assert db.get(Employee, 1).first_name == first_name


def test_seed_needs_the_demo_passwords(session_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_admin_password", None)
    with session_factory() as db:
        seed_script._reset(db)
        with pytest.raises(SystemExit, match="DEMO_ADMIN_PASSWORD"):
            seed_script.seed(db, 10, AS_OF)


def test_seed_command_line(session_factory, monkeypatch, capsys):
    monkeypatch.setattr(seed_script, "SessionLocal", session_factory)
    monkeypatch.setattr("sys.argv", ["seed", "--count", "5", "--reset"])
    seed_script.main()
    assert "Seeded 5 employees" in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["seed", "--if-empty"])
    seed_script.main()
    assert "nothing seeded" in capsys.readouterr().out
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Employee)) == 5


# SQLite can't reflect the "one open import" expression index, so Alembic skips comparing it;
# test_two_uploads_at_once_still_open_only_one_import checks that the migration created it.
@pytest.mark.filterwarnings("ignore:.*expression-based index uq_import_jobs_one_open")
@pytest.mark.filterwarnings("ignore:.*expression-based index 'uq_import_jobs_one_open'")
def test_models_match_the_migration(template_db):
    """Fails if a model changed without a new Alembic migration."""
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{template_db}")
    command.check(config)


def test_list_query_uses_the_name_index(db):
    explained = (
        db.connection()
        .exec_driver_sql(
            "EXPLAIN QUERY PLAN SELECT id FROM employees ORDER BY last_name, first_name LIMIT 20"
        )
        .fetchall()
    )
    assert any("ix_employees_name" in str(row) for row in explained)
