# ACME Salary Management

Web app for an HR Manager to manage and analyze salaries for 10,000 employees across countries.

- Requirements: [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)
- Architecture and plan: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Design pack: [brainstorm](docs/design/01-BRAINSTORM.md), [PM questions](docs/design/02-PM-QUESTIONS.md), [database](docs/design/03-DATABASE.md), [backend](docs/design/04-BACKEND.md), [UI](docs/design/05-UI.md), [deployment and secrets](docs/design/06-DEPLOYMENT.md), [clickable prototype](docs/design/prototype.html)
- Decisions log: [docs/DECISIONS.md](docs/DECISIONS.md)
- AI usage log: [docs/AI_USAGE.md](docs/AI_USAGE.md)

## Run it locally
Needs Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node 26 with npm. Docker and Postgres come with the deployment step; locally the app runs on SQLite.

**Backend** (API on http://localhost:8000, docs at `/api/v1/docs`)
```bash
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

## Checks
```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npm run lint && npm run typecheck && npm test -- --run && npm run build
```
