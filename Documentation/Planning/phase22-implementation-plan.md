# Phase 22 — Repeatable Quality Gates

**Last updated:** 2026-10-12  
**Current status:** PARTIAL — deterministic backend gates pass freshly; hosted GitHub Actions evidence (R001–R002) and a fresh PostgreSQL multi-worker rerun (R010) remain unavailable.
**Starting commit:** `bf2795b` (`main` was clean at inspection).  
**Owner evidence:** this document is the living Phase 22 plan and progress log.

## A. Phase overview

### Purpose and expected outcomes

Make the project's required quality checks repeatable in CI and close the test gaps named by the existing Phase 22 checklist. The gate must run deterministic checks on clean installs, exercise the complete local backend regression and frontend checks, verify the PostgreSQL migration chain, cover the documented failure paths, and prove tenant isolation across protected resource families.

### Scope and authority

The Phase 22 objective is explicitly named **Repeatable quality gates** in `Documentation/04-operations-and-roadmap.md` §33, item 4. Its detail comes from `Documentation/Verifia_Detailed_Implementation_Checklist.md` §22 (Unit Tests, Integration Tests, End-to-End, Failure Tests, Continuous Integration). The roadmap calls for CI covering lint, complete regression, migrations, frontend checks, API/database/storage/provider failures, and cross-tenant authorization. The checklist additionally names the workflow/tool paths, recovery and replay behaviors, production configuration, empty/prior-schema migration upgrades, and separation of opt-in provider tests.

**This phase is not a tenant-isolation feature redesign.** Tenant isolation already has implementation evidence; Phase 22 closes the checklist's promised route/resource-level negative-test coverage. The phase will not expand production provider approvals, claim real external-service coverage from mocks, resolve the separate Phase 17 threshold gate, or replace existing application architecture.

### Earlier-phase dependencies

- **Phase 20 — PARTIAL:** local controls and deterministic provider-error handling can be gated. Provider terms/data-class approval and production storage/network evidence are separate open items and cannot be closed by CI mocks.
- **Phase 21 — PARTIAL:** local event/transaction/readiness tests pass. Fresh Compose PostgreSQL stale-claim fencing, normal two-worker delivery, expired-lease recovery, and API liveness/readiness passed on 2026-10-13. PostgreSQL-specific injected rollback and real ERPNext integration remain separate open items.
- **Phase 17 — BLOCKED:** the ignored threshold file is unavailable. The CI deterministic suite must keep this gate explicitly separated/reported rather than fabricate thresholds or convert the missing-file skip into a pass.

### Explicit out of scope

- New product functionality or authorization architecture.
- Production deployment, production secrets, and production data.
- Live provider tests or live ERPNext calls in default pull-request checks.
- Choosing or benchmarking models (Phase 23), adding a second business process (Phase 24), or inventing Phase 17 acceptance thresholds.
- Broad unrelated lint/type debt cleanup unless a specific defect blocks a required Phase 22 check.

## B. Current-state assessment

### Observed facts at the start

- The repository was clean on `main` at `bf2795b`; the prior Phase 20–21 audit and implementation are committed. No user edits were present to preserve beyond committed history.
- The configured `origin` host is `github.com`, so GitHub Actions is the repository's relevant CI target.
- The roadmap names Phase 22 but there was no `Documentation/phase22-implementation-plan.md` and no `.github/workflows` directory at inspection.
- The backend has `requirements.txt`, `requirements-dev.txt`, Alembic revisions `0001` through `0011`, `pytest.ini`, a Windows-focused full-regression runner, and a test suite using isolated in-memory SQLite for ordinary API/service tests. Revision `0001` creates the PostgreSQL `vector` extension, so migration-chain CI needs PostgreSQL with pgvector.
- The frontend has a checked-in `package-lock.json` and scripts for test, typecheck, lint, and production build. Local `node_modules` and the backend virtual environment exist; CI must still install from lockfiles/dependency declarations on a clean runner.
- The last Phase 20–21 audit recorded a full backend result of 262 passed / 7 skipped using a process-only bcrypt compatibility shim on a host with bcrypt 5 despite the repository pin `<4.1`. That result is historical for this phase and will be re-run. The missing Phase 17 threshold file accounts for one explicit blocked skip; six live integration checks are opt-in.
- A broad Ruff run currently reports 1,378 findings. The explicit critical gate `ruff check --isolated --select E9,F821 app tests scripts` passes and is used by the new workflow; broader style/modernization cleanup remains visible debt rather than a knowingly failing CI step.
- Existing tests already exercise pieces of API, storage, provider, event recovery, and tenant behavior. Their actual coverage and missing resource families are being audited against §22 before new tests are added.

