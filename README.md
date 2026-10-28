# VerifiaAI

> **A configurable agentic business-process verification and orchestration platform for organizations whose processes depend heavily on documents, evidence, rules, calculations, and human decisions.**

---

## 🎯 Overview

Verifia is not a simple chatbot or wrapper around an LLM. It is an enterprise-grade business-process engine with an agentic intelligence layer designed to orchestrate complex document-driven workflows.

### Core Architectural Principle

```text
UNDERSTAND → VERIFY → ORCHESTRATE → ACT → VERIFY → CONTINUE / ESCALATE
```

```
┌─────────────────┐       ┌──────────────┐       ┌────────────────────────┐
│   AI / Agents   │ ────> │ Tool Gateway │ ────> │  Deterministic Services│
│ (Reason & Plan) │       └──────────────┘       │  (Calculate & Enforce) │
└─────────────────┘                              └────────────────────────┘       
        ▲                                                ▼
        │                                        ┌────────────────────────┐
        └──────────────── Events ─────────────── │     Business State     │
                                                 │      (PostgreSQL)      │
                                                 └────────────────────────┘
```

- **AI proposes, Deterministic systems execute:** Critical business calculations, rule validations, and state transitions are strictly deterministic and validated by the Workflow and Rule Engines.
- **Authoritative State:** PostgreSQL is the single authoritative source of business truth.
- **Auditability:** Every transition, tool execution, and verification decision produces an immutable event and audit record.

---

### 📊 Project Status & Test Suite

- **Current Phases:** **Phase 22 quality gates and Phase 23 evidence-based evaluation remain in progress; Phase 24 synthetic generalization passes locally; Phases 25–26 remain planned; Phase 27 AI Research & Evaluation Foundation is planned.** The CI disk-space remediation is in the current history, but its post-fix hosted Actions result is not recorded here. Phase 23's four-agent synthetic harness is tested; fake-provider runs are harness checks, not model-quality evidence. Live comparisons, system-level evaluation, and authorized representative-document evaluation remain open. Phase 20 remains partial pending provider/data-class approval and production evidence; the Phase 17 acceptance gate remains blocked because its ignored threshold file is unavailable. See the [Phase 27 plan](Documentation/phase27-ai-research-evaluation-plan.md) for the documentation-only AI gap audit and future backlog.
- **Backend Tests:** Latest recorded full regression: **277 passed, 7 skipped, 0 failures** (2026-10-13). Six skips are opt-in external integrations; one is the explicitly blocked Phase 17 gate. These results are local and do not establish a hosted Actions pass. See the [Phase 22 plan](Documentation/phase22-implementation-plan.md), [Phase 20–21 audit](Documentation/phase20-21-official-compliance-audit.md), and [Phases 20–24 audit](Documentation/phases20-24-comprehensive-audit-plan.md).
- **Frontend Tests:** 21 passed across 10 files; typecheck, lint, and production build pass. See `Documentation/project-audit-2026-10-10.md` for verification details.
- **Database Migrations:** `0011_durable_event_deliveries` is the checked-in Alembic head. Fresh Compose/PostgreSQL worker and readiness probes were recorded on 2026-10-13; the separate hosted GitHub Actions result remains unverified.

---

## 📁 Repository Structure

```text
VerifiaAI/
├── backend/                   # FastAPI backend application & domain services
│   ├── app/
│   │   ├── api/               # Router aggregation
│   │   ├── core/              # Settings and logging
│   │   ├── security/          # Authentication and authorization
│   │   ├── domain/            # Business domains: cases, processes, documents, etc.
│   │   ├── agents/            # Document, Verification, Workflow, Supervisor
│   │   ├── tools/             # Controlled Tool Gateway and integrations
│   │   ├── infrastructure/    # Database, LLM/providers, queue, and storage
│   │   └── events/            # Event history
│   ├── alembic/               # Database migrations
│   ├── scripts/               # Setup and evaluation utilities
│   └── tests/                 # Backend unit, integration, and live checks
├── frontend/                  # React/TypeScript SPA, tests, and Nginx container
├── workflows/import_export/   # Configurable Import/Export definition
├── data/                      # Local evaluation/storage data; ignored by Git
├── Documentation/             # Architecture blueprints, schemas, progress reports, and phase guides
├── docker-compose.yml         # PostgreSQL, Redis, backend, and frontend services
├── .env.example               # Environment configuration template
└── README.md                  # Project overview and quick start guide
```

AI implementation is part of the backend in its agent, domain, and infrastructure modules; there is no duplicate root-level `ai/` package. Backend tests live in `backend/tests/`.

---

## 🛠️ Technology Stack

- **Backend:** Python 3.11+, FastAPI, Uvicorn, SQLAlchemy 2.0, Alembic, Pydantic v2
- **Database & State:** PostgreSQL 16 with `pgvector` vector embeddings extension
- **Cache & Async Worker:** Redis 7 and a PostgreSQL-backed async event worker with durable leases and retries
- **Agent Orchestration:** Configurable per-agent model routes through the Model Gateway; current routes are documented as baselines in `Documentation/04-operations-and-roadmap.md`
- **Knowledge & RAG Embeddings:** Cloudflare Workers AI (`@cf/baai/bge-m3`, 1024-dim vectors) by default, with Hugging Face, local, and deterministic test adapters
- **Document Agent inference:** LLM7 `gpt-oss:20b` baseline; model/provider choices remain subject to Phase 23 comparative evaluation
- **Document Intelligence:** PyMuPDF, PaddleOCR / Tesseract OCR
- **Frontend:** React 19, TypeScript, Vite, React Router, TanStack Query, custom CSS
- **Testing:** Frontend verification: 21 tests across 10 files; typecheck, lint, and production build pass. Backend regression and Phase 20/21 integration evidence, including environment limitations, is in the [Phase 20–21 traceability report](Documentation/phase20-21-requirements-traceability.md).

