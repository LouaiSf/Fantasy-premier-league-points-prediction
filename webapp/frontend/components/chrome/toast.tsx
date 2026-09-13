"use client";

import { useApp } from "@/components/providers/app-provider";

export function Toast() {
  const { toastMessage } = useApp();
  return (
    <div className={`toast${toastMessage ? " is-visible" : ""}`} role="status" aria-live="polite">
      <span>{toastMessage}</span>
    </div>
  );
}
