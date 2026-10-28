# Verifia — Detailed Implementation Checklist

This checklist converts the Verifia implementation roadmap into concrete, independently checkable tasks. Each phase explains what must actually be implemented and includes a Definition of Done.

---

# 0. Project Rules Before Coding

- [x] PostgreSQL is the authoritative source of business state.
- [x] Every Case references a specific immutable `ProcessVersion` (case creation now requires a published version).
- [x] Agents never directly mutate authoritative business/workflow state; consequential changes go through validated services and tools.
- [x] Agents use capabilities through the Tool Gateway (Document, Verification, and Workflow actions go through their existing controlled paths; Supervisor delegates only through these child-agent services).
- [x] Workflow transitions are validated by the Workflow Engine.
- [x] Critical calculations and business rules are deterministic.
- [x] Human approvals are explicit and auditable (decision actor/time/comment plus event and audit records).
- [x] Important runtime business actions create events/audit records (case lifecycle, workflow, tasks, verification, and approvals).
- [x] Foundational organization isolation is enforced on Case creation, Workflow execution, the Tool Gateway, and Human Review paths; route-by-route security audit remains explicitly scheduled for Phase 20.
- [x] Configuration is data-driven rather than hard-coded.
- [x] Import/Export is the first complete end-to-end process: clean approval/completion and discrepancy/review/rejection were both exercised through authenticated application interfaces in Phase 17; ten-scenario evaluation remains a separate Phase 17 closeout gate.
- [x] Process behavior is represented through versioned configuration and the same application architecture; the Insurance Claim second-process generalization test passed through the shared APIs and persistence boundaries in Phase 24.

---

# 1. Repository & Development Foundation

## 1.1 Repository

- [x] Create Git repository.
- [x] Create `README.md`.
- [x] Create `.gitignore`.
- [x] Create `.env.example`.
- [x] Create `docker-compose.yml`.
- [x] Create `backend/`.
- [x] Create `frontend/`.
- [x] Create `backend/tests/` for the backend suite; keep frontend/end-to-end tests with their owning client when implemented.
- [x] Create `data/`.
- [x] Create `workflows/`.

Current root layout:

```text
VerifiaAI/
├── backend/
│   ├── app/
│   ├── alembic/
│   ├── scripts/
│   ├── tests/
│   └── requirements*.txt
├── frontend/
│   └── src/                 # Placeholder for Phase 18
├── data/
├── workflows/
├── Documentation/
├── docker-compose.yml
├── .env.example
└── README.md
```

There is no separate root-level `ai/` package: AI runtime code belongs to the backend agent, domain, and LLM-provider modules. Backend tests are under `backend/tests/`; frontend tests will live with the frontend implementation.

## 1.2 Backend

- [x] Set up Python environment.
- [x] Install FastAPI and Uvicorn.
- [x] Install SQLAlchemy and Alembic.
- [x] Install Pydantic.
- [x] Install PostgreSQL driver.
- [x] Install pytest.
- [x] Create `backend/app/main.py`.
- [x] Create configuration/settings module.
- [x] Load environment variables.
- [x] Configure logging.

## 1.3 Backend Modules

Current backend package layout:

```text
app/
├── api/                 # Router aggregation
├── core/                # Settings and logging
├── security/            # Authentication and authorization
├── agents/
├── domain/
│   ├── approvals/
│   ├── audit/
│   ├── cases/
│   ├── documents/
│   ├── knowledge/
│   ├── organizations/
│   ├── processes/
│   ├── rules/
│   ├── tasks/
│   ├── verifications/
│   └── workflows/
├── events/
├── infrastructure/
│   ├── database/
│   ├── llm/providers/
│   ├── queue/
│   └── storage/
└── tools/               # Tool Gateway and trusted integrations
```

For each module:

- [x] Create package.
- [x] Create schemas.
- [x] Create service layer.
- [x] Create models where needed.
- [x] Create API router where needed.
- [x] Keep business logic out of API handlers.

## 1.4 Infrastructure

- [x] Start PostgreSQL.
- [x] Connect FastAPI to PostgreSQL.
- [x] Add `/health`.
- [x] Configure Alembic.
- [x] Verify migrations from an empty database.
- [x] Start Redis.
- [x] Verify Redis connection.
- [x] Define asynchronous jobs: document processing, OCR, embeddings, long-running agents/verifications.

### Definition of Done

- [x] `docker compose up` starts required services.
- [x] FastAPI starts.
- [x] `/health` works.
- [x] PostgreSQL connection works.
- [x] Redis connection works.
- [x] Database migrations work.
- [x] README explains setup.

---

# 2. Database

## 2.1 Organization & Security

### Organization

- [x] ID.
- [x] Name.
- [x] Status.
- [x] Timestamps.

### User

- [x] ID.
- [x] Organization ID.
- [x] Name.
- [x] Email/auth identifier.
- [x] Status.
- [x] Timestamps.

### Roles

Initial roles:

- [x] Customer.
- [x] Employee.
- [x] Manager.
- [x] Admin.

Create:

- [x] `Role`.
- [x] `UserRole`.
- [x] `Department`.
- [x] `DepartmentMember`.

## 2.2 Process Configuration

### Process

- [x] Organization ID.
- [x] Name.
- [x] Description.
- [x] Status.

### ProcessVersion

- [x] Process ID.
- [x] Version number.
- [x] Status: DRAFT/PUBLISHED/ARCHIVED.
- [x] Created/published timestamps.
- [x] Existing cases reference the selected version.
- [x] Published versions cannot be modified in place.

## 2.3 Workflow

### WorkflowStage

- [x] Process version ID.
- [x] Name.
- [x] Description.
- [x] Order.
- [x] Entry/exit configuration.

### WorkflowTransition

- [x] Source stage.
- [x] Target stage.
- [x] Name.
- [x] Conditions.
- [x] Required permission.
- [x] Status.

## 2.4 Case

### Case

- [x] Organization ID.
- [x] Process version ID.
- [x] Case number.
- [x] Current stage.
- [x] Status.
- [x] Priority.
- [x] Created by.
- [x] Timestamps.

### CaseParticipant

- [x] Case ID.
- [x] User ID.
- [x] Participant role.

## 2.5 Documents

### Document

- [x] Case ID.
- [x] Document type.
- [x] Filename.
- [x] Storage reference.
- [x] Status.
- [x] Uploaded by/time.

### DocumentVersion

- [x] Document ID.
- [x] Version number.
- [x] Storage reference.
- [x] Hash/checksum.
- [x] Processing status.

### ExtractedField

- [x] Document version.
- [x] Field name.
- [x] Extracted value.
- [x] Normalized value.
- [x] Confidence.
- [x] Page/source location.
- [x] Extraction method.
- [x] Timestamp.

## 2.6 Requirements

Create `Requirement`:

- [x] Process version ID.
- [x] Name.
- [x] Description.
- [x] Type.
- [x] Mandatory flag.
- [x] Configuration.

Support at least:

- [x] Required document.
- [x] Required field.
- [x] Required verification.
- [x] Required approval.

## 2.7 Verification

### VerificationDefinition

- [x] Process version ID.
- [x] Name.
- [x] Business question/description.
- [x] Type.
- [x] Required evidence.
- [x] Configuration.

### VerificationExecution

- [x] Case ID.
- [x] Definition ID.
- [x] Status.
- [x] Inputs.
- [x] Result.
- [x] Evidence.
- [x] Executor.
- [x] Timestamp.

Statuses:

```text
PASS
FAIL
REVIEW
NOT_APPLICABLE
INCONCLUSIVE
```

## 2.8 Rules

### BusinessRule

- [x] Process version ID.
- [x] Name.
- [x] Description.
- [x] Expression/configuration.
- [x] Severity.
- [x] Active status.

Examples:

```text
invoice.quantity == purchase_order.quantity
invoice.total == invoice.quantity * invoice.unit_price
```

## 2.9 Tasks

- [x] Case ID.
- [x] Type.
- [x] Title/description.
- [x] Assigned user/role.
- [x] Status.
- [x] Priority.
- [x] Due date.
- [x] Completion metadata.

## 2.10 Approvals

- [x] Case ID.
- [x] Task ID.
- [x] Approval type.
- [x] Requested from.
- [x] Decision.
- [x] Comment/reason.
- [x] Decided by.
- [x] Decided at.

## 2.11 Tool Executions

- [x] Case ID.
- [x] Tool name.
- [x] Requesting agent.
- [x] Input.
- [x] Output.
- [x] Status.
- [x] Error.
- [x] Timestamp.

## 2.12 Events

Create event records for:

- [x] CASE_CREATED.
- [x] DOCUMENT_UPLOADED.
- [x] DOCUMENT_PROCESSED.
- [x] FIELDS_EXTRACTED.
- [x] VERIFICATION_STARTED.
- [x] VERIFICATION_COMPLETED.
- [x] TASK_CREATED.
- [x] TASK_COMPLETED.
- [x] APPROVAL_REQUESTED.
- [x] APPROVAL_GRANTED.
- [x] APPROVAL_REJECTED.
- [x] WORKFLOW_TRANSITIONED.
- [x] CASE_COMPLETED.

Each event stores:

- [x] Organization.
- [x] Case.
- [x] Event type.
- [x] Payload.
- [x] Actor/source.
- [x] Timestamp.

## 2.13 Audit

Audit at least:

- [x] Login.
- [x] Permission failures.
- [x] Workflow transitions.
- [x] Approvals.
- [x] Tool executions.
- [x] Configuration changes.
- [x] Document access.

## 2.14 Constraints & Indexes

- [x] Foreign keys.
- [x] Unique constraints.
- [x] Required fields.
- [x] Organization scoping.
- [x] Case/status/stage indexes.
- [x] Document/case indexes.
- [x] Task/assignee/status indexes.
- [x] Verification/case indexes.
- [x] Event/case/time indexes.

### Definition of Done

- [x] Complete Import/Export configuration can be represented.
- [x] A Case references an immutable ProcessVersion.
- [x] Documents, evidence, verifications, tasks, approvals, tools and events link to a Case.
- [x] Schema can be recreated entirely from migrations.

---

# 3. Domain Services & API

Architecture:

```text
API → Domain Service → Repository/ORM → PostgreSQL
```

## CaseService

- [x] Create case.
- [x] Retrieve case.
- [x] Update permitted metadata.
- [x] Retrieve current state.
- [x] Add participant.
- [x] Close case.
- [x] Reject invalid state changes.

## ProcessService

- [x] Create process.
- [x] Create version.
- [x] Add stages.
- [x] Add transitions.
- [x] Add requirements.
- [x] Add verifications.
- [x] Add rules.
- [x] Publish version.
- [x] Archive version.
- [x] Prevent editing published version.

## TaskService

- [x] Create task.
- [x] Retrieve tasks (with org/case/user/status/priority filters).
- [x] Update task (status, priority, completion metadata).
- [x] Auto-set `completed_at` on COMPLETED transition.
- [x] Emit TASK_CREATED and TASK_UPDATED events.

## API

