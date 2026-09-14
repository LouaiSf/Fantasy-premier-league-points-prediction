"use client";

import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { clubStyle } from "@/lib/club-colors";
import { crestUrl, money, num } from "@/lib/format";
import type { TeamRecord } from "@/lib/types";

function fixtureRibbon(team: TeamRecord | undefined, gameweek: number | null) {
  if (!team || gameweek == null) return [];
  return team.fixtures
    .filter((fixture) => fixture.gameweek >= gameweek)
    .sort((a, b) => a.gameweek - b.gameweek)
    .slice(0, 5);
}

export function PlayerDrawer() {
  const { selectedPlayer: player, closeProfile, snapshot } = useApp();
  const team = snapshot?.teams.find((t) => t.name === player?.team);
  const ribbon = fixtureRibbon(team, snapshot?.gameweek ?? null);
  const predictionAvailable = snapshot?.prediction_available ?? false;

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
                    <img
                      className="drawer-crest"
                      src={crestUrl(team.code)}
                      alt=""
                      aria-hidden="true"
                      width={104}
                      height={104}
                    />
                  )}
                  <span className="ghost-num drawer-ghostnum" aria-hidden="true">
                    {player.position}
                  </span>
                  {player.photo && (
                    <div className="drawer-portrait">
                      <PlayerPhoto src={player.photo} alt="" width={160} height={200} />
                    </div>
                  )}
                  <div className="drawer-id">
                    <span className="kicker">
                      {player.team} {player.flag ?? ""}
                    </span>
                    <h2 id="drawerName">{player.web_name || player.name}</h2>
                    <div className="drawer-meta">
                      <span>{player.position}</span>
                      <span>{money(player.value_m)}</span>
                      <span>{num(player.selected_by)}% owned</span>
                    </div>
                  </div>
                  <div className="drawer-status" data-status={player.status !== "a" ? "out" : "fit"}>
                    {player.news || (player.status === "a" ? "Fully available in the local snapshot." : `Status: ${player.status}`)}
                  </div>
                  <DialogPrimitive.Close
                    className="drawer-close"
                    aria-label="Close player profile"
                  >
                    ×
                  </DialogPrimitive.Close>
                </div>

                <div className="dsec">
                  <div className="slate">
                    <i>Output</i>
                    <b>Season numbers</b>
                    <span className="rule" />
                  </div>
                  <div className="dbugs">
                    <div className="dbug key">
                      <span>Projection</span>
                      <strong>{predictionAvailable ? num(player.predicted_points) : "--"}</strong>
                      <small>{predictionAvailable ? "next GW" : "unavailable"}</small>
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
