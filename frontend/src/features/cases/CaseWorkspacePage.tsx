import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, ArrowLeft, Bot, FileCheck2, History, LoaderCircle, RefreshCw, ShieldCheck } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router";
import { api } from "../../api/client";
import type { AgentRunResponse, CaseRecommendation, CaseReviewBundle, EventRecord } from "../../api/contracts";
import { queryKeys } from "../../api/queryKeys";
import { useAuth } from "../../auth/AuthContext";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { Button, EmptyState, ErrorNotice, ErrorState, LoadingState, PageHeader, SectionHeading, StatusBadge } from "../../components/Ui";
import { DocumentsPanel } from "./DocumentsPanel";
import { ReviewTasksPanel } from "./ReviewTasksPanel";

const CASE_VIEWS = [
  { id: "overview", label: "Overview", icon: ShieldCheck },
  { id: "documents", label: "Documents", icon: FileCheck2 },
  { id: "verification", label: "Verification", icon: ShieldCheck },
  { id: "review", label: "Tasks & approvals", icon: Activity },
  { id: "activity", label: "Activity", icon: History },
];

export function CaseWorkspacePage() {
  const { caseId = "" } = useParams();
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const [confirmAgent, setConfirmAgent] = useState(false);
  const [agentResult, setAgentResult] = useState<AgentRunResponse | null>(null);
  const queryClient = useQueryClient();
  const activeView = CASE_VIEWS.some((item) => item.id === searchParams.get("view")) ? searchParams.get("view")! : "overview";

  const reviewQuery = useQuery({
    queryKey: queryKeys.caseReview(user, caseId),
    queryFn: () => api.cases.review(caseId),
    enabled: Boolean(caseId),
  });
  const stateQuery = useQuery({
    queryKey: queryKeys.caseState(user, caseId),
    queryFn: () => api.cases.state(caseId),
    enabled: Boolean(caseId),
  });
  const eventsQuery = useQuery({
    queryKey: queryKeys.caseEvents(user, caseId),
    queryFn: () => api.cases.events(caseId, 0, 100),
    enabled: Boolean(caseId) && activeView === "activity",
  });
  const runAgent = useMutation({
    mutationFn: () => api.agents.runSupervisor(caseId),
    onSuccess: async (result) => {
      setConfirmAgent(false);
      setAgentResult(result);
      await queryClient.invalidateQueries({ queryKey: queryKeys.caseReview(user, caseId) });
    },
  });

  if (!caseId) return <ErrorState message="A case identifier is required to open this workspace." />;
  if (reviewQuery.isPending) return <LoadingState label="Opening case workspace" />;
  if (reviewQuery.isError) {
    return (
      <div className="page-stack">
        <Link className="back-link" to="/cases"><ArrowLeft size={16} aria-hidden="true" /> Back to cases</Link>
        <ErrorState message={getError(reviewQuery.error)} onRetry={() => void reviewQuery.refetch()} />
      </div>
    );
  }

  const bundle = reviewQuery.data;
  const record = bundle.case;
  const selectedView = CASE_VIEWS.find((item) => item.id === activeView) ?? CASE_VIEWS[0]!;
  const SelectedIcon = selectedView.icon;

  return (
    <div className="page-stack case-workspace">
      <Link className="back-link" to="/cases"><ArrowLeft size={16} aria-hidden="true" /> Back to cases</Link>
      <PageHeader
        eyebrow={`CASE ${record.case_number}`}
        title={record.title}
        description={`Created ${formatDateTime(record.created_at)} · Process version ${record.process_version_id.slice(0, 8)}`}
        actions={<StatusBadge status={record.status} />}
      />

      <div className="case-metadata-strip">
        <div><span>Case number</span><strong>{record.case_number}</strong></div>
        <div><span>Current stage</span><strong>{stateQuery.data?.current_stage_name || (stateQuery.isError ? "Stage details unavailable" : record.current_stage_id ? `Stage ${record.current_stage_id.slice(0, 8)}` : "Not assigned")}</strong></div>
        <div><span>Backend status</span><StatusBadge status={record.status} /></div>
        <div><span>Last updated</span><strong>{formatDateTime(record.updated_at)}</strong></div>
      </div>
      {stateQuery.isError && <div className="partial-data-note" role="status">Case state counts are unavailable. The case record above is from the review API.</div>}

      <nav className="case-section-nav" aria-label="Case sections">
        {CASE_VIEWS.map(({ id, label, icon: Icon }) => (
          <Link key={id} to={`/cases/${caseId}?view=${id}`} className={`case-section-link ${activeView === id ? "case-section-active" : ""}`} aria-current={activeView === id ? "page" : undefined}>
            <Icon size={16} aria-hidden="true" /><span>{label}</span>
          </Link>
        ))}
      </nav>

      {activeView === "overview" && (
        <OverviewView
          bundle={bundle}
          state={stateQuery.data}
          agentResult={agentResult}
          onRequestAgent={() => setConfirmAgent(true)}
          agentPending={runAgent.isPending}
          agentError={runAgent.error ? getError(runAgent.error) : null}
        />
      )}
      {activeView === "documents" && <DocumentsPanel caseId={caseId} bundle={bundle} />}
      {activeView === "verification" && <VerificationView bundle={bundle} />}
      {activeView === "review" && <ReviewTasksPanel caseId={caseId} bundle={bundle} />}
      {activeView === "activity" && (
        <ActivityView
          events={eventsQuery.data ?? []}
          pending={eventsQuery.isPending}
          error={eventsQuery.isError ? getError(eventsQuery.error) : null}
          onRetry={() => void eventsQuery.refetch()}
        />
      )}

      {activeView !== "overview" && (
        <p className="case-source-note"><SelectedIcon size={14} aria-hidden="true" /> Records shown here are returned by the authenticated case API. The backend remains authoritative for state and permissions.</p>
      )}

      <ConfirmDialog
        open={confirmAgent}
        title="Run Supervisor review?"
        description="The backend may send case context to the configured AI provider and delegate supported work through authorized tools. A proposal is not a business decision; the backend and any required human approval determine case state."
        confirmLabel="Run Supervisor"
        onConfirm={() => runAgent.mutate()}
        onClose={() => setConfirmAgent(false)}
        busy={runAgent.isPending}
      >
        <div className="agent-disclosure"><Bot size={18} aria-hidden="true" /><span>Use only information approved for the configured provider. Do not include sensitive data unless your organization has approved that data path.</span></div>
      </ConfirmDialog>
    </div>
  );
}

