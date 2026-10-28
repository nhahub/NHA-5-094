# Phase 23 — Evidence-Based Model and System Evaluation

**Last updated:** 2026-10-12  
**Current status:** PARTIAL — the synthetic benchmark and runtime contracts pass local tests; live candidate comparison, system-level evaluation, and authorized representative-document evidence remain open.
**Starting commit:** `090dd9f` (`main` was clean at inspection).  
**Owner evidence:** this document is the living Phase 23 plan and progress log.

## A. Phase overview

### Official objective and authority

Evaluate each agent independently before comparing the combined workflow. Within one agent evaluation, hold the cases, prompt/configuration, and scoring rules fixed; record provider/model identity, successes/failures, latency, and available usage data. Keep agent scores separate. After agent-level evaluation and model selection, run system-level workflow evaluation. Include synthetic baselines and licensed or explicitly authorized representative business documents. Make per-agent selections from quality, reliability, latency, and available cost/usage evidence; do not assume one provider fits every agent.

Authoritative sources:

- `Documentation/04-operations-and-roadmap.md` §33, Phase 23 — Evidence-based model choice.
- `Documentation/Verifia_Detailed_Implementation_Checklist.md` §23, AI & System Evaluation, including its four agent subsections, System subsection, and Definition of Done.
- Supporting constraints: `Documentation/external-model-provider-review.md` and the model gateway/agent contracts described in `Documentation/02-architecture.md`.

### Scope and exclusions

- **In scope:** versioned evaluation inputs and procedures; per-agent quality/reliability/latency/usage evidence for Document, Verification, Workflow, and Supervisor; separate end-to-end workflow measurements after agent-level evaluation; repeat-run variance and throughput/cost bounds where evidence allows; evidence-based route recommendations; synchronized documentation.
- **Out of scope:** changing business authority from deterministic services to model outputs; asserting exactly-once external side effects; production provider approval; sending real customer or confidential data to an unapproved provider; inventing acceptance thresholds; changing model/provider defaults before comparative evidence exists; Phase 24 multi-process generalization.
- **Data boundary:** the provider review register says no external model route is approved for production business data. Use only synthetic/public/non-sensitive data unless a dataset and route have explicit documented authorization. The current local Phase 17 synthetic pack is ignored by Git and cannot be a clean-checkout benchmark dependency without a checked-in or reproducibly generated fixture. No authorized representative business-document corpus has been identified yet.
- **External calls:** live provider comparisons may incur usage/cost and send the submitted prompt/document text to external services. This plan prepares repeatable machinery and offline tests first. Actual provider calls and any real-document use require applicable route/data authorization; no such call is claimed or performed during initial repository inspection.

### Initial repository state and dependencies

- Branch `main` was clean at commit `090dd9f` (`implement repeatable quality gates and CI workflow (phase 22)`). No Phase 23 plan or Phase 23 implementation was present.
- Phase 22 documentation reports backend regression **268 passed, 7 skipped, 0 failed**, critical Ruff passed, and frontend tests/typecheck/lint/build passed; current Phase 22 plan records the local PostgreSQL worker probes as passing and hosted Actions as pending. These are prior evidence, not re-run as part of initial Phase 23 inspection.
- `backend/scripts/evaluate_phase17_document_agent.py` evaluates one configured Document route against the local held-out synthetic pack. It records classification, field exact match, citation validity, model, and average latency, but it does not provide a common cross-agent runner, prompt/config versions, complete failure denominators, usage aggregation, repeated-run analysis, or selection report.
- `backend/scripts/evaluate_phase17_workflows.py` is a ten-scenario authenticated application journey with synthetic gold fields injected; it evaluates workflow rules/security outcomes, not model-generated agent quality.
- Agent classes accept/internally resolve `JsonModelAdapter`; the shared adapters expose `last_usage` with prompt/completion/total tokens where providers return usage. Stored agent `token_usage` currently includes model identity but generally not provider usage counts.
- Model routes are configurable per agent. Defaults are baselines (Document LLM7 `gpt-oss:20b`; Verification and Supervisor Groq `qwen/qwen3.8-27b`; Workflow Kilo `dots-studio/dots-3-note-preview:free`) and are not comparative winners.
- Current environment check found no configured Groq, LLM7, Kilo, or Gemini API credentials in loaded settings or root/backend `.env` files. The configured Ollama endpoint `127.0.0.1:11434` did not accept a connection; Docker API access failed with a named-pipe permission error. No model/provider request was sent.
- The user authorized bounded external provider calls using synthetic evaluation cases only. This does not authorize real business-document use. Missing credentials currently prevent live comparison.
- The local `data/phase17_evaluation` pack exists but `.gitignore` excludes it. It contains generated synthetic records and images. `backend/scripts/generate_phase17_evaluation_data.py` can generate it. The separate original Phase 17 acceptance-threshold file remains unavailable; Phase 23 must not create or infer it.
- Existing evaluation code/tests and adapter contracts should be reused. Agent evaluation must not persist into a shared application database or run the full Phase 17 scenario script against a user database.

