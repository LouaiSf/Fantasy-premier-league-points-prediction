import { CHIP_IDS, type ChipId, type ChipPlanEntry, type ChipRecommendation } from "@/lib/types";
import { num } from "@/lib/format";
import { ChipIcon } from "./chip-icon";

const CHIP_LABELS: Record<ChipId, string> = {
  triple_captain: "Triple Captain",
  bench_boost: "Bench Boost",
  free_hit: "Free Hit",
  wildcard: "Wildcard",
};

function gainLevel(value: number): string {
  if (value >= 8) return "high";
  if (value >= 4) return "medium";
  if (value > 0) return "low";
  return "none";
}

interface ChipGainHeatmapProps {
  recommendations: ChipRecommendation[];
  chipPlan: ChipPlanEntry[];
  currentGameweek: number;
  hasSquad: boolean;
}

export function ChipOpportunityMatrix({ recommendations, chipPlan, currentGameweek, hasSquad }: ChipGainHeatmapProps) {
  if (!hasSquad) return null;
  const byChip = new Map(recommendations.map((rec) => [rec.chip, rec]));
  const assigned = new Map(chipPlan.map((entry) => [entry.chip, entry.gw]));
  const gameweeks = Array.from(
    new Set(recommendations.flatMap((rec) => rec.candidate_gameweeks)),
  ).sort((a, b) => a - b);

  if (gameweeks.length === 0) return null;

  return (
    <div className="chip-opportunity-scroll">
      <table className="chip-opportunity-matrix">
        <caption>Gain in points, by chip and eligible gameweek</caption>
        <thead>
          <tr>
            <th scope="col">Chip</th>
            {gameweeks.map((gw) => (
              <th scope="col" key={gw} className={gw === currentGameweek ? "is-now" : undefined}>
                GW{gw}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {CHIP_IDS.map((chip) => {
            const rec = byChip.get(chip);
            const assignedGw = assigned.get(chip);
            return (
              <tr key={chip}>
                <th scope="row">
                  <span className="chip-matrix-label">
                    <ChipIcon id={chip} />
                    <span>{CHIP_LABELS[chip]}</span>
                  </span>
                </th>
                {gameweeks.map((gw) => {
                  const value = rec?.gains_by_week[String(gw)] ?? null;
                  const isCandidate = rec?.candidate_gameweeks.includes(gw) ?? false;
                  const isAssigned = assignedGw === gw;
                  if (!isCandidate) {
                    return <td key={`${chip}-${gw}`} className="chip-score chip-score--empty">—</td>;
                  }
                  return (
                    <td
                      key={`${chip}-${gw}`}
                      className={`chip-score chip-score--${value === null ? "empty" : gainLevel(value)}${isAssigned ? " is-recommended" : ""}`}
                      title={`${CHIP_LABELS[chip]} GW${gw}: ${value === null ? "no value" : num(value, 1) + " extra points"}`}
                    >
                      {value === null ? "—" : num(value, 1)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="chip-matrix-legend">
        <span><i className="chip-swatch chip-score--medium" /> Extra points vs the best no-chip week</span>
        <span><i className="chip-swatch is-recommended" /> The plan&apos;s assigned week for that chip</span>
      </p>
    </div>
  );
}
