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
        style={{
          background: "transparent",
          border: "none",
          color: "inherit",
          cursor: "pointer",
          fontSize: 16,
          fontWeight: 700,
          lineHeight: 1,
          padding: "2px 4px",
          marginLeft: "auto",
        }}
      >
        ×
      </button>
    </div>
  );
}
