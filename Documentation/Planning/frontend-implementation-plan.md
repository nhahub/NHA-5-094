# VerifiaAI Frontend Implementation Plan

**Audit baseline:** 2026-10-10  
**Plan snapshot:** `main`, clean working tree at `384535f` (`Document local project setup and demo bootstrap`)
**Scope:** Phase 18 operational frontend, with production security and backend gaps kept explicit.

**Baseline note:** This plan preserves its original pre-implementation audit and planning decisions. Statements that the customer case APIs or frontend are absent describe that baseline only. Current implementation and validation evidence are recorded in the [2026-10-10 project audit](project-audit-2026-10-10.md) and the update at the end of this file.

## Executive summary

The repository has a backend-only FastAPI application and an empty `frontend/` scaffold. It has no JavaScript manifest, lockfile, frontend tests, frontend Docker image, or frontend service. The current API is substantial enough for an authenticated internal operations application: login, organization-scoped cases, a consolidated case review bundle, document upload and processing, verification history, review tasks, manager approvals, process listing, agent invocation, and case events are implemented.

The first release is a React single-page application for authenticated internal operators. It provides a real-data dashboard, paginated case list and creation, a case workspace for documents/evidence/verifications/events and bounded agent recommendations, assigned review tasks, and manager approval decisions. Customer case history remains excluded until the backend provides participant-scoped case reads. Public registration is retired; Phase 19 adds ADMIN-controlled provisioning and a local operator bootstrap.

The frontend is a client of the existing API. It will not implement business calculations, infer a successful workflow transition from an AI proposal, or claim backend permission enforcement where the API does not provide it. Production readiness remains conditional on the separately planned identity/provisioning and production security phases.

## Repository and documentation audit

### Repository state

- `frontend/` contains only `.gitkeep` placeholders in `src/customer/` and `src/employee/`.
- No `package.json`, lockfile, TypeScript configuration, frontend source, frontend test, or existing UI system was found.
- Existing tracked frontend intent is React 18, TypeScript, Tailwind, and React Query in `README.md`; the operations guide recommends React + TypeScript and React Query. This plan uses the repository’s intended SPA architecture and selects versions compatible with the host runtime.
- `docker-compose.yml` currently runs PostgreSQL, Redis, and the FastAPI backend. The backend reads the root `.env` in Compose; the local guide runs the backend on the host and keeps the database/Redis in Docker.
- `.env` and `backend/.env` already exist locally and are ignored. Their contents were not printed or changed. `.env.example` and `backend/.env.example` contain backend settings only. No frontend secret or provider key will be added.
- Git status was clean before changes. No existing user changes were present to preserve.
- Docker CLI is installed, but the Docker Desktop Linux engine was not running during the audit. Container startup/build must be retried after the engine is available or recorded as blocked.

### Documentation reviewed

- `README.md`, `Documentation/README.md`, `Documentation/01-product-overview.md`, `Documentation/02-architecture.md`, `Documentation/03-database-schema.md`, `Documentation/04-operations-and-roadmap.md`, `Documentation/RUNNING_THE_PROJECT.md`
- `Documentation/Verifia_Detailed_Implementation_Checklist.md`, `Documentation/progress_report.md`, `Documentation/09-phase9-implementation-plan.md`, `Documentation/next-milestone-phase12-workflow-agent-plan.md`, and `Documentation/phase13-supervisor-agent-implementation-plan.md`
- There is no separate Phase 13 implementation report; the Phase 13 plan contains its implementation closeout and verification record.
- Relevant source reviewed includes API router aggregation, auth/case/document/task/approval/verification/workflow/process/agent/event/audit routers and their request/response schemas, case review bundle construction, document upload validation/status enums, agent execution schemas/service, Docker Compose, backend configuration, and the existing test inventory.

### Product and security constraints taken from the documentation

- Case state, deterministic verification, configured workflow policy, and human decisions are authoritative. AI contributes bounded proposals and summaries.
- Documents are untrusted data, not instructions. The UI renders backend text as text and does not render arbitrary HTML.
- Tenant isolation belongs to the backend. Client-side role checks only improve navigation and do not authorize an operation.
- The documented Phase 18 checklist covers login, cases, uploads, employee review, manager approval, actual case state, and clear loading/empty/error behavior.
- The operations guide and checklist identify public self-registration, weak development defaults, wildcard CORS, and incomplete route-by-route authorization as later security work. This frontend does not erase those limitations.
- Backend documentation reports the latest regression as 209 passed, 6 opt-in provider checks skipped, 0 failures; that is a recorded baseline, not a frontend verification result.

## Capability matrix

