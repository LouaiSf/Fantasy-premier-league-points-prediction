"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

function earliestKickoff(snapshot: ReturnType<typeof useApp>["snapshot"]): Date | null {
  if (!snapshot || snapshot.gameweek == null) return null;
  let earliest: number | null = null;
  for (const team of snapshot.teams) {
    for (const fixture of team.fixtures) {
      if (fixture.gameweek !== snapshot.gameweek || !fixture.kickoff_time) continue;
      const ts = Date.parse(fixture.kickoff_time);
      if (Number.isNaN(ts)) continue;
      if (earliest === null || ts < earliest) earliest = ts;
    }
  }
  return earliest === null ? null : new Date(earliest);
}

interface Part {
  readonly value: number;
  readonly unit: string;
}

function countdownParts(ms: number): Part[] {
  const totalMinutes = Math.floor(ms / 60000);
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;
  return days > 0
    ? [{ value: days, unit: "d" }, { value: hours, unit: "h" }, { value: minutes, unit: "m" }]
    : [{ value: hours, unit: "h" }, { value: minutes, unit: "m" }];
}

export function useDeadline() {
  const { snapshot } = useApp();
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);
  const deadline = earliestKickoff(snapshot);
  const remaining = deadline ? deadline.getTime() - now : null;
  return { snapshot, deadline, remaining };
}

// The deadline as a stadium departure sign: the gameweek, the time left in
// big figures, and a track that fills as the lock gets closer.
export function DeadlineClock({ variant = "rail" }: { readonly variant?: "rail" | "compact" }) {
  const { snapshot, deadline, remaining } = useDeadline();
  if (!snapshot) return null;

  if (!deadline || remaining == null) {
    return (
      <div className={`deadline deadline--${variant}`}>
        <span className="deadline-label">Season {snapshot.season}</span>
        <span className="deadline-time">Fixtures to come</span>
      </div>
    );
  }

  const inProgress = remaining <= 0;
  const urgent = remaining > 0 && remaining < 24 * 60 * 60 * 1000;
  const tension = inProgress ? 1 : Math.min(1, Math.max(0, 1 - remaining / WEEK_MS));
  const kickoff = deadline.toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });

  return (
    <div className={`deadline deadline--${variant}${urgent ? " is-urgent" : ""}`} aria-live="polite">
      <span className="deadline-label">
        {inProgress ? `Gameweek ${snapshot.gameweek} is live` : `Gameweek ${snapshot.gameweek} deadline`}
      </span>
      <span className="deadline-time">
        {inProgress
          ? "Matches under way"
          : countdownParts(remaining).map((part) => (
              <span className="deadline-part" key={part.unit}>
                <b key={part.value}>{part.value}</b>
                {part.unit}
              </span>
            ))}
      </span>
      {variant === "rail" && !inProgress && <span className="deadline-when">First kick-off {kickoff}</span>}
      <span className="deadline-track" aria-hidden="true">
        <i style={{ transform: `scaleX(${tension})` }} />
      </span>
    </div>
  );
}
