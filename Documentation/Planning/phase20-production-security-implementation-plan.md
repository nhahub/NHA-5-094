# VerifiaAI — Phase 20 Production Security Implementation Plan

**Status:** PARTIAL — local security controls are tested; provider/data approval and production topology/storage/scanner evidence remain open.
**Planning baseline:** 2026-10-11  
**Roadmap position:** Next after Phase 19; follows the Phase 18 frontend and Phase 19 identity/access work

## 1. Executive Summary

Phase 20 makes the existing development-oriented application configuration safe to deploy deliberately. It will fail closed when production starts with unsafe or missing security settings, establish explicit CORS and API documentation exposure rules, strengthen upload handling at every entry point, and define which business data may be sent to which external model providers.

The code already has useful controls: document uploads have type/signature checks and size limits, DOCX archives have expansion limits, the frontend Nginx config sets several browser security headers, and provider calls use configurable adapters. Those controls do not amount to a production policy yet. In particular, the backend defaults to a known development JWT key, debug mode, and wildcard CORS; the docs routes are always registered; the knowledge upload route reads the complete file before applying service validation; and the deployment and external-provider data rules are not explicit.

This plan separates existing controls from new acceptance requirements. It proposes a small configuration policy, tests at the application/configuration boundaries, and operational documentation. Phase 20 must not claim that an external provider is approved merely because an API key or adapter is configured.

## 2. Repository Baseline

The following facts were checked in the current repository:

| Area | Current behavior | Phase 20 implication |
|---|---|---|
| Backend settings | **backend/app/core/config.py** defaults to APP_ENV=development, DEBUG=true, a fixed development SECRET_KEY, and BACKEND_CORS_ORIGINS=[*]. Its CORS parser can fall back to wildcard origins. | Add explicit environment-aware validation and reject production placeholders, weak secrets, debug mode, and wildcard or malformed origins before the app serves requests. |
| API documentation | **backend/app/main.py** disables the OpenAPI JSON URL when DEBUG is false, but always registers /docs and /redoc. | Decide and implement one production policy for OpenAPI, Swagger UI, and ReDoc. Hidden-by-default is the recommended default. |
| CORS | The middleware currently permits credentials, all methods, and all headers whenever origins are configured. | Set a narrow production origin allowlist and the smallest required methods and headers. Confirm whether credentialed browser requests are needed; the frontend currently uses bearer-token API calls. |
| Reverse proxy | **frontend/nginx.conf** already sets nosniff, frame, referrer, permissions, and CSP headers; hides the Nginx version; proxies API routes; and limits the request body to 22 MiB. | Preserve these controls, verify them at the deployed edge, and coordinate upload limits. Do not set HSTS until HTTPS is enforced at the public TLS termination point. |
| Document uploads | **backend/app/domain/documents/upload.py** checks safe filenames, supported extensions, content signatures, declared MIME type, a 20 MiB setting, and DOCX archive limits. Document routes read no more than the configured limit plus one byte. | Retain and test the current checks; review content scanning and quarantine requirements for untrusted customer files. |
| Knowledge uploads | The knowledge upload route currently reads the full request body before passing it to service validation. | Enforce a request-size limit before unbounded memory use, consistent with document uploads and proxy limits. |
| Storage | The current configured adapter is local filesystem storage. Storage authorization and deployment mount permissions still need an operational policy. | Specify private storage, path/volume permissions, backup access, and cleanup behavior. Do not imply malware scanning exists. |
| External models | **backend/app/infrastructure/llm** supports multiple providers and per-agent routing. Provider keys and model routes are configuration-driven. The operations roadmap says to keep using synthetic/non-sensitive evaluation data until provider handling is reviewed. | Inventory every outbound route and payload; define approved data classes, minimization/redaction, provider terms, and fail-closed behavior. |
| Compose deployment | **docker-compose.yml** publishes PostgreSQL and Redis ports and contains development-friendly fallback credentials. | Keep local development simple while documenting and enforcing a separate production deployment profile with private dependencies and explicit secrets. |
| Existing tests | There are configuration and upload tests, including signature/MIME and oversize cases. | Extend them for production startup rejection, CORS/docs policy, each upload endpoint, provider policy, and secret-safe logging. |