Status values follow the requested classification vocabulary. “Test available” refers to the repository’s current backend tests before frontend implementation.

| Capability | Documented | Backend implemented | API available | Frontend required | Test available | Classification and notes |
|---|---|---|---|---|---|---|
| Bearer login and current identity | Yes | Yes | `POST /api/v1/auth/login`, `GET /api/v1/auth/me` | Yes | `backend/tests/test_auth_service.py` | `DOCUMENTED_AND_IMPLEMENTED`; access JWT, no refresh/revoke/logout endpoint |
| Account provisioning / registration | Controlled provisioning is required by checklist | Public `POST /auth/register` retired; authenticated organization ADMIN `GET/POST /auth/users` | Yes; backend derives organization/active state and excludes ADMIN | ADMIN-only User access directory/form | `test_auth_provisioning.py` | `IMPLEMENTED`; first ADMIN remains a development-only operator bootstrap; see Phase 19 review |
| Organization switching | Organization identity is documented | User belongs to one organization; no switch flow | No switch endpoint | No | None | `API_MISSING`; client query cache will be scoped to authenticated user/org |
| Case list, create, detail, state | Yes | Yes; case list is organization-scoped, detail/state check tenant | `GET/POST /cases`, `GET /cases/{id}`, `/state`, `/review`, `/events` | Yes for internal operators | `test_domain_api.py`, `test_case_orchestrator.py`, `test_human_review.py` | `DOCUMENTED_AND_IMPLEMENTED`; list lacks participant filter, text search, sort, and total count |
| Customer-specific case list/details | Yes in Phase 18 checklist | No participant-scoped list/detail policy; current list is organization-wide | Existing API is too broad for customer presentation | No until backend scope exists | No customer cross-case privacy test | `BLOCKED`; do not show customer users other tenant-member cases |
| Case review packet | Yes | Yes; case-scoped aggregate includes documents, fields, processing runs, tasks/comments, approvals, verification results, evidence, discrepancies, and bounded recommendations | `GET /cases/{id}/review` (internal roles; CUSTOMER receives 403) | Yes | `test_human_review.py` | `DOCUMENTED_AND_IMPLEMENTED`; output uses flexible JSON dictionaries, so UI parsing must tolerate optional fields |
| Document upload/list/download/process | Yes | Yes; content validation, tenant-scoped storage, versions, processing runs | `POST /documents` multipart, `GET /documents/case/{case_id}`, `GET /documents/{id}`, version content, version `/process` | Yes in case workspace | `test_document_upload.py`, `test_document_processing.py`, `test_document_parsing.py` | `DOCUMENTED_AND_IMPLEMENTED`; 20 MiB max by default; supported formats are PDF, PNG/JPEG, XLS/XLSX, CSV, DOCX, TXT |
| Extracted fields and evidence | Yes | Yes; extracted fields retain provenance and evidence is returned in review bundle | In bundle and verification detail; authenticated field API also exists | Yes, with provenance and confidence | `test_document_processing.py`, `test_rules_and_verifications.py` | `DOCUMENTED_AND_IMPLEMENTED`; extracted values are not independently authoritative |
| Verification history/results | Yes | Yes; deterministic execution, results, rule/calculation runs, evidence | `GET /cases/{id}/review` bundle includes verification history; separate verification reads also exist | Yes for viewing; no standalone verification execution action | `test_rules_and_verifications.py`, `test_verification_agent.py` | `DOCUMENTED_AND_IMPLEMENTED`; the UI reads history from the tenant-checked case bundle and preserves `PASS`, `FAIL`, `REVIEW`, `NOT_APPLICABLE`, and `INCONCLUSIVE` |
| Workflow state and transition | Yes | Workflow engine and transition API exist; routes read/write configuration as well as execution | `GET /cases/{id}/state`, `POST /workflows/validate`, `/transition` | Show current authoritative state; defer manual transition editor | `test_workflow_engine.py`, `test_workflow_router_authority.py` | `DOCUMENTED_AND_IMPLEMENTED`; configuration/read routes need a route-level tenant audit before an administration UI |
| Assigned tasks, comments, resolution | Yes | Yes; internal-user guards, actor/tenant checks, evidence-linked comments and resolutions | `GET /tasks/my`, `/case/{id}`, `POST /{id}/comments`, `/resolve`, `/start`, `/assign` | Yes | `test_human_review.py`, `test_domain_api.py` | `DOCUMENTED_AND_IMPLEMENTED`; resolve payload requires outcome, comment, and evidence IDs |
| Manager approvals | Yes | Yes; pending list and decisions enforce MANAGER/ADMIN | `GET /approvals/pending`, `/case/{id}`, `POST /{id}/decide` | Yes | `test_human_review.py` | `DOCUMENTED_AND_IMPLEMENTED`; decisions require a nonblank comment and backend response is authoritative |
| Agent invocation and case recommendations | Yes | Yes; four agent types, Supervisor parent-child IDs; review bundle exposes a limited safe recommendation projection | `POST /agents/run`; prior bounded recommendations in case review bundle | Yes with an explicit confirmation and advisory label | `test_supervisor_agent.py`, `test_document_agent.py`, `test_workflow_agent.py` | `DOCUMENTED_AND_IMPLEMENTED`; no global execution-history endpoint; never display raw execution context or hidden reasoning |
| Case event history | Yes | Yes | `GET /cases/{id}/events` | Yes | `test_domain_api.py`, `test_case_orchestrator.py` | `DOCUMENTED_AND_IMPLEMENTED`; event payload is not needed for a readable timeline |
| Organization audit log | Yes | Read API is present and tenant-filtered | `GET /audit` | Deferred from first release | `test_domain_api.py` | `DOCUMENTED_AND_IMPLEMENTED`; route has no role/permission gate, so do not surface sensitive audit detail until reviewed |
| Notifications/read state | Yes in data model and product docs | Notification table exists; no notification router | No | No | No API test | `API_MISSING`; later backend requirement |
| Knowledge sources and search | Yes | Yes; organization-scoped API | `/knowledge/sources`, document ingest, `/knowledge/search` | Later | `test_knowledge_router.py`, `test_knowledge_security.py` | `DOCUMENTED_AND_IMPLEMENTED`; separate feature, external embedding provider may receive query/document text |
| User/role/permission administration | Yes in architecture | User listing/provisioning is available to same-organization ADMIN; broader permission-catalog management is absent | `GET/POST /auth/users`; no role/permission catalog API | ADMIN-only user access directory and creation form | `test_auth_provisioning.py`, `App.test.tsx` | `PARTIALLY_IMPLEMENTED`; account provisioning works, role/permission policy administration remains planned |
| Integration/model administration | Yes in data model/roadmap | Models and adapters exist; no user-facing configuration API | No | No | Adapter/config tests only | `API_MISSING`; never expose provider credentials in browser configuration |
| Dashboard aggregates/global search | Product asks for operational overview | No aggregate/search endpoint | Existing list/queue APIs can supply a bounded snapshot | Yes, with exact labels about scope | Service/API tests, no frontend tests yet | `API_MISSING` for aggregates/search; dashboard uses a small, bounded set of real API reads and does not imply full totals |

