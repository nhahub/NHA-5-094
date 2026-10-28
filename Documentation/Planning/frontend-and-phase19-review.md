# Frontend and Phase 19 Security Review

**Review date:** 2026-10-10  
**Scope:** Existing React application and the roadmap's next security phase, Phase 19 — Identity and provisioning.

**Status note:** The initial assessment and implementation plan below preserve the pre-fix findings. The dated audit update at the end records which findings have since been resolved and supersedes their old “current” status statements.

## Initial assessment

### Architecture and supported surface

- The browser app is a React 19 and TypeScript SPA using Vite, React Router, TanStack Query, and Lucide icons. It calls the FastAPI `/api/v1` service through one bearer-token API client.
- Existing routes cover sign-in, operations overview, case register, case workspace (documents, verification, evidence, activity, and review), employee tasks, manager approvals, customer access boundary, and not-found/session states.
- The frontend deliberately does not claim support for administration, customer case lists, notifications, knowledge search, integration management, or agent traces because those workflows are not part of its current route/API surface.
- The Docker setup serves the SPA with Nginx and proxies API requests to the Compose backend. The local Vite server proxies to `127.0.0.1:8000`.

### Initial UI/UX findings

- The existing teal/navy palette and reusable page, panel, form, table, and state classes provide a workable starting point, but most CSS rules are compressed into long lines and use many one-off literal colors and spacing values.
- Several labels and secondary text use very small sizes; dense panels and card borders compete for attention. The sidebar and login hero rely on generic iconography and decorative gradients rather than a reusable Verifia mark.
- There is no branded favicon or referenced logo asset. The top bar uses a fixed business-operations label, while the workspace card presents a generic label because the current identity response has no organization display name.
- Existing routes have useful loading, empty, error, and success states. Dialog keyboard focus and the off-canvas mobile navigation need a full keyboard/focus pass.

### Initial security findings

| ID | Severity | Evidence and impact | Initial disposition |
|---|---|---|---|
| F-01 | Critical | `POST /auth/register` is unauthenticated and accepts `organization_id`, `role`, and `is_active`, allowing self-selected tenant membership, ADMIN assignment, and active accounts. | Remove public registration; add tenant-scoped ADMIN provisioning with a constrained request schema. |
| F-02 | High | The `users` table only enforces `(organization_id, email)` uniqueness, but login searches by email across all tenants and returns the first match. Duplicate addresses can make authentication ambiguous. | Enforce case-insensitive global email uniqueness in a new migration; fail closed when legacy duplicates are present. |
| F-03 | High | An untracked local demo script contains a fixed admin password, resets an existing account's password, and prints the password. | Preserve the script but make bootstrap interactive, development-only, non-resetting, and secret-silent. |
| F-04 | Medium | JWTs are stored in `sessionStorage`; this matches the current bearer-token API but remains exposed to same-origin script execution. The API has no refresh/revoke or HttpOnly cookie flow. | Keep the compatible session model, strengthen output policy, and document the remaining backend/session limitation. |
| F-05 | Medium | `get_current_user` validates user existence and `is_active` but does not validate the token subject format, compare signed organization/role claims to current identity, or check organization active state. | Fail closed for malformed/stale claims and inactive organizations; add negative tests. |
| F-06 | Medium | The frontend uses React text rendering and has no `dangerouslySetInnerHTML`, `innerHTML`, or `document.write` usage. It does not inline document/LLM content as HTML. | Preserve text-only rendering; keep document downloads authenticated and blob-backed. |
| F-07 | Medium | Production Nginx already sets CSP, nosniff, frame, referrer, and permissions headers. Production Docker/CSP runtime still needs an executable container check. | Retain and document the configured headers; container validation is environment-dependent. |
| F-08 | Medium | A configurable API origin can carry bearer tokens and document data, so cleartext HTTP to a non-local API would expose authenticated traffic. | Require HTTPS for public production app/API origins; allow HTTP only for loopback development and add URL-policy tests. |