### Expected deliverables

1. A clean-checkout reproducible synthetic benchmark with explicit versioned labels/cases and fixed scoring rules, or a deterministic fixture-generation step that the runner validates before use.
2. A common run/report contract for provider/model, agent, case-set version, prompt/config version, attempt status, safe failure reason, latency, and provider usage when available.
3. Agent-specific scores and segmentation matching §23; aggregate system scores are reported separately.
4. Repeat-run comparison and a transparent route recommendation only where actual comparable evidence exists.
5. An authorization register for any licensed/explicitly authorized representative documents and route/data combination. Until evidence exists, this item stays blocked and synthetic limitations are stated.
6. Updated roadmap/checklist/progress report/README/documentation index and a dated evidence log.

## B. Requirement traceability matrix

Statuses use the Phase 23 plan vocabulary. Requirement statuses are conservative; a created runner or dataset alone is not completion evidence.

| Requirement ID | Source | Required behavior | Current state | Implementation tasks | Tests / evidence | Acceptance criteria | Status |
|---|---|---|---|---|---|---|---|
| P23-R001 | Checklist §23 opening and Definition of Done | Provide a fixed, repeatable evaluation procedure for each agent, fixing cases, prompt/configuration, and scoring rules within each comparison. | Versioned four-agent synthetic dataset, fixed benchmark prompts/schemas, adapter runner, data/config hashes, safe report metadata and repeat summaries implemented. | T23-01, T23-02 | `tests/test_phase23_evaluation.py`; offline CLI smoke for all four agents. | Clean checkout loads pinned cases; same agent candidates use the same dataset/prompt/scorer; reports preserve run/failure/usage evidence. Live comparisons remain pending. | IMPLEMENTED — NOT VERIFIED |
| P23-R002 | Checklist §23 Document Agent | Score classification, field/required-field accuracy, hallucinated and unsupported fields, citation/source-locator correctness; segment by represented document type, scan quality, language/layout. | Scorer and four synthetic cases implement the named metrics and segment only represented document type, scan quality, language, and layout. Cases are exploratory; they do not represent licensed business documents. | T23-02, T23-03 | Scorer tests and fake-run CLI smoke; live provider run unavailable. | Every listed measure and denominator is tested; candidate quality and sample adequacy remain unverified. | IMPLEMENTED — NOT VERIFIED |
| P23-R003 | Checklist §23 Verification Agent | Score verification/tool/argument selection, interpretation, escalation, false accepts/rejects, and safe behavior with missing evidence/tool results. | Four fixed synthetic cases and scorer cover these outputs. Failed calls are counted separately, not misreported as false accept/reject decisions. | T23-01, T23-02, T23-04 | Scorer and failure-accounting tests; provider comparison pending. | Per-candidate measurements over fixed cases with false accept/reject denominators and missing-evidence cases. | IMPLEMENTED — NOT VERIFIED |
| P23-R004 | Checklist §23 Workflow Agent | Score next action, valid format, no unauthorized transition, escalation, proposal validity, replay, and stale-state handling. | Four synthetic state cases and scorer cover next action, format, target authorization, escalation, stale snapshot, and replay safety. Model output is not executed. | T23-01, T23-02, T23-04 | Scorer tests include invented target and unsafe stale proposal; candidate comparison pending. | Outputs are assessed against fixed labels without applying proposals to business state; live comparison remains pending. | IMPLEMENTED — NOT VERIFIED |
| P23-R005 | Checklist §23 Supervisor Agent | Measure bounded-context delegation, stop/continue/complete/escalation, incomplete-context and approval blockers, child limits/traces, safe model failures, call count, latency, recovery. | Four synthetic plan cases score decision, delegation sequence, available-child bounds/order and blockers. Runner measures benchmark-call failure, latency and usage. The existing Supervisor integration suite passes 16 tests covering parent/child traces, bounded/truncated context, provider/child failures, stale state, and recovery behavior. This verifies deterministic runtime contracts, not comparative per-model trace/recovery. | T23-01, T23-02, T23-04 | Scorer tests and adapter-failure case; `tests/test_supervisor_agent.py` (16 passed). Per-candidate runtime behavior still needs observed model runs. | Benchmark plus runtime evidence covers every checklist guarantee before completion. | IN PROGRESS |
| P23-R006 | Checklist §23 System | After agent-level evaluations, measure system time, human interventions, detected errors, false positives/negatives, successful completion, provider/config identity, failures, variance, throughput/cost bounds. | No repeated model-driven system benchmark or comparable usage/cost rollup exists. Phase 17's ten-case API journey disables orchestration and injects synthetic gold extraction; it is not a Phase 23 system/model benchmark and writes to its configured database. Docker API access is unavailable, and no agent routes have been selected from comparative evidence. | T23-05 | Design/run a separate isolated disposable-system benchmark after per-agent evaluation and selection; cover repeated workflow metrics and available usage. | System report is separate from agent scores and records scenario outcome, completion, intervention, errors, latency, failures, available usage, variance, throughput, and limits. | NOT STARTED |
| P23-R007 | Checklist §23 System; roadmap §33 Phase 23; provider review register | Include licensed or explicitly authorized representative business documents alongside synthetic baselines, with provider/data handling authorization. | Only a local synthetic generated corpus is identified. No authorized representative business-document corpus or provider data-class approval is recorded. | T23-06 | Dataset provenance and approval record; route review evidence. | Corpus license/authorization, provenance, data classes and permitted routes are recorded before any transfer/evaluation. | BLOCKED |
| P23-R008 | Checklist §23 opening and Definition of Done; roadmap §33 | Justify a separate provider/model route for each agent from task quality, reliability, latency, and available cost/usage evidence; no global winner assumption. | Four route defaults are documented baselines only. No comparable results exist. The user authorized bounded synthetic-only external calls, but provider credentials are absent; business-data review is also unresolved. | T23-02, T23-05, T23-07 | Comparable run reports and a documented decision matrix. | Each route is justified with evidence and limitations; unavailable cost/usage is explicit; no pooled score substitutes for per-agent results. | BLOCKED |