### Current implementation map

| Area | Existing implementation/evidence | Current gap or uncertainty | Blocks phase? |
|---|---|---|---|
| CI | No GitHub Actions workflow found. | No repeatable hosted quality gate. | Yes |
| Backend regression | `backend/scripts/run_backend_regression_windows.py`; `backend/pytest.ini`; backend tests. | Must prove clean dependency install and rerun full deterministic regression; host bcrypt mismatch is known. | Yes |
| Lint | Ruff is in `backend/requirements-dev.txt`; frontend ESLint is scripted. | No CI invocation; whole-repo Ruff baseline is not clean. | Yes, until a truthful gate strategy is established |
| Migrations | Alembic chain currently ends at `0011_durable_event_deliveries`; app migration environment uses configured PostgreSQL URI. | No CI migration check; empty and prior-supported-schema upgrades need evidence. | Yes |
| Frontend | npm lockfile plus test/typecheck/lint/build scripts. | No clean-install CI evidence. | Yes |
| Failure behavior | Existing tests cover several mocked provider, storage, API, and event cases. | Need map each §22 failure criterion to tests and fill only actual gaps. | Yes |
| Tenant isolation | Tenant-aware services and a few route/Case journey tests exist. | Checklist explicitly requires negative access for cases, tasks, documents, evidence, events, and tools; route coverage is not yet verified. | Yes |

## C. Requirement traceability matrix

Statuses are intentionally conservative until implementation and current-run evidence satisfy the acceptance criteria.

