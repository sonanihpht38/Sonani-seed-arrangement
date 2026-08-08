// App-level error boundary: a render error in one feature shows a recoverable
// fallback instead of a blank white screen for the whole app.

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // In production, forward this to Sentry / your logging endpoint.
    console.error("Unhandled UI error:", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div style={{ fontFamily: "system-ui, sans-serif", padding: 32, color: "#111" }}>
          <h1 style={{ fontSize: 20 }}>Something went wrong</h1>
          <p style={{ color: "#475569" }}>
            The screen failed to load. Try reloading; if it keeps happening, contact support.
          </p>
          <button
            onClick={() => this.setState({ error: null })}
            style={{
              marginTop: 12, padding: "8px 14px", borderRadius: 6, border: 0,
              cursor: "pointer", background: "#0f172a", color: "#fff", fontSize: 14,
            }}
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