## API integration matrix

All paths below are under `/api/v1` and use the backend’s OAuth2 bearer token unless noted. The frontend sends only fields defined by current Pydantic request schemas.

| Frontend flow | Backend endpoint and method | Request / response contract | Auth and error behavior | Planned integration test |
|---|---|---|---|---|
| Login and restore session | `POST /auth/login`; `GET /auth/me` | `{email,password}` → `{access_token,token_type,expires_in}`; `/me` → user with `id,organization_id,full_name,role,is_active` | Login 401; `/me` 401 clears local session | Login success/failure, bearer header, expired-token path |
| Organization user access | `GET /auth/users?skip=&limit=`; `POST /auth/users` | Lists scoped users; creates `{email,full_name,password,role}` with role CUSTOMER/EMPLOYEE/MANAGER | Requires live ADMIN; server derives organization and activation; rejects extras; creation is audited | Backend tenant/role/field/audit tests and frontend admin-route/directory tests |
| Cases list | `GET /cases?status=&skip=&limit=` | `CaseRead[]`; limit 1–100; skip offset | Tenant-scoped; 401/403/5xx handled as errors, not empty data | Filter and pagination query behavior, API error state |
| Create case | `GET /processes?skip=&limit=` and `GET /processes/{id}/versions`; `POST /cases` | `{title,case_metadata,process_version_id}` → `CaseRead` | Authenticated; backend 400 validation shown | Correct request body and successful navigation |
| Case workspace | `GET /cases/{id}/review`, `/state`, `/events?skip=&limit=` | Review bundle is `case`, `review_tasks`, `approvals`, `documents`, `verifications`, `evidence`, `discrepancies`, `recommendations`; state includes current stage and counts | Review denies CUSTOMER (403), cross-tenant case 404 | Render authoritative fields/status and safe error/retry states |
| Document upload | `POST /documents` multipart `case_id`, `document_type`, `file` | `DocumentUploadResult {document,duplicate}` | 400/413/415 validation, 404 case, 503 storage failure | Multipart field names, duplicate response, failure feedback |
| Process document | `POST /documents/{document_id}/versions/{version_id}/process` | No body → processing run with status, review reasons and safe error | 404/503; do not present failure as completion | Correct route, status rendering, API failure |
| Download document version | `GET /documents/{document_id}/versions/{version_id}/content` | Binary response | Auth bearer; private/no-store; download as Blob, never render arbitrary file inline | Auth header and filename/download action |
| Verification history | `GET /cases/{case_id}/review` | `CaseReviewBundle.verifications[]`, nested result summaries; evidence is in the same bundle | Case review performs the case organization check and denies CUSTOMER | Status distinction, result/evidence rendering |
| Assigned tasks | `GET /tasks/my` | `TaskRead[]`; resolution `{outcome:"COMPLETED"|"REJECTED",comment,evidence_ids}` | Internal reviewer; 403 customer, 404 not found, 409 invalid state | Resolution payload, duplicate-submit prevention, error state |
| Task comments | `GET/POST /tasks/{task_id}/comments` | Create `{comment,evidence_ids}` | Tenant/actor/permission checks; 403/404/409 | Comment and evidence references |
| Approvals | `GET /approvals/pending`; `POST /approvals/{id}/decide` | `{decision:"APPROVED"|"REJECTED",comment}` → `ApprovalRead` | MANAGER/ADMIN only; 403/404/409 | Correct decision/comment and cache invalidation |
| Supervisor request | `POST /agents/run` | `{case_id,agent_type:"SUPERVISOR",user_prompt?}` → success, summary, proposals, result data, execution id | Uses configured external model/provider and controlled backend agent paths; errors remain visible | Confirmation, payload, advisory/authoritative distinction, provider failure |

