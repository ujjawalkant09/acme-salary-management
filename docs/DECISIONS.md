# Decisions log

Every decision, where it came from and why. Q-numbers refer to the decision book (questions answered by the author on 14 Oct 2026). Hiring-team guidance (Sandli, 14 Oct 2026): make reasonable assumptions for load, speed, recovery and import limits and document them; design for 10,000 employees; import/export optional; basic logging is enough.

## Users and access
| Decision | Source | Why |
|---|---|---|
| Two roles: **HR Admin** (changes data) and **HR Viewer** (read-only); enforced by the API, edit controls hidden in the UI | Q01 | Some people report on pay but must not change it |
| Email + password login; passwords stored as hashes; signed session cookie; demo has one login per role | Q02 | Enough for the persona; SSO later through the same seam |
| HR only; no employee self-service | Q03 | Different product, 10,000 logins |
| Record who and when for every salary change and edit | Q04 | "Who changed this?" is a common HR question |
| No country-limited access | Q05 | Not needed now; queries go through one place |
| No limit on concurrent logins | Q33 | Targets assume ~5 at once, but nobody is blocked |

## Employee data
| Decision | Source | Why |
|---|---|---|
| Unique employee code (e.g. ACM-004521) is the business key and import matching key | Q06 | Stable across countries |
| No manager field | Q07 | Not needed for salary questions |
| Photos and documents: PDF/JPG/PNG ≤ 10 MB, private storage (S3), short-lived download links; Admins upload/delete, Viewers view | Q08 (re-confirmed) | Employee files with the record |
| Keep data after leaving; status "left"; never deleted | Q09, Q40 | History must survive; erasure is future work |
| Gender stored as an optional field only; not in lists, exports or reports | Q10 | Author's choice; no pay-fairness analysis |
| This app is the source of truth for pay | Q11 | No other HR system |

## Salary rules
| Decision | Source | Why |
|---|---|---|
| Yearly base salary; employment type full-time / part-time / contractor; part-time % | Q12 | One unit makes reports correct |
| Currency stored per salary entry, default = country's currency | Q13 | Handles people paid in another currency |
| Base salary only | Q14 | Bonuses etc. are out of scope |
| Future and past start dates allowed; no arrears calculation | Q15 | Arrears are payroll work |
| **Live exchange rates**: daily ECB reference rates via Frankfurter, stored by date; last good rates kept if a fetch fails; reports state the rate date | Q16 (re-confirmed) | Free API, no key; storing rates keeps figures explainable |
| Reports across countries in USD; within a country in local currency | Q17, Q42 | Fair comparison without mixing currencies |
| Part-timers compared at the full-time rate | Q18 | Fair comparison |
| No approval workflow | Q19 | HR records approved changes |
| No pay bands; compare with the peer median (same role, level, country) | Q20 | No official ranges exist |
| Salary history never edited; corrections are new entries | Q41 | Truthful history |

## Import, export and reports
| Decision | Source | Why |
|---|---|---|
| Excel/CSV import (background job, preview) and CSV export | Q21 | Moving off Excel is the core pain |
| Regular use, so preview before saving | Q22 | Safety |
| Whole file rejected by default; option to save only correct rows; failed rows downloadable with reasons | Q23 | No half-updated data; easy fixing |
| Missing people are never changed | Q24 | No accidental "left" marks |
| One file or many; country is a column | Q25 | Flexibility |
| ≤ 20,000 rows and 10 MB per file | Q26 | Covers all 10,000 employees with headroom |
| One import at a time | Q27 | Avoids conflicting bulk writes |
| No scheduled email reports | Q28 | On screen + CSV is enough |
| Insights priorities: cost by country/department, median by role, spread, unusual salaries | Q29 | Leadership's usual questions |

