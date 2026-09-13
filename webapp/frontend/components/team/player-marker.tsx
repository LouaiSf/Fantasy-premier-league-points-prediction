"use client";

import type { CSSProperties } from "react";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { num } from "@/lib/format";
import type { PlayerRecord } from "@/lib/types";

const CLUB_COLORS: Record<string, [string, string]> = {
  Arsenal: ["#ef0107", "#7a0004"],
  "Aston Villa": ["#95bfe5", "#530c2b"],
  Bournemouth: ["#da291c", "#3a0a06"],
  Brentford: ["#d20000", "#4a0000"],
  "Brighton and Hove Albion": ["#0057b8", "#001e42"],
  Chelsea: ["#034694", "#0a1c42"],
  "Crystal Palace": ["#1b458f", "#8d1c25"],
  Everton: ["#003399", "#001a4d"],
  Fulham: ["#b3121d", "#141414"],
  Liverpool: ["#c8102e", "#5a0010"],
  "Manchester City": ["#6cabdd", "#1c2c5b"],
  "Manchester United": ["#da291c", "#4e0c0c"],
  "Newcastle United": ["#3d3d3d", "#0c0c0c"],
  "Nottingham Forest": ["#dd0000", "#5c0000"],
  Sunderland: ["#e21c21", "#0b0b0b"],
  "Tottenham Hotspur": ["#1d2f6f", "#0a1130"],
  "West Ham United": ["#7a263a", "#2d0e17"],
  "Wolverhampton Wanderers": ["#fdb913", "#6e4e00"],
};

function clubStyle(team: string): CSSProperties {
  const [c1, c2] = CLUB_COLORS[team] ?? ["#555", "#111"];
  return { "--c1": c1, "--c2": c2 } as CSSProperties;
}

export function PlayerMarker({
  player,
  isCaptain,
  isBenchOption,
}: {
  player: PlayerRecord;
  isCaptain?: boolean;
  isBenchOption?: boolean;
}) {
  const { openProfile, snapshot } = useApp();
  const predictionAvailable = snapshot?.prediction_available ?? false;
  const doubt = player.status !== "a" || (player.chance_of_playing_next_round ?? 100) < 100;

  return (
    <button
      type="button"
      className={`pm${isBenchOption ? " is-bench-opt" : ""}`}
      onClick={() => openProfile(player)}
      aria-label={`Open ${player.name} profile`}
    >
      <div className="pm-pred">
        {predictionAvailable ? num(player.predicted_points) : num(player.form)}
      </div>
      {isCaptain && (
        <div className="pm-badge" aria-label="Captain">
          C
        </div>
      )}
      {doubt && (
        <div
          className="pm-flag"
          data-status={player.status === "a" ? "doubt" : player.status === "s" ? "susp" : "out"}
        >
          !
        </div>
      )}
      <div className="pm-bust" style={clubStyle(player.team)}>
        {player.photo && <PlayerPhoto src={player.photo} alt="" loading="lazy" />}
      </div>
      <span className="pm-name" style={clubStyle(player.team)}>
        {player.web_name || player.name}
      </span>
    </button>
  );
}
