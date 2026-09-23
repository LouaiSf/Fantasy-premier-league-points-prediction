"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { Pitch } from "@/components/team/pitch";
import { money, num, signed } from "@/lib/format";
import { fromTenths, sellingPricesTenthsForSquad } from "@/lib/finance";
import type { PlayerRecord, TransferResult, TransferRow } from "@/lib/types";

interface TeamPlanProps {
  readonly analysis: TransferResult | null;
  readonly freeTransfers: number;
  readonly onFreeTransfersChange: (value: number) => void;
  readonly bank: number;
  readonly onBankChange: (value: number) => void;
  readonly loading: boolean;
  readonly error: string | null;
  readonly onApply: (row: TransferRow) => void;
}

function playerName(player: PlayerRecord | null): string {
  return player?.web_name || player?.name || "--";
}

// Transfer rows carry sparse squad_records (element/name/team/position/
// value_m/predicted_points -- no photo, web_name or team_short); join each
// one back to the live snapshot before rendering a portrait or full name.
function mergeRecord(byElement: Map<number, PlayerRecord>, record: PlayerRecord): PlayerRecord {
  return { ...record, ...(byElement.get(record.element) ?? {}) };
}

function LaneRow({
  player,
  priceLabel,
  priceValue,
}: {
  readonly player: PlayerRecord;
  readonly priceLabel: string;
  readonly priceValue: number;
}) {
  return (
    <div className="team-plan-lane-row">
      <span className="team-plan-lane-photo">
        <PlayerPhoto
          src={player.photo ?? undefined}
          alt={player.name}
          name={player.name}
          variant="avatar"
          loading="lazy"
        />
      </span>
      <span className="team-plan-lane-id">
        <strong>{playerName(player)}</strong>
        <small>{player.position} · {player.team_short}</small>
      </span>
      <span className="team-plan-lane-price">
        {priceLabel} {money(priceValue)}
      </span>
    </div>
  );
}

function BenchStrip({ players }: { readonly players: PlayerRecord[] }) {
  return (
    <div className="team-plan-bench">
      {players.map((player) => (
        <div className="team-plan-bench-player" key={player.element}>
          <span className="team-plan-bench-photo">
            <PlayerPhoto
              src={player.photo ?? undefined}
              alt={player.name}
              name={player.name}
              variant="avatar"
              loading="lazy"
            />
          </span>
          <span className="team-plan-bench-id">
            <strong>{playerName(player)}</strong>
            <small>{player.position}</small>
          </span>
          <em>{num(player.predicted_points ?? player.form)}</em>
        </div>
      ))}
    </div>
  );
}

