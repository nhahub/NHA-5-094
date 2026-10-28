# VerifiaAI — Progress Report
*Updated: 2026-10-13*

---

## Overall Status

| Phase | Section | Status |
|---|---|---|
| **1. Repository & Development Foundation** | 1.1 – 1.4 + Restructure | ✅ Done |
| **2. Database** | Base schema plus later phase extensions | Migrations through 0011 are defined; 0011 is applied to the local Compose PostgreSQL database |
| **3. Domain Services & API** | CaseService, ProcessService, TaskService, EventService, REST API | ✅ Done |
| **4. Workflow Engine** | 4.1 – 4.4 (Deterministic Engine, Stage History, Events, Auditing) | ✅ Done |
| **5. Rules & Verification Engine** | Rule Engine, Calculation Engine, Verification Execution Service, REST API | ✅ Done |
| **6. Tool Gateway** | Trusted tool registry, policy checks, schema validation, execution audit | ✅ Core gateway complete; specialized agents use controlled paths, Supervisor delegates through them |
| **7. Object Storage & Document Upload** | Local storage adapter, validation, tenant-scoped upload/download, metadata, versions, events | ✅ Implemented and verified; cloud adapter deployment remains open |
| **8. Document Intelligence** | Format parsing, OCR adapter, configurable classification/extraction, provenance persistence | ✅ Core pipeline, evidence linking, live Tesseract OCR, and a 20-successful-document LLM7 evaluation verified; broader external-document accuracy and durable background processing remain open |
| **9. Knowledge / RAG** | Ingestion, configurable embeddings, pgvector HNSW search, org-scoped retrieval | ✅ Implemented — Cloudflare Workers AI BGE-M3 and local PostgreSQL/pgvector checks passed on small samples; broader retrieval-quality evaluation remains open |
| **10. Document Agent** | Document understanding, citation verification, review-task proposal, non-mutation compliance | Implemented; historical LLM7 sample results are recorded, but threshold acceptance is not reproducible without the missing local Phase 17 threshold file |
| **11. Verification Agent** | Stage-scoped verification planning, gateway calls, deterministic result interpretation | ✅ Implemented and regression-tested; live model quality not evaluated |
| **12. Workflow Agent** | Structured action contract, bounded context, model planning, Tool Gateway handoff, Workflow Engine authority | ✅ Implemented and verified — 2026-10-07 |
| **13. Supervisor Agent** | Bounded case-level coordination, sequential delegation, linked execution traces | ✅ Implemented and regression-tested — 2026-10-08 |
| **14. Model Gateway** | Provider-neutral routing, reliability, and usage logging | ✅ Done |
| **15. Case Orchestrator** | Trusted event dispatch, persisted-result deduplication, replay, and human-review handoff | ✅ Implemented with PostgreSQL outbox, expiring multi-worker leases, capped retries, and operator replay; external side effects remain at-least-once |
| **16. Human-in-the-Loop** | Review task lifecycle, case review packet, manager approvals, decision audit | ✅ Implemented and regression-tested |
| **17. Import/Export Near-Real Evaluation** | Ten synthetic workflows, provider-backed tools, document/OCR/retrieval/rule measurements, and per-case security probes exercised through authenticated APIs | Historical closeout recorded 2026-10-09; current threshold acceptance is **BLOCKED / not reproducible** because the ignored threshold file is absent |
| **18** | Customer and internal operations frontend | Implemented; 21 frontend tests and static/build checks pass. Local Docker frontend-to-backend health proxy verified; authenticated business-flow E2E remains unverified |
| **19** | Identity and provisioning | Implemented and regression-tested; migrations through 0011 are applied locally, but a fresh authenticated provisioning E2E remains open |
| **20** | Production security | Partial; security E2E and full backend regression pass locally; provider terms/data-class approval and production evidence remain open |
| **21** | Durable events and readiness | Fresh Docker verification on 2026-10-13: migration head 0011, `/livez` and `/readyz` HTTP 200, stale-claim fencing, normal delivery (1 attempt/0 duplicates), and expired-lease recovery (2 attempts/0 duplicates) all passed; PostgreSQL rollback probe and real ERPNext integration remain open |
| **22** | Repeatable quality gates | In progress; local backend regression passed 277/7 and critical Ruff passed. The disk-exhaustion remediation is included in `61da349` on `main`/`origin/main`; the post-fix hosted Actions result has not been verified |
| **23** | Evidence-based model and system evaluation | In progress; synthetic harness passes, while live comparisons, system-level evaluation, and authorized-document corpus evidence remain open |
| **24** | Insurance Claim generalization | Verified locally through the same authenticated APIs and persistence boundaries; synthetic test only |
| **25–26** | Final documentation and demo | Planned |
| **27** | AI Research & Evaluation Foundation | Planned; documentation-only gap audit completed 2026-10-17. Document Agent/RAG/Supervisor quality measurements, dataset breadth, model readiness, and baseline work remain not started. |

**Previous Phase 20–21 verification evidence (2026-10-11):** the earlier run reported the then-current HTTP security count and backend regression totals. Its live Compose database/readiness and two-worker probes passed at that time. Use the [official compliance audit](phase20-21-official-compliance-audit.md) for the superseding code, exact event names, current regression totals, and current live-check limits.

**Earlier audit run (2026-10-10):** the full backend regression reached 232 passed, 1 failed, and 6 opt-in live checks skipped. The only failure is `test_fictional_policy_questions_have_labeled_sources_and_threshold_gates`, because `data/phase17_evaluation/acceptance_thresholds.json` is missing; the user confirmed they do not have it. This file is ignored and absent from Git history, so no replacement values were invented. The host had bcrypt 5 while `backend/requirements.txt` pins bcrypt `<4.1`; that run used a process-only hash compatibility shim for the test process and changed no installed packages. **2026-10-12 update:** passlib's bcrypt backend was replaced with direct `bcrypt.hashpw`/`bcrypt.checkpw` calls in `app/security/service.py` so the service works with both bcrypt 4.x (CI) and 5.x (local host) without a shim; the fix is included in the committed Phase 22 baseline. Frontend verification passed with 21 tests across 10 files, typecheck, ESLint, and production build. See the dated audit addendum at the end of this report. Historical Phase 17 scenario results remain historical evidence and are not a current acceptance-gate pass.

---

## Phase 1 — Completed in Detail

### 1.1 Repository Foundation ✅

All root-level project files are in place:

| File / Dir | Purpose |
|---|---|
| [`README.md`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/README.md) | Project overview, architecture, quickstart guide |
| [`.gitignore`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/.gitignore) | Ignores Python cache, venv, .env, Docker volumes, IDE files |
| [`.env.example`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/.env.example) | Template with all environment variables documented |
| [`docker-compose.yml`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/docker-compose.yml) | Orchestrates PostgreSQL (pgvector), Redis, FastAPI backend |
| `backend/` | Python FastAPI backend application |
| `frontend/` | Placeholder for React + TypeScript frontend |
| `backend/tests/` | Backend unit, integration, and opt-in live-provider tests |
| `data/storage/` | Local file storage directory |
| `data/samples/` | Sample documents for testing |
| `workflows/import_export/` | Import/Export workflow configuration |
| `backend/app/agents/`, `backend/app/domain/`, `backend/app/infrastructure/llm/` | Implemented AI agents, document/knowledge capabilities, model gateway, and provider adapters |

---

### 1.2 Backend Setup ✅

The Python backend is fully initialized with:

**Virtual environment & dependencies** at [`backend/requirements.txt`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/requirements.txt):
- `FastAPI` + `Uvicorn` — API framework and ASGI server
- `SQLAlchemy 2.0` — ORM with async support
- `Alembic` — database migrations
- `Pydantic v2` — data validation and settings
- `asyncpg` + `psycopg2-binary` — async and sync PostgreSQL drivers
- `redis` — Redis client
- `python-jose` + `passlib[bcrypt]` — JWT auth and password hashing

**Core modules** at `backend/app/core/`:
- [`config.py`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/core/config.py) — `Settings` class using Pydantic BaseSettings; loads all variables from `.env` (DB URL, Redis URL, JWT secret, CORS origins, etc.)
- [`logging.py`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/core/logging.py) — Structured JSON logging, configures Uvicorn and SQLAlchemy loggers

**FastAPI entrypoint** at [`backend/app/main.py`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/main.py):
- `lifespan()` context manager handles startup/shutdown
- CORS middleware configured from settings
- All domain routers mounted under `/api/v1`
- `/health` endpoint — checks Redis connectivity and returns service status
- `/docs` and `/redoc` — Swagger UI and ReDoc (debug mode only)

---

### 1.3 Backend Modules ✅

All 14 domain modules were created, each with a standard 4-file structure:

| File | Purpose |
|---|---|
| `models.py` | SQLAlchemy ORM models (database tables) |
| `schemas.py` | Pydantic schemas (request/response validation) |
| `service.py` | Business logic layer (no DB logic in routers) |
| `router.py` | FastAPI router (HTTP handlers only, delegates to service) |

**Modules created:**

| Module (new path) | What it does |
|---|---|
| [`domain/cases/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/domain/cases/) | Case lifecycle: `Case`, `CaseParticipant`. Statuses: OPEN, IN_PROGRESS, PENDING_REVIEW, COMPLETED, REJECTED, CANCELLED |
| [`domain/processes/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/domain/processes/) | `Process` and `ProcessVersion` (immutable snapshots). Versions: DRAFT → PUBLISHED → ARCHIVED |
| [`domain/workflows/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/domain/workflows/) | `WorkflowStage` and `WorkflowTransition` — controls how cases move through stages |
| [`domain/documents/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/domain/documents/) | `Document`, `DocumentVersion`, `ExtractedField` — upload, versioning, field extraction results |
| [`domain/verifications/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/domain/verifications/) | `VerificationDefinition` (what to check) and `VerificationExecution` (run result: PASS/FAIL/REVIEW/INCONCLUSIVE) |
| [`domain/rules/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/domain/rules/) | `BusinessRule` — declarative rule expressions (e.g. `invoice.qty == po.qty`) |
| [`domain/tasks/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/domain/tasks/) | `Task` — assigned to users/roles with priority, due date, and completion metadata |
| [`domain/approvals/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/domain/approvals/) | `Approval` — explicit human decisions (APPROVED/REJECTED) with comment and timestamp |
| [`domain/knowledge/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/domain/knowledge/) | `KnowledgeDocument` — RAG knowledge base with pgvector embeddings |
| [`domain/audit/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/domain/audit/) | `AuditLog` — immutable audit trail for every important action |
| [`domain/organizations/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/domain/organizations/) | `Organization` stub — top-level tenant entity |
| [`security/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/security/) | `Organization`, `User`, `RoleEnum` (CUSTOMER/EMPLOYEE/MANAGER/ADMIN), JWT auth endpoints |
| [`agents/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/agents/) | Agent orchestration stubs — agent execution router and schemas |
| [`tools/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/tools/) | Policy-enforced Tool Gateway — trusted handler registry, scoped discovery/execution, contract validation, and execution logging |
| [`events/`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/events/) | `EventRecord` — business event bus (CASE_CREATED, DOCUMENT_UPLOADED, etc.) |

---

### 1.4 Infrastructure ✅

| Component | Status | Detail |
|---|---|---|
| **PostgreSQL + pgvector** | ✅ | `docker-compose.yml` uses `pgvector/pgvector:pg16` image |
| **Redis** | ✅ | `docker-compose.yml` uses `redis:7-alpine` |
| **FastAPI ↔ PostgreSQL** | ✅ | Async SQLAlchemy session in [`infrastructure/database/session.py`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/infrastructure/database/session.py) |
| **Alembic** | ✅ | Configured at [`backend/alembic.ini`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/alembic.ini) |
| **Initial migration** | ✅ | [`0001_initial_schema.py`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/alembic/versions/0001_initial_schema.py) — creates all tables |
| **Redis client** | ✅ | [`infrastructure/queue/redis.py`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/infrastructure/queue/redis.py) — async Redis with health check |
| **Async job queue** | ✅ | [`infrastructure/queue/queue.py`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/infrastructure/queue/queue.py) — `JobQueueService` with job types: `DOC_PROCESS`, `OCR`, `EMBED`, `VERIFY`, `AGENT` |
| **`/health` endpoint** | ✅ | Returns `{ status, app, version, environment, services: {api, redis} }` |

---

### Project Restructure (doc §34) ✅

The entire `backend/app/` directory was reorganized to match the architecture defined in `04-operations-and-roadmap.md § 34`:

**Before** (flat structure):
```
app/
├── auth/          ← Security
├── cases/         ← Domain
├── verification/  ← Domain
├── database/      ← Infrastructure
└── ...
```

**After** (layered architecture):
```
app/
├── api/                ← HTTP routing layer
├── core/               ← Settings + logging
├── security/           ← JWT auth, User/Org models (was: auth/)
├── domain/             ← All business logic grouped
│   ├── organizations/
│   ├── cases/
│   ├── processes/
│   ├── workflows/
│   ├── tasks/
│   ├── approvals/
│   ├── rules/
│   ├── documents/
│   ├── knowledge/
│   ├── audit/
│   └── verifications/  ← (was: verification/)
├── agents/             ← LangGraph agent orchestration
├── tools/              ← Tool Gateway
├── events/             ← Business event system
└── infrastructure/     ← Technical adapters
    ├── database/       ← (was: app/database/)
    ├── queue/          ← Redis + async job queue
    ├── storage/        ← File storage adapter (placeholder)
    ├── llm/            ← LLM/model gateway (placeholder)
    └── workflow/       ← Workflow engine (placeholder)
```

All imports updated throughout every `.py` file, including [`alembic/env.py`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/alembic/env.py).

---

## Phase 2 — Completed in Detail ✅

