# Project instructions — ACME Salary Management

Web app for an HR Manager to manage and analyze salaries for ~10,000 employees.
Read before building: [docs/REQUIREMENTS.md](../docs/REQUIREMENTS.md), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md), [docs/DECISIONS.md](../docs/DECISIONS.md), and the design pack in [docs/design/](../docs/design/). Where ARCHITECTURE.md and the design docs differ, the design docs win.

## Facts, not assumptions
- **Don't assume anything.** Before answering a question about this project (what changed, what is tested, whether something works), read the code, the diff or the command output first, then answer with what you actually found.
- Say where each fact comes from (file and line, or the command you ran). If you haven't checked something, say so instead of guessing.

## Code style
- **DRY, but not clever.** Pull out shared logic when it is genuinely repeated (2–3 real uses), not in anticipation. No extra layers, base classes, factories or config for things that have one use.
- **Simple and readable first.** A new reader should understand a feature by reading it once. Prefer plain functions, clear names and small modules over abstractions.
- Keep each feature neat: routers do HTTP only, services hold business rules, repositories hold queries (see ARCHITECTURE.md "Backend layout").
- Match the surrounding code: naming, comment density, idioms.
- Money is `Decimal` / `NUMERIC(14,2)` — never floats.
- Handle errors and edge cases explicitly (empty inputs, not-found, invalid values, boundaries). Bug-free beats feature-rich.
- No unused code, dead branches or commented-out code.

## Idempotent APIs
- A retried request must never create a second record or apply a change twice.
- `GET`, `PUT` and `DELETE` are idempotent by design: the same request twice gives the same end state.
- `POST` endpoints that create something or change money accept an **`Idempotency-Key`** header (a UUID the frontend generates once per user action): create employee, change salary, upload document, start import, apply import. The first response is stored for 24 hours with the key, the user and a hash of the request body; a repeat with the same key returns the stored response, and the same key with a different body returns `409`.
- Background jobs are safe to re-run: a job is claimed with `SELECT … FOR UPDATE SKIP LOCKED`, re-checking an import changes nothing, the daily rate fetch upserts by (currency, date), and the same import file is detected by its SHA-256 fingerprint.
- Every idempotent endpoint has a test that sends the same request twice.

## Atomic transactions
- Anything that changes more than one row or table succeeds or fails as a whole, in **one database transaction** (one session per request; commit at the end of the service call, roll back on any error). Never commit halfway.
- Must be atomic: a salary change (new history entry + the employee's current salary + who/when + cache version bump); mark as left / reactivate; applying an import (all rows, or only the correct rows if chosen, in one transaction); the daily rate refresh (store rates + update every employee's USD salary); create employee with its first salary entry.
- Concurrent edits use the `version` column (optimistic locking): a stale update returns `409`, never a silent overwrite.
- Files and the database can't share a transaction: upload the file first, then write the database row; if the database write fails, delete the uploaded file. Delete files only after the database change has committed.
- Tests cover rollback: force a failure in the middle and check that nothing was saved.

## Tests — every feature is covered
- **Every feature and every bug fix ships with tests in the same change.** Nothing is "done" without them.
- Cover the happy path **and** edge cases: validation errors, not-found, empty results, boundaries (page size limits, zero/negative amounts, dates), and permission/rate-limit responses where relevant.
- Backend: pytest — unit tests for services, API tests with TestClient against an isolated Postgres database per test (cloned from a migrated template). Deterministic (fixed seeds, no real network, no wall-clock dependence).
- Frontend: Vitest + Testing Library for components and hooks.
- Reuse fixtures/factories for test data instead of copying setup between tests.

## Always run the code
After every change, actually run it before saying it works:
1. Lint/format: `ruff check . && ruff format --check .` (backend), the frontend linter/type-check (`tsc --noEmit`) for UI work.
2. Run the full test suite (`pytest` / `npm test`) — not just the new tests.
3. Start the app or call the endpoint/script you changed and check the real output.
4. Report results honestly: if something fails, show the output and fix it; never claim a pass you did not see.

## Stack (fixed — don't swap without asking)
Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, PostgreSQL (everywhere: dev, tests, CI, production), uv, ruff, pytest · React + Vite + TypeScript, shadcn/ui (Tailwind + Radix), TanStack Table/Query, Recharts, Vitest · Docker / docker compose.

## Docs
- Record any new product or technical decision in `docs/DECISIONS.md` with its reason.
- Log notable AI-tool usage in `docs/AI_USAGE.md`.
- Update `README.md` setup steps when setup changes.
