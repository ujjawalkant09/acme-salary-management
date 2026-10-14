"""Worker tasks, kept separate from the loop so tests can call them directly."""

import logging
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import idempotency
from app.core.clock import now
from app.core.storage import LocalStorage
from app.models import EmployeeDocument
from app.services import employees, fx, imports

log = logging.getLogger("app.worker")

# The ECB publishes reference rates around 16:00 CET; fetch after 16:00 UTC to be safe.
FX_FETCH_HOUR_UTC = 16
DAILY_CHECK_EVERY = timedelta(minutes=10)
DOCUMENT_RETENTION = timedelta(days=30)

_last_daily_check = None


def process_next_job(db: Session, storage: LocalStorage) -> bool:
    job = imports.claim_next_job(db)
    if job is None:
        return False
    log.info("import job started", extra={"fields": {"job_id": job.id, "step": job.status}})
    imports.run_job(db, storage, job)
    return True


def daily_tasks_due() -> bool:
    global _last_daily_check
    if _last_daily_check is None or now() - _last_daily_check >= DAILY_CHECK_EVERY:
        _last_daily_check = now()
        return True
    return False


def purge_removed_documents(db: Session, storage: LocalStorage) -> int:
    """Delete files of documents removed more than 30 days ago (the row stays as a record)."""
    docs = db.scalars(
        select(EmployeeDocument).where(
            EmployeeDocument.deleted_at < now() - DOCUMENT_RETENTION,
            EmployeeDocument.storage_key != "",
        )
    ).all()
    keys = [d.storage_key for d in docs]
    for doc in docs:
        doc.storage_key = ""
    db.commit()
    for key in keys:  # only after the database change has committed
        storage.delete(key)
    return len(keys)


def run_daily_tasks(db: Session, storage: LocalStorage, client: httpx.Client) -> None:
    """Every task is safe to run again: each one checks what is still to do."""
    imports.reset_stuck_jobs(db)
    promoted = employees.promote_due_salaries(db)
    if promoted:
        log.info("future salaries took effect", extra={"fields": {"employees": promoted}})
    if now().hour >= FX_FETCH_HOUR_UTC and fx.refresh_daily_rates(db, client):
        log.info("exchange rates refreshed")
    idempotency.purge_expired(db)
    imports.purge_old_rows(db)
    purge_removed_documents(db, storage)
