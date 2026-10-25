# 03 · Database design

Engine: **PostgreSQL** everywhere (Docker locally, in the tests and CI, and on the EC2 server). One schema via SQLAlchemy + Alembic; no engine-specific SQL in the app code.

## 1. Entity relationship diagram
```mermaid
erDiagram
    COUNTRIES ||--o{ EMPLOYEES : "works in"
    DEPARTMENTS ||--o{ EMPLOYEES : "belongs to"
    USERS ||--o{ SALARY_RECORDS : "created"
    USERS ||--o{ EMPLOYEE_DOCUMENTS : "uploaded"
    EMPLOYEES ||--o{ EMPLOYEE_DOCUMENTS : "has files"
    EMPLOYEES ||--o{ SALARY_RECORDS : "has history"
    FX_RATES ||--o{ COUNTRIES : "currency"
    IMPORT_JOBS ||--o{ IMPORT_ROWS : "contains"
    IMPORT_JOBS ||--o{ SALARY_RECORDS : "created by (optional)"

    COUNTRIES { char2 code PK; text name; char3 currency }
    DEPARTMENTS { int id PK; text name UK }
    USERS { int id PK; text email UK; text name; text password_hash; text role; bool active; timestamp last_login_at }
    FX_RATES { char3 currency PK; date rate_date PK; numeric usd_per_unit; text source }
    EMPLOYEE_DOCUMENTS { int id PK; int employee_id FK; text kind; text file_name; text content_type; int size_bytes; text storage_key; int uploaded_by FK; timestamp uploaded_at; timestamp deleted_at }
    EMPLOYEES {
      int id PK; text employee_code UK; text first_name; text last_name; text email UK
      text job_title; smallint job_level; int department_id FK; char2 country_code FK; text city
      text gender; text employment_type; numeric fte; date hire_date
      text status; date left_on; text photo_key
      numeric current_salary; char3 current_currency; numeric current_salary_usd; date salary_effective_date
      int version; timestamp created_at; timestamp updated_at; int updated_by FK
    }
    SALARY_RECORDS {
      int id PK; int employee_id FK; numeric amount; char3 currency; date effective_date
      text reason; text note; int import_job_id FK; int created_by FK; timestamp created_at
    }
    IMPORT_JOBS {
      uuid id PK; text filename; char64 file_sha256; text status; text mode
      int total_rows; int processed_rows; int created_count; int updated_count; int error_count
      text error_message; timestamp created_at; timestamp started_at; timestamp finished_at
    }
    IMPORT_ROWS { uuid job_id PK; int row_number PK; text action; json payload; json errors }
```

## 2. Tables

### `employees`
| Column | Type | Notes |
|--------|------|-------|
| `id` | integer PK | Internal; never shown |
| `employee_code` | text, **unique**, not null | Business key (e.g. `ACM-004521`); import matching key |
| `first_name`, `last_name` | text, not null | |
| `email` | text, **unique (case-insensitive)** | Work email |
| `job_title` | text, not null | Free text, trimmed; normalized casing on write |
| `job_level` | smallint 1–6 | For peer comparison and future bands |
| `department_id` | FK → departments | |
| `country_code` | char(2) FK → countries | ISO 3166-1 |
| `city` | text, nullable | |
| `gender` | text, nullable (`female` / `male` / `non_binary` / `undisclosed`) | Optional (Q10). Never shown in lists, exports or Insights |
| `employment_type` | enum `full_time` / `part_time` / `contractor` | Check constraint |
| `fte` | numeric(4,3), default 1.000 | 0.5 = half-time; insights use `salary / fte` |
| `hire_date` | date | |
| `status` | enum `active` / `left` | Soft delete: "mark as left" (Q40) |
| `left_on` | date, nullable | Leaving date |
| `photo_key` | text, nullable | Object-storage key, **not** the image |
| `current_salary` | numeric(14,2) | **Denormalized** from the latest effective salary record |
| `current_currency` | char(3) | |
| `current_salary_usd` | numeric(14,2) | Precomputed with the rates in use: sorting and insights without joins |
| `salary_effective_date` | date | |
| `version` | integer | Optimistic locking: an update must send the version it read |
| `created_at`, `updated_at` | timestamptz | |
| `updated_by` | FK → users | Who made the last change (Q04) |

### `salary_records` (append-only history)
| Column | Type | Notes |
|--------|------|-------|
| `id` | PK | |
| `employee_id` | FK, not null | |
| `amount` | numeric(14,2) > 0 | **Annual base**, local currency |
| `currency` | char(3) | Usually the country's currency |
| `effective_date` | date | |
| `reason` | enum `hire` / `promotion` / `merit` / `market_adjustment` / `correction` / `other` | |
| `note` | text, nullable | |
| `import_job_id` | FK, nullable | Traceability: which upload created this record |
| `created_by` | FK → users | Who made the change (Q04) |
| `created_at` | timestamptz | |

Rows are **never updated or deleted**; a mistake gets a new `correction` record.

