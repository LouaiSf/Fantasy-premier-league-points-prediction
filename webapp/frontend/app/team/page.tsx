"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { api } from "@/lib/api";
import { money, num } from "@/lib/format";
import { previewSquad } from "@/lib/squad";
import { Pitch } from "@/components/team/pitch";
import { SquadEditor } from "@/components/team/squad-editor";
import { PlayerPhoto } from "@/components/player-photo";

export default function TeamPage() {
  const { snapshot, loading, error, squadPlayers, teamResult, setTeamResult, toast, openProfile } =
    useApp();
  const [picking, setPicking] = React.useState(false);

  if (loading) {
    return (
      <section className="page">
        <div className="shell" style={{ paddingBlock: "var(--space-16)" }}>
          <p>Loading the local season data…</p>
        </div>
      </section>
    );
  }

  if (error || !snapshot) {
    return (
      <section className="page">
        <div className="shell" style={{ paddingBlock: "var(--space-16)" }}>
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
  const flagged = squadPlayers.filter(
    (player) => player.status !== "a" || (player.chance_of_playing_next_round ?? 100) < 100,
  );

  async function autoPick() {
    setPicking(true);
    try {
      const result = await api.squad({ budget: 100, lock: [], ban: [] });
      setTeamResult(result);
      toast("Optimal squad loaded from the prediction pipeline.");
    } catch (err) {
      toast((err as Error).message);
    } finally {
      setPicking(false);
    }
  }

  return (
    <section className="page">
      <div className="hero-team">
        <div className="mane" aria-hidden="true" />
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
              <p className="eyebrow" style={{ color: "var(--muted-mid)" }}>
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
                <span>Squad availability</span>
                <strong>
                  {squadPlayers.length - flagged.length}/{squadPlayers.length || 15}
                </strong>
              </div>
              <button
                className="btn"
                type="button"
                style={{ width: "100%", marginTop: 14 }}
                disabled={!predictionAvailable || picking}
                onClick={autoPick}
              >
                {picking ? "Optimising…" : "Run auto-pick"}
              </button>
              {!predictionAvailable && (
                <p style={{ fontSize: 11, color: "var(--muted-mid)", marginTop: 8 }}>
                  Restore predictions_next_gw.csv to enable the optimiser.
                </p>
              )}
            </section>

            <section className="rail-block">
              <p className="eyebrow" style={{ color: "var(--muted-mid)" }}>
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
              <p className="eyebrow" style={{ color: "var(--muted-mid)" }}>
                Availability desk
              </p>
              <h2>Squad alerts</h2>
              {flagged.length ? (
                <div style={{ display: "grid", gap: 8 }}>
                  {flagged.map((player) => (
                    <p key={player.element} style={{ margin: 0, fontSize: 12 }}>
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
