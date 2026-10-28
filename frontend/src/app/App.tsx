import { useState, type FormEvent } from "react";
import { ArrowRight, BadgeCheck, BriefcaseBusiness, CircleHelp, FileCheck2, LockKeyhole, ShieldCheck } from "lucide-react";
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router";
import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { Button, ErrorNotice, Field, LoadingState } from "../components/Ui";
import { ApprovalsPage } from "../features/approvals/ApprovalsPage";
import { CaseWorkspacePage } from "../features/cases/CaseWorkspacePage";
import { CasesPage } from "../features/cases/CasesPage";
import { CustomerCasesPage } from "../features/cases/CustomerCasesPage";
import { CustomerCaseWorkspacePage } from "../features/cases/CustomerCaseWorkspacePage";
import { OverviewPage } from "../features/dashboard/OverviewPage";
import { TasksPage } from "../features/tasks/TasksPage";
import { UsersPage } from "../features/users/UsersPage";

function InternalWorkspaceGate() {
  return <AppShell />;
}

function RequireInternal() {
  const { user } = useAuth();
  return user?.role === "CUSTOMER" ? <Navigate to="/customer/cases" replace /> : <Outlet />;
}

function RequireCustomer() {
  const { user } = useAuth();
  return user?.role === "CUSTOMER" ? <Outlet /> : <Navigate to="/overview" replace />;
}

function WorkspaceHome() {
  const { user } = useAuth();
  return <Navigate to={user?.role === "CUSTOMER" ? "/customer/cases" : "/overview"} replace />;
}

function RequireAuth() {
  const { status, sessionError, retrySession } = useAuth();
  const location = useLocation();
  if (status === "loading") return <LoadingState label="Restoring your session" />;
  if (status === "unavailable") {
    return (
      <div className="auth-state-wrap">
        <div className="auth-state-card">
          <ErrorNotice>{sessionError || "The backend could not confirm your session."}</ErrorNotice>
          <Button variant="secondary" onClick={() => void retrySession()}>Retry session check</Button>
        </div>
      </div>
    );
  }
  if (status !== "authenticated") return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

function RequireManager() {
  const { user } = useAuth();
  if (user?.role !== "MANAGER" && user?.role !== "ADMIN") {
    return (
      <section className="route-denied" role="alert">
        <ShieldCheck size={26} aria-hidden="true" />
        <h1>Manager access required</h1>
        <p>Your current account cannot view or decide organization approvals. The backend enforces this access check.</p>
      </section>
    );
  }
  return <ApprovalsPage />;
}

function RequireAdmin() {
  const { user } = useAuth();
  if (user?.role !== "ADMIN") {
    return (
      <section className="route-denied" role="alert">
        <ShieldCheck size={26} aria-hidden="true" />
        <h1>Administrator access required</h1>
        <p>Your current account cannot manage organization users. The backend independently enforces this access check.</p>
      </section>
    );
  }
  return <UsersPage />;
}

function LoginPage() {
  const { status, login, sessionExpired } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status === "loading") return <LoadingState label="Checking your session" />;
  if (status === "authenticated") return <Navigate to="/overview" replace />;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      const destination = (location.state as { from?: string } | null)?.from;
      navigate(destination?.startsWith("/") && !destination.startsWith("//") ? destination : "/overview", { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign in could not be completed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-layout">
      <section className="login-story" aria-label="VerifiaAI product information">
        <div className="login-brand">
          <img className="brand-symbol" src="/verifia-mark.svg" alt="" width="42" height="42" />
          <strong>Verifia <span>AI</span></strong>
        </div>
        <div className="login-story-content">
          <p className="eyebrow eyebrow-light">EVIDENCE-LED OPERATIONS</p>
          <h1>Make every business decision traceable.</h1>
          <p>Coordinate documents, deterministic checks, and human review in one clear case workspace.</p>
          <div className="login-flow" aria-label="Case operating model">
            <div><FileCheck2 size={17} aria-hidden="true" /><span>Evidence</span></div>
            <span className="flow-line" aria-hidden="true" />
            <div><BadgeCheck size={17} aria-hidden="true" /><span>Verification</span></div>
            <span className="flow-line" aria-hidden="true" />
            <div><BriefcaseBusiness size={17} aria-hidden="true" /><span>Decision</span></div>
          </div>
        </div>
        <div className="login-story-foot"><LockKeyhole size={14} aria-hidden="true" /><span>AI proposes. Your process and people decide.</span></div>
      </section>

      <section className="login-form-side">
        <div className="login-form-card">
          <div className="login-form-heading">
            <p className="eyebrow">OPERATOR SIGN IN</p>
            <h2>Welcome back</h2>
            <p>Sign in with an account provisioned for this VerifiaAI environment.</p>
          </div>
          {sessionExpired && <ErrorNotice>Your session ended. Sign in again to continue.</ErrorNotice>}
          {error && <ErrorNotice>{error}</ErrorNotice>}
          <form onSubmit={handleSubmit} className="login-form">
            <Field id="login-email" label="Work email">
              <input
                id="login-email"
                type="email"
                autoComplete="username"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                disabled={submitting}
              />
            </Field>
            <Field id="login-password" label="Password">
              <input
                id="login-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                disabled={submitting}
              />
            </Field>
            <Button type="submit" className="login-submit" disabled={submitting} icon={<ArrowRight size={17} aria-hidden="true" />}>
              {submitting ? "Signing in…" : "Continue to workspace"}
            </Button>
          </form>
          <p className="provisioning-note"><CircleHelp size={15} aria-hidden="true" /> No account yet? Ask your environment owner for an approved account.</p>
        </div>
        <footer className="login-footer">VerifiaAI · Evidence, rules, workflows, and human judgment</footer>
      </section>
    </main>
  );
}

function NotFoundPage() {
  const { status } = useAuth();
  return (
    <div className="not-found-page">
      <span className="not-found-code">404</span>
      <h1>That page is not here</h1>
      <p>The route may have changed, or your account may not have access to it.</p>
      <Link className="button button-primary" to={status === "authenticated" ? "/overview" : "/login"}>Return to workspace</Link>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<InternalWorkspaceGate />}>
          <Route index element={<WorkspaceHome />} />
          <Route element={<RequireCustomer />}>
            <Route path="customer/cases" element={<CustomerCasesPage />} />
            <Route path="customer/cases/:caseId" element={<CustomerCaseWorkspacePage />} />
          </Route>
          <Route element={<RequireInternal />}>
            <Route path="overview" element={<OverviewPage />} />
            <Route path="cases" element={<CasesPage />} />
            <Route path="cases/:caseId" element={<CaseWorkspacePage />} />
            <Route path="tasks" element={<TasksPage />} />
            <Route path="approvals" element={<RequireManager />} />
            <Route path="admin/users" element={<RequireAdmin />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
