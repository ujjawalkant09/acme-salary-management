import random
import time
from datetime import date
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.core.config import get_settings
from app.models import Department, Employee, FxRate, SalaryRecord, User
from app.repositories import employees as repo
from app.schemas import EmployeeFilters
from scripts import seed as seed_script
from tests.conftest import BACKEND, count

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
        # Money stays Decimal end to end, rounded to the country's step.
        step = seed_script.COUNTRIES[e["country_code"]][3]
        assert all(type(r["amount"]) is Decimal and r["amount"] % step == 0 for r in history)
        assert type(e["current_salary_usd"]) is Decimal
        if e["status"] == "left":
            assert e["hire_date"] < e["left_on"] <= AS_OF
            assert all(r["effective_date"] <= e["left_on"] for r in history)
    countries = {e["country_code"] for e in employees}
    assert countries == {"IN", "US", "CA", "SG", "BR", "AU"}


async def test_seed_into_database(session_factory, monkeypatch):
    async with session_factory() as db:
        # The test fixture already added departments, rates and users; start from empty.
        await seed_script._reset(db)
        started = time.perf_counter()
        await seed_script.seed(db, 1000, AS_OF)
        assert time.perf_counter() - started < 10
        assert await count(db, Employee) == 1000
        assert await count(db, User) == 2
        assert await count(db, Department) == len(seed_script.DEPARTMENTS)
        assert await count(db, FxRate) == 6
        employee = await db.get(Employee, 1)
        latest = await repo.latest_effective_record(db, 1, AS_OF)
        assert employee.current_salary == latest.amount
        assert await count(db, SalaryRecord) > 1000
        # Each entry is recorded on its start date, never in the future.
        hire = await db.scalar(select(SalaryRecord).where(SalaryRecord.reason == "hire"))
        assert hire.created_at.date() == hire.effective_date


async def test_seed_refuses_to_run_twice_without_reset(session_factory):
    async with session_factory() as db:
        await seed_script._reset(db)
        await seed_script.seed(db, 10, AS_OF)
        try:
            await seed_script.seed(db, 10, AS_OF)
        except SystemExit as exc:
            assert "--reset" in str(exc)
        else:
            raise AssertionError("expected SystemExit")
        await seed_script.seed(db, 10, AS_OF, reset=True)
        assert await count(db, Employee) == 10


async def test_seed_if_empty_leaves_existing_data_alone(session_factory):
    async with session_factory() as db:
        await seed_script._reset(db)
        assert await seed_script.seed(db, 10, AS_OF, if_empty=True) is True
        first_name = (await db.get(Employee, 1)).first_name
        assert await seed_script.seed(db, 20, AS_OF, if_empty=True) is False
        assert await count(db, Employee) == 10
        assert await count(db, User) == 2
        assert (await db.get(Employee, 1)).first_name == first_name


async def test_seed_needs_the_demo_passwords(session_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_admin_password", None)
    async with session_factory() as db:
        await seed_script._reset(db)
        with pytest.raises(SystemExit, match="DEMO_ADMIN_PASSWORD"):
            await seed_script.seed(db, 10, AS_OF)


async def test_seed_command_line(session_factory, monkeypatch, capsys):
    monkeypatch.setattr(seed_script, "SessionLocal", session_factory)
    monkeypatch.setattr("sys.argv", ["seed", "--count", "5", "--reset"])
    await seed_script.main()
    assert "Seeded 5 employees" in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["seed", "--if-empty"])
    await seed_script.main()
    assert "nothing seeded" in capsys.readouterr().out
    async with session_factory() as db:
        assert await count(db, Employee) == 5


# SQLite can't reflect expression indexes, so Alembic skips comparing them. The plan tests
# below and test_two_uploads_at_once_still_open_only_one_import check the migrations made them.
@pytest.mark.filterwarnings("ignore:.*expression-based index")
def test_models_match_the_migration(template_db):
    """Fails if a model changed without a new Alembic migration."""
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{template_db}")
    command.check(config)


async def _query_plan(db, sql: str) -> str:
    connection = await db.connection()
    result = await connection.exec_driver_sql(f"EXPLAIN QUERY PLAN {sql}")
    return str(result.fetchall())


async def test_list_query_uses_the_name_index(db):
    plan = await _query_plan(db, "SELECT id FROM employees ORDER BY last_name, first_name LIMIT 20")
    assert "ix_employees_name" in plan


async def test_job_title_filter_uses_the_lower_case_index(db):
    query = repo.apply_filters(select(Employee), EmployeeFilters(job_title=" DevOps Engineer"))
    sql = query.compile(dialect=db.bind.dialect, compile_kwargs={"literal_binds": True})
    assert "ix_employees_job_title_lower" in await _query_plan(db, str(sql))


async def test_recent_salary_changes_use_the_created_index(db):
    plan = await _query_plan(
        db, "SELECT id FROM salary_records ORDER BY created_at DESC, id DESC LIMIT 10"
    )
    assert "ix_salary_records_created" in plan
    assert "TEMP B-TREE" not in plan  # read in index order, no sort of the whole table
