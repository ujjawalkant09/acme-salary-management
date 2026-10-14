# 04 · Backend design

**Python 3.12 + FastAPI + SQLAlchemy 2.0 (sync) + Pydantic v2 + Alembic.** One web service, plus a worker container (same image) for imports and the daily rate fetch.

*Why sync SQLAlchemy?* The work is short database queries for a handful of users. FastAPI runs sync endpoints in a thread pool, so we get simpler code, simpler tests and no async/sync mixing bugs, at no real cost at this scale.

## 1. Layers
```
routers/   HTTP only: parse params, call a service, shape the response
services/  business rules: salary changes, insights maths, import validation
repos/     SQL only: queries, filters, pagination
models.py  tables · schemas.py DTOs · core/ config, db, cache, rate limit, storage, errors
worker/    background job runner
```
Rules: routers never touch SQL; services never touch HTTP; services are unit-tested without a server.

## 2. API
All under `/api/v1`. JSON; money as strings (`"184000.00"`); dates ISO-8601.

| Method & path | Purpose | Rate limit |
|---|---|---|
| `POST /auth/login` · `POST /auth/logout` · `GET /auth/me` | Session login; current user and role | 5/min on login |
| `GET /health` | Liveness + DB check | none |
| `GET /meta` | Countries, departments, titles, levels, FX table, data version | 120/min |
| `GET /employees` | List: `q, country, department_id, job_title, level, status, employment_type, sort, order, page, page_size` | 120/min |
| `POST /employees` | Create, with initial salary record | 30/min |
| `GET /employees/{id}` | Profile | 120/min |
| `PATCH /employees/{id}` | Edit; body must include `version` | 30/min |
| `POST /employees/{id}/mark-left` · `/reactivate` | Mark as left (soft delete) / undo | 30/min |
| `GET /employees/{id}/salaries` | History, newest first | 120/min |
| `POST /employees/{id}/salaries` | Salary change | 30/min |
| `PUT /employees/{id}/photo` · `DELETE` | Upload / remove photo (Admin) | 10/min |
| `GET /employees/{id}/documents` | List documents | 120/min |
| `POST /employees/{id}/documents` | Upload a document (Admin; PDF/JPG/PNG ≤ 10 MB) | 10/min |
| `GET /employees/{id}/documents/{doc_id}/download` | Short-lived signed link | 60/min |
| `DELETE /employees/{id}/documents/{doc_id}` | Remove (Admin; soft delete) | 30/min |
| `GET /fx-rates` | Rates in use and their date | 120/min |
| `GET /employees/export.csv` | Streamed CSV of the filtered list | 5/min |
| `GET /insights/summary` | Headcount, payroll USD, median USD | 60/min |
| `GET /insights/by-country` · `/by-department` | Group stats | 60/min |
| `GET /insights/by-role?country=XX` | Min/p25/median/p75/max per title+level | 60/min |
| `GET /insights/distribution?country=&bins=` | Histogram | 60/min |
| `GET /insights/outliers?country=` | Paginated, outside 1.5×IQR of peers | 60/min |
| `GET /imports/template.xlsx` | Template with headers + an example row | 30/min |
| `POST /imports` | Upload file → `202 {job_id}` | 5/min |
| `GET /imports` · `GET /imports/{id}` | History · status + counters (polled) | 120/min |
| `GET /imports/{id}/rows?action=error` | Preview rows, paginated | 120/min |
| `POST /imports/{id}/commit` · `/cancel` | Apply / abandon | 5/min |
| `GET /imports/{id}/errors.csv` | Error report | 10/min |

**Pagination envelope**
```json
{ "items": [...], "page": 2, "page_size": 20, "total": 9874, "pages": 494 }
```
Default `page_size` 20, max 100. Sort is whitelisted (no arbitrary column names) and always has `id` as a tiebreaker, so pages are stable. Offset pagination is fine at 10k rows (the deepest page < 10 ms); the upgrade is **keyset** (`?after=<cursor>`) behind the same envelope.

**Errors**: one shape everywhere
```json
{ "error": { "code": "version_conflict", "message": "This employee was changed by someone else. Reload to see the latest.", "details": {} } }
```
`400` bad params · `404` · `409` version conflict / duplicate email or code · `413` file too large · `422` validation (per-field details) · `429` rate limited (`Retry-After`).

## 2b. Roles and permissions (Q01)
- Two roles: `hr_admin` and `hr_viewer`. A `require_role("hr_admin")` dependency guards **every** write endpoint (create, edit, salary change, mark as left, uploads, imports); reads need any signed-in user. The UI hides controls too, but the API is the real check (`403` with a clear message).
- Tests cover every write endpoint as a Viewer (must be `403`) and as an Admin.
- `created_by` / `updated_by` are taken from the session, never from the request body.

