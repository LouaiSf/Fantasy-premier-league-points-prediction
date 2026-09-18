"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { api } from "@/lib/api";
import { money, num } from "@/lib/format";
import { previewSquad } from "@/lib/squad";
import { Pitch } from "@/components/team/pitch";
import { SquadEditor } from "@/components/team/squad-editor";
import { PlayerPhoto } from "@/components/player-photo";
import { Loading } from "@/components/loading";
import { ModelInfo } from "@/components/model-info";

// The FPL budget every manager starts a season with.
const BUDGET = 100.0;

export default function TeamPage() {
  const {
    snapshot,
    loading,
    error,
    squadPlayers,
    squadElements,
    teamResult,
    setTeamResult,
    setSquadElements,
    toast,
    openProfile,
  } = useApp();
  const [picking, setPicking] = React.useState(false);
  const [liningUp, setLiningUp] = React.useState(false);

  if (loading) {
    return (
      <section className="page">
        <div className="shell">
          <Loading label="Loading season data…" />
        </div>
      </section>
    );
  }

  if (error || !snapshot) {
    return (
      <section className="page">
        <div className="shell shell--lg">
          <div className="pitch-empty">
            <h2>Platform data unavailable</h2>
            <p>{error}</p>
          </div>
        </div>
      </section>
    );
  }

  const preview = teamResult ?? previewSquad(squadPlayers);
  const xiPoints = preview
    ? "xi_points" in preview
      ? preview.xi_points
      : preview.xiPoints
    : null;
  const predictionAvailable = snapshot.prediction_available;
  // FPL gives every manager 100.0m. Prices move during a season, so a squad
  // saved last week can be worth more than the budget that bought it -- show
  // that as a negative rather than clamping it to zero and hiding the problem.
  const bank = preview ? BUDGET - preview.spend : 0;
  const flagged = squadPlayers.filter(
    (player) => player.status !== "a" || (player.chance_of_playing_next_round ?? 100) < 100,
  );

  async function autoPick() {
    setPicking(true);
    try {
      const result = await api.squad({ budget: BUDGET, lock: [], ban: [] });
      setSquadElements([...result.xi, ...result.bench].map((player) => player.element));
      setTeamResult(result);
      toast("Optimal squad loaded from the prediction pipeline.");
    } catch (err) {
      toast((err as Error).message);
    } finally {
      setPicking(false);
    }
  }

  async function optimiseLineup() {
    if (squadPlayers.length !== 15) {
      toast("Save a legal 15-player squad first.");
      return;
    }
    setLiningUp(true);
    try {
      const result = await api.lineup({ elements: squadElements });
      setTeamResult(result);
      toast("Starting XI, bench order and armband picks updated.");
    } catch (err) {
      toast((err as Error).message);
    } finally {
      setLiningUp(false);
    }
  }

  return (
    <section className="page" aria-label="My team">
      <div className="hero-team">
        <div className="hero-glow" aria-hidden="true" />
        <div className="hero-rays" aria-hidden="true" />
        <div className="hero-blade" aria-hidden="true" />
        <div className="shell hero-grid">
          <div className="hero-copy">
            <p className="eyebrow">Match centre</p>
            <h1 className="hero-title">
              My<em>Team</em>
            </h1>
            <div className="hero-rule" aria-hidden="true" />
            <p className="hero-lede">
              Set a legal squad, inspect availability, and put the model&apos;s best eleven on the
              turf.
            </p>
          </div>
          <div className="hero-numwrap" aria-hidden="true">
            <span className="hero-gw">{snapshot.gameweek ?? "--"}</span>
            <span className="hero-gw-ghost">{snapshot.gameweek ?? "--"}</span>
            <span className="hero-gw-tag">Gameweek</span>
          </div>
        </div>
        <div className="shell hero-strip" aria-label="Squad summary">
          <div className="cell">
            <span>Season</span>
            <strong>{snapshot.season}</strong>
          </div>
          <div className="cell">
            <span>Local players</span>
            <strong>{snapshot.players.length}</strong>
          </div>
          <div className="cell">
            <span>Squad cost</span>
            <strong>{preview ? money(preview.spend) : "--"}</strong>
          </div>
          <div className="cell">
            <span>XI projection</span>
            <strong>{preview && predictionAvailable ? num(xiPoints) : "N/A"}</strong>
          </div>
          <div className="cell">
            <span>Predictions</span>
            <strong>{predictionAvailable ? "Ready" : "Unavailable"}</strong>
          </div>
        </div>
        {predictionAvailable && (
          <div className="shell">
            <ModelInfo model={snapshot.model} timestamp={snapshot.prediction_timestamp} />
          </div>
        )}
      </div>

      <div className="pitch-zone">
        <div className="shell pitch-layout">
          <div>
            <div className="pitch-head">
              <h2>Starting XI</h2>
              <span className="kicker">{preview ? `Formation ${preview.formation}` : "No squad selected"}</span>
              <SquadEditor />
            </div>
            <Pitch />
            {flagged.length > 0 && (
              <div className="pitch-alert">
                <b>Squad alert</b>
                <span>
                  {flagged.length} player{flagged.length === 1 ? "" : "s"} flagged: {" "}
                  {flagged.map((player) => player.web_name || player.name).join(", ")}
                </span>
                <button className="btn sm secondary" type="button" onClick={() => openProfile(flagged[0])}>
                  Open {flagged[0].web_name}
                </button>
              </div>
            )}
          </div>

          <aside className="rail" aria-label="Matchday controls">
            <section className="rail-block">
              <p className="eyebrow muted">
                Predicted output
              </p>
              <h2>Matchday read</h2>
              <div className="rail-stat">
                <span>Starting XI projection</span>
                <strong>{preview && predictionAvailable ? num(xiPoints) : "N/A"}</strong>
              </div>
              <div className="rail-stat">
                <span>Formation</span>
                <strong>{preview?.formation ?? "--"}</strong>
              </div>
              <div className="rail-stat">
                <span>Captain</span>
                <strong>{preview?.captain?.web_name || preview?.captain?.name || "--"}</strong>
              </div>
              <div className="rail-stat">
                <span>Vice-captain</span>
                <strong>{preview?.vice_captain?.web_name || preview?.vice_captain?.name || "--"}</strong>
              </div>
              <div className="rail-stat">
                <span>Squad availability</span>
                <strong>
                  {squadPlayers.length - flagged.length}/{squadPlayers.length || 15}
                </strong>
              </div>
              <div className="rail-stat">
                <span>In the bank</span>
                <strong className={bank < 0 ? "is-over" : undefined}>
                  {preview ? money(bank) : "--"}
                </strong>
              </div>
              <button
                className="btn w-full"
                type="button"
                style={{ marginTop: 14 }}
                disabled={!predictionAvailable || squadPlayers.length !== 15 || liningUp}
                onClick={optimiseLineup}
              >
                {liningUp ? "Optimising lineup…" : "Optimise saved lineup"}
              </button>
              <button
                className="btn secondary w-full"
                type="button"
                style={{ marginTop: 8 }}
                disabled={!predictionAvailable || picking}
                onClick={autoPick}
              >
                {picking ? "Optimising…" : "Run auto-pick"}
              </button>
              {!predictionAvailable && (
                <p style={{ fontSize: 11, color: "var(--muted-mid)", marginTop: 8 }}>
                  {snapshot.prediction_error ?? "A matching prediction export is required."}
                </p>
              )}
            </section>

            <section className="rail-block">
              <p className="eyebrow muted">
                Dugout dock
              </p>
              <h2>Bench order</h2>
              <div className="bench">
                {preview && "bench" in preview
                  ? preview.bench.map((player) => (
                      <button
                        key={player.element}
                        type="button"
                        className="bench-player"
                        onClick={() => openProfile(player)}
                      >
                        <span>{player.position}</span>
                        <strong>{player.web_name || player.name}</strong>
                        <em>{num(player.predicted_points ?? player.form)}</em>
                        {player.photo && (
                          <div className="shot">
                            <PlayerPhoto src={player.photo} alt="" loading="lazy" />
                          </div>
                        )}
                      </button>
                    ))
                  : <p className="empty-copy">No bench until a squad is saved.</p>}
              </div>
            </section>

            <section className="rail-block">
              <p className="eyebrow muted">
                Availability desk
              </p>
              <h2>Squad alerts</h2>
              {flagged.length ? (
                <div className="squad-alerts-list">
                  {flagged.map((player) => (
                    <p key={player.element} className="squad-alerts-row">
                      <strong>{player.web_name}</strong>
                      <br />
                      {player.news || `${player.chance_of_playing_next_round ?? 0}% chance of playing`}
                    </p>
                  ))}
                </div>
              ) : (
                <p className="empty-copy">
                  {squadPlayers.length
                    ? "All selected players are currently marked available."
                    : "No squad loaded."}
                </p>
              )}
            </section>
          </aside>
        </div>
      </div>
    </section>
  );
}
