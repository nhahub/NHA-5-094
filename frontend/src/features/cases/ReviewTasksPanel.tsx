import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, MessageSquareText, ShieldCheck, UserRoundCheck } from "lucide-react";
import { Link } from "react-router";
import { api } from "../../api/client";
import type { CaseReviewBundle, EvidenceRecord, ReviewTask, TaskCommentCreate, TaskResolutionRequest } from "../../api/contracts";
import { queryKeys } from "../../api/queryKeys";
import { useAuth } from "../../auth/AuthContext";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { Button, EmptyState, ErrorNotice, LoadingState, SectionHeading, StatusBadge, SuccessNotice } from "../../components/Ui";

export function ReviewTasksPanel({ caseId, bundle }: { caseId: string; bundle: CaseReviewBundle }) {
  const { user } = useAuth();
  const tasksQuery = useQuery({
    queryKey: queryKeys.myTasks(user),
    queryFn: api.tasks.mine,
    enabled: Boolean(user),
  });
  const availableTaskIds = new Set((tasksQuery.data ?? []).map((task) => task.id));
  const hasOpenTasks = bundle.review_tasks.some((task) => !isClosed(task.status));

  return (
    <div className="page-stack">
      <section className="panel">
        <SectionHeading title="Review tasks" detail="Tasks, comments, and outcomes recorded for this case" />
        {tasksQuery.isError && <div className="partial-data-note" role="status">Your assignment list is unavailable, so task actions are hidden until the backend confirms your queue.</div>}
        {tasksQuery.isPending && hasOpenTasks && <LoadingState label="Checking your assigned task queue" />}
        {bundle.review_tasks.length === 0 ? (
          <EmptyState title="No review tasks" description="Tasks will appear here when the backend creates human work for this case." icon={<UserRoundCheck size={22} aria-hidden="true" />} />
        ) : (
          <div className="review-task-list">
            {bundle.review_tasks.map((task) => (
              <TaskReviewCard key={task.id} task={task} caseId={caseId} bundle={bundle} canAct={availableTaskIds.has(task.id)} />
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div><p className="eyebrow">HUMAN DECISIONS</p><h2>Approval history</h2></div>
          {user?.role === "MANAGER" || user?.role === "ADMIN" ? <Link className="inline-link" to="/approvals">Open approval queue</Link> : null}
        </div>
        {bundle.approvals.length === 0 ? (
          <EmptyState title="No approval request" description="An approval record will appear here if the configured process requires one." icon={<ShieldCheck size={22} aria-hidden="true" />} />
        ) : (
          <div className="approval-history-list">
            {bundle.approvals.map((approval) => (
              <article className="approval-history-card" key={approval.id}>
                <div><strong>{formatStatus(approval.approval_type)}</strong><span>{approval.created_at ? formatDateTime(approval.created_at) : "Request time unavailable"}</span></div>
                <StatusBadge status={approval.decision} />
                {approval.comment && <p>{approval.comment}</p>}
                {approval.decided_at && <small>Decision recorded {formatDateTime(approval.decided_at)}</small>}
                {approval.decision === "PENDING" && (user?.role === "MANAGER" || user?.role === "ADMIN") && <Link className="text-button" to="/approvals">Review pending decision</Link>}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function TaskReviewCard({
  task,
  caseId,
  bundle,
  canAct,
}: {
  task: ReviewTask;
  caseId: string;
  bundle: CaseReviewBundle;
  canAct: boolean;
}) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [commentText, setCommentText] = useState("");
  const [selectedEvidence, setSelectedEvidence] = useState<string[]>([]);
  const [commentError, setCommentError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [resolveOpen, setResolveOpen] = useState(false);

  const commentMutation = useMutation({
    mutationFn: (input: TaskCommentCreate) => api.tasks.addComment(task.id, input),
    onSuccess: async () => {
      setCommentText("");
      setSelectedEvidence([]);
      setCommentError(null);
      setSuccess("Comment added to the case review history.");
      await queryClient.invalidateQueries({ queryKey: queryKeys.caseReview(user, caseId) });
    },
  });

  function submitComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const clean = commentText.trim();
    if (!clean) {
      setCommentError("Add a comment before submitting.");
      return;
    }
    setCommentError(null);
    setSuccess(null);
    commentMutation.mutate({ comment: clean, evidence_ids: selectedEvidence });
  }

  const isOpen = !isClosed(task.status);

  return (
    <article className="review-task-card">
      <div className="review-task-head">
        <div className="task-type-mark"><MessageSquareText size={17} aria-hidden="true" /></div>
        <div className="review-task-title"><strong>{task.title}</strong><span>{task.task_type} · {task.priority} priority</span></div>
        <StatusBadge status={task.status} />
      </div>
      {task.description && <p className="review-task-description">{task.description}</p>}
      <div className="review-task-meta"><span>Task {task.id.slice(0, 8)}</span>{task.due_at && <span>Due {formatDateTime(task.due_at)}</span>}{task.assigned_user_id && <span>Assigned user {task.assigned_user_id.slice(0, 8)}</span>}</div>

      {task.comments.length > 0 && (
        <div className="task-comments">
          <h3>Review comments</h3>
          {task.comments.map((comment) => (
            <blockquote key={comment.id}>
              <p>{comment.comment}</p>
              <footer>{formatDateTime(comment.created_at)} · {comment.evidence_ids.length} evidence link{comment.evidence_ids.length === 1 ? "" : "s"}</footer>
            </blockquote>
          ))}
        </div>
      )}

      {isOpen && canAct && (
        <div className="task-actions-area">
          {success && <SuccessNotice>{success}</SuccessNotice>}
          {commentMutation.isError && <ErrorNotice>{getError(commentMutation.error)}</ErrorNotice>}
          {commentError && <ErrorNotice>{commentError}</ErrorNotice>}
          <form className="task-comment-form" onSubmit={submitComment}>
            <label htmlFor={`task-comment-${task.id}`}>Add an auditable comment</label>
            <textarea id={`task-comment-${task.id}`} value={commentText} onChange={(event) => setCommentText(event.target.value)} rows={3} maxLength={10_000} disabled={commentMutation.isPending} placeholder="Record the review finding or next step…" />
            <EvidenceChecklist taskId={task.id} evidence={bundle.evidence} selected={selectedEvidence} onChange={setSelectedEvidence} />
            <div className="task-form-actions">
              <Button type="submit" variant="secondary" disabled={commentMutation.isPending || !commentText.trim()} icon={<MessageSquareText size={15} aria-hidden="true" />}>{commentMutation.isPending ? "Adding…" : "Add comment"}</Button>
              <Button type="button" onClick={() => setResolveOpen(true)} icon={<Check size={15} aria-hidden="true" />}>Resolve task</Button>
            </div>
          </form>
        </div>
      )}

      {isOpen && !canAct && (
        <p className="task-action-note">Task actions are shown only for items returned in your assigned queue. If this task should be assigned to you, ask a manager to update it.</p>
      )}

      {resolveOpen && (
        <TaskResolutionDialog
          open={resolveOpen}
          task={task}
          evidence={bundle.evidence}
          onClose={() => setResolveOpen(false)}
          onResolved={async () => {
            setResolveOpen(false);
            setSuccess("The backend recorded the task outcome.");
            await Promise.all([
              queryClient.invalidateQueries({ queryKey: queryKeys.caseReview(user, caseId) }),
              queryClient.invalidateQueries({ queryKey: queryKeys.myTasks(user) }),
              queryClient.invalidateQueries({ queryKey: ["cases"] }),
            ]);
          }}
        />
      )}
    </article>
  );
}

function TaskResolutionDialog({
  open,
  task,
  evidence,
  onClose,
  onResolved,
}: {
  open: boolean;
  task: ReviewTask;
  evidence: EvidenceRecord[];
  onClose: () => void;
  onResolved: () => Promise<void>;
}) {
  const [outcome, setOutcome] = useState<TaskResolutionRequest["outcome"]>("COMPLETED");
  const [comment, setComment] = useState("");
  const [evidenceIds, setEvidenceIds] = useState<string[]>([]);
  const [formError, setFormError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (input: TaskResolutionRequest) => api.tasks.resolve(task.id, input),
    onSuccess: async () => {
      setFormError(null);
      await onResolved();
    },
  });

  function confirm() {
    if (!comment.trim()) {
      setFormError("A resolution comment is required.");
      return;
    }
    setFormError(null);
    mutation.mutate({ outcome, comment: comment.trim(), evidence_ids: evidenceIds });
  }

  return (
    <ConfirmDialog
      open={open}
      title="Resolve review task"
      description={`Record the authoritative outcome for “${task.title}”. A nonblank comment is required by the backend.`}
      confirmLabel={outcome === "COMPLETED" ? "Complete task" : "Reject task"}
      onConfirm={confirm}
      onClose={onClose}
      busy={mutation.isPending}
      danger={outcome === "REJECTED"}
      confirmDisabled={!comment.trim()}
    >
      <div className="dialog-form">
        <div className="form-field">
          <label htmlFor={`task-outcome-${task.id}`}>Outcome</label>
          <select id={`task-outcome-${task.id}`} value={outcome} onChange={(event) => setOutcome(event.target.value as TaskResolutionRequest["outcome"])} disabled={mutation.isPending}>
            <option value="COMPLETED">Completed</option>
            <option value="REJECTED">Rejected</option>
          </select>
        </div>
        <div className="form-field">
          <label htmlFor={`task-resolution-${task.id}`}>Resolution comment</label>
          <textarea id={`task-resolution-${task.id}`} value={comment} onChange={(event) => setComment(event.target.value)} rows={4} maxLength={10_000} disabled={mutation.isPending} required />
          <small className="field-hint">This comment is stored with the human decision.</small>
        </div>
        <EvidenceChecklist taskId={`resolution-${task.id}`} evidence={evidence} selected={evidenceIds} onChange={setEvidenceIds} />
        {formError && <ErrorNotice>{formError}</ErrorNotice>}
        {mutation.isError && <ErrorNotice>{getError(mutation.error)}</ErrorNotice>}
      </div>
    </ConfirmDialog>
  );
}

function EvidenceChecklist({
  taskId,
  evidence,
  selected,
  onChange,
}: {
  taskId: string;
  evidence: EvidenceRecord[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  if (evidence.length === 0) return <p className="field-hint">No case evidence is currently available to attach.</p>;
  function toggle(id: string) {
    onChange(selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id]);
  }
  return (
    <fieldset className="evidence-select">
      <legend>Attach case evidence (optional)</legend>
      <div className="evidence-checkbox-list">
        {evidence.map((item) => (
          <label key={item.id} htmlFor={`${taskId}-evidence-${item.id}`}>
            <input id={`${taskId}-evidence-${item.id}`} type="checkbox" checked={selected.includes(item.id)} onChange={() => toggle(item.id)} />
            <span>{item.description || formatStatus(item.evidence_type)}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function isClosed(status: string): boolean {
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
