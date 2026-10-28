# PHASE 13 — SUPERVISOR AGENT IMPLEMENTATION PLAN AND CLOSEOUT

**Status: Implemented and regression-tested — 2026-10-08.** Sections 2–45 preserve the planning-time repository review and implementation plan. Any statements there that Phase 13 was not started or that regression was unverified describe that earlier planning baseline. Section 46 records the implementation and current verification results.

**Repository review date:** October 8, 2026.

## 1. Executive Summary

Phase 13 adds a bounded, synchronous **case-level coordination agent**. It reads an assembled case snapshot, selects from a small allowlist of specialized agents, interprets their structured results, and returns a coordination outcome: `CONTINUE`, `ESCALATE`, `COMPLETE`, or `NEEDS_INFORMATION`.

The Supervisor must not become a second Workflow Agent, a general-purpose tool caller, or the event-driven Case Orchestrator planned for Phase 15. It proposes and delegates; existing agents and deterministic services retain their responsibilities and authority.

**Phase 12 remains implemented.** The Phase 13 implementation run completed a fresh backend regression successfully: 135 passed and 5 opt-in live integration checks skipped. The Phase 12-specific historical report of 120 passing tests remains the result recorded at that earlier milestone.

**Phase 12 readiness for Phase 13: READY.** The existing agent service interfaces supported synchronous delegation. Phase 13 added parent-child execution traceability. A broader API-wide tenant-scope review and live database/provider validation remain project-level open items.

## 2. Current Repository State

The repository contains the backend, domain services, agents, Tool Gateway, event/audit models, migrations `0001` through `0006`, agent-specific tests, and a Phase 12 plan.

The implemented agents are Document, Verification, and Workflow. There is **no Supervisor implementation** in the dispatcher: `AgentOrchestratorService.run_agent` handles those three types, while `SUPERVISOR` currently reaches the unsupported-agent error. `AgentRunRequest` mentions “supervisor” in a comment, and `AgentDefinition` can represent one, but neither establishes an executable Supervisor contract.

The progress report and checklist say Phase 12 is complete. The report records a passing regression run, but I could not reproduce that result in this review. The repository also documents open platform issues, including tenant-scope review across APIs and unverified live/database deployment checks.

## 3. Phase-by-Phase Status

| Phase | Status | Evidence and limits |
|---|---|---|
| 11 — Verification Agent | **Implemented; documented as complete** | Implementation and `test_verification_agent.py` exist. No focused Phase 11 test was run during this review. |
| 12 — Workflow Agent | **Implemented; documented as complete; current regression unverified** | `workflow_agent.py`, dispatcher integration, Gateway transition tool, dedicated tests, and checklist/report closeout are present. The recorded full-suite result is 120 passed and 5 skipped, but a fresh run did not finish during this review. |
| 13 — Supervisor Agent | **Not started** | No Supervisor class, context builder, delegation contract, runtime dispatch, or tests were found. Its checklist remains unchecked. |

## 4. Documentation Reviewed

- `README.md`
- `Documentation/README.md`
- `Documentation/01-product-overview.md`
- `Documentation/02-architecture.md`
- `Documentation/03-database-schema.md`
- `Documentation/04-operations-and-roadmap.md`
- `Documentation/Verifia_Detailed_Implementation_Checklist.md`
- `Documentation/progress_report.md`
- `Documentation/09-phase9-implementation-plan.md`
- `Documentation/next-milestone-phase12-workflow-agent-plan.md`

The implementation checklist and architecture, operations, and progress documents contain the Supervisor requirements and boundaries. No dedicated Phase 10, Phase 11, Phase 13, testing, or security document appeared in the repository inventory; those topics are covered in the shared architecture, operations, checklist, and phase-plan documents.

## 5. Documentation vs. Actual Implementation

The architecture says the Supervisor reads case state, identifies outstanding work, delegates, interprets results, and decides whether to continue, request information, or escalate. The checklist puts delegation and reacting to results in Phase 13, while the automatic event-driven case lifecycle appears under Phase 15.

The code follows that division so far: the dispatcher invokes specialized agents directly, and there is no automatic event-triggered agent loop. The Phase 12 plan and progress report describe a bounded Workflow Agent that uses the Gateway and deterministic Workflow Engine. Source code and tests for that implementation are present.

The README and progress report label Phase 12 complete, but that label is not fresh regression evidence. The test run attempted during this review did not yield a result. Neither documentation nor the existing `AgentExecution` model provides a dedicated parent-child execution relationship today.

## 6. Phase 12 Readiness for Phase 13

**READY WITH ISSUES.**

The Supervisor can build on the Workflow Agent’s bounded context, structured proposal, fail-closed validation, and deterministic Gateway handoff. The Verification and Document Agents also have callable service interfaces and execution traces.

Before Phase 13 is considered complete, implementation should:

