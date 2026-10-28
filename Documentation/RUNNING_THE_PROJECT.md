# Running Verifia Locally

This guide covers the local runtime: Docker runs PostgreSQL and Redis; the FastAPI backend and durable event worker run in Python virtual environments. The complete Docker Compose stack also includes the API, two-worker-capable event worker service, and frontend.

## Requirements

- Git
- Docker Desktop with Docker Compose v2
- Python 3.11
- Node.js 20.19+, 22.13+, or 24+ and npm (for the frontend)
- Tesseract OCR with English language data, if scanned documents will be processed
- API credentials for the external AI features that will be used

Docker Compose provides PostgreSQL 16 with pgvector and Redis 7.

## 1. Configure environment files

From the repository root, create local environment files:

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
```

The root `.env` supplies Docker Compose settings. The backend reads `backend/.env` when started from `backend/`. Keep database name, username, password, and port consistent in both files. These files are ignored by Git; do not commit credentials.

This is a **local development guide**. The sample values are not production credentials. In development, API docs and unscanned uploads remain enabled and configured model providers are allowed so the local workflow continues to work.

### Production security defaults

When `APP_ENV=production` or `staging`, the backend requires a unique 32-byte JWT secret, `DEBUG=false`, exact HTTPS CORS origins, and explicit non-local PostgreSQL URLs with unique credentials. API docs and unscanned file uploads are disabled by default. External model and embedding requests are denied unless the exact provider, model, and HTTPS endpoint origin are allowlisted. No provider route is currently approved for business data; see the [provider review register](external-model-provider-review.md).

Generate independent URL-safe production secrets rather than reusing the local values:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set `BACKEND_CORS_ORIGINS` to a JSON list such as `["https://app.example.com"]`; set both PostgreSQL URLs to the same production database host, database name, username, and generated password. Use a URL-safe generated password because Compose inserts it into both database URLs. Use `EXTERNAL_MODEL_DATA_POLICY=deny` until the relevant route and data handling have been approved. After approval, pin the route and endpoint origin together, for example `groq:qwen/qwen3.8-27b|https://api.groq.com`; this does not replace provider contract and payload review.

In development/test only, `ALLOW_UNSCANNED_UPLOADS=true` can enable uploads without a malware scanner. Production and staging reject this setting; uploads remain disabled there until a scanner is configured. A scanner integration is not currently installed.

The Compose stack is for local development, not a production TLS edge. It uses database `verifia_db`, user `verifia_user`, password `verifia_password`, PostgreSQL port `5432`, and Redis port `6379`; PostgreSQL, Redis, and backend ports are bound to loopback. Compose now fails early if `POSTGRES_PASSWORD` is missing from the root `.env`. If those local values are changed, update the matching settings and both database URLs in `backend/.env`. For this host-run backend configuration, the database and Redis host is `localhost`.

### Production Compose baseline

For a host-based TLS reverse proxy, first provision private PostgreSQL and TLS-enabled Redis services, then copy `env.production.example` to `.env.production`. Replace the JWT secret, database/Redis passwords, database/cache hostnames, and frontend origin; the two PostgreSQL URLs must describe the same database. Restrict the file permissions on the production host (`chmod 600 .env.production`). Generate independent URL-safe secrets with `python -c "import secrets; print(secrets.token_urlsafe(48))"`; the example placeholders are intentionally rejected by startup validation. The production Compose file publishes no database, Redis, or backend ports and binds the frontend only to `127.0.0.1:8080` by default. Configure the host TLS proxy to forward to that loopback address, enforce HTTPS, and set HSTS there after TLS is confirmed.

