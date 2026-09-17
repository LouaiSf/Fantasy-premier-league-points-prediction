"use client";

import * as React from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { ClubCrest } from "@/components/club-crest";
import { api } from "@/lib/api";
import { clubStyle } from "@/lib/club-colors";
import { money, num } from "@/lib/format";
import { Loading } from "@/components/loading";
import type { PlayerHistoryRecord, TeamRecord } from "@/lib/types";

function fixtureRibbon(team: TeamRecord | undefined, gameweek: number | null) {
  if (!team || gameweek == null) return [];
  return team.fixtures
    .filter((fixture) => fixture.gameweek >= gameweek)
    .sort((a, b) => a.gameweek - b.gameweek)
    .slice(0, 5);
}

// The scale the drawer colours a projection on. A gameweek's predicted points
// average a little over one, so six is a genuinely strong forecast rather than
// an arbitrary round number.
function projectionBand(points: number | null): "is-high" | "is-mid" | "is-low" | "is-none" {
  if (points == null || !Number.isFinite(points)) return "is-none";
  if (points >= 6) return "is-high";
  if (points >= 4) return "is-mid";
  return "is-low";
}

// The model reads a player's recent matches, not the season total, so the form
// shown beside a projection is the same window: the last five gameweeks the
// snapshot has for him. The history endpoint returns oldest first, so the
// recent end is the tail. Falls back to FPL's own form figure when the
// endpoint has nothing.
function recentForm(history: PlayerHistoryRecord[], fallback: number): number {
  const window = history.slice(-5);
  if (!window.length) return fallback;
  return window.reduce((sum, row) => sum + row.total_points, 0) / window.length;
}

function difficultyClass(difficulty: number | undefined): string {
  if (difficulty == null) return "";
  if (difficulty <= 2) return " fdr-easy";
  if (difficulty >= 4) return " fdr-hard";
  return "";
}

