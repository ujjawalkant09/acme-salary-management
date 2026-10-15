---
name: as-user-oracles
description: Run the as-user oracles (real-browser checks in e2e/) against ACME Pay and read their GREEN / RED / SKIP results, or write a new oracle scenario for a feature. Use when the user asks to run the oracles, the e2e or browser tests, to check a feature "as a user" / end to end, to add, create or extend an oracle or scenario, or to cover a journey they just checked by hand.
---

# as-user-oracles

The oracles live in `e2e/` (harness: `e2e/oracle_kit.py`, one oracle per file in `e2e/features/`, a click path per oracle in `e2e/features/<name>.md`). Read `e2e/README.md` once for the details. This skill gives the two workflows and a throwaway app to run them on.

| Ask | Command (from the repo root) |
|---|---|
| Start a throwaway app (new database, port 8100) | `.claude/skills/as-user-oracles/scripts/app.sh start` |
| Run every oracle on it | `.claude/skills/as-user-oracles/scripts/app.sh run` |
| Run one oracle / some scenarios | `.claude/skills/as-user-oracles/scripts/app.sh run salary S2 S3` |
| See what a person sees on a page | `.claude/skills/as-user-oracles/scripts/app.sh probe /people/10 --as viewer` |
| Stop it | `.claude/skills/as-user-oracles/scripts/app.sh stop` |
| Read-only run on the dev server (:8000) | `cd e2e && uv run python oracle_kit.py all` |

The throwaway app has its own database, files, secret and random demo passwords (in `$TMPDIR/acme-oracles-8100/`), and no rate limit. It never touches `backend/acme.db` or `backend/.env`, so it works in a worktree too. `app.sh run` allows the scenarios that change data (`ORACLE_ALLOW_WRITES=1`). **Never set that flag against the dev server or the AWS demo.**

Rules for credentials: never `cat`, `grep` or print `backend/.env`. The runner reads the passwords itself. Never print the throwaway app's `oracle.env` either.

## Workflow 1: run the oracles
1. **Pick the target.**
   - To check code you just changed, use the throwaway app: `app.sh start`, then `app.sh run`. Run `start` again after changing backend or frontend code, since it rebuilds the UI and restarts.
   - To check the dev server without changing data, run `cd e2e && uv run python oracle_kit.py all`. The salary S1–S3 scenarios SKIP.
   - To check the AWS demo read-only, set `ORACLE_BASE_URL=https://acme.docrelay.in` and the demo passwords, which come from the author (only the author runs `logins.sh`).
2. **Read the gates first.**
   - Exit `4 DOWN`: start the app.
   - Exit `4 FOREIGN`: the app was built from another commit. Rebuild it, or test the right checkout.
   - Exit `3`: a password is missing.
   - Exit `2`: a scenario id doesn't exist.
   None of these is a product bug.
3. **Read each scenario.** Every check prints `PASS` or `FAIL` with the value it saw, plus a screenshot path (`evidence:`). Open the screenshot of any RED.
4. **Triage a RED: rule out the test before blaming the app.**
   - Did the selector match something? Run `app.sh probe <page>` and compare with the oracle's selectors.
   - Was it the login, a missing employee, or a rate limit (429 "You're going a bit fast")? Use the throwaway app or wait a minute.
   - A timeout `EXCEPTION` usually means the page never reached the state the scenario waited for. The screenshot shows what was there instead.
   - Only then report it as a product bug, with the FAIL line and the screenshot.
5. **Report the summary line as is** (`9/11 green, 2 skipped`). A SKIP is not a pass, so say why each one skipped.
6. Finish with `app.sh stop`.

## Workflow 2: create an oracle scenario
1. **Pick one behaviour a person can see**, and name it the way a person would say it: "a viewer can't change a salary", "a search that matches no one says so". If the feature has no oracle yet, create `e2e/features/<name>.py` with `ORACLE = Oracle("<name>")` and a matching `<name>.md` (copy the shape of `people.py` and `people.md`).
2. **Look at the live page before writing a selector.** Run `app.sh start`, then `app.sh probe <path> [--as viewer|none] [--click "Name"]…`. `--click` presses a button, menu item, tab, option or link, in that order, and can be repeated (for example `--click "PS Priya Sharma HR Admin" --click "Sign out"`). Use only names you saw in the probe output.
   - Prefer, in this order: `get_by_role(name=…)`, `get_by_label(…)`, visible text, then a `data-testid`.
   - Add a `data-testid` to the frontend only where text is ambiguous or changes, as `current-salary` does. The frontend tests must still pass.
   - Inside an open dialog, Radix hides the rest of the page from role queries. Find background content with CSS or text (see `salary_history` in `oracle_kit.py`).
3. **Write the scenario** next to the others in its file:
   ```python
   @ORACLE.scenario("S5", "what a person sees, in their words")
   def short_name(page, ctx):
       stop = ctx.writes_refused()  # only if the scenario changes data
       if stop:
           return stop
       ctx.sign_in(page, "admin")  # or "viewer"; a cookie is reused after the first sign-in
       if not open_employee(page, ctx, "ACM-000105"):
           return Outcome.skip("employee ACM-000105 is not in this database")
       ck = Checks()
       ...  # act like a person: click, fill, choose
       ck.that(value == expected, f"<what> is {value!r}, expected {expected!r}")
       ck.note(ctx.shot(page, "<feature>-S5"))
       return ck
   ```
   - Take the next free id, and never reuse one: the harness refuses duplicates.
   - Wait for a settled page, never a fixed sleep. Use `locator.wait_for()` on rows, an empty state or a message, `eventually(read, expected)` for values that refresh, and `page.expect_response(...)` when the HTTP status is the point.
   - Put the real value in every message, so a RED explains itself.
   - Return `Outcome.skip(reason)` only when the environment lacks something.
   - A scenario that changes data starts with `ctx.writes_refused()` and uses **its own seeded employee**. Check `salary.md` for codes already taken; ACM-000105 and up are free. Seeded codes ACM-000001 to ACM-001000 exist in every seeded database.
   - Use the helpers in `oracle_kit.py` (`open_employee`, `salary_history`, `eventually`, `submit_login`) before writing new ones. Move a helper into `oracle_kit.py` only once 2–3 oracles need it.
4. **Write the click path**: add a row to the table in `<feature>.md` (id, scenario, employee, whether it changes data) and the steps a person follows by hand.
5. **Run it until GREEN**: `app.sh run <feature> S5`, then run the whole oracle (and `all` before finishing) to make sure nothing else broke.
6. **Prove it can fail.** Break the behaviour on purpose (one line in the frontend or a service), `app.sh start`, and run the scenario: it must go RED with a FAIL line that names the break. Then revert, confirm `git diff` is clean, run `app.sh start` again, and confirm GREEN. A scenario that can't go RED doesn't test anything.
7. **Run the checks**: `cd e2e && uv run ruff check . && uv run ruff format --check . && uv run pytest`. These load every feature file, so a duplicate id or a broken import fails here. If you added a test id, also run the frontend lint, type-check and tests.
8. **Report** the new scenario, its GREEN run, and the mutation that turned it RED.
