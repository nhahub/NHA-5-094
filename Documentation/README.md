# VerifiaAI — Project Documentation V2.1

*A unified business and technical reference for the Verifia platform: what it is, why it exists, how it is configured, how a case moves through the system, and how the AI is governed by deterministic business infrastructure.*

> **Version:** 2.1
> **Status:** Architecture and implementation blueprint
> **Primary demonstration:** Import / Export business process
> **Design approach:** Generic core + organization-specific configuration + organization integrations

> **Changes from V2.0:** split into four linked documents by audience (see below); fixed a section-numbering gap (§40 was missing, §41 renumbered to §40); removed duplicate architecture diagrams that repeated the same "AI proposes → deterministic validates/executes → business state → event" loop shown in §1 (previously redrawn in §25 and §39); corrected TOC anchor links; converted the 11 genuine flow/architecture ASCII diagrams into real Mermaid `flowchart` diagrams (see note below).

---

## How this documentation is organized

This used to be a single ~3,500-line file. It's now split into four parts so each reader can go straight to what they need instead of scrolling past content meant for someone else:

| Part | File | Audience | Read style |
|---|---|---|---|
| 1 | [Product Overview](01-product-overview.md) | Stakeholders, new hires | Read start to finish, once |
| 2 | [Architecture & AI Agent Design](02-architecture.md) | Engineers designing/reviewing the system | Reference, jump to a section |
| 3 | [Database Schema](03-database-schema.md) | Engineers writing migrations/queries | Reference, searched constantly |
| 4 | [Operations, Security & Roadmap](04-operations-and-roadmap.md) | DevOps, security reviewers, leadership | Reference, occasional sections |

> **Visual guide:** The diagrams throughout these documents are intentionally complementary. Start with the System Context, then the DFDs, architecture and agent views, followed by workflow/sequence, domain/database, security, and the concrete Import/Export example. Together they provide a visual explanation of Verifia without requiring the reader to read every section linearly.