## 2c. Daily exchange rates (Q16)
- A scheduled job (in the worker; daily at 16:00 UTC, after the ECB publishes) calls the Frankfurter API (ECB reference rates, no key) for the currencies in use, stores one row per currency per date, then updates `current_salary_usd` for all employees in one statement and bumps the data version (clearing the Insights cache).
- If the fetch fails or a currency is missing, the last good rates stay in use and a warning is logged; reports always show the rate date.
- Tests use a fixed rate snapshot and a fake HTTP client; no test touches the internet. The seed loads a fixed snapshot too.

## 2d. Idempotency and transactions
- **Idempotency-Key** header on `POST` endpoints that create records or change money (create employee, change salary, upload document, start import, apply import). Stored in `idempotency_keys` (key, user, endpoint, request hash, response status and body, expires after 24 hours). Same key + same body → the stored response; same key + different body → `409`. The frontend creates one key per user action (a double-click or a network retry reuses it).
- **One transaction per request**, committed at the end of the service call. Multi-row changes are atomic: salary change (history entry + current salary + audit + cache version), mark as left, create employee with first salary, import apply, daily rate refresh.
- **Optimistic locking** with `version` on employees: stale updates return `409`.
- **Files vs database:** upload the file, then write the row; on a database failure delete the file; delete files only after the database commit.

## 3. Caching
| Layer | What | Invalidation |
|-------|------|--------------|
| **Server: in-process TTL cache** (`cachetools`) | Insights and `/meta` responses | The key includes a **data version**: a single DB row bumped in the same transaction as every write. A new version → cache miss → never stale. TTL 10 min just bounds memory |
| **HTTP** | `ETag: "v<data_version>-<params hash>"` on insights/meta | The browser sends `If-None-Match` → `304`, no body |
| **Client** | TanStack Query (`staleTime` 30 s for lists, 5 min for meta) | Mutations invalidate the related queries |

*Why a data version in the DB rather than Redis pub/sub?* It's one primary-key read (~0.1 ms) and is correct even with several API instances; Redis only becomes useful when we want to **share** computed results across instances. The `Cache` interface makes that swap a config change (`CACHE_URL=redis://…`).

## 4. Rate limiting
- `slowapi` (token bucket per client key). Key = the signed-in user's id; login (no user yet) is keyed by client IP from the trusted proxy header.
- Limits per route group (table above): stricter for writes, uploads and export because they are expensive or risky.
- `429` + `Retry-After` + `X-RateLimit-Remaining` headers; the UI shows a friendly toast.
- Storage: memory in v1 → `RATE_LIMIT_STORAGE_URL=redis://…` for a shared limit across instances.