This plan does not treat a passing unit suite as proof that production networking, TLS termination, storage permissions, or provider contracts are configured correctly.

## 3. Objective and Security Boundaries

### Objective

Make unsafe production configuration impossible to start accidentally and give operators enforceable, reviewable rules for browser access, API documentation, uploaded files, and outbound model requests.

### Security boundaries

- Deterministic authorization and tenant isolation remain enforced by backend services and routes; frontend hiding is not an access control.
- AI output remains advisory. Deterministic workflow and permission services retain business authority.
- Uploaded files and extracted text remain untrusted, even after extension, MIME, signature, or archive validation.
- An API key, provider adapter, or user-facing warning does not constitute approval to send customer data to that provider.
- Phase 20 secures configuration and data handling. Phase 21 remains responsible for durable event delivery and dependency-aware readiness; Phase 22 remains responsible for CI quality gates.

## 4. Scope

### In scope

- Production-only startup validation for the JWT secret, debug mode, allowed origins, required configuration, and development placeholders.
- Explicit CORS, OpenAPI, Swagger UI, and ReDoc exposure behavior by environment.
- Upload limits and content validation applied consistently to case documents, customer uploads, document versions, and knowledge documents.
- A documented and configurable external-model data policy with provider/model/HTTPS-origin allowlisting and safe failure behavior.
- Secret-safe logs, deployment guidance, configuration examples, focused tests, and a Phase 20 closeout record.
- A deployment review of reverse-proxy headers, TLS assumptions, published service ports, and storage permissions.

### Out of scope

- Replacing the identity/session architecture or redoing Phases 18–19.
- Implementing a full antivirus service or a cloud storage adapter. Phase 20 must decide whether a scanner is a production gate or whether unscanned upload use is restricted; it must not claim scanning is present.
- Durable queue delivery, retries/replay of domain events, or readiness redesign (Phase 21).
- Building the project CI pipeline or completing every cross-tenant regression case (Phase 22).
- Selecting winning model providers or broad model benchmarking (Phase 23).
- A general-purpose policy management UI or customer-managed provider catalog.

## 5. Recommended Policy Decisions

These are proposed defaults for implementation. If product or deployment owners choose different values, record the decision and rationale in the Phase 20 closeout before changing the behavior.

### 5.1 Production configuration

- Treat production as an explicit environment. Validate the effective settings before the FastAPI app begins serving.
- Require DEBUG=false, a non-placeholder cryptographically random secret with at least 32 bytes, an explicit non-wildcard CORS origin list, and production database credentials/URLs.
- Reject known development values and malformed origins; never silently replace invalid production input with a permissive default.
- Keep development/test defaults usable for local workflows, and add tests proving that the same defaults fail in production mode.
- Fail at startup with a concise setting name and remediation hint. Never include secret values in exceptions or logs.
- Require provider credentials only when an external provider is selected for an enabled feature. Missing optional provider configuration must not silently switch to a different provider.

### 5.2 Browser and API documentation exposure

- Production CORS is an exact allowlist of deployed frontend origins. Reject * and origin strings with paths, credentials, query strings, or fragments.
- The UI uses bearer tokens; set allow_credentials=false unless the authentication design changes to cookies and that change is reviewed.
- Replace wildcard methods and headers with only the methods and headers used by the application.
- Hide OpenAPI JSON, Swagger UI, and ReDoc by default in production. If operators require them, make exposure an explicit setting and require restriction at the trusted network boundary.
- Keep local development origins documented separately from production origins.

### 5.3 Upload and storage policy

- Enforce a configured maximum on every upload route before reading an unbounded body. Keep the API and reverse-proxy limits consistent, including multipart overhead.
- Keep extension, detected content, and declared MIME checks. Treat these as format validation, not malware detection.
- Add regression coverage for chunked/oversized requests, empty files, malformed archives, and each route that accepts an upload.
- Require private storage paths and least-privilege filesystem/volume permissions. Do not serve arbitrary uploaded files as active HTML or inline content.
- Before production accepts untrusted customer files, either integrate a maintained malware scanner and quarantine flow or explicitly restrict the deployment/use case and document the residual risk. A future scanner integration is an optional product component; the Phase 20 release gate must state which policy was selected.

