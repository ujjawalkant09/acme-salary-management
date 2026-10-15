import uuid
from datetime import UTC, datetime, timedelta

import httpx

from app.core import idempotency
from app.models import AppState, IdempotencyKey
from app.schemas import SalaryChangeIn
from app.services import employees
from app.worker import __main__ as worker
from app.worker import tasks


def counting_client(calls: list) -> httpx.AsyncClient:
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"date": "2026-10-14", "rates": {"INR": 80}})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_rates_are_fetched_only_after_the_ecb_publishes(db, storage, frozen_clock):
    calls = []
    frozen_clock.set(datetime(2026, 10, 14, 9, tzinfo=UTC))
    await tasks.run_daily_tasks(db, storage, counting_client(calls))
    assert calls == []
    frozen_clock.set(datetime(2026, 10, 14, 16, 5, tzinfo=UTC))
    await tasks.run_daily_tasks(db, storage, counting_client(calls))
    await tasks.run_daily_tasks(db, storage, counting_client(calls))  # re-running changes nothing
    assert len(calls) == 1
    assert str((await db.get(AppState, 1)).fx_checked_on) == "2026-10-14"


def test_daily_check_is_throttled(monkeypatch, frozen_clock):
    monkeypatch.setattr(tasks, "_last_daily_check", None)
    assert tasks.daily_tasks_due()
    assert not tasks.daily_tasks_due()
    frozen_clock.set(frozen_clock.current + timedelta(minutes=10))
    assert tasks.daily_tasks_due()


async def test_expired_idempotency_keys_are_purged(db, admin, frozen_clock):
    db.add(IdempotencyKey(key=str(uuid.uuid4()), user_id=admin.id, endpoint="x",
                          request_hash="h", expires_at=frozen_clock.current + timedelta(hours=24)))  # fmt: skip
    await db.commit()
    assert await idempotency.purge_expired(db) == 0
    frozen_clock.set(frozen_clock.current + timedelta(hours=25))
    assert await idempotency.purge_expired(db) == 1


async def test_no_job_means_no_work(db, storage):
    assert await tasks.process_next_job(db, storage) is False


async def test_worker_loop_works_until_told_to_stop(session_factory, monkeypatch):
    """Runs the real loop: a job, then an idle poll, then SIGTERM stops it cleanly."""
    handlers, events = {}, []

    async def record(event):
        events.append(event)

    async def next_job(db, storage):
        events.append("job")
        if events.count("job") == 1:
            return True  # did some work: look again at once
        handlers[worker.signal.SIGTERM](worker.signal.SIGTERM, None)
        return False

    monkeypatch.setattr(
        worker.signal, "signal", lambda signum, handler: handlers.update({signum: handler})
    )
    monkeypatch.setattr(worker, "setup_logging", lambda level: None)
    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    monkeypatch.setattr(worker, "reset_stuck_jobs", lambda db: record("reset"))
    monkeypatch.setattr(worker, "process_next_job", next_job)
    monkeypatch.setattr(worker, "daily_tasks_due", lambda: events.count("job") == 1)
    monkeypatch.setattr(worker, "run_daily_tasks", lambda db, storage, client: record("daily"))
    monkeypatch.setattr(worker.asyncio, "sleep", lambda seconds: record("sleep"))

    await worker.main()
    assert set(handlers) == {worker.signal.SIGTERM, worker.signal.SIGINT}
    assert events == ["reset", "job", "daily", "job", "sleep"]


async def test_daily_tasks_apply_salaries_that_became_due(
    db, storage, admin, make_employee, frozen_clock
):
    e = await make_employee(salary="80000")
    raise_ = SalaryChangeIn(version=1, amount="90000", effective_date="2026-11-01", reason="merit")
    await employees.change_salary(db, admin, e.id, raise_)
    frozen_clock.set(datetime(2026, 11, 1, 9, tzinfo=UTC))  # before the rate fetch hour
    await tasks.run_daily_tasks(db, storage, counting_client([]))
    await db.refresh(e)
    assert e.current_salary == 90000
