"use client";

import { AnimatePresence, m } from "motion/react";
import { useApp } from "@/components/providers/app-provider";

export function Toast() {
  const { toastMessage, dismissToast } = useApp();
  return (
    <AnimatePresence>
      {toastMessage && (
        <m.div
          key={toastMessage}
          className="toast"
          role="status"
          aria-live="polite"
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 12 }}
        >
          <span>{toastMessage}</span>
          <button
            type="button"
            onClick={dismissToast}
            aria-label="Dismiss message"
            className="toast-dismiss"
          >
            ×
          </button>
        </m.div>
      )}
    </AnimatePresence>
  );
}
