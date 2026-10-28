# VerifiaAI — Official Phase 20–21 Compliance Audit

**Audit date:** 2026-10-11  
**Repository at audit start:** branch `main`, clean working tree at `098e075`.  
**Current disposition:** Phase 20 **PARTIAL**; Phase 21 **PARTIAL pending current live-worker/readiness recheck**.  
**Authoritative inventory:** [Phase 20–21 Official Compliance Matrix](phase20-21-official-compliance-matrix.md).

## A. Official sources reviewed

The audit read the actual Phase 20–21 checklist sections and their cited supporting material, then compared them with the source, tests, configuration, migrations, and prior phase reports:

- `Documentation/Verifia_Detailed_Implementation_Checklist.md` §§2.12, 20–22, including the event type inventory, security items, Case-history sequence, delivery/readiness items, and adjacent failure-test scope.
- `Documentation/04-operations-and-roadmap.md` §33, for the original Phase 20 production-security and Phase 21 operational-event scope.
- `Documentation/02-architecture.md` §§21–22 and `Documentation/03-database-schema.md` §26.41, for event flow, Case lifecycle, and transactional outbox behavior.
- `README.md`, `Documentation/progress_report.md`, `Documentation/phase20-21-requirements-traceability.md`, `Documentation/phase20-21-final-closeout.md`, `Documentation/phase20-production-security-implementation-plan.md`, `Documentation/phase21-durable-events-implementation-plan.md`, `Documentation/external-model-provider-review.md`, and `Documentation/RUNNING_THE_PROJECT.md`.
- Relevant backend configuration and source: `backend/app/core/config.py`; Case, document, verification, approval, task, audit, workflow and orchestration services; event service, models, delivery and worker; provider gateway/adapters; the `0011_durable_event_deliveries` migration.
- Relevant automated tests were inspected and run, including Phase 20 security, document upload/processing, provider adapters, tool/agent authorization, readiness, event delivery/orchestration, domain APIs, human review, and the authenticated Case journey.

At audit start the current checklist had every Phase 20 box unchecked and every Phase 21 box checked. Git history confirms Phase 21 was unchecked before the prior Phase 21 implementation was recorded. That prior checked state was re-tested rather than accepted as evidence.

## B. Official requirements inventory

The [official matrix](phase20-21-official-compliance-matrix.md) contains **23 Phase 20** and **11 Phase 21** stable IDs with original source, A/B/C/D classification, checklist status at audit start, acceptance behavior, code, tests, changes, remaining gap, action, and final checklist status.

The core official scope is:

- **Phase 20:** tenant/case/document/tool authorization; secrets/API-key handling; fail-closed production settings; exact CORS/docs policy; upload/file/storage review; untrusted document and least-privilege AI boundaries; external-model data classes and provider policy; synthetic test data; provider terms/redaction; and per-agent route failure behavior.
- **Phase 21:** centralized event creation; the documented Case-history sequence; authorized Case and audit history; timestamps/actor/source/tool links; durable event/outbox delivery; retries, duplicate handling, replay and worker recovery; and API liveness versus dependency readiness.

The roadmap’s Phase 20 and Phase 21 summary requirements map to the detailed checklist. The database schema adds one technical detail not stated verbatim in checklist §21: the event and trusted outbox write must share a transaction. This is classified **D**, a derived task required for durable delivery, and it is implemented and failure-tested.

## C. Checklist compliance

The matrix records each item and its original checkbox state. Phase 20’s former unchecked items were updated only where source and tests supported completion. Phase 21’s prechecked boxes were independently validated. Key statuses:

