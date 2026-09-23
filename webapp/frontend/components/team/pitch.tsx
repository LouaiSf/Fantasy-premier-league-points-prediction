"use client";

import { useApp } from "@/components/providers/app-provider";
import { PlayerMarker } from "@/components/team/player-marker";
import { previewSquad } from "@/lib/squad";
import type { PlayerRecord } from "@/lib/types";

const LINES: PlayerRecord["position"][] = ["GK", "DEF", "MID", "FWD"];

interface PitchResult {
  readonly xi: PlayerRecord[];
  readonly captain: PlayerRecord | null;
  readonly vice_captain: PlayerRecord | null;
}

interface PitchProps {
  /** A presentational result to render instead of the saved team's own
   * (e.g. a transfer plan's suggested XI). Applying it to My Team is the
   * caller's decision, never this component's. */
  readonly result?: PitchResult | null;
  /** The smaller variant used inside the transfer plan's evidence panel. */
  readonly compact?: boolean;
}

export function Pitch({ result: resultProp, compact }: PitchProps = {}) {
  const { squadPlayers, teamResult } = useApp();
  const result = resultProp !== undefined ? resultProp : (teamResult ?? previewSquad(squadPlayers));
  const pitchClassName = `pitch${compact ? " pitch--plan" : ""}`;

  if (!result) {
    return (
      <div className={pitchClassName} aria-label="Starting eleven">
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
        <div className="formation formation--empty">
          <div className="pitch-empty">
            <span className="eyebrow">Squad required</span>
            <h2>Build your 15</h2>
            <p>Use the squad editor, or restore the local prediction export to run the optimiser.</p>
          </div>
        </div>
      </div>
    );
  }

  // Keyed on the element, not the name: two current players can share a
  // surname (there are two Palmers and two Palacios in the 2026-27 export),
  // and matching on the name gives both of them the armband.
  const captainId = result.captain?.element;
  const viceCaptainId = result.vice_captain?.element;
  const xi = result.xi;

  return (
    <div className={pitchClassName} aria-label="Starting eleven">
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
                  isCaptain={player.element === captainId}
                  isViceCaptain={player.element === viceCaptainId}
                />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