### API integration, test baseline, and documented constraints

- The frontend's request client sends bearer tokens, omits ambient cookies, clears session state on 401, and scopes query keys by organization and user. Login restores identity from `/auth/me`; backend remains the authorization boundary.
- The case workspace uses the tenant-scoped review bundle instead of the direct verification-by-case route. Agent output is summarized and bounded; raw internal reasoning and `result_data` are not displayed.
- Existing frontend baseline before this review: 13 Vitest tests across 6 files; prior typecheck, lint, and build passed. Browser preview covered login at desktop/mobile sizes; authenticated live E2E was not available.
- Latest recorded backend baseline is 209 passed, 6 opt-in checks skipped, 0 failures. The 2026-10-10 full rerun was interrupted after it produced no output for seven minutes, so it is not a fresh pass.
- Product/security docs require organization isolation at backend resource boundaries, RBAC close to protected operations, deterministic workflow authority, immutable audit records, and treating LLM/document content as untrusted. Phase 20 remains responsible for production config defaults, CORS/API docs, uploads, and external-model data policies.

## Documented next phase

The operations roadmap explicitly names **Phase 19 — Identity and provisioning** as next after Phase 18. Its scope is to replace public self-service creation with controlled provisioning, prevent caller-selected organization/privileged role/active status, and add cross-tenant and privilege-escalation tests. The existing organization/user/role tables, JWT authentication, and audit log exist, so Phase 19 can proceed without replacing the authentication architecture.

Phase 20 is explicitly separate and follows Phase 19. It covers production startup defaults, CORS/API-doc exposure, uploads, and provider data handling; this implementation does not mark those controls complete.

## Phase 19 requirement-to-implementation matrix

| Source | Required behavior | Existing state | Security gap / dependency | Planned implementation and verification |
|---|---|---|---|---|
| Operations roadmap §34, Phase 19 | Replace anonymous self-service registration with controlled provisioning. | `/auth/register` is public. | Any network caller can create accounts. Existing auth/user tables are sufficient. | Remove the anonymous route; add authenticated organization-admin user list/create endpoints. Test anonymous and non-admin denial. |
| Operations roadmap §34, Phase 19 | Caller cannot choose tenant. | `UserCreate.organization_id` is accepted directly. | Cross-tenant account injection. | Derive the new user's organization from the authenticated ADMIN; reject extra `organization_id` fields. Test foreign-tenant payload attempts. |
| Operations roadmap §34, Phase 19 | Caller cannot self-assign a privileged role. | `UserCreate.role` accepts all roles including ADMIN. | Privilege escalation. | Provisioning endpoint accepts only CUSTOMER, EMPLOYEE, or MANAGER, and only from an authenticated same-tenant ADMIN. ADMIN bootstrap stays an operator-run local script. Test ADMIN assignment and employee escalation attempts. |
| Operations roadmap §34, Phase 19 | Caller cannot choose account active status. | `UserCreate.is_active` defaults true and can be overridden. | Caller controls activation. | Exclude status from the provisioning schema and set it server-side under admin provisioning policy. Test extra status fields are rejected and stored status follows policy. |
| Operations roadmap §34, Phase 19 | Cross-tenant identity isolation. | Email uniqueness is organization-scoped; login query is global. | Same email in multiple tenants makes login ambiguous. | Add a case-insensitive global email index migration with duplicate preflight; normalize new addresses and fail closed on ambiguous legacy data. Test case-fold duplicates and ambiguous-login denial. |
| Architecture and operations audit principles | Sensitive provisioning changes are auditable without storing secrets. | Audit service/model exists; user creation is not audited. | No actor/resource trace for provisioning. | Write user-provision action and safe metadata in the same DB transaction as creation. Never record a password/hash. Test audit row and atomicity. |
| Existing JWT auth contract | Revoked/inactive/stale identity cannot continue using a token. | `/me` checks user existence and active flag; token claims are not cross-checked; org active state is ignored. | Stale role/org claims and disabled tenants are not rejected at the identity dependency. | Validate subject UUID, compare signed `org_id`/role against live user, require active user and organization. Test malformed, stale, inactive, and cross-org claims. |
| Local setup guide and current local demo script | A clean local environment can obtain its first administrator without public signup or a fixed password. | The guide calls public registration; the untracked script embeds a fixed password and resets existing users. | Public bootstrap and credential disclosure/reset risk. | Make the existing bootstrap prompt for email/password, reject non-development settings and existing accounts, and never print credentials. Update setup guide and test helper behavior. |

