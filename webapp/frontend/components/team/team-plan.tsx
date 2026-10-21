"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { Pitch } from "@/components/team/pitch";
import { Face, Pos, Proj } from "@/components/signage";
import { Icon } from "@/components/icons";
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

export function playerName(player: PlayerRecord | null | undefined): string {
  return player?.web_name || player?.name || "--";
}

// Transfer rows carry sparse squad_records (element/name/team/position/
// value_m/predicted_points -- no photo, web_name or team_short); join each
// one back to the live snapshot before rendering a portrait or full name.
function mergeRecord(byElement: Map<number, PlayerRecord>, record: PlayerRecord): PlayerRecord {
  return { ...record, ...(byElement.get(record.element) ?? {}) };
}

export interface PlanMoves {
  readonly outPlayers: PlayerRecord[];
  readonly inPlayers: PlayerRecord[];
  readonly xi: PlayerRecord[];
  readonly bench: PlayerRecord[];
  readonly captain: PlayerRecord | null;
  readonly vice: PlayerRecord | null;
}

// Derived by element-set difference against the current 15, never by
// pairing up the API's `out`/`in` name arrays: with several same-position
// moves those two lists are not in matching order, and a shared surname
// (there are two Palmers in the 2026-27 export) can resolve to the wrong
// player entirely.
export function planMoves(
  recommendation: TransferRow,
  squadPlayers: PlayerRecord[],
  byElement: Map<number, PlayerRecord>,
): PlanMoves {
  const currentIds = new Set(squadPlayers.map((player) => player.element));
  const nextIds = new Set(recommendation.squad.map((player) => player.element));
  return {
    outPlayers: squadPlayers.filter((player) => !nextIds.has(player.element)),
    inPlayers: recommendation.squad
      .filter((player) => !currentIds.has(player.element))
      .map((player) => mergeRecord(byElement, player)),
    xi: recommendation.xi.map((player) => mergeRecord(byElement, player)),
    bench: recommendation.bench.map((player) => mergeRecord(byElement, player)),
    captain: recommendation.captain ? mergeRecord(byElement, recommendation.captain) : null,
    vice: recommendation.vice_captain ? mergeRecord(byElement, recommendation.vice_captain) : null,
  };
}

export function recommendationOf(analysis: TransferResult | null): TransferRow | null {
  return analysis?.recommended ?? analysis?.best ?? null;
}

function LaneRow({ player, price, index }: { readonly player: PlayerRecord; readonly price: string; readonly index: number }) {
  return (
    <div className="lane-row" style={{ "--i": index } as React.CSSProperties}>
      <Face player={player} />
      <span className="prow-name">
        <b>{playerName(player)}</b>
        <span>{player.team_short || player.team} · {price}</span>
      </span>
      <Pos pos={player.position} />
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
  const recommendation = recommendationOf(analysis);
  const byElement = React.useMemo(
    () => new Map((snapshot?.players ?? []).map((player) => [player.element, player])),
    [snapshot],
  );
  const sellingPricesTenths = React.useMemo(
    () => sellingPricesTenthsForSquad(squadPlayers, storedSquad?.finance ?? null),
    [squadPlayers, storedSquad],
  );
  const moves = recommendation ? planMoves(recommendation, squadPlayers, byElement) : null;
  const holding = !recommendation || recommendation.transfers === 0 || !moves || (!moves.outPlayers.length && !moves.inPlayers.length);

  return (
    <section className="section team-plan" id="plan" aria-label="Transfer and lineup plan">
      <div className="section-title">
        <div>
          <h2>The full plan</h2>
          <p>Transfers, lineup, bench and armband, worked out together.</p>
        </div>
        <div className="team-plan-controls">
          <label className="field" htmlFor="team-free-transfers">
            <span>Free transfers</span>
            <select
              id="team-free-transfers"
              className="select select--sm"
              value={freeTransfers}
              onChange={(event) => onFreeTransfersChange(Number(event.target.value))}
            >
              {[0, 1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <label className="field" htmlFor="team-bank">
            <span>In the bank (£m)</span>
            <input
              id="team-bank"
              className="input input--sm"
              type="number"
              min="0"
              max="100"
              step="0.1"
              value={bank}
              onChange={(event) => onBankChange(Number(event.target.value))}
            />
          </label>
        </div>
      </div>

      {loading && <div className="skel skel-row" aria-label="Working out the plan" />}
      {error && <p className="status-line is-error" role="alert">{error}</p>}
      {!loading && !error && !recommendation && (
        <p className="status-line">No legal plan fits the current budget. Try adding a little to the bank.</p>
      )}

      {!loading && !error && recommendation && moves && (
        <div className="panel">
          {holding ? (
            <div className="plan-hold">
              <span className="callout-mark"><Icon name="check" size={18} /></span>
              <p>
                <b>Keep the squad as it is.</b> No transfer this week beats what you already have by enough to be worth it.
                {recommendation.transfers === 0 && freeTransfers < 5 ? " Your free transfer rolls over to next week." : ""}
              </p>
            </div>
          ) : (
            <div className="lane">
              <div className="lane-col lane-col--out stagger">
                <h3><Icon name="arrow-left" size={18} /> Out</h3>
                {moves.outPlayers.map((player, index) => (
                  <LaneRow
                    key={player.element}
                    player={player}
                    price={`sells for ${money(fromTenths(sellingPricesTenths[player.element] ?? 0))}`}
                    index={index}
                  />
                ))}
              </div>
              <div className="lane-arrow" aria-hidden="true"><Icon name="arrow-right" size={32} /></div>
              <div className="lane-col lane-col--in stagger">
                <h3>In <Icon name="arrow-right" size={18} /></h3>
                {moves.inPlayers.map((player, index) => (
                  <LaneRow key={player.element} player={player} price={`costs ${money(player.value_m)}`} index={index} />
                ))}
              </div>
            </div>
          )}

          <div className="plan-summary">
            <span>
              <small>This week</small>
              <b>{num(recommendation.xi_points)} pts</b>
            </span>
            <span>
              <small>{holding ? "Change" : "Gain after any hit"}</small>
              <b className={recommendation.gain > 0 ? "is-up" : undefined}>{signed(recommendation.gain)} pts</b>
            </span>
            <span>
              <small>Bank after</small>
              <b>{money(recommendation.bank_after)}</b>
            </span>
            <span>
              <small>Captain</small>
              <b>{playerName(moves.captain)}</b>
            </span>
            <span>
              <small>Vice</small>
              <b>{playerName(moves.vice)}</b>
            </span>
          </div>

          {!holding && (
            <div className="plan-xi">
              <Pitch compact result={{ xi: moves.xi, captain: moves.captain, vice_captain: moves.vice }} />
              <div className="plan-bench">
                <h3>Bench, in order</h3>
                {moves.bench.map((player, index) => (
                  <div className="bench-row" key={player.element}>
                    <span className="bench-order">{index + 1}</span>
                    <Face player={player} size="sm" />
                    <span className="prow-name"><b>{playerName(player)}</b></span>
                    <Proj value={player.predicted_points ?? player.form} />
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="plan-foot">
            <p className="note">
              {analysis?.marginal_recommendation
                ? "It's close: the gain is small enough that holding is just as reasonable."
                : "Projections are estimates. Treat a gap of a point or less as a coin flip."}
            </p>
            <button
              className="btn btn--go"
              type="button"
              onClick={() => onApply(recommendation)}
              disabled={recommendation.squad.length !== 15}
            >
              {holding ? "Use this lineup" : "Apply this plan"} <Icon name="arrow-right" size={18} />
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