The case review route already bundles the primary case workspace data. The UI will prefer that bounded aggregate over issuing a request for each nested object. It may fetch the authenticated case state and event list separately because they have their own explicit read contracts. Every mutation invalidates affected React Query keys.

## Frontend architecture

- **Framework/build:** React + TypeScript + Vite SPA. No SSR is justified: the app is authenticated, backend-driven, and has no public SEO requirement.
- **Routing:** declarative client routes for Overview, Cases, Case workspace, My tasks, Approvals, and Sign in. Unimplemented capabilities will not get dead navigation items.
- **Server state:** TanStack Query with short freshness for operational data, no automatic retries for authorization/validation errors, and explicit invalidation after mutations.
- **API boundary:** one typed fetch client under `src/api`; central base URL; bearer token added there; JSON and multipart bodies handled in one place; consistent API error type and 401 event.
- **Domain contracts:** TypeScript interfaces mirror the request/response schemas for the features implemented. Flexible case review JSON is typed for observed fields and parsed defensively because the backend currently exposes dictionary fields.
- **Authentication:** store the access token in per-tab `sessionStorage`; validate it with `/auth/me` on app load; clear query cache on logout, session expiry, or a different user/org. There is no API logout/revocation/refresh contract. No public registration page.
- **Tenant context:** organization ID is derived from authenticated `/me`, never accepted from a user-supplied selector or sent as an authority claim. Query keys include the authenticated user/org identity. The app does not claim client checks enforce tenant isolation.
- **UI composition:** app shell, page headers, status badges, buttons/inputs, empty/error/loading states, accessible confirmation dialog, case table, document list, verification result panels, timeline, task-resolution form, approval decision form, and bounded agent result display.
- **Styling:** local CSS tokens and component classes; no remote font or asset dependency. Responsive sidebar and compact mobile navigation; tables retain a clear horizontal-scroll fallback on narrow screens.
- **Error handling:** distinguish 401 expired session, 403 forbidden, 404 unavailable record, validation/409 conflicts, 413 upload size, 415 type mismatch, 503 backend/storage/provider errors, and network/backend unavailable. Error text is rendered as text, never HTML.

## UI/UX system baseline

- **Identity:** “VerifiaAI” is presented as a calm evidence-and-workflow operations product, not a conversational bot.
- **Visual direction:** warm near-white workspace, deep ink navigation, teal action color, restrained amber/red/green statuses, dense but breathable tables, minimal shadows, and no ornamental charts or fake metrics.
- **Type:** system sans stack (Inter when installed locally, then Segoe UI/system UI); compact operational heading scale; tabular numerals for counts and IDs.
- **Spacing:** 4 px base rhythm; consistent page gutters; fixed desktop rail with a responsive drawer at tablet/mobile widths.
- **Surface conventions:** small radius for controls and panels, larger radius reserved for main workspace panels; borders and subtle elevation instead of gradients/glass effects.
- **Status semantics:** preserve backend values and visually distinguish `FAIL`, `ERROR`, `INCONCLUSIVE`, `REVIEW`, and success values. Unknown values remain visible with neutral styling.
- **Motion:** short transitions for focus, menu, and feedback; respect `prefers-reduced-motion`.
- **Accessibility:** semantic landmarks and headings, visible focus, labelled controls, announced mutation outcomes, keyboard-operable navigation/dialogs, contrast checks, status text in addition to color, touch-friendly actions, and reduced-motion support. Target WCAG 2.2 AA for shipped flows.