- [x] `POST /cases`
- [x] `GET /cases`
- [x] `GET /cases/{id}`
- [x] `GET /cases/{id}/state`
- [x] `GET /cases/{id}/events`
- [x] `PATCH /cases/{id}`
- [x] `POST /cases/{id}/close`
- [x] `POST /cases/{id}/participants`
- [x] `POST /processes`
- [x] `GET /processes`
- [x] `GET /processes/{id}`
- [x] `GET /processes/{id}/versions`
- [x] `POST /processes/{id}/versions`
- [x] `GET /processes/versions/{id}`
- [x] `POST /processes/versions/{id}/stages`
- [x] `POST /processes/versions/{id}/transitions`
- [x] `POST /processes/versions/{id}/requirements`
- [x] `POST /processes/versions/{id}/verifications`
- [x] `POST /processes/versions/{id}/rules`
- [x] `POST /processes/versions/{id}/publish`
- [x] `POST /processes/versions/{id}/archive`
- [x] `POST /tasks`
- [x] `GET /tasks`
- [x] `GET /tasks/my`
- [x] `GET /tasks/{id}`
- [x] `PATCH /tasks/{id}`

For every endpoint:

- [x] Request schema.
- [x] Response schema.
- [x] Authentication.
- [x] Authorization.
- [x] Validation.
- [x] Error responses.
- [x] Tests.

### Definition of Done

- [x] Cases can be created/retrieved through API.
- [x] Process configuration can be retrieved.
- [x] Published process versions cannot be mutated.
- [x] API handlers delegate business logic to services.
- [x] Tasks emit events and auto-set completion timestamps.

---

# 4. Workflow Engine

## 4.1 Transition Request

Create a structured request containing:

- [x] Case ID.
- [x] Current/source stage.
- [x] Target stage.
- [x] Actor.
- [x] Reason.

## 4.2 Validate Transition

Check:

- [x] Case exists.
- [x] ProcessVersion exists.
- [x] Current stage matches source.
- [x] Target is an allowed transition.
- [x] Required documents exist.
- [x] Required fields/verifications are satisfied.
- [x] Required approvals exist.
- [x] Actor has permission.
- [x] No blocking exception exists.
- [x] Case is not already completed.

## 4.3 Execute

When valid:

- [x] Update case stage.
- [x] Create workflow event.
- [x] Create audit record.
- [x] Return structured success.

When invalid:

- [x] Do not modify state.
- [x] Return structured rejection reason.
- [x] Audit where appropriate.

## 4.4 Test Without AI

Run:

```text
Document Collection
→ Document Verification
→ Inventory Check
→ Finance Review
→ Manager Approval
→ Shipping
→ Completed
```

Test:

- [x] Valid transition.
- [x] Invalid transition.
- [x] Missing requirement.
- [x] Missing approval.
- [x] Unauthorized transition.
- [x] Repeated transition.
- [x] Transition after completion.

### Definition of Done

- [x] Complete workflow can execute without AI.
- [x] Invalid transitions are rejected deterministically.
- [x] Successful transitions update state and create events.
- [x] Tests cover success and failure paths.

---

# 5. Rules & Deterministic Verification

## Rule Engine

Implement initially:

- [x] Equality.
- [x] Inequality.
- [x] Greater/less than.
- [x] Arithmetic.
- [x] Required field.
- [x] Existence.
- [x] Cross-document comparison.

Avoid building a full programming language.

## Calculation Engine

Example:

```text
total = quantity × unit_price
```

Test:

- [x] Integers.
- [x] Decimal values.
- [x] Missing values.
- [x] Invalid values.
- [x] Rounding.
- [x] Domain-specific edge cases.

## Verification

Implement:

```text
Verification Definition
        ↓
Inputs
        ↓
Rules / Calculations / Tools
        ↓
Deterministic Result
        ↓
VerificationExecution
```

## Evidence

Each result links to:

- [x] Source documents.
- [x] Extracted fields.
- [x] Tool results (successful, same-case tool execution IDs supplied to the verification run).
- [x] Rules.
- [x] Calculations.

Example:

```text
PO quantity = 500
Invoice quantity = 480
Difference = -20
```

### Definition of Done

- [x] Import/Export verification works without an LLM.
- [x] Same inputs produce repeatable results.
- [x] Results preserve evidence and inputs.
- [x] Discrepancies can produce REVIEW.

---

# 6. Tool Gateway

## Tool Contract

Every tool defines:

- [x] Name.
- [x] Description.
- [x] Input schema.
- [x] Output schema.
- [x] Required permission.
- [x] Organization scope.
- [x] Allowed agents.
- [x] Failure behavior.

## Initial Tools

- [x] `check_required_documents`
- [x] `compare_documents`
- [x] `calculate_order_total`
- [x] `check_inventory` (ERPNext adapter contract tests and live Tool Gateway use in Phase 17.)
- [x] `get_customer` (read-only ERPNext adapter, structured output contract, missing/malformed-record tests; live lookup awaits the local ERPNext service.)
- [x] `get_payment_status` (ERPNext adapter tests and live Tool Gateway use in Phase 17.)
- [x] `run_verification`
- [x] `create_task`
- [x] `request_approval`

`check_inventory`, `get_customer`, and `get_payment_status` have organization-scoped gateway contracts and trusted ERPNext adapters. Inventory and payment were exercised against the local ERPNext integration in Phase 17; customer lookup has adapter contract coverage but no live fixture result yet. These checks establish the selected ERPNext adapter, not production coverage for arbitrary providers.

## Authorization

```text
Agent
 ↓
Tool Gateway
 ↓
Agent allowed?
 ↓
Correct organization?
 ↓
Case accessible?
 ↓
Tool allowed for process?
 ↓
Execute
```

- [x] Implement organization, case, process-tool, agent-type, and permission checks.
- [x] Validate arguments.
- [x] Validate outputs.
- [x] Record execution.

Process-version configuration selects registered tools and can restrict agent types:

```json
{
  "tool_gateway": {
    "allowed_tools": {
      "calculate_order_total": {
        "enabled": true,
        "allowed_agents": ["VERIFICATION", "WORKFLOW"]
      },
      "check_inventory": {
        "enabled": true,
        "integration_type": "ERP",
        "integration_id": "<organization integration UUID>",
        "allowed_agents": ["VERIFICATION"]
      }
    }
  }
}
```

The gateway resolves tool names only through handlers registered in trusted
application code. Process and organization configuration can enable a handler,
restrict its agents, and select an organization integration; it cannot submit
executable code. Integration credentials remain behind the adapter and are
referenced through integration configuration, never tool arguments or traces.

### Definition of Done

- [x] Agents cannot bypass gateway. (Document Agent, Verification Agent, and Workflow Agent all use the Tool Gateway; Supervisor Agent integration is scheduled for Phase 13.)
- [x] Unauthorized calls fail.
- [x] Inputs/outputs are structured.
- [x] Every execution is auditable.

---

# 7. Object Storage & Document Upload

## Storage Abstraction

Implement:

```text
upload()
download()
delete()
exists()
```

- [x] Keep storage implementation behind an interface (`StorageBackend`: upload, download, delete, exists; local filesystem adapter implemented).
- [x] Store binary files outside PostgreSQL (atomic local filesystem writes; provider selected through adapter factory).
- [x] Store metadata/reference in PostgreSQL (document/version rows hold opaque storage references and integrity metadata).

## Upload Pipeline

```text
Upload
 ↓
Validate
 ↓
Hash
 ↓
Store
 ↓
Create Document
 ↓
Create DocumentVersion
 ↓
Create Event
```

Validate:

- [x] File type (PDF, PNG/JPEG, XLS/XLSX, CSV, DOCX, and UTF-8 TXT; extension, signature/content, and declared MIME are checked).
- [x] DOCX archive limits are configurable for entry count, total expanded bytes, and per-entry expanded bytes; encrypted, unsafe-path, macro-enabled, malformed, or oversized packages are rejected.
- [x] File size (configurable `DOCUMENT_MAX_FILE_SIZE_BYTES`; default 20 MiB).
- [x] Filename (safe single filename, printable characters, maximum 255 characters).
- [x] Storage success (metadata and upload event are committed after the binary is stored; failed DB work rolls back and removes the object).
- [x] Duplicate behavior (same case, type, and SHA-256 returns the existing document; identical bytes submitted as a new version do not create a duplicate version/event).

### Definition of Done

- [x] Documents upload to a Case (authenticated and organization-scoped multipart endpoint).
- [x] Metadata is persisted.
- [x] Binary storage is abstracted.
- [x] Versions are tracked and downloadable by version.
- [x] Upload event is created for each accepted new document/version.

Implementation note: the local filesystem adapter is implemented and tested. MinIO/S3 environment placeholders are not provider adapters; selecting either backend currently returns an explicit unavailable-backend error. Add and verify a deployment-specific provider adapter when the deployment target is chosen.

DOCX and TXT are accepted and stored as immutable document versions. Phase 7 does not parse their content; parsing, OCR, classification, and extraction remain Phase 8 work.

---

# 8. Document Intelligence

## Parsing

Support:

- [x] PDF text blocks and table extraction with page and bounding-box locators.
- [x] PNG/JPEG input validation and image inspection before OCR.
- [x] Excel XLSX cells and legacy XLS cells with sheet/cell locators.
- [x] CSV rows and columns with delimiter detection.
- [x] DOCX paragraphs, tables, headers, and footers plus UTF-8 TXT lines, aligned with the supported-input list in the architecture document.
- [x] Bound OOXML archive entries and expanded size before parser access; preserve hidden worksheet/image warnings rather than silently presenting skipped content as parsed.

## OCR

```text
Image/PDF
 ↓
OCR
 ↓
Text + page/location metadata
```

- [x] Detect image uploads and textless PDF pages that require OCR.
- [x] Provide a Tesseract adapter for scanned PDF pages and PNG/JPEG input, including timeout and image-size limits.
- [x] Store normalized parsed text and source blocks as a private object associated with the processing run.
- [x] Preserve page, bounding-box, sheet/cell, table, row/column, paragraph, and line locations where applicable.
- [x] Verify OCR against a real scanned image using the installed Tesseract executable; the SROIE receipt sample passed. Broader scanned-image/PDF accuracy checks remain open.

## Classification

Initial classes:

- [x] Invoice.
- [x] Purchase Order.
- [x] Packing List.
- [x] Unknown.
- [x] Keep the class catalog extensible by process configuration; include common commercial, financial, legal, trade, identity, logistics, and correspondence types without adding type-specific application workflows.

Store:

- [x] Persist predicted type, confidence, classifier model, and processing timestamps per versioned run.

## Structured Extraction

Invoice schema:

```text
invoice_number
supplier
date
currency
items
quantity
unit_price
total
```

- [x] Define default invoice, purchase order, and packing-list JSON Schema contracts and Pydantic output/provenance models; allow process configuration to extend schemas and version them.
- [x] Implement a document-specific JSON model adapter and extraction prompt with untrusted-document handling.
- [x] Validate configured schemas, required fields, types, date formats, numeric values, allowed field names, and cited source quotes.
- [x] Store extracted values, confidence, method/model, schema version, citations, and source locators against a processing run.
- [x] Flag invoice line-item and total discrepancies for review.

## Validation

- [x] Required fields.
- [x] Data types.
- [x] Date validity.
- [x] Numeric validity.
- [x] Invoice line-item/total logical consistency.
- [x] Configurable confidence threshold and review-required result.
- [x] Create one pending `DOCUMENT_REVIEW` task for a review-required processing run, with a high priority for low classification confidence. Tasks remain unassigned for manual pickup because no Phase 8 reviewer-assignment policy is configured.

### Definition of Done