function OverviewView({
  bundle,
  state,
  agentResult,
  onRequestAgent,
  agentPending,
  agentError,
}: {
  bundle: CaseReviewBundle;
  state?: { current_stage_name: string | null; documents_count: number; verifications_count: number; open_tasks_count: number; evidence_count: number };
  agentResult: AgentRunResponse | null;
  onRequestAgent: () => void;
  agentPending: boolean;
  agentError: string | null;
}) {
  const { user } = useAuth();
  const internal = user?.role !== "CUSTOMER";
  return (
    <div className="case-overview-grid">
      <section className="panel case-primary-panel">
        <SectionHeading title="Case snapshot" detail="Current values from VerifiaAI’s case services" />
        <dl className="snapshot-list">
          <div><dt>Case status</dt><dd><StatusBadge status={bundle.case.status} /></dd></div>
          <div><dt>Current workflow stage</dt><dd>{state?.current_stage_name || (bundle.case.current_stage_id ? `Stage ${bundle.case.current_stage_id.slice(0, 8)}` : "Not assigned")}</dd></div>
          <div><dt>Process version</dt><dd className="mono-id">{bundle.case.process_version_id}</dd></div>
          <div><dt>Completed</dt><dd>{bundle.case.completed_at ? formatDateTime(bundle.case.completed_at) : "Not completed"}</dd></div>
        </dl>
        <div className="case-count-grid">
          <CountItem label="Documents" count={state?.documents_count ?? bundle.documents.length} />
          <CountItem label="Verification runs" count={state?.verifications_count ?? bundle.verifications.length} />
          <CountItem label="Open tasks" count={state?.open_tasks_count ?? bundle.review_tasks.filter((task) => !isClosedTask(task.status)).length} />
          <CountItem label="Evidence records" count={state?.evidence_count ?? bundle.evidence.length} />
        </div>
      </section>

      <section className="panel attention-panel">
        <SectionHeading title="Attention" detail="Open discrepancies returned by the case review service" />
        {bundle.discrepancies.length === 0 ? (
          <div className="quiet-success"><ShieldCheck size={18} aria-hidden="true" /><span>No review discrepancies are recorded in this case packet.</span></div>
        ) : (
          <ul className="discrepancy-list">
            {bundle.discrepancies.map((item, index) => (
              <li key={`${item.kind}-${item.result_id ?? item.processing_run_id ?? index}`}>
                <AlertTriangle size={16} aria-hidden="true" />
                <div><strong>{formatStatus(item.kind)}</strong><span>{item.summary || item.reason || item.reasons?.join(" · ") || "Review the related case record."}</span></div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel agent-panel">
        <div className="section-heading">
          <div><p className="eyebrow">AI ASSISTANCE</p><h2>Agent recommendations</h2></div>
          {internal && <Button variant="secondary" icon={agentPending ? <LoaderCircle size={16} className="spin" aria-hidden="true" /> : <RefreshCw size={16} aria-hidden="true" />} onClick={onRequestAgent} disabled={agentPending}>Run Supervisor</Button>}
        </div>
        <p className="agent-boundary-note">AI output is advisory. Deterministic verification, authorized workflow actions, and human decisions establish business state.</p>
        {agentError && <ErrorNotice>{agentError}</ErrorNotice>}
        {agentResult && <AgentResultCard result={agentResult} />}
        {bundle.recommendations.length > 0 ? (
          <div className="recommendation-list">
            {bundle.recommendations.map((item) => <RecommendationCard key={item.execution_id} item={item} />)}
          </div>
        ) : !agentResult ? (
          <EmptyState title="No saved recommendation" description="The case has no bounded agent recommendation in its current review packet." icon={<Bot size={22} aria-hidden="true" />} />
        ) : null}
      </section>
    </div>
  );
}

function CountItem({ label, count }: { label: string; count: number }) {
  return <div className="case-count-item"><span>{label}</span><strong>{count}</strong></div>;
}

function VerificationView({ bundle }: { bundle: CaseReviewBundle }) {
  return (
    <div className="page-stack">
      <section className="panel">
        <SectionHeading title="Verification history" detail="Backend execution statuses and returned result summaries" />
        {bundle.verifications.length === 0 ? (
          <EmptyState title="No verification runs yet" description="A verification will appear here when the backend records an execution for this case." icon={<ShieldCheck size={22} aria-hidden="true" />} />
        ) : (
          <div className="verification-list">
            {bundle.verifications.map((execution) => (
              <article className="verification-card" key={execution.id}>
                <div className="verification-card-head">
                  <div><span className="eyebrow">EXECUTION {execution.id.slice(0, 8)}</span><p>{execution.started_at ? formatDateTime(execution.started_at) : "Start time unavailable"}</p></div>
                  <StatusBadge status={execution.status} />
                </div>
                {execution.results.length === 0 ? <p className="muted">The backend has not returned individual result rows.</p> : (
                  <ul className="result-list">
                    {execution.results.map((result) => (
                      <li key={result.id}>
                        <StatusBadge status={result.result} />
                        <div><strong>{result.summary || formatStatus(result.result)}</strong>{result.reason && <p>{result.reason}</p>}{result.confidence !== null && <span className="confidence-label">Model confidence · {Math.round(result.confidence * 100)}%</span>}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <SectionHeading title="Evidence records" detail="Source references attached to verification outcomes" />
        {bundle.evidence.length === 0 ? (
          <EmptyState title="No evidence records" description="Evidence will be listed when the backend links it to this case." icon={<FileCheck2 size={22} aria-hidden="true" />} />
        ) : (
          <div className="evidence-grid">
            {bundle.evidence.map((record) => (
              <article key={record.id} className="evidence-card">
                <div className="evidence-card-head"><strong>{formatStatus(record.evidence_type)}</strong><span className="mono-id">{record.id.slice(0, 8)}</span></div>
                {record.description && <p>{record.description}</p>}
                {record.items.length === 0 ? <p className="muted">No source items were included.</p> : (
                  <ul className="evidence-item-list">
                    {record.items.map((item) => <li key={item.id}><span>{item.field_reference || formatStatus(item.source_type)}</span><strong>{displayValue(item.value_snapshot)}</strong>{item.page_number !== null && <small>Page {item.page_number}</small>}</li>)}
                  </ul>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ActivityView({
  events,
  pending,
  error,
  onRetry,
}: {
  events: EventRecord[];
  pending: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  if (pending) return <LoadingState label="Loading case events" />;
  if (error) return <ErrorState message={error} onRetry={onRetry} />;
  if (events.length === 0) return <EmptyState title="No case events yet" description="Events are added when the backend records case work, decisions, and workflow changes." icon={<History size={22} aria-hidden="true" />} />;
  return (
    <section className="panel">
      <SectionHeading title="Case activity" detail="Immutable events returned for this case" />
      <ol className="event-timeline">
        {events.map((event) => (
          <li key={event.id}>
            <span className="timeline-marker" aria-hidden="true" />
            <div className="event-copy"><strong>{formatStatus(event.event_type)}</strong><span>{event.actor_type === "SYSTEM" ? "System event" : `${formatStatus(event.actor_type)} action`}</span></div>
            <time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time>
          </li>
        ))}
      </ol>
      {events.length === 100 && <p className="table-footnote">Showing the 100 event records returned for this page.</p>}
    </section>
  );
}

function AgentResultCard({ result }: { result: AgentRunResponse }) {
  return (
    <article className={`agent-result-card ${result.success ? "" : "agent-result-failed"}`}>
      <div className="agent-result-heading"><Bot size={17} aria-hidden="true" /><strong>Supervisor response</strong><StatusBadge status={result.success ? "SUCCESS" : "FAILED"} /></div>
      <p>{result.summary}</p>
      {result.execution_id && <small className="mono-id">Execution {result.execution_id}</small>}
      {result.proposals.length > 0 && (
        <ul className="proposal-list">
          {result.proposals.map((proposal, index) => (
            <li key={`${proposal.agent_name}-${proposal.proposed_action}-${index}`}>
              <span className="proposal-agent">{formatStatus(proposal.agent_name)}</span>
              <strong>{formatStatus(proposal.proposed_action)}</strong>
              {proposal.evidence_references.length > 0 && <small>Evidence references: {proposal.evidence_references.join(", ")}</small>}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

function RecommendationCard({ item }: { item: CaseRecommendation }) {
  const summary = safeRecommendationSummary(item);
  return (
    <article className="recommendation-card">
      <div className="recommendation-card-top"><span>{formatStatus(item.agent_type)} agent</span><StatusBadge status={item.status} /></div>
      <p>{summary || "The case review packet includes an agent recommendation without a display summary."}</p>
      <small className="mono-id">Execution {item.execution_id.slice(0, 8)}{item.completed_at ? ` · ${formatDateTime(item.completed_at)}` : ""}</small>
    </article>
  );
}

function safeRecommendationSummary(item: CaseRecommendation): string | null {
  const record = item.recommendation;
  for (const key of ["summary", "recommendation", "interpretation", "reason"]) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  for (const key of ["summary", "recommendation", "interpretation"]) {
    const nested = record[key];
    if (nested && typeof nested === "object" && !Array.isArray(nested)) {
      for (const nestedKey of ["summary", "recommendation", "reason"]) {
        const value = (nested as Record<string, unknown>)[nestedKey];
        if (typeof value === "string" && value.trim()) return value;
      }
    }
  }
  return null;
}

function displayValue(value: Record<string, unknown> | null): string {
  if (!value) return "Value unavailable";
  if ("value" in value) return String(value.value ?? "Value unavailable");
  const text = JSON.stringify(value);
  return text.length > 180 ? `${text.slice(0, 177)}…` : text;
}

function isClosedTask(status: string): boolean {
  return ["COMPLETED", "REJECTED", "CANCELLED"].includes(status.toUpperCase());
}

function formatStatus(value: string): string {
  return value.toLowerCase().split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function getError(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed.";
}