From the repository root on the production host:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml build backend frontend
docker compose --env-file .env.production -f docker-compose.production.yml run --rm backend python -m alembic upgrade head
docker compose --env-file .env.production -f docker-compose.production.yml up -d backend frontend
```

The backend and frontend share a private Compose network; API traffic from the browser passes through the frontend Nginx proxy. PostgreSQL and Redis remain external managed services and must accept connections only from the deployment network. The production Compose file sets backend and worker UID/GID to `10001:10001`; the Dockerfile creates `/app/data/storage` with mode `0750` and that ownership. A new empty named volume is initialized from the image directory. Existing volumes keep their current ownership and must be checked before deploying. This checkout has not completed the production image build or runtime volume check.

Before routing traffic to a deployment, build the production backend image and verify the effective identity and mounted storage permissions:

```powershell
docker compose --env-file .env.production -f docker-compose.production.yml build backend
docker compose --env-file .env.production -f docker-compose.production.yml run --rm --no-deps backend sh -c 'id && stat -c "%u:%g %a %n" /app/data/storage'
```

Expected output identifies UID/GID `10001:10001` and storage mode `750`. For an existing upload volume, first stop writers, take and verify a backup, inspect the volume name and mount, and confirm that the target contains only the application's upload directory. If ownership needs repair, perform a reviewed one-time maintenance operation against that confirmed volume only, then rerun the identity/permission check; never recursively change ownership of an unverified host path. The image build and volume check have not yet been completed in this checkout, so this is a deployment gate. Also validate host TLS certificate/renewal, HTTPS forwarding and HSTS, firewall exposure, managed-service TLS/network policy, backups/restore, monitoring, secret rotation, download authorization/headers, and provider contracts before production. Back up uploads and restrict host-level access; coordinate database password rotation with actual service credential rotation before updating the environment file. This Compose file is a deployment baseline, not proof of a production deployment.

Generate a private development JWT key and set `SECRET_KEY` in `backend/.env`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Configure provider keys in `backend/.env` for the features that need live inference:

| Feature | Environment variables |
|---|---|
| Document Agent | `LLM7_API_KEY` |
| Verification Agent and Supervisor | `GROQ_API_KEY` (optional fallbacks: `GROQ_API_KEY_FALLBACK_1`, `GROQ_API_KEY_FALLBACK_2`) |
| Workflow Agent | `KILO_API_KEY` |
| Knowledge embeddings | `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` |

These credentials are not included in the repository. The API can start without them, but provider-backed operations require valid credentials. Use synthetic, non-sensitive documents unless provider data handling has been reviewed.

For OCR, install Tesseract on the host and confirm `tesseract --version` works. If it is not on `PATH`, set `TESSERACT_CMD` in `backend/.env` to the full executable path.

## 2. Start PostgreSQL and Redis

From the repository root:

```powershell
docker compose up -d postgres redis
docker compose ps
```

Wait until both services are healthy before starting the backend. Docker volumes preserve the local database when containers stop.

## 3. Install backend dependencies

From the repository root, create and activate the virtual environment:

```powershell
Set-Location backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

For later sessions, activate the existing environment:

```powershell
Set-Location backend
.venv\Scripts\Activate.ps1
```

`requirements-dev.txt` installs the application and development dependencies. `requirements.txt` contains the default application dependencies. The optional local Sentence-Transformers provider is isolated in `requirements-local-embeddings.txt` because it installs PyTorch and its larger model runtime; install it only when setting `EMBEDDING_PROVIDER=local`. The default API-based embedding providers do not require it, and CI deliberately installs only the default/test dependencies.

## 4. Migrate the database and run the API

With the services running and the virtual environment active, from `backend/`:

```powershell
alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The first migration creates the `vector` extension provided by the pgvector-enabled PostgreSQL image.

API documentation: <http://127.0.0.1:8000/docs>

Liveness check: <http://127.0.0.1:8000/livez>

Readiness check: <http://127.0.0.1:8000/readyz>

`/livez` reports that the API process is running. `/readyz` returns HTTP 200 only when PostgreSQL and Redis are reachable; it does not report event-worker health. `/health` remains a compatibility endpoint.

### Start the durable event worker

The API writes trusted orchestration events and their delivery records to PostgreSQL in one transaction. Start the worker after applying migrations so those records can be processed. Open a **third PowerShell terminal** at the repository root:

```powershell
Set-Location backend
.venv\Scripts\Activate.ps1
python -m app.events.worker
```

Leave this terminal running while using the application. In the full Docker Compose setup, Compose starts the event worker automatically. You can run two local Compose workers to verify competing-worker behavior:

```powershell
$env:PORT = "8001" # only if host port 8000 is already occupied
docker compose up -d --scale event-worker=2 event-worker
docker compose ps event-worker
```

The event outbox uses at-least-once delivery with database leases, capped retries, and dead-letter status after five failed attempts. Orchestration checks persisted results to avoid repeating completed dispatches. A database operator can manually redrive a trusted failed or interrupted event from `backend/`:

```powershell
python scripts/replay_event_delivery.py <EVENT_UUID>
```

The command requires authorized database access. It does not expose event payloads, and it reports only delivery state and a safe error code. It will not override an active lease or replay a completed delivery.

## Create local demo data and login credentials

A new database starts without an organization, user, or published process version. After Step 4 has applied all migrations and the API is running, open a second PowerShell terminal at the repository root and create a local administrator:

```powershell
Set-Location backend
.venv\Scripts\Activate.ps1
python scripts/create_demo_user.py
```

The script is restricted to `APP_ENV=development`. It creates a demo organization if the database has none, prompts for an email (default `admin@example.com`), and asks you to enter and confirm a password with at least 15 characters. Password entry is hidden. Choose a password of at most 72 UTF-8 bytes; the script does not accept passwords as command-line arguments, print them, or reset an existing account.

The created email and password are the credentials you enter in this terminal; there is no shared default login. Keep this terminal open long enough to note the email you chose. The password is not displayed.

### Provisioning Staff Accounts via Backend API

Once signed in as an administrator, additional accounts with roles `CUSTOMER`, `EMPLOYEE`, or `MANAGER` can be provisioned through the frontend **User access** page or the backend REST API. Only an administrator can provision users; the API chooses the organization and active state and does not allow creating another ADMIN account:

```http
POST /api/v1/auth/users
Authorization: Bearer <ADMIN_JWT_TOKEN>
Content-Type: application/json