## 5. Bulk upload as a long-running job
```mermaid
sequenceDiagram
    participant UI
    participant API
    participant Store as File store
    participant DB
    participant W as Worker
    UI->>API: POST /imports (file)
    API->>API: check size, type (magic bytes), row limit
    API->>Store: save file imports/{job_id}
    API->>DB: insert import_job (queued)
    API-->>UI: 202 {job_id}
    loop every 1s
      UI->>API: GET /imports/{job_id}
    end
    W->>DB: claim queued job (FOR UPDATE SKIP LOCKED)
    W->>Store: read + parse (streaming)
    W->>DB: insert import_rows in chunks of 500, update processed_rows
    W->>Store: delete raw file
    W->>DB: status = validated (counts: create/update/error)
    UI->>API: POST /imports/{id}/commit
    API->>DB: status = commit_queued
    W->>DB: apply in ONE transaction; progress on a separate connection
    W->>DB: bump data version, status = completed
```
Design points:
- **The API never parses large files inside the request**: upload returns `202` immediately, so no request timeout and the UI stays responsive.
- **The job state lives in the database**, not in memory. A restart doesn't lose jobs: the worker stamps a heartbeat on the job while it works, and at startup and every 10 minutes, jobs in `validating` / `committing` with no heartbeat for 15 minutes are queued again (validation is idempotent; commit is one transaction, so it either happened or it didn't). A job another live worker is on is left alone.
- **Worker** = its own container in Docker Compose, from the same image as the web app, started with `python -m app.worker`. It polls `import_jobs` every second and also runs the daily exchange-rate fetch. A heavy import never slows the web pages, and each container restarts on its own. **Scale-out** = run more worker containers or machines; `SELECT … FOR UPDATE SKIP LOCKED` lets several workers share the queue safely.
- **No message broker, no Celery** (decided): the Postgres job table is the queue. It survives restarts, shows progress, needs nothing extra to run, and job status changes in the same transactions as the data. Rejected: processing inside the upload request (timeouts), FastAPI `BackgroundTasks` (lost on restart, no queue), Celery/RQ with Redis or RabbitMQ (two extra services for a few imports a year). Procrastinate (a Postgres-based queue library) would also work; our own version is ~100 lines. **Switch to a broker** if we get many task types, thousands of tasks a minute, several worker machines needing fast handoff, or needs like priorities and retries with back-off; only the "fetch next job" part would change.
- **Validation per row**: required fields, types, enums, country exists, currency matches country (warning), email format + uniqueness (in the file and the DB), salary > 0, level 1–6, dates are valid and not too far in the future. Every error is collected (not just the first) so HR fixes everything in one go.
- **Commit safety**: all-or-nothing in a single transaction; only one commit at a time (job-level lock); rows whose employee changed after the preview (`version` mismatch) are flagged rather than overwritten.
- **Performance**: openpyxl in `read_only` mode (streams; doesn't load the whole workbook), bulk `insert`/`update` in chunks, existing employees pre-loaded into a dict by `employee_code` (one query, not 10k). Target (REQUIREMENTS.md): 10k rows checked in ≤ 15 s and applied in ≤ 30 s.
- **Idempotency**: the file's SHA-256 is stored; re-uploading a completed file warns "already imported on …".

### 5b. One import pipeline, three ways in
The import is built as **source → validate → preview/apply**, so only the first step changes per source:

| Source | How data arrives | Auth |
|--------|------------------|------|
| File upload (v1) | `POST /imports` with an .xlsx/.csv | HR user session |
| Pull connector (later) | A scheduled job calls the HR tool's API (Workday, BambooHR, …) and creates an import job from the rows | Credentials for that tool, stored as secrets |
| Push API (later) | `POST /api/v1/integrations/employees:batch` with up to 1,000 employees per call | **API key**: shown once, stored only as a hash, can be revoked or rotated, limited to this endpoint. Calls send an `Idempotency-Key` header so a retried request is not applied twice |

All three create the same `import_job`, go through the same validation rules and leave the same history, so a row from Workday is checked exactly like a row from Excel. Pushed batches can be applied automatically (if valid) or held for HR review; that choice is made when the push API is built.

## 6. File storage (imports and photos)
A `Storage` interface: `put(key, bytes)`, `get(key)`, `delete(key)`, `url(key)`.
- `LocalStorage` (dev/tests) → `./storage/`
- `S3Storage` (prod) → a private AWS S3 bucket in the same region; photos are served through short-lived signed URLs or proxied with `Cache-Control: max-age=31536000, immutable`.
- Photo pipeline: check magic bytes (not just the extension) → Pillow open (decompression-bomb guard) → crop/resize to 256×256 → WebP → new key per upload.

## 7. Security baseline
- Validation at the edge with Pydantic; SQL only through bound parameters (ORM).
- Upload hardening: size limit, magic-byte check, `.xlsm` (macros) rejected, row limit, read-only parsing.
- **CSV injection**: export cells starting with `= + - @` get a leading `'`.
- CORS restricted to the app origin; security headers (CSP, `X-Content-Type-Options`, `Referrer-Policy`).
- **No salary or PII in logs**; request logs record path, status, timing and request id only.
- Secrets from environment variables only.
- **Login**: email and password with two roles; the demo has one account per role. Passwords are stored only as hashes in the `users` table (demo users are created by the seed from secrets); login sets a signed, `HttpOnly`, `Secure`, `SameSite=Lax` session cookie; the login endpoint has a strict rate limit (5/min) against guessing.
- Auth is a seam: every endpoint depends on `get_current_user`; adding SSO later only changes how that user is found.
- Uploads (photos, documents, imports): size limit, magic-byte type check, allowed types only (PDF, JPG, PNG; XLSX/CSV for imports), random storage keys, files never served from the app's own domain path without `Content-Disposition: attachment`.
- Gender is excluded from list responses and CSV export by the response schemas, not by the UI.

## 8. Observability
Structured JSON logs with a `request_id` (also returned as `X-Request-ID`), request timing, a slow-query log (> 200 ms), and job logs per import.

## 9. Configuration (env)
`DATABASE_URL`, `SECRET_KEY` (signs session cookies), `DEMO_ADMIN_PASSWORD`, `DEMO_VIEWER_PASSWORD` (used only by the seed), `FX_API_URL`, `MAX_DOCUMENT_MB=10`, `CACHE_URL` (default `memory://`), `RATE_LIMIT_STORAGE_URL` (default `memory://`), `STORAGE_BACKEND` (`local` / `s3`), `S3_*`, `MAX_UPLOAD_MB=10`, `MAX_IMPORT_ROWS=20000`, `CORS_ORIGINS`, `LOG_LEVEL`.

## 10. Testing strategy
| Level | What | Tooling |
|-------|------|---------|
| Unit | Insights maths (median, percentiles, IQR outliers), FX conversion, import row validation, salary-change rules | pytest, pure functions, no DB |
| Service/repo | Filters, sort, pagination, current-salary consistency, optimistic locking | pytest + temporary SQLite per test (transaction rollback) |
| API | Status codes, error shapes, 429, ETag/304, import job lifecycle (worker run synchronously in tests) | FastAPI `TestClient` |
| Frontend | Key components: directory filters, salary form, import preview | Vitest + Testing Library |

Deterministic: fixed seeds, frozen "today" in date-dependent tests, no network. Target: the whole backend suite in < 10 s.