- [x] Process a generated invoice PDF fixture end-to-end through parser, fake JSON model adapter, persistence, and storage.
- [x] Run OCR against a real scanned image sample with Tesseract installed; the live SROIE receipt check passed. Broader image/PDF OCR evaluation remains follow-up work.
- [x] Establish representative-document accuracy against the broader labeled Phase 17 set using the configured live Document Agent baseline. LLM7 `gpt-oss:20b` processed 20/29 documents with 1.00 classification accuracy, 0.9712 required-field exact match over 104 fields, and 1.00 citation validity over 300 citations; nine attempts failed (five provider/gateway errors, four output-format errors). This meets the configured minimum sample thresholds but remains a synthetic-data result, not real-world generalization. See `data/phase17_evaluation/reports/document_agent_llm7_20261009.json`.
- [x] Persist classification and schema-valid extracted fields.
- [x] Preserve source citations and locators through extraction.
- [x] Low confidence creates a pending human review task; the task is not auto-assigned to a person or role.

### Phase 8 implementation boundary and current verification

The implementation processes one selected immutable document version through an authenticated, organization-scoped endpoint. Processing runs retain parser/OCR/model/schema/configuration provenance, normalized content is stored through the object-storage abstraction, and extracted field values retain source citations. Review outcomes are represented as `NEEDS_REVIEW` and `review_required` and create a pending, unassigned `DOCUMENT_REVIEW` task with a linked run ID. Processing does not assign a reviewer or mutate workflow/case business state. The current API runs the processing call inline. The existing queue module only logs jobs and does not provide a durable worker, so production background dispatch/retry remains open rather than being described as implemented.

The default automated suite uses generated fixtures and deterministic fake adapters. Five opt-in live integration checks are available in `backend/tests/test_live_integrations.py`. The Groq synthetic-document check passes 3/3 class predictions and 17/17 expected field values with valid citations; live Cloudflare embedding, KnowledgeService, PostgreSQL/pgvector, and SROIE/Tesseract checks have also passed locally. Broader representative-document accuracy and varied OCR evaluation remain open in the Definition of Done.

---

# 9. Knowledge / RAG

## Knowledge Sources

Prepare:

- [x] Company SOP.
- [x] Import policy.
- [x] Approval policy.
- [x] Shipping procedure.
- [x] Required-document policy.

## Ingestion

```text
Document
 ↓
Parse
 ↓
Chunk
 ↓
Embed (Cloudflare Workers AI BAAI/bge-m3 API / optional Hugging Face or local adapter)
 ↓
pgvector (Vector(1024) HNSW Cosine Index)
```

- [x] Knowledge document metadata.
- [x] Text extraction (PDF, DOCX, TXT, CSV via Phase 8 parsers).
- [x] Chunking (sentence-aware with overlap).
- [x] Embedding generation (`@cf/baai/bge-m3` 1024-dim Cloudflare Workers AI API adapter with L2 normalization; live API and KnowledgeService ingestion smoke checks pass).
- [x] Vector storage (pgvector 1024-dim with HNSW index).
- [x] Organization metadata (`organization_id` denormalized & indexed for strict isolation).

## Retrieval

- [x] Semantic search (pgvector cosine ANN similarity).
- [x] Top-k retrieval (configurable limit).
- [x] Metadata filters (source_type, source_ids).
- [x] Organization filtering (hard-scoped SQL tenant isolation).
- [x] Source references (title, source name, chunk index, similarity score).

### Definition of Done

- [x] Policies can be ingested.
- [x] Relevant content can be retrieved.
- [x] Retrieval is organization-scoped.
- [x] Search API and Tool Gateway expose source-grounded results for configured agent use (the Document Agent does not yet add RAG results to its extraction prompt).
- [x] RAG is not treated as authoritative business state.

---

# 10. Document Agent

Pipeline:

```text
Document
 ↓
Understand
 ↓
Classify
 ↓
Extract
 ↓
Validate
 ↓
Structured Result
```

Implement:

- [x] Input schema.
- [x] Classification prompt/model.
- [x] Extraction prompt/model.
- [x] Structured output.
- [x] Evidence references.
- [x] Confidence handling.
- [x] Failure handling.

Prohibit direct mutation of authoritative business state:

- [x] Direct workflow mutation.
- [x] Direct mutation of case/workflow/approval state (processing, task, and execution records persist through their domain services).
- [x] Approvals.
- [x] Critical calculations.
- [x] Unrestricted tools.

### Definition of Done

- [x] Classification works.
- [x] Extraction works.
- [x] Output validates against schema.
- [x] Evidence is preserved.
- [x] Agent cannot directly mutate business state.

### Verification record — 2026-10-05

- [x] Phase 9 regression coverage: 21 phase-specific tests, including tenant isolation, source-scoped deduplication, RBAC, and knowledge-document route lifecycle.
- [x] Phase 10 coverage: 8 agent/gateway tests, including clean extraction, low-confidence review, failed-execution recording, zero-confidence preservation, and explicit gateway embedding failure behavior.
- [x] Default backend suite: 100 tests pass; five opt-in live integration tests skip when `VERIFIA_RUN_LIVE_TESTS` is unset.
- [x] Groq adapter contract: mocked request/JSON handling and ordered API-key fallback pass; Groq Qwen 3.8 27B is the configured Document Agent provider.
- [x] Opt-in live checks: Groq document evaluation, Cloudflare embedding/KnowledgeService, PostgreSQL/pgvector, and SROIE/Tesseract checks have passed locally.
- [x] Alembic offline SQL generation succeeds through migration `0006_knowledge_rag`.
- [x] Online migration application and PostgreSQL/pgvector extension, dimensions, and HNSW index were verified against the local configured database; relevance ranking evaluation remains separate.

---

# 11. Verification Agent

**Status: Implemented and verified — 2026-10-06.** The agent builds organization-scoped case/evidence context, offers only stage-applicable definitions and tools currently exposed by the Tool Gateway, validates the model plan, and executes every selected deterministic verification through the gateway. It then interprets the recorded outputs while retaining the gateway's deterministic results in a separate response field. Failures, inconclusive deterministic states, missing information, and model-identified discrepancies produce a human-review proposal. The agent cannot create tasks/approvals or mutate case/workflow state.

Input:

```text
Case State
+
Verification Definitions
+
Available Evidence
```

Implement:

- [x] Determine missing information.
- [x] Determine required verification from the case stage, configured definitions, and evidence.
- [x] Select tools from the authorized Tool Gateway inventory.
- [x] Call Tool Gateway and persist its auditable executions.
- [x] Interpret deterministic results in a separate model response.
- [x] Identify discrepancies and route them to human review.
- [x] Produce and validate structured planning and interpretation outputs.
- [x] Preserve deterministic results separately from model interpretation.
- [x] Prevent the agent from overwriting authoritative results; selected verifications must map to gateway calls.

### Definition of Done

- [x] Correct verification is selected from definitions applicable to the active case stage.
- [x] Appropriate tool is selected from the agent's authorized Tool Gateway inventory.
- [x] Tool call is authorized by Tool Gateway process policy and user permissions.
- [x] Deterministic result is preserved in `result_data.deterministic_results` independently of interpretation.
- [x] Discrepancy, inconclusive status, missing information, rejected calls, and failed calls can trigger review.

Coverage: `backend/tests/test_verification_agent.py` exercises a real configured `run_verification` gateway call, persisted agent/tool/verification execution traces, preservation of a deterministic `NOT_APPLICABLE` status, discrepancy-triggered review, and rejection of a tool not exposed to the agent before it can execute.

---

# 12. Workflow Agent

**Status: Implemented and verified — 2026-10-07.** The Workflow Agent replaces the previous hard-coded placeholder with a complete, auditable agent that reads bounded, organization-scoped case/workflow context, calls the configured JSON model adapter, validates the structured plan against the active process version (fail-closed on unknown actions, stale IDs, and disallowed tools), and routes every consequential action through the Tool Gateway and deterministic domain services. The Workflow Engine remains the sole authority for stage transitions, requirements, and approval gates.

Input:

```text
Case State
+
Workflow Definition
+
Verification Results
+
Tasks
+
Policies
```

Possible proposals:

- [x] Request document.
- [x] Run verification.
- [x] Create task.
- [x] Request approval.
- [x] Propose transition.
- [x] Escalate.

Implement:

- [x] Structured action schema (`ALLOWED_ACTIONS` frozenset; model cannot extend it at runtime).
- [x] Context builder (`_build_context` — bounded, organization-scoped, reads current stage, available transitions, open tasks, pending approvals, recent verifications, documents, and verification definitions).
- [x] Model call (injected `JsonModelAdapter`; structured JSON output bounded by planning schema).
- [x] Action validation (`_validate_plan` — fail-closed on unknown action, stale `target_stage_id`, unknown tool name, invalid UUID, malformed model output).
- [x] Workflow Engine handoff (new `transition_workflow` tool registered in `ToolGatewayService`; delegates to `WorkflowService.execute_transition` with `organization_id` scope; engine enforces all deterministic requirements).
- [x] Invalid proposal handling (raises `WorkflowAgentError`; persists FAILED `AgentExecution` trace; does not mutate case state).

### Definition of Done

- [x] Agent proposes structured actions.
- [x] Invalid proposals are rejected (unknown action or fields, stale or mismatched stage IDs, action/tool mismatch, cross-tenant case, unknown tool, malformed output).
- [x] Agent cannot directly change Case stage (all transitions go through Tool Gateway → `WorkflowService`).
- [x] Workflow Engine remains authoritative (deterministic rejection yields `proposal_state=REJECTED`; model output alone cannot mutate state).

### Verification record — 2026-10-08

- [x] 24 Phase 12 contract, security, gateway, and end-to-end tests pass in `backend/tests/test_workflow_agent.py`; 2 route tests verify actor identity and role are taken from authentication.
- [x] Coverage: PROPOSE_TRANSITION (pure proposal), ESCALATE, CREATE_TASK via Gateway, REQUEST_APPROVAL via Gateway, transition_workflow tool (real stage change), cross-tenant rejection, terminal case rejection, unknown action fail-closed + FAILED trace, malformed model response, unknown stage ID, unknown tool name, gateway denial / stale-state → REJECTED, disabled agent, WorkflowService cross-tenant validation, context scope, ALLOWED_ACTIONS contract, API dispatch, tool registration.
- [x] Full backend regression suite after Phase 12–13 hardening: 144 passed, 5 skipped (opt-in live tests); 0 failures.
- [x] `AgentExecution`, `ToolExecution`, and trace links persist correctly on success and failure.
- [x] `proposal_state` distinguishes `PROPOSED`, `EXECUTED`, and `REJECTED` in every API response.
- [x] Security: authenticated routes overwrite caller-supplied actor identity, role, and type; tenant isolation is enforced at `WorkflowService` (organization_id predicate), `ToolGatewayService._load_case_context` (cross-tenant 403), and `WorkflowAgent._load_scoped_case` (organization_id check). Cross-tenant writes do not add audit records to the case owner's tenant.
- [x] Model output alone cannot mutate case state; all stage changes require Tool Gateway → `WorkflowService.execute_transition`.
- [x] `_redact_context` removes `user_request` from persisted trace to avoid logging potentially sensitive user-supplied text.
- [x] No Phase 12 schema migration required; existing tables (`agent_executions`, `tool_executions`, `case_stage_history`) are reused.

