# VerifiaAI Next Milestone Plan: Phase 12 — Workflow Agent

**Prepared:** 2026-10-07

**Scope:** Repository review and implementation planning only. This document does not implement Phase 12. No files other than this plan were changed, and no tests were run for this review.

## Review notes and corrections

This plan incorporates a second pass over the prior assessment and corrects these points:

- The earlier inventory missed hidden/ignored paths. The repository does contain `.env.example`, `backend/.env.example`, frontend placeholder files, and `workflows/import_export/.gitkeep`; they are tracked. The README's structural references to these paths are therefore not absent, although frontend and workflow functionality remains a separate completion question.
- The progress report conflicts with itself on the backend test total: its summary says 102 passed while a later detailed record says 100 passed and five live tests skipped. README and the Phase 9 plan also contain older counts. No fresh test run was performed, so this plan does not present any of those counts as independently verified today.
- The progress report contains conflicting statements about online PostgreSQL/pgvector validation. Its phase summary and Phase 10 section report local database checks passed, while the detailed Phase 9 evaluation says `alembic current` could not connect and real PostgreSQL migration application/ranking remain unverified. The Phase 9 plan also says online application is unverified. Resolve this against a dated execution record before claiming release readiness.
- The workflow routes inspected authenticate a user but do not visibly pass organization scope into workflow service calls; `WorkflowService.validate_transition` loads a case by ID without an organization predicate. The Tool Gateway has stronger case/process organization checks. Treat scoped workflow access as a prerequisite to agent-mediated workflow actions.

## 1. Executive Summary

The next documented milestone is **Phase 12 — Workflow Agent**. Both the progress report and detailed checklist name it as next. Do not rename it Phase 13 or invent a Phase 12 alternative.

The current WORKFLOW dispatcher is a hard-coded placeholder. Replace it with a bounded, structured agent that reads the current case and configured workflow, proposes an allowlisted action, validates every referenced identifier, and sends any consequential action through the Tool Gateway and deterministic domain services. The Workflow Engine remains authoritative for transitions, requirements, approvals, and role checks. An LLM proposal alone must never change case state.

Before consequential actions are enabled, audit and enforce organization, case, process-version, stage, and actor authorization across workflow API/service paths. Prefer existing tables and services; no Phase 12 migration is presently justified. Use injected fake adapters for safety and contract tests. The roadmap places provider connectivity smoke checks in Phase 14 and comparative agent-quality evaluation in Phase 23.

## 2. Current Project State

- **Git:** `main`, at `477a912`, aligned with `origin/main`; the inspected working tree was clean.
- **Repository:** FastAPI backend, SQLAlchemy domain models, six Alembic revisions through `0006_knowledge_rag`, deterministic rules/calculation/verification/workflow services, Tool Gateway, document processing, knowledge retrieval, Document Agent, Verification Agent, and pytest suite.
- **Configuration:** root and backend `.env.example` files exist. `Settings` is defined in `backend/app/core/config.py`; it reads `.env` relative to the process working directory. README instructs users to provide the root or backend-local environment file for the chosen launch location.
- **Phase state:** report says Phases 9–11 implemented, Phase 12 next. README still says Phase 10 is current.
- **Database verification:** migration chain exists through `0006`; the online validation status is inconsistent across the report and Phase 9 plan.
- **Tests:** phase-specific and offline tests exist. The documented suite totals conflict; they were not rerun during this planning review.
- **Async processing:** `backend/app/infrastructure/queue/queue.py` defines job payloads but its enqueue implementation is a stub; it logs and returns success rather than durably placing work in Redis/Celery.

## 3. Phase-by-Phase Status

Statuses below reconcile checked-in structures and current documentation. “Complete” is not inferred from a commit title. Runtime claims not repeated during this planning task remain documentation-reported.