{
  "email": "employee@example.com",
  "full_name": "Jane Doe",
  "password": "Choose-a-unique-password-2026",
  "role": "EMPLOYEE"
}
```

## Run the frontend locally

### First run: start the complete local app

Install Node.js 20.19+, 22.13+, or 24+ and npm (see [Requirements](#requirements)). From the repository root, start the backend by following steps 1–4 above. To sign in and see demo data, also follow [Create local demo data and login credentials](#create-local-demo-data-and-login-credentials). Keep that backend terminal running.

Open a **second PowerShell terminal** at the repository root and run:

```powershell
Set-Location .\frontend
npm ci
npm run dev
```

Leave `npm run dev` running and open <http://127.0.0.1:5173>. The frontend uses the backend at `http://127.0.0.1:8000`; Vite forwards API requests there. Sign in with the email and password you chose in the demo-account step. The app has no public signup; an organization administrator provisions customer and staff accounts from **User access**. Customers can create cases from published process options and see or upload files only for cases linked to their account.

If you only want to view the frontend without starting the backend, run the frontend commands above and open the URL; pages that load or change data and login will not work until the API is available.

If your API runs at another address, set its URL before starting Vite:

```powershell
$env:VERIFIA_API_PROXY_TARGET = "http://127.0.0.1:8001"
npm run dev
```

Replace the sample address with your API URL. To stop the frontend, focus its terminal and press `Ctrl+C`.

For the containerized frontend, with Docker Desktop running and the root `.env` configured:

```powershell
docker compose up --build
```

Open <http://127.0.0.1:3000>. Nginx serves the single-page app and forwards `/api/v1` to the Compose backend service. `FRONTEND_PORT` in the root `.env` can change the host port. The Vite development server runs on the host and the Compose frontend is served by Nginx; both use the same API path. The production bundle accepts HTTP only when both the page and API target use loopback addresses for this local setup; public deployments require HTTPS.

If host port `8000` is already in use (for example, by a backend started directly on the host), set a temporary Compose port override before starting the stack:

```powershell
$env:PORT = "8001"
docker compose up --build
```

The Compose backend will be available on loopback port `8001`; the frontend continues to proxy API requests over the private Compose network. Close this PowerShell session after stopping the stack to clear the temporary override.

Frontend checks, from `frontend/`:

```powershell
npm run typecheck
npm run lint
npm run test
npm run build
```

## Phase 22 quality gates

The GitHub Actions workflow at `.github/workflows/quality-gates.yml` runs on pull requests, pushes to `main`, and manual dispatch. It installs backend dependencies from `backend/requirements-dev.txt`, runs the full deterministic backend regression and the scoped critical Ruff check, upgrades a disposable PostgreSQL/pgvector database through the previous revision and current Alembic head, verifies PostgreSQL stale-claim fencing, and exercises two-worker event delivery/recovery. A separate frontend job runs `npm ci`, tests, typecheck, lint, and a production build.

To run the deterministic checks locally, activate the backend virtual environment and run from `backend/`:

```powershell
python scripts/run_backend_regression_windows.py
ruff check --isolated --select E9,F821 app tests scripts
```

Run frontend checks from `frontend/`:

```powershell
npm ci
npm test -- --run
npm run typecheck
npm run lint
npm run build
```

The migration and live two-worker checks require PostgreSQL with pgvector and Redis; the workflow provisions disposable services for them. A local run requires those services to be available and the backend environment configured. `tests/test_readiness.py` also makes real asyncpg and Redis clients connect to isolated closed loopback ports to test startup/readiness and an unavailable-database Case request without stopping a service. Live provider checks remain opt-in and are not part of the default quality gate. The repository has a broader Ruff debt baseline, so the current backend lint command intentionally gates critical errors and undefined names rather than claiming a clean whole-project style pass. See the [Phase 22 plan](phase22-implementation-plan.md) for current results and blockers.

