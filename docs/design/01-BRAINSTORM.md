# 01 · Brainstorm: features, journeys and key decisions

> Status: **brainstorm (historical)**. Final decisions are in [../DECISIONS.md](../DECISIONS.md); where they differ (employee page instead of side panel, two roles, photos and documents, live rates), the decisions log wins. Items marked ❓ need a decision from us or the PM (see [02-PM-QUESTIONS.md](02-PM-QUESTIONS.md)).

## 1. Who we are building for
**Priya, HR Manager at ACME** (persona name is illustrative).
- Owns compensation data for ~10,000 people in ~10 countries.
- Today: one Excel file per country, emailed around, VLOOKUPs to combine them, pivot tables for every leadership question.
- Pain points: slow to find a person, no history ("what was his salary last year?"), copies get out of sync, cross-country comparisons need manual currency conversion, one bad paste can corrupt the sheet.

## 2. Jobs to be done
| When… | Priya wants to… | So that… |
|-------|-----------------|----------|
| A manager asks about someone | find the person and see their pay + history in seconds | she can answer on the spot |
| A raise or promotion is approved | record the new salary with an effective date and reason | history stays accurate and auditable |
| Someone joins or leaves | add or terminate them | headcount and payroll are right |
| The annual cycle happens or data comes from finance | upload many changes at once from Excel/CSV | she doesn't retype hundreds of rows |
| Leadership asks "how do we pay people?" | see pay by country, department and role, plus outliers | she can answer without building pivot tables |
| Finance needs a file | export exactly what she's looking at | Excel stays an exit path, not the system of record |

## 3. Core user journeys
1. **Look up a person**: press `/` → type a name → pick from results → a side panel opens with profile, current pay, history and "compared with peers". The list keeps its place behind it.
2. **Record a raise**: from the side panel, "Change salary" → new amount (shows % change live) → effective date → reason → save. The history updates and insights refresh.
3. **Bulk update**: Imports → download template → upload filled .xlsx/.csv → the system validates and shows a **preview** (42 new, 1,204 updates, 3 errors with row numbers) → fix or skip errors → confirm → progress bar → summary + downloadable error report.
4. **Answer a pay question**: Insights → pick a country → see the median by role, the spread, and outliers → click a bar to jump into the filtered directory.
5. **Export**: filter the directory → "Export" → CSV of exactly that view.

