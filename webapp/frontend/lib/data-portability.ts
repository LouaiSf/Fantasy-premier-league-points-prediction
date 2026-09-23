import { CHIP_INVENTORY_KEY, SQUAD_STORAGE_KEY } from "./storage-keys";

// This app keeps a manager's squad, finance and chip data in this browser's
// localStorage only -- there's no account or server-side sync. Export/import
// is the honest, bounded answer to "I want this on another device": a file
// the manager carries themselves, not a login system this project doesn't
// have the infrastructure for.
const EXPORT_VERSION = 1;

export interface ExportedData {
  version: number;
  exportedAt: string;
  squad: unknown;
  chipInventory: unknown;
}

export function exportLocalData(): ExportedData {
  const squadRaw = window.localStorage.getItem(SQUAD_STORAGE_KEY);
  const chipInventoryRaw = window.localStorage.getItem(CHIP_INVENTORY_KEY);
  return {
    version: EXPORT_VERSION,
    exportedAt: new Date().toISOString(),
    squad: squadRaw ? JSON.parse(squadRaw) : null,
    chipInventory: chipInventoryRaw ? JSON.parse(chipInventoryRaw) : null,
  };
}

export function downloadExportedData(): void {
  const data = exportLocalData();
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `fpl-assistant-export-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export class ImportError extends Error {}

// Overwrites this browser's saved squad and chip inventory with an earlier
// export. Deliberately does not merge: a partial merge between two squads
// (say, different seasons, or one with finance data and one without) has no
// single correct meaning, so importing is all-or-nothing and the caller
// reloads the page afterward to re-derive every dependent piece of state.
export function importLocalData(json: string): void {
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    throw new ImportError("That file isn't valid JSON.");
  }
  if (typeof parsed !== "object" || parsed === null || !("version" in parsed)) {
    throw new ImportError("That file doesn't look like an FPL Assistant export.");
  }
  const data = parsed as Partial<ExportedData>;
  if (data.version !== EXPORT_VERSION) {
    throw new ImportError(`Unsupported export version (${String(data.version)}); expected ${EXPORT_VERSION}.`);
  }
  if (data.squad) {
    window.localStorage.setItem(SQUAD_STORAGE_KEY, JSON.stringify(data.squad));
  } else {
    window.localStorage.removeItem(SQUAD_STORAGE_KEY);
  }
  if (data.chipInventory) {
    window.localStorage.setItem(CHIP_INVENTORY_KEY, JSON.stringify(data.chipInventory));
  } else {
    window.localStorage.removeItem(CHIP_INVENTORY_KEY);
  }
}