### 5.4 External-model data policy

- Use a default policy of synthetic/non-sensitive data only for external providers until an exact provider/model route has been reviewed and approved.
- Create a provider inventory recording vendor, endpoint, model, region where known, retention/training terms, subprocessors or transfer notes, credential owner, and the approved data classes.
- Minimize each request to task-relevant fields. Define redaction for direct identifiers, credentials, and other restricted fields before enabling business-document data.
- Fail closed when the active agent route or payload data class is not approved. Do not silently route to another vendor.
- Never log API keys, raw document text, full prompts, or full provider responses. Log provider/model identifiers, request correlation, outcome category, latency, and safe error metadata.
- Preserve per-agent timeout, retry, and failure handling; verify that an external failure cannot approve or advance a business action.

## 6. Proposed Implementation Workstreams

### W1 — Settings validation and startup policy

**Targets:** **backend/app/core/config.py**, **backend/app/main.py**, configuration tests.

1. Add typed settings for explicit docs exposure and external-model data policy, with environment-aware defaults.
2. Validate production settings as a coherent set, including the secret, DEBUG, CORS, database configuration, and provider route requirements.
3. Remove permissive production fallbacks. Keep test settings injectable so tests do not depend on developers' local .env files.
4. Ensure validation occurs before an ASGI server binds and does not reveal secrets in traceback/log summaries.

### W2 — CORS and API docs behavior

**Targets:** **backend/app/main.py**, **backend/app/core/config.py**, API/config tests, run/deployment docs.

1. Construct FastAPI docs URLs from the resolved environment policy; test JSON, Swagger UI, and ReDoc independently.
2. Apply exact origins and the minimal method/header set. Test allowed origin, rejected origin, wildcard rejection, and preflight behavior.
3. Confirm same-origin frontend proxy behavior and local Vite development origin behavior from the run guide.

### W3 — Upload limits, content handling, and storage controls

**Targets:** **backend/app/core/middleware.py**, **backend/app/domain/documents/router.py**, **backend/app/domain/knowledge/router.py**, **backend/app/domain/documents/upload.py**, **frontend/nginx.conf**, upload tests and deployment docs.

1. Check the body size at the request/proxy boundary before buffering; replace the knowledge route's unbounded read with bounded handling.
2. Align backend byte limit, multipart allowance, reverse-proxy maximum, and frontend error behavior.
3. Apply the same upload policy to employee, customer, version, and knowledge upload flows.
4. Decide and document the scanner/quarantine or restricted-use deployment gate for untrusted files.
5. Review storage path ownership, container mounts, file permissions, backups, and orphan cleanup. Preserve safe download headers and authorization checks.

### W4 — External-model inventory and policy enforcement

**Targets:** **backend/app/agents**, **backend/app/infrastructure/llm**, provider settings/examples, provider tests, operations/security docs.

1. Trace the payload sent by each agent and embedding path to every provider adapter.
2. Add an explicit policy check before outbound calls, using agent, provider/model route, and approved data classification.
3. Add minimization/redaction at a deliberate boundary; do not attempt heuristic redaction without tests for business identifiers and document contents.
4. Ensure policy denial and provider errors produce safe, auditable outcomes without logging sensitive payloads.
5. Complete a provider terms review before approving real business documents. Until then, keep production/test guidance synthetic-only.

### W5 — Reverse proxy and deployment profile

**Targets:** **frontend/nginx.conf**, **docker-compose.yml**, **backend/.env.example**, **README.md**, **Documentation/RUNNING_THE_PROJECT.md**, deployment/security documentation.