### Phase 19 architecture and test plan

- **API:** `GET /api/v1/auth/users` and `POST /api/v1/auth/users`, both requiring a live ADMIN identity. List only the actor's organization. Creation accepts name, unique email, password, and an allowed non-ADMIN role; organization and active state are server-owned. Anonymous `/auth/register` is retired.
- **Identity:** Normalize emails for lookup/storage and enforce case-insensitive global uniqueness because the existing login contract has no organization identifier. Migration preflight must stop safely and name the remediation requirement if duplicate legacy identities exist; it must not select or merge tenant users automatically.
- **Authorization:** Admin checks use the database-backed current identity, not caller-supplied claims or body fields. Non-admin roles and foreign-tenant payloads fail closed. Protected resource routes remain independently authorized by their owning domain services.
- **Audit:** Persist a successful provisioning audit record in the same database transaction as the new user. Record actor, organization, resource ID, role, email, and active policy only; exclude password, hash, and token.
- **Bootstrap:** Keep first-admin creation as an operator-run development script because no external identity provider or safe organization-owner bootstrap exists. The script prompts for credentials, does not reset existing users, and refuses non-development `APP_ENV`.
- **Database:** Add a new Alembic revision after the current head; do not edit the historical initial migration. Upgrade preflight identifies duplicate lowercased emails before replacing the tenant-scoped uniqueness rule with a global case-insensitive unique index. Downgrade restores the old constraint only if resulting rows satisfy it.
- **Tests:** Add anonymous access, authenticated non-admin denial, admin success, same-tenant list scope, foreign organization injection, ADMIN role injection, active-state injection, case-insensitive duplicate, legacy ambiguous login, inactive account/organization, malformed/stale token claims, audit metadata/no-secret, failed transaction rollback, and bootstrap no-default/no-reset tests. Preserve the existing auth and full regression tests.
- **Threat scenarios:** Self-provisioned tenant membership, privilege escalation to ADMIN/manager, login resolving another tenant's same email, disabled identity reuse, credential leakage through logs/CLI output, and non-atomic account/audit writes.
- **Rollback:** Keep API changes additive except for retiring public register. Migration downgrade is safe only when all emails are unique per organization; it does not delete or merge accounts. If duplicate-email preflight blocks deployment, resolve records with the organization owner before retrying.

## Frontend redesign plan

1. Establish color, type, spacing, radius, elevation, focus, and semantic-state tokens; remove compressed one-off styling and improve secondary-text legibility.
2. Create one reusable VerifiaAI mark as an SVG asset, use it in the shell and sign-in view, add the production favicon, and keep the wordmark text unchanged.
3. Refine shell hierarchy, page headings, tables, forms, action states, and responsive navigation across all existing routes. Do not add unsupported product sections.
4. Complete keyboard behavior for mobile navigation and dialogs, add a route-level error boundary, and preserve reduced-motion and visible-focus behavior.
5. Keep authenticated document downloads and text-only untrusted content handling; validate production API URL policy without exposing server secrets.
6. Add targeted tests for accessibility controls, error recovery, safe URL configuration, provisioning UI, and responsive component behavior. Inspect the rendered interface with the browser where the local server permits.

## Phase 19 implementation result

Phase 19 is implemented in the API and local bootstrap path:

- Removed anonymous `/auth/register`; only a live organization ADMIN can list and provision users, and the organization is derived from the signed-in administrator.
- Provisioning accepts only CUSTOMER, EMPLOYEE, or MANAGER, rejects extra fields such as `organization_id`, `role=ADMIN`, and `is_active`, normalizes email case, and writes a secret-free audit event in the same transaction as the user.
- `/auth/me` checks the token subject format, current account, organization and role claims, and active organization. Login rejects inactive accounts or organizations and fails closed when legacy duplicate identities are found.
- Migration `0009_global_user_email_identity` adds case-insensitive global email uniqueness and checks for duplicates before changing the schema. The local admin bootstrap is development-only, prompts without echo for a user-chosen password, refuses to reset existing users, and never prints the secret.
- The frontend includes an ADMIN-only **User access** route, safe user provisioning form, role-aware route handling, and public-origin HTTPS enforcement. Local loopback HTTP remains available for development.

### Verification

| Check | Result |
|---|---|
| Frontend tests | Passed: 17 tests across 7 files. |
| Frontend typecheck, lint, production build | Passed. Vite 8.3.4 built 1,703 modules. |
| Browser preview | Login rendered at desktop and 304 px viewport; fixed and rechecked narrow-screen horizontal overflow. No authenticated live API flow was available. |
| Alembic graph and offline SQL | Passed: `0009_global_user_email_identity` is head and `alembic upgrade head --sql` generated SQL through it. Migration was not applied to PostgreSQL. |
| Focused backend tests | Passed: 20 tests across auth service, provisioning, and development bootstrap. Added the missing `aiosqlite` test dependency to `requirements-dev.txt`. |
| Backend Ruff | Passed for the modified auth modules, migration, bootstrap script, and focused tests. |
| Full backend regression | One unrelated failure: `tests/test_phase17_evaluation_data.py` requires ignored local file `data/phase17_evaluation/acceptance_thresholds.json`, which is absent from this checkout. Six opt-in live provider tests were skipped; all other collected tests passed. |
| Docker Compose config | Passed. Docker engine access failed at `npipe:////./pipe/dockerDesktopLinuxEngine`, so the database migration, image build, and live app stack could not be checked. |
| Dependency audit | `npm audit --omit=dev` could not reach `registry.npmjs.org` (DNS `ENOTFOUND`); no audit result is claimed. |

See the current audit update below for the latest regression results and unresolved limitations. The Phase 20 scope remains open for production defaults, CORS/API-doc exposure, upload policy, and provider data handling.

## Current audit update — 2026-10-10

The original Phase 19 provisioning findings and the Phase 18 customer API gap are fixed in the current working tree. The implementation is usable through automated contracts, but live PostgreSQL/Compose and authenticated browser-to-API acceptance remain blocked by the unavailable Docker runtime and local browser/sandbox restrictions.