- **Phase 20 verified:** organization/case/document/tool authorization; production-secret separation and absence of provider keys in tracked source (the tracked env files are example templates with development/example defaults or placeholders); unsafe-startup rejection; CORS/docs rules; upload/content review and production fail-closed restriction; untrusted-input boundaries; least-privilege, structured tool contracts, and absence of agent SQL/shell tools; synthetic-only current provider use; configurable route allowlisting; and documented timeout/retry/failure policy.
- **Phase 20 partially complete:** provider retention/training terms, approved data classes, and field-level minimization/redaction are not complete. No provider is approved for real business data.
- **Phase 21 verified locally:** event taxonomy and history, actor/time attribution, authorized history, audit serialization, outbox transaction behavior, retry/replay/readiness tests, and an authenticated Case journey to completion.
- **Phase 21 implemented, not fully verified:** current Docker-backed multi-worker recovery and live readiness probes could not be repeated during this audit. Prior successful live probes are retained as dated historical evidence, not represented as a current rerun.

## D. Phase 20 results

**Disposition: PARTIAL.** The official local controls pass. The provider review requirement remains open: terms and data classes have not been approved, and the app has no field-level redaction/minimization. Staging and production deny external model routes by default; only synthetic/public/non-sensitive evaluation inputs may be sent before a route receives approval. Real case documents/text, identifiers, financial/payment data, credentials, secrets, and confidential business records remain local.

The upload review found no scanner integration. Production and staging therefore disable uploads by default and now reject `ALLOW_UNSCANNED_UPLOADS=true`; the MIME/signature/size validators are not presented as malware scanning. This satisfies the documented review and restriction, while a scanner itself remains absent.

Local environment validation, CORS/docs, route authorization, AI input/tool boundaries, and provider adapter behavior passed the backend regression. Production host topology and runtime storage checks were not exercised. Those production-hardening proposals are distinguished from the official checklist in sections J and the matrix.

## E. Phase 21 results

**Disposition: PARTIAL pending live recheck.** The raw Case history now uses the documented names `DOCUMENT_PROCESSED`, `TASK_COMPLETED`/`TASK_REJECTED`, and `APPROVAL_GRANTED`/`APPROVAL_REJECTED`; prior aliases remain accepted by orchestration. Verification now records `VERIFICATION_STARTED`. The isolated authenticated journey asserts the persisted lifecycle, timestamps, actors, audit access, tenant isolation, and final Case status.

Case, task, and approval business changes now add their event/outbox before commit. Eight injected event-insert failures verify rollback. The event system remains at-least-once: persisted orchestration-result checks suppress repeat completed orchestration, but an external effect before its local result is persisted still requires downstream idempotency. No exactly-once external-side-effect claim is made.

The full backend regression and readiness/delivery tests pass. Prior two-worker fresh-delivery and expired-lease probes passed on 2026-10-11. A repeat of those Docker probes and the live API/Nginx readiness checks was blocked in this audit because access to the Docker Desktop named pipe returned permission denied. No worker healthcheck exists; the original Phase 21 checklist requires API liveness and dependency readiness, not a worker heartbeat.

## F. Missing requirements discovered

The audit found these confirmed gaps and corrected them:

1. **Production upload override bypass:** production validation accepted `ALLOW_UNSCANNED_UPLOADS=true`, bypassing the no-scanner gate. Production/staging validation now rejects it, and the Phase 20 security test covers this input.
2. **State/event transaction ordering:** Case, task, and approval mutations could commit before adding their history event. If event insertion then failed, durable business state could be left without the required event. Event emission now occurs before commit; eight rollback tests cover Case create/close, approval request/decision, and task assignment/start/comment/resolution.
3. **Missing verification-start event:** the verification execution had a completion record but no `VERIFICATION_STARTED` history event. The service now stores it with the execution before evaluation.
4. **History taxonomy mismatch:** document completion, task completion, and approval decisions were persisted under generic/alternate names. Producers now use the event names listed in checklist §2.12 and the §21 history sequence; orchestration retains aliases for old events.
5. **Audit resource UUID serialization:** an authorized audit read could fail because an ORM UUID was returned for a string schema field. The serializer now converts the identifier to text, covered by the Case journey audit read.

The roadmap-level requirements were not missing from the checklist. Checklist §21 already contains event history, delivery, retries, replay/duplicate behavior, multi-worker, and readiness items; their detailed sources and verification appear in the matrix. Database-schema transaction coupling is recorded as derived work, not an invented independent phase.