| Phase | Status | Reconciliation |
|---|---|---|
| 1. Repository and development foundation | PARTIALLY COMPLETE | Backend, configuration, Docker Compose, tests, docs, frontend/workflow placeholders exist. The documentation reports foundation checks complete, but this review did not rerun them. |
| 2. Database | PARTIALLY COMPLETE | ORM models and migrations `0001`–`0006` exist. Online migration/pgvector verification claims conflict. |
| 3. Domain services and API | PARTIALLY COMPLETE | Case/process/task/approval and other services/routes exist. Checklist explicitly defers a backend-wide tenant-isolation review. |
| 4. Workflow Engine | PARTIALLY COMPLETE | Deterministic validation and execution services, stage/transition models, tests and history/audit logic exist. Organization/permission enforcement across workflow routes needs confirmation. |
| 5. Rules and deterministic verification | PARTIALLY COMPLETE | Rule/calculation evaluation, execution records, evidence and tests exist. Full orchestration into a case workflow remains later roadmap work. |
| 6. Tool Gateway | PARTIALLY COMPLETE | Core registry, policy checks, schemas, execution trace, and Document/Verification Agent usage exist. Workflow/Supervisor integration and some real external adapters remain. |
| 7. Object storage and upload | PARTIALLY COMPLETE | Local adapter, validation, tenant-aware upload/download and tests are documented. Production cloud adapter/deployment remains open. |
| 8. Document Intelligence | PARTIALLY COMPLETE | Parsing, OCR, classification/extraction and provenance exist. Broader labeled accuracy and durable processing remain open. |
| 9. Knowledge / RAG | PARTIALLY COMPLETE | Ingestion, embedding adapters, organization filter, pgvector schema, search API and Gateway search exist. Relevance-quality evidence is small/manual; database validation record conflicts. |
| 10. Document Agent | PARTIALLY COMPLETE | Agent, citations, review handling, API, execution trace and narrow live Groq evaluation exist. It can access knowledge search, but extraction does not yet consume retrieved policy results. |
| 11. Verification Agent | PARTIALLY COMPLETE | Stage-scoped planning, gateway execution, deterministic result separation and review proposal exist. Focused test does not show model-selected PASS/FAIL; live inference/quality is unevaluated. |
| 12. Workflow Agent | NOT STARTED | Current dispatcher returns a fixed proposal; no real context builder, adapter call, validation, workflow handoff, or execution trace. |
| 13. Supervisor Agent | NOT STARTED | Delegation and case-level coordination remain planned. |
| 14. Model Gateway | NOT STARTED | Provider-neutral routing, reliability policy and standardized usage logging remain planned. |
| 15. Case Orchestrator | NOT STARTED | Event-driven multi-agent loop remains planned. |
| 16. Human-in-the-Loop | PARTIALLY COMPLETE | Tasks and approvals exist with audit/event records; full orchestration/routing integration is not complete. |
| 17. Complete Import/Export MVP | NOT STARTED | Checklist and progress report identify the end-to-end MVP as a later target. |
| 18. Frontend | NOT STARTED | Frontend directories/placeholders exist; no application implementation is in the inspected inventory. |
| 19. Authentication and Authorization | PARTIALLY COMPLETE | JWT/RBAC foundations and gateway policies exist; checklist explicitly leaves an API-wide tenant-scope review open. |
| 20. Security | PARTIALLY COMPLETE | Guardrails and some tenant-isolation tests exist; system-wide authorization, prompt-injection and deployment review remain open. |
| 21. Events and Auditability | PARTIALLY COMPLETE | Event/audit models and service calls exist; complete cross-agent trace/orchestrator linkage remains open. |
| 22. Testing | PARTIALLY COMPLETE | Broad pytest coverage and opt-in live tests exist, but test totals conflict and multiple acceptance/evaluation gaps remain. |
| 23. AI and System Evaluation | PARTIALLY COMPLETE | Small live samples have been recorded; reusable representative evaluation suites and metrics are not established. |
| 24. Generalization Test | NOT STARTED | Dedicated second-process acceptance test is explicitly planned. |
| 25. Final Documentation | PARTIALLY COMPLETE | Rich docs exist but README, progress, checklist and Phase 9 validation/test totals drift. |
| 26. Final Demonstration | NOT STARTED | Demo requirements are documented; a completed end-to-end demonstration is not evidenced. |

## 4. Recent Commit Analysis

Recent history is evidence of work, not proof of completion:

- `477a912 — Update README to remove Phase 9 Implementation Plan`: edits README phase/test language. README still identifies Phase 10 as current, while the progress report says Phase 11 is implemented and Phase 12 next.
- `f7da0bd — Implement Phase 11 Verification Agent`: adds the Verification Agent, tests, and architecture/checklist/progress changes. Tests cover gateway execution, persistence, result separation, review escalation, and rejection of unavailable tools. The focused test's verification definition has no linked rules, yielding `NOT_APPLICABLE`.
- `00cf8cd — Add Groq Document Agent and validate AI runtime`: configures Groq JSON inference, adapter contracts, and opt-in live tests. Groq is the configured Document Agent provider; Gemini code remains but is not the configured path.
- `19bb1b8 — Record live dataset evaluation results`: records small retrieval/ingestion checks and ignores downloaded samples. It does not supply a reusable labeled scoring harness.
- `2a4a0d0 — Configure Cloudflare embeddings and Gemini document inference`: adds Cloudflare adapter/configuration and mocked tests. Subsequent docs/code say Groq is configured for Document Agent; Gemini is retained/unused for that path.
- `d9cd3db — Strengthen Phase 9 knowledge and Phase 10 document agent`: adds the Document Agent, tenant/security coverage, and Gateway search access. The extraction prompt still does not consume retrieved policy context.

## 5. Documentation vs. Implementation Reconciliation

The authoritative roadmap is `Documentation/Verifia_Detailed_Implementation_Checklist.md` plus `Documentation/progress_report.md`, read with architecture baseline documents `Documentation/01-product-overview.md` through `Documentation/04-operations-and-roadmap.md`.

The checklist's Phase 12 contract calls for structured action schema, context builder, model call, action validation, Workflow Engine handoff, and invalid-proposal handling. It states the agent proposes actions, cannot directly change case stage, and the Workflow Engine remains authoritative. The implementation currently has a WORKFLOW branch in `backend/app/agents/service.py` that returns a fixed “propose stage transition” response without examining case state or calling a model/service.

The documentation does not call for a new database or framework. Phase 14 intentionally follows Workflow and Supervisor contracts; Phase 23 owns comparative model-quality evaluation. The next milestone should implement the agent contract while fixing the security boundary it would rely on.

## 6. Phase 9 Status

**Status: PARTIALLY COMPLETE.**

Implemented pieces include:

- `backend/app/domain/knowledge/chunker.py`, `service.py`, `router.py`, `models.py`, and `schemas.py` for chunking, ingestion, retrieval and API.
- `backend/app/infrastructure/llm/embedding.py` for Cloudflare BGE-M3 default plus optional adapters/test adapter.
- Migration `backend/alembic/versions/0006_knowledge_rag.py` for 1024-dimension vector support, organization scope, HNSW definition and ingestion lifecycle columns.
- Organization filter in retrieval and source/document security tests.
- Gateway `search_knowledge` capability with bounded query/top-k schema and allowed-agent configuration.

