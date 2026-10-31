# Hockey Analytics

An NHL analytics project for collecting player and contract data, modeling player value, and translating performance into fair salary-cap value.

## Current Focus

The project is currently building the data foundation for future NHL analytics features, including:

* NHL player data
* Player statistics
* Contracts and cap hits
* NHL / AHL roster status
* LTIR tracking
* Salary-cap calculations
* Future player-value models

## Data Sources

Current and planned sources include:

* NHL
* MoneyPuck
* CapWages
* AHL HockeyTech / LeagueStat

The project prioritizes free or publicly available data sources.

## Tech Stack

* Python
* PostgreSQL
* pytest
* GitHub Actions
* React 19
* TypeScript
* Vite
* TypeScript
* React Router

## Project Structure

```text
Hockey-Analytics/
├── .github/
│   └── workflows/
├── backend/
│   ├── app/
│   ├── database/
│   └── tests/
├── frontend/
│   ├── src/api/
│   ├── components/
│   ├── mocks/
│   └── pages/
├── ml/
└── README.md
```

## Running the Frontend

The frontend currently uses realistic mock valuation data and does not require the backend or database.

```bash
cd frontend
npm install
npm run dev
```

Create a production build with `npm run build` and run lint with `npm run lint`.

## Running the API

The FastAPI backend implements the complete contract in
`docs/api-contract.md`. After configuring PostgreSQL and applying the schema:

```bash
uv sync --locked --all-groups
cd backend
uv run uvicorn app.main:create_runtime_app --factory --reload
```

The API listens on `http://localhost:8000`, serves interactive documentation at
`/docs`, and exposes a database-aware health check at `/api/health`. See
`backend/README.md` for frontend cutover, CORS, testing, and container commands.
For production, follow the complete
[Vercel and Neon deployment guide](docs/deployment-vercel-neon.md).

## Database

The frozen initial PostgreSQL schema and versioned migrations are located at:

```text
backend/database/schema.sql
backend/migrations/versions/
```

Install the development dependencies, copy the environment template, and enter your local
PostgreSQL credentials:

```bash
uv sync --locked --all-groups
cp backend/.env.example backend/.env
```

Run `uv run python -m alembic -c backend/alembic.ini upgrade head` before a loader. The
application uses `ENV=dev`, `ENV=nonprod`, or `ENV=prod` to select its database
configuration. Development can use the individual `DB_*` values. Nonprod and
prod use `DATABASE_URL` or their scoped `NONPROD_DATABASE_URL` /
`PROD_DATABASE_URL` value supplied by the deployment environment. The
application does not create or migrate the schema automatically. See
`backend/database/README.md` for migration creation, catalog snapshots, existing
database adoption, and the production release gate.

## Running the Data Collection

From `backend/`:

```bash
uv run python -m app.ScriptingFiles.FullDataScript.run_all
```

This loads checked-in player/goalie and current-season MoneyPuck data, NHL rosters,
historical NHL season statistics, active CapWages contracts, and the current
schedule, then refreshes roster statuses. Each stage is idempotent and targets
the schema in `backend/database/schema.sql`.

The checked-in team and line aggregate CSVs remain source assets: the current
schema intentionally has player/goalie stat tables but no team- or line-stat
tables.

To run only the roster-status refresh:

```bash
uv run python -m app.ScriptingFiles.FullDataScript.populate_roster_status
```

Run tests with:

```bash
uv run pytest
```

The backend OpenAPI document and frontend TypeScript contract are committed so
contract drift fails CI. After an intentional API change, regenerate both:

```bash
uv run python backend/export_openapi.py
cd frontend && npm run api:generate
```

The repository targets Python 3.12 and Node.js 24. Install uv 0.13.1.
Python dependencies are declared only in `pyproject.toml` and resolved in
`uv.lock`; deployment requirements are generated exports. After editing dependencies:

```bash
uv lock
bash scripts/export-requirements.sh
uv sync --locked --all-groups
```

Python tests enforce branch coverage and write HTML/XML/LCOV reports under
`coverage/python/`. Frontend coverage is enforced with
`cd frontend && npm run test:coverage`, which writes HTML, Cobertura XML, and
LCOV reports under `frontend/coverage/`. CI uploads both report directories.
The Python 3.12 regression floor is 58.80% branch-aware aggregate coverage.
`TradeValueService` has a separate 100% line-and-branch coverage gate, while
PostgreSQL-backed CI exercises the real query paths. The frontend baseline is 74.04% statements,
61.95% branches, 65.55% functions, and 77.35% lines. These exact floors prevent
coverage regressions and should be raised as each subsystem gains tests.

