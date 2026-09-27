import type { ChipPlanEntry, ChipRow } from "@/lib/types";
import { ChipIcon } from "./chip-icon";

interface ChipPlanTimelineProps {
  rows: ChipRow[];
  chipPlan: ChipPlanEntry[];
  currentGameweek: number;
}

// The first gameweek of the second half-season set: the strip breaks here
// because unused chips reset, not because anything changes on the pitch.
const SECOND_HALF_START_GW = 20;

export function ChipPlanTimeline({ rows, chipPlan, currentGameweek }: ChipPlanTimelineProps) {
  if (rows.length === 0) return null;
  const chipByGw = new Map(chipPlan.map((entry) => [entry.gw, entry]));

  return (
    <div className="chip-timeline-scroll" role="img" aria-label="Chip plan timeline from the current gameweek to the end of the season">
      <div className="chip-timeline">
        {rows.map((row) => {
          const entry = chipByGw.get(row.gw);
          return (
            <div
              key={row.gw}
              className={
                `chip-timeline-cell state-${row.projection_state}` +
                (row.gw === currentGameweek ? " is-now" : "") +
                (row.gw === SECOND_HALF_START_GW ? " is-half-start" : "")
              }
              title={`GW${row.gw}${entry ? ` · ${entry.chip.replace("_", " ")} planned` : ""}`}
            >
              <span className="chip-timeline-gw">{row.gw}</span>
              <span className="chip-timeline-markers">
                {row.dgw_teams > 0 && <span className="chip-timeline-dgw">DGW</span>}
                {row.blank_teams > 0 && <span className="chip-timeline-bgw">BGW</span>}
              </span>
              {entry && <ChipIcon id={entry.chip} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
