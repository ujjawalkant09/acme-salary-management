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

## Technical and delivery
| Decision | Why |
|---|---|
| Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2 | The role's language; typed and fast |
| PostgreSQL everywhere (Docker locally); SQLite only for fast unit tests; CI also runs tests on Postgres | Same engine in dev and prod |
| React + Vite + TypeScript; shadcn/ui only; TanStack Table and Query; Recharts | One light styling system |
| Docker for local development and deployment | One-command setup matching production |
| GitHub repo, private while building and made public by the author when implementation is done; GitHub Actions builds the image, pushes to ECR (OIDC, no stored keys) and deploys with SSM Run Command (no SSH port open); secrets in SSM Parameter Store; first setup and every manual deploy through one command, `.claude/skills/aws-deploy/scripts/deploy.sh` (see below) | Simple and secure. Frontend served by the same server (same origin: no CORS, simple secure cookies); S3 + CloudFront for the frontend is on the documented scaling path. Rejected: App Runner (closed to new customers since 30 April 2026), ECS Express Mode + RDS (load balancer, cluster and managed DB are more than this app needs) |
| **One-command deploy:** `deploy.sh` in the Claude skill `.claude/skills/aws-deploy/` applies a CloudFormation stack (all AWS resources), creates missing secrets, builds and pushes the image, sets the DNS record and releases through SSM; safe to re-run; `destroy.sh` removes it all | Author asked for "run the script and it's deployed". CloudFormation over Terraform: no extra tool or state file, re-runs change nothing, failed changes roll back. Over raw AWS CLI calls: those need hand-written existence checks for every resource |
| Deployment code lives in the git-ignored skill folder, not in the repo, until the author publishes the skills | Author | The author wants the deploy run as Claude skills; reviewers won't see it until then |
| **Demo server is off when unused:** `server.sh stop` backs up then stops; `server.sh start` turns it on and it backs up and stops itself after 4 hours | Author | Cuts the cost to about $6/month while idle; the Elastic IP keeps the address, so DNS never changes |
| **$10 monthly AWS budget alert** (email at 80% actual and 100% forecast) | Author | Early warning if a server is left running; it is an alert, not a cap |
| No credential ever leaves the author's machine: AWS keys only in a named profile, secrets only through pipes, author-only scripts refuse captured output, Claude never reads `.env` or secret values | Author | The author asked that no credential gets out |
| Public address **acme.docrelay.io** (author's GoDaddy domain); the script sets the `acme` A record to the Elastic IP through the GoDaddy API, token in the git-ignored `.env` | Author | No manual DNS step; the Elastic IP never changes, so the record is set once |
| Server is **`t4g.small` (Graviton, ARM)** instead of `t3.small` | Author | About 20% cheaper for the same size; the image builds natively on the author's Apple Silicon Mac and on GitHub's ARM runners |
| Secrets never in the repo, image or logs | Security baseline |
| Money stored as `NUMERIC(14,2)` and handled as Python `Decimal` end to end; sent as strings in JSON; never floats | Exact amounts; 14 digits leaves headroom for yearly salaries in any currency |
| Small commits, one per step; no AI attribution lines in commit messages; `.claude/skills/` git-ignored and not pushed until the author decides; `.claude/CLAUDE.md` (the AI working rules) committed | Reviewable history; the AI instructions are visible to reviewers |
| Word files (`*.docx`, including the assessment brief) are git-ignored and never pushed | The brief belongs to the hiring team; the repo is public |
| Demo video 3–5 minutes from a written script | |

## Implementation (backend and frontend, 14 Oct 2026)
| Decision | Why |
|---|---|
| **Services own the transaction**: each write service ends with one `commit()`; the request's session rolls back anything left over | One place where a change is saved; easy to see that a salary change, leave, create or import apply is all-or-nothing |
| **Idempotency key saved in the same transaction as the work**: the key row is added before the work runs and committed with it, then the response is stored on it. A retry of an unfinished request gets `409`, never a second change | No window where the work is saved but the key isn't (or the reverse) |
| Salary changes also send the employee's `version`; every salary change (even a future-dated one) gives a new version | A raise based on a stale screen is refused instead of silently stacking |
| Current salary = the latest entry in effect (ties: the newest entry); a backdated entry older than the current one only changes history; a daily task promotes future entries | One clear rule; same-day corrections replace the current amount |
| Salary start dates: not before the hire date and at most one year ahead | Catches typos without blocking planned raises |
| Marking someone as left takes effect immediately, whatever leaving date is entered | Simple; the date is recorded for history |
| Emails are stored lower-cased with a plain unique index (instead of an index on `lower(email)`) | Same effect, works the same on SQLite and Postgres |
| "Unusual" = outside 1.5 × IQR of the same role, level, country and currency, full-time equivalent; groups under 4 people are never flagged; the employee page shows the peer band from 2 people | Standard, explainable rule; tiny groups give noise |
| Filter counts leave out the filter's own selection (choosing India still shows how many are in the US) | Users see what each option would add |
| Import: blank optional cells (city, gender) leave stored values alone; departments must already exist; a changed salary without a date starts today (new people: the hire date); people who left can't get salary changes by import; the row limit is checked by the worker, not during upload | Safe defaults; nothing is cleared or created by accident |
| An import waiting for review also blocks a new one (cancel it first) | "One import at a time" with no half-reviewed jobs left behind |
| The CSV export uses the import's column names, so an exported file can be edited and imported back | Excel stays a two-way exit path |
| Export is built in memory instead of streamed | 10,000 rows are ~2 MB and take 0.16 s; streaming with a request-scoped database session is fragile |
| Local file downloads go through signed links to the app (15 minutes); S3 signed links replace them with the AWS deployment | Same short-lived-link behaviour in development and production |
| Sessions use Starlette's signed-cookie `SessionMiddleware` | No session table; the app stays stateless |
| The worker fetches exchange rates after 16:00 UTC, once a day | The ECB publishes around 16:00 CET |
| Tests hash passwords with bcrypt cost 4 (the app uses the default, 12) | The full backend suite runs in ~4 s |
| Frontend: shadcn/ui components written into `src/components/ui` by hand, `oxlint` for linting, newest package majors (React 19, React Router 8, TanStack Table 9, Vite 8) | No interactive CLI step; fast lint; current APIs |
