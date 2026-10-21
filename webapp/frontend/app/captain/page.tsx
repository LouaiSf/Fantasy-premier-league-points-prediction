"use client";

import * as React from "react";
import { m } from "motion/react";
import { useApp } from "@/components/providers/app-provider";
import { money, num } from "@/lib/format";
import { isFlagged, nextFixtureFor, whyLine } from "@/lib/why";
import type { PlayerRecord } from "@/lib/types";
import { Skeleton } from "@/components/skeleton";
import { Face, Fdr, GateSign, PlateFact, Pos, Proj, Segmented, VerdictPlate } from "@/components/signage";
import { Icon } from "@/components/icons";

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

// Official status "available" says nothing about whether he starts, so only
// a real doubt is ever named; the absence of one is not shown as a badge.
function doubtLabel(player: PlayerRecord): string | null {
  const chance = player.chance_of_playing_next_round ?? 100;
  if (player.status !== "a" || chance < 50) return "Big doubt";
  if (chance < 100) return `${chance}% to play`;
  return null;
}

export default function CaptainPage() {
  const { snapshot, loading, squadPlayers, openProfile } = useApp();
  const [pool, setPool] = React.useState<"squad" | "all">("squad");
  const [selectedElement, setSelectedElement] = React.useState<number | null>(null);

  if (loading || !snapshot) {
    return (
      <section className="page">
        <div className="skel skel-sign" />
        <Skeleton variant="hero" />
        <Skeleton variant="row" count={8} />
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
  const leadFixture = lead ? nextFixtureFor(snapshot, lead) : null;
  const isTop = lead?.element === topPick?.element;
  const unit = predictionAvailable ? "projected points" : "form";

  return (
    <section className="page captain-page" aria-label="Captain">
      <GateSign>
        <Segmented
          label="Who to choose from"
          value={pool}
          onChange={(value) => {
            setPool(value);
            setSelectedElement(null);
          }}
          options={[
            { value: "squad", label: "My squad", disabled: squadPlayers.length === 0 },
            { value: "all", label: "Everyone" },
          ]}
        />
      </GateSign>

      {lead ? (
        <VerdictPlate
          tone="spotlight"
          label="Captain pick"
          player={lead}
          title={isTop ? <>Captain {lead.web_name}.</> : <>{lead.web_name} it is.</>}
          body={
            isTop
              ? `${whyLine(lead, leadFixture)}. He tops ${pool === "squad" ? "your squad" : "the league"} on ${unit}${
                  runnerUp ? `, ${num(captainScore(lead, predictionAvailable) - captainScore(runnerUp, predictionAvailable))} clear of ${runnerUp.web_name}` : ""
                }.`
              : `Your call. ${topPick?.web_name} is the top pick at ${num(captainScore(topPick!, predictionAvailable))}; ${lead.web_name} is on ${num(captainScore(lead, predictionAvailable))}.`
          }
          facts={
            <>
              <PlateFact label="This week">{num(captainScore(lead, predictionAvailable))} pts</PlateFact>
              <PlateFact label="Opponent">
                <Fdr fixture={leadFixture} />
              </PlateFact>
              <PlateFact label="Owned by">{num(lead.selected_by)}%</PlateFact>
              <PlateFact label="Price">{money(lead.value_m)}</PlateFact>
            </>
          }
          actions={
            <>
              <button className="btn btn--go" type="button" onClick={() => openProfile(lead)}>
                See his profile <Icon name="arrow-right" size={18} />
              </button>
              {!isTop && (
                <button className="btn btn--line" type="button" onClick={() => setSelectedElement(null)}>
                  Back to the top pick
                </button>
              )}
            </>
          }
        />
      ) : (
        <div className="empty-state">
          <h2 className="empty-title">Nobody to choose from yet</h2>
          <p className="empty-message">
            {pool === "squad" ? "Add your 15 on My team, or switch to Everyone." : "No available outfield players in the data."}
          </p>
        </div>
      )}

      {!predictionAvailable && (
        <p className="note note--warn">Projections aren&apos;t ready, so this ranks players on recent form instead.</p>
      )}

      {ranked.length > 0 && (
        <section className="section" aria-label="Shortlist">
          <div className="section-title">
            <div>
              <h2>The shortlist</h2>
              <p>Tap a player to see him on the plate. Keepers are left out: doubling a clean sheet rarely beats an attacker.</p>
            </div>
          </div>
          <ol className="panel runway">
            {ranked.map((player, index) => {
              const fixture = nextFixtureFor(snapshot, player);
              const doubt = doubtLabel(player);
              const selected = lead?.element === player.element;
              return (
                <m.li
                  key={player.element}
                  layout="position"
                  transition={{ layout: { duration: 0.32, ease: [0.22, 1, 0.36, 1] } }}
                  className={`cand${selected ? " is-selected" : ""}`}
                >
                  <button
                    type="button"
                    className="cand-main"
                    aria-pressed={selected}
                    onClick={() => setSelectedElement(player.element)}
                  >
                    <span className="cand-rank">{index + 1}</span>
                    <Face player={player} />
                    <span className="prow-name">
                      <b>
                        {player.web_name || player.name}
                        {player.has_prior_history === false && <span className="badge badge--line">New to the league</span>}
                      </b>
                      <span className="why">{whyLine(player, fixture)}</span>
                    </span>
                    <Pos pos={player.position} />
                    <Fdr fixture={fixture} compact />
                    <span className="cand-form">
                      <small>Form</small>
                      <b>{num(player.form)}</b>
                    </span>
                    {doubt ? <span className="badge badge--warn">{doubt}</span> : <span aria-hidden="true" />}
                    <Proj value={captainScore(player, predictionAvailable)} />
                  </button>
                  <button
                    type="button"
                    className="cand-profile"
                    aria-label={`${player.web_name} profile`}
                    onClick={() => openProfile(player)}
                  >
                    <Icon name="chevron-right" size={20} />
                  </button>
                </m.li>
              );
            })}
          </ol>
        </section>
      )}

      {lead && runnerUp && (
        <section className="section" aria-label="Head to head">
          <div className="section-title">
            <div>
              <h2>
                {lead.web_name} or {runnerUp.web_name}?
              </h2>
              <p>The top two, side by side.</p>
            </div>
          </div>
          <div className="panel duel">
            {[lead, runnerUp].map((player, side) => (
              <button
                key={player.element}
                type="button"
                className={`duel-seat duel-seat--${side === 0 ? "a" : "b"}`}
                onClick={() => openProfile(player)}
              >
                <Face player={player} size="lg" />
                <span>
                  <b>{player.web_name}</b>
                  <small>{player.team}</small>
                </span>
              </button>
            ))}
            <div className="duel-rows">
              {(
                [
                  ["This week", captainScore(lead, predictionAvailable), captainScore(runnerUp, predictionAvailable), 1],
                  ["Form", Number(lead.form), Number(runnerUp.form), 1],
                  ["Points this season", lead.total_points, runnerUp.total_points, 0],
                  ["Owned by (%)", Number(lead.selected_by), Number(runnerUp.selected_by), 1],
                ] as const
              ).map(([label, a, b, digits]) => {
                const total = Math.abs(a) + Math.abs(b) || 1;
                return (
                  <div className="duel-row" key={label}>
                    <b className={a >= b ? "is-lead" : undefined}>{num(a, digits)}</b>
                    <div className="duel-mid">
                      <span>{label}</span>
                      <div className="duel-bars">
                        <i className={a >= b ? "is-lead" : undefined} style={{ width: `${(Math.abs(a) / total) * 100}%` }} />
                        <i className={b > a ? "is-lead" : undefined} style={{ width: `${(Math.abs(b) / total) * 100}%` }} />
                      </div>
                    </div>
                    <b className={b > a ? "is-lead" : undefined}>{num(b, digits)}</b>
                  </div>
                );
              })}
            </div>
          </div>
          {isFlagged(lead) && <p className="note note--alert">Check the news on {lead.web_name} before the deadline.</p>}
        </section>
      )}
    </section>
  );
}