| Audit ID | Requirement | Current implementation and evidence | Status |
|---|---|---|---|
| P18-R001 | Role-aware login, session restoration, logout and cache cleanup | `AuthContext`, API client, app route guards; frontend auth and app tests. Backend logout invalidates the token version and writes a secret-free audit row. | PASS in automated tests |
| P18-R002 | Internal case, task, document, verification and approval flows use backend results | Internal case/task/approval pages; API client and backend domain/human-review tests. Manager decisions remain server-authoritative. | PASS in automated tests; live E2E not run |
| P18-R003 | Customer create/list/detail/upload operations are limited to linked cases | `/cases/mine`, `/cases/mine/{id}`, `/documents/mine`, and customer process options; customer access tests cover unlinked and closed cases. Customer UI uses only those contracts. | PASS in automated tests; live E2E not run |
| P18-R004 | Supported documents can be previewed without rendering arbitrary uploaded HTML | PDF/image previews use authenticated Blob downloads, sandboxed PDF frames, MIME allowlists, and object-URL cleanup. `DocumentsPanel.test.tsx` covers the employee PDF preview; customer workspace tests cover its file actions. | PASS in automated tests |
| P18-R005 | Responsive operation, explicit loading/error states, build and developer setup | Frontend test suite: 21 passed across 10 files; typecheck, ESLint, and production build pass. Compose syntax passes. Full manual responsive/keyboard and authenticated live API review was not available. | PARTIAL |
| P19-R001 | Retire anonymous registration; ADMIN provisioning is organization-scoped and non-ADMIN | Provisioning derives organization and active state from the actor; request schema rejects caller-controlled fields; audited transaction. `test_auth_provisioning.py`. | PASS in automated tests |
| P19-R002 | Prevent ambiguous identities across organizations | Migration `0009_global_user_email_identity` preflights duplicate lowercase emails; service normalization and ambiguity fail-closed behavior are tested. | PASS in tests and offline migration SQL; PostgreSQL apply unverified |
| P19-R003 | Reject inactive/stale identity and revoke prior bearer sessions | Current user checks subject, role, tenant, user and organization; migration 0010 adds `token_version`; logout/password changes increment it. Logout audit assertions pass. | PASS in automated tests |
| P19-R004 | Safe first-admin and password lifecycle | Bootstrap is development-only, prompts with hidden input twice, requires 15 characters and at most 72 UTF-8 bytes, does not accept `--password`, reset existing accounts, or print the secret. Self-change/admin reset also revoke sessions and are audited without credential data. | PASS in automated tests |
| P19-R005 | Enforce role and tenant boundaries on protected API routes | Domain routers apply backend role checks and resource scoping for cases/documents, processes, tasks, approvals, workflow, rules, verifications, events, and agents. Current full backend run passed every collected case except the separate missing Phase 17 fixture. | PASS in automated tests; PostgreSQL-backed execution unverified |

### Latest verification results

- Frontend: `npm test -- --run` — **21 passed across 10 files**; `npm run typecheck`, `npm run lint`, and `npm run build` all passed. `docker compose config -q` passed.
- Backend: full regression — **232 passed, 1 failed, 6 skipped**. The only failure is the Phase 17 threshold-gate test because the ignored file `data/phase17_evaluation/acceptance_thresholds.json` is missing. The user confirmed they do not have it; no threshold values were fabricated. Six provider integration checks are opt-in.
- Backend targeted auth/bootstrap regression — **22 passed**. The Windows host has bcrypt 5 although the project pins `bcrypt>=4.0.1,<4.1`; tests used a temporary process-only hash shim matching the pinned bcrypt 4 truncation behavior. No dependency was installed or changed.
- Ruff: project-wide `ruff check app tests scripts` reports 1,303 findings in the current tree; the repository is not Ruff-clean. Findings include import-order, legacy typing, and FastAPI `Depends` rules; no repository-wide auto-fix was applied. The focused F-rule check across touched backend modules passes.
- Database: `python -m alembic heads` reports `0010_user_token_version`; `python -m alembic upgrade head --sql` generated offline SQL through 0010. The migration was not applied to PostgreSQL because Docker Desktop's Linux engine is unavailable.
- Runtime: `docker compose config -q` passes, but no container or live backend/frontend E2E was started. A shell health probe was denied by the Windows sandbox and the local browser refused the loopback URL, so no runtime health result is claimed.

### Remaining risks

- **Blocked — Phase 17 quality gate:** restore the original ignored `acceptance_thresholds.json` or the source that defines its values, then rerun the labeled threshold test and relevant evaluator. Current historical metrics do not reconstruct that gate.
- **Blocked — PostgreSQL migration:** start the Docker Desktop Linux engine (or provide a supported PostgreSQL instance), apply migrations through 0010, and run API integration tests against it.
- **Partial — browser/session architecture:** access tokens remain in `sessionStorage`, so a same-origin script compromise can read them. Logout/password changes now revoke server-side token versions, but there is no refresh-token or HttpOnly-cookie flow.
- **Open — Phase 20:** production startup defaults, CORS/API-doc exposure, upload policy, provider data handling, and runtime security headers are still future work.