export function PlayerDrawer() {
  const { selectedPlayer, closeProfile, snapshot } = useApp();
  // The drawer can be opened from anywhere, and not every caller holds a full
  // record: /api/squad answers with a trimmed shape carrying no minutes, ICT,
  // transfers or expected goals, so a marker on the pitch used to open a
  // drawer with holes in it -- and, once this component started reading
  // transfers_in_event, to throw on the way. Resolve the snapshot's own copy
  // by element and fall back to whatever was passed.
  const player = React.useMemo(() => {
    if (!selectedPlayer) return null;
    const full = snapshot?.players.find((p) => p.element === selectedPlayer.element);
    return full ?? selectedPlayer;
  }, [selectedPlayer, snapshot]);
  const team = snapshot?.teams.find((t) => t.name === player?.team);
  const ribbon = fixtureRibbon(team, snapshot?.gameweek ?? null);
  const nextUp = ribbon[0] ?? null;
  const predictionAvailable = snapshot?.prediction_available ?? false;
  // Heavily transferred in means the market has spotted something; heavily out
  // usually means news the snapshot's status field has not caught up with yet.
  const transfersIn = player?.transfers_in_event ?? 0;
  const transfersOut = player?.transfers_out_event ?? 0;
  const netTransfers = transfersIn - transfersOut;

  const [history, setHistory] = React.useState<PlayerHistoryRecord[]>([]);
  const [historyLoading, setHistoryLoading] = React.useState(false);
  const [historyPlayerId, setHistoryPlayerId] = React.useState<number | null>(null);
  const visibleHistory = historyPlayerId === player?.element ? history : [];
  const visibleHistoryLoading = Boolean(player && historyPlayerId !== player.element) || historyLoading;

  React.useEffect(() => {
    let cancelled = false;
    const playerId = player?.element ?? null;
    const timer = window.setTimeout(() => {
      if (!playerId) {
        setHistory([]);
        setHistoryPlayerId(null);
        setHistoryLoading(false);
        return;
      }

      setHistoryLoading(true);
      void api.playerHistory(playerId).then(
        (data) => {
          if (cancelled) return;
          setHistory(data.history || []);
          setHistoryPlayerId(playerId);
        },
        () => {
          if (cancelled) return;
          setHistory([]);
          setHistoryPlayerId(playerId);
        },
      ).finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    }, 0);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [player?.element]);

  return (
    <DialogPrimitive.Root open={Boolean(player)} onOpenChange={(open) => !open && closeProfile()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop className={`scrim${player ? " is-open" : ""}`} />
        <DialogPrimitive.Popup
          className={`drawer${player ? " is-open" : ""}`}
          aria-labelledby="drawerName"
        >
          {player && (
            <>
              <div className="drawer-scroll">
                <div className="drawer-hero" style={clubStyle(player.team)}>
                  <div className="drawer-texture" aria-hidden="true" />
                  {team && (
                    <ClubCrest
                      className="drawer-crest"
                      code={team.code}
                      team={team.name}
                      shortName={team.short_name}
                      size={104}
                      width={104}
                      height={104}
                      aria-hidden="true"
                    />
                  )}
                  <span className="ghost-num drawer-ghostnum" aria-hidden="true">
                    {player.position}
                  </span>
                  <div className="drawer-portrait">
                    <PlayerPhoto
                      src={player.photo ?? undefined}
                      alt={player.name}
                      name={player.name}
                      width={160}
                      height={200}
                    />
                  </div>
                  <div className="drawer-id">
                    <span className="kicker">
                      {player.team} {player.flag ?? ""}
                    </span>
                    <h2 id="drawerName">
                      {player.web_name || player.name}
                      {player.has_prior_history === false && <span className="badge new">New</span>}
                    </h2>
                    <div className="drawer-meta">
                      <span>{player.position}</span>
                      <span>{money(player.value_m)}</span>
                      <span>{num(player.selected_by)}% owned</span>
                    </div>
                  </div>
                  <div className="drawer-status" data-status={player.status !== "a" ? "out" : "fit"}>
                    {player.news || (player.status === "a" ? "Fully available in the local snapshot." : `Status: ${player.status}`)}
                  </div>
                  {player.has_prior_history === false && (
                    <p className="drawer-new-note">
                      New to the Premier League — predicted points are less reliable and lean on
                      baseline position priors rather than this player&apos;s own history.
                    </p>
                  )}
                  <DialogPrimitive.Close
                    className="drawer-close"
                    aria-label="Close player profile"
                  >
                    ×
                  </DialogPrimitive.Close>
                </div>

                <div className="dsec">
                  <div className="slate">
                    <i>Forecast</i>
                    <b>Next gameweek</b>
                    <span className="rule" />
                  </div>
                  <div className="proj-panel">
                    <div className={`proj-figure ${projectionBand(predictionAvailable ? player.predicted_points : null)}`}>
                      <i>Projected</i>
                      <strong>{predictionAvailable ? num(player.predicted_points) : "--"}</strong>
                      <small>{predictionAvailable ? "points" : "unavailable"}</small>
                    </div>
                    <dl className="proj-why">
                      <div>
                        <dt>Form</dt>
                        <dd>{num(recentForm(visibleHistory, player.form))}</dd>
                      </div>
                      {nextUp && (
                        <>
                          <div>
                            <dt>Opponent</dt>
                            <dd>{nextUp.opponent}</dd>
                          </div>
                          <div>
                            <dt>Venue</dt>
                            <dd>{nextUp.venue === "H" ? "Home" : "Away"}</dd>
                          </div>
                          <div>
                            <dt>Difficulty</dt>
                            <dd className={difficultyClass(nextUp.difficulty).trim()}>
                              {nextUp.difficulty}/5
                            </dd>
                          </div>
                        </>
                      )}
                      <div>
                        <dt>Owned</dt>
                        <dd>{num(player.selected_by)}%</dd>
                      </div>
                    </dl>
                  </div>
                  {player.has_prior_history === false && (
                    <p className="proj-caveat">
                      No prior Premier League record, so this figure comes from position
                      baselines rather than from what this player has actually done.
                    </p>
                  )}
                </div>

                <div className="dsec">
                  <div className="slate">
                    <i>Output</i>
                    <b>Season numbers</b>
                    <span className="rule" />
                  </div>
                  <div className="dbugs">
                    <div className="dbug key">
                      <span>Points / 90</span>
                      <strong>
                        {player.minutes > 0 ? num((player.total_points * 90) / player.minutes) : "0.0"}
                      </strong>
                      <small>rate, not total</small>
                    </div>
                    <div className="dbug">
                      <span>Form</span>
                      <strong>{num(player.form)}</strong>
                    </div>
                    <div className="dbug">
                      <span>Total points</span>
                      <strong>{player.total_points}</strong>
                    </div>
                    <div className="dbug">
                      <span>Minutes</span>
                      <strong>{player.minutes}</strong>
                    </div>
                  </div>
                </div>

                {ribbon.length > 0 && (
                  <div className="dsec">
                    <div className="slate">
                      <i>Schedule</i>
                      <b>Next fixtures</b>
                      <span className="rule" />
                    </div>
                    <div className="fixrib">
                      {ribbon.map((fixture) => (
                        <div key={fixture.gameweek} data-fdr={fixture.difficulty}>
                          <b>{fixture.opponent}</b>
                          <span>
                            GW{fixture.gameweek} · {fixture.venue}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="dsec">
                  <div className="slate">
                    <i>Ladder</i>
                    <b>Recent match history</b>
                    <span className="rule" />
                  </div>
                  {visibleHistoryLoading ? (
                    <Loading label="Loading history…" />
                  ) : visibleHistory.length > 0 ? (
                    <>
                      {/* Bars are scaled to this player's own best in the window,
                          so the shape reads as his rhythm rather than against a
                          league maximum that would flatten most players to nothing. */}
                      <div
                        className="sparkline"
                        role="img"
                        aria-label={`Points in the last ${visibleHistory.length} gameweeks: ${visibleHistory
                          .map((row) => `GW${row.gameweek} ${row.total_points}`)
                          .join(", ")}`}
                      >
                        {visibleHistory.map((row, idx) => {
                          const peak = Math.max(
                            ...visibleHistory.map((r) => Math.abs(r.total_points)),
                            1,
                          );
                          const height = Math.max(
                            4,
                            Math.round((Math.abs(row.total_points) / peak) * 100),
                          );
                          const tone =
                            row.total_points < 0
                              ? " is-negative"
                              : row.total_points >= 10
                                ? " is-haul"
                                : row.minutes === 0
                                  ? " is-blank"
                                  : "";
                          return (
                            <div className="sparkline-col" key={`spark-${row.season}-${row.gameweek}-${idx}`}>
                              <span className="sparkline-label">{row.total_points}</span>
                              <span className="sparkline-track">
                                <span
                                  className={`sparkline-bar${tone}`}
                                  style={{ height: `${height}%` }}
                                />
                              </span>
                              <span className="sparkline-label">{row.gameweek}</span>
                            </div>
                          );
                        })}
                      </div>
                      <table className="stable">
                      <thead>
                        <tr>
                          <th>GW</th>
                          <th>Opponent</th>
                          <th style={{ textAlign: "right" }}>Min</th>
                          <th style={{ textAlign: "right" }}>G/A</th>
                          <th style={{ textAlign: "right" }}>Pts</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleHistory.map((row, idx) => (
                          <tr key={`${row.season}-${row.gameweek}-${idx}`}>
                            <td>
                              GW{row.gameweek}{" "}
                              <small style={{ opacity: 0.6 }}>({row.season})</small>
                            </td>
                            <td>
                              {row.opponent || row.opponent_name} ({row.was_home ? "H" : "A"})
                            </td>
                            <td style={{ textAlign: "right" }}>{row.minutes}</td>
                            <td style={{ textAlign: "right" }}>
                              {row.goals_scored}/{row.assists}
                            </td>
                            <td
                              style={{
                                textAlign: "right",
                                fontWeight: 750,
                                color: row.total_points >= 6 ? "var(--lime)" : "inherit",
                              }}
                            >
                              {row.total_points}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                      </table>
                    </>
                  ) : (
                    <p style={{ color: "var(--muted-ink)", fontSize: 12 }}>
                      No recent gameweek history recorded in local snapshot.
                    </p>
                  )}
                </div>

                <div className="dsec">
                  <div className="slate">
                    <i>Market</i>
                    <b>Transfer momentum</b>
                    <span className="rule" />
                  </div>
                  <div className="xfer-row">
                    <span
                      className={`xfer-net ${
                        netTransfers > 0 ? "is-in" : netTransfers < 0 ? "is-out" : "is-flat"
                      }`}
                    >
                      {netTransfers > 0 ? "+" : ""}
                      {netTransfers.toLocaleString()}
                    </span>
                    <span className="xfer-detail">
                      net this gameweek · {transfersIn.toLocaleString()} in,{" "}
                      {transfersOut.toLocaleString()} out
                    </span>
                  </div>
                </div>

                <div className="dsec">
                  <div className="slate">
                    <i>Table</i>
                    <b>Underlying stats</b>
                    <span className="rule" />
                  </div>
                  <table className="stable">
                    <tbody>
                      <tr>
                        <th>Goals</th>
                        <td>{player.goals_scored}</td>
                      </tr>
                      <tr>
                        <th>Assists</th>
                        <td>{player.assists}</td>
                      </tr>
                      <tr>
                        <th>Clean sheets</th>
                        <td>{player.clean_sheets}</td>
                      </tr>
                      <tr>
                        <th>Bonus</th>
                        <td>{player.bonus}</td>
                      </tr>
                      <tr>
                        <th>ICT index</th>
                        <td>{num(player.ict_index)}</td>
                      </tr>
                      <tr>
                        <th>Expected goals</th>
                        <td>{num(player.expected_goals, 2)}</td>
                      </tr>
                      <tr>
                        <th>Expected assists</th>
                        <td>{num(player.expected_assists, 2)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {!predictionAvailable && (
                  <div className="dsec">
                    <p className="dread">
                      <em>Prediction unavailable.</em> Restore or regenerate the local prediction
                      export to populate forecast metrics for this player.
                    </p>
                  </div>
                )}
              </div>
              <div className="drawer-actions" id="drawerActions">
                <DialogPrimitive.Close className="btn primary">Close</DialogPrimitive.Close>
              </div>
            </>
          )}
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