## G. Implementation and fixes

Source changes:

- `backend/app/core/config.py` — fail closed on unscanned upload override in production/staging.
- `backend/app/domain/cases/service.py`, `backend/app/domain/approvals/service.py`, `backend/app/domain/tasks/service.py` — emit domain events/outbox before transaction commit; use explicit completion/grant/rejection event types; normalize approval enum values.
- `backend/app/domain/documents/processing.py` — emit `DOCUMENT_PROCESSED`.
- `backend/app/domain/verifications/service.py` — persist `VERIFICATION_STARTED`.
- `backend/app/domain/cases/orchestrator.py` — accept explicit event types and legacy aliases.
- `backend/app/domain/audit/schemas.py` — serialize UUID resource IDs as strings.

Test changes:

- `backend/tests/test_event_business_state_atomicity.py` — eight state rollback cases.
- `backend/tests/test_case_journey_e2e.py` — full authenticated event/history/audit/tenant-scope assertions and completed task event.
- `backend/tests/test_phase20_security_e2e.py` — production unscanned-upload override rejection.
- `backend/tests/test_human_review.py` and `backend/tests/test_domain_api.py` — approval/task event names and rejected-approval behavior.

No migration was added in this audit. Existing migration history remains unchanged.

## H. Test execution results

| Check | Command/result | Notes |
|---|---|---|
| Focused security/event/API/provider selection | 11 targeted test modules passed after final event changes. | Included atomicity, Case journey, Phase 20 HTTP security, delivery, readiness, domain API/services, human review, orchestration, model gateway, and external-model adapters. |
| Phase 20 security suite | **10 tests collected and passed** within the full regression. | `backend/tests/test_phase20_security_e2e.py`; includes rejection of the production unscanned-upload override. |
| Full backend regression, direct host run | `rtk proxy python scripts/run_backend_regression_windows.py` — **254 passed, 8 failed, 7 skipped**. | The eight failures were auth tests blocked by host bcrypt 5.0.0 rejecting inputs over 72 bytes, while the project pins bcrypt `<4.1`; this was an environment/dependency mismatch. |
| Full backend regression, compatibility run | From `backend/`, `rtk proxy python -c "import bcrypt; original_hashpw = bcrypt.hashpw; bcrypt.hashpw = lambda secret, salt: original_hashpw(secret[:72], salt); import sys; sys.argv = ['scripts/run_backend_regression_windows.py']; from scripts.run_backend_regression_windows import main; raise SystemExit(main())"` — **269 collected, 262 passed, 7 skipped, 0 failed in 62.15s**. | In-memory process-only bcrypt 4.x behavior shim; no installed dependency or application auth code changed. Six skips are opt-in live-provider checks; one is the explicitly BLOCKED Phase 17 threshold-file gate. |
| Ruff/static checks | Ruff **0.16.9** is available; `backend/requirements-dev.txt` specifies `ruff>=0.6.0` without an exact pin. `ruff check --select F821 app tests scripts` and the full Ruff check of the new rollback test pass. The repository-wide default check exits 1 with **1,326 findings**. `compileall` and `git diff --check` pass. | No broad auto-fix was applied. The whole-repository lint backlog remains; it does not change Phase 20/21 functional test results. |
| Docker worker/readiness runtime | **BLOCKED during this audit**. | Docker Desktop named-pipe access returned permission denied. No container was restarted or modified. Prior 2026-10-11 probes are identified as historical. |
| Phase 17 threshold test | **BLOCKED** skip with explicit reason. | `data/phase17_evaluation/acceptance_thresholds.json` is ignored, absent, and unavailable; no threshold values were invented. This is a prior-phase gate, not a Phase 20/21 failure. |

The full regression includes the focused test changes. No live model provider, ERPNext API, shared operational database, or synthetic production Case was used in the added tests. The Case journey uses disposable SQLite fixtures and deterministic model behavior.

