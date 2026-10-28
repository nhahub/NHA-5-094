# Phase 24 — Generalization Test

**Last updated:** 2026-10-12 (Africa/Cairo)  
**Status:** VERIFIED COMPLETE for the official local synthetic generalization acceptance. Production insurance readiness and live insurer integrations are outside this phase and are not claimed.  
**Starting commit:** `b5b15ef` (`main` and `origin/main`); clean tree at initial inspection.

## A. Objective and scope

### Official objective

Prove that a second process, the checklist's Insurance Claim example, can use the existing VerifiaAI architecture without process-specific application branches. The documented example sequence is:

`Claim Submitted → Document Collection → Claim Verification → Financial Review → Manager Approval → Payment`

Authoritative sources:

- `Documentation/04-operations-and-roadmap.md` §33, Phase 24 — Generalization.
- `Documentation/Verifia_Detailed_Implementation_Checklist.md` §24, including its eight checks and Definition of Done.
- Supporting generic architecture: `Documentation/02-architecture.md`, `Documentation/03-database-schema.md`, `backend/app/domain/processes/configuration_loader.py`, Case/Workflow/Document/Verification/Tool/Human Review services and API contracts.

### Requirements and exclusions

The same Case model, Workflow Engine, Verification Engine, Document Agent architecture, Tool Gateway, and Human Review system must support the second process. Only process configuration, rules, knowledge, documents, and domain tools may differ. The claim process must be created/versioned/published and exercised through the same API and persistence boundaries without special application branches.

Use fictional synthetic claims and deterministic registered tool adapters. Do not add a parallel claim service/router, hard-code insurance behavior into generic services, create executable tool handlers from JSON, or use real personal/financial claims. No schema migration is planned; add one only if a documented generic capability cannot be represented otherwise.

## B. Requirement traceability

| Requirement ID | Official source / behavior | Current state and evidence | Implementation task | Test strategy / acceptance criteria | Status |
|---|---|---|---|---|---|
| P24-R001 | Checklist §24: same Case model works for Insurance Claim. | Case is created through the shared authenticated API and stores the Insurance Claim process and immutable published version IDs. | T24-01, T24-02 | Assert the persisted Case references the loaded Insurance Claim version. | VERIFIED COMPLETE |
| P24-R002 | Checklist §24: same Workflow Engine works. | Six configured claim stages and five transitions use the existing transition API. | T24-01, T24-02 | Authenticated journey reaches Payment and Case status becomes COMPLETED. | VERIFIED COMPLETE |
| P24-R003 | Checklist §24: same Verification Engine works. | Configured claim-reference equality rule evaluates document fields. | T24-01, T24-02 | API returns PASS and the verification execution persists. | VERIFIED COMPLETE |
| P24-R004 | Checklist §24: same Document Agent architecture works. | The existing document pipeline reads the Case ProcessVersion's claim classes/schemas; only the model boundary is faked in test. | T24-01, T24-02 | Upload/classify/extract both synthetic documents through existing document APIs; both complete without review. | VERIFIED COMPLETE |
| P24-R005 | Checklist §24: same Tool Gateway works. | Existing `check_required_documents` tool is enabled by the process-version allowlist and role permission. | T24-01, T24-02 | Discover and execute the registered tool through `/api/v1/tools`; assert successful output and persisted execution. | VERIFIED COMPLETE |
| P24-R006 | Checklist §24: same Human Review system works. | Existing task and approval APIs operate on the claim Case. | T24-02 | Complete a financial-review task and manager approval through the shared APIs. | VERIFIED COMPLETE |
| P24-R007 | Checklist §24: only process configuration, rules, knowledge, documents and domain tools change. | Added a declarative JSON process and test-only adapter; no production app branch, migration, second engine, or alternate API was added. | T24-01, T24-03 | Review changed paths and generic loader test; process-specific content remains data. | VERIFIED COMPLETE |
| P24-R008 | Checklist §24: second process uses same API/persistence boundaries without process-specific branches. | One authenticated journey exercises the same Case/document/workflow/verification/tool/task/approval/event APIs and persistence. | T24-02, T24-03 | Assert persisted process binding, verification result, tool trace, completed Case, and lifecycle event history. | VERIFIED COMPLETE |

## C. Initial gap analysis

- **Reusable:** generic Process/ProcessVersion, declarative JSON loader, immutable version publishing, stage and transition definitions, document classes/extraction schemas, rules/calculations/verifications, requirements, registered-tool allowlisting, Case APIs, workflow APIs, Human Review/task/approval, and authenticated Case journey fixtures.
- **Closed:** `workflows/insurance_claim/process.json` and `backend/tests/test_phase24_generalization.py` now prove the shared pipeline for a distinct process without adding a production insurance branch.
- **Safety boundary:** claim details may contain personal and financial data. The test will use generated fictional names/addresses/amounts and a fake adapter only. No external provider calls, live insurer, or real claims database.
- **Risk:** Insurance stages such as Financial Review and Payment may be semantically represented by generic configured workflow, approval, and registered tools. Do not invent a payment integration requirement; use a deterministic test domain tool only if the Gateway has a supported extension point and the checklist requires that boundary to be exercised.
- **Schema/migrations:** current ProcessVersion configuration JSON and generic definitions likely suffice; no migration is justified unless tests prove otherwise.

## D. Task breakdown