- Establish parent-child execution linkage so delegated calls can be traced to a Supervisor run.
- Confirm tenant and permission checks at every delegated service boundary; the project still carries a broader API tenant-scope review as open work.
- Run and record the backend regression suite in an environment where it completes, plus focused Supervisor tests.
- Preserve the limitation that online PostgreSQL/pgvector and live-provider validation are environment checks, not proven by the offline test record.

These issues do not require redesigning Phase 12 before starting Phase 13.

## 7. Current Agent Architecture

| Component | Current responsibility | Inputs | Outputs | Authoritative? | Supervisor may call it? | Missing contract |
|---|---|---|---|---|---|---|
| Document Agent | Classify and process a case document; extract normalized fields and evidence; create review work when needed. | Case, document/version, optional guidance, storage and model adapter. | Classification, extracted fields, review status/task, proposals, execution ID. | Extraction is evidence-bearing data, not case/workflow authority. | **Yes, narrowly**, for a selected case document through its service interface. | Small Supervisor-facing result projection and parent execution linkage. |
| Verification Agent | Select and run eligible verifications through Gateway tools, then interpret deterministic outcomes. | Actor, case, optional prompt, model adapter; scoped definitions and tools. | Findings, deterministic results, review requirement, proposals and execution ID. | Deterministic results are authoritative; model interpretation is not. | **Yes**, when case state or returned document results indicate verification is appropriate. | Stable child-call contract and parent execution linkage. |
| Workflow Agent | Interpret current workflow context and propose or request permitted actions; route eligible tool actions through Gateway and Workflow Engine. | Actor, case, optional prompt, model adapter. | Proposal state, result summary, tool results, proposals and execution ID. | Proposal is not authoritative; Gateway and deterministic services establish execution outcomes. | **Yes, last**, after required evidence/verification is available. | Supervisor-facing result contract and parent execution linkage. |
| Supervisor | No implementation exists. Phase 13 plans case-level coordination and delegation. | Proposed: bounded case snapshot, user’s coordination request, prior child results. | Proposed: finite delegation plan and coordination decision. | **No.** It may recommend and delegate only. | Not applicable. | Entire execution contract, context builder, policy, persistence, and tests. |
| Agent dispatcher | Dispatches a request to Document, Verification, or Workflow. | `AgentRunRequest`, actor, database, optional storage/model adapter. | `AgentRunResponse`. | No. | Reuse as a trusted entry point; add Supervisor dispatch. | No Supervisor branch and no parent execution context. |
| Tool Gateway | Registers tools; validates process configuration, actor permissions, agent type, schema, and execution; records `ToolExecution`. | Case-scoped request, authenticated actor, trusted in-process agent ID. | Success, denial, failure and execution ID. | Enforces tool permission; underlying deterministic services establish business state. | **Indirectly only** through child agents. | Do not make it a generic Supervisor execution surface. |
| Workflow Engine/service | Validates and executes allowed case transitions. | Case, transition and actor, subject to process and workflow policy. | Deterministic state result and event/history. | **Yes** for workflow state. | Through Workflow Agent/Gateway only. | No direct Supervisor call path. |
| Verification service | Runs configured deterministic rules/calculations and persists results. | Case and verification definition. | Deterministic verification execution and results. | **Yes** for calculated/verified outcomes. | Through Verification Agent/Gateway only. | No direct Supervisor call path. |
| Event/Audit services | Store events and security-sensitive records. | Organization/case, actor, event/action, payload. | Persisted trace/audit rows. | Authoritative as records of what was recorded, not proof an AI conclusion is correct. | Supervisor lifecycle events may use existing event service. | Ensure correlation IDs are included; avoid sensitive prompt content. |

## 8. Phase 13 Objective

Implement a reusable `SupervisorAgent` that, for one explicit request:

1. Loads a minimal, organization-scoped case snapshot.
2. Determines whether a supported specialized capability is needed.
3. Delegates to at most the allowlisted specialized agents.
4. Validates and interprets their structured results.
5. Returns a finite coordination decision and a traceable result.

The call should be synchronous and bounded for this phase. It should not wake automatically on case events, persist a resumable orchestration graph, or run a case to completion unattended.

## 9. Why Phase 13 Is Needed

The three current agents each address one capability. The system has no implemented component that coordinates their use at case level, interprets their combined results, or presents one case-level outcome. Phase 13 fills that gap while keeping automatic, event-driven progress for Phase 15.

## 10. Scope

### In Scope

- Supervisor contract, service, scoped context builder, and execution record.
- Finite allowlist of Document, Verification, and Workflow delegation, with eligibility rules.
- Sequential delegation and result interpretation.
- Bounded child count, timeouts, safe failure results, and trace correlation.
- Existing authenticated `POST /api/v1/agents/run` dispatch for `agent_type=SUPERVISOR`.
- Tests and documentation updates.

### Out of Scope

