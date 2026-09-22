"use client";

import type { PlayerRecord, TransferResult, TransferRow } from "@/lib/types";
import { money, num, signed } from "@/lib/format";

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

function PlanPlayers({ players, label }: { readonly players: PlayerRecord[]; readonly label: string }) {
  return (
    <div className="team-plan-player-group">
      <span className="kicker">{label}</span>
      <ul>
        {players.map((player) => (
          <li key={player.element}><span>{player.position}</span><strong>{playerName(player)}</strong><em>{num(player.predicted_points ?? player.form)}</em></li>
        ))}
      </ul>
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
  const recommendation = analysis?.recommended ?? analysis?.best ?? null;
  const uncertainty = analysis?.marginal_recommendation
    ? "The recommended edge is inside the model margin; holding is defensible."
    : "Projected points carry roughly one point of model error per player; treat small gaps as noise.";

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
          <div className="team-plan-verdict">
            <div>
              <span className="kicker">Recommendation</span>
              <strong>{recommendation.transfers === 0 ? "Hold this week" : `${recommendation.transfers} transfer${recommendation.transfers === 1 ? "" : "s"}`}</strong>
              <p>{recommendation.out.length ? `${recommendation.out.join(", ")} → ${recommendation.in.join(", ")}` : "No squad changes; lineup advice still refreshed."}</p>
            </div>
            <div className="team-plan-score">
              <span className="kicker">Net projected gain</span>
              <strong className={recommendation.gain >= 0 ? "is-positive" : "is-negative"}>{signed(recommendation.gain)}</strong>
              <small>{money(recommendation.bank_after)} bank after · {recommendation.formation}</small>
            </div>
          </div>
          <div className="team-plan-evidence">
            <PlanPlayers players={recommendation.xi} label={`Starting XI · ${num(recommendation.xi_points)} pts`} />
            <PlanPlayers players={recommendation.bench} label="Bench order" />
            <div className="team-plan-armbands">
              <span className="kicker">Armbands</span>
              <p>Captain <strong>{playerName(recommendation.captain)}</strong></p>
              <p>Vice-captain <strong>{playerName(recommendation.vice_captain)}</strong></p>
              <p>Captained total <strong>{num(recommendation.captained_total)} pts</strong></p>
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