| Requirement ID | Source | Required behavior | Current state | Implementation task | Tests | Acceptance criteria | Status |
|---|---|---|---|---|---|---|---|
| P22-R001 | Roadmap §33 item 4; checklist §22 Continuous Integration | Run repeatable CI for backend/frontend lint and complete deterministic regression. | GitHub Actions workflow is added; hosted execution is pending. | T22-01, T22-04 | Workflow validation; backend full regression; Ruff and frontend lint. | Pull request/push workflow invokes documented checks on clean runners and does not silently ignore failures. | IMPLEMENTED — NOT VERIFIED |
| P22-R002 | Checklist §22 Continuous Integration | Validate a clean install, migration chain, and frontend production build. | Workflow now installs backend requirements and uses `npm ci`; its PostgreSQL job upgrades from empty through revision `0010` to head. Hosted run is pending. | T22-01, T22-02, T22-04 | CI install; migration-version assertions; frontend `npm ci` + build. | A clean runner installs from repository manifests, upgrades an empty PostgreSQL/pgvector DB through `0011_durable_event_deliveries`, and builds frontend output. | IMPLEMENTED — NOT VERIFIED |
| P22-R003 | Checklist §22 Integration Tests | Verify API-to-database integration and database failure behavior. | SQLite API integration and event-write rollback tests pass. A real asyncpg client against a closed loopback port verifies startup stays live/unready and Case creation returns a sanitized 503 without false success. | T22-02, T22-03 | `test_readiness.py`; full backend regression. | API and readiness fail safely when the configured DB cannot be reached; no success is reported for a failed Case request. | VERIFIED COMPLETE |
| P22-R004 | Checklist §22 Integration Tests | Verify API-to-storage and document validation/failure behavior. | Local storage round-trip, traversal, upload and processing tests exist; API outage test asserts 503 and no document row. | T22-03 | Storage success/failure, invalid/missing document and upload/processing cases. | Storage failures return controlled outcomes with no false success or cross-tenant disclosure. | VERIFIED COMPLETE |
| P22-R005 | Checklist §22 Integration Tests | Verify Tool Gateway-to-Tool and Agent-to-Tool Gateway authorization/failure behavior. | Tool Gateway and agent suites verify contract validation, tenant/role denial, and gateway use. | T22-03 | Tool schema/permission, agent gateway, unauthorized tool and tool failure tests. | Invalid or unauthorized tool requests are rejected; downstream failures stay bounded and auditable. | VERIFIED COMPLETE |
| P22-R006 | Checklist §22 Integration Tests | Verify Verification-to-Rules and Workflow-to-Case integrations. | Verification/rules and workflow/Case integration tests are present and passed in the latest full regression. | T22-03 | Verification/rule and workflow/Case integration tests. | Applicable workflow outcomes persist through the intended service boundary and invalid transitions are rejected. | VERIFIED COMPLETE |
| P22-R007 | Checklist §22 End-to-End | Exercise the documented Case journey from create through upload, processing, extraction, verification, review, resolution, approval, and completion. | An isolated authenticated Case journey exists and passed the latest full regression. | T22-03, T22-05 | Current end-to-end Case journey regression. | The journey asserts persisted lifecycle/events/permissions with disposable data and deterministic providers. | VERIFIED COMPLETE |
| P22-R008 | Checklist §22 Failure Tests | Cover missing/invalid documents, low-confidence extraction, calculation failure, verification mismatch, unauthorized user/tool, invalid transition, provider timeout/failure, tool failure, and duplicate event. | Existing document, rule/calculation, authorization, model gateway, tool, workflow, and duplicate-delivery tests cover the listed deterministic failure classes. | T22-03 | Named focused tests and complete regression. | Each listed failure has a deterministic test asserting safe state and controlled error/escalation. | VERIFIED COMPLETE |
| P22-R009 | Checklist §22 Failure Tests | Cover database/Redis unavailable at startup and during an in-flight workflow. | Real asyncpg and Redis clients connect to deliberately closed loopback ports: startup completes, `/readyz` returns 503 with both dependencies disconnected, `/livez` stays 200, and a Case-creation request with unavailable PostgreSQL returns a safe 503. Redis is not used by the business request/worker path; its documented role is readiness. | T22-03 | `test_readiness.py`; full backend regression. | Startup is not falsely marked ready; database-dependent request fails without false success; Redis outage is reflected by readiness. | VERIFIED COMPLETE |
| P22-R010 | Checklist §22 Failure Tests | Cover worker restart, replay, retry exhaustion, and concurrent duplicate delivery. | All three PostgreSQL probes executed against the live Compose database (port 5433): stale-claim fencing, normal delivery with two running workers, and expired-lease crash recovery. All three passed. | T22-03, T22-05 | `test_event_delivery.py`; PostgreSQL `phase21_worker_e2e.py` probe; two-worker E2E. | Deterministic subchecks pass; current PostgreSQL fencing and multi-worker recovery results are recorded. | VERIFIED COMPLETE |
| P22-R011 | Checklist §22 Failure Tests; checklist §20 Data | Reject cross-tenant access for cases, tasks, documents, evidence, events, and tools. | Negative checks cover case/review, task, document, task-comment evidence association, case event, and Tool Gateway service access. Evidence has no standalone API and is only exposed through scoped case/task bundles. | T22-03 | Focused negative API/service checks for all six resource families. | A foreign-tenant actor cannot read or mutate any listed resource; responses do not disclose foreign records. | VERIFIED COMPLETE |
| P22-R012 | Checklist §22 Failure Tests | Verify production configuration rejects unsafe defaults. | Phase 20 security tests exist and passed in the latest full regression. | T22-03 | Existing production-settings test suite. | Weak/default secret, unsafe CORS/debug, missing production settings, and unscanned-upload override are rejected. | VERIFIED COMPLETE |
| P22-R013 | Checklist §22 Continuous Integration | Keep opt-in provider tests separated from deterministic regression checks. | The full local run skipped six explicitly marked live integrations; workflow uses no external secrets and does not opt into live tests. | T22-01, T22-04 | Default CI regression and separate opt-in/manual live job documentation. | No provider credentials/network are required for pull-request CI; live checks report skipped/blocked status. | VERIFIED COMPLETE |

