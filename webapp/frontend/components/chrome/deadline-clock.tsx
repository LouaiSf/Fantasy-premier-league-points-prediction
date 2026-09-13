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

function formatCountdown(ms: number): string {
  if (ms <= 0) return "Locked";
  const totalMinutes = Math.floor(ms / 60000);
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;
  return `${days}d ${hours}h ${minutes}m`;
}

export function DeadlineClock() {
  const { snapshot } = useApp();
  const [now, setNow] = React.useState(() => Date.now());

  React.useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);

  const deadline = earliestKickoff(snapshot);
  if (!deadline) return null;

  const remaining = deadline.getTime() - now;
  const urgent = remaining > 0 && remaining < 24 * 60 * 60 * 1000;
  const tension = Math.min(100, Math.max(0, 100 - (remaining / WEEK_MS) * 100));

  return (
    <div className={`deadline${urgent ? " urgent" : ""}`} aria-live="polite">
      <strong>GW{snapshot?.gameweek} first kickoff</strong>
      <span>{formatCountdown(remaining)}</span>
      <div className="deadline-tension" aria-hidden="true">
        <i style={{ width: `${tension}%` }} />
      </div>
    </div>
  );
}
