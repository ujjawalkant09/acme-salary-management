# ACME Salary Management

Web app for an HR Manager to manage and analyze salaries for 10,000 employees across countries.

- Requirements: [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)
- Architecture and plan: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Design pack: [brainstorm](docs/design/01-BRAINSTORM.md), [PM questions](docs/design/02-PM-QUESTIONS.md), [database](docs/design/03-DATABASE.md), [backend](docs/design/04-BACKEND.md), [UI](docs/design/05-UI.md), [deployment and secrets](docs/design/06-DEPLOYMENT.md), [clickable prototype](docs/design/prototype.html)
- Decisions log: [docs/DECISIONS.md](docs/DECISIONS.md)
- AI usage log: [docs/AI_USAGE.md](docs/AI_USAGE.md)

## Run it locally
Needs Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 26 with npm, and Docker. The app and the tests run on PostgreSQL, as in production: `docker compose up -d --wait db` starts it locally (`dev.sh` does this for you).

**One command:** `./dev.sh` starts Postgres, installs, migrates, seeds an empty database and starts the API, the worker and the frontend together (Ctrl+C stops those three; `docker compose stop db` stops the database). `./dev.sh --fast` skips the setup and just starts them. The steps it runs are below.

**Backend** (API on http://localhost:8000, docs at `/api/v1/docs`)
```bash
docker compose up -d --wait db   # Postgres on localhost:5432 (data kept in a Docker volume)
cd backend
uv sync
cp .env.example .env              # then set SECRET_KEY and the two demo passwords
uv run alembic upgrade head       # create the database
uv run python -m scripts.seed     # 10,000 employees + the two demo logins (--reset to start over)
uv run uvicorn app.main:app --reload --port 8000
uv run python -m app.worker       # second terminal: imports and daily exchange rates
```

**Frontend** (http://localhost:5173, proxies `/api` to the backend)
```bash
cd frontend
npm install
npm run dev
```
`npm run build` writes `frontend/dist`; the backend then serves the UI itself on http://localhost:8000.

**Demo logins** (created by the seed): `priya.sharma@acme.example` (HR Admin) and `arjun.mehta@acme.example` (HR Viewer), with the passwords you set in `backend/.env`.

## Deploy to AWS
One command builds the image and deploys everything (one EC2 server, Postgres, HTTPS) to https://acme.docrelay.in. The demo server is off when unused to save money; while it is off, anyone with the wake link can start it at https://wake.acme.docrelay.in (about 2–3 minutes). Setup, commands and costs: [.claude/skills/aws-deploy/SKILL.md](.claude/skills/aws-deploy/SKILL.md).
From GitHub: **Actions > Deploy > Run workflow** runs every check and releases `main` (it turns the server on if it is off).
```bash
.claude/skills/aws-deploy/scripts/deploy.sh          # create or update everything, release the current commit
.claude/skills/aws-deploy/scripts/server.sh start    # turn the demo on (stops itself after 4 hours)
.claude/skills/aws-deploy/scripts/server.sh stop     # back up, then turn it off
.claude/skills/aws-deploy/scripts/logins.sh          # (your own terminal) demo passwords and the wake link
```

## Checks
The backend tests need the local Postgres running; each test gets its own fresh database (`acme_test`, cloned from a migrated template), so your `acme` data is never touched.
```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest --cov
cd frontend && npm run lint && npm run typecheck && npm run coverage && npm run build
```
Both test runs print a coverage report and fail if coverage drops below the floor (backend 98%, set in `pyproject.toml`; frontend in `vite.config.ts`). Plain `uv run pytest` / `npm test` run the tests without it.
CI (`.github/workflows/ci.yml`) runs these on every push, plus the deploy-script tests, a secret scan and the production image against Postgres.

**As-user oracles** (`e2e/`): real-browser checks of the running app (sign-in, People, salary changes including a retried save and two admins at once), each scenario GREEN, RED or SKIP. CI runs them against the production image. To run them locally, see [e2e/README.md](e2e/README.md):
```bash
cd e2e && uv sync && uv run playwright install chromium
uv run python oracle_kit.py all     # against http://localhost:8000; data-changing scenarios SKIP
```
