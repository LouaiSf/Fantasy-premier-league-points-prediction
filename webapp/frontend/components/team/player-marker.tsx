"use client";

import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { clubStyle } from "@/lib/club-colors";
import { num } from "@/lib/format";
import { isFlagged } from "@/lib/why";
import type { PlayerRecord } from "@/lib/types";

export function PlayerMarker({
  player,
  isCaptain,
  isViceCaptain,
}: {
  player: PlayerRecord;
  isCaptain?: boolean;
  isViceCaptain?: boolean;
}) {
  const { openProfile, snapshot } = useApp();
  const predictionAvailable = snapshot?.prediction_available ?? false;
  const value = predictionAvailable ? player.predicted_points : player.form;
  const band = value == null ? "none" : Number(value) >= 6 ? "hi" : Number(value) >= 4 ? "mid" : "lo";
  const doubt = isFlagged(player);

  return (
    <button
      type="button"
      className={`pm${doubt ? " is-flagged" : ""}`}
      onClick={() => openProfile(player)}
      aria-label={`${player.name}${isCaptain ? ", captain" : isViceCaptain ? ", vice-captain" : ""}${doubt ? ", availability flag" : ""}. Open profile`}
    >
      <span className="pm-bust" style={clubStyle(player.team)}>
        <PlayerPhoto src={player.photo ?? undefined} alt="" name={player.name} variant="pitch" loading="lazy" />
      </span>
      {isCaptain && <span className="armband pm-band">C</span>}
      {!isCaptain && isViceCaptain && <span className="armband armband--vice pm-band">V</span>}
      {doubt && (
        <span className="pm-flag" data-status={player.status === "a" ? "doubt" : player.status === "s" ? "susp" : "out"}>
          {player.chance_of_playing_next_round != null && player.status === "a"
            ? `${player.chance_of_playing_next_round}%`
            : player.status === "s" ? "Ban" : "Out"}
        </span>
      )}
      <span className="pm-plate">
        <span className="pm-name">{player.web_name || player.name}</span>
        <span className={`pm-pts proj--${band}`}>{value == null ? "–" : num(value)}</span>
      </span>
    </button>
  );
}