## Repository-specific roadmap

Each phase includes its backend dependency, UI deliverables, state, security, accessibility, automated/manual verification, acceptance/definition of done, risks, complexity, and documentation work. Status is updated as implementation evidence is collected.

### F0 — Repository audit and frontend architecture — COMPLETE

- **Objective / value:** Establish the existing product/API boundary so the frontend follows implemented backend behavior.
- **Dependencies / backend:** None; inspect Phase 17 closeout, real routers, schemas, and security checks.
- **UI/API/state deliverables:** Capability matrix, actual endpoint matrix, route and feature boundaries, no UI yet, no frontend state.
- **Security / accessibility:** Identify unsafe public registration, customer case-scope gap, and endpoints without role gates; establish that client permissions are never authority. Define accessibility as a release requirement.
- **Automated/manual verification:** Repository status/history and file inventory; router/schema source review; confirm no frontend exists and no separate Phase 13 report exists.
- **Acceptance / DoD:** Plan maps implemented features to real paths and records missing APIs and auth limitations. **Evidence:** this audit and matrix.
- **Risks / complexity:** Historical plans include illustrative endpoints that do not match current routes. **LOW.**
- **Docs:** This plan; progress report records the audit baseline.

### F1 — Product structure and design system — IMPLEMENTED

- **Objective / value:** Establish a recognizable, accessible operations UI before building multiple flows.
- **Dependencies / backend:** F0; no endpoint dependency.
- **UI deliverables:** Token stylesheet, logo/wordmark treatment, app navigation, page header, buttons, form controls, badges/status indicators, skeleton/empty/error feedback, confirmation dialog, responsive layout rules.
- **State / API:** Local UI state only; no backend calls.
- **Security / accessibility:** No provider keys or sensitive data in design tokens; semantic navigation and forms, contrast/focus/reduced-motion/dialog keyboard behavior.
- **Automated/manual verification:** Component state tests and accessibility-focused assertions; inspect desktop, tablet, mobile, keyboard-only, and reduced-motion layouts.
- **Acceptance / DoD:** Shared components cover every first-release page state and have no placeholder actions.
- **Risks / complexity:** Keep custom components small; avoid introducing an inaccessible widget library. **MEDIUM.**
- **Docs:** Design-system reference, implementation plan, README screenshot/demo notes if available.

### F2 — React foundation and application shell — IMPLEMENTED

- **Objective / value:** Provide a maintainable runtime and coherent navigation.
- **Dependencies / backend:** F1; FastAPI `/health` is useful for connectivity messaging, not a business metric.
- **UI deliverables:** Vite/React/TypeScript strict setup, routes, shell, responsive navigation, not-found route, query provider, config boundary, lint/build/test scripts.
- **State / API:** Query client and API client; no domain state duplicated in components.
- **Security / accessibility:** Relative production API path; browser-visible `VITE_*` values contain no secrets; route links are keyboard accessible; no unsafe redirects.
- **Automated/manual verification:** Typecheck, lint, component route test, production build; verify direct refresh on nested routes.
- **Acceptance / DoD:** App shell and nested routes load in development and production static server with fallback.
- **Risks / complexity:** SPA route fallback and API routing must agree across Vite and Nginx. **MEDIUM.**
- **Docs:** Frontend setup, scripts, environment variable table, architecture diagram.

### F3 — Authentication and organization context — IMPLEMENTED

- **Objective / value:** Let existing provisioned users sign in and keep client data separated by identity.
- **Dependencies / backend:** F2; `POST /auth/login`, `GET /auth/me`.
- **UI deliverables:** Sign-in screen, session restoration, local sign-out, protected routes, user/role identity in shell, expired-session feedback.
- **State / API:** Token in `sessionStorage`; user loaded from `/me`; cache keys scoped by user/org and cache cleared on identity changes.
- **Security / accessibility:** No registration page; no localStorage token; no organization ID supplied as trusted authority; backend remains permission boundary; password field labels and accessible errors.
- **Automated/manual verification:** Login success/failure, `/me` restore, missing/expired token, 401 clearing, logout cache cleanup, keyboard form use.
- **Acceptance / DoD:** Protected routes require a current `/me`; any authorization error is shown safely; no role-gated action is represented as backend security.
- **Risks / complexity:** No refresh/revoke/logout API; tab closure ends the client session while JWT can remain valid until expiry. Account provisioning remains a backend blocker. **HIGH.**
- **Docs:** Authentication behavior and security limitations in README and security review.