1. Verify currently configured browser headers and document which layer terminates HTTPS.
2. Add HSTS only at a HTTPS-enforcing edge; do not send it over local HTTP.
3. Ensure production DB/Redis services are private and not published to public interfaces; remove development fallback credentials from production instructions.
4. Specify secret provisioning, rotation, environment-file permissions, storage volume permissions, and a production configuration example that contains placeholders only.
5. Keep the local quick-start and development bootstrap instructions clearly separated from production deployment.

### W6 — Verification and closeout

**Targets:** backend tests, deployment smoke checks, **Documentation/Verifia_Detailed_Implementation_Checklist.md**, **Documentation/progress_report.md**, **Documentation/04-operations-and-roadmap.md**.

1. Run focused configuration, CORS/docs, upload, provider-policy, and log-redaction tests.
2. Run the backend regression and frontend checks; report any known unrelated limitation, including the unreproducible Phase 17 thresholds gate.
3. Validate migration state only if Phase 20 changes the schema; no schema change is expected by this plan.
4. Verify production settings in a non-production deployment-like environment, including proxy headers and private dependency exposure.
5. Record exact commands/results, deployment assumptions, policy decisions, and unresolved risks in the closeout.

## 7. Implementation Order and Gates

| Gate | Work | Exit condition |
|---|---|---|
| G0 — Policy decisions | Confirm production deployment topology, public frontend origins, docs policy, upload scanner/restricted-use decision, and provider data classes/approved routes. | Decisions are written down; no policy depends on an unverified provider assumption. |
| G1 — Fail-closed config | Implement environment-aware settings validation and startup errors. | Unsafe production config is rejected; valid test/development configuration still loads; errors contain no secret values. |
| G2 — Network surface | Enforce CORS and docs policy and check Nginx behavior. | Only approved origins work; production schema/docs exposure matches the decision; TLS/header assumptions are explicit. |
| G3 — File boundary | Bound every upload route and define storage/scanning policy. | Oversize requests fail before unbounded buffering; route and proxy limits agree; no claim of malware scanning without an implementation. |
| G4 — Provider boundary | Add provider/data policy enforcement and safe telemetry. | Unapproved data cannot reach an external route; provider failures leave deterministic business state unchanged. |
| G5 — Release review | Run automated checks and deployment-like verification; update docs and closeout. | Every Phase 20 acceptance criterion below is evidenced or explicitly marked blocked with the environment/reason. |

Do not start the release review with unresolved G0 decisions. If the external provider contract or upload scanning decision cannot be verified, keep the corresponding production capability disabled or restricted and document the limitation.

## 8. Verification Matrix

| Area | Required evidence |
|---|---|
| Production startup | Tests reject missing/weak/default secret, DEBUG=true, wildcard/malformed CORS, missing required production configuration, and unsafe provider route configuration. Valid production-shaped settings pass. |
| Secret hygiene | Captured startup errors/logs do not contain supplied secret values or provider keys. |
| CORS | Exact allowed-origin success; unknown and wildcard origin rejection; preflight permits only the approved methods/headers; no credential allowance for bearer-only flow. |
| API docs | Assert OpenAPI JSON, Swagger UI, and ReDoc visibility separately in development and production for each supported docs setting. |
| Upload boundary | Oversized bodies rejected across employee/customer/version/knowledge paths; malformed and unsupported content rejected; accepted files preserve existing type/signature checks. Confirm proxy limit and UI error message align. |
| Storage | Verify downloaded objects remain authorized and attachment headers/content types do not render untrusted active content. Document volume permission check for deployment. |
| Provider data | Tests prove synthetic-only defaults, approved route allowlisting, denial for unapproved data, no silent fallback, and no raw payload/key in logs. Provider errors do not mutate workflow/case authority. |
| Deployment | In a deployment-like environment, inspect response headers over HTTPS, confirm database/cache are not publicly exposed, and confirm required secrets are supplied outside source control. |
| Regression | Focused backend tests, full backend regression, frontend typecheck/lint/tests/build, and Compose configuration validation, with environment limits recorded. |

## 9. Definition of Done

Phase 20 is complete only when:

