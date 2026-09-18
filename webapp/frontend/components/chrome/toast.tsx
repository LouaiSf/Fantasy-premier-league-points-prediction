"use client";

import { useApp } from "@/components/providers/app-provider";

export function Toast() {
  const { toastMessage, dismissToast } = useApp();
  return (
    <div className={`toast${toastMessage ? " is-visible" : ""}`} role="status" aria-live="polite">
      <span>{toastMessage}</span>
      <button
        type="button"
        onClick={dismissToast}
        aria-label="Dismiss message"
        className="toast-dismiss"
      >
        ×
      </button>
    </div>
  );
}