## Compliance, reliability and performance
| Decision | Source | Why |
|---|---|---|
| Employees in 6 countries: India, United States, Canada, Singapore, Brazil, Australia | Author | The brief says "multiple countries"; no specific countries are required |
| One deployment: **a single AWS EC2 server in Mumbai (ap-south-1) running Docker Compose** (Caddy for HTTPS, app, Postgres), files in S3, logs in CloudWatch | Author | Nothing in the brief requires a platform; one server easily handles 10,000 (and 50,000) employees; simplest to run and explain. Mumbai is the closest region to India, the largest employee group. See design/06-DEPLOYMENT.md |
| Data protection laws out of scope; keep personal data to a minimum | Author | Not part of the brief |
| Nightly database dumps to S3 (kept 14 days) and weekly disk snapshots; restore within ~2 hours; if the server is down, the app is down until restored | Q31 (revised) | Practical for one server. The Q31 answer (7-day managed backups, 4-hour restore) assumed RDS; replaced when hosting moved to one EC2 server |
| Accessibility is not a goal; keep the UI library's built-in basics | Q32 | Author's choice |
| Busiest at the April salary review and month-end | Q34 | Planning assumption |
| Design and test for 10,000 employees | Q35 | Hiring team guidance |
| Speed targets as in REQUIREMENTS.md | Q36 | Our own, since none were set |
| No wake-up delay: the server is always on | Q37 (superseded) | The free Render demo was dropped in favour of one AWS server |
| Structured logs to CloudWatch; clear errors; no alerting or tracing | Q38 | Hiring team guidance |

## Reliability rules
| Decision | Source | Why |
|---|---|---|
| `Idempotency-Key` header on POSTs that create records or change money; responses stored 24 h; same key + different body → 409 | Author (CLAUDE.md) | Double-clicks and network retries never create duplicates or apply a raise twice |
| One database transaction per request; multi-row changes (salary change, import apply, rate refresh, mark as left, create with first salary) are atomic; optimistic locking with `version` | Author (CLAUDE.md) | No half-saved data; no silent overwrites |

## Background jobs
| Decision | Source | Why |
|---|---|---|
| No message broker and no Celery: a Postgres `import_jobs` table is the queue; a separate **worker container** (same image, `python -m app.worker`) claims jobs with `SELECT … FOR UPDATE SKIP LOCKED`, validates in chunks of 500, applies in one transaction, and also runs the daily rate fetch | Author | Survives restarts, shows progress, nothing extra to run; volumes are a few imports a year. Switch to Celery/RQ only with many task types or high throughput |

## UI
| Decision | Source | Why |
|---|---|---|
| Employee details on their **own page** (/people/<id>); Back returns to the filtered list | Q39 | Room for history and documents; shareable link |
| Left sidebar with signed-in user; calm Home; left filter panel with counts and chips; Insights in tabs | UI research (design/07) | Feedback that v2 was crowded |
| No dark mode; each country's own number format (₹18,40,000 / R$ 202.500 / $64,500) | Author | |
| The People filter panel starts **hidden**; "Show filters" opens it (not remembered between visits) | Author | The table gets the full width on first view; the chips above the table still show any active filters |

