"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { ClubCrest } from "@/components/club-crest";
import { clubStyle } from "@/lib/club-colors";
import { money, num } from "@/lib/format";
import type { PlayerRecord, TeamRecord } from "@/lib/types";
import { Loading } from "@/components/loading";
import { ModelInfo } from "@/components/model-info";

function captainScore(player: PlayerRecord, predictionAvailable: boolean): number {
  return predictionAvailable ? Number(player.predicted_points ?? 0) : Number(player.form ?? 0);
}

// Goalkeepers are excluded from the armband entirely rather than ranked and
// left to lose. A keeper's ceiling is a clean sheet, a handful of saves and
// three bonus -- so even in the rare week where one tops a projection,
// doubling it is the wrong bet against any starting attacker. Over the
// 2024-25 and 2025-26 holdout seasons, dropping them lifted the mean return
// of the top pick from 6.49 to 6.71 points against the two-stage model, and
// from 6.34 to 6.36 against the single-stage one.

// Predictions for players with no PL history lean on baseline priors rather
// than their own form, so at a near-tied score a proven player is the safer
// armband -- only break the tie this way, never override a real gap.
function compareCaptains(a: PlayerRecord, b: PlayerRecord, predictionAvailable: boolean): number {
  const diff = captainScore(b, predictionAvailable) - captainScore(a, predictionAvailable);
  if (Math.abs(diff) < 0.3) {
    const hasHistoryA = a.has_prior_history !== false;
    const hasHistoryB = b.has_prior_history !== false;
    if (hasHistoryA !== hasHistoryB) return hasHistoryA ? -1 : 1;
  }
  return diff;
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
  const [selectedElement, setSelectedElement] = React.useState<number | null>(null);

  if (loading || !snapshot) {
    return (
      <section className="page">
        <div className="shell">
          <Loading label="Loading season data…" />
        </div>
      </section>
    );
  }

  const predictionAvailable = snapshot.prediction_available;
  const basePool = pool === "squad" ? squadPlayers : snapshot.players;
  const ranked = [...basePool]
    .filter((player) => player.status === "a")
    .filter((player) => player.position !== "GK")
    .sort((a, b) => compareCaptains(a, b, predictionAvailable))
    .slice(0, 10);
  const topPick = ranked[0] ?? null;
  const lead = (selectedElement != null && ranked.find((p) => p.element === selectedElement)) || topPick;
  const runnerUp = ranked.find((p) => p.element !== lead?.element) ?? null;
  const teamByName = new Map(snapshot.teams.map((team) => [team.name, team]));
  const leadTeam = lead ? teamByName.get(lead.team) : undefined;
  const leadFixture = lead ? nextFixture(leadTeam, snapshot.gameweek) : null;
  const leadRisk = lead ? riskFor(lead) : null;

  return (
    <section className="page cap-page paper-scope" aria-label="Captain and form">
      <div className="cap-hero" style={lead ? clubStyle(lead.team) : undefined}>
        {lead && (
          <>
            {leadTeam && (
              <ClubCrest
                className="cap-crest"
                code={leadTeam.code}
                team={leadTeam.name}
                shortName={leadTeam.short_name}
                aria-hidden="true"
              />
            )}
            <div className="cap-shot" aria-hidden="true">
              <PlayerPhoto
                src={lead.photo_large ?? lead.photo ?? undefined}
                fallbackSrc={lead.photo ?? undefined}
                alt={lead.name}
                name={lead.name}
                width={250}
                height={250}
                loading="eager"
                fetchPriority="high"
              />
            </div>
            <span className="cap-armband">
              <span className="cap-marker-mark" aria-hidden="true">C</span> Captain pick
            </span>
          </>
        )}
        <div className="shell cap-inner">
          <div className="cap-copy">
            <span className="eyebrow">Armband desk</span>
            <h1>
              Captain
              <span>&amp; Form</span>
            </h1>
            <p className="cap-quote">
              {lead && lead.element === topPick?.element
                ? `${lead.web_name} leads the ${pool === "squad" ? "squad" : "league"} pool on ${
                    predictionAvailable ? "projected points" : "current form"
                  }, at ${num(captainScore(lead, predictionAvailable))}.`
                : lead
                  ? `Your armband pick, at ${num(captainScore(lead, predictionAvailable))} ${
                      predictionAvailable ? "projected points" : "form"
                    }.`
                  : "No available candidates in this pool yet."}
            </p>
            {lead && (
              <div className="cap-tags">
                <span className="solid">{lead.team}</span>
                <span>{lead.position}</span>
                {leadFixture && (
                  <span>
                    Next: {leadFixture.opponent} ({leadFixture.venue}) · FDR {leadFixture.difficulty}
                  </span>
                )}
                {leadRisk && <span>{leadRisk.label}</span>}
              </div>
            )}
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
          {predictionAvailable && (
            <ModelInfo model={snapshot.model} timestamp={snapshot.prediction_timestamp} />
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
            const isSelected = lead?.element === player.element;
            return (
              <div
                key={player.element}
                role="button"
                tabIndex={0}
                className={`cand${index === 0 ? " is-lead" : ""}${isSelected ? " is-selected" : ""}`}
                style={{ ...clubStyle(player.team), "--i": index } as React.CSSProperties}
                aria-pressed={isSelected}
                onClick={() => setSelectedElement(player.element)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setSelectedElement(player.element);
                  }
                }}
              >
                <span className="cand-rank">{String(index + 1).padStart(2, "0")}</span>
                <span className="shot">
                  <PlayerPhoto src={player.photo ?? undefined} alt={player.name} name={player.name} loading="lazy" />
                </span>
                <span className="cand-id">
                  <b>
                    {player.web_name || player.name}
                    {player.has_prior_history === false && <span className="badge new">New</span>}
                  </b>
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
                  <button
                    type="button"
                    className="cand-view"
                    onClick={(event) => {
                      event.stopPropagation();
                      openProfile(player);
                    }}
                  >
                    Profile
                  </button>
                </span>
              </div>
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
                <div className="shot">
                  <PlayerPhoto
                    src={lead.photo_large ?? lead.photo ?? undefined}
                    fallbackSrc={lead.photo ?? undefined}
                    alt={lead.name}
                    name={lead.name}
                  />
                </div>
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
                        <i
                          className={`duel-a${Number(a) >= Number(b) ? " is-leader" : ""}`}
                          style={{ "--w": `${(Number(a) / total) * 100}%` } as React.CSSProperties}
                        />
                        <i
                          className={`duel-b${Number(b) > Number(a) ? " is-leader" : ""}`}
                          style={{ "--w": `${(Number(b) / total) * 100}%` } as React.CSSProperties}
                        />
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
                <div className="shot">
                  <PlayerPhoto
                    src={runnerUp.photo_large ?? runnerUp.photo ?? undefined}
                    fallbackSrc={runnerUp.photo ?? undefined}
                    alt={runnerUp.name}
                    name={runnerUp.name}
                  />
                </div>
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