- Event-driven case automation, durable resumption, event deduplication, and background orchestration (Phase 15).
- New model provider or Model Gateway (Phase 14).
- General recursive multi-agent framework or arbitrary tool selection.
- New approval authority or automatic business approvals.
- Full human-review lifecycle work (Phase 16).
- Generalized evaluation or multi-process acceptance work (Phases 23–24).

## 11. Supervisor Responsibilities

The Supervisor may:

- Summarize current case status and identify apparent missing work from bounded context.
- Choose among supported agent capabilities according to deterministic eligibility rules and a validated model plan.
- Delegate sequentially and interpret structured child results.
- Stop when the case is complete, the next step requires a human, required inputs are unavailable, or an agent fails.
- Return a coordination result explaining what was attempted, what authoritative results were returned, and what remains.

It should not infer that a case is complete from a model summary. Completion must be grounded in persisted case status and deterministic workflow/verification state.

## 12. Supervisor Authority Boundary

```text
Authenticated request
  → organization-scoped case snapshot
  → Supervisor proposes bounded delegation plan
  → validator checks target, sequence, inputs and limits
  → existing specialized agent service
  → Gateway and deterministic service, where needed
  → persisted child result and authoritative state
  → Supervisor returns continue / escalate / complete
```

The Supervisor may choose a **capability** to invoke, but it cannot grant permission, expand an agent’s tools, or provide a trusted agent identity. Each child agent must use its existing authorization path and Gateway rules. Direct database mutation by Supervisor is prohibited.

## 13. Agent Delegation Architecture

Use a small in-process `SupervisorAgent` service that invokes existing agent services. Do not make HTTP requests from the backend to its own API.

Start with **sequential** delegation and a maximum of three child calls per Supervisor execution, at most one call to each target type. The limit should be a named constant and tested. Parallel execution is deferred until the team can show that calls have no ordering or shared-session hazards.

The initial decision order should be:

1. **Document Agent:** only for a concrete case document that exists in the bounded context and is eligible for processing.
2. **Verification Agent:** when relevant evidence/documents are available and verification is not already current or complete.
3. **Workflow Agent:** only after prior results are available, or when no document/verification work is required.

The validated plan may stop earlier. A child failure must not silently trigger a retry or an alternative agent that repeats side effects.

## 14. Context Design

Build context in trusted Python code, not in the model prompt. Scope every record to both `actor.organization_id` and `case.id`; bind workflow details to the case’s immutable `process_version_id`.

Include only:

- Case ID, status, current stage and process-version ID.
- Minimal process/stage requirements needed to select a capability.
- Relevant document IDs, versions, processing status and concise extraction/review summaries.
- Current relevant verification statuses and result IDs.
- Counts or concise summaries of open tasks and pending approvals.
- IDs and statuses of prior child executions for this Supervisor run, if any.
- A short, bounded user request.

Do not include full document text, credentials, arbitrary organization records, complete event history, or unrestricted RAG results. Treat all user-provided and document-derived text as untrusted data. Set explicit maximum counts and string lengths, and reject or truncate overlarge inputs before model invocation.

## 15. Input / Output Contracts

Follow Pydantic v2 conventions and the existing JSON model adapter. Proposed contracts:

- `SupervisorInput`: `case_id`, optional bounded `user_request`, and optional document ID only when the user explicitly requests document work.
- `SupervisorContext`: typed snapshot with case/process/stage IDs, bounded eligible-document summaries, verification/task/approval summaries, and prior child results.
- `DelegationAction`: enum agent type, typed target IDs, concise reason, and bounded input. No Python paths, function names, raw tool calls, or executable instructions.
- `DelegationPlan`: ordered action list with `maxItems=3`, plus a stop reason when no action is appropriate.
- `DelegationResult`: child agent type, child execution ID, status, result reference/summary, and safe failure category.
- `SupervisorDecision`: `CONTINUE`, `ESCALATE`, `COMPLETE`, or `NEEDS_INFORMATION`; bounded rationale and outstanding-information list.
- `SupervisorExecutionResult`: parent execution ID, decision, child execution IDs/results, and authoritative state references used.

Reject unknown fields, invalid IDs, duplicate targets, actions outside eligibility rules, and result values that do not match the schema. Reconcile any narrower enum with the checklist’s current stop/escalate/continue language before implementation; `COMPLETE` must be derived from case state, not model assertion.

## 16. Delegation Contracts

Every delegated call must carry the authenticated actor, case ID, trusted storage/model dependencies where required, and parent execution ID for trace linkage. The Supervisor may not supply an organization ID or agent identity as trusted input; derive both from the authenticated actor and persisted agent definition.

A child returns its existing structured result and execution ID. The Supervisor should normalize that into `DelegationResult` without rewriting deterministic statuses.

- **Document:** one document ID/version; do not hand the child the entire case document set. A low-confidence/review result stops automatic progression and returns `NEEDS_INFORMATION` or `ESCALATE`.
- **Verification:** case scope; accept deterministic result statuses verbatim. Failure or inconclusive status stops the chain or escalates.
- **Workflow:** invoke only after the Supervisor has current workflow context. Treat proposed transition and tool result as different statuses. Only report execution when the deterministic workflow result confirms it.