The runtime chain is `.env` in the process working directory → Pydantic `Settings` in `backend/app/core/config.py` → `get_embedding_adapter()` → Cloudflare Workers AI when `EMBEDDING_PROVIDER=cloudflare` → external embedding request. Relevant settings: `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL_NAME`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, and `CLOUDFLARE_AI_BASE_URL`. Credentials are optional during settings construction and required when the Cloudflare adapter is used; adapter failure should fail the operation rather than substitute fake vectors.

The report describes small live cosine comparisons (SROIE text 4/5 first, 5/5 top-three; synthetic set 4/4 first) and ingestion checks. These are not a statistical benchmark. SQLite fallback search does not establish pgvector relevance ranking. The detailed progress report and Phase 9 plan say online migration/vector ranking remain unverified, while other Phase 9/10 summary text says local PostgreSQL/pgvector checks passed. Resolve the discrepancy with one dated DB run and one maintained record.

## 7. Phase 10 Status

**Status: PARTIALLY COMPLETE.**

`backend/app/agents/document_agent.py` uses document-processing services, validates structured classification/extraction and citations, can propose human review, and persists an agent trace. `search_knowledge` is exposed to configured identities through the Gateway, but the Document Agent extraction prompt does not consume retrieved policy output. Therefore Gateway accessibility does not mean RAG-grounded document processing is integrated.

The progress report records a live Groq evaluation of three generated clean-text documents: 3/3 classifications, 17/17 expected field values, 17/17 citations. This is a narrow smoke/evaluation sample. Varied layouts, OCR noise, missing/ambiguous fields, larger labels, and broad accuracy remain untested. OCR check covers a small SROIE sample; scanned-PDF and broader accuracy work remains open. Durable background processing is also open.

Relevant provider chain is `Settings` → `DOCUMENT_MODEL_PROVIDER` (Groq by default) → Groq adapter in `backend/app/domain/documents/intelligence.py` → configured Groq endpoint/model. `GROQ_API_KEY` and fallback keys are used on provider invocation; timeout/retry/model values have defaults. Ollama and Gemini settings/adapters are optional paths, not Phase 12 requirements.

## 8. Phase 11 Status

**Status: PARTIALLY COMPLETE.**

`backend/app/agents/verification_agent.py` assembles organization-scoped case/evidence context, stage-applicable verification definitions, and Gateway-exposed tools. It validates selected IDs and tool availability, calls `ToolGatewayService`, and returns deterministic results separately from model interpretation. Missing information, discrepancies, missing required documents, failures and inconclusive results can yield a human-review proposal. The agent records `AgentExecution`; tools record executions.

The focused tests cover actual configured deterministic service invocation and trace preservation, but the featured test definition has no linked rules and returns `NOT_APPLICABLE`. Rule PASS/FAIL behavior is tested separately in `test_rules_and_verifications.py`. Live Verification Agent inference/quality has not been evaluated. No complete event-driven reviewer task/orchestrator loop is evidenced.

## 9. AI / Dataset Evaluation Status

| Work | Completed per repository documentation | Not established |
|---|---|---|
| Document Agent / Groq | Three generated documents, classifications, field exact matches and citations passed | Broad accuracy, robustness to OCR/noisy layouts, ambiguity and missing fields |
| Embeddings / Cloudflare | Small SROIE, DocLayNet text-cell and synthetic comparisons; sample vectors normalized | Statistically robust relevance and production-scale behavior |
| Knowledge ingestion | Small sample ingestion persisted through service | Vector-ranking quality where SQLite fallback is used; durable retry/large-corpus behavior |
| OCR / Tesseract | One SROIE image check passed per progress report | Scanned-PDF and varied labeled OCR accuracy |
| PostgreSQL / pgvector | Conflicting pass/unverified records in current docs | A single reproducible, dated migration + HNSW ranking result |
| Verification Agent | Fake/contract tests and deterministic service coverage | Live model quality or repeatable quality benchmark |
| Gemini | Historical provider use/limitations noted; not configured current Document Agent provider | Any requirement that Gemini be a Phase 12 dependency |

`backend/tests/test_live_integrations.py` is opt-in with `VERIFIA_RUN_LIVE_TESTS=1`, external credentials, local OCR, and a database. Downloaded evaluation samples are ignored by Git. Live-provider or dataset absence is an infrastructure/provider limitation where applicable; missing reusable metrics/harness is a testing gap; incorrect application behavior is a product defect. Do not classify a provider 503 as a Verifia product bug without evidence of faulty adapter behavior.

## 10. Current Architecture Status

The architecture still intends: **UNDERSTAND → VERIFY → ORCHESTRATE → ACT → VERIFY → CONTINUE / ESCALATE**. PostgreSQL is authoritative; a Case binds to a published ProcessVersion; agents propose; the Gateway controls tool access; deterministic services enforce rules, calculations, permissions and workflow transitions; human approvals are explicit.

Integration actually evidenced:

- Document Agent → Tool Gateway: yes for configured tools; knowledge search is accessible.
- Knowledge retrieval → Document Agent extraction prompt: no.
- Verification Agent → Tool Gateway → deterministic Verification Service: yes.
- Verification result → complete human review workflow: proposal exists, but full orchestrated task/escalation loop is later work.
- Workflow Agent → Workflow Engine: no; hard-coded proposal only.
- Supervisor delegation and event-driven Case Orchestrator: planned, not implemented.
- Durable job queue: no; current queue module is a stub.
- External inventory/customer/payment adapters: Gateway contracts exist, but no usable provider configuration/credential contract is documented.

Thus Verifia remains a configurable business-process platform rather than a chatbot, but the complete end-to-end process loop is not yet integrated.

## 11. Missing / Incomplete Work

