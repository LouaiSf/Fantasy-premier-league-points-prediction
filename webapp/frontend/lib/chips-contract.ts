import { CHIP_IDS, CHIPS_CONTRACT_VERSION, type ChipsResult } from "./types";

export const CHIPS_CONTRACT_ERROR =
  "Chip advice server is out of date. Restart the Flask API and retry.";

const CHIP_STATUSES = ["watch", "consider", "hold", "unavailable", "compare"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isArray(value: unknown): value is unknown[] {
  return Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return isArray(value) && value.every((v) => typeof v === "string");
}

function isNumberArray(value: unknown): value is number[] {
  return isArray(value) && value.every((v) => typeof v === "number");
}

function isNumberOrNull(value: unknown): value is number | null {
  return value === null || typeof value === "number";
}

function isStringOrNull(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isDecisionPolicy(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value.minimum_projected_gain === "number" &&
    typeof value.uncertainty_note === "string" &&
    typeof value.basis === "string"
  );
}

function isChipKeyedNumberMap(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return CHIP_IDS.every((chip) => !(chip in value) || isNumberOrNull(value[chip]));
}

function isValidRow(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value.gw === "number" &&
    typeof value.matches === "number" &&
    typeof value.dgw_teams === "number" &&
    typeof value.blank_teams === "number" &&
    typeof value.avg_fdr === "number" &&
    isChipKeyedNumberMap(value.projected_gain) &&
    isChipKeyedNumberMap(value.raw_signal) &&
    isChipKeyedNumberMap(value.fixture_signal_index) &&
    typeof value.projection_state === "string"
  );
}

function isValidRecommendation(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value.label === "string" &&
    typeof value.status === "string" &&
    typeof value.chip === "string" &&
    isArray(value.candidate_gameweeks) &&
    isNumberOrNull(value.gw) &&
    isNumberOrNull(value.candidate_gw) &&
    isNumberOrNull(value.projected_gain) &&
    isNumberOrNull(value.fixture_signal_index) &&
    isArray(value.alternatives) &&
    isDecisionPolicy(value.decision_policy) &&
    isArray(value.reasons) &&
    isArray(value.warnings) &&
    isNumberOrNull(value.raw_signal) &&
    isArray(value.inventory_windows) &&
    CHIP_STATUSES.includes(value.status as never)
  );
}

/**
 * Parses an unknown JSON payload as a ChipsResult, validating every field the
 * UI reads without a null check. An older/incompatible Flask process omits
 * fields like projection_gameweeks, which otherwise crashes the page at the
 * `.length` accesses in chips/page.tsx.
 */
export function parseChipsResult(value: unknown): ChipsResult {
  if (
    !isRecord(value) ||
    typeof value.ok !== "boolean" ||
    typeof value.contract_version !== "number" ||
    value.contract_version < CHIPS_CONTRACT_VERSION ||
    typeof value.first_gw !== "number" ||
    typeof value.last_gw !== "number" ||
    typeof value.any_dgw !== "boolean" ||
    typeof value.any_bgw !== "boolean" ||
    typeof value.has_squad !== "boolean" ||
    !isArray(value.rows) ||
    !value.rows.every(isValidRow) ||
    !isArray(value.recommendations) ||
    !value.recommendations.every(isValidRecommendation) ||
    typeof value.current_gameweek !== "number" ||
    typeof value.projection_mode !== "string" ||
    (value.inventory_source !== "local_user_reported" && value.inventory_source !== "unknown") ||
    !(value.primary_decision === null || isRecord(value.primary_decision)) ||
    typeof value.projection_semantics !== "string" ||
    typeof value.projection_note !== "string" ||
    !isNumberArray(value.scheduled_gameweeks) ||
    typeof value.projection_source !== "string" ||
    !isStringOrNull(value.projection_generated_at) ||
    !isNumberArray(value.projection_gameweeks) ||
    typeof value.requested_horizon !== "number" ||
    typeof value.evaluated_horizon !== "number" ||
    !isStringOrNull(value.coverage_warning) ||
    typeof value.data_quality !== "string" ||
    typeof value.methodology_version !== "string" ||
    !isDecisionPolicy(value.decision_policy) ||
    (value.unmapped_teams !== undefined && !isStringArray(value.unmapped_teams))
  ) {
    throw new Error(CHIPS_CONTRACT_ERROR);
  }
  return value as unknown as ChipsResult;
}