For all targets, honor the existing service’s timeout/error behavior; record a child failure and stop. Do not retry side-effecting calls in Phase 13.

## 17. Tool Gateway Integration

The Supervisor must not call `ToolGatewayService.execute_tool` directly. Child agents remain responsible for their own Gateway calls, agent identity, schemas, policy checks, and deterministic service handoffs.

The Supervisor’s allowlist is separate from the Gateway registry: it lists child agent types only. A failed or denied child tool result must remain a failure/denial in the Supervisor output.

## 18. Workflow Integration

The Workflow Agent remains responsible for proposing workflow actions from current stage and process configuration. The Supervisor may decide to invoke it but must not author transitions, call `WorkflowService`, or interpret a proposal as an executed transition.

Phase 13 must not subscribe to workflow events or restart itself after a transition. Those are Phase 15 concerns.

## 19. Verification Integration

The Verification Agent selects relevant checks, invokes permitted Gateway tools, and interprets deterministic outputs. The Supervisor may use its structured result to decide whether a later capability is appropriate. It must preserve `FAIL`, `REVIEW`, `INCONCLUSIVE`, and other deterministic result states exactly and must not override them.

## 20. Document Agent Integration

The Document Agent processes one explicitly identified document through the existing document pipeline. The Supervisor can select that capability when relevant document status indicates processing is needed, but must not pass whole document contents or use its own model output as extracted evidence.

A review task or low-confidence result is a stop/escalation condition, not permission to continue as though the document were verified.

## 21. Event / Audit / Trace Design

Use `AgentExecution` as the primary record for the Supervisor and each child. Include `parent_execution_id` in child trace metadata or add a nullable self-reference if queryable relational lineage is required. Prefer an explicit nullable FK plus index if implementation confirms parent-child queries are a product requirement; document the migration and rollback plan before adding it.

Add bounded lifecycle events such as `SUPERVISOR_STARTED`, `SUPERVISOR_DELEGATION_COMPLETED`, and `SUPERVISOR_COMPLETED` only where event consumers or audit needs justify them. Put parent execution ID, child execution ID, delegation type, status, and correlation ID in event payloads. Do not log full prompts, document text, secrets, or sensitive extraction payloads.

Keep `ToolExecution` for tool calls, `EventRecord` for case events, and `AuditLog` for security-sensitive actions. Avoid duplicating tool output into audit rows.

## 22. Database Impact

Reuse `AgentDefinition`, `AgentExecution`, `ToolExecution`, events, audit, cases, processes, tasks, approvals, and verification records. No new business-state table is justified.

A migration is **conditional**: add `AgentExecution.parent_execution_id` with a self-FK and index only if JSON/event correlation is insufficient for required trace queries. Do not add a workflow or orchestration-state table in Phase 13.

## 23. API Impact

Add `SUPERVISOR` as a supported value on the existing `POST /api/v1/agents/run` route and dispatch through `AgentOrchestratorService`. Preserve authentication and actor derivation. Return `AgentRunResponse` with `agent_type="SUPERVISOR"` and structured coordination result data.

Do not accept caller-supplied organization, role, agent definition ID, child agent identity, or tool authority. Preserve existing route error conventions, but map agent validation/provider failures safely instead of exposing raw exception details.

## 24. AI / Model Adapter Impact

Reuse the existing injected `JsonModelAdapter` and settings/provider selection. Keep model output to a bounded delegation plan and decision; child agents use their existing model contracts.

Do not hard-code a provider or introduce a Phase 14 Model Gateway abstraction in Phase 13. Deterministic eligibility validation should constrain model choices before any delegation begins.

## 25. Security Architecture

- Authenticate the user and verify the case belongs to the actor’s organization before context construction.
- Revalidate case, process version, document IDs and current status at each child boundary.
- Do not allow the model to choose arbitrary agent types, tool names, roles, permissions, organization IDs, or database IDs outside supplied eligible context.
- Reuse each child’s authorization and Gateway checks.
- Treat user prompts, uploaded documents, extraction summaries, and retrieved content as untrusted.
- Limit context size, child count, model output size, and execution time.
- Return 404 for concealed cross-tenant cases where consistent with existing API policy.
- Ensure errors do not expose credentials, prompts, provider internals, or cross-tenant record existence.

## 26. Failure Handling

Persist a failed Supervisor execution for invalid model output, child exceptions, timeout, missing/changed case state, or storage/provider failure. Use safe structured failure categories such as `INVALID_PLAN`, `CHILD_FAILED`, `TIMEOUT`, `STALE_CONTEXT`, and `DEPENDENCY_UNAVAILABLE`.

Stop on failure. Do not report completion, continue to Workflow Agent, or manufacture a successful child result after a failure. Keep authoritative case state unchanged unless a child’s deterministic service already committed a valid action.