# 13. Supervisor Agent

**Status: Implemented and regression-tested — 2026-10-08.** The authenticated agent endpoint dispatches a bounded, synchronous Supervisor request. It assembles organization- and process-version-scoped context, validates a finite sequential plan, and delegates to at most one each of the Document, Verification, and Workflow Agents. Child executions link to their Supervisor execution through `AgentExecution.parent_execution_id`. The Supervisor cannot call tools directly, recurse, approve, or mutate business state; delegated actions retain each child agent's existing authorization and Tool Gateway path.

Responsibilities:

- [x] Observe bounded, organization-scoped Case and ProcessVersion state.
- [x] Identify work through the validated finite plan and current eligibility checks.
- [x] Choose an allowlisted specialized agent and delegate sequentially, at most once per type.
- [x] Receive and sanitize structured child results with parent-child execution traces.
- [x] Return a bounded `CONTINUE`, `ESCALATE`, `COMPLETE`, or `NEEDS_INFORMATION` decision.
- [x] Stop safely on invalid plans, stale context, timeout, or child failure.

Architecture:

```text
Supervisor
 ├── Document Agent
 ├── Verification Agent
 └── Workflow Agent
          ↓
        Tools
          ↓
     Verifia Core
```

### Definition of Done

- [x] Supervisor can inspect bounded Case state.
- [x] Supervisor can delegate through existing child-agent services.
- [x] Supervisor can interpret results and return a coordination decision.
- [x] Supervisor can stop or escalate safely.
- [x] Supervisor cannot bypass controls; no direct tool or business-state mutation path exists.

- [x] Pending document-review tasks and approvals block workflow delegation, including on later coordination runs.
- [x] Latest verification status is selected per configured check; truncated context is disclosed and cannot authorize delegation.

Verification evidence: `backend/tests/test_supervisor_agent.py` — 16 passed. Full backend regression after Phase 12–13 hardening — 144 passed, 5 opt-in live integration checks skipped. Python compilation passed; Ruff reports 0 findings across the reviewed agent, workflow, and test files. Alembic reports `0007_agent_execution_parent` as the head; applying it to a live PostgreSQL database remains an environment check.

---

# 14. Model Gateway

Model selection is deliberately sequenced after each agent's responsibilities and structured input/output contracts are implemented. Phases 12 and 13 use injected fake adapters for repeatable behavior and safety tests; do not make or claim per-agent model-quality decisions from those tests. Phase 14 may run live API connectivity and structured-output smoke checks. Comparative quality evaluation belongs to Phase 23, using stable, agent-specific evaluation cases.

Architecture:

```text
Agent
 ↓
Model Gateway
 ├── Configured API Provider
 └── Additional providers when selected and evaluated
```

Implement:

- [x] Common model interface (`JsonModelAdapter`, `BaseProviderAdapter`, `ModelUsage`, `ModelResponse`).
- [x] Adapter for the selected API provider (`GroqJsonAdapter` with multi-key failover).
- [x] Provider/model selection configuration without fixing a model per agent (`ModelGateway.get_adapter`, `GeminiJsonAdapter`, `OllamaJsonAdapter`, `OpenAICompatibleJsonAdapter`, `FakeJsonModelAdapter`).
- [x] Timeout handling (`ModelTimeoutError`, configurable `timeout_seconds`).
- [x] Retry handling (exponential backoff on transient HTTP 408/429/5xx and network dropouts).
- [x] Error handling (`ModelGatewayError`, `ModelAuthenticationError`, `ModelRateLimitError`, `ModelTimeoutError`, `ModelOutputFormatError`, `ModelProviderUnavailableError`).
- [x] Usage logging (`ModelUsage` capturing prompt/completion/total tokens and latency).

Workflow and Supervisor contracts are now implemented and use the existing adapter interface. Phase 14 may perform live API connectivity and structured-output smoke checks; dedicated model selection and comparative model-quality evaluation remain separate work, with quality evaluation scheduled for Phase 23. Do not assume Gemini or local inference as a project requirement; neither is currently selected. The Verification Agent currently uses the configured JSON adapter as a runtime baseline, but no live Verification model evaluation has been completed.

### Definition of Done

- [x] Agents use one model abstraction.
- [x] Providers are configurable.
- [x] Provider-specific logic is isolated.
- [x] Model failures are handled safely.
- [x] Live API smoke checks confirm connectivity and structured-output handling; they do not claim agent quality.
- [x] Keep comparative agent-quality selection out of Phase 14; it is explicitly scoped to Phase 23 after stable agent contracts and evaluation sets exist.

Verification evidence: `backend/tests/test_model_gateway.py` — 19 passed; `backend/tests/test_external_model_adapters.py` — 8 passed. Full backend regression suite — 163 passed, 5 opt-in live integration checks skipped (0 failures).

---

# 15. Case Orchestrator

Runtime contract:

- Trusted domain services dispatch after persisting events; the public `POST /events` endpoint records events only and cannot trigger orchestration.
- `CASE_ORCHESTRATION_ENABLED` is the operational kill switch. Document upload routes pass their storage adapter into synchronous orchestration.
- Successful and human-wait outcomes are recorded as `ORCHESTRATION_RESULT` events. Sequential duplicate delivery is skipped; failed trusted events can be reloaded with `CaseOrchestrator.resume_event(event_id)` and replayed.
- This phase does not add a background queue or guarantee cross-process exactly-once execution. The persisted event log and outcome records support explicit resumption; worker scheduling and distributed coordination remain future operational work.

Event-driven flow:

```text
CASE_CREATED
    ↓
Supervisor
    ↓
Document Agent
    ↓
DOCUMENT_PROCESSED
    ↓
Verification Agent
    ↓
Deterministic Tools
    ↓
VERIFICATION_COMPLETED
    ↓
Workflow Agent
    ↓
Workflow Engine
    ↓
New Case State
```

Implement handlers for:

- [x] Case created.
- [x] Document uploaded.
- [x] Document processed.
- [x] Verification started.
- [x] Verification completed.
- [x] Task created/completed.
- [x] Approval completed.
- [x] Workflow transition.
- [x] Case completed.

Also implement:

- [x] Retry behavior.
- [x] Failure handling.
- [x] Duplicate-event handling.
- [x] Traceability between events and agent/tool executions.

### Definition of Done

- [x] Events trigger correct work.
- [x] A Case can progress without manual DB manipulation.
- [x] Failures do not silently corrupt state.
- [x] Agent activity is traceable.

---

# 16. Human-in-the-Loop

Runtime contract:

- Internal users work review tasks through organization-scoped task APIs. Managers and administrators assign tasks and decide approvals; employees can claim unassigned tasks and resolve tasks assigned to them.
- Review comments are immutable records with validated same-case evidence links. Resolution records the outcome, comment, evidence, user and timestamp before trusted orchestration runs.
- `GET /cases/{case_id}/review` returns the case review packet: tasks and comments, approval requests, documents and extracted fields with citations, processing review reasons, verification results, evidence, discrepancies, and bounded agent recommendations. It never exposes storage references; document bytes remain behind the authenticated download endpoint.
- Approval rejections leave the case in `PENDING_REVIEW`; approvals and task resolutions are audited and emitted as events. This phase provides review APIs and data; the frontend remains Phase 18.

## Review Tasks

Support:

- [x] Document review.
- [x] Verification review.
- [x] Exception review.
- [x] General review.

Implement:

- [x] Assignment.
- [x] Status.
- [x] Comments.
- [x] Evidence links.
- [x] Completion.

## Review Screen Data

Human sees:

- [x] Case information.
- [x] Relevant documents.
- [x] Extracted fields.
- [x] Verification result.
- [x] Evidence.
- [x] Discrepancy.
- [x] AI interpretation/recommendation.

## Approval

Manager sees:

- [x] Case summary.
- [x] Verification results.
- [x] Evidence.
- [x] Outstanding issues.
- [x] AI recommendation.
- [x] Approve/reject controls.

Record:

- [x] Decision.
- [x] User.
- [x] Timestamp.
- [x] Comment.
- [x] Event.
- [x] Audit record.

### Definition of Done

- [x] AI can stop and request human action.
- [x] Human can inspect evidence.
- [x] Human decision is recorded.
- [x] Workflow reacts to the decision.
- [x] Audit trail identifies who/when/why.

---

# 17. Complete Import/Export Near-Real Evaluation

Implementation note (2026-10-09): the declarative process template is published. A repeatable authenticated API evaluation exercised all ten synthetic scenarios against live ERPNext inventory/payment records. All ten expected workflow outcomes matched; ten invalid transitions returned HTTP 400 and ten unauthorized customer tool calls returned HTTP 403. The LLM7 Document Agent sample gate passes. See `workflow_security_20261009.json`.

Example:

```text
Import Order #1042
```

Documents:

- [x] Purchase Order.
- [x] Commercial Invoice.
- [x] Packing List.

Complete:

- [x] Create Case.
- [x] Assign ProcessVersion.
- [x] Set initial stage.
- [x] Upload documents.
- [x] Process documents.
- [x] Extract fields.
- [x] Verify document completeness.
- [x] Compare PO and Invoice.
- [x] Calculate totals.
- [x] Check inventory.
- [x] Check payment status.
- [x] Record evidence.
- [x] Detect discrepancy.
- [x] Create review task.
- [x] Employee resolves issue.
- [x] Workflow Agent proposes next action.
- [x] Workflow Engine validates.
- [x] Request manager approval.
- [x] Manager approves.
- [x] Move to shipping.
- [x] Complete Case.

### Definition of Done

- [x] Clean approval/completion and discrepancy/review/rejection Cases have run through authenticated application interfaces with no direct database edits; the dated run traces are recorded. The ten-scenario outcome/security evaluation remains open.
- [x] Required provider-backed tools, labeled evaluation data, and quality results satisfy the Phase 17 closeout gates or have explicit agreed deferrals. The synthetic data, separate OCR/retrieval/document/rule results, and ten-scenario API evaluation are recorded with limitations.
- [x] No manual database edits were used to create or advance the clean or discrepancy demonstration Cases.

## Phase 17 Closeout Subplan

This work upgrades the existing Import/Export example into a repeatable,
near-real evaluation of the generic Verifia platform. The fictional company is
an evaluation fixture, not a claim to reproduce any real company's internal
policies. Keep business rules, process stages, document schemas, and tool
permissions in configuration; keep executable integrations in trusted adapter
code. Do not begin Phase 18 until the final closeout gate passes.

### 17.1 Establish a Reproducible Evaluation Environment

- [x] Start the configured PostgreSQL service and verify the application can connect (PostgreSQL 16.15).
- [x] Apply migrations through the current head and record the applied revision (`0008_human_review_comments`).
- [x] Verify pgvector 0.8.6, vector dimensions, HNSW index, and a real ranked query against PostgreSQL; the labeled policy retrieval run is recorded in `data/phase17_evaluation/reports/retrieval_20261008.json`.
- [x] Verify local object storage and Tesseract; the live SROIE OCR check passed.
- [x] Verify configured Groq and Cloudflare API calls without exposing keys in output, logs, or tracked files. The three-document Groq smoke result and environment details are recorded in `data/phase17_evaluation/reports/`.
- [x] Obtain a clean full backend regression run using `python scripts/run_backend_regression_windows.py`; it passes, skips six opt-in live checks, and excludes the inaccessible stale `tests/_pytest_phase15` temporary directory. See `environment_20261009.json`.
- [x] Record software versions, environment prerequisites, and the exact regression command in `data/phase17_evaluation/reports/environment_20261009.json`.