### F4 — Operational dashboard and case intake — IMPLEMENTED

- **Objective / value:** Give operators a real queue snapshot and fast access to active cases.
- **Dependencies / backend:** F3; cases list and processes/version reads.
- **UI deliverables:** Overview page, recent cases, real assigned-task/pending-approval counts, case table, status filter, bounded local search, pagination, create-case flow.
- **State / API:** Bounded requests only; cases use `skip`, `limit`, and optional `status`; process list/version selector; invalidation after case creation. Dashboard labels the returned window rather than implying a global total.
- **Security / accessibility:** Do not show customer case listings until participant scope exists; internal role checks are UX only; form validation and clear status labels.
- **Automated/manual verification:** Query parameter, pagination, status filter, create request body, validation, empty/error states, role-specific navigation.
- **Acceptance / DoD:** Operators can create a case bound to an available version and open it from a real API response; no fake metrics or search claims.
- **Risks / complexity:** Backend has no full-text search/count aggregate and caps cases at 100 per request. **HIGH.**
- **Docs:** Dashboard data definitions, case create contract, known pagination/search limits.

### F5 — Case workspace, documents, evidence, verification, and history — IMPLEMENTED

- **Objective / value:** Make the case the central operational view and preserve authoritative evidence/status.
- **Dependencies / backend:** F4; case review bundle/state/events, document, verification, and binary download APIs.
- **UI deliverables:** Case summary, current backend status/stage, document upload/list/download/process status, extracted fields/confidence/source references, evidence panels, verification history, discrepancies, event timeline, processing/review states.
- **State / API:** Prefer one review-bundle read; state/events and document actions use their explicit APIs. Upload multipart fields exactly as declared. Mutations invalidate case bundle/document/state queries.
- **Security / accessibility:** Enforce 20 MiB client usability limit while backend remains final validator; allow only backend-supported extensions; download through authenticated Blob path; never inline-render untrusted files or HTML; preserve `INCONCLUSIVE`/`ERROR`/`FAIL`.
- **Automated/manual verification:** Correct multipart body and binary headers, file validation messages, status distinction, extracted evidence labels, error/permission/not-found paths, responsive case workspace.
- **Acceptance / DoD:** Every displayed result comes from API data; failures are not shown as success; recommendations are visually separate from deterministic outcomes.
- **Risks / complexity:** Review bundle uses flexible dictionaries, and processing may depend on external model/OCR/storage configuration. **VERY HIGH.**
- **Docs:** Case review bundle field map, upload types/limits, processing statuses, download handling.

### F6 — Employee tasks and manager approvals — IMPLEMENTED

- **Objective / value:** Complete the human-review loop with auditable, evidence-linked decisions.
- **Dependencies / backend:** F5; task list/comments/resolve and pending/decide approvals.
- **UI deliverables:** My Tasks queue, task details/comments, resolution form with `COMPLETED` or `REJECTED` and required comment, approvals queue, approve/reject confirmation and required comment.
- **State / API:** Server state from `/tasks/my` and `/approvals/pending`; mutations prevent duplicate submissions and invalidate task/case/approval queries.
- **Security / accessibility:** Customer excluded from internal queues; approval actions shown only to MANAGER/ADMIN for usability; always rely on API 403/409; evidence IDs constrained to case-visible records.
- **Automated/manual verification:** Exact request payloads, error handling for 403/404/409, disabled pending buttons, successful authoritative response and refreshed state, keyboard dialog/form use.
- **Acceptance / DoD:** Employees can resolve permitted tasks with a reason; managers can record approval/rejection with a comment; backend response determines final UI status.
- **Risks / complexity:** Assignment policy and dynamic permissions are not exposed as a permission API. **HIGH.**
- **Docs:** Task and approval interaction/API guide; current authorization boundary.

### F7 — Agent recommendations and audit-safe execution feedback — IMPLEMENTED