## C. Initial gap analysis

### Evaluation inputs and isolation

- **Verified:** the Phase 17 generator creates ten fictional Import/Export scenarios, synthetic documents and scan variants with expected outcomes; the generated data directory is Git-ignored. The original Phase 17 gate file is absent and cannot be reconstructed.
- **Gap:** evaluation artifacts and prompts must be versioned or deterministically generated so a clean checkout and later candidate runs see identical inputs. A new Phase 23 runner must not consume the missing Phase 17 threshold file or modify the historical gate.
- **Decision:** create a separate versioned Phase 23 case manifest/scoring configuration and a clean-checkout fixture strategy. Reuse generated Phase 17 synthetic cases only if the generator is deterministic, the manifest is verified, and the Phase 23 runner validates the expected version/hash. Do not silently call a missing or stale local dataset a passing run.

### Agent boundaries and measurements

- **Verified:** Document Agent has a prior live single-provider evaluator; Verification, Workflow, and Supervisor accept model adapters and have deterministic contract/safety tests. Shared adapters track usage metadata, but not every provider returns it. Agent persistence stores only limited metadata.
- **Gap:** there is no consistent candidate-selection runner, per-call attempt accounting, prompt/config fingerprint, repeat-run variance, per-agent scorecard, or safe-cost report. Current test coverage is not live provider quality evidence.
- **Decision:** keep evaluation in scripts/modules and test fixtures, not in production business flows or persisted business tables unless an official criterion proves a schema change is necessary. Record unavailable usage as `null`/unreported, never as zero. Do not include prompt, raw document, secret, or provider response body in result reports.

### Data and provider constraints

- **Verified:** the provider review register explicitly limits unapproved external routes to synthetic/public/non-sensitive data and says real customer/confidential case data remains local. No provider route is approved for business data.
- **Gap:** no licensed/explicitly authorized representative business corpus or approval record was identified. An evaluation request could send data externally and consume provider quota/cost.
- **Decision:** implement and test the harness with synthetic fixtures. Keep authorized-business-corpus evaluation blocked until provenance, license/authorization, data classes, route approval, minimization, and use conditions are documented. Do not send real case data or initiate paid/live candidate calls without the necessary authorization.