## Branch Workflow

Development follows:

```text
PR title → current Release-x.y.z (or Hotfix-x.y.z) → manual Prod merge
```

GitHub Actions routes PRs and creates Prod promotion PRs.
See [CI and automatic promotion setup](docs/ci-promotion.md) for the required
GitHub repository settings, hotfix branch policy, and rollout sequence.

## Roadmap

### Completed foundation

* PostgreSQL schema and idempotent ingestion pipeline
* FastAPI implementation of the frontend API contract
* React application with a mock/live API switch
* Player-value training and evaluation pipeline
* Reproducible Python 3.12 and Node.js 24 environments
* CI promotion workflow, coverage gates, and Vercel/Neon deployment configuration

### Next milestone: live NonProd vertical slice

1. Provision the NonProd Neon database, apply the schema, and load a validated dataset.
2. Deploy the backend and verify health, seasons, players, teams, contracts, cap, search,
   overview, and comparison endpoints against real data.
3. Deploy the frontend with `VITE_USE_MOCK_API=false`, validate CORS and deep links, and
   complete an end-to-end smoke test.
4. Add live API contract tests for response shapes, null handling, traded-player totals,
   pagination, sorting, and error envelopes.

### Following milestones

1. **Salary-cap accuracy:** implement buried-contract relief, accrued cap space, and LTIR
   pool rules; add scenario-based cap tests.
2. **Data reliability:** improve NHL/AHL roster reconciliation, ingestion observability,
   freshness checks, and failure recovery.
3. **Model integration:** version and publish trained player-value outputs, expose model
   freshness/quality metadata, and validate projections before presenting them as current.
4. **Product depth:** replace remaining development-only messaging, expand player and team
   analytics, and improve comparison workflows.
5. **Quality:** raise backend service/ML and frontend HTTP/search/page coverage above the
   current regression floors as each milestone lands.

## Disclaimer

This is an independent project and is not affiliated with the NHL, AHL, MoneyPuck, CapWages, or their respective organizations.

The uv workspace installs `app` from `backend/src` and `ml` from `ml/src`.
Run commands from the repository root after `uv sync --locked --all-groups`.
The `ingestion`, `ml`, and `dev` groups keep job, training, and test tools out
of the API requirements export. Preserve the compatibility pins in
`tool.uv.constraint-dependencies` until an intentional dependency upgrade.
Run `bash scripts/export-requirements.sh --check` to verify generated exports.

Python lint, formatting, and type checks run as blocking steps in backend CI.
Run `uv run ruff check`, `uv run ruff format --check`, and `uv run ty check`
from the repository root. No check suppressions or reduced coverage
thresholds are used. The retired loaders are archived as byte-preserved `.py.txt`
references. Framework-state exceptions and enum
boundary decisions remain prerequisites for their source-remediation phases;
this configuration change grants no exception to the Python rules.

Build and verify both distributions with `bash scripts/verify-packages.sh`.
It checks wheel contents and imports non-editable installations from outside
this checkout. Backend CI runs the same check. The API wheel includes `app`
without `app.ScriptingFiles`; run ingestion from the trusted workspace with
`uv sync --locked --all-groups`, which installs the source package in editable
mode. The ML wheel includes its published metadata resource, but excludes
training outputs, model binaries, datasets, and tests.

Historical CSVs now live in `backend/data/`. Source ingestion resolves that
location independently of the current directory; `TRADEVALUE_DATA_DIR` can
select another dataset directory. Editable ML installations resolve their project directory independently of the
current working directory; wheel installations use the current working directory.
When run from the repository root,
outputs retain their `ml/models/` and `ml/evaluation/outputs/` destinations.
Override these with `TRADEVALUE_MODEL_DIR` and `TRADEVALUE_EVALUATION_DIR`.
`TRADEVALUE_ENV_FILE` selects an explicit dotenv file; source installations
continue to default to `backend/.env`. Deployed applications use exported
settings and do not bundle dotenv files.