> **On ASCII diagrams:** The original V2.0 had 118 plain-text (` ```text `) diagram blocks alongside 12 Mermaid diagrams. Most of those text blocks were directory/entity trees or short linear chains (e.g. `Case → Documents → Evidence`) — those render fine as plain text and were left alone; converting a folder tree into a flowchart would make it *less* readable, not more. The 11 blocks that were genuinely multi-box architecture or process-flow diagrams (drawn with `┌─┐└┘├┤`) have been converted to real Mermaid `flowchart` diagrams, since box-drawing characters render inconsistently across fonts/viewers and can't be zoomed, copied cleanly, or exported like Mermaid can. The 44 database table definitions in Part 3 were kept as plain-text column lists on purpose — see that document's intro note.

### Engineering plans, audits, and operational guides

- [Frontend implementation plan and API/security capability map](frontend-implementation-plan.md)
- [Frontend design system and accessibility baseline](frontend-design-system.md)
- [Frontend implementation and verification closeout](progress_report.md)
- [Frontend security findings and Phase 19 implementation](frontend-and-phase19-review.md)
- [Phase 20 production security implementation plan](phase20-production-security-implementation-plan.md)
- [Phase 21 durable events implementation plan and closeout](phase21-durable-events-implementation-plan.md)
- [Official Phase 20–21 compliance matrix](phase20-21-official-compliance-matrix.md)
- [Official Phase 20–21 A–K compliance audit](phase20-21-official-compliance-audit.md)
- [Historical Phase 20–21 traceability snapshot](phase20-21-requirements-traceability.md)
- [Historical Phase 20–21 closeout snapshot](phase20-21-final-closeout.md)
- [Phase 22 repeatable quality gates implementation plan](phase22-implementation-plan.md)
- [Phase 23 evidence-based model evaluation plan](phase23-implementation-plan.md)
- [Phase 24 Insurance Claim generalization implementation plan](phase24-implementation-plan.md)
- [Phase 27 AI Research & Evaluation Foundation plan](phase27-ai-research-evaluation-plan.md)
- [Phases 20–24 comprehensive audit and remediation plan](phases20-24-comprehensive-audit-plan.md)
- [External model provider review and allowlist policy](external-model-provider-review.md)
- [Production Compose environment template](../env.production.example) and [deployment profile](../docker-compose.production.yml)
- [Full phase, security, test, and documentation audit (2026-10-10)](project-audit-2026-10-10.md)
- [Local run guide, including first administrator setup](RUNNING_THE_PROJECT.md)

---

## Full Table of Contents

### Part 1 — [Product Overview](01-product-overview.md)
1. [Executive Summary](01-product-overview.md#1-executive-summary)
2. [Product Definition](01-product-overview.md#2-product-definition)
3. [The Problem](01-product-overview.md#3-the-problem)
4. [Product Scope and Boundaries](01-product-overview.md#4-product-scope-and-boundaries)
5. [Core Concepts](01-product-overview.md#5-core-concepts)

### Part 2 — [Architecture & AI Agent Design](02-architecture.md)
6. [The Three-Layer Architecture](02-architecture.md#6-the-three-layer-architecture)
7. [Organization Configuration](02-architecture.md#7-organization-configuration)
8. [Business Case Model](02-architecture.md#8-business-case-model)
9. [Process Model](02-architecture.md#9-process-model)
10. [Requirements, Rules, Verifications, Tasks and Approvals](02-architecture.md#10-requirements-rules-verifications-tasks-and-approvals)
11. [AI Agent Architecture](02-architecture.md#11-ai-agent-architecture)
12. [Agent Responsibilities](02-architecture.md#12-agent-responsibilities)
13. [AI Loop vs. Business Workflow Loop](02-architecture.md#13-ai-loop-vs-business-workflow-loop)
14. [Model Gateway and Hybrid AI Strategy](02-architecture.md#14-model-gateway-and-hybrid-ai-strategy)
15. [Agent Tools and Tool Gateway](02-architecture.md#15-agent-tools-and-tool-gateway)
16. [Deterministic Verification and Computation](02-architecture.md#16-deterministic-verification-and-computation)
17. [Document Intelligence](02-architecture.md#17-document-intelligence)
18. [Knowledge and RAG](02-architecture.md#18-knowledge-and-rag)
19. [Workflow Engine](02-architecture.md#19-workflow-engine)
20. [Human-in-the-Loop and Exceptions](02-architecture.md#20-human-in-the-loop-and-exceptions)
21. [Case State, Memory and Events](02-architecture.md#21-case-state-memory-and-events)
22. [End-to-End Runtime Flow](02-architecture.md#22-end-to-end-runtime-flow)
23. [Import / Export Demonstration Workflow](02-architecture.md#23-import--export-demonstration-workflow)

### Part 3 — [Database Schema](03-database-schema.md)
24. [Database Architecture](03-database-schema.md#24-database-architecture)
25. [Database Entity Model](03-database-schema.md#25-database-entity-model)
26. [Database Tables](03-database-schema.md#26-database-tables)
27. [Data Integrity, Versioning and Multi-Tenancy](03-database-schema.md#27-data-integrity-versioning-and-multi-tenancy)

### Part 4 — [Operations, Security & Roadmap](04-operations-and-roadmap.md)
28. [Security and Guardrails](04-operations-and-roadmap.md#28-security-and-guardrails)
29. [Authentication and Authorization](04-operations-and-roadmap.md#29-authentication-and-authorization)
30. [Task Routing and Notifications](04-operations-and-roadmap.md#30-task-routing-and-notifications)
31. [Observability and Audit](04-operations-and-roadmap.md#31-observability-and-audit)
32. [API and Service Boundaries](04-operations-and-roadmap.md#32-api-and-service-boundaries)
33. [Technology Stack](04-operations-and-roadmap.md#33-technology-stack)
34. [Project Structure](04-operations-and-roadmap.md#34-project-structure)
35. [Reliability Principles](04-operations-and-roadmap.md#35-reliability-principles)
36. [Evaluation Framework](04-operations-and-roadmap.md#36-evaluation-framework)
37. [Demo Requirements](04-operations-and-roadmap.md#37-demo-requirements)
38. [Future Extensions](04-operations-and-roadmap.md#38-future-extensions)
39. [Final Architecture](04-operations-and-roadmap.md#39-final-architecture)
40. [Project Vision](04-operations-and-roadmap.md#40-project-vision)
- [Appendix A — Architectural Invariants](04-operations-and-roadmap.md#appendix-a--architectural-invariants)
- [Appendix B — Conceptual Data Flow](04-operations-and-roadmap.md#appendix-b--conceptual-data-flow)

---

This V2.1 set of documents is the architecture baseline for the implementation phase. The next engineering artifacts should derive from it rather than redefine the system independently.