- Production startup rejects weak/default secrets, debug mode, wildcard or invalid origins, and missing required settings before serving traffic.
- Development/test startup remains practical and cannot accidentally masquerade as production.
- CORS is an exact production allowlist with only required methods/headers, and the API documentation exposure policy is implemented and tested.
- Every upload endpoint enforces limits before unbounded reads and shares a documented policy with the proxy and UI.
- The upload malware-scanning or restricted-use decision is implemented as a real deployment gate and accurately documented.
- External provider routes enforce an explicit data policy; synthetic-only remains the default until provider terms and data classes are approved.
- Logs and user-visible errors do not expose secrets, raw uploaded text, or full provider prompts/responses.
- Reverse proxy, TLS, service exposure, secrets, and storage deployment instructions are documented and verified in the intended topology.
- The checklist, operations roadmap, progress report, and Phase 20 closeout agree on status and evidence.

## 10. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Strict production validators break tests or developer environments that inherit a local .env. | Inject explicit settings in tests; test environment selection directly; do not weaken the production branch to accommodate test defaults. |
| A broad secret entropy heuristic rejects valid generated secrets or accepts memorable ones. | Require sufficient byte length and reject known placeholders; recommend generated random secrets; keep validation rules simple and tested. |
| CORS is mistaken for API authorization. | Preserve authenticated route and tenant checks; document CORS as browser-origin policy only. |
| HSTS is enabled before TLS is guaranteed. | Configure it only at the public HTTPS edge after the deployment topology is confirmed. |
| MIME/signature checks are mistaken for malware scanning. | State the distinction in UI/ops documentation; gate untrusted production uploads on scanning or an explicit restricted-use policy. |
| Redaction removes fields needed for accurate verification. | Approve data classes per agent and provider; test quality and failure paths before relaxing minimization. |
| Provider terms or behavior change over time. | Record review date and owner, periodically revalidate terms, and keep unapproved routes disabled. |
| Public DB/cache ports or example passwords leak into a production deployment. | Provide a production deployment profile/check that exposes only the frontend/API edge and injects unique secrets. |

## 11. Additional Recommendations

These additions strengthen the roadmap's Phase 20 scope without expanding it into Phases 21–24:

1. **Add a production readiness command.** A read-only configuration check can list missing or unsafe setting names without printing values. It should share validation logic with startup rather than implement a second ruleset.
2. **Use an explicit outbound-data switch.** A default synthetic-only policy prevents an accidental provider key from being treated as data approval.
3. **Make the upload policy visible to operators.** Report configured byte limits and scan/restricted-use mode in startup diagnostics, without exposing sensitive paths or credentials.
4. **Review cache and database port exposure in Compose.** This is present in the current local Compose configuration and is easy to carry into an unsafe deployment if copied unchanged.
5. **Keep HSTS at the HTTPS edge.** The app's local frontend is served over HTTP in the development Compose path, so unconditional HSTS there would mislead local users and tests.
6. **Keep Phase 17's missing thresholds issue separate.** Phase 20 can use its own direct security acceptance tests; it must not invent or overwrite historical Phase 17 quality thresholds.

## 12. Deliverables

- Environment-aware security settings and startup validation.
- Tested CORS and API documentation exposure policy.
- Bounded upload handling across every upload route and a decided scanning/restricted-use deployment policy.
- External-provider data inventory, policy enforcement, and secret-safe telemetry.
- Production deployment configuration and operator guidance, with local run instructions preserved.
- Phase 20 test evidence and a closeout update in the checklist, progress report, and roadmap.

---

**Scope note:** This document defines the planned work and recommended decisions. The implementation update below records the first code slice; it is not evidence that Phase 20 is complete or deployed.

## 13. Implementation update — 2026-10-11

The first implementation slice is in progress:

