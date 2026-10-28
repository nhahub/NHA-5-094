import { Component, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

type State = { failed: boolean };

export class AppErrorBoundary extends Component<{ children: ReactNode }, State> {
  override state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  override render() {
    if (this.state.failed) {
      return (
        <main className="fatal-error-page" role="alert">
          <div className="fatal-error-card">
            <span className="fatal-error-mark" aria-hidden="true"><AlertTriangle size={22} /></span>
            <p className="eyebrow">WORKSPACE ERROR</p>
            <h1>This page could not be displayed</h1>
            <p>Reload the workspace to try again. If the problem continues, contact your administrator.</p>
            <button className="button button-primary" type="button" onClick={() => window.location.reload()}>Reload workspace</button>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}