## 27. Retry / Idempotency

Do not add Supervisor-level retries in Phase 13. Provider-level retry behavior may follow the existing adapter’s configured policy before a delegation plan is accepted. Never automatically retry a child call that may have created a task, approval, or transition.

Idempotency keys and durable retry/resumption belong with Phase 15 unless a concrete existing service contract requires them sooner.

## 28. Loop / Recursion Protection

- Supervisor may delegate only to the three named child types.
- Child agents may not invoke Supervisor.
- Maximum three child calls per parent execution; one per type.
- No recursive delegation, repeated planning loop, or self-triggering events.
- Persist a finite delegation sequence and stop reason.
- Reject unknown agent type and duplicate child target before execution.

## 29. Observability

Record Supervisor and child execution IDs, case and organization scope, agent type, start/end times, duration, status, safe failure category, decision enum, delegation reason, and correlation/parent IDs.

Measure child count and total execution duration. Do not log raw model prompts or full case/document content. Sanitize provider errors and user text before persisting summaries. Use existing execution/event structures; add fields only when there is a demonstrated query or retention requirement.

## 30. Performance Considerations

Sequential execution has predictable ordering but cumulative latency. Bound the total child count and each model/agent timeout; return a safe timeout result rather than holding a request indefinitely.

Do not parallelize calls in Phase 13. Measure latency and model-call count in representative tests. Durable background work and queues are documented future capabilities and belong to later phases unless the current synchronous API proves unusable.

## 31. Configuration / `.env`

**No new environment variables are required.** Reuse settings for the existing JSON model adapter and its provider timeout/retry configuration. No Supervisor-specific API key or provider selector is justified.

The expected path is existing environment configuration → `Settings` → `get_json_model_adapter()` → injected Supervisor → child services. Missing provider credentials should fail the Supervisor invocation safely, not prevent application startup.

## 32. Testing Strategy

Tests below are proposed; they have **not** been run in this review.

Use deterministic fake model adapters for contract and safety tests. Keep real database/service behavior for tenant scoping, child execution records, Gateway policy, and Workflow Engine results where integration fixtures permit. Mock external providers and storage. Do not rely only on asserting that a mock was called.

Every test should prove an acceptance requirement, identify the boundary under test, state which services are real, and assert both the expected result and that invalid paths do not mutate authoritative state.

## 33. Documented Tests

The project documents Phase 12 coverage for structured proposals, Gateway execution, deterministic transitions, invalid proposal handling, cross-tenant isolation, trace redaction, 18 focused Workflow Agent tests, and a 120-passed/5-skipped full suite.

These are Phase 12 results. The Supervisor checklist itself contains only high-level acceptance bullets and does not define a detailed Phase 13 test suite.

## 34. Recommended Additional Tests

| Test | Requirement and boundary | Real vs. mocked | Expected / failure condition |
|---|---|---|---|
| Supervisor plan schema | Bounded, finite output contract | Real Pydantic validation; fake adapter | Valid plan accepted; unknown fields/types/targets rejected. |
| Context tenant and version scope | No cross-tenant or wrong-version data | Real DB queries/fixtures | Only case-bound data appears; any foreign record is absent or rejected. |
| Delegation eligibility | Only eligible child agent is invoked | Real context/policy; fake model | Invalid/duplicate child plan rejected before execution. |
| Child result preservation | Deterministic outcomes remain authoritative | Real verification/workflow service where feasible | Exact status preserved; any rewritten status fails. |
| Failure and timeout | Stop safely and trace failure | Real execution record; child/provider stub | Parent marked failed/escalated; no later child or false completion. |
| Cross-tenant API | Authenticated tenant cannot invoke foreign case | Real API and database fixtures | Concealed/rejected response; no model call or child execution. |
| Recursion/limits | No cycles and finite calls | Real dispatcher, fake adapters | Fourth call or Supervisor child target rejected. |
| Trace linkage | Parent and children are queryable together | Real DB and event records | Parent ID/correlation links all children; missing link fails. |
| Workflow authority | Supervisor cannot mutate case | Real case/workflow DB state | Proposal alone leaves state unchanged; only deterministic child result can change it. |
| Prompt injection | Document/user text cannot expand plan authority | Fake content, real validator | Allowlist remains fixed; arbitrary tools/permissions are rejected. |
| API response semantics | Proposal, child result, and authoritative state are distinct | Real router/service, fake adapter | Response separates decision from child execution and business outcome. |
| Regression suite | Existing behavior remains intact | Full backend suite | Passing result recorded; incomplete/interrupted run is not reported as pass. |

## 35. End-to-End Scenarios

**Recommended case-review scenario:** An authenticated user requests coordination for a case with a newly uploaded document in an eligible state.