1. Real Workflow Agent contract/context/validation/handoff/trace (Phase 12).
2. Route- and service-level workflow tenant/authorization guarantees before exposing model-mediated action.
3. Consistent action semantics: distinguish recommendations, tool execution, human approval, and actual transition result.
4. Current end-to-end orchestration, Supervisor and durable jobs (later roadmap phases).
5. Document Agent use of retrieved policy context, if/when explicitly scoped.
6. Repeatable retrieval and broader document/OCR evaluations.
7. API-wide tenant isolation audit.
8. Authoritative test-count and DB-validation records.
9. Production integration adapters and deployment storage decisions, once contracts exist.

## 12. Recommended Next Milestone

### Phase 12 — Workflow Agent

**Objective:** Replace the fixed placeholder with a structured, auditable agent that reads bounded case/workflow facts, proposes one or more allowed actions, validates all references against the active process version, and hands permitted work to deterministic services through the Tool Gateway.

**Why now:** It is the official next phase, depends on already implemented Workflow Engine, verification results, tasks/approvals and Tool Gateway, and is a prerequisite to Supervisor/Case Orchestrator work. It addresses an existing integration gap rather than introducing an unrelated feature.

**Prerequisites:** (1) lock proposal-versus-execution semantics, (2) enforce organization/resource authorization at workflow service boundaries, (3) agree process-configured action allowlist and human-review behavior. Use injected fake adapters. No live model-quality target.

**Dependencies:** Phases 3–6, 11; reuse `WorkflowService`, `ToolGatewayService`, existing case/process/task/approval/verification models, `AgentExecution`, events and audit.

**Architecture impact:** New Workflow Agent context/plan/validation layer; existing deterministic services remain authoritative. No new framework or microservice.

**Database impact:** No schema change expected. Reuse existing trace/tool/event/audit records.

**API impact:** Dispatch through `/api/v1/agents/run`; keep request/response backward-compatible if possible; clearly distinguish a proposal from executed action/result.

**AI impact:** Inject existing `JsonModelAdapter`; strict structured outputs, bounded context and IDs; no model-created arbitrary tool names or direct state mutation.

**Security impact:** Tenant isolation, actor permissions, stage/version validation, process allowlists, prompt-injection boundary, bounded data exposure, trace redaction.

**Testing impact:** Unit, service, API, gateway, security and end-to-end contract tests with fakes. Follow checklist DoD and use existing workflow-engine tests. Live connectivity belongs to Phase 14; quality comparison belongs to Phase 23.

**Documentation/deployment:** Update README/progress/checklist/architecture at completion; no new configuration or deployment dependency anticipated.

## 13. Detailed Implementation Plan

All implementation tasks should preserve existing API and schema unless a demonstrated requirement forces a change. Each task's likely file targets are guidance based on inspected structure, not a claim that every path must change.

### WFA-01 — Specify structured action contract and authority boundary (P0)

- **Objective / why:** Define finite action types, required fields, result states, and which are proposals vs executable calls; prevent model text from being mistaken for an authoritative transition.
- **Likely files:** `backend/app/agents/schemas.py`, `backend/app/agents/service.py`, new `backend/app/agents/workflow_agent.py`, new `backend/tests/test_workflow_agent.py`.
- **Reuse / new:** Reuse `AgentProposal`, `AgentRunRequest/Response`, JSON adapter contract; add typed Workflow Agent action/result models and allowlist validator.
- **Database:** None. Use existing `AgentExecution`.
- **API:** Preserve `/agents/run`; version/extend response only if action union requires it.
- **Configuration / dependencies:** None new; depends on checklist Phase 12, Verification Agent pattern, workflow schema.
- **Security / error handling:** Treat case/document/model strings as untrusted; unknown actions/fields/IDs fail closed; model confidence never grants permission.
- **Logging/audit:** Record structured inputs/outputs and safe failure reason in `AgentExecution`.
- **Tests:** Allowed/unknown action; malformed IDs; extra fields; oversized arrays/strings; proposal is not execution.
- **Acceptance / DoD:** Finite documented contract; no arbitrary code, SQL, URL, or tool-name field; every action's authority is explicit.

### WFA-02 — Scope workflow lookups and authorize operations (P0)

- **Objective / why:** Ensure Workflow Agent cannot read or act on another organization’s case/process/stage. Inspected workflow routes depend on `get_current_user` but do not pass organization scope to the service; `validate_transition` loads a case by ID without an organization predicate.
- **Likely files:** `backend/app/domain/workflows/router.py`, `backend/app/domain/workflows/service.py`, `backend/app/tools/service.py`, workflow/API/Gateway tests.
- **Reuse / new:** Reuse `User.organization_id`, case/process ownership, Gateway’s existing checks and role policy; add scoped service methods/guards only where missing.
- **Database:** None expected; confirm FK and process-version relationships before design.
- **API:** Keep routes; return non-disclosing 404 for cross-tenant resource IDs and 403 for authenticated but disallowed actions.
- **Configuration / dependencies:** No new env var; depends on WFA-01 and an audit of how cases/processes are fetched.
- **Security / errors:** Bind case, actor, process version, stage and transition; reject mismatched ownership and terminal cases.
- **Logging/audit:** Audit denied consequential actions without logging sensitive source contents.
- **Tests:** Cross-tenant reads/writes; unowned process/stage; wrong role; case/process version mismatch; stale stage.
- **Acceptance / DoD:** Service-level scope holds even when not called through HTTP; routes cannot bypass it.

### WFA-03 — Build bounded, reproducible workflow context (P1)