## Technical and delivery
| Decision | Why |
|---|---|
| Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2 | The role's language; typed and fast |
| PostgreSQL everywhere (Docker locally); SQLite only for fast unit tests; CI also runs tests on Postgres | Same engine in dev and prod |
| React + Vite + TypeScript; shadcn/ui only; TanStack Table and Query; Recharts | One light styling system |
| Docker for local development and deployment | One-command setup matching production |
| GitHub repo, private while building and made public by the author when implementation is done; GitHub Actions builds the image, pushes to ECR (OIDC, no stored keys) and deploys with SSM Run Command (no SSH port open); secrets in SSM Parameter Store; first setup and every manual deploy through one command, `.claude/skills/aws-deploy/scripts/deploy.sh` (see below) | Simple and secure. Frontend served by the same server (same origin: no CORS, simple secure cookies); S3 + CloudFront for the frontend is on the documented scaling path. Rejected: App Runner (closed to new customers since 30 April 2026), ECS Express Mode + RDS (load balancer, cluster and managed DB are more than this app needs) |
| **One-command deploy:** `deploy.sh` in the Claude skill `.claude/skills/aws-deploy/` applies a CloudFormation stack (all AWS resources), creates missing secrets, builds and pushes the image, sets the DNS record and releases through SSM; safe to re-run; `destroy.sh` removes it all | Author asked for "run the script and it's deployed". CloudFormation over Terraform: no extra tool or state file, re-runs change nothing, failed changes roll back. Over raw AWS CLI calls: those need hand-written existence checks for every resource |
| Deployment code lives in the skill folder `.claude/skills/aws-deploy/`, not a separate `deploy/` folder; the other skills stay git-ignored, and `aws-deploy` may be pushed when GitHub Actions needs it (its `config.env` stays ignored) | Author | The author wants the deploy run as Claude skills; GitHub can only run code that is in the repo |
| **GitHub Deploy button** (manual `workflow_dispatch` on `main`) runs all CI checks, then `deploy.sh --release`; not automatic on every push | Author | The demo server is off most of the time; a button starts it, deploys and keeps the 4-hour auto-stop. Every push still runs CI |
| The GitHub OIDC role can only release (push the image, sync server scripts, start the server, send SSM commands); infrastructure, IAM and secret changes run only from the author's laptop | Security | A leaked or misused workflow can't widen its own access, create resources or read secrets. The role trusts GitHub's ID-based subject (`repo:owner@id/repo@id:environment:production`), so a renamed or re-created repo with the same name can't use it |
| CI runs the real image against Postgres, besides the SQLite unit tests | A Postgres-only bug | The worker's job claim failed only on Postgres; SQLite ignores `FOR UPDATE` |
| Every deploy runs `python -m scripts.seed --if-empty` after migrations: a fresh database gets the 10,000 demo employees and two logins, an existing one is left alone | Deploy design | One deploy command sets up a new server completely, and re-running it can never overwrite real data |
| **Demo server is off when unused:** `server.sh stop` backs up then stops; `server.sh start` turns it on and it backs up and stops itself after 4 hours | Author | Cuts the cost to about $6/month while idle; the Elastic IP keeps the address, so DNS never changes |
| **$10 monthly AWS budget alert** (email at 80% actual and 100% forecast) | Author | Early warning if a server is left running; it is an alert, not a cap |
| No credential ever leaves the author's machine: AWS keys only in a named profile, secrets only through pipes, author-only scripts refuse captured output, Claude never reads `.env` or secret values | Author | The author asked that no credential gets out |
| Public address **acme.docrelay.in** (author's GoDaddy domain); the script sets the `acme` A record to the Elastic IP through the GoDaddy API, with a personal access token (or KEY:SECRET pair) in the git-ignored `.env` | Author | No manual DNS step; the Elastic IP never changes, so the record is set once. Changed from `docrelay.io`, which is registered at Namecheap, not in the author's GoDaddy account |
| Server is **`t4g.small` (Graviton, ARM)** instead of `t3.small` | Author | About 20% cheaper for the same size; the image builds natively on the author's Apple Silicon Mac and on GitHub's ARM runners |
| Secrets never in the repo, image or logs | Security baseline |
| Money stored as `NUMERIC(14,2)` and handled as Python `Decimal` end to end; sent as strings in JSON; never floats | Exact amounts; 14 digits leaves headroom for yearly salaries in any currency |
| Small commits, one per step; no AI attribution lines in commit messages; `.claude/skills/` git-ignored and not pushed until the author decides (except `aws-deploy`, published at the author's request); `.claude/CLAUDE.md` (the AI working rules) committed | Reviewable history; the AI instructions are visible to reviewers |
| Word files (`*.docx`, including the assessment brief) are git-ignored and never pushed | The brief belongs to the hiring team; the repo is public |
| Demo video 3–5 minutes from a written script | |

## Implementation (backend and frontend, 14 Oct 2026)
| Decision | Why |
|---|---|
| **Services own the transaction**: each write service ends with one `commit()`; the request's session rolls back anything left over | One place where a change is saved; easy to see that a salary change, leave, create or import apply is all-or-nothing |
| **Idempotency key saved in the same transaction as the work**: the key row is added before the work runs and committed with it, then the response is stored on it. A retry of an unfinished request gets `409`, never a second change | No window where the work is saved but the key isn't (or the reverse) |
| Salary changes also send the employee's `version`; every salary change (even a future-dated one) gives a new version | A raise based on a stale screen is refused instead of silently stacking |
| Current salary = the latest entry in effect (ties: the newest entry); for someone who hasn't started yet, their earliest entry (ties: the newest). A backdated entry older than the current one only changes history; a daily task promotes future entries | One clear rule; same-day corrections replace the current amount, also before the start date |
| Salary start dates: not before the hire date and at most one year ahead | Catches typos without blocking planned raises |
| Marking someone as left takes effect immediately, whatever leaving date is entered | Simple; the date is recorded for history |
| Emails are stored lower-cased with a plain unique index (instead of an index on `lower(email)`) | Same effect, works the same on SQLite and Postgres |
| "Unusual" = outside 1.5 × IQR of the same role, level, country and currency, full-time equivalent; groups under 4 people are never flagged; the employee page shows the peer band from 2 people | Standard, explainable rule; tiny groups give noise |
| Filter counts leave out the filter's own selection (choosing India still shows how many are in the US) | Users see what each option would add |
| Import: blank optional cells (city, gender) leave stored values alone; departments must already exist; a blank currency keeps the employee's current currency (new people: the country's); a changed salary without a date starts today, or on the start date of someone who hasn't started (new people: the hire date); people who left can't get salary changes by import; the row limit is checked by the worker, not during upload | Safe defaults; nothing is cleared or created by accident |
| Applying an import re-checks each row against the database: an employee who changed, or a code or email someone took after the check, stops `all_or_nothing` and skips just that row with `valid_rows_only`. A failed job's file is deleted (failed jobs are never retried) | Nothing is overwritten or half-applied by a change made during review; no personal data left in storage |
| Import jobs carry a heartbeat; the worker re-queues only jobs quiet for 15 minutes, at startup and every 10 minutes | A restart recovers stuck jobs without taking over one another worker is still on |
| The daily rate refresh computes USD salaries in Python (same rounding as everywhere else) and writes them without touching `updated_at` or `version` | "Updated by" shows the last real edit; no cent differences between the app and the refresh |
| If storing an idempotent response fails after the work committed, the request still returns its result; a retry gets `409` "already processed" | The client sees what happened, and the work never runs twice |
| An import waiting for review also blocks a new one (cancel it first) | "One import at a time" with no half-reviewed jobs left behind |
| The CSV export uses the import's column names, so an exported file can be edited and imported back | Excel stays a two-way exit path |
| Export is built in memory instead of streamed | 10,000 rows are ~2 MB and take 0.16 s; streaming with a request-scoped database session is fragile |
| Local file downloads go through signed links to the app (15 minutes); S3 signed links replace them with the AWS deployment | Same short-lived-link behaviour in development and production |
| Sessions use Starlette's signed-cookie `SessionMiddleware` | No session table; the app stays stateless |
| The worker fetches exchange rates after 16:00 UTC, once a day | The ECB publishes around 16:00 CET |
| Tests hash passwords with bcrypt cost 4 (the app uses the default, 12) | The full backend suite runs in ~4 s |
| Frontend: shadcn/ui components written into `src/components/ui` by hand, `oxlint` for linting, newest package majors (React 19, React Router 8, TanStack Table 9, Vite 8) | No interactive CLI step; fast lint; current APIs |
| Docker layers are cached between builds: in ECR under a `buildcache` tag for releases (built on a `docker-container` BuildKit builder, since Docker's default builder can't export a cache), and in the GitHub Actions cache for CI | A release after a code-only change builds in ~10 s instead of ~60 s; the cache tag is re-pushed each build, so the keep-last-10 rule never expires it, and replaced caches (untagged) are dropped after a day so they don't use up the 10 rollback slots |
| Hashed `/assets/*` files are cached for a year (`immutable`); `index.html` is sent with `no-cache` | Asset names change with their content; a stale `index.html` after a release would point at assets that no longer exist |

## As-user oracles (15 Oct 2026)
| Decision | Why |
|---|---|
| Real-browser checks ("as-user oracles") in `e2e/`: one file per feature with numbered scenarios S1, S2…, each ending GREEN, RED or SKIP, plus a `.md` click path per feature. Playwright for Python, in its own uv project | They catch what unit and API tests can't: what the form actually sends, what each role sees, a retried save. Python keeps them in the backend's toolchain; a separate project keeps Playwright out of the production image |
| Committed in `e2e/` and run in CI against the production image on Postgres (and so before every deploy), not kept as a local Claude skill | `.claude/skills/` is not pushed; checks that guard releases belong in the repo |
| `/api/v1/health` reports the build commit (`GIT_COMMIT`, set by CI and `deploy.sh`); the runner refuses to test a build from another commit | A RED against an old build blames the wrong code. A commit hash reveals nothing a reviewer of this repo can't see |
| Scenarios that change data SKIP unless `ORACLE_ALLOW_WRITES=1`; each uses its own seeded employee | A read-only run is safe against a working database or the demo; write scenarios can't interfere with each other |
| Selectors are roles, labels and visible text; a `data-testid` only where text is fragile (`current-salary`) | Tests what a person sees and stays readable; no test ids sprinkled everywhere |
| The browser runs in UTC | The salary form dates "today" from the browser's clock and the server uses UTC; in India between 00:00 and 05:30 a local "today" is the server's tomorrow and would be saved as an upcoming change |
| Each role signs in once per run and later scenarios reuse its cookie | One full run signs in 4 times, under the 5-a-minute limit, so it also works against the rate-limited demo |
| A Claude skill, `as-user-oracles`, runs and writes the oracles; it is committed (the author's call, like `aws-deploy`) | The workflow (throwaway app, probe the page, prove a new scenario can go RED) is the same each time; committed, CI tests its scripts |
| The skill's throwaway app makes its own database, secret and random demo passwords instead of reading `backend/.env` | Data-changing scenarios never touch the dev database, it works in a fresh worktree, and no real password is read |
| The signed-in user reaches the pages through React context set by `App`, not from the query cache | Signing out crashed the app (blank page): pages read the cache and re-rendered with no user before `App` swapped to sign-in. Found by the new oracle (login S4) |

## Test and security review (15 Oct 2026)
| Decision | Why |
|---|---|
| "One open import at a time" is also a partial unique index (`uq_import_jobs_one_open`); the service's check stays for the friendly message, and two uploads at the same moment get the generic `409` | The check alone let two simultaneous uploads both through |
| The problem-rows CSV (`errors.csv`) escapes formulas the same way as the employee export | It writes back cells exactly as uploaded, so a file from someone else could put a live formula in front of an HR Admin |
| Frontend coverage with `@vitest/coverage-v8` (`npm run coverage`), leaving out the vendored shadcn/ui files; backend coverage with `pytest-cov` on demand (`uv run --with pytest-cov`) | Shows untested code without adding a backend dependency |
| Kept as they are: login is limited per IP (5 a minute) and not per account; uvicorn trusts forwarded headers from any address | bcrypt keeps guessing slow; only Caddy can reach the app, and Caddy replaces `X-Forwarded-For`. Revisit if port 8000 is ever exposed |
| Two indexes from an `EXPLAIN ANALYZE` pass over the app's real queries on Postgres (10,000 employees, 35,283 salary entries): `salary_records (created_at, id)` and `employees (lower(job_title))`. Search (`%term%`) and deep pages still read the whole table | "Recent salary changes" sorted every salary entry to return 10 (23.8 ms → 0.07 ms) and salary entries only grow; the job-title filter compares lower case, which the `job_title` column index can't serve (2.4 ms → 0.5 ms). The rest already used an index or stays under 16 ms at 10,000 rows |

## Async backend (15 Oct 2026)
| Decision | Why |
|---|---|
| `async def` endpoints and SQLAlchemy `AsyncSession` throughout: API, services, repositories, the worker loop (with `httpx.AsyncClient`) and the seed script. Replaces the first sync design | Author's choice. One event loop serves requests that are waiting on the database without a thread each. Measured with ApacheBench (one uvicorn process, Postgres 16, 10,000 employees, single runs on a laptop): 13–43% more requests a second at 10–50 at once, no clear difference one at a time, slower slowest-5% (p95) at 50+. At 100 at once the sync server stalled: its 40 threads waited on 15 database connections and requests failed after 30 s; async served all of them. At the expected load (about 5 people) both answer in 5–25 ms |
| `DATABASE_URL` keeps its sync form (`sqlite:///…`, `postgresql+psycopg://…`); the app maps SQLite to `aiosqlite`, and psycopg runs in its own async mode | Alembic, the deploy configs and every `.env` stay as they are |
| SQLite connections are not pooled (`NullPool`) | A SQLite connection is cheap to open, and an aiosqlite connection belongs to the event loop that opened it (the test client runs the app on its own loop) |
| bcrypt, Pillow, building the xlsx template and file reads/writes run in a thread (`asyncio.to_thread`) | A slow call on the event loop would hold up every other request |
| After a write, the service reloads the employee (`refresh()`) before building the response | An async session can't load the department on first access; this also fixed a bug in the sync version, where moving someone to another department returned the old department's name |
| `Idempotency-Key` handling reads the user's id before running the work | A rollback expires every loaded object; the sync session reloaded it silently, the async one raised (`MissingGreenlet`), so a race on the same key would have returned a 500 |
| Tests: `pytest-asyncio` in auto mode; a coroutine that is never awaited fails the test | A forgotten `await` otherwise only prints a warning and the test can still pass |

## Wake page (15 Oct 2026)
| Decision | Why |
|---|---|
| A wake page at `wake.acme.docrelay.in` (Lambda + API Gateway HTTP API + ACM certificate) starts the stopped server; the main address keeps pointing straight at the server | Something has to answer while the server is off. A separate address needs no CloudFront in front of the app, no DNS change for `acme` and no change to Caddy's certificate |
| Access is a shared wake code (64 random hex characters in SSM, compared in constant time), shareable as `#code=…` in the link; API Gateway throttles the whole page to 2 requests a second | The app's own logins live on the server that is off. Cognito or per-person expiring links are more to build and run than "may start a demo server" needs; the worst a leaked code does is start the server, and the app still needs a login. The part after `#` never reaches a server or a log |
| Starting needs a click, not just a visit | Crawlers and link previews would otherwise keep the server on |
| Every boot schedules the auto-stop (a systemd unit that runs before the SSM agent, so `server.sh start <hours>` still wins) | A server started by the wake page or the AWS console would otherwise run until someone stops it |
| The wake code lives one level below the app's secrets (`/acme-salary/wake/WAKE_CODE`) | The server reads only the top level into its settings, so the app never gets it |
| The Lambda's code is uploaded by `deploy.sh` (`update-function-code`) after the stack; the stack holds a placeholder | Inline code in the template is capped at 4 KB and can't be tested as a file; a separate code bucket would have to exist before the stack that creates the bucket |
| The certificate is requested by `deploy.sh`, which adds ACM's proof record in GoDaddy and waits, and is passed to the stack; the stack's wake address is off until it exists | CloudFormation can only finish DNS validation by itself in Route 53; the DNS is in GoDaddy |
