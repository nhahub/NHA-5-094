import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, BriefcaseBusiness, ClipboardCheck, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { useAuth } from "../../auth/AuthContext";
import { EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from "../../components/Ui";

const CASE_PAGE_SIZE = 100;
const CLOSED_CASES = new Set(["COMPLETED", "REJECTED", "CANCELLED"]);
const CLOSED_TASKS = new Set(["COMPLETED", "REJECTED", "CANCELLED"]);

function countLabel(count: number, cap: number): string {
  return count === cap ? `${cap}+` : String(count);
}

export function OverviewPage() {
  const { user } = useAuth();
  const casesQuery = useQuery({
    queryKey: queryKeys.cases(user, { skip: 0, limit: CASE_PAGE_SIZE }),
    queryFn: () => api.cases.list({ skip: 0, limit: CASE_PAGE_SIZE }),
    enabled: Boolean(user),
  });
  const tasksQuery = useQuery({
    queryKey: queryKeys.myTasks(user),
    queryFn: api.tasks.mine,
    enabled: Boolean(user),
  });
  const canApprove = user?.role === "MANAGER" || user?.role === "ADMIN";
  const approvalsQuery = useQuery({
    queryKey: queryKeys.pendingApprovals(user),
    queryFn: api.approvals.pending,
    enabled: canApprove,
  });

  const cases = casesQuery.data ?? [];
  const tasks = tasksQuery.data ?? [];
  const approvals = approvalsQuery.data ?? [];
  const activeCases = cases.filter((item) => !CLOSED_CASES.has(item.status.toUpperCase())).length;
  const reviewCases = cases.filter((item) => item.status.toUpperCase() === "PENDING_REVIEW").length;
  const openTasks = tasks.filter((task) => !CLOSED_TASKS.has(task.status.toUpperCase())).length;
  const casesCapped = cases.length === CASE_PAGE_SIZE;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="OPERATIONS OVERVIEW"
        title={`Good ${getDaypart()}, ${firstName(user?.full_name)}.`}
        description="A live snapshot of the queues and case work available to your account."
        actions={<span className="date-chip">{new Intl.DateTimeFormat(undefined, { dateStyle: "full" }).format(new Date())}</span>}
      />

      {casesQuery.isError && !casesQuery.data && <ErrorState message={getError(casesQuery.error)} onRetry={() => void casesQuery.refetch()} />}

      <section className="metric-grid" aria-label="Operational queue snapshot">
        <MetricCard
          icon={<BriefcaseBusiness size={18} aria-hidden="true" />}
          label="Active cases in view"
          value={casesQuery.isPending ? "—" : countLabel(activeCases, CASE_PAGE_SIZE)}
          detail={casesCapped ? "Latest API page · 100 records max" : "From the cases returned by the API"}
          tone="teal"
        />
        <MetricCard
          icon={<AlertTriangle size={18} aria-hidden="true" />}
          label="Cases pending review"
          value={casesQuery.isPending ? "—" : countLabel(reviewCases, CASE_PAGE_SIZE)}
          detail={casesCapped ? "Within the latest 100 returned cases" : "Among the cases returned by the API"}
          tone="amber"
        />
        <MetricCard
          icon={<ClipboardCheck size={18} aria-hidden="true" />}
          label="Open tasks in your queue"
          value={tasksQuery.isPending ? "—" : String(openTasks)}
          detail="Assigned to your user, role, or department"
          tone="blue"
        />
        {canApprove && (
          <MetricCard
            icon={<ShieldCheck size={18} aria-hidden="true" />}
            label="Pending approvals"
            value={approvalsQuery.isPending ? "—" : String(approvals.length)}
            detail="Organization approvals awaiting a manager decision"
            tone="violet"
          />
        )}
      </section>

      {(tasksQuery.isError || (canApprove && approvalsQuery.isError)) && (
        <div className="partial-data-note" role="status">
          Some queue information is unavailable. Each section below shows its own current state.
        </div>
      )}

      <section className="panel recent-cases-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">CASE REGISTER</p>
            <h2>Recent cases</h2>
          </div>
          <Link className="inline-link" to="/cases">View all cases <ArrowRight size={15} aria-hidden="true" /></Link>
        </div>
        {casesQuery.isPending ? (
          <LoadingState label="Loading case register" />
        ) : casesQuery.isError ? (
          <ErrorState message={getError(casesQuery.error)} onRetry={() => void casesQuery.refetch()} />
        ) : cases.length === 0 ? (
          <EmptyState
            title="No cases in this workspace"
            description="Create a case from an available published process version to begin a workflow."
            icon={<BriefcaseBusiness size={22} aria-hidden="true" />}
            action={<Link className="button button-primary" to="/cases">Open case register</Link>}
          />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr><th scope="col">Case</th><th scope="col">Process</th><th scope="col">Current status</th><th scope="col">Updated</th><th scope="col"><span className="sr-only">Open case</span></th></tr>
              </thead>
              <tbody>
                {cases.slice(0, 6).map((item) => (
                  <tr key={item.id}>
                    <td><Link className="case-number-link" to={`/cases/${item.id}`}>{item.case_number}</Link><span className="table-secondary">{item.title}</span></td>
                    <td><span className="mono-id">{item.process_id.slice(0, 8)}</span></td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>{formatDate(item.updated_at)}</td>
                    <td><Link className="icon-link" aria-label={`Open ${item.case_number}`} to={`/cases/${item.id}`}><ArrowRight size={17} aria-hidden="true" /></Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {casesCapped && <p className="table-footnote">The API does not return a total case count. This snapshot is based on one page of 100 records.</p>}
      </section>

      <section className="workflow-principle">
        <div className="principle-symbol"><ShieldCheck size={20} aria-hidden="true" /></div>
        <div><strong>Recommendations and decisions stay distinct</strong><p>AI summaries help reviewers understand a case. Verification results, workflow transitions, and human approvals remain backend-confirmed records.</p></div>
      </section>
    </div>
  );
}

function MetricCard({
  icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
  tone: string;
}) {
  return (
    <article className="metric-card">
      <div className={`metric-icon metric-${tone}`}>{icon}</div>
      <div className="metric-value-row"><span>{label}</span><strong>{value}</strong></div>
      <p>{detail}</p>
    </article>
  );
}

function firstName(fullName?: string): string {
  return fullName?.trim().split(/\s+/)[0] || "there";
}

function getDaypart(): string {
  const hour = new Date().getHours();
  return hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

function getError(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed.";
}