## D. Architecture and implementation design

### CI boundary

Use a least-privilege GitHub Actions workflow if the repository's Git hosting is confirmed compatible with GitHub Actions by its existing remote/project settings. Trigger deterministic checks on pull requests and pushes to the default branch. Use separate backend, PostgreSQL migration, and frontend jobs so failures identify the affected gate. Keep provider/OCR/ERPNext credentials out of pull-request workflows. Pin runtime major/minor versions to the versions supported by the project manifests and install backend/frontend dependencies from the committed manifests and npm lockfile.

The database migration job must use an isolated PostgreSQL image with pgvector, start from an empty database, run `alembic upgrade head`, and assert the current migration head. If the prior supported schema can be represented without modifying shared history, use a disposable database to upgrade from its prior revision; never edit or squash existing revisions. Test code remains SQLite-isolated unless the requirement needs PostgreSQL semantics.

### Test coverage design

Build a traceability inventory of §22 criteria and existing test names before editing tests. Add parameterized negative authorization tests using two organizations and actors. Reuse established route dependencies and fixtures; do not bypass authorization by setting a foreign `organization_id` supplied by the caller. Where resource APIs are not implemented, record the requirement as not applicable only with route/code evidence.

Failure tests must inject dependency/provider/storage/DB failures at established seams and assert persisted business state, event/outbox rows, and controlled API responses. Do not contact real providers in default CI. Preserve at-least-once event semantics and avoid claiming exactly-once external effects.

### Lint gate decision

Measure the current whole-project Ruff and frontend ESLint results. If the existing Ruff baseline prevents a truthful green CI lint gate, establish an explicit baseline/diff-only policy or a scoped lint gate that prevents new violations, and document its exact coverage. Do not silently suppress findings or label a known-failing check as passed. The chosen CI policy must be repeatable and visible.

## E. Dependency-aware task breakdown

| Task ID | Requirement ID | Description | Priority | Dependencies | Expected files | Implementation steps | Tests / acceptance | Status |
|---|---|---|---|---|---|---|---|---|
| T22-00 | P22-R001–R013 | Inventory current commands, tests, failure behavior, tenant route/resource surface, runtimes, and hosted Git capability. | P0 | None | Plan; test/source inventory | Compare every checklist §22 item to actual test names and routes; run fresh baselines. | Evidence-backed coverage matrix and documented environment limits. | VERIFIED COMPLETE |
| T22-01 | P22-R001, R013 | Add deterministic CI workflow and separate opt-in integration guidance. | P0 | T22-00 | `.github/workflows/quality-gates.yml`; docs | Define stable jobs, least privilege, dependency caching, no secrets, and failure visibility. | Workflow parses; hosted run remains pending. | IMPLEMENTED — NOT VERIFIED |
| T22-02 | P22-R002, R003 | Add empty/prior-supported PostgreSQL migration gate with pgvector and current-head assertion. | P0 | T22-00 | `.github/workflows/quality-gates.yml` | Use disposable Postgres service; upgrade from empty through `0010`, then head. | Workflow asserts `0010_user_token_version` and `0011_durable_event_deliveries`; hosted job remains pending. | IMPLEMENTED — NOT VERIFIED |
| T22-03 | P22-R003–R012 | Fill verified API/storage/provider/database/event and cross-tenant test gaps. | P0 | T22-00 | Backend authorization, storage, readiness, and event-delivery tests; database session and API error handling. | Add tests only after mapping existing tests/routes; exercise controlled dependency failures; assert denial and rollback. | Latest full regression: 268 passed, 7 skipped, 0 failed in 61.97s; focused readiness/event suite: 15 passed before final timeout-classification refinement; final actual-client outage cases: 2 passed after that refinement. | VERIFIED COMPLETE |
| T22-04 | P22-R001, R002, R013 | Gate complete backend regression and frontend clean-install test/type/lint/build; settle Ruff baseline policy. | P0 | T22-00, T22-01 | Workflow; README/run guide | Use repository scripts/manifests; avoid live integrations and false green. | Local backend: 268 passed, 7 skipped, 0 failed; frontend baseline: 21 tests plus typecheck, ESLint and build passed; workflow installs from manifests but hosted clean-run evidence is pending. | IMPLEMENTED — NOT VERIFIED |
| T22-05 | P22-R007, R010 | Run integrated regression including migrations, Case journey, event recovery, and Docker-backed checks where available. | P1 | T22-02–T22-04 | Tests, `backend/scripts/phase21_worker_e2e.py`, workflow, and plan log. | Run targeted suites then full suites; record external/Docker blockers as BLOCKED. | Full backend regression: 268 passed, 7 skipped, 0 failed (66.14 s). All three PostgreSQL probes PASS against live Compose services: (1) stale-claim fencing, (2) normal two-worker delivery (attempts=1, duplicate_results=0), (3) expired-lease crash recovery (attempts=2, duplicate_results=0). | VERIFIED COMPLETE |
| T22-06 | P22-R001–R013 | Reconcile checklist, roadmap, README, progress report and documentation index with evidence. | P1 | T22-01–T22-05 | Existing project docs; plan | Update only after accepted tests; preserve earlier-phase partial/blocked status. | Plan, checklist, progress report, roadmap, README, documentation index and run guide agree with current evidence; final diff review and whitespace check passed. | VERIFIED COMPLETE |

