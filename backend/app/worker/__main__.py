"""Background worker: `python -m app.worker`.

Processes import jobs from the `import_jobs` table and runs the daily housekeeping
(exchange rates after the ECB publishes, future-dated salaries, expired idempotency keys,
old import rows and removed documents).
"""

import asyncio
import logging
import signal

import httpx

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import setup_logging
from app.core.storage import get_storage
from app.services.imports import reset_stuck_jobs
from app.worker.tasks import daily_tasks_due, process_next_job, run_daily_tasks

log = logging.getLogger("app.worker")
POLL_SECONDS = 1.0


async def main() -> None:
    setup_logging(get_settings().log_level)
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    storage = get_storage()
    async with SessionLocal() as db:
        await reset_stuck_jobs(db)
    log.info("worker started")
    async with httpx.AsyncClient(timeout=20) as client:
        while not stopping:
            async with SessionLocal() as db:
                worked = await process_next_job(db, storage)
                if daily_tasks_due():
                    await run_daily_tasks(db, storage, client)
            if not worked:
                await asyncio.sleep(POLL_SECONDS)
    log.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
