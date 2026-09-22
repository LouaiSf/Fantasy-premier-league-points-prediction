import { CHIP_IDS, type ChipId, type ChipRecommendation, type ChipRow } from "@/lib/types";
import { ChipIcon } from "./chip-icon";

const CHIP_LABELS: Record<ChipId, string> = {
  triple_captain: "Triple Captain",
  bench_boost: "Bench Boost",
  free_hit: "Free Hit",
  wildcard: "Wildcard",
};

function cellLevel(value: number | null | undefined): string {
  if (value == null) return "empty";
  if (value >= 8) return "high";
  if (value >= 4) return "medium";
  if (value > 0) return "low";
  return "none";
}

interface ChipOpportunityMatrixProps {
  rows: ChipRow[];
  recommendations: ChipRecommendation[];
  projectionMode: "fixture_signal" | "model_projection";
  hasSquad: boolean;
}

export function ChipOpportunityMatrix({ rows, recommendations, projectionMode, hasSquad }: ChipOpportunityMatrixProps) {
  const recommended = new Map(
    recommendations
      .filter((rec) => rec.status === "play")
      .map((rec) => [rec.chip, rec.candidate_gw]),
  );
  return (
    <div className="chip-opportunity-scroll">
      <table className="chip-opportunity-matrix">
        <caption>{projectionMode === "fixture_signal" || !hasSquad ? "Fixture signal index by chip and gameweek" : "Projected gain by chip and gameweek"}</caption>
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
                const points = row.projected_gain[chip] ?? null;
                const fixtureIndex = row.fixture_signal_index[chip] ?? null;
                const value = points ?? fixtureIndex;
                const isRecommended = recommended.get(chip) === row.gw;
                return (
                  <td
                    key={`${chip}-${row.gw}`}
                    className={`chip-score chip-score--${cellLevel(value)}${isRecommended ? " is-recommended" : ""}`}
                    title={CHIP_LABELS[chip] + " GW" + row.gw + ": " + (value == null ? "No value" : points == null ? "fixture signal index " + value.toFixed(1) : value.toFixed(1) + " projected points")}
                  >
                    {value == null ? "—" : value.toFixed(1)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