## I. Documentation consistency

Updated the checklist statuses and evidence, provider data classification and timeout/retry table, run-guide upload policy, roadmap status, README test total, progress report, Phase 20/21 plan reconciliation, and current compliance artifacts. The old `phase20-21-requirements-traceability.md` and `phase20-21-final-closeout.md` now have superseded banners pointing to the current matrix/report; their prior dated results remain historical.

The current records agree: Phase 20 is partial pending provider terms/data-class approval; Phase 21 is locally test-backed but its current live Docker recheck is pending; Phase 17 remains blocked. The matrix separates original checklist requirements from later plan proposals.

## J. Optional proposals excluded from mandatory scope

These were not promoted to official Phase 20/21 requirements solely because they appeared in later AI-assisted plans:

- Full production TLS termination, firewall/backup/secret-rotation runbooks, managed-service connectivity, production image build, and named-volume runtime verification.
- A malware-scanner service, quarantine workflow, or cloud-storage adapter. The selected current production restriction is to reject unscanned uploads until scanning is configured.
- A worker heartbeat/Compose healthcheck. The official readiness item is API liveness versus PostgreSQL/Redis readiness.
- Whole-project Ruff/mypy cleanup. Phase 22 CI, broader cross-tenant coverage, and migration-from-empty/upgrade gates remain in their owning scope.

These tasks may be useful before a real production deployment, but they are not used to downgrade an official Phase 20/21 requirement unless the source documents require them. Provider approval and the unscanned-upload restriction are official/current data-policy concerns and remain recorded as described above.

## K. Final acceptance matrix

| Official requirement group | Result | Evidence summary |
|---|---|---|
| P20-OFFICIAL-001–021, P20-OFFICIAL-023 | **PASS** | Local authorization, startup, CORS/docs, upload review/restriction, AI/tool, and provider-route behavior pass the full regression. See individual statuses in the matrix. |
| P20-OFFICIAL-022 — provider terms and data minimization before business data | **PARTIAL** | Provider inventory exists, but terms/data-class approvals and field-level redaction are not complete. Real business data remains prohibited from outbound routes. |
| Phase 20 overall | **PARTIAL** | Required provider review work remains open. No production readiness claim is made. |
| P21-OFFICIAL-001–006, P21-OFFICIAL-010–011 | **PASS** | Local event taxonomy/history, authorization, attribution, audit, tool links, and isolated journey pass tests; delivery contract is documented at-least-once. |
| P21-OFFICIAL-007–009 — atomicity, multi-worker recovery, live readiness | **PARTIAL** | Automated/isolated tests pass; current Docker runtime recheck was blocked. Prior live Docker results remain historical, not a current rerun. |
| Phase 21 overall | **PARTIAL** | Core local behavior is verified; current live worker/readiness confirmation is outstanding. |
| Phase 17 historical thresholds | **BLOCKED** | Original threshold file is absent and unavailable; no values were recreated. Separate from Phase 20/21. |

No phase is declared fully complete while the above required provider review and live recheck evidence remain open.


## Supplemental revalidation - 2026-10-12

This dated supplement supersedes only the prior pending live-worker statement where later Phase 22 evidence exists. The Phase 22 plan records PostgreSQL migration-to-head, stale-claim fencing, two-worker delivery, and simulated expired-lease recovery passing on 2026-10-12. The Docker Desktop Linux-engine pipe was missing during the newer comprehensive audit, so those checks were not repeated in that run.

The full backend regression passed 277 tests, skipped 7, and failed 0. Six skips are opt-in external integrations; one is the blocked Phase 17 threshold gate. Phase 20 remains PARTIAL because provider/data approvals and production deployment evidence are open. Phase 21 internal event, readiness, transactional rollback, and authenticated Case lifecycle behavior is locally verified; no real ERPNext or production environment is claimed. See the [Phases 20-24 comprehensive audit](phases20-24-comprehensive-audit-plan.md) for the latest requirement status.
