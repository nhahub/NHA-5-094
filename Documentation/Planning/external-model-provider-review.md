# VerifiaAI External Model Provider Review

**Status:** No provider/model route is approved for production business data.  
**Runtime default:** Development/test environments allow configured routes for local evaluation; staging and production deny model requests unless an exact provider/model route is explicitly allowlisted.

This inventory supports Phase 20. A configured API key, endpoint, or model is not provider approval. Until the owner records and approves the applicable terms and data classes, use only synthetic or otherwise non-sensitive content.

## Data classification and current use

Until a provider/model/endpoint route has an approved record below, only synthetic, public, or otherwise non-sensitive evaluation inputs may leave the application. Real customer documents and extracted text, case records, personal identifiers, financial/payment data, credentials, secrets, and confidential business data remain local. The current allowlist controls which route can be called; it does not classify fields or redact payloads. Therefore, an allowlisted route is not permission to send real case data unless its approval record explicitly covers that data class and tested minimization/redaction behavior.

## Runtime enforcement

The backend uses:

- **EXTERNAL_MODEL_DATA_POLICY=deny** to disable all model and remote embedding requests.
- **EXTERNAL_MODEL_DATA_POLICY=allowlist** with exact entries in **EXTERNAL_MODEL_ALLOWED_ROUTES**, formatted as `provider:model|https://endpoint-origin`.
- An omitted policy defaults to allow in development/test and deny in staging/production.
- Local embedding mode remains local. Ollama is treated as a route that must be explicitly approved outside development because its configured URL can point to another host.

For example, an operator who has reviewed and approved one exact route can configure:

    EXTERNAL_MODEL_DATA_POLICY=allowlist
    EXTERNAL_MODEL_ALLOWED_ROUTES=["groq:qwen/qwen3.8-27b|https://api.groq.com"]

That allows the approved provider/model at that exact endpoint origin to receive the content passed by its application caller. The runtime compares the configured endpoint's scheme, hostname, and port against the origin in the allowlist; it does not pin the URL path. Keep provider keys and endpoint paths under operator control, and re-review any path change. It does not perform field-level data classification or redact names, financial data, or document contents. Therefore the allowlist must stay empty until the operator accepts the full payload's data handling for that route. Approval of an origin is not approval of provider terms or arbitrary custom hosts.

## Configured timeout, retry, and failure behavior

Agent providers are independently selected through `DOCUMENT_MODEL_PROVIDER`, `VERIFICATION_MODEL_PROVIDER`, `WORKFLOW_MODEL_PROVIDER`, and `SUPERVISOR_MODEL_PROVIDER`. Current defaults are LLM7, Groq, Kilo, and Groq respectively. These are development/configuration defaults, not provider approvals. The behavior below is the current adapter behavior, not an SLA; production changes require re-review.

| Agent or route | Current adapter behavior | Rate limit and fail-safe behavior |
|---|---|---|
| Document agent (LLM7 default) | OpenAI-compatible adapter: 120-second request timeout and up to 2 retries with exponential backoff for HTTP 429/5xx, timeouts, and transport errors. | Exhaustion raises a typed model error; no automatic cross-provider fallback. The agent must not treat a failed call as a completed extraction. |
| Verification agent (Groq default) | 120-second timeout and up to 2 retries per configured credential for transient HTTP 408/500/502/503/504, timeouts, and transport errors. | 401/403/429 rotates to another explicitly configured Groq credential; exhaustion raises typed authentication, rate-limit, timeout, or availability errors. No cross-vendor fallback. |
| Workflow agent (Kilo default) | Uses the OpenAI-compatible adapter behavior above: 120 seconds and up to 2 retries on 429/5xx, timeout, or transport error. | Exhaustion is returned as a model error; workflow authority remains in deterministic services and the workflow engine. |
| Supervisor agent (Groq default) | Uses the Groq behavior above; child-agent execution is separately bounded to 150 seconds. | Failed or timed-out children produce a failed/limited execution result; no business state is approved by the supervisor model. |
| Optional Gemini route | 120-second timeout and up to 3 retries with exponential backoff for 429/5xx, timeout, and transport errors. | Exhaustion raises typed model errors; no automatic cross-provider fallback. Gemini is not a default agent route. |
| Optional Ollama model route | 120-second request timeout; no automatic retry. | Connection, timeout, HTTP, or response errors fail the call; configured Ollama URLs are subject to the same external-route allowlist in staging/production. |
| Remote embeddings (Cloudflare/Hugging Face) | 60-second HTTP timeout; no automatic retry. | Request/response errors fail ingestion or embedding work; there is no automatic provider switch. Local embeddings are an explicit separate mode. |

Provider adapters and gateway tests cover structured responses, timeout and provider failures, retry behavior, Groq credential rotation/rate limiting, and Gemini rate-limit exhaustion. These tests exercise deterministic mocked providers and do not verify live provider SLAs or terms. The shared per-provider limits and the lack of field redaction remain documented limitations.

## Provider and agent route inventory

The repository's current defaults are configuration baselines, not selected providers. The vendor review fields below are intentionally unresolved; do not mark a row approved based only on the default route.

| Use | Provider / model baseline | Configured endpoint | Data sent | Terms, retention, region, and training review | Approval |
|---|---|---|---|---|---|
| Document agent | LLM7 / gpt-oss:20b | LLM7-compatible chat completion URL | Extracted/document-derived text and case context; exact payload depends on caller | **Unreviewed** | **Not approved** |
| Verification agent | Groq / qwen/qwen3.8-27b | Groq chat completion URL | Verification context and case fields; exact payload depends on caller | **Unreviewed** | **Not approved** |
| Workflow agent | Kilo / dots-studio/dots-3-note-preview:free | Kilo gateway chat completion URL | Workflow context; exact payload depends on caller | **Unreviewed** | **Not approved** |
| Supervisor agent | Groq / qwen/qwen3.8-27b | Groq chat completion URL | Case summary and delegated results; exact payload depends on caller | **Unreviewed** | **Not approved** |
| Embeddings | Cloudflare / @cf/baai/bge-m3 | Cloudflare AI API | Text supplied to the embedding pipeline | **Unreviewed** | **Not approved** |
| Optional routes | Gemini, OpenAI-compatible, Hugging Face Inference, Ollama | Environment-configured | Depends on the configured agent or embedding route | **Unreviewed** | **Not approved** |

## Approval record

Complete one record per provider/model/endpoint-origin route before adding it to the production allowlist:

- Provider legal name and service:
- Exact endpoint hostname and deployment configuration:
- Model identifier and use (agent/embedding):
- Data classes sent by this call path:
- Data classes explicitly allowed and prohibited:
- Retention and deletion terms:
- Training/use-of-input terms:
- Processing region and cross-border transfer notes:
- Subprocessors and contractual/DPA review:
- Redaction/minimization rule and evidence:
- Credential owner and rotation process:
- Reviewer and approval date:
- Re-review date or triggering change:

Any endpoint, model, terms, data-class, or payload change invalidates the prior approval until reviewed again.
