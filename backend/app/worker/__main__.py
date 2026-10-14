"""Background worker: `python -m app.worker`.

Processes import jobs from the `import_jobs` table and runs the daily housekeeping
(exchange rates after the ECB publishes, future-dated salaries, expired idempotency keys,
old import rows and removed documents).
"""

import logging
import signal
import time

import httpx

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import setup_logging
from app.core.storage import get_storage
from app.services.imports import reset_stuck_jobs
from app.worker.tasks import daily_tasks_due, process_next_job, run_daily_tasks

log = logging.getLogger("app.worker")
POLL_SECONDS = 1.0


def main() -> None:
    setup_logging(get_settings().log_level)
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    storage = get_storage()
    with SessionLocal() as db:
        reset_stuck_jobs(db)
    log.info("worker started")
    with httpx.Client(timeout=20) as client:
        while not stopping:
            with SessionLocal() as db:
                worked = process_next_job(db, storage)
                if daily_tasks_due():
                    run_daily_tasks(db, storage, client)
            if not worked:
                time.sleep(POLL_SECONDS)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
