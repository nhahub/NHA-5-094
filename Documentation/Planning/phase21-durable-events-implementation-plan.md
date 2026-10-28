# Phase 21 — Durable Events, Recovery, and Readiness

**Status:** PARTIAL — fresh PostgreSQL worker-delivery/recovery and API readiness probes passed on 2026-10-13. PostgreSQL-specific transaction-failure verification and real ERPNext integration are not verified.
**Planning source:** This repository did not contain a standalone Phase 21 plan when the audit began. Scope below is derived from `04-operations-and-roadmap.md` §33, the Implementation Checklist §21 (Events & Auditability), and §22 (Testing); this document records that derivation rather than inventing a new phase objective.

## 1. Documented objective

The roadmap defines Phase 21 as operational event guarantees: durable delivery, retry/dead-letter handling, idempotency, replay, and duplicate handling across worker restarts and multiple workers, with dependency-aware readiness. The checklist adds the event-history expectations: one event creation boundary, authorized Case and audit history, timestamps, actor/source attribution, and links to tool executions where relevant.

### Prerequisites and dependencies

- Phase 19 identity and tenant authorization provides the actor, organization, Case, and audit boundaries used by event-history routes.
- Phase 20 production configuration and service wiring provides the database/cache checks, container network, and upload/provider policy. Phase 20 remains partial pending production topology and provider/storage review; Phase 21 does not approve any provider route or production deployment.
- PostgreSQL is authoritative for event rows and delivery state. Redis remains an API readiness dependency, not the event outbox.
- Existing Case orchestration and `EventService` remain the business dispatch path. A separate message broker/API was not required by the documented scope.

## 2. Implementation

- Added `EventDelivery`, a one-to-one outbox record for trusted events, and Alembic migration `0011_durable_event_deliveries`.
- Added a transaction-aware `EventService.add_event` boundary. Existing event-producing domain paths, including document processing and Supervisor lifecycle records, now use this shared constructor; event creation and trusted outbox insertion share the caller's transaction.
- Added a standalone `python -m app.events.worker` process. Compose runs it separately from the API and permits multiple replicas. PostgreSQL `FOR UPDATE SKIP LOCKED` claims rows, a lease expiry makes interrupted work reclaimable, and a per-claim token prevents stale workers from finalizing a newer claim.
- Added capped exponential retry, a five-attempt dead-letter limit, trusted-event replay via `CaseOrchestrator.resume_event`, and the operator command `scripts/replay_event_delivery.py <EVENT_UUID>`.
- Preserved persisted orchestration-result checks for duplicate completed dispatches. Delivery is explicitly **at least once**: effects made in an external system before a corresponding persisted result still require that system's own idempotency key.
- Added `/livez` and dependency-aware `/readyz`; readiness checks PostgreSQL and Redis. Worker state remains separately observable through Compose because the documented health endpoint does not have a worker heartbeat.
- Updated the frontend Nginx backend health proxy and local/production Compose API health checks to use `/readyz`.
- Removed the eager `app.events` router import that caused a circular import when starting `python -m app.events.worker`; package exports now load lazily.

## 3. Recovery runbook

For a host-run backend, apply migrations and start the worker from a separate terminal:

```powershell
Set-Location backend
.venv\Scripts\Activate.ps1
python -m app.events.worker
```

The full Docker stack starts a worker automatically. To scale the Compose workers:

```powershell
docker compose up -d --scale event-worker=2 event-worker
docker compose ps event-worker
```

After identifying a trusted failed/dead-lettered event UUID from authorized operational records, an operator with database access can replay it:

```powershell
Set-Location backend
python scripts/replay_event_delivery.py <EVENT_UUID>
```

The replay command accepts only trusted events and does not override an active lease or a completed delivery. It reports delivery status, attempt count, and a safe error code; it does not print event payloads or raw provider errors.

## 4. Traceability and verification

See [Phase 20–21 requirement and test traceability](phase20-21-requirements-traceability.md) for requirement IDs, implementation/test references, evidence, and remaining limits. The live Compose worker check is `python scripts/phase21_worker_e2e.py`; `--simulate-expired-lease` begins with persisted interrupted-worker state to exercise recovery. Those worker probes validate delivery/recovery. The separate `backend/tests/test_case_journey_e2e.py` validates an isolated authenticated API journey through approval and completion; it does not call ERPNext.

## 5. Completion status

The core durable delivery, retry, replay, multi-worker claim, event linkage, and API readiness requirements are implemented and have focused executable coverage. The local PostgreSQL migration was applied; API liveness/readiness and the frontend Nginx readiness proxy returned success; two live Compose worker probes completed fresh and expired-lease events with exactly one orchestration result each. An isolated authenticated API journey also exercised document processing, verification, workflow, manager approval, event/audit history, and persisted completion. The historical Phase 17 10-scenario evaluator was not run against the shared DB because it persists data, the current stack lacks an active EMPLOYEE account, and ERPNext is not running. The isolated journey meets the internal Case lifecycle scope but does not establish live ERPNext behavior. No Phase 21 evidence establishes production TLS, provider approval, or production storage permissions.

### Official checklist reconciliation — 2026-10-11

The raw event taxonomy now matches the original checklist sequence (`DOCUMENT_PROCESSED`, `TASK_COMPLETED`, `APPROVAL_GRANTED`/`APPROVAL_REJECTED`) while orchestration continues to accept legacy aliases. The full backend regression passed 262 tests with 7 explicit skips and no failures. Docker-backed probes could not be repeated during the latest audit because the Docker Desktop named pipe was inaccessible; prior successful live probes are historical. See the [official compliance matrix](phase20-21-official-compliance-matrix.md) and [A–K audit](phase20-21-official-compliance-audit.md) for the evidence boundaries and requirement classification.

### Post-commit verification — 2026-10-12

The fresh focused event, transaction-failure, readiness, and authenticated Case journey group passed, and the full backend regression passed **277 tests** with 7 documented skips. Docker check `rtk docker compose ps` exited 1 because `//./pipe/dockerDesktopLinuxEngine` was unavailable, so no PostgreSQL multi-worker or live healthcheck result was reproduced. The successful PostgreSQL migration/fencing/two-worker/expired-lease probes recorded in the Phase 22 plan remain historical. Phase 21 is therefore **PARTIAL** pending fresh infrastructure probes; do not substitute the SQLite/unit results for multi-worker PostgreSQL evidence. Exact commands and per-requirement status are in the [Phases 20–24 audit plan](phases20-24-comprehensive-audit-plan.md).

### Fresh Docker verification — 2026-10-13

The running Compose stack was inspected without restarting services. Alembic reports `0011_durable_event_deliveries (head)`; `/livez` and `/readyz` each returned HTTP 200. All three PostgreSQL worker probes exited 0: stale-claim fencing finalized only the reclaimed lease; normal delivery completed with `attempts=1, duplicate_results=0`; expired-lease recovery completed with `attempts=2, duplicate_results=0`. The probes create isolated synthetic organization/event rows and remove them in `finally` cleanup. Two event-worker containers were running. These results supersede the 2026-10-12 Docker-unavailable note for worker/readiness checks. PostgreSQL transaction rollback under injected event-write failure and real ERPNext integration remain unverified.