**Gate:** database, migrations, storage, OCR, model, embedding, and the full default test suite have verifiable results. A provider check that was skipped or could not connect is recorded as unverified, not passed.

### 17.2 Define the Fictional Company and Evaluation Data Pack

- [x] Define one fictional importer profile, its roles, supplier/item identifiers, currency, and operating assumptions.
- [x] Label company policies as fictional. No jurisdiction-specific rules are evaluated; jurisdiction is intentionally unset.
- [x] Create matched Purchase Order, Commercial Invoice, and Packing List bundles with saved expected field values and expected workflow outcomes.
- [x] Include clean cases and controlled variations for missing documents, quantity/total/currency mismatches, a low-quality scan, inventory shortage, unpaid/part-paid invoice, and approval rejection.
- [x] Add a compact fictional policy corpus and 12 labeled questions with expected supporting sources.
- [x] Select and acquire the official DocLayNet ICDAR 2023 20-page development set for OCR/layout evaluation. Its archive includes an Apache-2.0 license; the source archive is stored outside Git under `data/phase17_evaluation/external/`, with checksum and results in `doclaynet_ocr_20261009.json`. This general layout sample does not replace trade-document field evaluation or DocILE research access.
- [x] Keep a dataset manifest with provenance, synthetic status, split, and expected labels. No external dataset is redistributed.
- [x] Keep evaluation examples separate from prompt examples and tuning examples to reduce leakage.

**Gate:** the data pack is reproducible, labeled, and sufficient to evaluate each target without representing synthetic results as real-company data.

### 17.3 Complete the Generic Process Configuration

- [x] Configure document classes and extraction schemas for the three required trade-document types.
- [x] Configure deterministic rules/calculations for required fields, cross-document quantities, line totals, and currency-aware totals in the scenario.
- [x] Link configured rules to verifications and configure expected evidence and review behavior.
- [x] Configure required-document checks, stage requirements, approval gates, and transitions in the ProcessVersion.
- [x] Extend the JSON publisher to load the scenario configuration, including rules, calculations, and verification links; reject invalid references before publishing.
- [x] Verify a published version is immutable and the Case records the selected version in focused loader tests.

**Gate:** the same application code can run the scenario from process data; Import/Export behavior is not hidden in a special-case application path.

### 17.4 Implement and Configure Real Provider Tools

- [x] Select ERPNext/Frappe as the ERP provider and install the local self-hosted demo (`frappe/erpnext:v16.50.0`); create the fictional Northstar company. ERPNext requires a country to initialize its chart and fixtures, so the demo uses United States for ERP setup only; jurisdiction-specific rules are not evaluated.
- [x] Define and exercise secure configuration using organization-scoped ERP/FINANCE integration records and environment-variable secret references; API credentials are stored only in the ignored root `.env`, never in process JSON or tool execution data.
- [x] Define `check_inventory` inputs for item/SKU, requested quantity, and warehouse; return structured available/reserved quantities and a decision.
- [x] Define `get_payment_status` mapping and structured unpaid/part-paid/paid/unknown results with outstanding amount and currency where available.
- [x] Implement the trusted asynchronous ERPNext adapter behind the Tool Gateway, with organization scoping, timeouts, bounded retries, safe errors, output validation, and auditable execution integration.
- [x] Cover successful/missing records, insufficient stock, payment statuses, provider failure, and safe authorization errors in adapter tests. Live adapter checks against ERPNext verified available/insufficient inventory and paid/partially-paid/unpaid/missing invoice results. Live Tool Gateway calls are verified in the clean case; timeout and malformed-provider responses remain adapter-test-only.
- [x] Keep provider-specific field mapping in the adapter/configuration boundary; the ERPNext adapter maps provider records to stable gateway outputs and process JSON only maps business inputs.

**Gate:** passed for configured inventory and payment calls in the clean case. Live malformed-provider and timeout responses remain covered by adapter tests, not by a deliberately fault-injected ERPNext server.

### 17.5 Run the Complete Case Through Application Interfaces

- [x] Create the Case and select the published ProcessVersion through application services/API; clean case `CASE-20261008-5814` used version `3fe6f747-07d7-4214-976c-82fdba1143b6`.
- [x] Upload and process the three source documents through storage and the document-processing pipeline in the clean case.
- [x] Run extraction, configured document/rule checks, inventory, and payment checks; the clean case records three verification executions and live inventory/payment results.
- [x] Confirm source citations, verification results, evidence, and workflow events are visible in the authenticated case review bundle; the clean case has three evidence records and 29 events.
- [x] Trigger the intentional business discrepancy through the live API using the synthetic invoice-quantity-mismatch case. All three documents were processed with Kilo Dots3 Note Preview; deterministic order consistency returned `FAIL` with one evidence record and the case entered `HUMAN_REVIEW`. The API run passed, but this three-document run is a workflow smoke test, not a comparative document-quality score.
- [x] Resolve the mismatch as an employee and record a manager decision. An evidence-linked employee review task was completed; the manager rejected shipment and the case correctly remained held at `MANAGER_APPROVAL` / `PENDING_REVIEW`. Rejection is the expected safe outcome for this fixture; the clean case separately demonstrates completion after approval.
- [x] Exercise a clean completion through the application interfaces. The persisted state is `COMPLETED`, with 3 documents, 3 verifications, 3 evidence items, and 0 open tasks.
- [x] Exercise the discrepancy/review rejection path through the application interfaces. The case is intentionally held after the manager rejects; the separate clean case covers `COMPLETED`.
- [x] Exercise provider-failure, denied-action, and rejected-approval safety behavior; the provider failure held the case at `DOCUMENT_REVIEW`, customer tool access returned 403, rejected-approval/missing-required-document behavior is covered by passing workflow/HITL tests, and the invalid backward transition returned 400.
- [x] Use no direct database edits to create or advance the demonstration cases.

**Gate:** the Case can be reconstructed from its application records, evidence, tool traces, events, and audit history, including why it stopped or advanced.

### 17.6 Measure Quality and Record Limitations

- [x] Meet the document-agent held-out sample thresholds on one fixed provider/model. LLM7 `gpt-oss:20b` evaluated 20 of 29 documents with 1.00 classification accuracy, 0.9712 required-field exact match over 104 labeled fields, and 1.00 citation validity across 300 citations. The 101 exact-match non-null fields necessarily carry citations under the document validation rule, exceeding the 30-field minimum. Nine documents failed (5 `ModelGatewayError`, 4 `ModelOutputFormatError`), but the minimum successful sample thresholds are met. See `document_agent_llm7_20261009.json`. Earlier Groq results remain recorded separately and did not meet the sample minimum. Kilo Gateway is configured but has not been live-tested.
- [x] Score OCR quality on five generated, labeled scan pages through Tesseract: normalized token recall 0.9761; see `data/phase17_evaluation/reports/ocr_20261008.json`. This is controlled synthetic-page evidence, not a real-world OCR benchmark.
- [x] Score policy retrieval using labeled queries and a recorded top-k relevance measure: recall@3 1.00 and MRR 0.958 over 12 queries (small synthetic corpus; see dated report).
- [x] Score the configured deterministic rules against labeled gold fields across the ten scenarios: **69/69 rule decisions matched** across the seven configured checks (with inapplicable missing-document checks excluded); see `rule_diagnostics_20261009.json`. This isolates the rule engine from extraction and provider errors.
- [x] Score final workflow action selection and case outcomes across all ten scenarios. All ten expected outcomes matched through authenticated application APIs: one clean completion, six discrepancy holds, one required-document hold, one low-quality scan held for human inspection, and one manager rejection. Its OCR score is recorded separately. See `data/phase17_evaluation/reports/workflow_security_20261009.json`.
- [x] Confirm zero unauthorized tool executions and zero invalid workflow transitions across the ten-scenario evaluation set. Each case had one customer tool attempt, denied with HTTP 403, and one invalid transition attempt, rejected with HTTP 400; observed successful unauthorized executions and accepted invalid transitions were both zero. See the dated workflow/security report.
- [x] Record run completion, provider failures, latency, and model/provider identity where available. Groq token usage is not returned by the current adapter, so token counts cannot be reported.
- [x] Agree on initial acceptance thresholds before interpreting scores; `acceptance_thresholds.json` defines them and reports include sample sizes and limitations.
- [x] Save repeatable evaluation commands and dated results without storing secrets or redistributing source data. Commands are documented in the Phase 17 closeout report and reports are saved under `data/phase17_evaluation/reports/`.

**Gate:** results can be rerun and compared; measured accuracy is not inferred from one clean demo case.

### 17.7 Phase 17 Closeout

- [x] Complete every Phase 17 checklist item above or record an explicit, agreed reason for any deferred item. The synthetic-data limitation, DocILE access limitation, and non-production ERPNext fixture scope are recorded; all required Phase 17 evaluation gates have passing evidence.
- [x] Update this checklist and `Documentation/progress_report.md` with the environment, data, provider routing, verified results, and remaining limitations.
- [x] Run the full backend regression after the implementation changes: **209 passed, 6 opt-in live checks skipped, 0 failures**. Repeatable Windows command: `python scripts/run_backend_regression_windows.py`. The runner handles this host's pytest temp-directory ACL issue without changing application behavior; it excludes inaccessible stale `tests/_pytest_phase15` data. One upstream Starlette TestClient deprecation warning remains.
- [x] Confirm process configuration and the clean end-to-end run require no manual database edits; both publication and the completed case used application services/API.
- [x] Confirm the Phase 17 exit gate permits Phase 18 to begin: all Phase 17 gates and its Definition of Done are satisfied. Frontend implementation itself remains Phase 18 work.

**Decisions recorded:** ERPNext/Frappe is the selected ERP adapter target and is running locally with organization-scoped integration credentials; secrets remain in ignored `.env`. The synthetic Import/Export pack remains the primary business-extraction corpus. The official DocLayNet 20-page development sample is selected only for OCR/layout evaluation; its downloaded archive contains an Apache-2.0 license and is excluded from Git. DocILE access is still unavailable. No jurisdiction-specific legal/customs policy is evaluated, so the fictional company profile leaves jurisdiction unset. Initial thresholds are in `data/phase17_evaluation/acceptance_thresholds.json`. Per-agent provider routes are configurable: Document baseline LLM7 `gpt-oss:20b`, Verification Groq Qwen 3.8 27B, Workflow Kilo Dots3 Note Preview Free, and Supervisor Groq Qwen 3.8 27B. These are not comparative winners; role-specific model selection remains Phase 23. Provider throttling and authentication failures remain recorded limitations, not quality claims. The Document Agent minimum sample gate and the ten-scenario workflow/security gates pass on the recorded synthetic evaluation. Phase 17 is **closed** for its stated near-real evaluation scope; this does not assert production readiness or generalization beyond the tested data and ERPNext fixture.

**Audit follow-up — 2026-10-10:** The historical Phase 17 closeout above records results obtained when its local threshold file was available. `data/phase17_evaluation/acceptance_thresholds.json` is ignored, absent from this checkout and its Git history, and the user does not have a copy. The current suite therefore cannot reproduce the document-agent acceptance gate. Keep the historical result as historical evidence, but mark the Phase 17 gate **BLOCKED / not reproducible in this checkout** until the original thresholds are restored. Do not infer replacement values from the reported metrics. Phase 27 task T27-07 records the owner-approved recovery/replacement decision path without changing this historical closeout.