1. API authenticates the user and loads the case within the user’s organization.
2. Supervisor builds a bounded snapshot tied to the case’s process version.
3. The validated plan delegates to Document Agent for the identified document.
4. Document Agent returns extraction/review status and execution ID.
5. If the document requires human review, Supervisor stops and returns `NEEDS_INFORMATION` or `ESCALATE`; it does not run verification or propose completion.
6. If the result is usable and policy/context indicate verification is needed, Supervisor delegates to Verification Agent.
7. Verification results and deterministic statuses are preserved.
8. Workflow Agent runs only if verification and case state permit it.
9. Workflow proposals remain proposals; an executed transition is reported only when Gateway and Workflow Engine confirm it.
10. Parent and child executions are linked; failures leave case state unchanged unless a valid deterministic child action already committed.

This proves one bounded coordination request. It does not prove an event-driven case lifecycle or unattended case completion.

## 36. Detailed Implementation Tasks

### P13-01 — Contract and policy

- **Objective:** Define Pydantic input, context, delegation, result, decision, and failure contracts.
- **Dependencies:** None.
- **Likely files:** `backend/app/agents/schemas.py`; new `backend/app/agents/supervisor_agent.py`.
- **Reuse/new:** Reuse `AgentRunResponse`, `AgentExecution`, JSON adapter; add finite Supervisor-specific schemas.
- **Data flow:** Case snapshot → validated plan → child result list → final decision.
- **Security/errors:** Enforce allowlisted child types, bounded strings/counts, unknown-field rejection.
- **Tests:** Valid/invalid plan schema; invalid IDs and duplicate targets.
- **Acceptance/DoD:** Every model-controlled field is typed, bounded, and non-executable.

### P13-02 — Scoped context builder

- **Objective:** Build minimum sufficient case context.
- **Dependencies:** P13-01.
- **Likely files:** `supervisor_agent.py`; possibly shared context helpers if existing patterns justify reuse.
- **Reuse/new:** Reuse case/process/document/task/approval/verification models and Workflow Agent scoping patterns.
- **Data flow:** Authenticated actor + case → tenant/version-scoped snapshot.
- **Security/errors:** Reject missing/cross-tenant case; bind stage data to immutable process version; cap records and text.
- **Tests:** Cross-tenant, stale/wrong-version records, context bounds.
- **Acceptance/DoD:** No unrestricted corpus or foreign-tenant data reaches the adapter.

### P13-03 — Delegation policy and executor

- **Objective:** Validate and execute sequential child actions.
- **Dependencies:** P13-01, P13-02.
- **Likely files:** `supervisor_agent.py`, `backend/app/agents/service.py`.
- **Reuse/new:** Invoke Document, Verification, Workflow agent services in-process.
- **Data flow:** Validated plan → child service → normalized child result.
- **Security/errors:** Actor and trusted agent identity derived server-side; maximum three calls; stop on first failure/review boundary.
- **Tests:** Eligibility/order, child failures, timeout, duplicate/recursive target rejection.
- **Acceptance/DoD:** No direct tool or deterministic business-service invocation from Supervisor.

### P13-04 — Execution and trace linkage

- **Objective:** Persist parent and child execution lineage safely.
- **Dependencies:** P13-03.
- **Likely files:** `backend/app/agents/models.py`, agent service, event service; conditional Alembic revision.
- **Reuse/new:** Reuse AgentExecution, ToolExecution, EventRecord and existing audit patterns.
- **Data flow:** Parent execution ID passed as trusted trace metadata to each child.
- **Security/errors:** Store bounded summaries and IDs; never persist secrets or full sensitive prompts.
- **Tests:** Parent/child lookup and redaction; failed child still links to parent.
- **Acceptance/DoD:** A reviewer can reconstruct one coordination run and its child outcomes.
- **Schema decision:** Add nullable `parent_execution_id` self-FK and index only if relational lineage is needed for queries; document migration and rollback.

### P13-05 — Dispatcher and API integration

- **Objective:** Expose Supervisor through the existing agent endpoint.
- **Dependencies:** P13-01 through P13-04.
- **Likely files:** `backend/app/agents/service.py`, `schemas.py`, `router.py`.
- **Reuse/new:** Existing authenticated `/api/v1/agents/run` entry point and response envelope.
- **Data flow:** `agent_type=SUPERVISOR` → Supervisor service → structured `AgentRunResponse`.
- **Security/errors:** Actor from authentication only; safe error mapping; no caller-supplied tenant or agent ID.
- **Tests:** API success, invalid case, cross-tenant, disabled definition, provider/child failure.
- **Acceptance/DoD:** Supervisor requests dispatch successfully and unsupported plans fail closed.

### P13-06 — Lifecycle events and observability

- **Objective:** Make executions, decisions, failures, and delegation relationships inspectable.
- **Dependencies:** P13-04.
- **Likely files:** `supervisor_agent.py`, `events/service.py`, tests.
- **Reuse/new:** Existing event and execution records; add only necessary correlation metadata.
- **Data flow:** Parent/child lifecycle → safe event payloads and execution output.
- **Security/errors:** No prompts, secrets, full documents, or unnecessary sensitive extraction.
- **Tests:** Event/execution links, redaction, failure status.
- **Acceptance/DoD:** Successful and failed runs have enough safe trace data to diagnose execution.

