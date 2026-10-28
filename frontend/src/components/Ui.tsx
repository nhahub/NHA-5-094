import type { ButtonHTMLAttributes, ReactNode } from "react";
import { AlertCircle, CheckCircle2, CircleHelp, LoaderCircle } from "lucide-react";

const POSITIVE = new Set(["APPROVED", "COMPLETED", "PASS", "PROCESSED", "SUCCESS", "ACTIVE", "CONTINUE"]);
const NEGATIVE = new Set(["CANCELLED", "ERROR", "FAIL", "FAILED", "REJECTED", "ESCALATE"]);
const CAUTION = new Set(["INCONCLUSIVE", "IN_PROGRESS", "NEEDS_REVIEW", "PENDING", "PENDING_REVIEW", "PROCESSING", "QUEUED", "REVIEW", "RUNNING", "NEEDS_INFORMATION"]);

export function statusTone(value: string): "positive" | "negative" | "caution" | "neutral" {
  const normalized = value.trim().toUpperCase();
  if (POSITIVE.has(normalized)) return "positive";
  if (NEGATIVE.has(normalized)) return "negative";
  if (CAUTION.has(normalized)) return "caution";
  return "neutral";
}

export function formatStatus(value: string): string {
  if (value.toUpperCase() === "NOT_APPLICABLE") return "Not applicable";
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge status-${statusTone(status)}`}>{formatStatus(status)}</span>;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}

export function SectionHeading({ title, detail, action }: { title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="section-heading">
      <div>
        <h2>{title}</h2>
        {detail && <p>{detail}</p>}
      </div>
      {action}
    </div>
  );
}

export function LoadingState({ label = "Loading information" }: { label?: string }) {
  return (
    <div className="state-panel state-loading" role="status" aria-live="polite">
      <LoaderCircle size={18} className="spin" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state-panel state-error" role="alert">
      <AlertCircle size={18} aria-hidden="true" />
      <div className="state-copy">
        <strong>We couldn’t load this information</strong>
        <span>{message}</span>
      </div>
      {onRetry && <button className="text-button" type="button" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  icon,
  action,
}: {
  title: string;
  description: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon ?? <CircleHelp size={22} aria-hidden="true" />}</div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function SuccessNotice({ children }: { children: ReactNode }) {
  return (
    <div className="notice notice-success" role="status">
      <CheckCircle2 size={17} aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}

export function ErrorNotice({ children }: { children: ReactNode }) {
  return (
    <div className="notice notice-error" role="alert">
      <AlertCircle size={17} aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  icon,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "quiet" | "danger";
  icon?: ReactNode;
}) {
  return (
    <button className={`button button-${variant} ${className}`.trim()} {...props}>
      {icon}
      <span>{children}</span>
    </button>
  );
}

export function Field({
  label,
  hint,
  error,
  id,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  id: string;
  children: ReactNode;
}) {
  const helpId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className="form-field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && <small id={helpId} className="field-hint">{hint}</small>}
      {error && <small id={errorId} className="field-error">{error}</small>}
    </div>
  );
}

export function joinDescribedBy(...ids: Array<string | undefined>): string | undefined {
  const value = ids.filter(Boolean).join(" ");
  return value || undefined;
}