---

# 18. Frontend

**Status:** Internal and customer frontend flows implemented on 2026-10-10. See [frontend implementation plan](frontend-implementation-plan.md), [frontend and Phase 19 review](frontend-and-phase19-review.md), and the [progress report](progress_report.md). Customer endpoints return only cases linked to the authenticated customer.

## Customer

- [x] Login through a backend-provisioned account.
- [x] Customer case workspace and case actions use participant-scoped API endpoints.
- [x] Create Case from an organization-active, published process option.
- [x] Case list contains only the authenticated customer's linked cases.
- [x] Case details return the customer-safe case projection.
- [x] Upload documents to a linked, open case.
- [x] Show document upload status and latest version metadata.
- [x] Show case status from backend state.
- [x] Show required document requests from the published process and support customer uploads.

## Employee

- [x] Task list.
- [x] Assigned tasks from the authenticated `/tasks/my` API.
- [x] Case details for internal operators.
- [x] Inline PDF/image preview for supported types using authenticated document downloads; other types remain downloadable.
- [x] Extracted fields.
- [x] Verification results.
- [x] Evidence.
- [x] Resolve permitted task with a comment and selected evidence, using the backend response.

## Manager

- [x] Approval list.
- [x] Case summary.
- [x] Evidence.
- [x] Verification history.
- [x] Approve.
- [x] Reject.
- [x] Require a comment.

### Definition of Done

- [x] Customer can create, list, open, and upload to linked cases through participant-scoped APIs.
- [x] Employee can review assigned work through the internal case workspace.
- [x] Manager can approve/reject with a required reason.
- [x] Frontend communicates through the backend API client only.
- [x] UI reflects backend-returned Case state.
- [x] Role-aware navigation uses authenticated APIs; the backend remains the permission authority.
- [x] Loading, empty, pending, and API-error states are provided for case and task workflows.

Automated frontend verification: **21 tests passed across 10 files**; typecheck, lint, and production build pass. On 2026-10-11 the rebuilt Docker frontend and backend started successfully, the browser login page loaded without console warnings/errors, and Nginx's `/health/backend` proxy returned API healthy/Redis connected. Compose reported the PostgreSQL and Redis containers healthy. Authenticated customer/internal business-flow E2E remains unverified; see the Phase 20 plan for runtime details.

---

# 19. Authentication & Authorization

Implement:

- [x] Authentication.
- [x] JWT/session handling (expiry and token-version revocation; no refresh-token endpoint is defined).
- [x] User identity.
- [x] Organization identity.
- [x] Server-side role checks.
- [x] Server-side authorization on protected API operations; frontend role gates are only navigation UX.
- [ ] Replace public self-registration with controlled tenant/user provisioning; callers must not choose their organization, privileged role, or active status.
- [x] Define account lifecycle, password change/reset policy, access-token expiry/revocation, and development-only administrator bootstrap. Refresh tokens are not implemented; bearer tokens remain in per-tab session storage.

Test:

- [x] Cross-organization access denied.
- [x] Customer cannot approve.
- [x] Employee cannot perform manager-only approval.
- [x] Agent cannot use unauthorized tool.
- [x] Agent cannot directly modify workflow.
- [x] Users cannot access unauthorized documents.
- [x] Anonymous users cannot self-register into an existing tenant or create privileged/active accounts; the public route is retired and provisioning requires an authenticated organization ADMIN.
- [x] Role/organization fields supplied or altered by a caller cannot elevate access; provisioning derives organization and activation server-side, allows only CUSTOMER/EMPLOYEE/MANAGER, and `/auth/me` rejects stale role/organization claims.
- [x] Logout, self-service password change, and administrator password reset increment the target user's token version so prior access tokens fail validation; credential lifecycle events are audited without password material.
- [x] Local first-admin setup requires a development environment, a user-chosen password of at least 15 characters, hidden input and confirmation; it does not accept a password command-line argument or reset existing accounts.
- [x] Route authorization is enforced server-side for customer/internal resources, employee tasks, manager approvals, and administrator provisioning; Phase 18/19 security regression tests cover negative role and cross-tenant access paths.
- [x] Apply migrations through `0010_user_token_version` to the supported PostgreSQL stack. The current local Compose database is at migration head `0011_durable_event_deliveries`; this does not verify production database operations.

### Definition of Done

Every protected operation checks identity, organization and permission. Provisioning tests prove that unauthenticated or low-privilege callers cannot create accounts in another organization, assign privileged roles, or activate accounts.

---

# 20. Security

Phase 20 controls have local implementation and test evidence, but provider approval and production deployment evidence remain incomplete. The latest full backend regression recorded in this audit passed 277 tests, skipped 7, and had no failures. Six skips are opt-in live-provider checks; the seventh is the blocked Phase 17 threshold file. Fresh Docker-backed worker/readiness probes passed on 2026-10-13; they do not close Phase 20's production/provider evidence gaps. See the [official Phase 20–21 compliance audit](phase20-21-official-compliance-audit.md), [requirement matrix](phase20-21-official-compliance-matrix.md), and [Phase 20 implementation plan](phase20-production-security-implementation-plan.md).

## Data

- [x] Organization isolation (covered by tenant-scoped service and route tests; exhaustive cross-tenant coverage across every resource remains a Phase 22 test item).
- [x] Case-level authorization.
- [x] Document authorization.
- [x] Tool authorization.
- [x] Secrets outside source code.
- [x] No provider API keys found in tracked source; see current audit evidence.
- [x] Production startup fails closed when the secret key is weak/default, debug mode is enabled, CORS is wildcard, or required production settings are absent. Production/staging also reject `ALLOW_UNSCANNED_UPLOADS=true` until a scanner is configured.
- [x] Define a narrow CORS allowlist and production API/docs exposure policy.
- [x] Review upload limits, file-type validation, malware/content handling, and storage access controls. Size/signature/MIME checks are implemented; no malware scanner exists, and unscanned production uploads stay disabled.

## AI

- [x] Uploaded documents are untrusted data.
- [x] Document content cannot override system instructions in the agent contract; this is a defense-in-depth prompt/schema control, not a guarantee against every prompt injection.
- [x] Prompt-injection defenses, with the same limitation above.
- [x] Least-privilege tools.
- [x] Structured tool arguments.
- [x] Structured tool outputs.
- [x] No agent-exposed arbitrary SQL tool.
- [x] No agent-exposed unrestricted shell execution.

## External Models

- [x] Define data allowed to leave the system: synthetic or otherwise non-sensitive evaluation content only until an exact provider/model route receives documented approval.
- [x] Define data that must remain local: real customer documents and extracted content, personal/financial records, credentials, secrets, and confidential case data until approval and tested minimization/redaction.
- [x] Keep provider policy configurable and deny unapproved production/staging routes by default.
- [x] Use synthetic/non-sensitive test and evaluation data for unapproved routes.
- [ ] Record provider retention/training terms and implement redaction/minimization before sending business content externally. Providers remain unreviewed and field-level redaction is not implemented.
- [x] Define configured timeout/retry/rate-limit/fail-safe behavior by agent route in the provider review register. Ollama and embedding adapters intentionally have timeout-only failure behavior; no automatic vendor failover is claimed.

---

# 21. Events & Auditability

Case history should reconstruct:

```text
Case Created
↓
Document Uploaded
↓
Document Processed
↓
Verification Started
↓
Verification Completed
↓
Task Created
↓
Task Completed
↓
Approval Requested
↓
Approval Granted
↓
Workflow Transitioned
↓
Case Completed
```

- [x] Centralize event creation through `EventService.add_event` and `EventService.emit_event`, including domain events that must share a transaction with their business-state changes.
- [x] Retrieve Case event history through the authorized, tenant-scoped case event route.
- [x] Retrieve authorized audit history through the organization-scoped ADMIN audit route.
- [x] Timestamp every event through the shared event model's creation timestamp.
- [x] Identify actor/source using the event's actor type and optional actor ID.
- [x] Link tool executions where appropriate: verification-completion events carry the validated tool-execution IDs used for that verification.
- [x] Define durable delivery, retry/dead-letter handling, persisted-result idempotency, and duplicate-event behavior across expired leases and multiple workers. Delivery is at least once; see the Phase 21 closeout for the external-side-effect limit.
- [x] Provide `/livez` and dependency-aware `/readyz` signals for API liveness and PostgreSQL/Redis availability. The Phase 21 requirement does not define a worker heartbeat; worker process status/logs can be inspected through Compose, but Compose has no worker healthcheck.

### Definition of Done

- [x] Case history can reconstruct what happened from start to completion in the isolated internal API journey. `backend/tests/test_case_journey_e2e.py` verifies `DOCUMENT_PROCESSED`, `VERIFICATION_STARTED`/`VERIFICATION_COMPLETED`, `TASK_COMPLETED`, `APPROVAL_GRANTED`, workflow, audit history, and persisted completion. It uses disposable SQLite fixtures and deterministic model behavior; real ERPNext and the historical 10-scenario evaluator remain unverified.

### Phase 21 operational delivery verification — 2026-10-11

- [x] Added migration `0011_durable_event_deliveries` and applied it to the running local PostgreSQL database without changing existing user/event records.
- [x] Added the PostgreSQL-backed worker to both local and production Compose profiles; local Compose supports multiple worker replicas.
- [x] Added bounded retry/backoff, five-attempt dead-letter handling, expired-lease recovery, lease-token fencing, and an operator replay command for trusted failed/interrupted events.
- [x] Added isolated delivery/readiness unit and HTTP tests; live Compose E2E completed a fresh delivery on attempt 1 and expired-lease recovery on attempt 2 across two running workers, each with one persisted orchestration result. Both probes cleaned up their temporary organization.
- [x] Applied readiness checks to the backend healthcheck and frontend Nginx health proxy.
- [x] A new isolated authenticated internal Case journey passed through completion; this closes the internal event-history lifecycle check. Real ERPNext and the separate 10-scenario Phase 17 evaluator remain unverified because ERPNext is unavailable and that evaluator persists test cases in its configured database.

### Official compliance audit update — 2026-10-11

- [x] Aligned raw lifecycle rows with the checklist taxonomy: document processing emits `DOCUMENT_PROCESSED`; task resolution emits `TASK_COMPLETED` or `TASK_REJECTED`; approval decisions emit `APPROVAL_GRANTED` or `APPROVAL_REJECTED`. Older event aliases remain accepted by orchestration.
- [x] Kept Case, approval, and task changes in the same transaction as their domain event/outbox write. Eight failure-injection tests prove state rolls back when event insertion fails.
- [x] The full backend regression passed **262**, skipped **7**, failed **0**. A process-only bcrypt 4.x behavior shim was used because the host has bcrypt 5.0.0 while the project pins bcrypt below 4.1; no application code or installed dependency was changed for the shim.
- [x] Re-run Docker-backed worker/readiness probes on 2026-10-13: migration head `0011_durable_event_deliveries`; `/livez` and `/readyz` HTTP 200; stale-claim fencing passed; normal delivery completed with one attempt and zero duplicates; expired-lease recovery completed with two attempts and zero duplicates. The tests used temporary synthetic rows and cleaned them up. PostgreSQL-specific transaction rollback remains separately unverified.