### P13-07 — Security and integration verification

- **Objective:** Prove the authority boundary across the complete call chain.
- **Dependencies:** P13-01 through P13-06.
- **Likely files:** New `backend/tests/test_supervisor_agent.py`; API/Gateway tests as needed.
- **Reuse/new:** Existing test fixtures, fake adapters, real service/database fixtures.
- **Data flow:** API → context → Supervisor → child → Gateway/deterministic result.
- **Security/errors:** Tenant, process-version, stale-state, prompt-injection, and recursion cases.
- **Tests:** Recommended tests above plus E2E scenario.
- **Acceptance/DoD:** Invalid input cannot cause child side effects; proposals alone cannot mutate state.

### P13-08 — Documentation and closeout

- **Objective:** Reconcile code, tests, roadmap, configuration, and limits.
- **Dependencies:** P13-01 through P13-07.
- **Likely files:** README, progress report, checklist, architecture, operations/roadmap.
- **Reuse/new:** Update existing docs; no new Phase 13 specification file is required unless the team wants one.
- **Data flow:** Test and implementation evidence → documented status.
- **Security/errors:** Describe actual context, data transfer, failure behavior, and limits.
- **Tests:** Record commands and exact results, including skipped or environment-dependent checks.
- **Acceptance/DoD:** Documentation does not claim an unverified regression or future Phase 15 behavior.

## 37. Implementation Order

1. P13-01 contracts and policy.
2. P13-02 scoped context builder.
3. P13-03 validated sequential delegation.
4. P13-04 parent-child trace design and any justified migration.
5. P13-05 dispatcher/API integration.
6. P13-06 lifecycle observability.
7. P13-07 security, integration, end-to-end tests, and full regression.
8. P13-08 documentation and completion review.

## 38. Blockers

No architecture blocker prevents starting Phase 13. The current full-suite result remains unverified in this review and must be rerun successfully before claiming Phase 13 regression completion. Broader tenant isolation remains an explicitly open project item and must not be misrepresented as solved by Supervisor-specific checks.

## 39. Risks

- **Authority confusion:** A model summary may be mistaken for a deterministic result. Keep proposal, child execution, and business-state fields separate.
- **Duplicate side effects:** Retrying child calls can create duplicate tasks or approvals. Do not retry them automatically.
- **Tenant leakage:** Context assembly and child service boundaries both require scope checks.
- **Trace gaps:** Parent-child links are not currently first-class in `AgentExecution`.
- **Latency:** Sequential child calls can be slow; bound them and avoid starting unnecessary agents.
- **Scope creep:** Event-triggered loops, durable resumption, or generic recursive delegation would cross into Phase 15.

## 40. Technical Debt

- Broad route-by-route tenant-scope review remains open in the project documentation.
- Agent execution records lack a dedicated parent execution relation.
- Full backend tests did not complete during this review; the documented prior result remains the only recorded regression result inspected.
- Online PostgreSQL/pgvector and live-provider checks remain separate environment validation.
- Existing event service commits events independently; implementation should verify transaction ordering and avoid reporting a completed parent if required trace writes fail.

## 41. Documentation Updates

Update the checklist’s Phase 13 section with concrete criteria and test evidence. Update the architecture’s agent flow to distinguish synchronous request-scoped coordination from the Phase 15 event-driven Case Orchestrator. Update README and progress report with actual test evidence, migration decision, environment limitations, and the no-new-configuration conclusion.

## 42. Production Readiness Requirements

Before production use, confirm:

- Successful full backend regression in a supported environment.
- Cross-tenant isolation for Supervisor context and every delegated path.
- Safe handling of invalid model output, unavailable providers, timeout, and child failure.
- Bounded context, child calls, duration, and stored data.
- Traceability from parent execution through child executions and Gateway records.
- No model-only case completion, approval, or workflow mutation.
- Operational confirmation of database migrations if a trace-link migration is added.
- Live-provider and deployment checks recorded separately from deterministic unit/integration evidence.

## 43. Final Definition of Done

Phase 13 is complete only when:

- The authenticated agent endpoint can dispatch a Supervisor request for an organization-scoped case.
- Supervisor context is bounded, process-version-bound, and excludes irrelevant sensitive data.
- The model can return only a finite, validated delegation plan and coordination decision.
- Delegation is sequential, allowlisted, capped, non-recursive, and uses existing child-agent services.
- Document, Verification, and Workflow results remain clearly distinct from Supervisor decisions and deterministic business state.
- Supervisor cannot call arbitrary tools, grant permissions, approve actions, mutate cases, or bypass Gateway/deterministic services.
- Failures stop safely and are persisted with a safe category; side-effecting child calls are not automatically retried.
- Parent and child executions are traceable with case/organization scope and correlation IDs.
- Tenant isolation, process-version binding, stale-state behavior, prompt-injection resistance, failure handling, and API semantics have meaningful tests.
- The complete backend regression suite has a recorded successful result; skipped tests and environment checks are accurately described.
- Architecture, checklist, README, and progress report match the implementation and preserve Phase 15 boundaries.

