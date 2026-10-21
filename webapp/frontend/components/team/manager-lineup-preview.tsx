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
          <span className="eyebrow muted">Public lineup · GW{lineup.lineup_gameweek}</span>
          <h2>{lineup.manager.team_name || "Unnamed team"}</h2>
          <p>{lineup.manager.manager_name || "Unnamed manager"} · Entry {lineup.manager.entry_id}</p>
        </div>
        <button className="btn ghost sm" type="button" onClick={onClose}>Close preview</button>
      </div>
      <div className="manager-preview-stats">
        <span><b>Overall rank</b>{lineup.overall_rank ?? "--"}</span>
        <span><b>Total points</b>{lineup.total_points ?? "--"}</span>
        <span><b>Bank</b>{lineup.bank == null ? "--" : money(lineup.bank)}</span>
        <span><b>Active chip</b>{lineup.active_chip ?? "None"}</span>
      </div>
      <div className="manager-preview-columns">
        <div>
          <span className="kicker">Starting XI</span>
          <ol className="manager-pick-list">
            {xi.map((pick) => (
              <li key={pick.element}>
                <span>{pick.position}</span>
                <strong>{playerLabel(byElement.get(pick.element))}</strong>
                {pick.is_captain && <em>Captain</em>}
                {pick.is_vice_captain && <em>Vice</em>}
              </li>
            ))}
          </ol>
        </div>
        <div>
          <span className="kicker">Bench order</span>
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
            {lineup.missing_elements.length} player{lineup.missing_elements.length === 1 ? "" : "s"} are missing from this season&apos;s local snapshot: {lineup.missing_elements.join(", ")}.
          </p>
        )}
        <button className="btn" type="button" onClick={onImport} disabled={unresolved || ordered.length !== 15 || importing}>
          {importing ? "Saving team…" : "Set as my team"}
        </button>
      </div>
    </section>
  );
}