- **Objective / why:** Supply only facts needed for workflow recommendation and grounding.
- **Likely files:** `backend/app/agents/workflow_agent.py`; reuse models/services in cases, processes, workflows, verifications, tasks, approvals; tests in `test_workflow_agent.py`.
- **Reuse / new:** Reuse `Case`, `WorkflowStage`, `WorkflowTransition`, `VerificationExecution`, `Task`, `Approval`; add read-only context builder.
- **Database/API/config:** Read-only queries; no migration, endpoint, or setting expected.
- **Dependencies:** WFA-02; establish authoritative definitions of current status/open tasks/pending approvals.
- **Security / errors:** Scope every query by actor organization and case; bound record count/text; omit secrets and unnecessary raw document text; empty/terminal state yields explicit context status.
- **Logging/audit:** Include source record IDs/version/stage IDs in trace; avoid logging raw sensitive fields.
- **Tests:** Relevant stage only; correct process version; open vs completed tasks; pending vs decided approvals; empty and terminal case; context limits.
- **Acceptance / DoD:** Same DB snapshot yields same context; every material recommendation can point to supplied record IDs.

### WFA-04 — Implement model planning and strict validation (P1)

- **Objective / why:** Replace hard-coded response with a contract-tested Workflow Agent.
- **Likely files:** `backend/app/agents/workflow_agent.py`, `backend/app/agents/schemas.py`, `backend/app/agents/service.py`.
- **Reuse / new:** Existing `JsonModelAdapter`, fake-adapter injection, Verification Agent structured schema/validation patterns.
- **Database/API/config:** Persist trace in `AgentExecution`; no migration/config; return action and explicit proposal state.
- **Dependencies:** WFA-01 and WFA-03.
- **Security / errors:** Validate action against context, process config and actor-visible tools; invalid JSON/provider failure returns safe error and failed trace; no direct DB writes from model output.
- **Logging/audit:** Record adapter/model metadata available today and execution status; redact secrets and raw provider response as needed.
- **Tests:** Each action kind, unknown/stale IDs, invalid stage, no available action, malformed output, provider exception, disabled agent.
- **Acceptance / DoD:** All returned proposals are schema-valid and context-grounded; invalid output never reaches an action handler.

### WFA-05 — Connect allowed actions to Gateway and deterministic services (P1)

- **Objective / why:** Ensure agent capabilities use the policy boundary and deterministic implementations. Current Gateway includes `create_task` and `request_approval` allowed for WORKFLOW, but no registered transition tool is evident; `run_verification` currently excludes WORKFLOW.
- **Likely files:** `backend/app/tools/service.py`, `backend/app/tools/schemas.py`, `backend/app/domain/workflows/service.py`, Workflow Agent and gateway tests.
- **Reuse / new:** Reuse existing tool registry, `WorkflowService.validate_transition/execute_transition`, TaskService, ApprovalService. Add a narrowly scoped transition tool delegated to `WorkflowService`; allow `run_verification` for WORKFLOW only under process-level tool policy. Map `REQUEST_DOCUMENT` and `ESCALATE` to validated human tasks through the existing `create_task` tool. Do not add parallel business logic.
- **Database:** Existing case stage history, tool executions, tasks, approvals; no migration expected.
- **API:** No new public endpoint required; Gateway call is internal to trusted orchestrator.
- **Configuration:** Reuse process-version `tool_gateway.allowed_tools`/`allowed_agents`; no env variable.
- **Dependencies:** WFA-02, WFA-04.
- **Security / errors:** Validate tool permission, actor role, current stage, case/process binding and workflow requirements before mutation. Never auto-retry side-effect tools; gateway denial is a rejection/review result.
- **Logging/audit:** Existing ToolExecution plus Workflow Engine event/audit; link execution IDs to AgentExecution.
- **Tests:** Tool disabled/allowed; task/approval request; failed request; stale stage; missing requirement/approval; actual transition only after deterministic checks; duplicate request/idempotency expectation.
- **Acceptance / DoD:** Every agent-requested state effect crosses Gateway and domain service; no model-provided result is authoritative. Workflow Engine handoff is implemented through the new bounded transition tool, with process policy and human approval checks enforced before state changes.

### WFA-06 — Persist trace and connect review outcomes (P1)

- **Objective / why:** Let a reviewer reconstruct proposal, tool calls and authoritative outcome.
- **Likely files:** `backend/app/agents/workflow_agent.py`, `backend/app/events/service.py`, `backend/app/domain/audit/service.py`, tests.
- **Reuse / new:** `AgentExecution`, `ToolExecution`, `EventRecord`, `AuditLog`; add no duplicate agent-run table.
- **Database/API/config:** Existing JSON trace fields expected to suffice. Only propose migration after identifying query/replay need and review retention; no setting expected.
- **Dependencies:** WFA-04/05.
- **Security / errors:** Redact credentials and unnecessary document text; store failed and rejected status distinctly; trace write failure must not falsely report successful transition.
- **Logging/audit:** Link case, organization, actor, agent, tool execution, workflow result and event IDs.
- **Tests:** Success/rejection/failure traces; trace links and tenant ownership; redaction; DB rollback/commit behavior around transition.
- **Acceptance / DoD:** Execution ID gives a complete audit path without turning model rationale into a source of truth.

### WFA-07 — Complete API dispatch and error mapping (P1)

- **Objective / why:** Replace WORKFLOW placeholder via existing API.
- **Likely files:** `backend/app/agents/service.py`, `backend/app/agents/router.py`, `backend/app/agents/schemas.py`, agent/API tests.
- **Reuse / new:** Existing `/api/v1/agents/run`; DOCUMENT/VERIFICATION dispatch patterns.
- **Database/API/config:** Preserve existing request fields and response where possible; distinguish `PROPOSED`, `REJECTED`, and `EXECUTED` states; no new setting.
- **Dependencies:** WFA-01–06.
- **Security / errors:** Map authz, not-found, schema, provider and infrastructure errors separately; avoid returning internal exception text/secrets.
- **Logging/audit:** Return execution ID and linked result identifiers.
- **Tests:** API success/proposal, cross-tenant case, invalid model response, missing case, disabled agent, gateway rejection and internal provider failure.
- **Acceptance / DoD:** Endpoint never says transition completed unless Workflow Engine confirms it.

