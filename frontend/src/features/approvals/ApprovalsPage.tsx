import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, ShieldCheck, X } from "lucide-react";
import { Link } from "react-router";
import { api } from "../../api/client";
import type { ApprovalDecisionRequest, ApprovalRecord } from "../../api/contracts";
import { queryKeys } from "../../api/queryKeys";
import { useAuth } from "../../auth/AuthContext";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { Button, EmptyState, ErrorState, PageHeader, StatusBadge, SuccessNotice } from "../../components/Ui";

export function ApprovalsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const approvalsQuery = useQuery({
    queryKey: queryKeys.pendingApprovals(user),
    queryFn: api.approvals.pending,
    enabled: user?.role === "MANAGER" || user?.role === "ADMIN",
  });
  const [selected, setSelected] = useState<{ approval: ApprovalRecord; decision: ApprovalDecisionRequest["decision"] } | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const decisionMutation = useMutation({
    mutationFn: ({ approvalId, input }: { approvalId: string; input: ApprovalDecisionRequest }) => api.approvals.decide(approvalId, input),
    onSuccess: async (approval) => {
      setSelected(null);
      setSuccess(`${formatStatus(approval.decision)} decision was recorded by the backend.`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.pendingApprovals(user) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.caseReview(user, approval.case_id) }),
        queryClient.invalidateQueries({ queryKey: ["cases"] }),
      ]);
    },
  });

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="MANAGER REVIEW"
        title="Approvals"
        description="Record an authorized human decision with a reason. The backend confirms the outcome."
        actions={<span className="approval-count"><ShieldCheck size={16} aria-hidden="true" />{approvalsQuery.data?.length ?? 0} pending</span>}
      />
      {success && <SuccessNotice>{success}</SuccessNotice>}
      {approvalsQuery.isPending ? (
        <div className="state-panel state-loading" role="status">Loading approval queue…</div>
      ) : approvalsQuery.isError ? (
        <ErrorState message={getError(approvalsQuery.error)} onRetry={() => void approvalsQuery.refetch()} />
      ) : approvalsQuery.data.length === 0 ? (
        <section className="panel"><EmptyState title="Approval queue is clear" description="There are no pending approvals available to your account." icon={<ShieldCheck size={22} aria-hidden="true" />} /></section>
      ) : (
        <section className="approval-queue">
          {approvalsQuery.data.map((approval) => (
            <article className="approval-card" key={approval.id}>
              <div className="approval-card-icon"><ShieldCheck size={18} aria-hidden="true" /></div>
              <div className="approval-card-main">
                <div className="approval-card-heading"><div><p className="eyebrow">{formatStatus(approval.approval_type)} APPROVAL</p><h2>Decision required</h2></div><StatusBadge status={approval.decision} /></div>
                <div className="approval-card-meta">
                  <span>Requested {formatDateTime(approval.created_at)}</span>
                  <Link className="approval-case-link" to={`/cases/${approval.case_id}`}>Open case <ArrowRight size={14} aria-hidden="true" /></Link>
                  {approval.task_id && <span>Task {approval.task_id.slice(0, 8)}</span>}
                </div>
                <div className="approval-card-actions">
                  <Button variant="secondary" onClick={() => { setSuccess(null); setSelected({ approval, decision: "REJECTED" }); }} icon={<X size={16} aria-hidden="true" />}>Reject</Button>
                  <Button onClick={() => { setSuccess(null); setSelected({ approval, decision: "APPROVED" }); }} icon={<Check size={16} aria-hidden="true" />}>Approve</Button>
                </div>
              </div>
            </article>
          ))}
        </section>
      )}

      {selected && <DecisionDialog
        key={`${selected.approval.id}:${selected.decision}`}
        selected={selected}
        busy={decisionMutation.isPending}
        error={decisionMutation.error ? getError(decisionMutation.error) : null}
        onClose={() => { if (!decisionMutation.isPending) { setSelected(null); decisionMutation.reset(); } }}
        onSubmit={(comment) => {
          if (!selected) return;
          decisionMutation.mutate({ approvalId: selected.approval.id, input: { decision: selected.decision, comment } });
        }}
      />}
    </div>
  );
}

function DecisionDialog({
  selected,
  busy,
  error,
  onClose,
  onSubmit,
}: {
  selected: { approval: ApprovalRecord; decision: ApprovalDecisionRequest["decision"] } | null;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (comment: string) => void;
}) {
  const [comment, setComment] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const current = selected;

  function confirm() {
    const clean = comment.trim();
    if (!clean) {
      setValidationError("A decision comment is required.");
      return;
    }
    setValidationError(null);
    onSubmit(clean);
  }

  return (
    <ConfirmDialog
      open={Boolean(current)}
      title={current?.decision === "APPROVED" ? "Approve this request?" : "Reject this request?"}
      description={current ? `${formatStatus(current.approval.approval_type)} for case ${current.approval.case_id.slice(0, 8)}. The backend will record your identity, comment, and decision time.` : ""}
      confirmLabel={current?.decision === "APPROVED" ? "Confirm approval" : "Confirm rejection"}
      onConfirm={confirm}
      onClose={onClose}
      busy={busy}
      danger={current?.decision === "REJECTED"}
      confirmDisabled={!comment.trim()}
    >
      <div className="dialog-form">
        <div className="form-field">
          <label htmlFor="approval-comment">Decision comment</label>
          <textarea id="approval-comment" rows={4} maxLength={10_000} value={comment} onChange={(event) => { setComment(event.target.value); setValidationError(null); }} disabled={busy} required />
          <small className="field-hint">This explanation is stored with the approval record.</small>
        </div>
        {validationError && <div className="field-error" role="alert">{validationError}</div>}
        {error && <div className="field-error" role="alert">{error}</div>}
      </div>
    </ConfirmDialog>
  );
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