## 4. Feature list (MoSCoW)
### Must (v1)
- **Directory**: server-side pagination, search, filters (country, department, job title, level, status, employment type), sort by any column including salary in USD. Filters live in the URL (shareable, back button works).
- **Employee profile** side panel: personal + job info, current salary (local + USD), salary history timeline.
- **Create / edit / terminate** an employee (soft delete; history kept). Rehire = reactivate.
- **Salary change** as an effective-dated record with a reason (hire, promotion, merit, market adjustment, correction).
- **Insights dashboard**: headcount, total annual payroll (USD), median salary; breakdown by country and department; role-within-country table (min / p25 / median / p75 / max); distribution histogram; outliers (outside 1.5× IQR for their role and country).
- **Bulk import** (CSV + XLSX) with template, validate → preview → commit as a background job, and an error report. *(Promoted from v2: it's the actual Excel-replacement moment. See §6.)*
- **CSV export** of the current filtered view.
- **Seed**: 10,000 deterministic employees.
- Performance basics: indexes, pagination, caching, rate limiting.

### Should (v1 if time allows, designed for now)
- **Employee photo** upload (avatars from initials by default). See §7.
- **Compa-ratio** per employee: salary ÷ median of peers (same role + country), shown as a small "below / at / above peers" indicator.
- **Import history** list with re-downloadable error reports.
- **Activity log**: who changed what (needs auth to be meaningful, so it's partial in v1).

### Could (later)
- Pay bands per role/level/country, and "out of band" flags.
- Pay-equity analysis (needs gender data; sensitive ❓).
- Scheduled future raises and budget modelling ("what if everyone in India gets +8%?").
- HRIS sync (Workday/BambooHR) instead of file uploads.

### Won't (v1), on purpose
- Authentication/RBAC (single persona, synthetic data; it is the first production add-on).
- Payroll processing, tax, payslips, bonus/equity.
- Live FX rates (non-reproducible reports).
- Microservices, Redis or queues on day one (see backend design for the upgrade path).

## 5. How we fetch and show HR data
| View | Fetch pattern | Why |
|------|---------------|-----|
| Directory | `GET /employees?page&page_size&filters&sort`, 20 rows/page, returns `total` | Never ship 10k rows to the browser |
| Search box | debounced 300 ms, same endpoint with `q` | No request per keystroke |
| Filter dropdowns | `GET /meta` once, cached client + server side | Small, changes rarely |
| Profile panel | `GET /employees/{id}` + `/salaries` in parallel; prefetch on row hover | Feels instant |
| Insights | one endpoint per widget, cached server-side and invalidated on writes | Each card loads independently; one slow query doesn't block the page |
| Import progress | poll `GET /imports/{id}` every 1 s while running | Simpler than WebSockets, enough for one user |

**Showing money honestly:** within a country → local currency (`₹18,40,000`); across countries → USD with a small "≈ USD at fixed rates (as of 2026-01-01)" note. Totals and medians are never mixed across currencies.

## 6. Bulk upload: the decision
**Recommendation: yes, in v1**, because "Excel → web app" is the whole point of the brief.

Flow: **Upload → Validate → Preview → Commit → Report**
- Formats: `.xlsx` (what HR actually has) and `.csv`. Max 10 MB / 20,000 rows.
- **Matching key**: `employee_code`. Exists → update; doesn't → create. Employees *missing* from the file are **not** touched (no surprise terminations).
- A salary change in the file creates a new salary record (with `effective_date`, defaulting to today) instead of overwriting.
- **Validation is all-or-nothing by default**: if any row has errors, nothing is written until HR fixes the file or chooses "Import valid rows only". Partial imports are a classic source of silent data drift.
- **Long-running work**: the upload returns immediately with a job id; parsing, validation and commit run in a background worker; the UI polls progress. See [04-BACKEND.md §5](04-BACKEND.md).
- Re-uploading the same file is detected (SHA-256) and warned about.
- The error report is a downloadable CSV: original row + error column, so HR fixes it in Excel and re-uploads.

## 7. Employee photos: the decision
- **Default: generated initials avatar** (zero storage, no PII, works for all 10k seeded people).
- Optional upload: JPEG/PNG/WebP, ≤ 2 MB → server re-encodes to a 256×256 WebP (**strips EXIF/GPS metadata**, normalizes size) → stored in **object storage** (S3-compatible: Cloudflare R2 / S3 in production, local folder in dev) → the DB stores only the key.
- **Never store images in the database** (bloats backups, slows queries).
- Photos are personal data: ❓ consent and need (do HR managers actually need faces to manage pay?). If the PM says no, we drop upload and keep initials.

## 8. What employee information we store (data minimization)
Store only what salary management needs. See [03-DATABASE.md](03-DATABASE.md) for the full schema.
- **Identity**: employee code, first/last name, work email, photo (optional).
- **Job**: job title, level, department, manager, country, city, employment type (full-time / part-time / contractor), FTE %, hire date, status.
- **Pay**: annual base salary, currency, effective date, reason, note.
- **Not stored** on purpose: national ID, bank details, home address, date of birth, gender ❓ (needed only for pay-equity analysis), tax data. Less sensitive data = less risk and fewer compliance obligations.

## 9. Risks and how the design handles them
| Risk | Mitigation |
|------|------------|
| Bad bulk upload corrupts data | Validate → preview → explicit confirm; all-or-nothing; every change is a new salary record (reversible) |
| Two HR users edit the same person | Optimistic locking (`version` column → 409 "this record changed, reload") |
| Misleading cross-country numbers | USD normalization with a fixed, dated FX table, labelled in the UI |
| Stale dashboard after an edit | Cache keyed by a data version that every write bumps |
| CSV export opened in Excel runs a formula | Escape cells that start with `= + - @` (CSV injection) |
| Abuse / accidental hammering | Rate limits per client, stricter on import and export |
