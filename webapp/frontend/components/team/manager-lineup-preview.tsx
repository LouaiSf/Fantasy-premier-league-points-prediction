"use client";

import * as React from "react";
import type { ManagerLineup, PlatformSnapshot, PlayerRecord } from "@/lib/types";
import { money } from "@/lib/format";

interface ManagerLineupPreviewProps {
  readonly lineup: ManagerLineup;
  readonly snapshot: PlatformSnapshot;
  readonly importing: boolean;
  readonly onImport: () => void;
  readonly onClose: () => void;
}

function playerLabel(player: PlayerRecord | undefined): string {
  return player?.web_name || player?.name || "Unknown player";
}

export function ManagerLineupPreview({
  lineup,
  snapshot,
  importing,
  onImport,
  onClose,
}: ManagerLineupPreviewProps) {
  const byElement = React.useMemo(
    () => new Map(snapshot.players.map((player) => [player.element, player])),
    [snapshot.players],
  );
  const ordered = React.useMemo(
    () => [...lineup.picks].sort((a, b) => a.position - b.position),
    [lineup.picks],
  );
  const xi = ordered.filter((pick) => pick.position <= 11);
  const bench = ordered.filter((pick) => pick.position > 11);
  const captain = ordered.find((pick) => pick.is_captain);
  const viceCaptain = ordered.find((pick) => pick.is_vice_captain);
  const unresolved = lineup.missing_elements.length > 0;

  return (
    <section className="manager-preview" aria-label="Public manager lineup preview">
      <div className="manager-preview-head">
        <div>
          <h2>{lineup.manager.team_name || "Unnamed team"}</h2>
          <p>{lineup.manager.manager_name || "Unnamed manager"} · their gameweek {lineup.lineup_gameweek} lineup</p>
        </div>
        <button className="btn btn--ghost btn--sm" type="button" onClick={onClose}>Not this one</button>
      </div>
      <div className="manager-preview-stats">
        <span><b>Overall rank</b>{lineup.overall_rank != null ? lineup.overall_rank.toLocaleString() : "–"}</span>
        <span><b>Total points</b>{lineup.total_points ?? "--"}</span>
        <span><b>Bank</b>{lineup.bank == null ? "--" : money(lineup.bank)}</span>
        <span><b>Active chip</b>{lineup.active_chip ?? "None"}</span>
      </div>
      <div className="manager-preview-columns">
        <div>
          <h3>Starting XI</h3>
          <ol className="manager-pick-list">
            {xi.map((pick) => (
              <li key={pick.element}>
                <span>{pick.position}</span>
                <strong>{playerLabel(byElement.get(pick.element))}</strong>
                {pick.is_captain && <span className="armband">C</span>}
                {pick.is_vice_captain && <span className="armband armband--vice">V</span>}
              </li>
            ))}
          </ol>
        </div>
        <div>
          <h3>Bench</h3>
          <ol className="manager-pick-list manager-pick-list--bench">
            {bench.map((pick) => (
              <li key={pick.element}>
                <span>{pick.position - 11}</span>
                <strong>{playerLabel(byElement.get(pick.element))}</strong>
              </li>
            ))}
          </ol>
        </div>
      </div>
      <div className="manager-preview-actions">
        <p>
          Captain: <b>{playerLabel(byElement.get(captain?.element ?? -1))}</b> · Vice: <b>{playerLabel(byElement.get(viceCaptain?.element ?? -1))}</b>
        </p>
        {unresolved && (
          <p className="manager-preview-warning" role="alert">
            {lineup.missing_elements.length === 1 ? "One of their players isn’t" : `${lineup.missing_elements.length} of their players aren’t`} in our player list yet, so this team can&apos;t come in until the next data update.
          </p>
        )}
        <button className="btn btn--go" type="button" onClick={onImport} disabled={unresolved || ordered.length !== 15 || importing}>
          {importing ? "Bringing it in…" : "This is my team"}
        </button>
      </div>
    </section>
  );
}