---

# 22. Testing

## Unit Tests

- [x] Calculations (`test_rules_and_verifications.py`).
- [x] Rules (`test_rules_and_verifications.py`).
- [x] Workflow (`test_workflow_engine.py`, `test_workflow_agent.py`).
- [x] Permissions (`test_human_review.py`, `test_workflow_agent.py`, and tool authorization tests).
- [x] Case service (`test_domain_services.py`, `test_case_journey_e2e.py`).
- [x] Document validation (`test_document_upload.py`, `test_document_intelligence.py`).
- [x] Verification statuses (`test_rules_and_verifications.py`, `test_verification_agent.py`).
- [x] Approval logic (`test_domain_api.py`, `test_human_review.py`, `test_case_journey_e2e.py`).
- [x] Tool authorization (`test_modules.py`, `test_verification_agent.py`, `test_workflow_agent.py`).

## Integration Tests

- [x] API → DB (isolated API/database fixtures and transaction rollback tests; PostgreSQL migration validation is tracked separately below).
- [x] API → Storage (local round-trip and API storage outage tests).
- [x] Tool Gateway → Tool.
- [x] Verification → Rules.
- [x] Agent → Tool Gateway.
- [x] Workflow → Case.

## End-to-End

```text
Create Case
→ Upload
→ Process
→ Extract
→ Verify
→ Detect Issue
→ Review
→ Resolve
→ Approval
→ Complete
```

## Failure Tests

- [x] Missing document.
- [x] Invalid document.
- [x] Low-confidence extraction.
- [x] Calculation failure.
- [x] Verification mismatch.
- [x] Unauthorized user.
- [x] Unauthorized tool.
- [x] Invalid transition.
- [x] Model timeout.
- [x] Model failure.
- [x] Tool failure.
- [x] Duplicate event.
- [x] Database/Redis unavailable during startup and during an in-flight workflow. A real asyncpg and Redis client test connects to closed loopback ports: startup remains live, `/readyz` reports 503, `/livez` reports 200, and an in-flight Case creation returns a sanitized 503 with PostgreSQL unavailable. Redis is a readiness dependency and is not used by the Case/worker processing path.
- [x] PostgreSQL multi-worker delivery/recovery probes: stale-claim fencing, normal delivery with two Compose workers, and expired-lease recovery passed against Compose PostgreSQL on 2026-10-13. This is local infrastructure evidence, not hosted CI evidence.
- [x] Cross-tenant access attempts for every protected resource family (cases, tasks, documents, evidence associations, events, and tools); evidence is exposed through scoped case/task bundles, not a standalone API.
- [x] Production configuration rejects unsafe defaults.
- [x] Migration from an empty database and upgrade from the prior supported schema to `0011_durable_event_deliveries` passed in the Phase 22 local PostgreSQL verification on 2026-10-12. On 2026-10-13 the running database was confirmed at head; the fresh empty/prior-schema migration was not rerun during this verification.

## Continuous Integration

- [ ] Add CI for linting, the complete backend regression suite, and frontend checks when Phase 18 begins. **Workflow is now implemented in `.github/workflows/quality-gates.yml`; keep unchecked until a hosted run succeeds.**
- [ ] Validate a clean install, migration chain, and production build in CI.
- [x] Keep opt-in provider tests explicitly separated from deterministic regression checks; six live checks remain opt-in and are not enabled by the CI workflow.

**Phase 22 verification note — 2026-10-13:** the full local backend regression passed **277 tests, skipped 7, failed 0** after the hosted dependency-install fix; six skips are opt-in live checks and one is the blocked Phase 17 threshold gate. Fresh Compose PostgreSQL worker and readiness probes also passed. The screenshot-provided hosted run failed before tests because pip ran out of runner disk while installing PyTorch/NVIDIA packages. Those optional local-embedding packages are now separated from standard/CI requirements, and the workflow disables pip caching. A post-fix hosted run is still required; do not check the CI items off until it passes. See the [Phase 22 implementation plan](phase22-implementation-plan.md) for commands and limits.

**Final independent revalidation — 2026-10-12:** after commit `fc4a77b2d1dc1b0218b4fbf0981a1e20bded6af8`, the project-venv backend regression freshly passed **277 tests, skipped 7, failed 0** in **69.05 seconds**; the focused auth/event/upload/readiness/verification group passed **123 tests** and critical Ruff passed. Six live integrations remained skipped; the Phase 17 threshold gate reported the missing original file. The Docker pipe and hosted Actions result remained unavailable. These results supersede the earlier 49.14-second full-suite measurement as the latest local run; PostgreSQL worker results remain historical.

---

# 23. AI & System Evaluation

# 23. AI & System Evaluation

Evaluate each agent independently before evaluating the combined system. For one agent run, keep its evaluation cases, prompt/configuration, and scoring rules fixed; record provider/model identity, successful and failed calls, latency, and any usage data available. Compare candidate providers within that agent's task rather than pooling unlike agent scores. Do not infer end-to-end system quality from an isolated agent score. After agent-level evaluation and selection, run the system-level workflow evaluation below. The Phase 17 Document Agent results are an earlier single-provider baseline, not a comparative model-selection result.

## Document Agent

- [ ] Classification accuracy.
- [ ] Field extraction accuracy.
- [ ] Required-field accuracy.
- [ ] Hallucinated-field rate.
- [ ] Citation/source-locator correctness and unsupported-field rate.
- [ ] Results segmented by document type, scan quality, language/layout where represented.

## Verification Agent

- [ ] Correct verification selected.
- [ ] Correct tool selected.
- [ ] Correct arguments.
- [ ] Correct interpretation.
- [ ] Correct escalation.
- [ ] False accept/false reject rates and safe behavior when evidence or tool results are missing.

## Workflow Agent

- [ ] Correct next action.
- [ ] Valid action format.
- [ ] No unauthorized transition.
- [ ] Correct escalation.
- [ ] Proposal validity, replay behavior, and safe handling of stale case state.

## Supervisor Agent

- [ ] Correct child-agent delegation for the bounded case context.
- [ ] Correct stop, continue, complete, or escalation decision.
- [ ] No delegation when required context is incomplete or review/approval blockers remain.
- [ ] Child execution limits and parent/child trace links are preserved.
- [ ] Provider/model failures stop safely without unauthorized state changes.
- [ ] Delegation quality, bounded call count, latency, and failure recovery are measured independently.

## System

- [ ] Processing time.
- [ ] Human intervention count.
- [ ] Errors detected.
- [ ] False positives.
- [ ] False negatives.
- [ ] Successful completion rate.
- [ ] Provider/model identity, prompt/config version, latency, token/usage data when exposed, rate limits, and failure reasons.
- [ ] Repeated-run variance and cost/throughput bounds for each candidate route.
- [ ] Include licensed or explicitly authorized representative business documents; retain synthetic data as a controlled baseline.

### Definition of Done

- [ ] Evaluation dataset exists.
- [ ] Evaluation procedure is repeatable.
- [ ] Results are recorded.
- [ ] Baseline/comparison is documented where useful.
- [ ] Agent-level results are reported separately from end-to-end workflow results and limitations are explicit.
- [ ] Candidate model/provider selection is justified by task quality, reliability, latency, and available cost/usage evidence; no single provider is assumed to fit every agent.

**Implementation note — 2026-10-12:** a versioned, four-agent synthetic benchmark, shared offline-capable runner, task-level scorers, and safe report metadata are implemented. The focused suite passes **8 tests**; the fake-provider CLI completed four cases × two runs for each of the four agents (32 calls), which verifies harness execution only. The existing Supervisor runtime integration suite also passes **16 tests** for trace, bounds, stale-state, failure, and recovery contracts; this is not per-model comparative evidence. No external provider credentials are configured, so no live candidate comparison or route selection is claimed. The official acceptance boxes above remain unchecked pending live comparative evidence, system-level evaluation, and a licensed or explicitly authorized representative business-document corpus with route/data approval. See the [Phase 23 implementation plan](phase23-implementation-plan.md). Phase 27 adds RAG coverage, dataset breadth, local/hosted readiness, and broader AI baselines; Phase 23 remains the owner for official per-agent comparisons, system evaluation, corpus authorization, and route recommendations.

---

# 24. Generalization Test

Use a second small configuration such as:

```text
Insurance Claim
→ Claim Submitted
→ Document Collection
→ Claim Verification
→ Financial Review
→ Manager Approval
→ Payment
```

Check:

- [x] Same Case model works; the Case binds to the published Insurance Claim ProcessVersion.
- [x] Same Workflow Engine works; the configured six-stage claim path reaches Payment.
- [x] Same Verification Engine works; the configured claim-number rule passes on extracted synthetic evidence and persists its execution.
- [x] Same Document Agent architecture works; the existing document API/pipeline classifies and extracts process-configured claim schemas using a deterministic test adapter.
- [x] Same Tool Gateway works; the registered `check_required_documents` tool is exposed and executed under the process allowlist.
- [x] Same Human Review system works; the financial-review task and manager approval complete through existing APIs.
- [x] Only process configuration, rules, knowledge, documents and domain tools need changing; no insurance-specific application branch or schema migration was added.
- [x] Run the second process through the same API and persistence boundaries, without process-specific application branches; the authenticated synthetic journey is `backend/tests/test_phase24_generalization.py`.

### Definition of Done

- [x] Second process can be represented without creating a second application architecture; the declarative Insurance Claim version and authenticated end-to-end journey pass.

**Phase 24 implementation note — 2026-10-12:** `workflows/insurance_claim/process.json` defines the official stage sequence, process-specific document classes/schemas, deterministic claim-reference rule, requirements, approval, and registered-tool allowlist. The authenticated journey passed through Case creation, upload/classification/extraction, workflow transitions, Tool Gateway execution, verification, task review, manager approval, Payment completion, and Case event history. Focused Phase 24 plus process-loader tests passed **6/6**; the full backend regression passed **277 tests, skipped 7, failed 0**. The test uses fictional synthetic data, isolated storage/database fixtures, and a fake model adapter; it is not evidence of a live insurer integration or production insurance readiness. See the [Phase 24 implementation plan](phase24-implementation-plan.md).

**Fresh Phase 24 verification — 2026-10-12:** the Phase 24 plus process-loader suite was rerun from the project `.venv` and passed **6/6**; the independent authenticated journey, event, authorization, upload, readiness, verification, and gateway group passed **123 tests**; the full deterministic regression passed **277 passed, 7 skipped, 0 failed**. Critical Ruff (`E9,F821`) passed. This fresh run confirms only the synthetic local acceptance described above. Docker-backed worker checks and hosted Actions remain unverified in this session.

---

# 25. Final Documentation

## Architecture

- [ ] System Context.
- [ ] Three-Layer Architecture.
- [ ] Level-1 DFD.
- [ ] Case Processing DFD.
- [ ] Agent Architecture.
- [ ] AI vs Deterministic vs Human.
- [ ] Workflow vs AI Orchestration.
- [ ] Security Architecture.
- [ ] Case Lifecycle Sequence.
- [ ] Database ERD.
- [ ] UML.

## Technical

