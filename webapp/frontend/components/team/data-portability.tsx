"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { downloadExportedData, importLocalData, ImportError } from "@/lib/data-portability";

// This app has no account system -- the squad and chip data below live in
// this browser's localStorage only. Export/import is the honest, bounded
// way to move them to another device: a file the manager carries
// themselves, not a login system this project doesn't have.
export function DataPortability() {
  const { toast } = useApp();
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const [importing, setImporting] = React.useState(false);

  function handleExport() {
    try {
      downloadExportedData();
      toast("Exported your squad and chip data.");
    } catch (err) {
      toast(`Export failed: ${(err as Error).message}`);
    }
  }

  async function handleFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setImporting(true);
    try {
      const text = await file.text();
      importLocalData(text);
      toast("Imported -- reloading…");
      window.location.reload();
    } catch (err) {
      toast(err instanceof ImportError ? err.message : "Import failed.");
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="data-portability">
      <p>Your squad and chip data live in this browser only. Export a file to move them to another device.</p>
      <div className="data-portability-actions">
        <button type="button" className="btn secondary sm" onClick={handleExport}>
          Export my data
        </button>
        <button
          type="button"
          className="btn secondary sm"
          onClick={() => fileInputRef.current?.click()}
          disabled={importing}
        >
          {importing ? "Importing…" : "Import"}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json"
          className="sr-only"
          onChange={(event) => void handleFile(event)}
          aria-label="Import FPL Assistant data file"
        />
      </div>
    </div>
  );
}
