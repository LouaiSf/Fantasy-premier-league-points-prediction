"use client";

import * as React from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { ClubCrest } from "@/components/club-crest";
import { api } from "@/lib/api";
import { clubStyle } from "@/lib/club-colors";
import { money, num } from "@/lib/format";
import Link from "next/link";
import { Fdr, Pos, Proj } from "@/components/signage";
import { Icon } from "@/components/icons";
import { fixtureText, whyLine } from "@/lib/why";
import type { PlayerHistoryRecord, TeamRecord } from "@/lib/types";

function fixtureRibbon(team: TeamRecord | undefined, gameweek: number | null) {
  if (!team || gameweek == null) return [];
  return team.fixtures
    .filter((fixture) => fixture.gameweek >= gameweek)
    .sort((a, b) => a.gameweek - b.gameweek)
    .slice(0, 5);
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

  const projection = predictionAvailable ? player?.predicted_points ?? null : null;
  const form5 = player ? recentForm(visibleHistory, player.form) : 0;
  const peak = Math.max(...visibleHistory.map((row) => Math.abs(row.total_points)), 1);
  const flaggedNow = player ? player.status !== "a" || (player.chance_of_playing_next_round ?? 100) < 100 : false;
  const statusText = player
    ? player.news || (player.status === "a" ? "Fit and available." : "Not available.")
    : "";

  return (
    <DialogPrimitive.Root open={Boolean(player)} onOpenChange={(open) => !open && closeProfile()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop className="scrim" />
        <DialogPrimitive.Popup className="drawer" aria-labelledby="drawerName">
          {player && (
            <>
              <div className="drawer-scroll">
                <header className="dossier" style={clubStyle(player.team)}>
                  {team && (
                    <ClubCrest
                      className="dossier-crest"
                      code={team.code}
                      team={team.name}
                      shortName={team.short_name}
                      size={100}
                      width={150}
                      height={150}
                      aria-hidden="true"
                    />
                  )}
                  <div className="dossier-cutout" aria-hidden="true">
                    <PlayerPhoto
                      key={player.element}
                      src={player.photo_large ?? player.photo ?? undefined}
                      fallbackSrc={player.photo ?? undefined}
                      alt=""
                      name={player.name}
                      variant="hero"
                    />
                  </div>
                  <div className="dossier-id">
                    <span className="dossier-meta">
                      <Pos pos={player.position} />
                      <span>{player.team}</span>
                    </span>
                    <h2 id="drawerName">{player.web_name || player.name}</h2>
                    {player.web_name && player.web_name !== player.name && <p className="dossier-full">{player.name}</p>}
                  </div>
                  <DialogPrimitive.Close className="drawer-close" aria-label="Close profile">
                    <Icon name="close" size={22} />
                  </DialogPrimitive.Close>
                </header>

                <div className={`dossier-status${flaggedNow ? " is-flag" : ""}`}>
                  <Icon name={flaggedNow ? "alert" : "check"} size={18} />
                  <span>{statusText}</span>
                </div>

                <div className="dossier-figures">
                  <span>
                    <small>This week</small>
                    <Proj value={projection} suffix="pts" />
                  </span>
                  <span>
                    <small>Price</small>
                    <b>{money(player.value_m)}</b>
                  </span>
                  <span>
                    <small>Owned by</small>
                    <b>{num(player.selected_by)}%</b>
                  </span>
                  <span>
                    <small>Last five games</small>
                    <b>
                      {num(form5)} <em>a game</em>
                    </b>
                  </span>
                </div>

                <section className="dsec">
                  <h3>This week</h3>
                  <p className="dsec-lede">
                    {nextUp ? (
                      <>
                        {whyLine(player, nextUp)}.{" "}
                        {projection != null ? (
                          <>
                            We expect about <b>{num(projection)} points</b>.
                          </>
                        ) : null}
                      </>
                    ) : (
                      "No game this gameweek."
                    )}
                  </p>
                  {player.has_prior_history === false && (
                    <p className="note note--warn">
                      New to the league, so this projection leans on how players in his position usually do. Treat it as a rough guide.
                    </p>
                  )}
                </section>

                {ribbon.length > 0 && (
                  <section className="dsec">
                    <h3>Next {ribbon.length} games</h3>
                    <ol className="fixrun">
                      {ribbon.map((fixture) => (
                        <li key={`${fixture.gameweek}-${fixture.opponent}`}>
                          <small>GW{fixture.gameweek}</small>
                          <Fdr fixture={fixture} />
                          <span className="sr-only">{fixtureText(fixture)}</span>
                        </li>
                      ))}
                    </ol>
                  </section>
                )}

                <section className="dsec">
                  <h3>Recent points</h3>
                  {visibleHistoryLoading ? (
                    <div className="skel" style={{ height: 120 }} aria-label="Loading recent games" />
                  ) : visibleHistory.length > 0 ? (
                    <>
                      <div
                        className="pointsbars"
                        role="img"
                        aria-label={`Points in recent gameweeks: ${visibleHistory.map((row) => `GW${row.gameweek} ${row.total_points}`).join(", ")}`}
                      >
                        {visibleHistory.map((row, idx) => {
                          const height = Math.max(4, Math.round((Math.abs(row.total_points) / peak) * 100));
                          const tone = row.total_points < 0 ? " is-neg" : row.total_points >= 10 ? " is-haul" : row.minutes === 0 ? " is-blank" : "";
                          return (
                            <span className="pointsbar" key={`${row.season}-${row.gameweek}-${idx}`} style={{ "--i": idx } as React.CSSProperties}>
                              <b>{row.total_points}</b>
                              <i className={tone} style={{ height: `${height}%` }} />
                              <small>{row.gameweek}</small>
                            </span>
                          );
                        })}
                      </div>
                      <details className="dsec-more">
                        <summary>
                          Game by game <Icon name="chevron-down" size={16} />
                        </summary>
                        <table className="table">
                          <thead>
                            <tr>
                              <th>GW</th>
                              <th>Opponent</th>
                              <th className="num">Mins</th>
                              <th className="num">G / A</th>
                              <th className="num">Pts</th>
                            </tr>
                          </thead>
                          <tbody>
                            {visibleHistory.map((row, idx) => (
                              <tr key={`${row.season}-${row.gameweek}-${idx}`}>
                                <td>{row.gameweek}</td>
                                <td>
                                  {row.opponent_name || row.opponent} ({row.was_home ? "H" : "A"})
                                </td>
                                <td className="num">{row.minutes}</td>
                                <td className="num">
                                  {row.goals_scored} / {row.assists}
                                </td>
                                <td className="num">
                                  <b>{row.total_points}</b>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </details>
                    </>
                  ) : (
                    <p className="note">No games recorded for him yet this season.</p>
                  )}
                </section>

                <section className="dsec">
                  <h3>Season so far</h3>
                  <dl className="statgrid">
                    <div><dt>Points</dt><dd>{player.total_points}</dd></div>
                    <div><dt>Minutes</dt><dd>{player.minutes.toLocaleString()}</dd></div>
                    <div><dt>Points per 90</dt><dd>{player.minutes > 0 ? num((player.total_points * 90) / player.minutes) : "–"}</dd></div>
                    <div><dt>Goals</dt><dd>{player.goals_scored}</dd></div>
                    <div><dt>Assists</dt><dd>{player.assists}</dd></div>
                    <div><dt>Clean sheets</dt><dd>{player.clean_sheets}</dd></div>
                    <div><dt>Bonus</dt><dd>{player.bonus}</dd></div>
                    <div><dt>Expected goals</dt><dd>{num(player.expected_goals, 1)}</dd></div>
                    <div><dt>Expected assists</dt><dd>{num(player.expected_assists, 1)}</dd></div>
                  </dl>
                </section>

                <section className="dsec">
                  <h3>Transfers this week</h3>
                  <p className="dsec-lede">
                    <b className={netTransfers > 0 ? "is-up" : netTransfers < 0 ? "is-down" : undefined}>
                      {netTransfers > 0 ? "+" : netTransfers < 0 ? "−" : ""}
                      {Math.abs(netTransfers).toLocaleString()}
                    </b>{" "}
                    {netTransfers > 0
                      ? "more managers bringing him in than selling."
                      : netTransfers < 0
                        ? "more managers selling him than bringing him in."
                        : "No net movement."}{" "}
                    <span className="note">
                      {transfersIn.toLocaleString()} in, {transfersOut.toLocaleString()} out.
                    </span>
                  </p>
                </section>
              </div>
              <div className="drawer-actions">
                <Link className="btn btn--line" href={`/comparison?a=${player.element}`} onClick={() => closeProfile()}>
                  Compare him <Icon name="swap" size={18} />
                </Link>
                <DialogPrimitive.Close className="btn">Done</DialogPrimitive.Close>
              </div>
            </>
          )}
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