- [ ] Installation.
- [ ] Environment variables.
- [ ] Database setup.
- [ ] API.
- [ ] Database schema.
- [ ] Agent architecture.
- [ ] Tool architecture.
- [ ] Workflow Engine.
- [ ] Verification Engine.
- [ ] Document pipeline.
- [ ] Security.
- [ ] Testing.
- [ ] Evaluation.

## Demo

- [ ] Explain Import/Export process.
- [ ] Explain Case lifecycle.
- [ ] Explain AI responsibilities.
- [ ] Explain deterministic responsibilities.
- [ ] Explain human responsibilities.
- [ ] Explain evidence.
- [ ] Explain auditability.
- [ ] Explain why agents cannot directly mutate business state.
- [ ] Explain generalization.
- [ ] Record current role-specific model/provider routes, configuration names, fallback behavior, limitations, and evaluation date.
- [ ] Document deployment topology, data retention, backup/restore, migration, secrets, CORS, and production configuration requirements.

---

# 26. Final Demonstration

## Demo Story

```text
1. User creates Import/Export Case
          ↓
2. Documents uploaded
          ↓
3. Document Agent processes them
          ↓
4. Extracted information shown
          ↓
5. Verification Agent starts verification
          ↓
6. Deterministic tools calculate/check
          ↓
7. Discrepancy detected
          ↓
8. Human review task created
          ↓
9. Human resolves discrepancy
          ↓
10. Workflow Agent proposes next step
          ↓
11. Workflow Engine validates
          ↓
12. Manager approval
          ↓
13. Case completed
          ↓
14. Audit history shows the complete trail
```

## Preparation

- [ ] Prepare demo database.
- [ ] Prepare Customer/Employee/Manager users.
- [ ] Prepare sample documents.
- [ ] Prepare process configuration.
- [ ] Prepare knowledge documents.
- [ ] Prepare deterministic tool data.
- [ ] Prepare intentional discrepancy.
- [ ] Run complete demo before presentation.
- [ ] Verify evidence.
- [ ] Verify human review.
- [ ] Verify approval.
- [ ] Verify audit history.
- [ ] Prepare fallback screenshots/video.

---

# 27. AI Research & Evaluation Foundation

**Status:** PLANNED — documentation audit completed 2026-10-17; all implementation and evaluation work below remains not started. See the [Phase 27 plan](phase27-ai-research-evaluation-plan.md) for evidence, priorities, dependencies, and acceptance criteria.

Complete these six workstreams first:

- [ ] **T27-01 — Document Agent quality and adapters:** expand labeled coverage, measure field/citation/review behavior, and compare compatible adapters on the same cases.
- [ ] **T27-02 — RAG quality and retrieval improvements:** define the product boundary, build a retrieval benchmark, and select any chunking/embedding/hybrid/reranking experiments from measured errors.
- [ ] **T27-03 — Supervisor and orchestration quality:** expand measured routing, sequencing, recovery, termination, and escalation scenarios while preserving deterministic authority.
- [ ] **T27-04 — Datasets and evaluation infrastructure:** maintain clean-checkout, versioned manifests, labels, provenance, licensing, splits, and reproducible synthetic fixtures.
- [ ] **T27-05 — Local and hosted model assessment:** record exact model/version, license, structured-output behavior, context, hardware, privacy, usage, and readiness evidence; feed comparisons to Phase 23.
- [ ] **T27-06 — Baseline measurement and evidence-based improvement planning:** establish fixed baselines, analyze failures, and compare future changes on the same cases and metrics.

Additional evidence-backed tasks:

- [ ] **T27-07 — Resolve the Phase 17 threshold gate:** recover the original approved threshold file or obtain owner approval for a versioned replacement; rerun the exact gate. Never infer old values.
- [ ] **T27-08 — Obtain approved representative-data routes:** use Phase 20 P20-OFFICIAL-022 and Phase 23 P23-R007/T23-06 as the owners; do not transfer business documents until provider/data approvals and tested minimization are recorded.
- [ ] **T27-09 — Improve evaluation traceability:** define safe per-invocation provider/model version, prompt/config and dataset/scorer fingerprints, latency, attempts, and available usage metadata; exclude secrets and raw document content.
- [ ] **T27-10 — Add AI-specific adversarial evaluation:** version cases for prompt injection, conflicting evidence, unsupported claims, malformed outputs, safe abstention/escalation, and authorization boundaries.
- [ ] **T27-11 — Correct and measure Document Agent evidence fidelity:** distinguish the actual reason for review and preserve every validated citation locator or explicitly narrow the contract; add focused regression/evaluation criteria in a future implementation task.

**Priority and dependency notes:** Phase 17 threshold recovery and representative business-data approval are P0 prerequisites for those specific acceptance claims; synthetic-only evaluation can continue independently. Phase 23 remains authoritative for live per-agent model comparisons, Supervisor scoring, system-level evaluation, authorized-corpus evaluation, and route recommendations. Phase 25 Final Documentation and Phase 26 Final Demonstration remain separate unchecked deliverables.

### Phase 27 Definition of Done

- [ ] Document, RAG, Supervisor, dataset, model-readiness, and baseline reports contain dated evidence, fixed versions, failures, and limitations.
- [ ] RAG retrieval quality is separated from answer quality, with tenant/document authorization and empty-result behavior evaluated.
- [ ] Model candidate results are comparable per agent; system-level metrics remain separate; no unsupported winner or universal threshold is claimed.
- [ ] Phase 17's missing threshold file has an owner-approved disposition and the applicable gate is reproduced before it is marked passed.
- [ ] Any representative corpus has recorded provenance/license/authorization and an approved route/data class before use.
- [ ] The deterministic, authorization, human-review, and business-rule boundaries remain intact.
- [ ] Roadmap, checklist, progress report, READMEs, and this plan agree. No Phase 27 research or implementation task is marked complete without its evidence.

**Audit record:** [x] Documentation-only repository inspection and backlog integration completed 2026-10-17. This records the audit and planning deliverable only; all Phase 27 implementation, benchmarking, and model-selection tasks above remain unchecked.

---

# Final Dependency Order

```text
Phases 0–17: Backend foundation, agents, controlled orchestration, human decisions,
             and the defined near-real evaluation closeout
        ↓
18. Frontend
        ↓
19. Authentication & Authorization
        ↓
20. Security
        ↓
21. Events & Auditability
        ↓
22. Testing & CI
        ↓
23. AI & System Evaluation / comparative model selection
        ↓
24. Generalization
        ↓
25. Final Documentation
        ↓
26. Final Demonstration
        ↓
27. AI Research & Evaluation Foundation
```

# Project Completion Checkpoints

## M1 — Infrastructure

- [x] Repository works.
- [x] Docker services start.
- [x] FastAPI works.
- [x] PostgreSQL works.
- [x] Redis works.
- [x] Migrations work.

## M2 — Business Foundation

- [x] Database complete.
- [x] Process configuration works.
- [x] Case creation works.
- [x] API works.

## M3 — Deterministic Core

- [x] Workflow Engine works.
- [x] Rules work.
- [x] Calculations work.
- [x] Verification works.

## M4 — Controlled Capabilities

- [x] Tool Gateway works.
- [x] Authorization works.
- [x] Tool execution is audited.

## M5 — Document Intelligence

- [x] Upload works.
- [x] Parsing works.
- [x] OCR works for the currently tested local SROIE and 20-page DocLayNet sample; broader scanned trade-document accuracy remains open.
- [x] Classification works through the configured JSON adapter contract.
- [x] Extraction works through schema-validated, citation-checked contracts.
- [x] Evidence/provenance is persisted with source locators and review-task linkage.

## M6 — AI Layer

- [x] Model Gateway works with configurable role-specific provider routes; comparative model selection remains open.
- [x] Document Agent works.
- [x] Verification Agent works.
- [x] Workflow Agent works within the bounded orchestration contract.
- [x] Supervisor works within bounded delegation and control rules.

## M7 — Complete MVP

- [x] Durable event orchestration works for persisted case execution and history; PostgreSQL outbox delivery/recovery across multiple workers confirmed passing on 2026-10-12: stale-claim fencing (PASS), normal two-worker delivery (attempts=1, duplicate_results=0), and expired-lease crash recovery (attempts=2, duplicate_results=0).
- [x] Human review works through the tested task/evidence flow.
- [x] Approval works through the tested manager decision flow.
- [x] Complete synthetic Import/Export Case works for the Phase 17 scenarios; this is not proof of production readiness.

## M8 — Productization

- [x] Frontend works.
- [ ] Security works.
- [ ] Testing is complete.
- [ ] Evaluation is documented.
- [ ] Second process configuration works.
- [x] Documentation is updated.
- [ ] Final demo is repeatable.

## Phase 19 — Identity and provisioning closeout

- [x] Remove anonymous `/api/v1/auth/register`; require a live ADMIN identity for organization user listing and provisioning.
- [x] Derive organization and active state from the authenticated actor and server policy; reject caller-supplied organization, activation, and ADMIN role fields.
- [x] Add case-insensitive global email uniqueness with a migration preflight for duplicate legacy addresses; ambiguous legacy login fails closed.
- [x] Audit user provisioning atomically without storing passwords, password hashes, or bearer tokens in audit metadata.
- [x] Reject inactive users, inactive organizations, malformed subjects, and stale role/organization claims during login/current-identity validation.
- [x] Add frontend User access for ADMIN only; frontend visibility complements backend authorization and is not the security boundary.
- [x] Replace hardcoded local bootstrap credentials with a development-only interactive first-admin script; it does not reset existing passwords or print the chosen password.
- [x] Update the local guide, frontend setup, roadmap, progress report, and security findings.
- [ ] Exercise the Phase 19 authenticated provisioning flow against the real PostgreSQL/Compose stack. **Partially verified:** migrations through `0011_durable_event_deliveries` are applied to the running database, but a fresh authenticated provisioning E2E was not run in this turn. Focused auth/bootstrap tests are recorded in the dated audit; the current full backend suite's only compatible-run failure is the missing Phase 17 threshold file.

These checkpoints summarize the current baseline and do not override phase-specific definitions of done. Phases 18–19 are implemented subject to their recorded live-browser/provisioning limits; Phase 20 remains partial pending production topology, storage runtime, scanning policy, and provider review; Phase 21's internal event lifecycle and fresh Docker/PostgreSQL worker/readiness probes passed on 2026-10-13, while PostgreSQL-specific rollback and ERPNext integration remain open; Phase 22 local checks pass and the CI dependency disk-space remediation is committed, but the post-fix hosted Actions result remains unverified; Phase 23 evaluation remains in progress; Phase 24's synthetic Insurance Claim generalization test passes; Phases 25–26 remain planned; and Phase 27 is planned after a documentation-only AI gap audit. The Phase 17 historical acceptance gate is blocked by its missing original threshold file. Synthetic-data limits remain explicit.

---

# Core Implementation Principle

> **Don't build the AI first. Build the system that the AI is allowed to operate.**

Practical sequence:

```text
Business State
      ↓
Business Rules
      ↓
Workflow
      ↓
Deterministic Capabilities
      ↓
Documents / Knowledge
      ↓
Controlled Tools
      ↓
Agents
      ↓
Orchestration
      ↓
Human Decisions
      ↓
Complete Business Process
```

Critical boundary:

```text
AI
 ↓
Reason
 ↓
Propose / Request
 ↓
Policy + Permission + Workflow Validation
 ↓
Deterministic Execution
 ↓
Business State
 ↓
Event
 ↓
AI observes the new state
```