All **45 database tables**, constraints, foreign keys, and indexes specified across [§26 of the Architecture Blueprint](file:///c:/Users/Adham/Desktop/VerifiaAI-1/Documentation/03-database-schema.md#26-database-tables) are fully defined as SQLAlchemy 2.0 ORM models with `pgvector` extension support:

| Logical Area | Models Created | Description |
|---|---|---|
| **Organization & Security** | `Organization`, `Department`, `DepartmentMember`, `User`, `Role`, `Permission`, `RolePermission`, `UserRole` | Tenant scoping, RBAC hierarchy, department membership, and unique constraints (`uq_users_org_email`) |
| **Process Configuration** | `Process`, `ProcessVersion`, `Requirement` | Process lifecycle (`ACTIVE`/`INACTIVE`), immutable `ProcessVersion` (`DRAFT` → `PUBLISHED` → `ARCHIVED`), prerequisites |
| **Workflow Engine** | `WorkflowStage`, `WorkflowTransition` | Ordered states (`is_initial`, `is_terminal`), deterministic transition paths with condition config and permissions |
| **Runtime & Cases** | `Case`, `CaseParticipant`, `CaseData`, `CaseStageHistory` | Immutable version binding, structured extracted facts, participant types, and direct stage transition audit trail |
| **Documents & Evidence** | `Document`, `DocumentVersion`, `ExtractedField`, `Evidence`, `EvidenceItem` | Versioned storage metadata, field locators/bounding boxes/confidences, multi-source evidence items |
| **Verification & Rules** | `VerificationDefinition`, `VerificationRule`, `VerificationExecution`, `VerificationResult`, `BusinessRule`, `CalculationDefinition`, `RuleExecution`, `CalculationExecution` | Declarative business rules, deterministic formulas, execution runs (`PASS`, `FAIL`, `REVIEW`, `NOT_APPLICABLE`, `INCONCLUSIVE`) |
| **Tasks & Approvals** | `Task`, `Approval` | Human/system review queues (`PENDING` → `ASSIGNED` → `IN_PROGRESS` → `COMPLETED`/`REJECTED`), explicit decision trail |
| **Tools & Integrations** | `ToolDefinition`, `ToolExecution`, `Integration`, `IntegrationConfig` | Auditable Tool Gateway logging, ERP/Logistics integration adapters |
| **Knowledge (RAG)** | `KnowledgeSource`, `KnowledgeDocument`, `KnowledgeChunk` | SOP/policy document ingestion with `Vector(1536)` embeddings using `pgvector` |
| **AI Layer** | `ModelConfig`, `AgentDefinition`, `AgentExecution` | Provider gateway configurations, agent specializations, execution context & token metrics |
| **Events & Audit** | `EventRecord`, `AuditLog`, `Notification` | 13 business event types, immutable security audit logs, user notifications |

### Migration & Verification
- **Alembic migrations**: `0001_initial_schema.py` creates the initial schema; `0002_tool_execution_organization_scope.py` adds organization scope to tool execution audit records; `0003_verification_evidence_links.py` links evidence bundles to verification executions; and `0004_approval_type.py` persists approval types.
- **Test suite**: Added [`test_database_models.py`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/tests/test_database_models.py) verifying all 45 tables, relations, and enums. **14 / 14 tests passing**.

---

## Phase 3 — Completed in Detail ✅

### CaseService

| Method | Description |
|---|---|
| `create_case(db, org_id, created_by_user_id, case_in)` | Requires a published process version owned by the same organization; creates case with auto-generated `CASE-YYYYMMDD-XXXX` number, sets initial stage, emits `CASE_CREATED` event |
| `get_cases(db, org_id, status, stage, skip, limit)` | Tenant-scoped listing with optional filters |
| `get_case_by_id(db, case_id)` | Single case lookup |
| `get_case_state(db, case_id)` | Full state snapshot: case data, stage info, counts (documents, tasks, verifications, evidence), participants |
| `update_case(db, case_id, case_update)` | Updates title/metadata; raises `ValueError` if case is `COMPLETED`/`CANCELLED` |
| `close_case(db, case_id, close_req, actor_id)` | Sets status, records `completed_at`, emits `CASE_COMPLETED`/`CASE_CANCELLED` event |
| `add_participant(db, case_id, participant_in)` | Adds `CaseParticipant` with typed roles (CUSTOMER/ASSIGNEE/REVIEWER/OBSERVER) |

### ProcessService

| Method | Description |
|---|---|
| `create_process(db, org_id, process_in, created_by)` | Creates process + auto-generates DRAFT version v1 |
| `get_processes(db, org_id, skip, limit)` | Tenant-scoped listing |
| `get_versions_by_process_id(db, process_id)` | All versions for a process |
| `create_new_version(db, process_id, version_in, created_by)` | Auto-increments version number; always starts as DRAFT |
| `add_stage_to_version(db, version_id, stage_in)` | Enforces DRAFT guard via `_assert_version_is_draft()` |
| `add_transition_to_version(db, version_id, transition_in)` | Enforces DRAFT guard |
| `add_requirement_to_version(db, version_id, req_in)` | Enforces DRAFT guard |
| `add_verification_to_version(db, version_id, verif_in)` | Enforces DRAFT guard |
| `add_rule_to_version(db, version_id, rule_in)` | Enforces DRAFT guard |
| `publish_version(db, version_id)` | Validates ≥1 stage exists, then transitions DRAFT → PUBLISHED with `published_at` timestamp |
| `archive_version(db, version_id)` | Transitions PUBLISHED → ARCHIVED |

### TaskService

| Method | Description |
|---|---|
| `create_task(db, task_in, created_by_id, created_by_type)` | Validates case exists, creates task, emits `TASK_CREATED` event |
| `get_tasks(db, org_id, case_id, assigned_user_id, status, priority, skip, limit)` | Tenant-scoped with JOINed filters |
| `get_tasks_for_user(db, user_id, org_id)` | Tasks assigned to specific user |
| `get_task_by_id(db, task_id)` | Single task lookup |
| `update_task(db, task_id, task_update, actor_id, actor_type)` | Updates fields, auto-sets `completed_at` when status → COMPLETED, emits `TASK_UPDATED` event |

### ApprovalService

| Method | Description |
|---|---|
| `request_approval(db, approval_in, organization_id, actor_id, actor_type)` | Creates a typed PENDING request only for a case in the actor's organization; an optional task must belong to that case; emits `APPROVAL_REQUESTED` and an audit record |
| `decide_approval(db, approval_id, decided_by_user_id, decision_in, organization_id)` | Allows one decision from PENDING, records the human actor, timestamp, and comment, and writes `APPROVAL_DECIDED` event and audit records |
| `get_approvals_by_case(db, case_id)` | Lists approval records after the API verifies the case belongs to the authenticated user's organization |

### EventService

| Method | Description |
|---|---|
| `emit_event(db, event_type, organization_id, actor_type, actor_id, case_id, payload)` | Creates immutable `EventRecord`, accepts optional `**kwargs` for extra context |
| `get_events_for_case(db, case_id, skip, limit)` | Ordered ascending by `created_at` |
| `get_events_for_organization(db, org_id, skip, limit)` | Ordered descending |

### REST API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/cases` | Create case |
| `GET` | `/api/v1/cases` | List cases (tenant-scoped, filterable) |
| `GET` | `/api/v1/cases/{id}` | Get case |
| `GET` | `/api/v1/cases/{id}/state` | Full state snapshot |
| `GET` | `/api/v1/cases/{id}/events` | Case event log |
| `PATCH` | `/api/v1/cases/{id}` | Update title/metadata |
| `POST` | `/api/v1/cases/{id}/close` | Close case |
| `POST` | `/api/v1/cases/{id}/participants` | Add participant |
| `POST` | `/api/v1/processes` | Create process |
| `GET` | `/api/v1/processes` | List processes |
| `GET` | `/api/v1/processes/{id}` | Get process |
| `GET` | `/api/v1/processes/{id}/versions` | List versions |
| `POST` | `/api/v1/processes/{id}/versions` | Create new draft version |
| `GET` | `/api/v1/processes/versions/{id}` | Get version detail |
| `POST` | `/api/v1/processes/versions/{id}/stages` | Add stage (DRAFT guard) |
| `POST` | `/api/v1/processes/versions/{id}/transitions` | Add transition (DRAFT guard) |
| `POST` | `/api/v1/processes/versions/{id}/requirements` | Add requirement (DRAFT guard) |
| `POST` | `/api/v1/processes/versions/{id}/verifications` | Add verification (DRAFT guard) |
| `POST` | `/api/v1/processes/versions/{id}/rules` | Add rule (DRAFT guard) |
| `POST` | `/api/v1/processes/versions/{id}/publish` | Publish version |
| `POST` | `/api/v1/processes/versions/{id}/archive` | Archive version |
| `POST` | `/api/v1/tasks` | Create task |
| `GET` | `/api/v1/tasks` | List tasks (filterable) |
| `GET` | `/api/v1/tasks/my` | Current user's tasks |
| `GET` | `/api/v1/tasks/{id}` | Get task |
| `PATCH` | `/api/v1/tasks/{id}` | Update task |

### Test Coverage

| Test File | Tests | Coverage |
|---|---|---|
| [`test_domain_services.py`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/tests/test_domain_services.py) | 4 | Process lifecycle & immutability; case creation, events, state, close, protection; published-version and same-organization case guard; task creation, query, completion |
| [`test_domain_api.py`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/tests/test_domain_api.py) | 4 | Process, Case, and Task API round-trips; approval request/decision event and audit lifecycle |

**Total: 20 / 20 tests passing** ✅

---

## Phase 4 — Completed in Detail ✅

### WorkflowService & Deterministic Engine

| Component / Method | Description |
|---|---|
| `validate_transition(db, request)` | Deterministically verifies: case existence, non-terminal case state, target stage version binding, stage transition paths, actor role authorization, human approval prerequisite, and stage requirements (required documents, verifications, approvals, data fields). Returns structured `TransitionResult` with violation details. |
| `execute_transition(db, request)` | Executes validation; on failure records `WORKFLOW_TRANSITION_REJECTED` audit log and returns result; on success updates case stage/status, inserts `CaseStageHistory`, emits `WORKFLOW_TRANSITIONED` (and `CASE_COMPLETED` on terminal), and creates `WORKFLOW_TRANSITION_EXECUTED` audit record. |
| Stage & Transition Management | `create_stage`, `get_stages_by_version`, `get_stage_by_id`, `create_transition`, `get_transitions_from_stage`, `get_transitions_by_version`. |

### REST API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/workflows/stages` | Create workflow stage |
| `GET` | `/api/v1/workflows/stages/version/{version_id}` | List stages for a process version |
| `POST` | `/api/v1/workflows/transitions` | Create workflow transition rule |
| `GET` | `/api/v1/workflows/transitions/version/{version_id}` | List transitions for a process version |
| `POST` | `/api/v1/workflows/validate` | Deterministic transition pre-check endpoint |
| `POST` | `/api/v1/workflows/transition` | Execute workflow stage transition |

### Test Coverage

| Test File | Tests | Coverage |
|---|---|---|
| [`test_workflow_engine.py`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/tests/test_workflow_engine.py) | 3 | Full 7-stage Import/Export pipeline simulation without AI; error invariants (jumping stages, repeated transitions, non-existent target, stage mismatch, closed case mutation); REST API validation and transition execution round-trip. |

**Total: 23 / 23 tests passing** ✅

---

## Phase 5 — Completed in Detail ✅

### Rule Engine ([`engine.py`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/app/domain/rules/engine.py))

Fully deterministic, zero-`eval()` rule and calculation engine:

| Operator / Feature | Description |
|---|---|
| `EQUAL`, `NOT_EQUAL` | Decimal-first numeric equality, case-insensitive string fallback |
| `GREATER_THAN`, `LESS_THAN`, `GTE`, `LTE` | Numeric and datetime comparisons |
| `EXISTS`, `IS_NULL` | Presence / absence checks |
| `IN`, `CONTAINS`, `STARTS_WITH`, `ENDS_WITH` | Collection and string membership |
| `REGEX_MATCH` | Safe `re.search()` without eval |
| `WITHIN_TOLERANCE` | Absolute or percentage delta check |
| `DATE_DIFF_DAYS_LTE` | Date range check (parsed ISO/multiple formats) |
| `AND`, `OR`, `NOT` | Composable boolean logic with nested traces |
| **Aggregates** | `SUM`, `COUNT`, `AVG`, `MIN`, `MAX` over lists |

### Calculation Engine

| Capability | Description |
|---|---|
| Structured JSON AST | Nested `ADD`, `SUBTRACT`, `MULTIPLY`, `DIVIDE`, `ROUND`, `ABS`, `MIN`, `MAX`, `IF_ELSE` |
| Infix string formulas | Safe shunting-yard parser: `qty * unit_price + tax` (no `eval()`) |
| Missing-field safety | Returns `None` instead of crashing on missing values |
| Division-by-zero safety | Returns `None` on zero divisors |
| Decimal precision | All arithmetic done with Python `Decimal` |

### RuleService & VerificationService

| Method | Description |
|---|---|
| `create_rule` / `get_rules_by_version` | CRUD for `BusinessRule` declarative expressions |
| `create_calculation` / `get_calculations_by_version` | CRUD for `CalculationDefinition` formula specs |
| `evaluate_rule(rule_id / expression, context)` | Ad-hoc or DB-backed rule evaluation with full trace |
| `evaluate_calculation(calc_id / formula, context)` | Ad-hoc or DB-backed formula evaluation |
| `VerificationService.run_verification(case_id, verification_id)` | Full orchestration: context assembly → calculations → rules → `VerificationExecution` + `VerificationResult` + `RuleExecution` + `CalculationExecution` records + event + audit log |

### REST API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/rules` | Create business rule |
| `GET` | `/api/v1/rules/version/{id}` | List rules for version |
| `POST` | `/api/v1/rules/calculations` | Create calculation definition |
| `GET` | `/api/v1/rules/calculations/version/{id}` | List calculations for version |
| `POST` | `/api/v1/rules/evaluate` | Ad-hoc rule expression evaluation |
| `POST` | `/api/v1/rules/calculate` | Ad-hoc formula evaluation |
| `POST` | `/api/v1/verifications/definitions` | Create verification definition |
| `GET` | `/api/v1/verifications/definitions/version/{id}` | List definitions for version |
| `POST` | `/api/v1/verifications/execute` | Run verification against case |
| `GET` | `/api/v1/verifications/case/{id}` | List executions for case |
| `GET` | `/api/v1/verifications/{id}` | Get execution detail |

### Test Coverage

| Test File | Tests | Coverage |
|---|---|---|
| [`test_rules_and_verifications.py`](file:///c:/Users/Adham/Desktop/VerifiaAI-1/backend/tests/test_rules_and_verifications.py) | 5 | Engine primitives and missing-value policies; Calculation engine (structured, infix, aggregates, division by zero, missing fields); Verification lifecycle with case facts, source document, extracted-field locator, successful tool output, rule/calculation traces, and cross-case tool-reference rejection; REST API round-trip including evidence response |

**At Phase 5 completion: 27 / 27 tests passing** ✅

### Verification Evidence Links

Each verification execution now owns an `Evidence` bundle exposed in the verification response. Evidence items link to the case's source documents and extracted fields (including page number, bounding box, confidence, and extraction method), rule and calculation execution traces, and optional successful `ToolExecution` records explicitly supplied with the run. Tool execution references are validated against the same case and organization; failed, missing, or cross-case references are rejected. `0003_verification_evidence_links.py` adds the nullable execution foreign key to `evidence` so older evidence remains valid.

---

## Phase 6 — Tool Gateway (Core complete; integrations continue) 🟡

The first Phase 6 increment is committed as `15d5b26` (`Implement Phase 6 policy-enforced Tool Gateway`). It establishes the generic, configuration-driven gateway described in the checklist and keeps executable handlers in trusted application code. The Import/Export workflow remains configuration for demonstrating the generic platform rather than logic embedded in the gateway.

### Tool Contract and Registration

Each registered tool publishes its name, description, input schema, output schema, required permission code, and allowed agent types. Registration accepts only async handlers from trusted application code. Process-version configuration enables registered tools and can further restrict allowed agent types; it cannot introduce executable handlers.

| Tool | Implementation status | Purpose |
|---|---|---|
| `calculate_order_total` | ✅ Built-in | Decimal-based subtotal, tax, and total calculation |
| `check_required_documents` | ✅ Built-in | Compares required document types in process requirements with documents attached to the case |
| `compare_documents` | ✅ Built-in | Compares case fields or extracted document fields and returns match/mismatch/inconclusive status with evidence references |
| `run_verification` | ✅ Built-in | Invokes deterministic VerificationService and returns the verification status and linked evidence bundle ID(s) |
| `create_task` | ✅ Built-in | Creates a case task after checking optional stage and assignee organization scope |
| `request_approval` | ✅ Built-in | Creates a pending case approval and emits an approval-requested event |
| `check_inventory` | 🟡 Contract registered | Requires an active organization integration and trusted adapter implementation |
| `get_customer` | 🟡 Contract registered | Requires an active organization integration and trusted adapter implementation |
| `get_payment_status` | 🟡 Contract registered | Requires an active organization integration and trusted adapter implementation |

Integration-backed tool contracts dispatch through a shared adapter boundary. The adapter is trusted async application code selected by the configured integration type. The gateway does not execute process-supplied code, and integration credentials stay in integration configuration rather than tool arguments or execution traces.

### ToolGatewayService

| Method / capability | Description |
|---|---|
| `register_tool(...)` | Registers a trusted async handler with structured input/output schemas, permission code, and allowed agent types. Duplicate or invalid tool names and synchronous handlers are rejected. |
| `register_integration_adapter(type, handler)` | Registers trusted async adapter code for an integration type. |
| `list_tools(db, actor, case_id)` | Resolves the case/process configuration and returns enabled registered tools only when the organization, permission, and integration readiness checks pass. |
| `execute_tool(db, request, actor, agent_id?)` | Creates a trace, loads the case/process context, applies policy checks, validates input, invokes the handler with a timeout, validates output, and records success, rejection, or failure. Agent identity is an internal service parameter rather than client-controlled request data. |
| Schema validation | Checks supported JSON Schema constraints including object properties, required keys, extra properties, types, enums, numeric bounds, string lengths, list lengths, UUID/date-time formats, and finite numeric values. |

### Authorization and Execution Audit

Execution checks the authenticated actor's organization against the case, verifies that the case has a valid process version, enforces the process tool allowlist (disabled unless explicitly enabled), intersects process and built-in agent-type restrictions, verifies the registered tool permission, and confirms an active integration/adapter when required. Unknown tools, policy denials, invalid input/output, handler exceptions, and timeouts have structured outcomes and are recorded. The public API rejects extra request fields, preventing callers from spoofing agent identity.

`ToolExecution` records organization and case scope, tool, requester type/id, input/output JSON, status, error, and start/completion timestamps. A new migration adds the organization foreign key and index to tool execution records.

### REST API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/tools?case_id={id}` | Lists registered tools enabled and authorized for the specified case's process |
| `POST` | `/api/v1/tools/execute` | Executes a tool as the authenticated user; returns structured result or an HTTP error with execution ID |

The execute request contains `tool_name`, `case_id`, and an `arguments` object. Tool-specific input and output schemas are enforced by the gateway. The response includes success/status, output or error, execution ID, and HTTP status code.

Process-version configuration selects available tools. For example:

```json
{
  "tool_gateway": {
    "allowed_tools": {
      "calculate_order_total": {
        "enabled": true,
        "allowed_agents": ["VERIFICATION", "WORKFLOW"]
      },
      "check_inventory": {
        "enabled": true,
        "integration_type": "ERP",
        "integration_id": "<organization integration UUID>",
        "allowed_agents": ["VERIFICATION"]
      }
    }
  }
}
```

### Test Coverage

| Test | Coverage |
|---|---|
| `test_tool_gateway_calculation_is_scoped_authorized_and_audited` | Successful deterministic calculation and trace; filtered discovery; missing arguments; process-policy and permission denials; allowed/denied agent type; unknown tool; cross-organization denial; audit record count/status |
| `test_tool_gateway_api_filters_discovery_and_rejects_agent_spoofing` | Authenticated discovery and execution; user identity recorded; client-supplied `agent_id` rejected; invalid request contract returns validation error and execution ID |
| Full backend test suite | **31 / 31 passed**, with one existing Starlette/httpx deprecation warning |

Alembic history and offline SQL generation pass through `0004_approval_type.py`.

### Remaining in Phase 6

- Wire agent orchestration so agents invoke capabilities only through this gateway; until then, the checklist's “agents cannot bypass gateway” Definition of Done remains open.
- Implement and exercise production organization adapters for `check_inventory`, `get_customer`, and `get_payment_status`; only their contracts and shared adapter boundary are currently registered.

---

## Phase 7 — Object Storage & Document Upload ✅

Phase 7 is implemented against the existing `Document`, `DocumentVersion`, `ExtractedField`, and `Case` models. Document bytes are kept outside PostgreSQL behind the storage contract; PostgreSQL stores the case relationship, opaque storage reference, SHA-256 hash, MIME type, byte size, uploader, version, and timestamps. No database migration was needed because the existing schema already contains the required metadata fields.

### Storage Boundary and Local Adapter

`StorageBackend` defines asynchronous `upload`, `download`, `delete`, and `exists` operations. `LocalFileStorage` implements the contract using atomic temporary-file writes and replacement. It resolves opaque POSIX-style references beneath a configured root, rejects absolute paths, traversal, and backslashes, and performs filesystem work off the async event loop. The backend factory selects the local adapter and fails explicitly for an unimplemented provider instead of silently treating MinIO settings as working storage.

The configured default is `STORAGE_BACKEND=local`, rooted at `STORAGE_LOCAL_PATH=./data/storage`. Upload size is controlled by `DOCUMENT_MAX_FILE_SIZE_BYTES` (20 MiB by default). MinIO/S3 adapters, credentials, bucket lifecycle, and production storage operations remain deployment work; environment placeholders alone do not count as adapters.

### Upload Pipeline and API

The authenticated multipart upload validates the case against the caller's organization, canonicalizes document type, checks filename safety and the configured size limit, and verifies supported file content against the extension and declared MIME type. Supported types are PDF, PNG, JPEG, XLS, XLSX, CSV, DOCX, and UTF-8 TXT. DOCX OOXML packages are checked for required Word document parts, encrypted/macro-enabled content, unsafe paths, entry count, and expanded size before storage. These formats are accepted and stored only; parsing and extraction belong to Phase 8. The service hashes content with SHA-256, stores the bytes, creates the document and version rows, and emits `DOCUMENT_UPLOADED`. If database/event persistence fails, the transaction is rolled back and the newly stored object is removed.

| Method | Path | Behavior |
|---|---|---|
| `POST` | `/api/v1/documents` | Uploads a file to a case; exact case/type/content duplicates return the existing document without another event. |
| `POST` | `/api/v1/documents/{document_id}/versions` | Adds a new immutable content version; identical content already in that document is treated as a duplicate. |
| `GET` | `/api/v1/documents/case/{case_id}` | Lists case documents within the authenticated organization. |
| `GET` | `/api/v1/documents/{document_id}` | Returns tenant-scoped document metadata and versions. |
| `GET` | `/api/v1/documents/{document_id}/versions/{version_id}/content` | Downloads a specific stored version with private/no-store and nosniff headers. |
| `POST` | `/api/v1/documents/{version_id}/fields` | Persists extracted fields against the scoped version and marks the document processed. |

Storage references are intentionally omitted from public response schemas. Binary retrieval requires an authorized document/version route, and unknown or cross-organization references are not returned through the API.

### Verification

`backend/tests/test_document_upload.py` covers local storage round-trip and deletion, traversal rejection, extension/content/MIME/size/filename validation, safe DOCX package checks and archive limits, UTF-8 text validation, API upload, metadata and persisted object bytes, exact duplicate handling, second-version creation, version-specific downloads, upload event count, and invalid-case rejection. Full backend verification after DOCX/TXT support on 2026-09-30: **47 / 47 tests passed**. One existing Starlette/httpx deprecation warning remains.

### Remaining deployment work

- Implement and integration-test a MinIO/S3 adapter when the target provider and deployment settings are selected. Current supported backend is local filesystem storage.
- Add operational retention/backup policy and provider-level lifecycle/availability monitoring with the deployment configuration.

---

## Phase 8 — Document Intelligence (Core implemented; runtime verification open) 🟡

Phase 8 now has format parsers for PDF, scanned/image PDF detection, PNG/JPEG, XLS/XLSX, CSV, DOCX, and UTF-8 TXT. Parser outputs use normalized text/table/cell blocks and keep source locations such as PDF page/bounding box, spreadsheet sheet/cell, CSV row/column, Word paragraph/table, or text line. Hidden spreadsheet sheets are skipped with a warning, and embedded DOCX images are explicitly noted as not OCRed.

The OCR adapter uses Tesseract for image files and only PDF pages identified as textless. It returns recognized lines, confidence, and page/image-coordinate boxes. Per-image/page limits and OCR timeouts are configured. Tesseract 5.4.0 and English data are installed in the local Windows environment; the real SROIE receipt OCR check passed. Broader OCR evaluation, including scanned PDFs, remains open.

The classification catalog covers the required invoice, purchase order, packing list, and unknown types, with additional common document classes and process-configurable catalog extension. Each agent now reads its provider and model from role-specific settings. The Document baseline is LLM7 `gpt-oss:20b`, which passed the held-out sample thresholds; Kilo `dots-studio/dots-3-note-preview:free` also served the live three-document mismatch workflow. Verification and Supervisor are assigned Groq Qwen 3.8 27B, while Workflow is assigned Kilo Dots3. These assignments are working baselines, not comparative model-quality winners. The Gemini adapter remains available in code but is not selected. Structured extraction is driven by versioned JSON Schemas (default invoice, purchase order, and packing list schemas, with process-level extension), validates required fields and types, checks date formats and numeric constraints, verifies citations against parser source blocks, and marks low-confidence or logically inconsistent invoice results for review.

`DocumentProcessingRun` persists per-version run number/status, parser and model versions, predicted class/confidence, schema/configuration provenance, review reasons, and safe failure details. `ExtractedField` now links to its processing run and stores a normalized value with source text and locator. Normalized parser output is written to private object storage. An authenticated organization-scoped endpoint runs a selected version through this pipeline and emits completion/failure events. Review-required runs create a pending, unassigned `DOCUMENT_REVIEW` task linked to the processing run; low classification confidence raises its priority. No reviewer-assignment policy or workflow/case mutation is added.

Verification on 2026-09-30: **63 / 63 backend tests passed**. New tests cover parsing and source locations, mocked OCR output/provenance, classification/extraction contracts, schema/citation checks (including rejecting values without citations), and an invoice PDF fixture through processing persistence using a deterministic fake model adapter, including creation of a pending review task for a low-confidence field. `alembic upgrade head --sql` succeeds through `0005_document_processing_runs`. `git diff --check` passes (Git reports expected Windows line-ending normalization notices).

### Remaining Phase 8 verification and boundary items

- Broaden OCR evaluation across scanned PDFs and varied images; the current SROIE receipt OCR check passed with local Tesseract.
- Evaluate Groq classification and extraction on a larger, varied labeled set. The initial generated invoice, purchase-order, and packing-list set passed 3/3 classifications and 17/17 expected field matches with source citations, but this is only a smoke evaluation and not a general accuracy benchmark.
- Define a process-level reviewer assignment policy; review tasks currently remain unassigned for manual pickup.
- Replace the current inline processing endpoint with durable background dispatch when a real queue worker is implemented; the existing queue service only logs jobs and is not a durable worker.
- Add XLS fixture coverage; the XLS parser is implemented via `xlrd`, but current tests use XLSX fixtures.

---

## Phase 9 — Knowledge / RAG (Core implemented; live validation open) 🟡

*Provider and sample evaluation updated: 2026-10-06 — Cloudflare Workers AI BGE-M3 live embedding and small-corpus checks passed; local PostgreSQL/pgvector migration, extension, dimensions, and HNSW checks passed; relevance-quality benchmarking remains open.*

Phase 9 delivers the full Knowledge / RAG (Retrieval-Augmented Generation) layer. It enables agents and verification processes to retrieve organisation-scoped policy and SOP context through semantic vector search without treating retrieved text as authoritative business state.

### Database — Alembic Migration `0006_knowledge_rag`

| Step | Change |
|---|---|
| 1 | `DELETE FROM knowledge_chunks` — clears stale placeholder data |
| 2 | Replaces `Vector(1536)` with `Vector(1024)` to match BAAI/bge-m3 native output |
| 3 | Adds `organization_id UUID NOT NULL` + FK + `idx_knowledge_chunks_org_id` index (denormalized tenant isolation) |
| 4 | Creates HNSW cosine ANN index `idx_knowledge_chunks_embedding_hnsw` (`m=16`, `ef_construction=64`) |
| 5 | Adds `status VARCHAR(40)`, `chunk_count INTEGER`, `ingested_at TIMESTAMPTZ` to `knowledge_documents` |

Full `downgrade()` path defined. Migration chain: `0001 → 0002 → 0003 → 0004 → 0005 → 0006`.

### Embedding Model — BAAI/bge-m3 via Cloudflare Workers AI API

Model: **`BAAI/bge-m3`** (1024 dimensions, 8192-token context, SOTA multilingual — Arabic + English native support).

Execution: **Cloudflare Workers AI API (remote)**. No local PyTorch, no GPU, no model weight downloads.

| Adapter | Purpose |
|---|---|
| `CloudflareBGEEmbeddingAdapter` | **Configured default API adapter.** Uses Cloudflare Workers AI's OpenAI-compatible embeddings endpoint for `@cf/baai/bge-m3`, validates 1024 dimensions, and normalizes vectors. Uses `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`. |
| `HuggingFaceAPIEmbeddingAdapter` | Optional API adapter using `HUGGINGFACE_HUB_TOKEN`. |
| `BGEM3EmbeddingAdapter` | Alternative local adapter via `sentence-transformers`. Used only when `EMBEDDING_PROVIDER=local`. |
| `FakeEmbeddingAdapter` | Deterministic zero-vector adapter — no HTTP calls in CI. Used for deterministic adapter and gateway tests. |
| `ErrorEmbeddingAdapter` | Always raises `RuntimeError` — tests failure paths. |

Factory `get_embedding_adapter()` reads `EMBEDDING_PROVIDER` from settings and instantiates the correct adapter.

### Configuration Added (`.env` + `config.py`)

| Variable | Value | Purpose |
|---|---|---|
| `EMBEDDING_PROVIDER` | `cloudflare` | Selects Cloudflare Workers AI API adapter |
| `EMBEDDING_MODEL_NAME` | `@cf/baai/bge-m3` | Cloudflare model identifier |
| `CLOUDFLARE_ACCOUNT_ID` | Configured in the local root `.env` | Cloudflare account identifier; secret values are not recorded here |
| `CLOUDFLARE_API_TOKEN` | Configured in the local root `.env` | Bearer token for Workers AI; secret values are not recorded here |
| `GROQ_API_KEY` | Configured in local ignored `.env` files | Primary Groq API key; secret values are not recorded here |
| `GROQ_API_KEY_FALLBACK_1`, `GROQ_API_KEY_FALLBACK_2` | Configured in local ignored `.env` files | Ordered fallback credentials; same-organization keys share quota |
| `LLM7_API_KEY` | Configured in the local ignored root `.env` | LLM7 credential used by the Phase 17 document evaluation; secret value is not recorded |
| `KILO_API_KEY` | Configured in the local ignored root and backend `.env` files | Gateway credential used for the Workflow route and live mismatch document run; secret value is not recorded |

Per-agent provider/model settings are documented in both environment templates. The runtime resolves each role through `DOCUMENT_MODEL_PROVIDER`, `VERIFICATION_MODEL_PROVIDER`, `WORKFLOW_MODEL_PROVIDER`, and `SUPERVISOR_MODEL_PROVIDER`. A live probe found the Groq primary key returned HTTP 401, while the configured fallback key served both the Verification Agent and a Supervisor delegation smoke run (Supervisor returned `ESCALATE`). LLM7 returned HTTP 429 during a later retry; Kilo returned structured JSON and processed the three synthetic mismatch documents. Provider quotas may change, so evaluations use synthetic/non-sensitive data. The provider list used for selection is [open-free-llm-api/awesome-freellm-apis](https://github.com/open-free-llm-api/awesome-freellm-apis).
| `GROQ_DOCUMENT_MODEL` | `qwen/qwen3.8-27b` | Configured Document Agent model |
| `EMBEDDING_DEVICE` | `cpu` | Used only in local mode |

`.env` files are excluded from Git. The local evaluation used the root `.env`; direct backend launches load `backend/.env`, so copy the provider settings there when running the backend outside Docker Compose. Never put secret values in tracked environment templates or this report.

### Domain Implementation

**`TextChunker`** (`domain/knowledge/chunker.py`) — sentence-aware chunking with Arabic and Latin punctuation boundary detection. Configurable `chunk_size`, `overlap`, `min_chunk_length`. Returns `ChunkResult` with `chunk_index`, `char_start`, `char_end`.

**`KnowledgeService`** (`domain/knowledge/service.py`) — full ingestion and retrieval:

| Method | Description |
|---|---|
| `create_source` | Creates org-scoped `KnowledgeSource` |
| `get_sources` / `get_source_by_id` | Org-scoped list and lookup (IDOR guard) |
| `update_source` | Partial update via `model_dump(exclude_unset=True)` |
| `upload_document` | SHA-256 dedup → store → `KnowledgeDocument(status=PENDING)` |
| `ingest_document` | `parse_document_content()` → `TextChunker` → `embed()` → delete old chunks → `db.add_all()` → `status=INGESTED` |
| `delete_document` | Removes storage file + DB row + cascades chunks |
| `search_knowledge` | pgvector `<=>` cosine ANN with `org_id` WHERE; SQLite ORM fallback for tests |

**`KnowledgeDocumentStatus` enum:** `PENDING → INGESTING → INGESTED (or FAILED)`

### API Surface — 10 Endpoints (`domain/knowledge/router.py`)

| Method | Endpoint | Auth |
|---|---|---|
| `POST` | `/api/v1/knowledge/sources` | MANAGER/ADMIN |
| `GET` | `/api/v1/knowledge/sources` | EMPLOYEE+ |
| `GET` | `/api/v1/knowledge/sources/{id}` | EMPLOYEE+ |
| `PATCH` | `/api/v1/knowledge/sources/{id}` | MANAGER/ADMIN |
| `POST` | `/api/v1/knowledge/sources/{id}/documents` | MANAGER/ADMIN |
| `POST` | `/api/v1/knowledge/documents/{id}/ingest` | MANAGER/ADMIN |
| `GET` | `/api/v1/knowledge/sources/{id}/documents` | EMPLOYEE+ |
| `GET` | `/api/v1/knowledge/documents/{id}` | EMPLOYEE+ |
| `DELETE` | `/api/v1/knowledge/documents/{id}` | MANAGER/ADMIN |
| `POST` | `/api/v1/knowledge/search` | EMPLOYEE+ |

`org_id` always from JWT. Cross-org lookups return `404` (IDOR protection). `_require_manager()` enforces RBAC on all write operations.

### Test Suite

| Test File | Tests | Coverage |
|---|---|---|
| `test_knowledge_chunker.py` | 4 | Basic splitting, empty input, Arabic text, overlap + chunk_index |
| `test_knowledge_embedding.py` | 4 | FakeAdapter dimension/output, empty input, ErrorAdapter raises, factory returns correct type |
| `test_knowledge_service.py` | 2 | Source CRUD; full upload → ingest → search pipeline with FakeEmbeddingAdapter |
| `test_knowledge_router.py` | 5 | Source CRUD, RBAC, upload/ingest/read/delete lifecycle, and search via authenticated AsyncClient |
| `test_knowledge_security.py` | 6 | Cross-tenant source/document access, tenant-filtered retrieval, and source-scoped deduplication |
| **Phase 9 total** | **21** | All pass ✅; meets the plan's 19-test minimum |
| **Full backend suite at Phase 9 closeout** | **100 passed, 5 live checks skipped by default** | All non-live tests passed at that milestone |

### External-provider and database verification boundary

On 2026-10-06, the live Cloudflare BGE-M3 adapter embedded five SROIE receipt transcriptions, three DocLayNet text-cell samples, and five targeted receipt queries. The expected receipt ranked first for 4/5 queries and in the top three for 5/5. A four-document generated synthetic policy set retrieved the expected item first for 4/4 paraphrased queries. These are small-sample cosine checks over returned vectors; they are not a statistically robust benchmark and do not exercise PostgreSQL ranking.

The actual `KnowledgeService` upload, parse, chunk, embed, and persistence path ingested the combined SROIE text as 4 chunks and DocLayNet text-cell content as 24 chunks, with both documents reaching `INGESTED` in an isolated SQLite evaluation database. Its SQLite search fallback does not rank by vector distance, so the returned rows do not verify semantic retrieval ordering. The downloaded image files were correctly flagged as requiring OCR; a later live Tesseract check passed against an SROIE receipt. The local public and generated evaluation files are Git-ignored under `data/samples/evaluation`. Repeatable live provider checks are available in `backend/tests/test_live_integrations.py`; the small-corpus hit@k analysis above remains a manually run evaluation, not a statistical benchmark.

At the Phase 9 implementation milestone, the full migration chain generated offline SQL through `0006_knowledge_rag`, but an online `alembic current` check could not connect. Phase 17 later verified the database through migration `0008_human_review_comments`, pgvector 0.8.6, a real ranked PostgreSQL query, and a 12-query labeled retrieval run (recall@3 **1.00**, MRR **0.958**). The later validation is documented in the Phase 17 section below.

---

## Phase 10 — Document Agent ✅

*Provider setup and evaluation updated: 2026-10-06 — Groq Qwen 3.8 27B configured and live-validated through Verifia's Document Agent. Three generated documents passed classification (3/3), expected-field exact match (17/17), and source-citation validation (17/17). This small synthetic evaluation is not a broad accuracy benchmark.*

The Document Agent uses the Phase 8 document-processing service to process one organization-scoped case document/version. It returns structured classification and extracted fields with confidence and source evidence, proposes validated extraction or human review, and records an `AgentExecution` trace. Groq Qwen 3.8 27B is the configured external inference provider through a JSON-mode adapter; Ollama remains optional. The Gemini adapter is retained as unused provider code, but the Document Agent no longer depends on Gemini. The agent does not directly approve a case or mutate authoritative workflow state. A low-confidence processing outcome can create the pending review task through the existing document-processing service; assignment remains outside this phase.

The `search_knowledge` capability is registered in the Tool Gateway, is organization-scoped, and is allowed to configured agent identities. The gateway integration test exercises that capability using a Document Agent identity. The Document Agent's current extraction prompt does not yet consume retrieved policy results; the test verifies gateway access, not retrieval-augmented extraction.

### Phase 10 verification

| Coverage | Result |
|---|---|
| Clean extraction and citation/evidence output | ✅ |
| Low-confidence review proposal and task link | ✅ |
| Failed processing records a failed agent execution | ✅ |
| Zero classification confidence remains zero in the proposal | ✅ |
| Gateway search uses an explicit fake adapter in tests | ✅ |
| Configured embedder failure is recorded as failure, not replaced by fake results | ✅ |
| Full backend regression | ✅ 100 passed, 5 opt-in live integrations skipped by default |
| Live Groq synthetic evaluation | ✅ 3/3 document classes, 17/17 expected field values, 17/17 cited fields |
| Live OCR / database environment | ✅ Tesseract SROIE check and PostgreSQL/pgvector migration/vector checks passed |

### Deferred operational validation

- Expand Groq's labeled evaluation beyond three generated, clean-text examples; test varied layouts, OCR noise, missing fields, and ambiguous values before making a broad accuracy claim.
- The opt-in live integration suite is in `backend/tests/test_live_integrations.py`; the Groq representative synthetic-document check passed. The other live checks remain opt-in and can be run together when external API quota is available.
- Evaluate semantic ranking quality with a relevance-labeled corpus; the live database/vector-dimension and HNSW/migration checks pass, while the SQLite fallback is not a vector-ranking test.
- Implement durable background processing and retries.
- Define reviewer assignment/routing.
- Integrate retrieved policy context into agent prompts when that work is in scope.

---

## Phase 11 — Verification Agent ✅

**Implemented: 2026-10-06.** The previous `/agents/run` Verification branch returned a fixed placeholder proposal. It now dispatches to `VerificationAgent`, which assembles organization-scoped case data, latest document versions and extracted fields, stage-applicable verification definitions, and the tools the Tool Gateway exposes to the actor and agent for that case.

The configured JSON model adapter plans missing information, required checks, and bounded tool calls. The agent validates definition IDs, tool availability, and that each selected verification maps to a `run_verification` call. It executes every call through the Tool Gateway, which continues to enforce process configuration, agent policy, user permissions, schema validation, and execution auditing. The model then returns a structured interpretation of gateway outputs. Tool execution records and deterministic verification statuses/results are returned separately from the model interpretation; the model cannot write authoritative verification results, change case state, or create tasks/approvals.

Missing information, model-identified discrepancies, deterministic FAIL/REVIEW/INCONCLUSIVE/MISMATCH results, missing required documents, and rejected or failed gateway calls produce a human-review proposal. `NOT_APPLICABLE` is preserved as a deterministic outcome without automatically escalating. The agent records success and failure `AgentExecution` traces.

### Phase 11 verification

| Coverage | Result |
|---|---|
| Configured deterministic verification called through Tool Gateway | ✅ |
| Tool and verification executions persisted with agent identity | ✅ |
| Deterministic status preserved separately from model interpretation | ✅ |
| Discrepancy and inconclusive result trigger human review | ✅ |
| Tool unavailable to agent rejected before execution | ✅ |
| Focused Verification Agent tests | ✅ 2 passed |
| Full backend regression | ✅ 5 opt-in live integrations skipped by default |

The real verification definition in the focused test has no linked rules, so the expected deterministic status is `NOT_APPLICABLE`; this validates preservation and review escalation, not a PASS/FAIL business rule. Business-rule PASS/FAIL behavior remains covered by `test_rules_and_verifications.py`. Live model inference for this agent was not part of the automated suite.

## Phase 12 — Workflow Agent ✅

**Implemented: 2026-10-07.** The `/agents/run` endpoint for `AgentType.WORKFLOW` dispatches to `WorkflowAgent`, replacing the previous hard-coded placeholder. The Workflow Agent reads bounded, organization-scoped case context, workflow definition, active stage, available transitions, open tasks, pending approvals, recent verifications, and documents.

The configured JSON model adapter returns structured action proposals (`ALLOWED_ACTIONS`: `PROPOSE_TRANSITION`, `ESCALATE`, `CREATE_TASK`, `REQUEST_APPROVAL`, `RUN_VERIFICATION`). The agent enforces fail-closed validation (`_validate_plan`) on unknown actions and fields, stale or mismatched stage IDs, mismatched action/tool pairs, unknown tool names, and malformed proposals. Transition calls must bind their source stage to the observed stage; verification calls must bind the configured verification ID. Bounded context queries detect overflow and stop before planning rather than silently omitting requirements or workflow facts. Direct Workflow API routes derive actor ID, role, and type from the authenticated user, and tenant-scoped transition execution and rejection auditing keep case reads within the caller's organization.

Consequential stage transitions are executed strictly through the Tool Gateway's registered `transition_workflow` tool, which delegates to `WorkflowService.execute_transition` under organization-scoped isolation. The model output alone cannot mutate business state, and deterministic engine policy remains authoritative (`proposal_state` tracks `PROPOSED`, `EXECUTED`, or `REJECTED`). All executions persist audit traces (`AgentExecution` and `ToolExecution`), and `_redact_context` strips sensitive user prompts from stored context metadata.

### Phase 12 verification

| Coverage | Result |
|---|---|
| Pure transition proposal (`PROPOSE_TRANSITION`) and escalation (`ESCALATE`) | ✅ |
| Controlled tool call execution via Tool Gateway (`CREATE_TASK`, `REQUEST_APPROVAL`) | ✅ |
| Authoritative stage transition through `transition_workflow` → `WorkflowService` | ✅ |
| Invalid proposal rejection (unknown action, stale target stage, unknown tool, malformed output) | ✅ |
| Cross-tenant case isolation (organization_id check on case, service, and gateway) | ✅ |
| Gateway denial or deterministic stale-state yields `proposal_state=REJECTED` | ✅ |
| Context metadata redaction (protects raw user request text) | ✅ |
| Workflow Agent and route authorization regression tests | ✅ 26 passed across `test_workflow_agent.py` and `test_workflow_router_authority.py` |
| Full backend regression after Phase 12–13 hardening | ✅ 144 passed, 5 opt-in live integrations skipped |

---

## Phase 13 — Supervisor Agent ✅

**Implemented and regression-tested: 2026-10-08.** The authenticated `/api/v1/agents/run` endpoint now dispatches `AgentType.SUPERVISOR`. For one request, the Supervisor assembles a bounded organization- and ProcessVersion-scoped case context, validates a strict allowlisted plan, then invokes at most one Document, Verification, and Workflow child sequentially. It returns a structured `CONTINUE`, `ESCALATE`, `COMPLETE`, or `NEEDS_INFORMATION` result. Child executions persist a `parent_execution_id` linking them to the Supervisor trace.

The Supervisor does not directly call tools or mutate business state. Child agents retain their existing authorization and Tool Gateway paths. Invalid/stale plans, child failure, timeout, provider errors, unresolved document-review tasks, pending approvals, and incomplete bounded context stop progression. Verification context now selects the newest result per configured check, and overflow is surfaced so a partial context cannot authorize delegation. No new environment setting or provider was added. The execution limit is one synchronous request; trusted-event progression and explicit replay are implemented by Phase 15, while background workers and cross-process coordination remain open operational work.

### Phase 13 verification

| Coverage | Result |
|---|---|
| Dedicated Model Gateway & provider adapter suite | ✅ 19 passed (`backend/tests/test_model_gateway.py`) |
| External model adapter contract tests | ✅ 8 passed (`backend/tests/test_external_model_adapters.py`) |
| Dedicated Supervisor API/delegation/safety suite | ✅ 16 passed (`backend/tests/test_supervisor_agent.py`) |
| Full backend regression suite | ✅ 163 passed; 5 opt-in live integration checks skipped (0 failures) |
| Python source compilation | ✅ `python -m compileall -q app tests` |
| Alembic migration chain | ✅ `0007_agent_execution_parent` resolves as the current head |
| Live PostgreSQL migration application | Not run in this environment |
| Live model/provider quality | Not run; tests use deterministic fake adapters |

---

## Phase 14 Completion Summary — Model Gateway

The unified **Model Gateway** (`backend/app/infrastructure/llm/`) is now fully implemented, isolated, and integrated across all domain layers with 100% backward-compatibility:

1. **Gateway Abstraction & Contract**:
   - `JsonModelAdapter` protocol with `generate_json` and `generate_response` (returning rich `ModelResponse` containing structured JSON payload and token usage metrics).
   - Structured error hierarchy: `ModelGatewayError`, `ModelAuthenticationError`, `ModelRateLimitError`, `ModelTimeoutError`, `ModelOutputFormatError`, `ModelProviderUnavailableError`.
   - `ModelGateway` provider registry and factory (`get_adapter(provider, model, **kwargs)`).
2. **Provider Adapters**:
   - `GroqJsonAdapter`: Multi-key rotation/failover across `GROQ_API_KEY`, `GROQ_API_KEY_FALLBACK_1`, `GROQ_API_KEY_FALLBACK_2`, exponential backoff on HTTP 408/429/5xx, token metrics from OpenAI-compatible `usage`.
   - `GeminiJsonAdapter`: Native `application/json` schema-enforced generation, dynamic `GEMINI_API_KEY` resolution, transient error retries, `usageMetadata` token extraction.
   - `OllamaJsonAdapter`: Local inference support with schema injection and configurable options.
   - `OpenAICompatibleJsonAdapter`: Generic endpoint adapter for self-hosted / vLLM / LiteLLM / OpenRouter endpoints.
   - `FakeJsonModelAdapter`: Deterministic testing adapter with recorded calls and canned responses.
3. **Domain Layer Compatibility**:
   - `app.domain.documents.intelligence` re-exports `JsonModelAdapter`, `ModelGateway`, and adapters. `DocumentIntelligenceError = ModelGatewayError` ensures zero breaking changes across existing agents and error-handling blocks.
4. **Verification**:
   - 19 new tests in `backend/tests/test_model_gateway.py` + full test suite pass (163 passed, 0 failed).

---

## Phase 15 Completion Summary — Case Orchestrator

The **Case Orchestrator** (`backend/app/domain/cases/orchestrator.py`) is integrated with trusted domain-event producers to drive synchronous case progression. `CASE_ORCHESTRATION_ENABLED` provides a kill switch; the public event-recording endpoint does not dispatch business actions.

1. **Event-Driven Saga Coordination**:
   - `CaseOrchestrator.dispatch_event` handles case creation, document upload/processing, verification completion, task creation/completion, approval decisions, workflow transitions, and case completion using the event names emitted by domain services.
   - Completed and human-wait results persist as `ORCHESTRATION_RESULT` events. Sequential duplicate deliveries are skipped. Failed events are auditable and can be reloaded by ID through `CaseOrchestrator.resume_event` for explicit replay.
   - The implementation dispatches synchronously after trusted events are persisted. It does not claim a background queue, cross-process locking, or atomic compensation across multiple committed domain actions.
2. **Autonomous Progression & HITL Handoff**:
   - High-confidence document extraction triggers deterministic stage-verification and workflow-service checks; the Workflow Engine retains transition authority.
   - Low confidence extraction or failed citations cleanly yield human review tasks (`DOCUMENT_REVIEW`) and set orchestration status to `WAITING_ON_HUMAN`.
   - Completing review tasks and granting required approvals automatically re-evaluates workflow eligibility.
3. **Verification**:
   - 10 dedicated orchestration tests cover event dispatch, failure replay, duplicate delivery, document review, approval, and workflow progression.
   - Full backend regression: **175 passed, 5 opt-in live checks skipped** (0 failures).

---

## Phase 16 Completion Summary — Human-in-the-Loop

Phase 16 completes the backend review loop while keeping the project’s sequential workflow and later frontend boundary intact. Internal users can assign, claim, comment on, inspect, and resolve review tasks through organization-scoped APIs. Human comments persist as immutable rows and can link only evidence records belonging to the task’s case. Human resolutions record the outcome, comment, evidence links, actor, and timestamp; an audit record is written before the trusted event dispatches orchestration. Rejected task resolutions and rejected approvals keep the case in `PENDING_REVIEW`, while completed tasks and approved decisions re-evaluate workflow eligibility through the Phase 15 orchestrator.

The `GET /api/v1/cases/{case_id}/review` endpoint returns a unified, read-only case review bundle with case state, review tasks and comments, approval requests, documents and versions, extracted fields with source citations, processing review reasons, verification results, evidence, discrepancies, and bounded agent recommendations. It does not expose storage references; document content remains behind the authenticated document download endpoint. Manager and administrator roles can assign tasks and decide approvals, and internal task/review endpoints reject customer accounts. Cross-organization records resolve as not found.

Migration `0008_human_review_comments` adds the immutable comment table. Six dedicated tests cover review bundle composition, evidence-link scope validation, task assignment and claim permissions, manager-only approval decisions, rejection holds, audit records, and tenant isolation. The full backend regression reports **179 passed, 5 opt-in live checks skipped**. Ruff checks on the changed Phase 16 source/tests and Python compilation pass; Alembic offline SQL generation reaches migration `0008_human_review_comments` successfully.

## What's Next

Phase 17 evaluated the generic platform across its ordered workstreams: environment, fictional company/data, generic process configuration, provider tools, application-interface journeys, quality measurements, and closeout. ERPNext/Frappe is the self-hosted ERP adapter target; the synthetic Import/Export pack is the primary trade-document corpus; the company jurisdiction remains unset because legal/customs compliance is out of scope; initial thresholds are in `data/phase17_evaluation/acceptance_thresholds.json`; and comparative model selection remains Phase 23. ERPNext requires a country for its accounting fixtures, so the isolated demo uses United States only for ERP initialization. The Phase 17 closeout gates now pass; Phase 18 can begin.

`workflows/import_export/process.json` describes the import-order stages, document requirements, workflow transitions, document schemas, rules, calculations, verification links, and tool allowlist as process data. `backend/app/domain/processes/configuration_loader.py` publishes JSON process definitions through `ProcessService`, and `backend/scripts/load_process_definition.py` exposes it as a CLI operation. Focused loader tests cover configuration validation, version immutability, and Case-to-version linkage; no manual database edits are needed to publish the template.

The local environment is verified: PostgreSQL 16.15, pgvector 0.8.6, migration head `0008_human_review_comments`, local object storage, Tesseract, Cloudflare BGE-M3, LLM7/Groq/Kilo credentials, and ERPNext v16.50. The latest full backend regression passed; **6 opt-in live checks were skipped** by default. The current runtime walkthrough and test details are in `data/phase17_evaluation/reports/runtime_walkthrough_20261009.json` and `environment_20261009.json`.

The synthetic pack contains 10 fictional company cases, 29 trade-document assets, five labeled generated scans, four fictional policies, and 12 labeled retrieval questions. Cloudflare BGE-M3 with PostgreSQL/pgvector achieved recall@3 **1.00** and MRR **0.958** on all 12 policy queries. Tesseract token recall was **0.9761** on five generated scans and **0.8622** on the official DocLayNet ICDAR 2023 20-page development sample; both meet the initial OCR threshold, but DocLayNet is a general layout/OCR diagnostic and not trade-document extraction. The DocLayNet archive (8,484,377 bytes) includes its Apache-2.0 license, is evaluated directly from the archive, and is excluded from Git. Earlier Groq runs each produced only 10 successful documents from 20 attempts (48 fields, 144 citations) because the other calls hit HTTP 429; those partial samples did not pass. A live LLM7 `gpt-oss:20b` evaluation then processed 20 of the full 29-document pack successfully: classification accuracy **1.00**, normalized required-field exact match **0.9712** across **104** labeled fields, and citation validity **1.00** across **300** citation objects. At least 101 exact-match non-null fields carry citations because extraction validation rejects non-null values without citations, exceeding the 30 cited-field minimum. Nine other documents failed (five provider/gateway errors and four output-format errors); the recorded successful sample still meets the configured minimums. Results are in `document_agent_llm7_20261009.json`; retain its failure counts and synthetic-data limitation when interpreting the metrics.

The local ERPNext fixture contains the fictional Northstar company, inventory, warehouse, supplier, and paid/part-paid/unpaid invoices. Organization-scoped ERP/FINANCE integrations use secret references; credentials remain in ignored `.env`. The ERPNext adapter maps provider fields to generic Tool Gateway outputs. Live inventory/payment queries were exercised through the gateway in the clean API case, including available stock and paid invoice status. Adapter tests also cover insufficient stock, other payment states, missing records, provider failures, and authorization errors. The configured process version is `3fe6f747-07d7-4214-976c-82fdba1143b6`.

The clean API journey completed case `CASE-20261008-5814` without direct database edits: three source documents were uploaded and processed, three verification executions and evidence records were persisted, inventory and payment tools returned live ERPNext results through the Tool Gateway, the manager approval was recorded, and the case reached `COMPLETED` with zero open tasks. Its review bundle and 29 case events are accessible through the authenticated application API. The trace summary is saved in `runtime_walkthrough_20261009.json`.

A second mismatch case initially encountered LLM7 rate limits (HTTP 429), safely holding without unsupported advancement. Retried through the authenticated API with Kilo Dots3 Note Preview, all three documents classified and extracted successfully (packing list 7 fields, invoice 6, purchase order 7). The configured deterministic verification returned `FAIL` with one evidence record; the case entered `HUMAN_REVIEW`. An employee completed an evidence-linked discrepancy task, then the manager rejected shipment; the case remains `PENDING_REVIEW` at `MANAGER_APPROVAL`, as required for a rejected decision. The clean case separately demonstrates approved completion. Customer tool listing returned zero tools, a direct unauthorized tool call returned HTTP 403, and an invalid backward workflow transition returned HTTP 400. These checks prove the specific observed controls, not zero violations over a ten-scenario evaluation set.

The API, PostgreSQL, Redis, object storage, Tesseract, and ERPNext services were healthy during the application-interface run. Migrations are at `0008_human_review_comments`. The ERPNext-required United States setting is limited to isolated accounting initialization and does not represent a jurisdiction-specific policy evaluation.

An earlier process revision matched **49/49** deterministic rule decisions; after adding configured inventory and payment checks, the current rules match **69/69** applicable decisions across all ten scenarios. These rule results isolate deterministic logic from extraction and provider errors. The Document Agent sample-size/quality gate passes on LLM7 at the configured minima. DocILE research access remains unavailable; DocLayNet supplies only a licensed general OCR/layout diagnostic. The synthetic scans and 20-page DocLayNet subset do not establish performance on varied trade documents. Provider throttling still affects repeatability: LLM7 returned HTTP 429 during a recent run, and the Groq primary key returned HTTP 401 while its fallback served one Verification Agent run. These model routes are configuration baselines, not comparative winners.

Verification details: the latest full backend regression passed **209 tests, skipped six opt-in live checks, and had zero failures**; the repeatable Windows command is `python scripts/run_backend_regression_windows.py`. The runner handles temp-directory ACLs and excludes inaccessible stale `tests/_pytest_phase15` data without mocking application behavior. The current configured rule evaluator matched **69/69** applicable decisions across ten scenarios. The ten-scenario workflow/security report matched all expected outcomes and rejected all ten customer tool calls (403) and invalid transitions (400). The DocLayNet OCR command is `python -m scripts.evaluate_phase17_ocr --doclaynet-zip ../data/phase17_evaluation/external/doclaynet_dev_public.zip --output ../data/phase17_evaluation/reports/doclaynet_ocr_20261009.json`; result **0.8622 token recall over 20 pages**, meeting the initial OCR threshold. Synthetic OCR remains **0.9761/5 pages**, and policy retrieval remains **recall@3 1.00, MRR 0.958/12 queries**. Partial Groq results and runtime traces are recorded with limitations; Phase 17 closeout is complete for the defined scope.

At the time of this Phase 17 closeout, **Phase 18 — Frontend** was eligible to begin. The discrepancy/review rejection path and clean approval/completion path had both been exercised, and all ten scenario workflow/security gates passed. This does not constitute comparative model selection, which remains planned for Phase 23.

### Open checklist items carried forward

| Open item | Why it remains open |
|---|---|
| Production adapter coverage beyond Phase 17's ERPNext sandbox | Phase 17 has live ERPNext inventory/payment adapters; production-grade connectors for other providers and customer lookup are still future integration work. |
| Complete tenant isolation across all APIs | Case creation, WorkflowService, and Tool Gateway enforce org scope; route-by-route authorization audit belongs to the Security phase. |
| Safe tenant/user provisioning and production configuration | Public registration and development defaults still require hardening before deployment; controlled provisioning and fail-closed production settings are planned for Phases 19–20. |
| Prove a second process works without application-specific code | Platform is generic; dedicated generalization test is Phase 24. |
| Broader live OCR evaluation (Phase 8) | Tesseract works on the local SROIE sample, but scanned-PDF coverage and a varied accuracy set remain open. |

### Expert improvement priorities for the remaining plan

The Phase 17 closeout established the defined synthetic and local-fixture baseline, not production readiness. At that time safe account provisioning was the top hardening priority; it has since been implemented and is recorded in the Phase 19 closeout below. Phase 20 remains open: it should reject weak/default secrets, debug mode, and wildcard CORS in production, and define upload and external-provider data controls.

The remaining sequence is reflected in the checklist: Phase 20 production security, Phase 21 durable event delivery, retries, idempotency, replay and dependency-aware readiness; Phase 22 CI and failure/authorization coverage; Phase 23 per-agent model comparison; and Phase 24 a second process without process-specific application branches. The current role-specific providers are evaluation baselines, not selected winners. Synthetic data remains useful as a controlled baseline, but it cannot establish generalization to real trade documents.

## Phase 17 Closeout — 2026-10-09

Phase 17 is complete for its defined near-real evaluation scope. The final workflow/security evaluator is repeatable at `backend/scripts/evaluate_phase17_workflows.py`; its report is `data/phase17_evaluation/reports/workflow_security_20261009.json`. It ran all ten labeled synthetic Import/Export scenarios against published ProcessVersion `6a86e409-87bb-42fa-8931-ef2573b4ba57` through authenticated HTTP application interfaces. All **10/10 expected outcomes matched**: one completed clean shipment, six verification failures held at `HUMAN_REVIEW`, one missing-packing-list case held at `DOCUMENT_REVIEW`, one low-quality scan deliberately held for operator inspection, and one manager rejection held at `MANAGER_APPROVAL`. For each scenario, the invalid workflow transition returned HTTP 400 and the customer tool attempt returned HTTP 403: **10/10 rejections in both checks, zero accepted invalid transitions, and zero successful unauthorized tool executions**. Inventory and payment outcomes came from the local synthetic ERPNext fixture; labeled extraction fields were supplied through the document API to isolate configured workflow behavior from live Document Agent variability.

After linking the inventory and payment rules into the published process, the deterministic rule evaluation now matches **69/69 applicable decisions across ten scenarios and seven configured checks** (`rule_diagnostics_20261009.json`); missing-document checks are handled by the workflow prerequisite gate and excluded from this rule denominator.

The missing-document negative path exposed an API error response serialization defect: UUIDs in validation violation records were not JSON serializable. The workflow route now serializes violation models in JSON mode. The rerun verified the missing-document transition returns a controlled 400 and all ten cases pass. The data generator's warehouse label now matches the ERPNext fixture (`Main Warehouse - NDI`). The low-quality scan outcome is a deliberate human hold and does not claim automatic OCR-triggered workflow behavior; OCR metrics remain a separate evaluation. All results use fictional data and a local test ERP; they do not establish production readiness, jurisdiction-specific compliance, or broad real-world document generalization. Provider-specific live tests remain opt-in and are counted among the six regression skips.

The API serialization fix and corrected data assertion both pass the complete backend regression: **209 passed, 6 skipped, 0 failures** using `python scripts/run_backend_regression_windows.py`. The six skips are explicitly opt-in live provider checks (`VERIFIA_RUN_LIVE_TESTS=1`), not hidden failures. Ruff passes for the changed workflow router, verification service, evaluation scripts, and related tests. A single upstream Starlette `TestClient` deprecation warning remains; it does not fail the suite. Phase 18 (Frontend) may begin after this closeout, but its implementation has not started. Comparative model selection remains Phase 23, and broader generalization remains Phase 24.

## Phase 18 Closeout — 2026-10-10

Implemented the first authenticated internal operations frontend in `frontend/`: a responsive React/TypeScript SPA with login/session restoration, overview, case register and published-process intake, case workspace, document upload/process/download, verification/evidence/history, assigned tasks, manager approvals, and explicitly confirmed Supervisor recommendations. It uses the existing `/api/v1` contracts, bearer authentication, per-identity query keys, and server-confirmed statuses. Customer case listing and self-registration remain unavailable because the current backend does not provide participant-scoped case reads or safe public provisioning.

The frontend includes a production Vite build, Nginx static serving and same-origin API proxy, Compose service, local Vite proxy, design-system reference, API/capability map, and updated run instructions. It keeps provider credentials out of browser settings and does not treat agent recommendations as decisions.

Verification after a clean lockfile install:

- `npm run typecheck` — passed.
- `npm run lint` — passed with ESLint 10.12.0.
- `npm run test` — **13 passed across 6 files** (session restore/login/logout/cache clearing, role/customer route boundaries, API bearer and 401 behavior, multipart uploads, case search/pagination, status mapping, and approval comments/decisions).
- `npm run build` — passed; Vite 8.3.4 produced the static production bundle.
- `docker compose config -q` — passed.
- Browser preview — login rendered at the default desktop viewport and a 390 px viewport; no browser console errors were reported.

At the Phase 18 closeout, the Docker CLI could not reach the Docker Desktop Linux engine, so the frontend image was not built and Compose services were not started. A live authenticated frontend-to-backend E2E run was not possible, and the backend runner did not produce a result at that time. The frontend checks established client behavior and compilation, not backend authorization or production readiness. Phase 19 has since been implemented and is closed below; Phase 20 remains open.

## Phase 19 Closeout — 2026-10-10

Implemented controlled identity provisioning and the corresponding frontend administration flow. Anonymous registration is retired. A live organization ADMIN can list and provision users only within their organization; the server chooses organization and active state, rejects ADMIN assignment and extra fields, normalizes email identity, and writes safe audit metadata atomically with account creation. Login and `/auth/me` reject inactive organizations, inactive accounts, malformed subjects, stale identity claims, and ambiguous legacy email matches. Migration `0009_global_user_email_identity` adds case-insensitive global email uniqueness with a duplicate preflight. The local admin bootstrap is development-only, prompts for an email and a user-chosen password, refuses to reset an existing account, and does not print the password.

Verification:

- Focused backend auth, provisioning, and bootstrap tests: **20 passed**. Ruff passed for the modified security modules, migration, bootstrap script, and focused tests.
- Full backend regression: one unrelated failure because ignored local file `data/phase17_evaluation/acceptance_thresholds.json` is missing; six opt-in provider tests skipped; remaining tests passed. The prior clean full regression was 209 passed, 6 skipped.
- Frontend: **17 tests passed across 7 files**; typecheck, lint, and production build passed. Browser preview showed the login page down to 304 px without horizontal overflow.
- Alembic head and `alembic upgrade head --sql` passed through migration 0009. The migration was not applied to PostgreSQL because Docker Desktop's Linux engine was inaccessible (`npipe:////./pipe/dockerDesktopLinuxEngine`); Compose configuration itself passed.
- `npm audit --omit=dev` could not reach `registry.npmjs.org` because DNS resolution returned `ENOTFOUND`. No dependency-audit result is claimed.
- No live authenticated frontend-to-backend flow or production container check was possible in this environment.

Phase 20 remains next: production startup defaults, CORS/API-doc exposure, upload policy, and provider data handling. See the [Phase 20 implementation plan](phase20-production-security-implementation-plan.md). Session storage of bearer tokens and runtime validation of production Nginx headers remain documented security limitations.

## Project audit follow-up — 2026-10-10

This follow-up supersedes current-status statements in the earlier Phase 18/19 closeouts while preserving their historical results.

- Phase 18 now includes participant-scoped customer case creation, list/detail, document request status, uploads, and PDF/image previews. Internal employee PDF/image preview is also implemented. Automated frontend verification: **21 passed across 10 files**; typecheck, lint, and build passed.
- Phase 19 route checks now cover customer/internal resource access, task and approval roles, workflow/rules/verifications/events/agents, and tenant-scoped process/document access. Logout and password change/reset revoke access tokens through migration `0010_user_token_version`; logout and password audit events contain no credential material.
- The first-admin script now requires a development environment, a user-chosen password of at least 15 characters, hidden entry and confirmation, and does not accept password command-line arguments or reset accounts.
- Focused auth/bootstrap backend tests: **22 passed**. Full backend regression: **232 passed, 1 failed, 6 skipped**. The sole failure requires the ignored `data/phase17_evaluation/acceptance_thresholds.json`, which is absent from the checkout and unavailable to the user. Its values were not reconstructed or guessed. The historical Phase 17 results remain historical; the acceptance gate is currently not reproducible.
- The local Python runtime has bcrypt 5 while `backend/requirements.txt` pins `<4.1`; backend tests used a process-only compatibility shim, with no package changes. The pinned dependency should be installed in the project virtual environment for an unshimmed run.
- Alembic head is `0010_user_token_version`; `python -m alembic upgrade head --sql` generated SQL through 0010. `docker compose config -q` passed. PostgreSQL application, Docker runtime, and authenticated browser-to-API E2E were not verified because the Docker engine was unavailable and loopback access was blocked by the Windows sandbox/browser.
- Project-wide Ruff is not clean: `ruff check app tests scripts` reported **1,303 findings** after import sorting and unused-import cleanup in touched modules. Findings include legacy typing, import-order, and FastAPI dependency-rule findings; no mass auto-fix was applied.
- Phase 17 acceptance, PostgreSQL migration application, and live Phase 18/19 E2E remain **BLOCKED/PARTIAL**, not complete. See [the dated project audit](project-audit-2026-10-10.md) for requirement IDs, phase-by-phase status, test evidence, and remaining work.

## Phase 20 Implementation Update — 2026-10-11

**Status: In progress; no release verification has been performed for this slice.**

- Production and staging configuration now rejects weak/default JWT secrets, debug mode, non-HTTPS or wildcard CORS origins, missing PostgreSQL URLs, and development database credentials.
- API docs default off in production; CORS is bearer-token-oriented with exact configured origins, no credential allowance, and explicit methods/headers.
- External model and embedding routes are denied by default outside development/test. Production allowlisting pins the provider, model, and HTTPS endpoint origin together. No route is approved for business data; terms and payload-level data review remain outstanding.
- All document uploads are disabled in production by default because no malware scanner is installed. Explicitly enabling unscanned uploads is a deployment risk acceptance, not a security control.
- Knowledge upload bytes are bounded before application buffering and use the common filename, size, declared MIME, and file-signature checks. A request-body middleware also caps incoming bodies before multipart parsing.
- PostgreSQL, Redis, and backend host ports in the local Compose file now bind to loopback; Compose also requires an explicit database password. The frontend remains the host-published web edge.
- A separate production Compose baseline connects to private PostgreSQL and TLS-enabled Redis services, keeps the backend off host-published ports, binds the frontend to loopback for a host TLS proxy, and persists uploads in a named volume. Its production environment template contains placeholders only.
- Secret-safe provider error handling was tightened to avoid returning raw provider response bodies, request URLs, prompts, or model-output snippets in errors.
- The Phase 20 HTTP security suite and local Docker frontend/backend health path have been verified. Production-topology verification and provider/storage reviews remain outstanding. See the [Phase 20 plan](phase20-production-security-implementation-plan.md); the [provider review register](external-model-provider-review.md) records approval gaps.

## Phase 20–21 Audit and Integration Update — 2026-10-11

This update supersedes earlier statements that Phase 21 is still planned. At audit start, the repository had no standalone Phase 21 plan. Its scope was derived from the operations roadmap's event guarantees and the implementation checklist's Events & Auditability section. The linked plan and traceability matrix record that derivation.

### Phase 20 — remains partial

- The production security implementation and the 9/9 Phase 20 HTTP security E2E remain in place. In this run, frontend typecheck, lint, all 21 tests across 10 files, and production build passed.
- Local Compose configuration, loopback service bindings, backend readiness, and the frontend Nginx health proxy were exercised. This does not close production TLS/managed-service topology, storage-volume permissions and download handling, malware scanning, or provider contract/data review. No provider is approved for business data.
- The historical Phase 17 threshold file remains absent. The user confirmed it is unavailable; no thresholds were recreated.

### Phase 21 — durable event delivery and readiness

- Added `event_deliveries` and migration `0011_durable_event_deliveries`; Alembic reports that revision as head in the running PostgreSQL container. The additive migration preserved existing user rows and prior events.
- Event writes now use `EventService.add_event` or `emit_event`, including transactional document-processing events and Supervisor lifecycle records. Trusted event and outbox writes share their caller's database transaction. Verification-completion events include the validated tool-execution IDs used for the result.
- Added a dedicated PostgreSQL-backed worker, multi-worker row claims, expiring leases, stale-claim fencing, bounded retry/backoff, dead-lettering after five attempts, and controlled trusted-event replay. `scripts/replay_event_delivery.py` requires database operator access and does not print payloads.
- Fixed worker startup's eager-import cycle by making `app.events` package exports lazy. Worker SQL echo is disabled so idle polling does not flood its logs.
- With two Compose workers running, a fresh event completed on attempt 1 with one orchestration result. A second live PostgreSQL E2E started from a persisted expired processing lease; a worker reclaimed it, completed on attempt 2, emitted one result, and the script removed only its temporary organization.
- `/livez` returned alive; `/readyz` returned ready with PostgreSQL and Redis connected; Nginx `/health/backend` forwarded HTTP 200. The isolated authenticated API journey now covers Case creation through completion, including document processing, verification, manager approval, event history, and persisted audit state; it uses deterministic model behavior and does not verify ERPNext.

### Verification summary

- Full backend suite: **260 collected; 253 passed, 0 failed, 7 skipped, 1 deprecation warning in 70.93s** with `python scripts/run_backend_regression_windows.py` from `backend/`. Six skips are opt-in external-provider integrations. The seventh skip is an explicit BLOCKED Phase 17 threshold gate because the ignored `data/phase17_evaluation/acceptance_thresholds.json` is absent; a separate regression verifies that missing-file condition is reported explicitly.
- The host Python installation has bcrypt 5.0.0 while `backend/requirements.txt` pins `<4.1`. A process-only shim matching the pinned bcrypt 4.x truncation behavior let the suite exercise the remaining tests; no package or application code changed for that shim. Without it, host bcrypt incompatibility causes eight additional test failures.
- Focused backend checks passed for delivery, readiness, orchestration, Phase 20 HTTP security, database models, and the isolated Case journey. `compileall`, replay CLI help, local Compose config, both live delivery E2Es, and migration-head verification passed. The five touched Python files pass Ruff, as does the F821 undefined-name check; project-wide Ruff and mypy results are in the final closeout.
- Production Compose was not deployed: no populated `.env.production` or provisioned external PostgreSQL/TLS Redis is available. The app Dockerfile and production Compose declare UID/GID 10001, but an image build was stopped during very large unbounded dependency resolution; production image and named-volume permissions remain unverified. Production TLS, storage, and provider checks remain open.
- The historical 10-scenario evaluator was not run: its read-only preflight found no active EMPLOYEE account in the current database, ERPNext is not running in Compose, and it persists synthetic Cases. No shared-database users or Cases were created. The new isolated API journey uses SQLite and disposable local identities instead.

## Prior Phase 20–21 closeout — 2026-10-11 (superseded)

This section supersedes earlier current-state totals and open journey statements in the prior audit update. Older phase-specific results remain historical.

- The Phase 17 threshold file is ignored, absent, and unavailable from the user. It is not committed or generated from documented synthetic data; values cannot be reconstructed from evaluation scores. The test now preserves all original gate assertions when the file exists, and explicitly reports BLOCKED when it does not. The full runner therefore has no test failures, while the historical threshold acceptance itself remains BLOCKED.
- The isolated Case API test passed on its own and in the 260-test regression. It asserts authenticated employee/manager/customer paths, upload and processing persistence, verification gating, guarded workflow transitions, approval decision authorization, Case history, audit history, and final persisted completion. It does not call ERPNext or a live model provider.
- With two running Compose workers, a fresh outbox delivery passed with one result on attempt 1; an expired lease was reclaimed and completed with one result on attempt 2. Both probes removed only their temporary organization. All six local Compose containers remained running; API/frontend/PostgreSQL/Redis reported healthy, and PostgreSQL remained at Alembic head `0011_durable_event_deliveries`.
- Phase 20 remains PARTIAL: production TLS/topology, external managed service connectivity, production image build, existing-volume permissions, malware scanning, and provider approval have not been verified. Phase 21's documented internal event and Case lifecycle requirements are verified locally; real ERPNext integration remains unverified.
- See the [final closeout report](phase20-21-final-closeout.md) for the complete acceptance matrices, exact commands, and evidence boundaries.

## Official compliance audit update — 2026-10-11

- The complete backend regression passed **262 tests, skipped 7, failed 0** (269 collected) using an in-memory bcrypt 4.x compatibility shim for the host's bcrypt 5.0.0. Six skips are opt-in provider checks; one is the explicitly blocked Phase 17 threshold gate.
- The Phase 20 HTTP security suite and authenticated Case journey pass. The event history now uses `DOCUMENT_PROCESSED`, `TASK_COMPLETED`, and `APPROVAL_GRANTED`/`APPROVAL_REJECTED`; eight injected event-write failures confirm Case, task, and approval state rolls back.
- Phase 20 remains **PARTIAL** because provider terms/data-class approval is missing. Phase 21 is **PARTIAL**: automated tests pass, while a current live Docker worker/readiness recheck is pending because Docker's named pipe was inaccessible during this audit. The Phase 17 threshold gate remains **BLOCKED**.
- The authoritative requirement inventory is [the official matrix](phase20-21-official-compliance-matrix.md); implementation and evidence are in [the A–K audit](phase20-21-official-compliance-audit.md). The older traceability/closeout files are marked superseded.

See also the [Phase 21 plan](phase21-durable-events-implementation-plan.md), [Phase 20 plan](phase20-production-security-implementation-plan.md), [external-provider register](external-model-provider-review.md), and [local run guide](RUNNING_THE_PROJECT.md).

## Phase 22 Implementation Update — 2026-10-12

Phase 22's authoritative objective is **Repeatable quality gates**, listed in `Documentation/04-operations-and-roadmap.md` §33 and detailed in section 22 of the implementation checklist. The living [Phase 22 implementation plan](phase22-implementation-plan.md) maps 13 requirements to tasks, tests, acceptance criteria, and evidence.

- Added `.github/workflows/quality-gates.yml`: backend deterministic regression and critical lint, disposable pgvector migration assertions and two-worker recovery probes, and a frontend clean-install/test/typecheck/lint/build job. The workflow uses standard action versions (`checkout@v4`, `setup-python@v5`, `setup-node@v4`), triggers on pull requests, pushes to `main`, and manual dispatch.
- Fixed a bcrypt compatibility defect in `backend/app/security/service.py` where bcrypt 5.0.0 on the host broke passlib's internal probe. The service now uses direct `bcrypt.hashpw`/`bcrypt.checkpw` calls, ensuring compatibility across both bcrypt 4.x (CI) and 5.x (local host) with no shim needed.
- Full backend regression passed: **268 tests passed, 7 skipped, 0 failed** in 80.42 seconds. Six skips are opt-in live integrations; one explicitly blocks Phase 17 acceptance because the original ignored threshold file is unavailable. Critical Python lint `python -m ruff check --isolated --select E9,F821 app tests scripts` passed cleanly.
- Frontend verification passed completely: 21 tests across 10 files (`npm test -- --run`), TypeScript compilation (`npm run typecheck`), ESLint (`npm run lint`), and production build (`npm run build`).
- Live Docker probes confirmed passing on 2026-10-12 against running Compose PostgreSQL (port 5433) and event workers:
  1. `python scripts/phase21_worker_e2e.py --verify-stale-claim-fencing` passed.
  2. `python scripts/phase21_worker_e2e.py --timeout 30` passed (normal delivery with 2 workers, attempts=1, duplicate_results=0).
  3. `python scripts/phase21_worker_e2e.py --timeout 30 --simulate-expired-lease` passed (expired-lease recovery, attempts=2, duplicate_results=0).
  4. Alembic migration head assertion confirmed at `0011_durable_event_deliveries`.
- **Status: IN PROGRESS.** Requirements R003–R013 are verified complete locally. R001 and R002 are implemented in `.github/workflows/quality-gates.yml` and require a commit and push to GitHub to record a hosted GitHub Actions run.

## Phase 23 Implementation Update — 2026-10-12

Phase 23's official objective is evidence-based per-agent model selection followed by a separate system-level evaluation. The [living Phase 23 implementation plan](phase23-implementation-plan.md) tracks the checklist requirements, evidence, and remaining gates.

- Added `backend/evaluation/phase23/dataset_v1.json`, a tracked v1 manifest with four fictional synthetic cases for each of Document, Verification, Workflow, and Supervisor.
- Added `backend/scripts/evaluate_phase23_agent.py` with fixed benchmark prompts/schemas, separate task-specific scorers, dataset/prompt/scorer fingerprints, provider/model identity, per-case call status and safe error class, latency, optional provider usage, repeated-run variance, and reports that exclude prompts, source text, raw responses, and secrets. Generated reports under `data/phase23_evaluation/reports/` are Git-ignored.
- Added scorer/harness tests in `backend/tests/test_phase23_evaluation.py`. Focused Phase 23 tests passed **8/8**. Critical Ruff (`E9,F821`) and Python byte-compilation passed.
- Ran the CLI with the fake provider for all four agents: four cases × two runs each, **32 successful fake calls and zero failed calls**. The fake model's low task scores are only stub-output behavior and do not measure model quality or support route selection.
- No live provider calls were sent: no Groq, LLM7, Kilo, or Gemini credentials were configured, and the local Ollama endpoint was unreachable during inspection. The user authorized bounded external calls for synthetic cases only; there is still no identified licensed/explicitly authorized representative business-document corpus or provider/data approval for real business documents.
- **Status: IN PROGRESS.** Comparative per-agent provider evidence and recommendations, candidate-model behavior on integrated Supervisor child-trace/recovery paths, repeated system-level evaluation, and representative authorized-document evidence remain open. Existing route defaults are not winners. Phase 22 evidence above is historical and independent of this Phase 23 work.

**Follow-up preflight — 2026-10-12:** all four agent runtime suites passed **51/51** deterministic integration tests (`test_document_agent.py`, `test_verification_agent.py`, and `test_workflow_agent.py` passed 35/35; `test_supervisor_agent.py` passed 16/16). Combined with `test_phase23_evaluation.py` (8/8), **59/59** agent runtime and evaluation tests passed. Critical Ruff (`E9,F821`) and Python byte-compilation passed cleanly. Four-agent fake CLI smoke runs (32 calls) completed with zero failed calls. Provider-key presence remains false for Groq, LLM7, Kilo, and Gemini; loopback Ollama remains unreachable; Docker Desktop named pipe remains inaccessible. No representative business corpus has been authorized. Live comparisons, system-level benchmarking, and authorized-document evaluations remain open and blocked by environment prerequisites.



## Phases 20-24 audit and Phase 24 implementation update - 2026-10-12

This update supersedes earlier current-status summaries where their evidence is older. Historical records remain dated and are not presented as fresh runs.

- Added the declarative Insurance Claim process at workflows/insurance_claim/process.json with the official six stages, process-scoped claim document schemas, a deterministic claim-reference verification, requirements, approvals, and a registered Tool Gateway allowlist. No production insurance branch or database migration was added.
- Added backend/tests/test_phase24_generalization.py. The synthetic authenticated API journey creates a Case bound to the published claim version; uploads and processes fictional PDFs; executes required-document checking and claim verification; completes a financial-review task and manager approval; reaches Payment; and checks persisted Case events.
- Phase 24 and process-loader focused tests passed 6/6. The final full backend regression passed 277 tests, skipped 7, failed 0 in 49.14 seconds. Six skips are opt-in external integrations; one is the blocked Phase 17 evaluation gate because the original ignored threshold file is unavailable. Critical Python lint E9,F821 passed.
- Phase 20 remains partial: provider retention/data-class approval, field minimization, production TLS/topology/storage permissions, and upload scanning evidence remain outstanding. The full deterministic backend suite revalidated local controls.
- Phase 21 internal event and authenticated Case lifecycle tests pass. The Phase 22 plan records the empty/prior-schema PostgreSQL upgrades, stale-claim fencing, two-worker delivery, and expired-lease recovery probes passing on 2026-10-12. Docker Desktop pipe was missing in this audit, so no fresh container check is claimed; real ERPNext remains unverified.
- Phase 22 remains in progress. The workflow and deterministic/local gates are implemented, and recorded PostgreSQL probes passed; hosted GitHub Actions evidence was not observable here and remains pending.
- Phase 23 remains in progress. Synthetic harness/runtime tests pass, but all checked provider-key settings are absent, so no live comparisons were sent. No authorized representative business-document corpus or provider/data approval is recorded; no model route recommendation is made.
- Phase 24 local acceptance passes. This does not establish live insurer integration, production insurance readiness, provider approval, or real-claim data authorization.
- No commit or push was made. See the Phases 20-24 audit, Phase 24 implementation plan, Phase 22 plan, and local run guide.

## Final verification and Phase 20–24 closure review — 2026-10-12

This follow-up supersedes the preceding same-day test-duration and current-working-tree statements while preserving their dated results as historical evidence. It began on `main` at `fc4a77b2d1dc1b0218b4fbf0981a1e20bded6af8`, equal to `origin/main`, with a clean working tree. The earlier “No commit or push was made” note describes the state at the end of the original audit; this follow-up made no commit or push.

- Fresh project-venv results on Windows/Python 3.14.0: Phase 24 plus process-loader **6 passed**; focused authenticated Case/event/authorization/upload/readiness/verification/gateway group **123 passed**; full deterministic backend regression **277 passed, 7 skipped, 0 failed** in **69.05 seconds**; critical Ruff (`E9,F821`) passed. Six skipped tests require opt-in live integrations; one is the blocked Phase 17 gate because its original threshold file is unavailable.
- The test session initially stalled in restricted mode when Windows asyncio tried to create a local loopback socket pair; the faulthandler identified `asyncio.proactor_events._make_self_pipe`. The same suites completed after narrowly permitting local loopback. This was an environment limitation, not a test failure.
- `docker compose ps` exited 1 because the Docker Linux-engine named pipe was unavailable. No fresh PostgreSQL multi-worker probe was run; prior passing migration/fencing/two-worker/expired-lease probes remain historical. No hosted Actions result tied to this SHA was observable (`gh` is not installed and page fetches returned cache misses).
- No provider call or real customer/business document was used. Phase 20 remains PARTIAL for provider/data approval and production evidence; Phase 21 remains PARTIAL for fresh PostgreSQL/live readiness evidence; Phase 22 remains PARTIAL for hosted Actions and fresh worker evidence; Phase 23 remains PARTIAL for live/system/corpus requirements; Phase 24 is VERIFIED for the synthetic local acceptance. Phase 17 remains BLOCKED and its thresholds were not reconstructed.
- The active audit corrects the stale Phase 21 task link to `P21-OFFICIAL-010` and contains the per-requirement status matrix and exact commands in [the Phases 20–24 audit plan](phases20-24-comprehensive-audit-plan.md). Documentation-only follow-up edits are left uncommitted for review.

## CI runner disk-space remediation — 2026-10-13

The hosted Phase 22 backend job failed at dependency installation with `OSError: [Errno 28] No space left on device`; the frontend job passed. The standard requirements were installing the optional local Sentence-Transformers adapter, which brought in PyTorch and NVIDIA CUDA packages on the CPU-only runner. The local embedding runtime is now isolated in `backend/requirements-local-embeddings.txt`; normal backend/CI requirements omit it, and the workflow uses `--no-cache-dir` without pip caching. The full local backend regression passed **277 tests, skipped 7, failed 0** after the change; critical Ruff passed.

The remediation is committed on `main` and `origin/main` as `61da349`. The post-fix hosted Actions result has not been observed in this review, so Phase 22's hosted gate remains open until both backend and frontend jobs are confirmed green for this commit. The earlier statement that the fix was uncommitted is superseded.

## Whole-project remaining work — 2026-10-13

This section summarizes the current project state and next actions across all phases. It supersedes older current-state statements where new evidence is available; dated test results remain historical evidence for the dates shown. At the start of this update, `main` and `origin/main` both pointed to `61da349` and the working tree was clean.

### Phase overview

| Phase(s) | Current status | Remaining work |
|---|---|---|
| 1–6 | Core repository, database, API, workflow, rules, and Tool Gateway are implemented. | No major phase-level implementation gap is currently recorded. |
| 7 | Local storage, tenant-scoped uploads/downloads, metadata, and versions are implemented. | Deploy and verify a cloud storage adapter, production permissions, retention, backup, and restore behavior. |
| 8 | Core parsing, OCR, classification/extraction, and evidence persistence are implemented. | Evaluate varied external-document quality and make background processing durable, observable, and recoverable. |
| 9 | Organization-scoped retrieval and pgvector integration are implemented and checked on small samples. | Run a broader retrieval-quality evaluation on a representative, authorized corpus. |
| 10–16 | Document, Verification, Workflow, and Supervisor agents, Model Gateway, orchestration, and human review are implemented and regression-tested. | Live model quality is not established; external side effects require downstream idempotency because event delivery is at least once. |
| 17 | Historical synthetic evaluation results are recorded; current acceptance is **BLOCKED / not reproducible**. | Restore the original ignored `data/phase17_evaluation/acceptance_thresholds.json`, or approve a new versioned threshold set and rerun the gate. Do not infer or recreate the missing values. |
| 18 | Customer and internal frontend flows are implemented; frontend tests, typecheck, lint, and build have passed. | Run and record a full authenticated browser-to-API business journey, including upload, processing, review, approval, and tenant/role boundaries. |
| 19 | Identity and organization-scoped provisioning are implemented and backend-regression-tested. | Verify admin provisioning and login through a fresh authenticated end-to-end flow against the current database schema. |
| 20 | **PARTIAL.** Local security controls and regression tests pass. | Obtain provider/data-owner approval; implement and test data minimization/redaction; verify production TLS, managed services, storage permissions, scanning, secrets, and backup/restore. |
| 21 | Internal event lifecycle and fresh local Docker/PostgreSQL worker checks pass. | Add/record a live PostgreSQL transaction-rollback probe and verify real ERPNext integration. Preserve idempotency for any external business action. |
| 22 | **IN PROGRESS.** Deterministic local gates pass; dependency-install disk exhaustion was remediated in `61da349`. | Observe and record the post-fix hosted GitHub Actions run for `61da349`; both backend and frontend jobs must pass. |
| 23 | **IN PROGRESS.** Synthetic four-agent harness and tests are implemented. | Run controlled per-agent model comparisons, repeated system-level evaluation, and an authorized representative-document evaluation after provider/data approval. |
| 24 | **VERIFIED locally for synthetic acceptance.** The Insurance Claim flow uses the shared authenticated application boundaries. | No additional synthetic acceptance item is recorded; real insurer integration and production readiness remain unverified. |
| 25–26 | Planned final documentation and demonstration. | Complete architecture/data-flow diagrams, deployment and model-route notes, demo fixtures and accounts, clean/discrepancy scenarios, rehearsal, evidence, and fallback recording. |

### Fresh verification recorded on 2026-10-13

- Environment: Windows host with Docker Desktop 29.8.2 and the project Compose stack running. The database reported Alembic head `0011_durable_event_deliveries`; backend `/livez` and `/readyz` each returned HTTP 200.
- PostgreSQL worker probes all passed: `python scripts/phase21_worker_e2e.py --verify-stale-claim-fencing`; `python scripts/phase21_worker_e2e.py --timeout 30` (one attempt, zero duplicate results); and `python scripts/phase21_worker_e2e.py --timeout 30 --simulate-expired-lease` (two attempts, zero duplicate results). These used synthetic data and cleaned up their records.
- Full backend regression: **277 passed, 7 skipped, 0 failed**, with one deprecation warning. Six skips are opt-in live integrations; the remaining skip is the blocked Phase 17 threshold gate.
- Phase 24 plus process-loader tests: **6 passed**. Critical Ruff gate (`E9,F821`) passed. `git diff --check` passed after the CI remediation change.
- The screenshots' backend CI failure was an install-time runner disk exhaustion before tests or migrations ran. The fix moves optional local embedding dependencies to `backend/requirements-local-embeddings.txt` and disables pip caching for the ephemeral workflow. Local checks do not establish that the hosted rerun passed.

### Ordered actions to close the project

1. Check GitHub Actions for commit `61da349`; record the run URL and both job outcomes in the Phase 22 plan and this report. If either job fails, fix the observed failure and rerun it.
2. Resolve the Phase 17 threshold prerequisite by recovering the original approved file or obtaining approval for a new, versioned threshold set; rerun its gate and preserve the historical results separately.
3. Run a fresh authenticated frontend journey covering customer/internal access, admin provisioning, case intake, document upload and processing, verification, task resolution, manager decision, final status, and event history.
4. Complete Phase 20 route/data approvals and production-topology evidence before sending business documents to any external provider or accepting untrusted customer uploads in production.
5. Complete Phase 21 PostgreSQL rollback and real ERPNext integration evidence; document how connected systems handle at-least-once delivery safely.
6. Complete Phase 23 model comparisons and repeated system evaluation using synthetic data first. Use representative business documents only after their provenance and the provider/data route are approved.
7. Finish Phases 25–26 documentation and demo preparation, then perform and record the complete rehearsal.
8. Treat broader repository-wide Ruff/mypy cleanup as engineering hardening after release gates. Older audit notes reported 1,378 Ruff findings and 63 mypy errors; those counts are historical and should be freshly measured before planning cleanup.

The Phase 17 checkboxes and result narrative above retain the historical 2026-10-09 closeout. The later audit note remains authoritative for the current state: its original ignored threshold file is absent, so current acceptance is blocked. Likewise, the 2026-10-12 Docker-unavailable notes describe that audit run; the fresh 2026-10-13 Compose worker results above supersede them for current local worker verification. Hosted CI, production approval, and real-provider evidence remain open until independently recorded.

## Phase 27 — AI Research & Evaluation Foundation — 2026-10-17

**Status: PLANNED.** Completed a documentation-only audit on `main` at `70059fab` (equal to `origin/main`, with a clean tree at audit start). The plan is [Phase 27 — AI Research & Evaluation Foundation](phase27-ai-research-evaluation-plan.md). No AI implementation, tests, datasets, evaluator scripts, configuration, model settings, live calls, or experiments were changed or run for this audit.

The repository has a working Document Agent pipeline, organization-scoped semantic knowledge search, bounded Supervisor orchestration, provider adapters, and a versioned Phase 23 four-agent synthetic scorer. The audit found the following work remains:

- **Document Agent:** broaden measured extraction/classification cases; assess confidence and review calibration; investigate that non-confidence review triggers can be labeled as a classification-confidence issue; measure multi-source citation fidelity because persistence currently selects the first citation only.
- **RAG:** Knowledge search is registered as a Tool Gateway capability for DOCUMENT, VERIFICATION, and SUPERVISOR, and existing tests cover gateway dispatch and embedding failure. The integration test executes the gateway tool directly; it does not establish model-driven agent use, answer grounding, or quality impact. Decide whether retrieval remains a standalone API or supplies grounded evidence to a selected agent. Expand beyond the historical 12-question synthetic retrieval set, and measure retrieval separately from generated-answer accuracy and abstention.
- **Supervisor:** code and deterministic tests cover bounded context, allowed children, timeout/failure handling, and safe state checks. Actual candidate-model planning quality and repeated system-level outcomes remain unmeasured.
- **Datasets and models:** the tracked Phase 23 benchmark has four synthetic cases per agent. The Phase 17 generated corpus is ignored by Git. Provider adapters exist, but model comparisons are pending; the Phase 23 environment check from 2026-10-12 reported missing API credentials and an unreachable Ollama endpoint, and those conditions were not rechecked here.
- **Traceability and security:** runtime agent execution records inspected here retain the model label rather than complete per-call usage/version evidence. A broader labeled adversarial suite is also still needed beyond the existing safety contract tests.

**Priorities and dependencies:** P0 owner decisions are required to recover or replace the missing Phase 17 threshold file and to approve any representative business-data route/corpus. Synthetic-only evaluation can proceed independently. P1 work establishes Document, RAG, and Supervisor baselines and expands versioned evaluation data. P2 work improves runtime evaluation traceability and adversarial coverage. Phase 23 remains the owner for its official candidate comparisons, system-level evaluation, route recommendations, and authorized-corpus criterion; Phase 20 remains the owner of provider/data approval. See the new plan's gap matrix for file/test evidence, acceptance criteria, deliverables, and task IDs.

No Phase 27 experiment, score, threshold, or model recommendation is claimed. All implementation and evaluation work in the new phase remains PLANNED / NOT STARTED.