### Earlier-phase dependencies

- **Phase 14 Model Gateway:** implemented provider-neutral adapters, per-agent routes, retry/failure types and optional usage reporting. Reuse it; verify adapters expose stable safe metadata.
- **Phases 10–13 agents:** existing structured schemas and deterministic authority boundaries are prerequisites. Phase 23 measures them; it must not give model proposals business authority.
- **Phase 17 synthetic baseline:** generated labels and previous single-provider results are useful historical inputs, but its acceptance thresholds are a separate missing file. Preserve its historical evidence and avoid mixing its threshold gate with Phase 23 scoring.
- **Phase 20 provider review:** production business data remains unapproved. This is a real blocker for the licensed/authorized-data criterion, not a reason to prevent offline synthetic tooling.
- **Phase 22 tests:** prior reported quality gates remain reusable unless touched by Phase 23 changes. Run only affected tests plus Phase 23 tests, then relevant regression checks.

## D. Architecture and evaluation design

### Data flow

Versioned case manifests and scoring rules → one selected agent adapter/config → existing agent contract with isolated synthetic context → per-case outcome record → agent-specific scorer → JSON report → separate cross-run comparison/decision report. A separate system harness may invoke the existing authenticated API only against a disposable database/organization and must report system results independently.

### Report contract

Each run records UTC timestamp, runner version, agent, provider and configured/returned model identity, dataset/scoring/prompt/config version or hashes, attempt count, success/failure state, safe error class, per-case and aggregate latency, available token/usage metadata, and omissions. Reports exclude credentials, full prompts, document contents, personal data, and raw external error bodies. A provider not returning usage produces an explicit unavailable value. Repeated runs retain per-run results and summarize variance rather than overwriting or pooling unlike agents.

### Scoring and selection

Use the checklist's named criteria and labels as the score definitions. Preserve true positives, false positives, false negatives, failed calls, and denominators. Do not invent universal thresholds or combine different agents into one quality score. The decision record compares candidates per agent and names quality/reliability/latency/usage tradeoffs and dataset limits. Cost is recorded only when provider-reported prices or verified rates and usage are available; do not infer cost from token counts without a dated source/rate record.

### Data protection and repeatability

Default to synthetic-only inputs. Pin dataset version/hash, scorer version, relevant prompt/config fingerprint, provider/model ID, and run conditions. Keep provider keys in environment configuration and never serialize them. System runs must use isolated disposable state and cleanup; no historic or user database is an evaluation target.

## E. Dependency-aware task breakdown

| Task ID | Requirements | Description | Priority | Dependencies | Expected files | Tests and acceptance | Status |
|---|---|---|---|---|---|---|---|
| T23-00 | P23-R001–R008 | Inspect official criteria, current agent/gateway paths, data provenance, prior evidence, and repo state. | P0 | None | This plan; roadmap/checklist and source inventory. | Sources and initial status are recorded with verified/blocked distinctions. | VERIFIED COMPLETE |
| T23-01 | P23-R001–R006 | Define a versioned clean-checkout synthetic case set and explicit scorer/provenance contracts for each agent. | P0 | T23-00 | `backend/evaluation/phase23/dataset_v1.json`; tests. | Dataset integrity and expected-label tests; no untracked local corpus dependency. | VERIFIED COMPLETE |
| T23-02 | P23-R001–R003, R008 | Implement shared candidate runner/report metadata for provider/model, fixed config, attempts, safe errors, latency, and available usage. | P0 | T23-01 | `backend/scripts/evaluate_phase23_agent.py`; tests. | Fake adapter produces reports; secrets/prompts are absent; unavailable usage is explicit; external routes require explicit opt-in. | VERIFIED COMPLETE (HARNESS ONLY) |
| T23-03 | P23-R002 | Complete Document Agent scorer and segments for its represented case attributes. | P0 | T23-01, T23-02 | Phase 23 document scorer and fixtures; tests. | Classification, field/required-field accuracy, hallucinated/unsupported rate, citation locator correctness, and per-segment denominators are tested. | VERIFIED COMPLETE (SCORER ONLY) |
| T23-04 | P23-R003–R005 | Add labeled agent-specific Verification, Workflow, and Supervisor scoring through existing contracts. | P0 | T23-01, T23-02 | Agent score modules/fixtures and tests. | Task-level quality/safety criteria are scored without applying proposals; the Supervisor integration suite verifies deterministic trace/bounds/failure/recovery contracts, but candidate-model behavior on those runtime paths is unmeasured. | IN PROGRESS |
| T23-05 | P23-R006 | Add repeated-run, system-level evaluation/reporting for completion, time, intervention, errors, false outcomes, throughput, variance and available usage. | P1 | T23-01–T23-04 | Isolated harness/report schema and tests. | System score remains separate; state is isolated and cleaned; report includes run conditions and limitations. | NOT STARTED |
| T23-06 | P23-R007 | Identify and approve licensed/explicitly authorized representative documents and allowable routes before use. | P1 | T23-00; owner authorization | Provenance/approval register; corpus manifest if available. | No external evaluation of business documents until license/authorization and route/data approvals are recorded. | BLOCKED |
| T23-07 | P23-R008 | Run comparable per-agent candidate evaluations and create route-specific evidence-based recommendation. | P1 | T23-02–T23-06; live-call approval and credentials | Run reports and decision record. | Same cases/scorer/config per candidate, failure denominator included; real reports observed; no unsupported winner claim. | BLOCKED |
| T23-08 | P23-R001–R008 | Reconcile plan, checklist, roadmap, progress report, README and documentation index with evidence. | P1 | T23-01–T23-07 | Existing docs and phase plan. | Docs agree, statuses are evidence-backed, tests/commands and limitations are reproducible. | IN PROGRESS |