## F. Testing strategy

| Layer | Gate | Environment | Required evidence |
|---|---|---|---|
| Backend unit/service/API regression | `python scripts/run_backend_regression_windows.py` on constrained Windows local host; direct `python -m pytest` in hosted Linux CI after verifying parity. | Isolated SQLite fixtures; controlled closed-loopback actual driver failures; no live provider credentials. | Full collected/passed/skipped/failed counts and named skipped reasons. |
| Backend lint | `ruff check ...` according to the verified project baseline strategy. | Clean development dependencies. | Exact command and baseline scope; no silently ignored failures. |
| PostgreSQL migration | `python -m alembic upgrade head`, then assert `alembic current`/head. | Disposable PostgreSQL with `vector` extension. | Empty database reaches `0011_durable_event_deliveries`; prior revision upgrade if explicitly supported. |
| Frontend | `npm ci`, `npm test -- --run`, `npm run typecheck`, `npm run lint`, `npm run build`. | Supported Node runtime; lockfile only. | All scripts exit zero and production bundle is generated. |
| Cross-tenant API/security | Existing auth/client fixtures plus two tenant identities. | SQLite test DB and deterministic storage/providers. | Denials/no foreign data for each protected resource family and mutation path. |
| Failure/recovery | Focused tests then backend regression. | Mock unavailable DB/Redis/provider/storage; isolated worker/outbox fixtures. | Controlled failure, no false-ready state, duplicate/retry safety, transactional rollback. |
| Live providers / Docker / ERPNext | Separate/manual only. | Explicit opt-in credentials/services. | Clearly labeled PASS/BLOCKED/SKIPPED; excluded from default pull-request gate. |

## G. Risks and blockers

