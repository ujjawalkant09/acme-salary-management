# As-user oracles

Checks that drive the **running app in a real browser** (Playwright, Chromium), the way the HR team uses it, and read what a person sees. The pytest and Vitest suites test pieces in isolation. These oracles catch what only shows up end to end: a form that sends the wrong thing, a retry that saves twice, a button shown to the wrong role.

Each file in `features/` is one oracle with numbered scenarios. Next to it is a `.md` with the scenario table and a click path, so a person can repeat every scenario by hand.

| Oracle | Scenarios |
|---|---|
| [login](features/login.md) | admin signs in · wrong password · the viewer can't change anything · sign out |
| [people](features/people.md) | list and paging · search by code · empty state and Clear · open a person and come back |
| [salary](features/salary.md) | change a salary · lost answer + Save again saves once (idempotency) · two admins at once (409) · invalid amounts |

## Results
- **GREEN**: every check passed. **RED**: a check failed or the scenario crashed. **SKIP**: the environment lacks something (an employee, or permission to change data). A SKIP is never counted as GREEN.
- Every check prints as `PASS` or `FAIL` with the value it saw. Each scenario saves a screenshot (`evidence:`), in `e2e/screenshots/` by default.
- Exit code: `0` no RED · `1` a RED · `2` an unknown scenario id · `3` a demo password is missing · `4` the app is down or is not built from this checkout.

Before any scenario runs, two gates stop a RED the app isn't to blame for:
- **App gate.** `/api/v1/health` must answer. When the image was built with a commit (`GIT_COMMIT`, set by CI and `deploy.sh`), it must match this checkout's `HEAD`. Run from source, there is no commit to compare.
- **Login gate.** Both demo passwords must be known: `DEMO_ADMIN_PASSWORD` / `DEMO_VIEWER_PASSWORD` from the environment, otherwise from `backend/.env` (with quotes stripped).

## Run them
The quickest way is the Claude skill [`as-user-oracles`](../.claude/skills/as-user-oracles/SKILL.md). Its `scripts/app.sh start` starts a throwaway app (its own database, secrets and passwords), `app.sh run` runs every oracle on it, and `app.sh probe <page>` shows what's on a page while you write a scenario. It works without Claude too. The manual steps follow.

One-time setup:
```bash
cd e2e
uv sync
uv run playwright install chromium
```

**Against a throwaway app** (needed for the salary scenarios, which change data). Secrets and passwords come from `backend/.env`:
```bash
cd frontend && npm run build && cd ../backend
docker compose exec -T db psql -U acme -d postgres -c 'DROP DATABASE IF EXISTS acme_oracles WITH (FORCE)' -c 'CREATE DATABASE acme_oracles'
export DATABASE_URL=postgresql+psycopg://acme:acme@localhost:5432/acme_oracles STORAGE_DIR=/tmp/acme-oracles-files RATE_LIMIT_ENABLED=false
uv run alembic upgrade head && uv run python -m scripts.seed --count 1000 --reset
uv run uvicorn app.main:app --port 8100
```
Then, in another terminal:
```bash
cd e2e
ORACLE_BASE_URL=http://localhost:8100 ORACLE_ALLOW_WRITES=1 uv run python oracle_kit.py all
```

**Other runs:**
```bash
uv run python oracle_kit.py login                  # one oracle, against http://localhost:8000
uv run python oracle_kit.py people S2 S4           # some scenarios
uv run python oracle_kit.py salary S1-S3           # a range
ORACLE_HEADED=1 uv run python oracle_kit.py login S1    # watch it in a window
```
Without `ORACLE_ALLOW_WRITES=1`, the scenarios that change data SKIP, so a read-only run is safe against your everyday database or the AWS demo.

| Variable | What it changes |
|---|---|
| `ORACLE_BASE_URL` | The app to test. Default `http://localhost:8000`. The Vite dev server (`:5173`) works too. |
| `ORACLE_ALLOW_WRITES` | `1` runs the scenarios that change data. Only on a throwaway database. |
| `ORACLE_HEADED` | `1` shows the browser window. |
| `ORACLE_SHOT_DIR` | The screenshot folder. Default `e2e/screenshots/`. |
| `DEMO_ADMIN_PASSWORD`, `DEMO_VIEWER_PASSWORD` | The demo passwords, when they are not in `backend/.env`. |

The app allows 5 sign-ins a minute. One full run signs in 4 times: each role signs in once and later scenarios reuse its cookie. Run against an app with `RATE_LIMIT_ENABLED=false`, or wait a minute between runs.

## Rules for writing scenarios
1. **Only use a selector you saw work on the live page.** Prefer what a person sees: roles, labels and text (`get_by_role`, `get_by_label`). Add a `data-testid` to the app only where those are fragile, like `current-salary`.
2. **SKIP is not GREEN.** Return `Outcome.skip(reason)` only when the environment lacks something. Never pass a check that didn't run.
3. **Before calling a RED a bug, rule out the test:** the selector, the login, the URL.
4. **Wait for a settled page, never a fixed time:** `wait_for()` on rows, an empty state or a message, or `eventually(...)` for a value that is still refreshing.
5. **Put the real value in every check message,** so a RED says what was there.
6. **Scenarios that change data** start with `ctx.writes_refused()` and use their own employee, so they never get in each other's way.
7. **When you check a journey by hand that has no scenario yet, add one,** with its row and click path in the feature's `.md`.

To add an oracle, create `features/<name>.py` with `ORACLE = Oracle("<name>")` and `@ORACLE.scenario("S1", "what a person sees")` functions that return `Checks`, plus `features/<name>.md`. The runner finds it by file name.

## How we know they work
The harness has its own unit tests (`uv run pytest`, no browser needed). The oracles were also checked by breaking the app on purpose:
- A frontend that sends a new `Idempotency-Key` on every click turned salary S2 RED: the retry was answered 409, and the two keys differed.
- A backend with the version check removed turned salary S3 RED: the stale save was answered 201, and it overwrote the first change.
