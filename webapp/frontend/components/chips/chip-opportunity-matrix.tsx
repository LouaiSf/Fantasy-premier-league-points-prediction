import { CHIP_IDS, type ChipId, type ChipPrimaryDecision, type ChipRow } from "@/lib/types";
import { ChipIcon } from "./chip-icon";

const CHIP_LABELS: Record<ChipId, string> = {
  triple_captain: "Triple Captain",
  bench_boost: "Bench Boost",
  free_hit: "Free Hit",
  wildcard: "Wildcard",
};

const RAW_UNITS: Record<ChipId, string> = {
  triple_captain: "extra captain points",
  bench_boost: "gross bench points",
  free_hit: "raw lineup difference",
  wildcard: "rebuild potential vs a frozen squad",
};

// Only a measured gain (points over the best normal week) earns a colour
// level. Raw evidence and fixture indexes are different units and stay neutral.
function gainLevel(value: number): string {
  if (value >= 8) return "high";
  if (value >= 4) return "medium";
  if (value > 0) return "low";
  return "none";
}

interface ChipOpportunityMatrixProps {
  rows: ChipRow[];
  primary: ChipPrimaryDecision | null;
  projectionMode: "fixture_signal" | "model_projection";
  hasSquad: boolean;
}

export function ChipOpportunityMatrix({ rows, primary, projectionMode, hasSquad }: ChipOpportunityMatrixProps) {
  const fixtureOnly = projectionMode === "fixture_signal" || !hasSquad;
  return (
    <div className="chip-opportunity-scroll">
      <table className="chip-opportunity-matrix">
        <caption>
          {fixtureOnly ? "Fixture signal index by chip and gameweek" : "Chip evidence by gameweek"}
        </caption>
        <thead>
          <tr>
            <th scope="col">Chip</th>
            {rows.map((row) => <th scope="col" key={row.gw}>GW{row.gw}</th>)}
          </tr>
        </thead>
        <tbody>
          {CHIP_IDS.map((chip) => (
            <tr key={chip}>
              <th scope="row">
                <span className="chip-matrix-label">
                  <ChipIcon id={chip} />
                  <span>{CHIP_LABELS[chip]}</span>
                </span>
              </th>
              {rows.map((row) => {
                const gain = row.projected_gain[chip] ?? null;
                const raw = row.raw_signal[chip] ?? null;
                const index = row.fixture_signal_index[chip] ?? null;
                const isPrimary = primary?.chip === chip && primary.gw === row.gw;
                let kind: "gain" | "raw" | "index" | "empty" = "empty";
                let value: number | null = null;
                if (gain !== null) { kind = "gain"; value = gain; }
                else if (raw !== null) { kind = "raw"; value = raw; }
                else if (index !== null) { kind = "index"; value = index; }
                const unit = kind === "gain" ? "extra points over your best normal week"
                  : kind === "raw" ? RAW_UNITS[chip] + " (not a gain)"
                    : "fixture signal index (not points)";
                return (
                  <td
                    key={`${chip}-${row.gw}`}
                    className={`chip-score chip-score--${kind === "gain" && value !== null ? gainLevel(value) : kind}${isPrimary ? " is-recommended" : ""}`}
                    title={CHIP_LABELS[chip] + " GW" + row.gw + ": " + (value === null ? "no value" : value.toFixed(1) + " " + unit)}
                  >
                    {value === null ? "—" : value.toFixed(1)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="chip-matrix-legend">
        <span><i className="chip-swatch chip-score--medium" /> Extra points over your best normal week (Triple Captain only)</span>
        <span><i className="chip-swatch chip-score--raw" /> Raw evidence in that chip&apos;s own units, not a gain</span>
        <span><i className="chip-swatch chip-score--index" /> Fixture signal index, not points</span>
      </p>
    </div>
  );
}