- Whole-project Ruff has known outstanding findings; the baseline and sustainable CI policy must be remeasured.
- The local host's bcrypt 5.0.0 does not satisfy the repository's `bcrypt<4.1` constraint. The Passlib compatibility failure was fixed in Milestone 4 by using direct bcrypt 4.x/5.x-compatible hash and verify calls; CI still installs from the tracked constraint.
- Backend dependency manifests include ML/OCR libraries that may make cold installation slow or memory-intensive. The full regression still needs a genuine clean install; do not omit required runtime packages merely to speed CI.
- PostgreSQL migration tests require the pgvector extension. A vanilla Postgres service will not satisfy revision `0001`.
- GitHub Actions use is supported by roadmap intent but repository hosting configuration has not yet been checked; if incompatible, record the supported CI alternative rather than silently creating an unused workflow.
- Docker Desktop access was previously blocked in this Windows environment. Current service availability will be probed before any live checks; no container will be stopped or restarted.
- At an earlier closure attempt, the Docker Linux-engine named pipe was absent and `gh` was not installed. Milestone 4 later recorded passing local PostgreSQL worker probes. The Docker pipe is missing again in the comprehensive audit, so no fresh probe was run. The workflow is tracked on the recorded `origin/main` baseline, but no hosted Actions result was observable.
- Opt-in provider integrations, real ERPNext, production routes, and the ignored Phase 17 threshold file remain outside default CI.

### Hosted CI access and exact run steps

The configured `origin` points to GitHub and the workflow is tracked at the recorded `origin/main` baseline. `gh` is not installed, and the GitHub Actions page could not be fetched from this environment; there is no hosted result to claim. To close R001–R002:

1. Review the current workspace in GitHub Desktop, then commit and push when ready to trigger a hosted run. This audit did not commit or push.
2. Open the repository's **Actions** tab and select **Phase 22 Quality Gates**. A push to `main` or a pull request triggers it automatically; the workflow also supports **Run workflow**.
3. Wait for both **Backend regression, lint, migrations, and worker recovery** and **Frontend tests, typecheck, lint, and production build** jobs to finish. Require all steps green; check the pytest summary for the explicit six opt-in skips and blocked Phase 17 threshold skip.
4. Record the run URL, commit SHA, job outcomes, and any failure logs here before changing R001/R002/R010 to PASS. A workflow file or local YAML parse is not hosted execution evidence.

## H. Definition of done

Phase 22 can be marked `VERIFIED COMPLETE` only when:

1. The roadmap/checklist criteria above each have an ID, implemented test/gate, and current evidence.
2. Pull request and default-branch CI installs from tracked manifests/lockfiles, runs the declared lint gate, complete deterministic backend regression, migration chain, and all frontend checks/build.
3. PostgreSQL migration validation starts with an empty database and reaches the checked-in Alembic head; no historical migration is rewritten.
4. Each applicable §22 integration/failure/tenant criterion maps to at least one deterministic test, including every listed protected resource family.
5. Provider/live-service checks are visibly separated from deterministic CI, and missing credentials/services cannot create a false pass.
6. The Phase 22 plan, checklist, roadmap, README, progress report, and documentation index agree with actual current evidence.
7. Remaining production-only/earlier-phase gaps remain explicitly partial, blocked, or deferred; they are not silently counted as Phase 22 passes.

## Progress log

### 2026-10-11 — Milestone 0: scope and initial repository inspection

- **Verified:** clean `main` at `bf2795b`; official Phase 22 objective is the roadmap's repeatable quality gate; §22 checklist spells out CI, regression, migrations, frontend, failure and tenant test items. No CI workflow or Phase 22 plan existed. Backend uses SQLite-isolated tests and PostgreSQL/pgvector migrations; frontend lockfile and scripts exist.
- **Changed:** created this plan before code/test implementation.
- **Test results:** no Phase 22 tests run yet; prior Phase 20–21 regression counts are recorded as historical only.
- **Open questions/actions:** map existing tests against each criterion; inspect remote/CI compatibility; measure fresh backend/frontend/lint/migration baselines.
- **Next milestone:** complete the checklist-to-test and protected-route inventory, then execute baseline checks before adding CI or tests.

### 2026-10-11 — Milestone 1: deterministic gaps and CI workflow