### WFA-08 — Documentation and completion review (P1)

- **Objective / why:** Keep roadmap claims aligned with verified code.
- **Likely files:** `README.md`, `Documentation/progress_report.md`, `Documentation/Verifia_Detailed_Implementation_Checklist.md`, `Documentation/02-architecture.md`, possibly API/config docs.
- **Reuse / new:** Update existing docs; no new architecture framework.
- **Database/API/config:** Document actual migration/API/setting changes only.
- **Dependencies:** WFA-01–07 and implementation validation.
- **Security / errors:** Document authority boundaries, tenant behavior, provider transfer and failure handling; never include secrets.
- **Tests/evidence:** Map every Phase 12 criterion to a test or explicitly recorded manual verification. Reconcile test totals and database validation status.
- **Acceptance / DoD:** README, progress and checklist agree on current phase, test result, limitations and next phase.

## 14. Database Changes

**No Phase 12 schema change is currently justified.** Reuse:

- `agent_definitions` and `agent_executions` from `backend/app/agents/models.py`.
- `cases` and immutable `process_version_id`.
- `workflow_stages`, `workflow_transitions`, and `case_stage_history`.
- Verification execution/result/evidence records; tasks and approvals.
- Tool execution, event and audit records.

Do not create a duplicate workflow-state table or proposal table. If implementation proves JSON trace fields inadequate, state the concrete query/replay/retention requirement first. Any later migration should specify FK ownership, tenant scope, indexes, constraints, immutability/retention, migration predecessor, data backfill and rollback. Migration rollback must not erase authoritative case history.

## 15. API Changes

Use current `POST /api/v1/agents/run` with `agent_type=WORKFLOW`. Prefer a backwards-compatible typed `result_data` and proposal status. Do not trust client-supplied actor, role, organization, current stage or tool authority; derive identity from authenticated user and persisted case state.

Workflow API routes are defined in `backend/app/domain/workflows/router.py`. The reviewed handlers inject `get_current_user`, but pass stage/transition requests to service methods without visibly passing organization scope. The implementation phase must verify/fix service-level scoping and actor authorization, not just add checks to the agent route. Use 404 for cross-tenant resource concealment and 403 for an authenticated but unauthorized operation.

## 16. Agent / AI Changes

The Workflow Agent should accept an injected existing JSON model adapter. Its bounded context should include current case status/stage and process version, configured transitions/requirements for that stage, relevant verification outcomes/evidence IDs, open tasks and pending approvals. It should not ingest the entire document corpus or use knowledge retrieval absent a specific workflow-policy requirement.

Output should be a finite allowlisted structured action with rationale and source IDs. A recommendation is distinct from a tool invocation; a tool invocation is distinct from an authoritative business outcome. The model may suggest `REQUEST_DOCUMENT`, `RUN_VERIFICATION`, `CREATE_TASK`, `REQUEST_APPROVAL`, `PROPOSE_TRANSITION`, or `ESCALATE` per checklist. Map document requests and escalations to validated tasks; route verification and approval requests through their existing Gateway tools; route transitions through the new deterministic transition tool. The deterministic service decides whether any requested action is permitted. For now do not attach provider-quality claims. Phase 14 owns model connectivity smoke checks; Phase 23 owns comparative evaluation.

## 17. Tool Gateway Changes

`backend/app/tools/service.py` has registered tools including `check_required_documents`, `search_knowledge`, `run_verification`, `create_task`, and `request_approval`; Workflow is allowed for some (including task/approval) under process policy. `run_verification` is currently allowed to Verification/Supervisor identities, not Workflow. No case-transition tool appears among the inspected registrations.

Reuse `ToolGatewayService` and process config `tool_gateway.allowed_tools`. Phase 12's target includes Workflow Engine handoff, so add a minimal transition tool delegated to `WorkflowService` and enforce all requirements. Permit `run_verification` for the Workflow identity only where the process allowlist enables it. Map document requests/escalations to the existing task tool and approval requests to `request_approval`. The transition tool must re-read case state and deterministic policy at execution time; pending human approval blocks the transition. Never allow model to call an arbitrary tool or invoke business services outside trusted orchestration. Persist success, denial and failure; do not retry side effects without idempotency.

## 18. Security Requirements

- Tenant scope every case/process/stage/transition/evidence/task/approval lookup at route and service boundary.
- Bind a case to its original published ProcessVersion; reject cross-version transitions.
- Enforce actor permission, agent identity, process allowlist, tool schema and action-specific policy in Gateway.
- Validate all model-provided IDs against current context and recheck current stage at execution time to avoid stale proposals.
- Treat uploaded documents, retrieved passages and case text as untrusted data, never as instructions.
- Bound context size, model output, tool-call count, query size and external requests.
- Prevent arbitrary SQL, code, URLs, SSRF and unrestricted external API calls.
- Minimize fields sent to external model; redact credentials and sensitive provider errors from output/trace.
- Record allowed and rejected actions, responsible actor, deterministic outcome, and human approval identity/time.
- Test cross-tenant resource access, unauthorized tools, malicious prompt content, stale stage, terminal case, and bypass attempts.

## 19. .env / Configuration Requirements

Phase 12 should add **no new environment variables**. The runtime chain is:

`root .env` or `backend/.env` (depending on working directory) → Pydantic `Settings` in `backend/app/core/config.py` → `get_json_model_adapter()` and existing `DOCUMENT_MODEL_PROVIDER` selection → Workflow Agent → provider request when invoked.

| Setting | Purpose / consumer | Required/default/startup behavior | Phase 12 verification |
|---|---|---|---|
| `DOCUMENT_MODEL_PROVIDER` | Selects configured JSON model adapter used by agent | Default is Groq; provider-specific credentials are not globally required at settings load | Fake adapter tests; invalid provider and missing-key failure safely reported |
| `GROQ_API_KEY` plus optional fallbacks | Auth for Groq adapter | Optional in settings; required only for live Groq call; missing key should fail invocation, not unrelated startup | Mock missing-key and failure path; no live quality claim |
| `GROQ_DOCUMENT_MODEL` | Groq model identifier consumed by configured JSON adapter | Default in Settings and both env templates | Assert adapter receives configured model |
| `GROQ_API_BASE_URL` | Groq endpoint used by adapter | Default in Settings/env templates; only used on Groq path | Mock endpoint construction and failure behavior |
| `GROQ_REQUEST_TIMEOUT_SECONDS`, `GROQ_MAX_RETRIES`, `GROQ_RETRY_BASE_SECONDS` | Provider timeout/retry policy | Defaults in Settings/env templates | Unit-test timeout/retry; never retry side-effecting tools |
| `GROQ_API_KEY_FALLBACK_1`, `GROQ_API_KEY_FALLBACK_2` | Ordered credential fallbacks on provider errors | Optional; empty/unset by default | Existing adapter tests verify fallback ordering; never log values |
| `OLLAMA_BASE_URL`, model settings | Optional local adapter | Defaults present; only if provider selected | Inject fake adapter in Phase 12 |

`Settings` reads `.env` relative to current process directory; README documents root and backend-local copies. Keep secrets out of logs and documentation. Do not add a Workflow-specific model selector before Phase 14 Model Gateway. Fail safely at invocation when the chosen provider cannot be configured; do not block API startup for optional external AI.

## 20. Testing Plan

This is derived from checklist Phase 12, workflow-engine requirements, Tool Gateway requirements and documented architecture. Tests are proposed here, not executed during this planning task.

**Existing tests to reuse:** `backend/tests/test_workflow_engine.py`, `test_verification_agent.py`, `test_document_agent.py` (Gateway assertions), `test_rules_and_verifications.py`, `test_domain_api.py`, `test_config.py`, `test_external_model_adapters.py`. No standalone `test_tools.py` appeared in the inspected test inventory.

**Required new tests:**

1. Structured action schema, allowlisted actions and unknown-field rejection.
2. Context scope to actor organization, case's bound version and active stage.
3. Valid and invalid proposal for each action type; unavailable tool; unknown/stale record IDs.
4. Deterministic engine denial for stale stage, wrong process version, terminal case, missing document/verification/approval, wrong role.
5. Cross-tenant requests rejected at both API and service layers.
6. Model malformed response, provider exception, disabled agent and empty/oversized context fail closed and trace failure.
7. Gateway authorization/allowlist denial is preserved, not converted into a successful action.
8. No case mutation from model output alone; any stage update only follows an authorized successful deterministic transition.
9. Event/audit/AgentExecution/ToolExecution links are consistent and do not contain secrets/raw unnecessary text.
10. API clearly distinguishes proposal, rejection, execution and deterministic result.
11. Prompt-injection-shaped document content cannot alter action or permission allowlists.

**Existing tests:** present in repository; exact current pass totals conflict in docs. **Missing tests:** dedicated Workflow Agent contract/API/integration suite and workflow route/service cross-tenant coverage. **Recommended additions:** concurrent stale-stage execution and idempotency for side-effecting tool requests. Live API quality is not required for Phase 12; adapter smoke checks belong to Phase 14 and comparative quality work to Phase 23.

## 21. End-to-End Validation Plan

Scenario: employee invokes the Workflow Agent for an import/export case at “Document Review.”

1. API authenticates actor and loads the case only within the actor's organization.
2. Service loads the case's immutable ProcessVersion, current stage, configured transitions/requirements, latest relevant verification status, open tasks and pending approvals.
3. Model returns structured `PROPOSE_TRANSITION` or `REQUEST_APPROVAL` with IDs from supplied context.
4. Validator rejects unsupported, stale, cross-version or out-of-scope references.
5. If a configured action is eligible for execution, trusted orchestrator calls Tool Gateway; Gateway checks actor permission, allowed agent/tool, process configuration, schema and case scope.
6. Workflow/approval service applies deterministic requirements and checks current state again. Missing human approval blocks transition; the model cannot supply approval.
7. API response distinguishes proposal, gateway call and authoritative workflow result.
8. `AgentExecution`, `ToolExecution`, `EventRecord`, `AuditLog`, and stage history link to the case and actor.
9. Rejected, failed, unavailable-provider, cross-tenant or stale-stage paths leave state unchanged and are traceable.

This validates Phase 12 integration; it does not claim Supervisor or full Case Orchestrator completion.

## 22. Documentation Updates Required

- Update README status to Phase 11 implemented / Phase 12 next now; only label Phase 12 current/complete after evidence exists.
- At completion update Phase 12 checklist criteria with links to tests/evidence.
- Reconcile 100/102/older test totals and record the exact run and command in one canonical place.
- Resolve the conflicting online PostgreSQL/pgvector validation record with a dated execution result.
- Update architecture docs to show proposal → Gateway authorization → deterministic Workflow Engine → state/event.
- Document external model data path, required-on-invocation credentials, errors, timeouts, and safe failure.
- Document Phase 12 scope and deferrals: no Supervisor, Case Orchestrator, durable queue, broad model-quality claim, or complete MVP.
- Keep repository layout docs aligned with current checked-in paths.

