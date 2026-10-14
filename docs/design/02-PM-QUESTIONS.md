# Questions for the Product Manager

> **Status (14 Oct 2026):** sent to the hiring team, together with 11 performance questions (peak users, busy periods, future scale, speed targets, import time and concurrency, recovery time, demo wake-up time, alerting, tracing).
> **Reply (Sandli):** make reasonable assumptions from the HR Manager persona and document them; design for 10,000 employees (50,000+ not required); no fixed speed targets, define and explain our own; import/export are optional, document limits if included; no fixed recovery or wake-up requirement; basic logging and error handling are enough; capture every decision, especially what is left out and why, in the one-page requirements.
> **Outcome:** the author answered all questions in the decision book; the final answers are in [../DECISIONS.md](../DECISIONS.md) and summarised in [../REQUIREMENTS.md](../REQUIREMENTS.md). Where an answer below differs from "our guess", the decisions log wins.


The 20 questions we are sending to the PM. Under each one: **why we ask**, and **our guess for now**, which is what we build if we don't get an answer.

Questions we answered ourselves are in [../DECISIONS.md](../DECISIONS.md).

## Users and access

**1. Will only the HR Manager use this app, or the whole HR team? If it's the whole team, do we need different roles and permissions, for example who can view salaries and who can edit them?**
- Why: roles affect every screen and every action.
- Our guess: a few HR users with full access; the design leaves room for roles.

**2. How should users log in: with their company Google or Microsoft account, or with an email and password?**
- Our guess: one shared demo login for now; company login (SSO) in production.

**3. Will employees also log in to see their own salary details, or is the app only for HR?**
- Why: this is the biggest scope question. It means 10,000 logins, strict "see only your own data" rules and a separate "my salary" page.
- Our guess: HR only.

**4. Do we need to record who changed what, and when (an audit history)?**
- Our guess: we record what changed and when; "who" comes once there are real user logins.

## Employee information

**5. Does every employee have one unique ID across all countries?**
- Why: bulk upload uses this ID to find the right person.
- Our guess: yes, an employee code like `ACM-004521`.

**6. Do we need to store each employee's manager?**
- Our guess: optional field; not used in reports yet.

**7. Do we need to store employee photos or any employee documents, such as offer letters or contracts?**
- Why: documents are sensitive files that need secure storage and strict access rules.
- Our guess: no documents; initials instead of photos.

**8. How long should we keep an employee's data after they leave the company?**
- Our guess: kept, marked as "left".

## Salary

**9. Is salary always a yearly amount, or are some people paid hourly or monthly? Will we also have contract workers?**
- Why: mixing yearly and monthly numbers makes every report wrong.
- Our guess: everything stored as a yearly amount; contractors marked with an employment type.

**10. Is everyone paid in their own country's currency?**
- Our guess: each salary stores its own currency, defaulting to the country's currency.

**11. Should we also track bonuses, allowances or stock options, or only base salary?**
- Our guess: base salary only.

**12. Can a salary change start on a future date, or on a past date (which would create arrears)? If arrears apply, should the app calculate the arrears amount, or only record the new salary from that date?**
- Why: calculating arrears is payroll work, which is out of scope.
- Our guess: both dates allowed; we only record the new salary, we don't calculate arrears.

## Bulk data upload

**13. How will bulk employee data come in: an Excel upload, pulled from another HR tool, or pushed by another system to our API?**
- Our guess: Excel/CSV upload first; the import is built so a connector or a push API can be added later. See design/04-BACKEND.md §5b.

**14. Is uploading a one-time move off Excel, or will HR do it regularly, for example every month or during the yearly salary review?**
- Our guess: regular, so it gets a safe preview-before-saving screen.

**15. If a file has some incorrect rows, should we save the correct rows and skip the rest, or reject the whole file?**
- Our guess: reject by default; HR can choose "save only the correct rows".

**16. Will HR upload one file for all countries, or a separate file for each country?**
- Our guess: either works; country is a column in the file.

**17. For Excel uploads, what is the largest file we should expect (number of rows or file size)?**
- Our guess: up to 20,000 rows or 10 MB.

## Reports

**18. Should the app send regular reports (for example weekly or monthly) about salary costs and distribution to stakeholders such as leadership or finance? If yes, who should receive them, and how often?**
- Our guess: no automatic emails; reports on screen plus CSV export.

## Compliance and reliability

**19. In which countries do our employees work? If any are in Europe, does our legal team require their data to be stored in a European region because of GDPR?**
- Outcome: not required by the brief; data protection laws are out of scope. Employees are in 6 countries outside Europe, and the app is hosted in Mumbai (ap-south-1; see DECISIONS.md).

**20. How reliable does the app need to be (for example, available during working hours or 24/7), and how often should we back up the data?**
- Our guess: working hours; daily automatic database backups.