- **Changed:** added `.github/workflows/quality-gates.yml` with backend regression, a scoped critical Ruff gate, pgvector migration assertions and two-worker recovery probes, plus frontend clean-install/test/typecheck/lint/build jobs. Added negative tests for foreign-tenant evidence/document access, DB/Redis readiness failures, and document upload storage outage behavior.
- **Verified:** targeted backend additions passed (27 tests); full backend regression passed **265, skipped 7, failed 0** in 57.51s. Ruff `E9,F821` passed. The workflow YAML parsed successfully. Frontend baseline passed 21 tests and typecheck/lint/build earlier in this run.
- **Skipped/blocked at this 2026-10-11 milestone:** six live provider/runtime checks are intentionally opt-in. The Phase 17 threshold acceptance remains blocked because the user-confirmed ignored threshold file is unavailable. Docker Desktop's engine pipe was unavailable at that point, so the PostgreSQL migration and multi-worker probes were deferred; the later 2026-10-12 Milestone 4 below records those probes passing. Hosted GitHub Actions results remain pending.
- **New/confirmed risk:** repository-wide Ruff has 1,378 pre-existing findings, so the workflow uses an explicit critical-error/undefined-name gate rather than claiming the whole codebase passes style lint. Real DB/Redis outages during startup and in-flight work remain unverified; mocked readiness and transactional rollback coverage passed.
- **Next milestone:** trigger the workflow on GitHub and record its hosted clean-install, PostgreSQL migration, frontend and two-worker results; address or disposition real DB/Redis startup and in-flight outage coverage.

### 2026-10-11 — Milestone 2: documentation reconciliation and final diff review

- **Changed at this 2026-10-11 milestone:** updated the official checklist, roadmap, README, progress report, documentation index, and run guide. Phase 22 is consistently labeled IN PROGRESS; Phase 20 remains PARTIAL and Phase 17 remains BLOCKED. The Phase 21 live service recheck was still pending at this point; the later 2026-10-12 Milestone 4 records passing live PostgreSQL probes.
- **Verified:** documentation links and status references were checked; `git diff --check` passed. Final diff review found only the intended Phase 22 workflow, plan, tests, and documentation updates. The working tree remains on `main`; no commit was created.
- **Remaining at this 2026-10-11 milestone:** no GitHub Actions run had been observed and Docker migration/two-worker probes were not locally runnable yet. The later Milestone 4 records the Docker-backed probes passing; hosted CI remains the open Phase 22 gate.

### 2026-10-12 — Milestone 4: bcrypt fix and PostgreSQL multi-worker probes

- **Defect found and fixed:** re-running the full regression revealed 8 new failures in `test_auth_provisioning.py` and `test_auth_service.py`. Root cause: `bcrypt 5.0.0` (installed on the local host, which violates the `bcrypt<4.1` pin in `requirements.txt`) removed the `__about__` submodule that passlib 1.7.4 reads during backend detection. This caused `AttributeError: module 'bcrypt' has no attribute '__about__'` → cascaded `ValueError: password cannot be longer than 72 bytes` on all hash/verify calls. Fix: replaced passlib `CryptContext` in `backend/app/security/service.py` with direct `bcrypt.hashpw` / `bcrypt.checkpw` / `bcrypt.gensalt` calls. The output format ($2b$) is identical; the fix is compatible with both bcrypt 4.x (what CI will install) and 5.x (local host). Passlib import removed from `service.py`; `requirements.txt` pin unchanged. `conftest.py` left clean.
- **Verified:** full backend regression **268 passed, 7 skipped, 0 failed** in 66.14 s (exit 0). Critical Ruff gate `ruff check --isolated --select E9,F821 app tests scripts` — passed.
- **R010 probes — all three PASS against live Compose PostgreSQL (port 5433, pgvector/pgvector:pg16 healthy):**
  1. `python scripts/phase21_worker_e2e.py --verify-stale-claim-fencing` → `PASS: PostgreSQL fenced stale claim; the reclaimed lease finalized once.`
  2. `python scripts/phase21_worker_e2e.py --timeout 30` → `PASS: Compose worker completed one durable event delivery (expired_lease_recovery=False); attempts=1, duplicate_results=0.`
  3. `python scripts/phase21_worker_e2e.py --timeout 30 --simulate-expired-lease` → `PASS: Compose worker completed one durable event delivery (expired_lease_recovery=True); attempts=2, duplicate_results=0.`
