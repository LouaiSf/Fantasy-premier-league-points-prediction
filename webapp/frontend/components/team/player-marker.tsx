"use client";

import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { clubStyle } from "@/lib/club-colors";
import { num } from "@/lib/format";
import type { PlayerRecord } from "@/lib/types";

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