export function TeamPlan({
  analysis,
  freeTransfers,
  onFreeTransfersChange,
  bank,
  onBankChange,
  loading,
  error,
  onApply,
}: TeamPlanProps) {
  const { snapshot, squadPlayers, storedSquad } = useApp();
  const recommendation = analysis?.recommended ?? analysis?.best ?? null;
  const uncertainty = analysis?.marginal_recommendation
    ? "The recommended edge is inside the model margin; holding is defensible."
    : "Projected points carry roughly one point of model error per player; treat small gaps as noise.";

  const byElement = React.useMemo(
    () => new Map((snapshot?.players ?? []).map((player) => [player.element, player])),
    [snapshot],
  );
  const sellingPricesTenths = React.useMemo(
    () => sellingPricesTenthsForSquad(squadPlayers, storedSquad?.finance ?? null),
    [squadPlayers, storedSquad],
  );

  // Derived by element-set difference against the current 15, never by
  // pairing up the API's `out`/`in` name arrays: with several same-position
  // moves those two lists are not in matching order, and a shared surname
  // (there are two Palmers in the 2026-27 export) can resolve to the wrong
  // player entirely.
  let outPlayers: PlayerRecord[] = [];
  let inPlayers: PlayerRecord[] = [];
  let suggestedXi: PlayerRecord[] = [];
  let suggestedBench: PlayerRecord[] = [];
  let suggestedCaptain: PlayerRecord | null = null;
  let suggestedVice: PlayerRecord | null = null;

  if (recommendation) {
    const currentIds = new Set(squadPlayers.map((player) => player.element));
    const nextIds = new Set(recommendation.squad.map((player) => player.element));
    outPlayers = squadPlayers.filter((player) => !nextIds.has(player.element));
    inPlayers = recommendation.squad
      .filter((player) => !currentIds.has(player.element))
      .map((player) => mergeRecord(byElement, player));
    suggestedXi = recommendation.xi.map((player) => mergeRecord(byElement, player));
    suggestedBench = recommendation.bench.map((player) => mergeRecord(byElement, player));
    suggestedCaptain = recommendation.captain ? mergeRecord(byElement, recommendation.captain) : null;
    suggestedVice = recommendation.vice_captain ? mergeRecord(byElement, recommendation.vice_captain) : null;
  }

  return (
    <section className="team-plan" aria-label="Combined next move plan">
      <div className="team-plan-head">
        <div>
          <span className="eyebrow muted">Next move</span>
          <h2>One plan for the whole team</h2>
          <p>Choose only the free transfers you can make without a hit. The optimizer returns the move, XI, bench, and armbands together.</p>
        </div>
        <label className="team-plan-control" htmlFor="team-free-transfers">
          <span className="kicker">Free transfers</span>
          <select id="team-free-transfers" value={freeTransfers} onChange={(event) => onFreeTransfersChange(Number(event.target.value))}>
            {[0, 1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label className="team-plan-control" htmlFor="team-bank">
          <span className="kicker">Bank (£m)</span>
          <input
            id="team-bank"
            type="number"
            min="0"
            max="100"
            step="0.1"
            value={bank}
            onChange={(event) => onBankChange(Number(event.target.value))}
          />
        </label>
      </div>
      {loading && <p className="team-plan-status" role="status">Building the joint transfer and lineup plan…</p>}
      {error && <p className="team-plan-status is-error" role="alert">{error}</p>}
      {!loading && !error && recommendation && (
        <>
          <div className="team-plan-result-strip">
            <div>
              <span className="kicker">Recommendation</span>
              <strong>{recommendation.transfers === 0 ? "Hold this week" : `${recommendation.transfers} transfer${recommendation.transfers === 1 ? "" : "s"}`}</strong>
            </div>
            <div className="team-plan-result-score">
              <span className={recommendation.gain >= 0 ? "is-positive" : "is-negative"}>
                {signed(recommendation.gain)} pts
              </span>
              <small>{money(recommendation.bank_after)} bank after · {recommendation.formation}</small>
            </div>
          </div>

          {recommendation.transfers === 0 || (!outPlayers.length && !inPlayers.length) ? (
            <div className="team-plan-hold">Hold — no squad changes; lineup advice still refreshed.</div>
          ) : (
            <div className="team-plan-lane">
              <div className="team-plan-lane-col is-out">
                <span className="team-plan-lane-label">Out</span>
                {outPlayers.map((player) => (
                  <LaneRow
                    key={player.element}
                    player={player}
                    priceLabel="Sell"
                    priceValue={fromTenths(sellingPricesTenths[player.element] ?? 0)}
                  />
                ))}
              </div>
              <div className="team-plan-lane-col is-in">
                <span className="team-plan-lane-label">In</span>
                {inPlayers.map((player) => (
                  <LaneRow key={player.element} player={player} priceLabel="Buy" priceValue={player.value_m} />
                ))}
              </div>
            </div>
          )}

          <div className="team-plan-suggested">
            <div className="team-plan-suggested-head">
              <h3>Suggested starting XI</h3>
              <span className="kicker">{num(recommendation.xi_points)} pts</span>
            </div>
            <div className="team-plan-suggested-body">
              <Pitch compact result={{ xi: suggestedXi, captain: suggestedCaptain, vice_captain: suggestedVice }} />
              <aside className="team-plan-suggested-rail">
                <div className="team-plan-bench-block">
                  <span className="kicker">Bench</span>
                  <BenchStrip players={suggestedBench} />
                </div>
                <div className="team-plan-armbands">
                  <span className="kicker">Armbands</span>
                  <p>Captain <strong>{playerName(suggestedCaptain)}</strong></p>
                  <p>Vice-captain <strong>{playerName(suggestedVice)}</strong></p>
                  <p>Captained total <strong>{num(recommendation.captained_total)} pts</strong></p>
                </div>
              </aside>
            </div>
          </div>

          <div className="team-plan-foot">
            <p>{uncertainty}</p>
            <button className="btn" type="button" onClick={() => onApply(recommendation)} disabled={recommendation.squad.length !== 15}>
              Apply suggestion
            </button>
          </div>
        </>
      )}
      {!loading && !error && !recommendation && <p className="team-plan-status">No legal recommendation was found within the current budget.</p>}
    </section>
  );
}