### Reference tables
- `countries(code, name, currency)`: 6 rows (IN, US, CA, SG, BR, AU), seeded.
- `departments(id, name)`: small; normalized so a rename touches one row and filters stay typo-free.
- `fx_rates(currency, rate_date, usd_per_unit, source)`: **one row per currency per day** from the daily ECB fetch (Q16). The newest date is "rates in use"; after each fetch one bulk `UPDATE employees SET current_salary_usd = …` refreshes USD values. Old rows are kept, so any report can say which date it used.

### `users`
| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `email` | text, unique (case-insensitive) | Login name |
| `name` | text | Shown in the sidebar and in "changed by" |
| `password_hash` | text | Argon2/bcrypt; the password itself is never stored |
| `role` | enum `hr_admin` / `hr_viewer` | Q01 |
| `active` | bool | Disable without deleting history |
| `last_login_at` | timestamptz | |

### `employee_documents`
| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `employee_id` | FK | |
| `kind` | enum `photo` / `document` | One current photo per employee |
| `file_name`, `content_type`, `size_bytes` | | PDF, JPG, PNG only; ≤ 10 MB (Q08) |
| `storage_key` | text | Key in private object storage; the file is never in the database |
| `uploaded_by`, `uploaded_at` | FK → users, timestamptz | |
| `deleted_at` | timestamptz, nullable | Soft delete; the file is purged from storage after 30 days |

### `idempotency_keys`
| Column | Type | Notes |
|---|---|---|
| `key` | text | From the `Idempotency-Key` header; primary key together with `user_id` |
| `user_id` | FK → users | Keys are scoped per user |
| `endpoint` | text | e.g. `POST /employees/{id}/salaries` |
| `request_hash` | char(64) | SHA-256 of the body; a different body with the same key → `409` |
| `status_code`, `response_body` | int, jsonb | Returned again on a repeat |
| `created_at`, `expires_at` | timestamptz | Removed after 24 hours by the worker |

### Import tables (bulk upload)
- `import_jobs`: one row per upload. `status`: `queued → validating → validated → committing → completed`, or `failed` / `cancelled`. `mode`: `all_or_nothing` / `valid_rows_only`. The counters drive the progress bar.
- `import_rows`: the parsed staging rows. `action`: `create` / `update` / `unchanged` / `error`; `payload` = normalized values; `errors` = list of `{field, message}`. Powers the preview and the error report. Purged after 30 days.

Raw uploaded files are **not** kept after parsing (less PII lying around).

## 3. Indexes (each one tied to a real query)
| Index | Serves |
|-------|--------|
| `employees(employee_code)` unique | Import matching, lookup by code |
| `employees(lower(email))` unique | Duplicate check, search |
| `employees(status, country_code, job_title)` | Directory filters (almost always `status = active`) and role-within-country insights |
| `employees(department_id)` | Department filter and insight |
| `employees(last_name, first_name)` | Default sort and name prefix search |
| `employees(current_salary_usd)` | Sort by salary, distribution |
| `employee_documents(employee_id, deleted_at)` | Documents on the employee page |
| `fx_rates(rate_date DESC)` (PK covers currency + date) | "Rates in use" lookup |
| `users(lower(email))` unique | Login |
| `salary_records(employee_id, effective_date DESC)` | Profile history, "latest effective" lookup |
| `import_rows(job_id, action)` | Preview counts, error report |

Each is verified with `EXPLAIN` in a test or doc. Not added: an index per column "just in case", since every index slows writes and the import.

**Search at 10k rows:** `ILIKE '%term%'` over names, email and code is a sequential scan, but 10k rows scan in a few ms. If we grow 10–100×: Postgres `pg_trgm` GIN index, behind the same API.

## 4. Why the denormalized `current_salary`
The "latest salary per employee" query (a window function or subquery over history) would run on *every* list page, sort and insight. Storing the current value on `employees`:
- makes list, sort and aggregates single-table, index-friendly queries;
- costs one extra column update **in the same transaction** as the new salary record (kept consistent by the service layer, and checked by a test);
- for **future-dated** raises, a small daily job (and a startup check) promotes records whose `effective_date` has arrived.

## 5. Money and dates
- `NUMERIC(14,2)` (up to 999,999,999,999.99, plenty for yearly salaries in any currency, including INR) + Python `Decimal` end to end; never floats. JSON sends amounts as strings.
- Dates are `DATE` (effective dates have no time zone); audit timestamps are UTC `timestamptz`.

## 6. Photos and documents
Documents follow the same pattern as photos: stored under `employees/<id>/docs/<uuid>.<ext>`, served through short-lived signed links, only HR Admins can upload or delete.

`photo_key` like `employees/4521/9f3c….webp` points to S3-compatible object storage (local folder in dev). Images are re-encoded to 256×256 WebP on upload (EXIF stripped). Served with long-lived cache headers; a new upload gets a new key, so caches never serve a stale photo.

## 7. Seed data (10,000 employees)
- Deterministic: a fixed RNG seed gives the same 10k people every run, so tests and the demo are stable.
- Realistic: the 6 countries weighted by headcount (India largest), departments, titles × levels, a salary = base by role/level × country factor × noise, 1–4 history records per person, a few deliberate outliers (so the outlier view has something to show).
- Fast: bulk inserts in batches of 1,000 inside one transaction; target < 10 s.