- **Environment note:** Docker Desktop 29.8.2 is running. PostgreSQL is healthy on localhost:5433 (Docker host port) / container port 5432. Two event-worker containers (`verifiaai-event-worker-1` and `verifiaai-event-worker-2`) are running. Both ports 5432 (local native) and 5433 (Docker-mapped) have listeners; the `.env` file and the probe script correctly use port 5433.
- **Remaining as recorded at the Phase 22 implementation close:** R001 and R002 require an observable hosted GitHub Actions run. The workflow is tracked on the current `origin/main` baseline, but no hosted result was available to this audit. R001 and R002 remain implemented with hosted verification pending.
- **Next action:** review the current workspace in GitHub Desktop, then commit and push when ready to trigger a hosted run. The workflow is already tracked at the recorded `origin/main` baseline; this audit could not observe a hosted result. Record the Actions run URL and job outcomes before changing R001/R002 status. No commit or push was made here.


## Supplemental revalidation - first audit run (historical; superseded below)

The latest full deterministic backend regression during the Phases 20-24 audit passed **277 tests, skipped 7, failed 0** in 49.14 seconds. Six skips are opt-in live integrations; the remaining skip is the explicitly blocked Phase 17 threshold gate. The Phase 22-specific PostgreSQL migration and worker probes recorded above passed on 2026-10-12; Docker Desktop was unavailable for a fresh rerun during the later audit.

The workflow is tracked on origin/main at the recorded audit baseline, but a GitHub Actions run result could not be observed from this environment. After reviewing and committing/pushing the current workspace in GitHub Desktop, inspect the Actions tab and record a run URL and job outcomes before closing R001-R002. No commit or push was made as part of the audit.

## Post-commit verification - 2026-10-12

The project-venv full regression was freshly rerun on commit `fc4a77b2d1dc1b0218b4fbf0981a1e20bded6af8`: **277 passed, 7 skipped, 0 failed**, 69.05 seconds. Critical Ruff passed. Six live integrations were skipped because `VERIFIA_RUN_LIVE_TESTS` was false; the Phase 17 threshold gate reported its explicit missing-file block. The hosted Actions page and commit page returned cache misses and `gh` is unavailable, so no hosted result for this SHA is claimed. `docker compose ps` exited 1 because the Docker Linux-engine named pipe was missing; earlier migration and worker results remain historical. R001–R002 are **BLOCKED** on a verifiable hosted run and R010 is **PARTIAL** pending fresh Docker-backed probes. See §9 of the [Phases 20–24 audit plan](phases20-24-comprehensive-audit-plan.md).

## 2026-10-13 — hosted runner disk exhaustion and remediation

- **Observed hosted failure:** the GitHub Actions screenshot shows the backend job failing during dependency installation with `OSError: [Errno 28] No space left on device`; the separate frontend job passed. This is an install-time runner capacity failure, before lint, tests, migrations, or worker probes ran.
- **Root cause:** `backend/requirements.txt` included the optional local Sentence-Transformers adapter. Installing it on a CPU-only Linux runner pulled PyTorch and NVIDIA CUDA runtime packages even though the configured/default embedding route is API-based.
- **Changed in the current workspace:** moved `sentence-transformers` and `huggingface-hub` into `backend/requirements-local-embeddings.txt`; the standard app and CI requirements no longer install that local-only ML runtime. Removed pip caching from the ephemeral backend job and added `--no-cache-dir` to both pip install steps. README/run-guide instructions now explain how to opt into local embeddings, and the adapter's missing-package message points to the optional requirements file.
- **Local verification after the change:** full backend regression **277 passed, 7 skipped, 0 failed** in **55.13 seconds**; critical Ruff `E9,F821` gate passed; `git diff --check` passed. The initial restricted test attempt stalled before collection and was interrupted; the successful rerun used the approved loopback-enabled runner.
- **Still pending:** no post-fix hosted run exists yet because these changes are uncommitted. Keep R001–R002 open until the updated workflow is committed/pushed and both hosted jobs pass. The current hosted failure must not be reported as a green CI result.