| Task ID | Requirement links | Priority / dependencies | Files and implementation | Test and acceptance | Status |
|---|---|---|---|---|---|
| T24-00 | P24-R001–R008 | P0; none | Inspect official sources, loader, existing generic APIs/tests, record baseline. | Source-to-requirement mapping and initial state captured. | VERIFIED COMPLETE |
| T24-01 | P24-R001–R007 | P0; T24-00 | Added `workflows/insurance_claim/process.json` with the documented stage sequence, requirements, claim document classes/schemas, deterministic claim-reference rule/verification, and safe registered-tool allowlist. | Generic loader publishes the version; loader tests and the API journey pass; no backend process branch/migration. | VERIFIED COMPLETE |
| T24-02 | P24-R001–R008 | P0; T24-01 | Added an isolated authenticated API journey for Case, document, workflow, verification, Tool Gateway, task, approval, events and temporary storage. The fake adapter is test-only. | Journey passed with synthetic data; Case version, verification, tool trace and lifecycle event history are persisted; no special endpoint or code branch. | VERIFIED COMPLETE |
| T24-03 | P24-R007–R008 | P1; T24-01/T24-02 | Reconciled the checklist, roadmap, Phase 24 plan, cross-phase audit, progress report, README, docs index, and run guide. | Status reflects test evidence and documented external limits. | VERIFIED COMPLETE |

## E. Test strategy and Definition of Done

1. Static config validation rejects unknown stage/rule/verification references and publishes all configured definitions through existing services.
2. Authenticated API journey creates a Case bound to the Insurance Claim ProcessVersion and traverses the configured stages using the shared workflow boundary.
3. Claim-document upload/processing, configured verification, Tool Gateway authorization, Human Review/task, manager approval, and Payment completion use existing contracts and persist expected records/events.
4. Existing generic workflow, gateway, and human-review suites continue to cover policy rejection; this Phase 24 journey focuses on the official valid second-process path.
5. No process-specific app branch, alternate architecture/API, schema migration, real personal data, or external provider call is introduced.
6. Run focused Phase 24 and affected existing process-loader/Case journey tests; critical Ruff and relevant backend regression. Isolated storage/database fixtures are required.
7. Mark checklist §24 complete only after all of these observable assertions pass; Phase 24 does not imply production insurance readiness or real insurer integration.

## F. Progress log

### 2026-10-12 — Milestone 0: scope and initial gap

- Confirmed the official Insurance Claim generalization scope in checklist §24 and roadmap §33. The existing JSON loader and authenticated Case journey are reusable.
- Recorded the clean starting state at `b5b15ef`. No claim process template or Phase 24 plan existed.
- Added this living plan before implementation.

### 2026-10-12 — Milestone 1: implementation and local acceptance

- Added the declarative Insurance Claim process with the official six-stage sequence, two configurable document classes/schemas, one deterministic claim-reference rule/verification, document and approval requirements, and an allowlist of registered tools.
- Added an authenticated end-to-end test that uploads and processes fictional claim-form and repair-estimate PDFs, verifies the extracted claim number, executes `check_required_documents` through the Tool Gateway API, resolves a financial-review task, approves the claim as a manager, reaches Payment, and checks Case event history.
- Focused Phase 24 plus process-loader tests passed **6/6**. Full backend regression passed **277 tests, skipped 7, failed 0**. Critical Ruff (`E9,F821`) passed before final documentation updates; repeat final checks after edits.
- The test fakes only model JSON generation; file parsing, schema validation, storage, API authorization, workflow, verification, Tool Gateway, task/approval, events and persistence remain real.

### 2026-10-12 — Post-commit final verification

- Reviewed the committed implementation at `fc4a77b2d1dc1b0218b4fbf0981a1e20bded6af8`, with `HEAD == origin/main` and a clean tree at review start. The commit adds the process JSON, test, and documentation; it adds no Insurance Claim branch under `backend/app` and no Alembic migration.
- Fresh project-venv checks passed: Phase 24 plus process loader **6/6**; the focused authenticated Case/event/authorization/upload/readiness/verification group **123 passed**; complete deterministic backend regression **277 passed, 7 skipped, 0 failed** in **69.05 seconds**; critical Ruff `E9,F821` passed.
- Six live integrations were skipped with `VERIFIA_RUN_LIVE_TESTS` disabled; the Phase 17 gate was skipped because the original threshold file is unavailable. No live provider or insurer call was made, and no real claim document was used.
- Docker-backed multi-worker checks remain blocked because the Docker Linux-engine pipe is missing. See §9 of the [Phases 20–24 audit plan](phases20-24-comprehensive-audit-plan.md) for exact commands, exit codes, and the phase status matrix.

## G. Risks and blockers

| Risk / blocker | Effect | Handling | Status |
|---|---|---|---|
| Async API tests stall inside the restricted shell | Tests do not report collection before socket access is granted | The approved local regression runner outside the sandbox completed. | RESOLVED |
| Docker Linux-engine pipe is missing in the current session | Fresh PostgreSQL multi-worker probe unavailable | Retain the dated Phase 22 passing evidence and clearly label that it was not rerun in this audit. | BLOCKED for fresh infrastructure recheck |
| No provider credentials/approved claim corpus | No live model or real-claim evaluation | Use synthetic fixtures and fake adapter; keep provider/data criteria open. | BLOCKED for external evaluation |
