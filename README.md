# Hockey Analytics

An NHL analytics app for exploring player performance, contracts, teams, and
estimated salary-cap value. Data comes from the NHL, MoneyPuck, CapWages,
CapSpace, and AHL HockeyTech/LeagueStat feeds.

The stack is React 19, TypeScript, Vite, FastAPI, PostgreSQL, and Python ML tools.
Use Python 3.12, uv 0.13.1, and Node.js 24.

## Start the frontend

The frontend uses mock data by default and can run without the API or database.

```bash
cd frontend
npm ci
npm run dev
```

To use a running API, create `frontend/.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK_API=false
```

Restart the dev server after changing these settings. Hosted builds need a
redeployment. See the [API guide](backend/README.md#frontend-connection) for CORS.

## Start the API

From the repository root:

```bash
uv sync --locked --all-groups
cp backend/.env.example backend/.env
```

Edit `backend/.env` with your local PostgreSQL credentials, then run:

```bash
uv run python -m alembic -c backend/alembic.ini upgrade head
uv run uvicorn app.main:create_runtime_app --factory --reload
```

The API serves at `http://localhost:8000`, interactive docs at `/docs`, and a
database health check at `/api/health`. It never applies migrations on startup.
See the [database guide](backend/database/README.md) for migration rules.

## Load data and run checks

After applying migrations, run ingestion from the repository root:

```bash
uv run python -m app.ScriptingFiles.FullDataScript.run_all
```

The pipeline loads statistics, rosters, contracts, and schedules. See the
[ingestion guide](backend/src/app/ScriptingFiles/FullDataScript/README.md) for
individual commands, validation, and historical contract recovery.

Python checks:

```bash
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
```

The full Python suite needs a disposable PostgreSQL database. Follow the
[verification guide](docs/python-verification.md) for database setup, isolated
unit tests, coverage gates, and package checks.

Frontend checks, from `frontend/`:

```bash
npm run lint
npm run test:coverage
npm run build
```

Frontend runtime coverage must remain at 100%. CI publishes coverage reports.

## Change dependencies or the API contract

Python dependencies live in the workspace `pyproject.toml` files and `uv.lock`.
After editing dependencies, run from the repository root:

```bash
uv lock
bash scripts/export-requirements.sh
uv sync --locked --all-groups
```

Deployment requirements are generated; do not edit them directly. Keep the
workspace compatibility pins until an intentional dependency upgrade.

After changing API schemas, regenerate the committed contracts:

```bash
uv run python backend/export_openapi.py
cd frontend
npm run api:generate
```

## Logging and releases

Application logs are enabled in Dev and disabled for `ENV=nonprod` and
`ENV=prod`, including errors. The frontend reads `ENV` at build time; changing
it requires a rebuild. See [logging configuration and events](docs/logging-events.md).

Create feature branches from current `origin/Dev`; every feature PR targets `Dev`.
The promotion path is:

```text
Feature → Dev → selected Release-x.y.z or Hotfix-x.y.z → manual Prod merge
```

See the [release workflow](docs/ci-promotion.md) and
[Vercel/Neon deployment guide](docs/deployment-vercel-neon.md) for configuration,
migration approval, and deployment checks.

## Repository map

| Location | Purpose |
| --- | --- |
| `backend/src/app/` | API, ingestion, and shared Python code |
| `backend/database/`, `backend/migrations/` | Frozen initial schema, database tools, and migrations |
| `backend/data/` | Historical source CSVs |
| `frontend/src/` | React app and API client |
| `ml/src/ml/` | Features, training, and evaluation |
| `tests/backend/`, `tests/ml/` | Python tests |
| `.github/workflows/` | CI and release automation |

Further references: [API contract](docs/api-contract.md),
[Python commands](docs/python-commands.md), and [ML guide](ml/README.md).
Product plans are available on the app's Future Plans page.

This independent project is not affiliated with the NHL, AHL, MoneyPuck,
CapWages, or their organizations.
