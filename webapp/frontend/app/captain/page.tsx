"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { clubStyle } from "@/lib/club-colors";
import { money, num } from "@/lib/format";
import type { PlayerRecord, TeamRecord } from "@/lib/types";

function captainScore(player: PlayerRecord, predictionAvailable: boolean): number {
  return predictionAvailable ? Number(player.predicted_points ?? 0) : Number(player.form ?? 0);
}

function riskFor(player: PlayerRecord): { label: string; level: "low" | "med" | "high" } {
  const chance = player.chance_of_playing_next_round ?? 100;
  if (player.status !== "a" || chance < 50) return { label: "High risk", level: "high" };
  if (chance < 100) return { label: "Some doubt", level: "med" };
  return { label: "Nailed on", level: "low" };
}

function nextFixture(team: TeamRecord | undefined, gameweek: number | null) {
  if (!team || gameweek == null) return null;
  return team.fixtures.find((fixture) => fixture.gameweek === gameweek) ?? null;
}

export default function CaptainPage() {
  const { snapshot, loading, squadPlayers, openProfile } = useApp();
  const [pool, setPool] = React.useState<"squad" | "all">("squad");

  if (loading || !snapshot) {
    return (
      <section className="page">
        <div className="shell" style={{ paddingBlock: "var(--space-16)" }}>
          <p>Loading the local season data…</p>
        </div>
      </section>
    );
  }

  const predictionAvailable = snapshot.prediction_available;
  const basePool = pool === "squad" ? squadPlayers : snapshot.players;
  const ranked = [...basePool]
    .filter((player) => player.status === "a")
    .sort((a, b) => captainScore(b, predictionAvailable) - captainScore(a, predictionAvailable))
    .slice(0, 10);
  const lead = ranked[0] ?? null;
  const runnerUp = ranked[1] ?? null;
  const teamByName = new Map(snapshot.teams.map((team) => [team.name, team]));

  return (
    <section className="page cap-page paper-scope">
      <div className="cap-hero">
        <div className="mane" aria-hidden="true" />
        <div className="shell cap-inner">
          <div className="cap-copy">
            <span className="eyebrow">Armband desk</span>
            <h1>
              Captain
              <span>&amp; Form</span>
            </h1>
            <p className="cap-quote">
              {lead
                ? `${lead.web_name} leads the ${pool === "squad" ? "squad" : "league"} pool on ${
                    predictionAvailable ? "projected points" : "current form"
                  }, at ${num(captainScore(lead, predictionAvailable))}.`
                : "No available candidates in this pool yet."}
            </p>
          </div>
          {lead && (
            <div className="cap-metrics">
              <div className="bug">
                <span>{predictionAvailable ? "Projection" : "Form"}</span>
                <strong>{num(captainScore(lead, predictionAvailable))}</strong>
              </div>
              <div className="bug">
                <span>Ownership</span>
                <strong>{num(lead.selected_by)}%</strong>
              </div>
              <div className="bug">
                <span>Price</span>
                <strong>{money(lead.value_m)}</strong>
              </div>
              <div className="bug">
                <span>Club</span>
                <strong>{lead.team_short}</strong>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="shell">
        <div className="sub-head">
          <h3>Captaincy shortlist</h3>
          <span className="rule" />
          <div className="mini-chips" role="group" aria-label="Candidate pool">
            <button
              type="button"
              aria-pressed={pool === "squad"}
              className={`mini-chip${pool === "squad" ? " is-active" : ""}`}
              onClick={() => setPool("squad")}
            >
              My squad
            </button>
            <button
              type="button"
              aria-pressed={pool === "all"}
              className={`mini-chip${pool === "all" ? " is-active" : ""}`}
              onClick={() => setPool("all")}
            >
              All players
            </button>
          </div>
        </div>

        {!predictionAvailable && (
          <p style={{ color: "var(--muted-ink)", fontSize: 13, marginTop: -8, marginBottom: 16 }}>
            Prediction export unavailable — ranked by official FPL form only.
          </p>
        )}

        <div className="runway">
          {ranked.map((player, index) => {
            const fixture = nextFixture(teamByName.get(player.team), snapshot.gameweek);
            const risk = riskFor(player);
            return (
              <button
                key={player.element}
                type="button"
                className={`cand${index === 0 ? " is-lead" : ""}`}
                style={clubStyle(player.team)}
                onClick={() => openProfile(player)}
              >
                <span className="cand-rank">{String(index + 1).padStart(2, "0")}</span>
                <span className="shot">
                  {player.photo && <PlayerPhoto src={player.photo} alt="" loading="lazy" />}
                </span>
                <span className="cand-id">
                  <b>{player.web_name || player.name}</b>
                  <span className="muted">
                    {player.team} · {player.position}
                  </span>
                </span>
                <span className="cand-fix">
                  <span className="muted">Next</span>
                  {fixture ? (
                    <span>
                      {fixture.opponent} ({fixture.venue}) · FDR {fixture.difficulty}
                    </span>
                  ) : (
                    <span>No fixture found</span>
                  )}
                </span>
                <span className="cand-meters">
                  <div className="meter-label">
                    <span>Form</span>
                    <b>{num(player.form)}</b>
                  </div>
                  <div className="meter">
                    <i style={{ width: `${Math.min(100, Number(player.form) * 10)}%` }} />
                  </div>
                  <div className="meter-label">
                    <span>ICT</span>
                    <b>{num(player.ict_index)}</b>
                  </div>
                  <div className="meter">
                    <i style={{ width: `${Math.min(100, Number(player.ict_index))}%` }} />
                  </div>
                </span>
                <span className="cand-right">
                  <span className="proj">{num(captainScore(player, predictionAvailable))}</span>
                  <span className="risk" data-risk={risk.level}>
                    {risk.label}
                  </span>
                </span>
              </button>
            );
          })}
          {!ranked.length && <p className="picker-empty">No available candidates in this pool.</p>}
        </div>

        {lead && runnerUp && (
          <>
            <div className="sub-head">
              <h3>Captaincy battle</h3>
              <span className="rule" />
              <small>The top two candidates, head to head</small>
            </div>
            <div className="battle">
              <button
                type="button"
                className="battle-pick"
                style={clubStyle(lead.team)}
                onClick={() => openProfile(lead)}
              >
                {lead.photo && (
                  <div className="shot">
                    <PlayerPhoto src={lead.photo} alt="" />
                  </div>
                )}
                <div className="battle-pick-copy">
                  <span className="eyebrow">Rank 1</span>
                  <h4>{lead.web_name}</h4>
                </div>
              </button>
              <div className="battle-data">
                <h4>Head to head</h4>
                {[
                  ["Projection", captainScore(lead, predictionAvailable), captainScore(runnerUp, predictionAvailable), 1],
                  ["Form", Number(lead.form), Number(runnerUp.form), 1],
                  ["Ownership %", Number(lead.selected_by), Number(runnerUp.selected_by), 1],
                  ["ICT index", Number(lead.ict_index), Number(runnerUp.ict_index), 1],
                ].map(([label, a, b, digits]) => {
                  const total = (Number(a) || 0) + (Number(b) || 0) || 1;
                  return (
                    <div className="duel-row" key={label as string}>
                      <strong>{num(a, digits as number)}</strong>
                      <span className="duel-label">{label}</span>
                      <strong>{num(b, digits as number)}</strong>
                      <div className="duel-track">
                        <i style={{ width: `${(Number(a) / total) * 100}%`, background: "var(--pl-purple)" }} />
                        <i style={{ width: `${(Number(b) / total) * 100}%`, background: "var(--pink)" }} />
                      </div>
                    </div>
                  );
                })}
              </div>
              <button
                type="button"
                className="battle-pick"
                style={clubStyle(runnerUp.team)}
                onClick={() => openProfile(runnerUp)}
              >
                {runnerUp.photo && (
                  <div className="shot">
                    <PlayerPhoto src={runnerUp.photo} alt="" />
                  </div>
                )}
                <div className="battle-pick-copy">
                  <span className="eyebrow">Rank 2</span>
                  <h4>{runnerUp.web_name}</h4>
                </div>
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