## F. Testing strategy

- Add deterministic tests for manifest integrity, version/hash pinning, scoring functions, false accept/reject and unsupported-output denominators, error accounting, usage-unavailable behavior, safe report serialization, repeat-run aggregation and candidate separation.
- Inject the existing fake `JsonModelAdapter` for harness contract tests. These tests prove runner and scorer behavior only; they are not model-quality evidence.
- Use existing agent-specific contract/security tests as regression when the runner calls those agent codepaths. Do not use mocked output to claim comparative provider results.
- Run live provider evaluations only with synthetic/public/non-sensitive fixed inputs, a bounded explicit candidate/call count, applicable provider authorization and accepted usage/cost. Record throttling, failures and timeouts; do not hide them.
- Run any end-to-end system evaluation against a disposable SQLite/PostgreSQL database and isolated synthetic identities, never the user's shared operational database. If required services are unavailable, preserve blocked status.
- Before closing, run new Phase 23 tests, touched agent/gateway regressions, critical Ruff, and the full backend regression if production code changed. Frontend/migrations are out of scope unless implementation reveals a required dependency.

### Reproducible local commands

Run from `backend/` in PowerShell. The module form is intentional so Python resolves the backend `app` package:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_phase23_evaluation.py
.\.venv\Scripts\ruff.exe check --isolated --select E9,F821 scripts\evaluate_phase23_agent.py tests\test_phase23_evaluation.py
.\.venv\Scripts\python.exe -m scripts.evaluate_phase23_agent --agent document --provider fake --limit 4 --runs 2
.\.venv\Scripts\python.exe -m scripts.evaluate_phase23_agent --agent verification --provider fake --limit 4 --runs 2
.\.venv\Scripts\python.exe -m scripts.evaluate_phase23_agent --agent workflow --provider fake --limit 4 --runs 2
.\.venv\Scripts\python.exe -m scripts.evaluate_phase23_agent --agent supervisor --provider fake --limit 4 --runs 2
```

Fake-provider output validates the runner/scorer wiring only; it is not model-quality evidence. For an explicitly bounded synthetic-only candidate run, configure a provider credential locally and add `--confirm-external-calls` to the selected provider command. Reports are written under the Git-ignored `data/phase23_evaluation/reports/` directory unless `--output` is supplied. Never use real business documents until their provenance and provider/data approval are recorded.

## G. Risks, blockers, and decisions

| Risk/blocker | Impact | Resolution needed | Status |
|---|---|---|---|
| No approved representative business corpus or route/data approval found | Checklist's authorized-document portion and generalization evidence cannot be satisfied honestly. | Owner provides licensed/authorized non-sensitive corpus and approves applicable provider route/data classes, or records authorized local-only evaluation route. | BLOCKED |
| Live provider evaluation can consume quota/cost and transmit request content | Synthetic-only bounded external calls are authorized, but candidate evidence cannot be obtained because no provider credentials are configured. No live request has been sent. | Configure the chosen provider credentials locally and select a candidate/model and usage budget; representative business data still requires separate documented authorization. | BLOCKED |
| Phase 17 dataset is ignored and missing in clean checkout | Existing live Document Agent evaluator is not a repeatable repository benchmark as-is. | Check in a distinct non-sensitive dataset or deterministic Phase 23 fixture/generator plus manifest validation. | OPEN |
| Provider usage/cost is heterogeneous or unavailable | Cost/throughput comparison may be incomplete. | Record raw provider-reported usage when available; note missing metrics; use only dated verified rates for cost. | OPEN |
| No official numeric thresholds define winners | A benchmark can compare evidence, but cannot invent acceptance gates. | Report per-agent measurements and justified recommendation with uncertainty; ask owner only if product requires a hard numeric gate. | OPEN |

## H. Definition of Done

1. Each Section 23 requirement maps to a fixed case set, configuration/prompt identity, scoring rule, reproducible command and report.
2. Four agent-level scorecards measure the criteria in the checklist, including reliability/failure denominators, latency, and available usage; their results stay separate.
3. System-level evaluation runs after agent evaluation and separately measures the checklist's workflow metrics over repeated runs.
4. Synthetic data is retained as a controlled baseline. Any representative business corpus has recorded provenance, license/explicit authorization, data classes, approved route, and handling limits before use.
5. Route choices are justified separately per agent using comparable evidence; unavailable costs/usage, failure limits, sample size and dataset generalization limits are explicit.
6. Relevant deterministic tests and regression checks pass. Live/hosted/production claims only use observed evidence.
7. Plan, checklist, progress report, roadmap, README and index agree. The phase remains IN PROGRESS while mandatory evaluation/authorization evidence is blocked or missing.

## Progress log

### 2026-10-12 — Milestone 0: repository inspection and scope establishment

- **Verified:** clean `main` at `090dd9f`; the official objective is Phase 23 evidence-based model choice in roadmap §33 and checklist §23. No Phase 23 plan existed. The checklist requires separate Document/Verification/Workflow/Supervisor evaluation before system evaluation and specifically names per-agent and system metrics.
- **Verified:** configurable agent routes and model gateway are implemented; the Document Agent has a single-route Phase 17 evaluator; a separate Phase 17 workflow script injects synthetic gold fields and is not a model comparison. Existing Phase 17 synthetic data is ignored by Git. Provider usage may be available through adapter `last_usage`; agent execution persistence does not consistently record provider token counts.
- **Verified:** provider review prohibits sending real/confidential business data to unapproved external routes; no approved representative corpus was identified. Current route defaults are baselines, not winners.
- **Changed:** created this living plan before Phase 23 implementation. Task T23-00 is complete; T23-01 onward are pending except the documented authorization blockers.
- **Tests:** no Phase 23 tests or provider evaluations run during inspection. Prior Phase 22 results are reused as historical baseline only.
- **Next actions:** establish a tracked, versioned synthetic evaluation dataset and scorer contract; implement offline-tested per-agent runner and metric reports; then request/confirm authorization before bounded external model calls or using any representative business documents.

### 2026-10-12 — Milestone 1: synthetic benchmark and offline runner

- **Changed:** added the tracked v1 manifest with four fictional synthetic cases for each of Document, Verification, Workflow, and Supervisor; fixed task prompts/schemas and agent-specific scoring; common runner metadata for dataset/prompt/scorer hashes, provider/model identity, attempts, safe failure classes, per-case latency, optional provider usage, repeated-run variance, and represented Document segments. Reports omit prompts, source content, raw model responses, and credentials. Added an ignored location for generated Phase 23 reports.
- **Verified:** focused tests passed **8/8** (`pytest -q tests/test_phase23_evaluation.py`); critical Ruff (`E9,F821`) and Python byte-compilation passed. The offline CLI was smoke-run across all four roles with four cases and two runs each (**32 fake calls**); this demonstrates harness execution only and is not candidate quality evidence.
- **Boundary:** the user authorized bounded external provider calls on synthetic cases only. No calls were sent because no Groq, LLM7, Kilo, or Gemini credentials are configured; Ollama was unreachable. Docker API access was denied by its named-pipe permission. No authorized representative business corpus or route approval is recorded. No production business data was sent.
- **Open:** live per-agent comparisons and route recommendations (R008), per-candidate Supervisor trace/recovery behavior (part of R005), system-level repeated workflow evaluation after route selection (R006), and representative authorized-document evaluation (R007). The checklist's official acceptance boxes remain unchecked.

### 2026-10-12 — Milestone 2: Supervisor runtime preflight and remaining gates

- **Verified:** `tests/test_supervisor_agent.py` passed **16/16**. Coverage includes parent/child trace linkage, bounds and truncated context, provider/child failures, stale-case handling, and recovery/fail-safe outcomes. This is deterministic integration evidence for the runtime contract; it is not evidence that a candidate model produces better Supervisor plans.
- **Verified:** current local settings still contain no Groq, LLM7, Kilo, or Gemini credential. Docker API access remains denied by the Docker Desktop named pipe.
- **Decision:** do not use `scripts/evaluate_phase17_workflows.py` as Phase 23 system evidence: it disables orchestration, injects synthetic gold extraction, and creates records in its configured application database. The Phase 23 system benchmark remains sequenced after per-agent route evaluation and must use a disposable isolated database.
- **Open:** live comparisons cannot run until a local candidate credential/model is configured. System evaluation also needs selected per-agent routes and a safe isolated runtime. Representative-document evaluation requires an authorized corpus and route/data record.

### 2026-10-12 — Milestone 3: full agent suite preflight, static checks, and harness confirmation

- **Verified:** `tests/test_document_agent.py`, `tests/test_verification_agent.py`, and `tests/test_workflow_agent.py` passed **35/35**. Combined with `tests/test_supervisor_agent.py` (**16/16**), all four agent runtime suites pass **51/51** deterministic integration tests.
- **Verified:** focused Phase 23 evaluation suite `tests/test_phase23_evaluation.py` passed **8/8** (total **59/59** agent runtime and evaluation tests passing).
- **Verified:** critical Ruff lint (`.\.venv\Scripts\ruff.exe check --isolated --select E9,F821 scripts\evaluate_phase23_agent.py tests\test_phase23_evaluation.py`) passed cleanly with zero warnings/errors.
- **Verified:** Python byte-compilation on evaluator script and test file completed with zero errors.
- **Verified:** repeated fake-provider CLI smoke runs across all four agent tasks (`document`, `verification`, `workflow`, `supervisor`) completed 32 calls (4 cases × 2 runs each) with zero failed calls, validating scoring logic, segment breakdowns, variance calculation, and safe report generation into `data/phase23_evaluation/reports/`.
- **Confirmed environment constraints:** provider keys (`GROQ_API_KEY`, `LLM7_API_KEY`, `KILO_API_KEY`, `GEMINI_API_KEY`) remain unconfigured; local Ollama endpoint (`127.0.0.1:11434`) is unreachable; Docker Desktop named-pipe is inaccessible. No licensed or explicitly authorized representative business-document corpus exists.
- **Remaining work:** live candidate comparisons and route selections (T23-07), system-level model benchmark (T23-05), and authorized-document evaluation (T23-06) remain blocked pending credentials, running endpoints, and corpus authorization.

### Final local revalidation — 2026-10-12

The fresh full backend regression passed **277 tests, skipped 7, failed 0**, including the Phase 23 evaluator and agent-runtime suites. No provider call was made in this review, and the live-test switch was disabled. This confirms the synthetic harness/runtime tests only; it does not close P23-R006 system-level comparison, P23-R007 authorized-corpus evaluation, or P23-R008 live route comparison/selection. Keep those requirements open until the documented route, corpus, and data approvals exist. See §9 of the [Phases 20–24 audit plan](phases20-24-comprehensive-audit-plan.md).

## Cross-phase note — 2026-10-17

[Phase 27 — AI Research & Evaluation Foundation](phase27-ai-research-evaluation-plan.md) adds a documented backlog for broader Document Agent and RAG coverage, a decision on RAG-to-agent integration, model readiness, runtime evaluation traceability, and additional Supervisor/adversarial scenarios. Phase 23 remains the authoritative owner for P23-R005 Supervisor scorer completion, P23-R006/T23-05 system-level evaluation, P23-R007/T23-06 corpus approval, and P23-R008/T23-07 per-agent comparisons and route recommendations. Phase 27 references those tasks instead of duplicating or closing them. Phase 17's missing threshold remains a separate blocked dependency; no value is inferred in either plan.