---

## 🚀 Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 20.19+, 22.13+, or 24+ (for frontend)
- Groq API key(s) and Cloudflare Workers AI API token

### 2. Environment Configuration
Copy the sample environment file:
```bash
cp .env.example .env
```
For running the backend directly from `backend/`, also copy `backend/.env.example` to `backend/.env`.
Update the environment file used by your run mode with the provider credentials for the features you will use. Current per-agent routes and required fields are listed in the no-Docker setup guide and the environment template.

### 3. Start Infrastructure Services
Start PostgreSQL (with pgvector) and Redis using Docker Compose:
```bash
docker compose up -d postgres redis
```

### 4. Running Backend Locally
```bash
cd backend
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

The default Cloudflare/Hugging Face API embedding providers do not need PyTorch. To use the optional local Sentence-Transformers embedding provider, install its larger ML dependencies separately with `pip install -r requirements-local-embeddings.txt` before setting `EMBEDDING_PROVIDER=local`.

### 5. Running Tests
```bash
cd backend
python -m pytest
```
The default suite uses deterministic adapters and does not call external APIs. The live checks are real provider/runtime integration tests, not replacements for the fast unit contracts. Configure `backend/.env`, activate `backend/.venv`, then run from `backend/` in PowerShell:
```powershell
$env:VERIFIA_RUN_LIVE_TESTS = "1"
python -m pytest -m live -v
Remove-Item Env:VERIFIA_RUN_LIVE_TESTS
```
Live checks make real Groq and Cloudflare API requests and require configured local OCR and PostgreSQL/pgvector services. They remain opt-in to keep the default suite deterministic.
Visit Interactive API Documentation at: `http://localhost:8000/docs`

For a host-run backend, start the durable event worker in a second backend terminal after applying migrations: `python -m app.events.worker`. The full Docker Compose stack starts its event worker automatically. See the [run guide](Documentation/RUNNING_THE_PROJECT.md) for recovery, readiness, and scaling steps.

### 6. Running the frontend

Start the backend and provision a local operator account first. Then, from the repository root:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api/v1` to `http://127.0.0.1:8000` by default. Set `VERIFIA_API_PROXY_TARGET` before starting Vite when the backend uses another address. For the packaged frontend and same-origin API proxy, run `docker compose up --build` from the repository root and open `http://127.0.0.1:3000`. For the full local setup and first-admin login bootstrap, follow [`Documentation/RUNNING_THE_PROJECT.md`](Documentation/RUNNING_THE_PROJECT.md).

Frontend quality commands, from `frontend/`:

```powershell
npm run typecheck
npm run lint
npm run test
npm run build
```

The app has no public registration screen. An organization ADMIN can provision customer and staff users from **User access**; the development-only bootstrap asks you to choose the initial administrator email and password. Customer cases use participant-scoped API endpoints. The app does not accept provider credentials in browser configuration. See the [project audit](Documentation/project-audit-2026-10-10.md), [security review](Documentation/frontend-and-phase19-review.md), [frontend implementation plan](Documentation/frontend-implementation-plan.md), and [design system](Documentation/frontend-design-system.md) for current capabilities and access boundaries.

---

## 📚 Documentation

Detailed architectural specifications and guides are available in `Documentation/`:
0. [Run the project locally](Documentation/RUNNING_THE_PROJECT.md)
1. [Product Overview](Documentation/01-product-overview.md)
2. [Architecture & AI Agent Design](Documentation/02-architecture.md)
3. [Database Schema](Documentation/03-database-schema.md)
4. [Operations, Security & Roadmap](Documentation/04-operations-and-roadmap.md)
5. [Implementation Progress Report](Documentation/progress_report.md)
6. [Implementation Checklist](Documentation/Verifia_Detailed_Implementation_Checklist.md)
7. [Frontend Implementation Plan](Documentation/frontend-implementation-plan.md)
8. [Frontend Design System](Documentation/frontend-design-system.md)
9. [Phase 20 Security Plan](Documentation/phase20-production-security-implementation-plan.md)
10. [Phase 21 Durable Events Plan and Closeout](Documentation/phase21-durable-events-implementation-plan.md)
11. [Phase 20–21 Traceability Matrices](Documentation/phase20-21-requirements-traceability.md)
12. [Phase 22 Quality Gates Implementation Plan](Documentation/phase22-implementation-plan.md)
13. [Phase 23 Evidence-Based Model Evaluation Plan](Documentation/phase23-implementation-plan.md)
14. [Phase 24 Insurance Claim Generalization Plan](Documentation/phase24-implementation-plan.md)
15. [Phases 20–24 Comprehensive Audit and Remediation](Documentation/phases20-24-comprehensive-audit-plan.md)
16. [Phase 27 AI Research & Evaluation Foundation](Documentation/phase27-ai-research-evaluation-plan.md)