## 23. Blockers

| Severity | Blocker | Impact / action | Blocks Phase 12? |
|---|---|---|---|
| High | Workflow route/service organization and permission enforcement is not established in inspected handlers | Verify and implement service-level tenant/resource guards before agent actions | Yes, for consequential actions |
| High | Proposal vs execution boundary is underspecified | Adopt typed proposal result and deterministic action policy before model integration | Yes |
| Medium | Workflow transition tool absent from inspected Gateway registry | Add the narrowly scoped Gateway tool delegating to WorkflowService | Yes, for the documented engine handoff |
| Medium | DB/pgvector validation status conflicts across docs | Reconcile evidence; required for honest readiness claim, not core Phase 12 | No |
| Medium | Test totals conflict | Record one authoritative run at implementation completion | No for development, yes for completion claim |

## 24. Risks and Technical Debt

| Severity | Category | Issue / affected area | Recommended action | Blocks Phase 12? |
|---|---|---|---|---|
| High | Security | Workflow API/service scope and actor checks | Add defense-in-depth scope and cross-tenant tests | Yes for writes |
| High | Integration | Workflow dispatch is a placeholder | Implement Phase 12 contract and Gateway handoff | Core scope |
| High | Architecture | Supervisor/event-driven loop absent | Keep Phase 12 narrowly scoped; schedule phases 13–15 | No |
| Medium | Evaluation | Retrieval comparisons are small/manual; model sample narrow | Build labeled repeatable evaluation on roadmap schedule | No |
| Medium | Operations | Queue stub does not durably enqueue | Implement in planned background-processing/productization milestone | No |
| Medium | Observability | Agent and tool traces are not a unified orchestration trace | Link existing records; improve standardized tracing in Phase 14/15 | Partial |
| Medium | Documentation | README, progress/checklist and phase plan disagree | Reconcile in Phase 12 closeout | Yes for completion claim |
| Medium | Integration | Real inventory/customer/payment adapters lack provider contracts | Defer until contracts/credentials exist | No |
| Low | Productization | Cloud object storage deployment adapter absent | Select deployment needs before production rollout | No |

## 25. Prioritized Roadmap

- **P0 — Blocking:** Enforce workflow tenant/actor/resource scope; define action authority and proposal/execution result semantics.
- **P1 — Required for Phase 12:** Build bounded context, structured Workflow Agent, validator, minimal Gateway/deterministic handoff, trace, API mapping, and documented tests.
- **P2 — Important but can follow:** Reconcile suite and DB status records; broad OCR/document/retrieval evaluation; durable workers; production storage and external adapters when contracts are known.
- **P3 — Future:** Phase 13 Supervisor → Phase 14 Model Gateway → Phase 15 Case Orchestrator → Phase 16 human review integration → Phase 17 Import/Export MVP → Phase 23 AI/system evaluation → Phase 24 generalization, following checklist dependencies.

Recommended sequence: security boundary → action contract → context builder → model proposal/validator → Gateway/deterministic execution → trace → API/security/integration tests → documentation reconciliation → mark Phase 12 complete.

## 26. Definition of Done

- Workflow Agent emits validated structured proposals grounded in scoped case/workflow context.
- Unknown, stale, unauthorized, cross-tenant, terminal-state or process-version-mismatched actions are rejected.
- Model output alone cannot mutate case/workflow state; consequential actions go through Gateway and deterministic services.
- Workflow Engine enforces transitions, requirements, roles and approval gates.
- Success, denial and failure produce linked safe agent/tool/event/audit traces.
- Focused, API, security, gateway and end-to-end tests pass, alongside the documented backend regression suite; counts are recorded consistently.
- README, progress report, checklist and architecture docs agree on implementation and limitations.

## 27. Final Recommendation

Implement **Phase 12 — Workflow Agent** next, beginning with organization-scoped authorization and explicit proposal/action boundaries. Reuse the current case/workflow/verification/task/approval models, Tool Gateway and deterministic Workflow Engine. Do not add a database, framework, queue, or Workflow-specific provider configuration without demonstrated need. Keep the model an interpreter/planner; only deterministic, authorized services can establish a business result.

## Review evidence and source documents

Primary documents reviewed: [README](../README.md), [Documentation index](README.md), [Product Overview](01-product-overview.md), [Architecture](02-architecture.md), [Database Schema](03-database-schema.md), [Operations and Roadmap](04-operations-and-roadmap.md), [Implementation Checklist](Verifia_Detailed_Implementation_Checklist.md), [Progress Report](progress_report.md), and [Phase 9 plan](09-phase9-implementation-plan.md).

Code/tests reviewed include `backend/app/agents/service.py`, `backend/app/agents/verification_agent.py`, `backend/app/agents/document_agent.py`, `backend/app/agents/models.py`, `backend/app/core/config.py`, `backend/app/domain/workflows/router.py`, `backend/app/domain/workflows/service.py`, `backend/app/domain/workflows/models.py`, `backend/app/tools/service.py`, `backend/app/infrastructure/queue/queue.py`, migrations `0001`–`0006`, and relevant tests under `backend/tests/` including `test_verification_agent.py`, `test_workflow_engine.py`, `test_rules_and_verifications.py`, `test_knowledge_security.py`, `test_document_agent.py`, `test_external_model_adapters.py`, and `test_live_integrations.py`.

Git status/history and recent commit diffs were inspected. This is a source/document review, not a fresh test run, live provider check, migration run, or security audit; implementation should verify the corresponding acceptance criteria in the target environment.