## 44. Prioritized Roadmap

- **P0 — Blocking:** Contracts, tenant-scoped context, deterministic delegation eligibility, strict authority boundary, safe child failure handling.
- **P1 — Required:** Dispatcher/API integration, parent-child traceability, event/observability behavior, focused and end-to-end tests, verified regression.
- **P2 — Important:** Production migration validation if lineage schema changes; operational latency and cost measurement; broader API tenant review.
- **P3 — Future:** Event-driven case orchestration, durable retries/resumption, human review lifecycle expansion, evaluation and generalization work.

## 45. Final Recommendation

Implement Phase 13 as a **single-request case coordinator** that chooses from existing specialized agents and returns a structured, traceable decision. Keep deterministic eligibility and authorization outside model control. Do not add a queue, framework, provider, or automatic event loop. Phase 15 should own reacting to case events and driving durable case progression.

**The key distinction:** Phase 12 decides and proposes workflow actions within the workflow domain. Phase 13 selects and coordinates specialized agent capabilities for one case-level request. Phase 15 reacts to events and drives case progression over time. This separation implements what Phase 12 does not already provide without accidentally implementing Phase 15.

## 46. Implementation Closeout — 2026-10-08

### Implemented behavior

- `AgentType.SUPERVISOR` is dispatched through the existing authenticated agent endpoint.
- The Supervisor builds a bounded organization- and ProcessVersion-scoped context and validates a strict plan before invoking children.
- Delegation is synchronous, sequential, allowlisted, limited to three calls, at most one call per child type, and non-recursive.
- Document, Verification, and Workflow executions carry `parent_execution_id`; the migration adds the self-reference and parent/case indexes.
- Child results are sanitized into bounded projections. Failure, timeout, stale state, invalid plans, and provider exceptions stop safely and are recorded with safe error categories.
- The Supervisor does not call arbitrary tools or directly mutate case/workflow state. Existing child-agent authorization and Gateway paths remain authoritative.
- No new environment variables, provider, queue, or event-driven loop were introduced.

### Changed implementation files

- `backend/app/agents/supervisor_agent.py`
- `backend/app/agents/schemas.py`
- `backend/app/agents/service.py` and `backend/app/agents/router.py`
- `backend/app/agents/document_agent.py`, `verification_agent.py`, and `workflow_agent.py`
- `backend/app/agents/models.py`
- `backend/app/domain/documents/processing.py` (rollback-safe failure handling required for reliable child failure traces)
- `backend/alembic/versions/0007_agent_execution_parent.py`
- `backend/tests/test_supervisor_agent.py`

### Verification executed

| Check | Command/result |
|---|---|
| Focused Supervisor suite | `rtk proxy python -m pytest -q --tb=short --show-capture=no -o log_cli=false tests/test_supervisor_agent.py` — **15 passed** |
| Full backend regression | `rtk proxy python -m pytest -q --tb=short --show-capture=no -o log_cli=false` — **135 passed, 5 skipped, 0 failed** |
| Python compilation | `rtk proxy python -m compileall -q app` — **passed** |
| Alembic head resolution | `rtk proxy python -m alembic heads` — **`0007_agent_execution_parent (head)`** |

The five skipped checks are opt-in live integrations gated by `VERIFIA_RUN_LIVE_TESTS=1`. A live PostgreSQL migration upgrade/downgrade and live-provider evaluation were not run. No contents of `backend/.env` were inspected or included in documentation.

### Definition of Done status

| Requirement | Result |
|---|---|
| Authenticated endpoint dispatch and organization-scoped case access | **PASS** — covered by API and tenant-scope tests |
| Bounded context and process-version/current-stage eligibility | **PASS** — bounded projection, stale-stage and invalid-target tests |
| Finite validated delegation plan | **PASS** — allowlist, count, duplicate, ordering, and recursion tests |
| Child results and parent-child traceability | **PASS** — linked Document, Verification, and Workflow trace tests |
| No direct tool bypass or business-state mutation by Supervisor | **PASS** — authorization and no-side-effect tests |
| Safe failure behavior for child failure, timeout, provider error, malformed plans | **PASS** — focused tests |
| Focused and full regression | **PASS** — 15 focused; 135 full-suite passes |
| Live PostgreSQL migration and provider checks | **NOT RUN** — environment validation remains open |

### Documentation updated

README, architecture, database schema, operations roadmap, implementation checklist, and progress report now reflect the implemented Phase 13 behavior, migration head, executed test results, and remaining environment checks.
