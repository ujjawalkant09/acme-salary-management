import uuid
from datetime import UTC, datetime, timedelta

import httpx

from app.core import idempotency
from app.models import AppState, IdempotencyKey
from app.worker import tasks


def counting_client(calls: list) -> httpx.Client:
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"date": "2026-10-14", "rates": {"INR": 80}})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_rates_are_fetched_only_after_the_ecb_publishes(db, storage, frozen_clock):
    calls = []
    frozen_clock.set(datetime(2026, 10, 14, 9, tzinfo=UTC))
    tasks.run_daily_tasks(db, storage, counting_client(calls))
    assert calls == []
    frozen_clock.set(datetime(2026, 10, 14, 16, 5, tzinfo=UTC))
    tasks.run_daily_tasks(db, storage, counting_client(calls))
    tasks.run_daily_tasks(db, storage, counting_client(calls))  # re-running changes nothing
    assert len(calls) == 1
    assert str(db.get(AppState, 1).fx_checked_on) == "2026-10-14"


def test_daily_check_is_throttled(monkeypatch, frozen_clock):
    monkeypatch.setattr(tasks, "_last_daily_check", None)
    assert tasks.daily_tasks_due()
    assert not tasks.daily_tasks_due()
    frozen_clock.set(frozen_clock.current + timedelta(minutes=10))
    assert tasks.daily_tasks_due()


def test_expired_idempotency_keys_are_purged(db, admin, frozen_clock):
    db.add(IdempotencyKey(key=str(uuid.uuid4()), user_id=admin.id, endpoint="x",
                          request_hash="h", expires_at=frozen_clock.current + timedelta(hours=24)))  # fmt: skip
    db.commit()
    assert idempotency.purge_expired(db) == 0
    frozen_clock.set(frozen_clock.current + timedelta(hours=25))
    assert idempotency.purge_expired(db) == 1


def test_no_job_means_no_work(db, storage):
    assert tasks.process_next_job(db, storage) is False
