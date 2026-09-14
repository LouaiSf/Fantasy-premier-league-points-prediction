"use client";

import * as React from "react";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null });
    if (typeof window !== "undefined") {
      window.location.reload();
    }
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <section className="page" style={{ display: "grid", placeItems: "center", minHeight: "60vh" }}>
          <div
            className="panel card-tint"
            style={{
              maxWidth: 540,
              padding: "var(--space-8)",
              textAlign: "center",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "var(--space-4)",
            }}
          >
            <p className="eyebrow" style={{ color: "var(--pink)" }}>
              Runtime Notice
            </p>
            <h2 style={{ margin: 0, font: "800 24px/1.2 var(--display)" }}>
              Something went wrong
            </h2>
            <p style={{ color: "var(--muted-foreground)", fontSize: 14, margin: 0 }}>
              {this.state.error?.message || "An unexpected error occurred while rendering this surface."}
            </p>
            <button
              type="button"
              className="btn btn-primary"
              onClick={this.handleReload}
              style={{ marginTop: "var(--space-2)" }}
            >
              Reload Surface
            </button>
          </div>
        </section>
      );
    }

    return this.props.children;
  }
}