- **Objective / value:** Make the AI layer legible without presenting it as the business authority.
- **Dependencies / backend:** F5; bounded recommendations in review bundle and `POST /agents/run`.
- **UI deliverables:** Prior recommendation list, explicit Supervisor run confirmation, summary/proposal cards, execution ID and status; clear “AI recommendation” and backend-confirmed status distinction.
- **State / API:** Mutation is explicit and user-triggered; display only public response fields and limited recommendation projections; refetch case review after run.
- **Security / accessibility:** Warn that case/document context can be sent to configured external providers and backend-authorized tools can run; never display raw execution input context, hidden reasoning, provider keys, or arbitrary HTML; failure is not success.
- **Automated/manual verification:** Confirmation gating, request body, proposal/result separation, no auto-transition, no sensitive fields rendered, provider/backend failure state.
- **Acceptance / DoD:** Agent results remain advisory in the UI unless the backend returns a persisted deterministic/human outcome. No fabricated trace relationships.
- **Risks / complexity:** Synchronous provider latency and rate limits; current history projection is case-scoped and capped at 20, not a global trace API. **HIGH.**
- **Docs:** Agent UI data policy, exposed response fields, trace-history limitations.

### F8 — Frontend hardening, accessibility, quality gates, Docker, and closeout — IMPLEMENTED; CONTAINER RUNTIME NOT VERIFIED

- **Objective / value:** Make the implemented Phase 18 slice repeatable to install, test, and demonstrate.
- **Dependencies / backend:** F1–F7; existing Compose services and backend API.
- **UI/deployment deliverables:** Strict type/lint/build gates, meaningful unit/component tests, security/accessibility review, production frontend image, Nginx SPA fallback and `/api/v1` proxy, Compose frontend service, local development guide.
- **State / API:** Production defaults to same-origin `/api/v1`; dev proxy targets host backend; no frontend API secrets or provider credentials.
- **Security / accessibility:** Check session cache clearing, response text escaping, redirects, file handling, 401/403/413/415/503 states, reduced motion, keyboard paths, contrast, touch targets.
- **Automated/manual verification:** Frontend static checks, component/API-client tests, production build, Compose config, Docker build/start where daemon is available, nested route refresh, API reachability, manual desktop/tablet/mobile checks.
- **Acceptance / DoD:** All implemented acceptance tests pass, docs accurately distinguish verified from blocked, and no dead buttons/fake values remain.
- **Risks / complexity:** A local Docker health/proxy run does not prove authenticated business workflows, provider behavior, migrations, or production TLS. Frontend checks cannot prove backend authorization. **VERY HIGH.**
- **Docs:** README, `RUNNING_THE_PROJECT.md`, design-system guide, test matrix/results, progress report, Phase 18 checklist.

### F9 — Deferred backend capabilities (not part of frontend acceptance)

- **Objective / value:** Keep the next roadmap review actionable without faking unavailable features.
- **Dependencies / backend:** Production security Phase 20, repeatable quality Phase 22, and later product work. Phase 19 identity and provisioning are implemented.
- **Deliverables:** No current UI; candidate future areas are participant-scoped customer cases, safe user provisioning, permission catalog, organization switching, notifications, global search/aggregates, user/role administration, integration/model configuration, and global agent trace browsing.
- **State / API:** Requires new documented APIs and backend authorization tests before pages or client hooks are added.
- **Security / accessibility:** Tenant/resource scope and permission contract must exist before adding navigation; future controls must meet the same accessibility baseline.
- **Automated/manual verification:** Backend contract, tenant-isolation, privilege-escalation, and API failure tests precede frontend page tests.
- **Acceptance / DoD:** A deferred feature moves into scope only when the backend endpoint/schema, permissions, and test evidence exist.
- **Risks / complexity:** Account provisioning and customer case scope are high risk; notifications/admin/search are product decisions. **MEDIUM to VERY HIGH.**
- **Docs:** Keep these as backend dependencies and future capabilities, not operational frontend claims.

## Frontend verification matrix

