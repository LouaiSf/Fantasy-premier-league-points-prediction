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
        <section className="page page--centered">
          <div className="error-card">
            <p className="eyebrow alert">
              Runtime Notice
            </p>
            <h2>
              Something went wrong
            </h2>
            <p>
              {this.state.error?.message || "An unexpected error occurred while rendering this surface."}
            </p>
            <button
              type="button"
              className="btn"
              onClick={this.handleReload}
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