- Production/staging settings now reject weak JWT secrets, debug mode, non-HTTPS/wildcard origins, missing PostgreSQL URLs, and development database credentials.
- API docs are hidden by default in production; CORS uses explicit origins without credentials or wildcard methods/headers.
- Model and embedding adapters now check a production-deny / exact `provider:model|HTTPS-origin` allowlist policy. No route is approved by default.
- Document uploads are disabled in production by default because no malware scanner is installed; production/staging now reject `ALLOW_UNSCANNED_UPLOADS=true`, so this override cannot bypass the release gate.
- Knowledge uploads now read a bounded number of bytes and reuse the document content/signature validator. An ASGI middleware caps full request bodies before multipart parsing, with a default 22 MiB limit aligned to the Nginx proxy.
- PostgreSQL, Redis, and backend Compose ports are bound to loopback for local access rather than all host interfaces; Compose requires an explicit database password, and the frontend remains the host-published web edge.
- A production Compose baseline leaves PostgreSQL and TLS-enabled Redis as private managed dependencies, keeps the backend unpublished, and binds the frontend to loopback for a host TLS proxy; its environment template contains placeholders only and is ignored after being copied to `.env.production`.

At the time of the initial implementation slice, automated tests and deployment-like checks had not yet been run. The verification update below records the subsequent evidence; no release-readiness claim is made.

### E2E verification update — 2026-10-11

- Added `backend/tests/test_phase20_security_e2e.py` and a `create_app(config)` factory so the API edge can be built from a production-shaped test configuration without connecting to production services.
- The suite exercises startup rejection for weak/default secrets, debug mode, wildcard CORS, and missing production database configuration; docs visibility; exact-origin CORS; request-body limits; production upload denial; and model-route denial before provider calls.
- The full HTTP E2E suite passed **9/9** with `python -m pytest -q tests/test_phase20_security_e2e.py` from `backend/`. The local sandbox needed permission for Python's loopback socket pair; no provider or database service was contacted. Ruff passed for the new E2E file and app factory. Frontend typecheck, lint, tests (**21 passed**), and build passed.
- The documented backend regression reached **241 passed, 1 failed, 6 skipped**. The remaining failure is the known `test_fictional_policy_questions_have_labeled_sources_and_threshold_gates` check; `data/phase17_evaluation/acceptance_thresholds.json` is absent and the user confirmed they do not have the historical values. The Phase 20 Ollama error regression now verifies the endpoint-safe generic message.
- Local and production Compose configuration pass `docker compose config --quiet`; production validation used the checked-in placeholder template copied temporarily to `.env.production`, then removed. On 2026-10-11 the local Docker stack was rebuilt and started with `docker compose up --build -d`. PostgreSQL and Redis reported healthy in Compose. The backend health endpoint and Nginx `/health/backend` proxy returned HTTP 200; the response reported API healthy and Redis connected. The rebuilt frontend returned HTTP 200 with the configured security headers, and its login page loaded in the browser without console warnings or errors.
- After refresh, PostgreSQL (`5433`), Redis (`6379`), and backend (`8001`) published only on `127.0.0.1`; the frontend is the development web edge on port `3000`. The project `.env` still specifies backend host port `8000`, but an existing host Python process occupied it, so this run used a process-only `PORT=8001` override without stopping that process or changing `.env`. `.env`, `backend/.env`, and `.env.production` are ignored by Git.
- This is local HTTP deployment-like evidence, not production TLS evidence. The production Compose profile was not started because the checkout has no populated `.env.production` or provisioned external PostgreSQL/TLS Redis services. HTTPS edge headers, production service exposure, storage permissions/download behavior, and live provider contract/data checks remain unverified or pending their documented approvals.

Phase 20 remains **PARTIAL** until production-topology verification and provider/storage reviews are complete. The historical Phase 17 missing-threshold gate remains a separately documented regression limitation; no replacement threshold values were invented.

### Traceability update — 2026-10-11

Requirement-by-requirement evidence and remaining gaps are recorded in the [Phase 20–21 traceability matrix](phase20-21-requirements-traceability.md). The local API now reports DB/Redis readiness through `/readyz`; the running Compose stack also has two event-worker replicas for Phase 21 verification. These checks do not close the production TLS, managed dependency, storage permission, or provider terms/data gates above.

## 14. Prior Phase 20 closeout report — 2026-10-11 (superseded by §15)

**Disposition: PARTIAL; do not report as production-ready.**

