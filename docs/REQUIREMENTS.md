# ACME Pay: requirements (v1)

**Goal.** Replace the Excel files ACME's HR team uses for 10,000 employees in 6 countries with a web app where HR can keep salary data accurate and answer "how do we pay people?" in seconds.
**Persona.** HR Manager: expert in pay, not technical; today filters and pivots spreadsheets by hand. **Users:** the HR team, as HR Admin (can change data) or HR Viewer (read-only).

## In scope
| Feature | Why |
|---|---|
| **Sign-in with two roles** (HR Admin, HR Viewer); signed-in user shown, sign out | Salary data is sensitive; some people report on pay but must not change it |
| **Home**: 3 key numbers, "needs your attention", recent changes | A calm start that points to what needs action |
| **People directory**: search, left filter panel with counts, chips, sort, pagination, CSV export | Finding a person is the most frequent task; fast at 10,000 rows |
| **Employee page**: salary (local + USD), position vs. peers, history, photo, documents, details | Answers "what does X earn, and is it fair compared with peers?" |
| **Add, edit, mark as left** (never deleted); optional gender field | Pay history must survive people leaving |
| **Salary changes** as dated entries (future or past) with a reason; who and when recorded; never edited (corrections are new entries) | Spreadsheets overwrite history; HR is asked "when, why and by whom?" |
| **Photos and documents** (PDF/JPG/PNG ≤ 10 MB, private storage; Admins upload) | Keeps employee files with the record instead of shared drives |
| **Insights**: by country/department, by role (with spread), unusual salaries | Leadership's pay questions without pivot tables |
| **Live exchange rates**: daily ECB rates stored by date; reports say which date | Fair cross-country comparison in USD |
| **Excel/CSV import**: template → check → review → apply as a background job; whole file rejected by default (or save correct rows only); failed rows downloadable; one import at a time; ≤ 20,000 rows / 10 MB; missing people never changed | HR lives in Excel; a safe import is how they move off it |
| **Seed script**: 10,000 deterministic employees | Required; also the test and demo dataset |

## Deliberately left out
Company SSO (password login + roles is enough; SSO fits the same seam later) · country-limited access · employee self-service · payroll, tax, payslips and arrears calculation · bonuses, allowances and stock · pay bands and pay-fairness reports (gender is stored but not analysed) · approval workflows · scheduled email reports · manager/reporting lines · HR-system connectors and push API (this app is the source of truth; the import pipeline is designed to accept them) · accessibility testing (the UI library's built-in basics only) · Load balancers, autoscaling, Redis, queues, microservices · alerting and tracing · dark mode and mobile polish.
*Why:* each either belongs to another product (payroll, self-service), needs data or decisions we don't have (bands, equity, SSO provider), or adds moving parts that 10,000 employees and a small HR team don't need.

## Assumptions and targets (no fixed requirements were given; chosen and documented)
- **Load:** no limit on logins; targets assume ~5 people working at once; busiest at the April salary review and month-end. Designed and tested for 10,000 employees.
- **Speed (95 of 100 requests, server-side):** list ≤ 200 ms · employee page ≤ 150 ms · save ≤ 300 ms · Insights ≤ 500 ms (≤ 50 ms cached) · export of 10,000 ≤ 3 s · import of 10,000 rows: check ≤ 15 s, apply ≤ 30 s · seed ≤ 10 s.
- **Built-in protection:** indexes, pagination, caching cleared on every change, per-user rate limits, money as exact decimals.
- **Hosting:** one AWS EC2 server in Mumbai (closest region to India, the largest employee group) running Docker Compose: HTTPS proxy, web app, background worker and Postgres; files in S3; logs in CloudWatch. Always on. Nightly database backups to S3 (14 days) and weekly disk snapshots; restore within ~2 hours. One server handles 10,000 (and 50,000) employees; the scaling path is documented, not built. Data protection laws are out of scope.
- **Monitoring:** structured logs (CloudWatch on AWS) and clear error messages.

**Success:** HR finds anyone in < 5 s, records a raise in < 30 s, and answers the key pay questions without leaving the app.
