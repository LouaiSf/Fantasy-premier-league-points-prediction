"use client";

import { useApp } from "@/components/providers/app-provider";
import { PlayerMarker } from "@/components/team/player-marker";
import { previewSquad } from "@/lib/squad";
import type { PlayerRecord } from "@/lib/types";

const LINES: PlayerRecord["position"][] = ["GK", "DEF", "MID", "FWD"];

export function Pitch() {
  const { squadPlayers, teamResult } = useApp();
  const result = teamResult ?? previewSquad(squadPlayers);

  if (!result) {
    return (
      <div className="pitch" aria-label="Starting eleven">
        <div className="pitch-lines" aria-hidden="true">
          <div className="half" />
          <div className="circle" />
          <div className="box top" />
          <div className="box bottom" />
          <div className="six top" />
          <div className="six bottom" />
          <div className="spot top" />
          <div className="spot bottom" />
        </div>
        <div className="formation" style={{ display: "grid", placeItems: "center" }}>
          <div className="pitch-empty">
            <span className="eyebrow">Squad required</span>
            <h2>Build your 15</h2>
            <p>Use the squad editor, or restore the local prediction export to run the optimiser.</p>
          </div>
        </div>
      </div>
    );
  }

  const captainName = "captain" in result ? result.captain?.name : undefined;
  const xi = "xi" in result ? result.xi : [];

  return (
    <div className="pitch" aria-label="Starting eleven">
      <div className="pitch-lines" aria-hidden="true">
        <div className="half" />
        <div className="circle" />
        <div className="box top" />
        <div className="box bottom" />
        <div className="six top" />
        <div className="six bottom" />
        <div className="spot top" />
        <div className="spot bottom" />
      </div>
      <div className="formation">
        {LINES.map((position) => {
          const line = xi.filter((player) => player.position === position);
          if (!line.length) return null;
          return (
            <div className="player-line" key={position}>
              {line.map((player) => (
                <PlayerMarker
                  key={player.element}
                  player={player}
                  isCaptain={player.name === captainName}
                />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