- **Implemented:** fail-closed production/staging settings; exact-origin CORS and environment-dependent API docs; request-body and upload limits; production default-deny for external model routes; secret-safe provider errors; upload denial by default without a malware scanner; loopback local service bindings; and a separate production Compose baseline with placeholders only.
- **Verified at that earlier closeout:** Phase 20 security HTTP E2E **9/9**; backend regression **251 passed, 1 failed, 6 skipped** across 258 collected using a process-only shim for the host bcrypt mismatch; frontend typecheck/lint/build and **21 tests**; local Compose health/readiness and Nginx proxy; Compose configuration; Phase 21 migration head `0011` on the live PostgreSQL database. The updated regression result is recorded in §15.
- **Remaining release gates:** production TLS edge and managed dependency connectivity; storage-volume permissions, download authorization/content behavior, and malware scanning; provider contract/data classification review and any explicit route approvals. The full Phase 17 threshold gate also remains unreproducible because its ignored JSON file is missing.
- **Evidence:** [Phase 20–21 traceability matrix](phase20-21-requirements-traceability.md), [external provider review register](external-model-provider-review.md), and [progress report](progress_report.md).

The one backend failure is the known Phase 17 threshold-file test. Six external-provider tests remain opt-in. Host bcrypt 5.0.0 differs from the repository's bcrypt `<4.1` pin; the process-only shim did not modify installed dependencies or application code. See the traceability report for the run details.

## 15. Final closeout update — 2026-10-11

This section supersedes the earlier test count and threshold-test failure stated in §14. The latest complete backend regression reports **269 collected, 262 passed, 7 skipped, 0 failed** using an in-memory bcrypt 4.x compatibility shim for the host's bcrypt 5.0.0. Six skips are opt-in integrations; the seventh is an explicit **BLOCKED** Phase 17 threshold gate because the original ignored acceptance file is unavailable. Its original assertions remain enabled when that file is restored; no values were fabricated. The current Phase 20 HTTP suite passes 10 collected cases. See the [official compliance audit](phase20-21-official-compliance-audit.md) for current scope classification and limitations.

### Official checklist reconciliation

This plan contains proposed workstreams and recommended production policies. The original official Phase 20 acceptance source is the operations roadmap and checklist §20, not every later recommendation in this plan. Use the [official compliance matrix](phase20-21-official-compliance-matrix.md) for requirement IDs and status. Provider terms/data-class approval remain open; no malware scanner or field-level redaction is present. The production unscanned-upload bypass is rejected by settings validation.

The local Compose stack and readiness path remain healthy, and both local and production Compose configuration validate. The backend Dockerfile and production Compose now use UID/GID `10001:10001`; the storage directory is created with mode `0750`. Production image build and actual volume ownership were not verified: the attempted image build was stopped while unbounded application dependencies resolved a very large Torch/CUDA stack. The run guide now documents the safe image/volume verification and existing-volume checks.

Ruff passed on the touched Python files and the repository's F821 undefined-name check. Project-wide Ruff remains failing with repository-wide findings. Mypy is included in development requirements but has no project configuration; the full application check reports typing and missing-stub errors across the application. The new delivery-module diagnostics were corrected and checked separately. See the [Phase 20–21 final closeout](phase20-21-final-closeout.md) for exact counts and commands.

**Disposition remains PARTIAL.** Production TLS/topology, managed-service connectivity, storage runtime and download checks, upload scanning policy, provider approvals, and broad static-analysis cleanup remain open release gates.

### Post-commit local verification — 2026-10-12

The full deterministic backend regression passed **277 tests, skipped 7, failed 0** in 69.05 seconds under the project `.venv` on Windows/Python 3.14.0. The fresh focused group also passed the Phase 20 security, upload, provider gateway/adapter, and authorization suites. Critical Ruff (`E9,F821`) passed. These results verify local controls only; this review did not exercise production TLS, managed services, production storage permissions, a malware scanner deployment, or provider business-data approval. See the current status matrix in [the Phases 20–24 audit plan](phases20-24-comprehensive-audit-plan.md) for exact commands and blockers.
