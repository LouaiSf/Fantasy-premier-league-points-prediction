import type { SquadFinance } from "./types";

export interface TransferDraftPair {
  readonly out_element: number;
  readonly in_element: number;
}

export interface SavedTransferDraft {
  readonly version: 1;
  readonly season: string;
  readonly gameweek: number | null;
  readonly fingerprint: string;
  readonly pairs: TransferDraftPair[];
  readonly max_transfers: number;
  readonly free_transfers: number;
  readonly bank_tenths: number;
  readonly saved_at: string;
}

export interface HeldWeek {
  readonly version: 1;
  readonly season: string;
  readonly gameweek: number;
  readonly fingerprint: string;
  readonly created_at: string;
}

export function transferDraftKey(season: string): string {
  return `fpl-assistant-transfer-draft:${season}`;
}

export function heldWeekKey(season: string): string {
  return `fpl-assistant-held-week:${season}`;
}

export function squadFingerprint(
  season: string,
  elements: readonly number[],
  finance: SquadFinance | null,
): string {
  const ownedPrices = Object.entries(finance?.ownedPrices ?? {})
    .map(([element, price]) => [Number(element), price.purchaseTenths, price.sellingTenths ?? null] as const)
    .sort(([left], [right]) => left - right);
  return JSON.stringify({
    season,
    elements: [...elements].sort((left, right) => left - right),
    bankTenths: finance?.bankTenths ?? null,
    ownedPrices,
  });
}

export function isSavedTransferDraft(value: unknown): value is SavedTransferDraft {
  if (typeof value !== "object" || value === null) return false;
  const draft = value as Record<string, unknown>;
  return draft.version === 1 &&
    typeof draft.season === "string" &&
    (draft.gameweek === null || (typeof draft.gameweek === "number" && Number.isInteger(draft.gameweek))) &&
    typeof draft.fingerprint === "string" &&
    Array.isArray(draft.pairs) &&
    draft.pairs.every((pair) => typeof pair === "object" && pair !== null &&
      Number.isSafeInteger((pair as Record<string, unknown>).out_element) &&
      Number.isSafeInteger((pair as Record<string, unknown>).in_element)) &&
    Number.isInteger(draft.max_transfers) &&
    Number.isInteger(draft.free_transfers) &&
    Number.isSafeInteger(draft.bank_tenths) &&
    typeof draft.saved_at === "string";
}

export function isHeldWeek(value: unknown): value is HeldWeek {
  if (typeof value !== "object" || value === null) return false;
  const hold = value as Record<string, unknown>;
  return hold.version === 1 &&
    typeof hold.season === "string" &&
    Number.isInteger(hold.gameweek) &&
    typeof hold.fingerprint === "string" &&
    typeof hold.created_at === "string";
}

export const MAX_SCENARIOS = 3;

export interface SavedScenario {
  readonly id: string;
  readonly name: string;
  readonly pairs: TransferDraftPair[];
  readonly free_transfers: number;
  readonly bank_tenths: number;
  readonly fingerprint: string;
  readonly prediction_timestamp: string | null;
  readonly saved_at: string;
}

export function scenarioKey(season: string): string {
  return `fpl-assistant-transfer-scenarios:${season}`;
}

export function isSavedScenario(value: unknown): value is SavedScenario {
  if (typeof value !== "object" || value === null) return false;
  const scenario = value as Record<string, unknown>;
  return typeof scenario.id === "string" &&
    typeof scenario.name === "string" &&
    Array.isArray(scenario.pairs) &&
    scenario.pairs.every((pair) => typeof pair === "object" && pair !== null &&
      Number.isSafeInteger((pair as Record<string, unknown>).out_element) &&
      Number.isSafeInteger((pair as Record<string, unknown>).in_element)) &&
    Number.isInteger(scenario.free_transfers) &&
    Number.isSafeInteger(scenario.bank_tenths) &&
    typeof scenario.fingerprint === "string" &&
    (scenario.prediction_timestamp === null || typeof scenario.prediction_timestamp === "string") &&
    typeof scenario.saved_at === "string";
}

/** A scenario is comparable only against the same squad and the same prediction snapshot. */
export function scenarioStaleReason(
  scenario: SavedScenario,
  fingerprint: string,
  predictionTimestamp: string | null,
): string | null {
  if (scenario.fingerprint !== fingerprint) return "Saved for a different squad";
  if (scenario.prediction_timestamp !== predictionTimestamp) return "Saved against an older prediction snapshot";
  return null;
}