To get hosted evidence, commit and push the changes with GitHub Desktop. Then open the repository's **Actions** tab and inspect **Phase 22 Quality Gates** for the pushed commit. Both backend and frontend jobs must succeed; the backend summary will show the expected opt-in live-test and missing Phase 17 threshold skips. Do not treat the local YAML parse as a hosted run.

## Phase 23 synthetic agent evaluation

The Phase 23 evaluator compares one agent route at a time against a tracked, fictional synthetic case set. Run from the repository's `backend/` directory in PowerShell. The module form makes the backend `app` package importable:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_phase23_agent --agent document --provider fake --limit 4 --runs 2
.\.venv\Scripts\python.exe -m scripts.evaluate_phase23_agent --agent verification --provider fake --limit 4 --runs 2
.\.venv\Scripts\python.exe -m scripts.evaluate_phase23_agent --agent workflow --provider fake --limit 4 --runs 2
.\.venv\Scripts\python.exe -m scripts.evaluate_phase23_agent --agent supervisor --provider fake --limit 4 --runs 2
```

The default `fake` adapter is offline. Its scores verify the runner and scorer wiring only; they are not model-quality results. For a bounded external comparison, first configure the selected provider's credential and model locally using the backend environment instructions, then specify that provider and pass `--confirm-external-calls`, for example:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_phase23_agent --agent document --provider groq --limit 4 --runs 1 --confirm-external-calls
```

This uses the configured/default model for that provider. Add `--model "your-actual-model-id"` only when overriding it, replacing the example text with a model ID supported by the selected provider.

Only the versioned synthetic benchmark cases are sent by this command. Each run is capped at four cases and three repeats. External calls can consume provider quota or incur cost. Do not provide real business documents until their provenance, authorization, and provider/data route approval are documented. Reports are written to the Git-ignored `data/phase23_evaluation/reports/` directory. To run the focused harness tests, use `python -m pytest -q tests/test_phase23_evaluation.py` from `backend/`. See the [Phase 23 implementation plan](phase23-implementation-plan.md) for evidence and outstanding gates.

The browser app accepts only backend-provisioned accounts. `VITE_API_BASE_URL` optionally selects the API base URL; leave it unset for the default same-origin `/api/v1` path. Production builds require HTTPS for public app/API targets, with loopback HTTP reserved for local Compose use. Do not put AI provider keys in `VITE_*` variables; browser bundles are public to every user who can load the app. Use synthetic, non-sensitive documents for local inference unless the organization has reviewed its provider data path.

## Optional backend checks

From `backend/` with the virtual environment active:

```powershell
python -m pytest
```

The regular test suite uses isolated fixtures and deterministic provider fakes. External-provider checks are opt-in and require the corresponding credentials and services.

### Phase 20 HTTP security E2E

From `backend/` with the virtual environment active, run the production-shaped HTTP boundary checks:

```powershell
python -m pytest -q tests/test_phase20_security_e2e.py
```

This suite exercises the app's HTTP configuration for production API docs, exact-origin CORS, oversized request rejection, the unscanned-upload gate, and external model route denial. It uses synthetic settings and an isolated SQLite fixture; it does not call a real model provider. The separate Docker deployment check still requires Docker Desktop and the external services described in the production deployment guide.

### Phase 24 Insurance Claim generalization E2E

From `backend/` with the virtual environment active, run the synthetic Insurance Claim journey and the declarative process-loader tests:

```powershell
python -m pytest -q tests/test_phase24_generalization.py tests/test_process_configuration_loader.py
```

The test publishes [`workflows/insurance_claim/process.json`](../workflows/insurance_claim/process.json) through the generic process loader, then uses the existing authenticated Case, document, workflow, verification, Tool Gateway, task, approval, event, and persistence boundaries. It generates fictional PDFs and fakes only model JSON generation; it does not call an external provider, connect to an insurer, or use real claim data. The full acceptance and remaining infrastructure limits are in the [Phase 24 plan](phase24-implementation-plan.md).

## Troubleshooting

| Issue | Check |
|---|---|
| PostgreSQL connection refused | Confirm the Compose PostgreSQL service is healthy and both `.env` files have matching credentials and ports. |
| `vector` extension unavailable | Confirm PostgreSQL is using the pgvector-enabled Compose image and is healthy. |
| Health endpoint reports Redis disconnected | Confirm Redis is healthy and `backend/.env` points to `localhost:6379`. |
| Tesseract not found | Install Tesseract and English language data; set `TESSERACT_CMD` if needed. |
| AI provider authentication or quota error | Confirm the selected provider matches the configured key and check provider account, quota, and model availability. |
| Authenticated operations have no data | Provision a local organization/user and publish a process version; the database starts empty. |
