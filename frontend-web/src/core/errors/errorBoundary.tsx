import { Component, type ErrorInfo, type ReactNode } from "react";
import { telemetry } from "../observability/telemetry";

interface ErrorBoundaryProps { children: ReactNode; fallback?: ReactNode }
interface ErrorBoundaryState { hasError: boolean }

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    telemetry.record({ event: "ui_error", metadata: { name: error.name, componentStack: info.componentStack ?? "" } });
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;
    return this.props.fallback ?? (
      <section className="error-boundary" role="alert">
        <div className="error-boundary__icon" aria-hidden="true">!</div>
        <h1>This view needs a restart</h1>
        <p>A component failed safely. Your session and tenant data were not changed.</p>
        <button type="button" className="button button--primary" onClick={() => window.location.reload()}>
          Reload view
        </button>
      </section>
    );
  }
}