| Requirement | Documentation reference | Existing test | New verification | Command / status |
|---|---|---|---|---|
| Case, upload, employee review, manager approval, actual state | `Verifia_Detailed_Implementation_Checklist.md` §18 | Backend `test_domain_api.py`, `test_document_upload.py`, `test_human_review.py` | Case list/pagination and approval decision UI tests; API multipart contract test | `npm run test`: 6 files, 13 tests passed; no live backend E2E |
| Auth, tenant context, role-aware UX | Checklist §19; Operations §29; `RUNNING_THE_PROJECT.md` local demo | Backend `test_auth_service.py`, `test_knowledge_security.py`, `test_human_review.py` | Session restore/login/logout/cache tests; role-route gate; API bearer/401 tests | `npm run test`: passed; backend cross-tenant gaps remain |
| Useful loading/empty/error/pending states | Checklist §18 DoD; pasted frontend request §21 | No prior frontend tests | Shared status/empty/error states and query-driven page coverage | Component tests pass; full browser/backend error matrix remains manual |
| Static checks and production output | README; checklist §22 CI | No prior frontend checks | Strict typecheck, lint, production build | `npm run typecheck`, `npm run lint`, `npm run build`: all pass |
| API client and mutation contracts | Pydantic router/schema definitions; progress report Phase 16 | Backend route tests | Bearer, JSON/multipart, 401, upload field names, approval request/comment | `npm run test`: passed |
| Accessibility and responsive use | Pasted frontend request §§22–23 | No frontend tests | Semantic labels, dialog keyboard handling, 390 px login viewport review | Login rendered in desktop/mobile preview; full browser review and axe scan remain open |
| Backend integration | Checklist §22; progress report Phase 17 real API walkthrough | Existing backend integration/evaluation tests | Run frontend against authenticated backend if database/services are available | Local Compose services are healthy and frontend Nginx `/health/backend` returns HTTP 200; authenticated business workflows and migrations remain unverified |
| Docker/deployment | `docker-compose.yml`, `RUNNING_THE_PROJECT.md`, pasted request §§29–30 | No prior frontend Docker checks | Compose config, frontend Docker build/start, route/API smoke | Compose config passes; rebuilt images and local containers start; frontend returns security headers; DB/cache/backend bind to loopback. Production TLS and public-edge checks remain open |

Frontend checks are additional to, not replacements for, the documented backend regression (`python scripts/run_backend_regression_windows.py` from `backend/`) and opt-in provider checks. The frontend was installed from its lockfile with `npm ci`; the verified run passed typecheck, lint, build, and 21 tests across 10 files. The Phase 19 focused backend set passed 22 tests. The latest documented full backend regression collected 260 tests: 253 passed, 0 failed, and 7 skipped. Six are opt-in checks; one explicitly blocks Phase 17 acceptance because ignored fixture `data/phase17_evaluation/acceptance_thresholds.json` is missing. The host run used a process-only shim for bcrypt 5 behavior to match the project pin `<4.1`. The Phase 20 HTTP security E2E suite passed 9/9. See the [final Phase 20–21 closeout](phase20-21-final-closeout.md) for the final environment and static-analysis results.

## Roadmap validation and scope decisions

1. The app uses the existing login/me API and provides no public self-registration. Organization ADMIN users can provision non-ADMIN accounts through the Phase 19 scoped API.
2. Internal case operations use the existing organization-scoped case and review routes. Customer role case listing is deferred because the backend lacks participant-scoped reads.
3. Dashboard indicators are derived from bounded real responses, labelled by their exact scope; no charts or global totals are invented.
4. Document/status/evidence/verifications and human review use current contracts. The UI preserves unknown/new enum values rather than relabelling them as success.
5. Workflow editing, permission catalog management, notification preferences, integrations, model configuration, global agent history, and unrestricted audit browsing are omitted until APIs and authorization contracts support them. Basic account provisioning is implemented in Phase 19.
6. The selected Docker model is static frontend serving with Nginx and a same-origin API proxy to the Compose backend. Development uses Vite proxying to the documented host API.
7. A real backend E2E run requires a running PostgreSQL/Redis/API, migrated schema, provisioned local user/process, local object storage, and provider/OCR configuration for provider-backed paths. If those prerequisites or Docker remain unavailable, the limitation will be documented instead of labelled PASS.

## Final acceptance boundary

Phase 18 frontend acceptance covers only the verified internal operator flows above. It does not complete the entire VerifiaAI product roadmap or assert production readiness. A final verdict may be PASS only for the scoped implementation when its checks run successfully; environment-blocked Docker/backend integration yields PASS WITH ISSUES or FAIL according to the observed impact.

## Current implementation update — 2026-10-10

The initial plan's blocked customer-case item has since been implemented with participant-scoped API contracts and customer pages. Customers can create a case from published active process options, see only their linked cases, and upload requested or additional documents to an open linked case. Internal document handling now previews authenticated PDF/image blobs in a sandboxed PDF frame or image element; arbitrary uploaded HTML is not rendered.

Phase 19 identity work now also includes per-user token-version revocation for logout and password changes, password change/admin reset endpoints, safe audit events, role checks on protected domain routes, and the development-only hidden first-admin password prompt. The migration chain is at `0010_user_token_version`.

At the time of the earlier frontend closeout, checks included 21 frontend tests, typecheck, lint, and production build; its backend total and environment notes are historical. Current backend and Docker evidence is recorded in the [Phase 20–21 final closeout](phase20-21-final-closeout.md). The authenticated browser-to-API flow remains unverified even though an isolated backend API Case lifecycle test now passes.
