"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { Loading } from "@/components/loading";
import { EmptyState } from "@/components/empty-state";
import { ChipIcon } from "@/components/chips/chip-icon";
import { ChipOpportunityMatrix } from "@/components/chips/chip-opportunity-matrix";
import { CHIP_IDS, type ChipId, type ChipInventory, type ChipRecommendation, type ChipRow, type ChipsResult } from "@/lib/types";

const CHIP_LABELS: Record<ChipId, string> = {
  triple_captain: "Triple Captain",
  bench_boost: "Bench Boost",
  free_hit: "Free Hit",
  wildcard: "Wildcard",
};

const CHIP_DESCRIPTIONS: Record<ChipId, string> = {
  triple_captain: "Captain points are tripled instead of doubled.",
  bench_boost: "All four bench players count in the gameweek total.",
  free_hit: "Build a one-week squad, then return to the original team.",
  wildcard: "Make unlimited permanent transfers in the gameweek.",
};

function blankInventory(): ChipInventory {
  return {
    first_half: {
      triple_captain: "unused",
      bench_boost: "unused",
      free_hit: "unused",
      wildcard: "unused",
    },
    second_half: {
      triple_captain: "unused",
      bench_boost: "unused",
      free_hit: "unused",
      wildcard: "unused",
    },
  };
}

function inventoryStatusLabel(state: ChipInventory["first_half"][ChipId]): string {
  if (state === "used") return "Used";
  if (state === "expired") return "Expired";
  return "Available";
}

function nextInventoryState(state: ChipInventory["first_half"][ChipId]): ChipInventory["first_half"][ChipId] {
  if (state === "unused") return "used";
  if (state === "used") return "expired";
  return "unused";
}

function captainFixtureLabel(fixtures: number): string {
  if (fixtures === 2) return "Double gameweek";
  return `${fixtures} ${fixtures === 1 ? "fixture" : "fixtures"}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isChipState(value: unknown): value is ChipInventory["first_half"][ChipId] {
  return value === "unused" || value === "used" || value === "expired";
}

function isInventoryHalf(value: unknown): value is ChipInventory["first_half"] {
  return isRecord(value) && CHIP_IDS.every((chip) => isChipState(value[chip]));
}

function readInventory(): ChipInventory | null {
  if (typeof window === "undefined") return null;
  try {
    const stored = window.localStorage.getItem("fpl-assistant-chip-inventory");
    if (!stored) return null;
    const parsed: unknown = JSON.parse(stored);
    if (!isRecord(parsed) || !isInventoryHalf(parsed.first_half) || !isInventoryHalf(parsed.second_half)) return null;
    return { first_half: parsed.first_half, second_half: parsed.second_half };
  } catch {
    return null;
  }
}

function WhyThisChoice({ recommendation, data }: { recommendation: ChipRecommendation; data: ChipsResult }) {
  const evidence = recommendation.evidence;
  return (
    <details className="chip-method chip-why">
      <summary>Why this choice</summary>
      <p>{recommendation.formula ?? "No player-level calculation is available for this candidate."}</p>
      {evidence?.chip === "triple_captain" && evidence.captain && (
        <p>
          {evidence.captain.name} ({evidence.captain.team}) projects {num(evidence.captain.projected_points ?? 0, 1)} points across {captainFixtureLabel(evidence.captain.fixtures)}.
          Normal captain total: {num(evidence.normal_captain_total, 1)}; Triple Captain total: {num(evidence.triple_captain_total ?? 0, 1)}; incremental gain: {num(evidence.incremental_gain ?? 0, 1)}.
        </p>
      )}
      {evidence?.chip === "bench_boost" && (
        <>
          <ul>{evidence.ordered_bench.map((player) => (
            <li key={player.element}>{player.player}: {num(player.points, 1)} pts, {player.available ? "available" : "unavailable"}</li>
          ))}</ul>
          <p>Bench total: {num(evidence.bench_total, 1)} points.</p>
        </>
      )}
      {evidence?.chip === "free_hit" && (
        <p>
          Current total {num(evidence.current_xi_captain_total, 1)}; optimized total {num(evidence.optimized_xi_captain_total ?? 0, 1)}; raw gain {num(evidence.raw_delta ?? 0, 1)} points across {evidence.changed_player_count} changed players.
        </p>
      )}
      {evidence?.chip === "wildcard" && (
        <>
          <p>
            Current total {num(evidence.current_cumulative_total, 1)}; optimized total {num(evidence.optimized_cumulative_total, 1)} across {evidence.horizon_length} weeks and {evidence.changed_player_count} changed players.
          </p>
          <p>Weekly gains: {Object.entries(evidence.weekly_deltas).map(([gw, gain]) => "GW" + gw + " " + num(gain, 1)).join(" · ")}.</p>
        </>
      )}
      {recommendation.alternatives.length > 0 && (
        <p>
          Top candidates: {recommendation.alternatives.map((candidate) => (
            "GW" + candidate.gw + " " + (candidate.projected_gain == null ? "index " + num(candidate.fixture_signal_index ?? 0, 1) : "+" + num(candidate.projected_gain, 1) + " pts")
          )).join(" · ")}.
          {recommendation.runner_up_gameweek != null && recommendation.gap_to_runner_up != null
            ? " Runner-up GW" + recommendation.runner_up_gameweek + "; gap " + num(recommendation.gap_to_runner_up, 1) + (recommendation.projected_gain != null ? " pts." : " index units.")
            : ""}
        </p>
      )}
      <p>Source: {data.projection_source}; coverage: {data.projection_gameweeks.length ? data.projection_gameweeks.map((gw) => "GW" + gw).join(", ") : "none"}. Inventory: {data.inventory_sync_state}. {recommendation.decision_policy.uncertainty_note}</p>
      {recommendation.warnings.map((warning) => <p key={warning}>{warning}</p>)}
    </details>
  );
}

export default function ChipsPage() {
  const { snapshot, loading, squadNames } = useApp();
  const [data, setData] = React.useState<ChipsResult | null>(null);
  const [fetching, setFetching] = React.useState(false);
  const [fetchError, setFetchError] = React.useState<string | null>(null);
  const [horizon, setHorizon] = React.useState<number>(8);
  const [useSquad, setUseSquad] = React.useState<boolean>(true);
  const [inventory, setInventory] = React.useState<ChipInventory | null>(null);
  const [inventoryLoaded, setInventoryLoaded] = React.useState(false);
  const scheduledGameweeks = React.useMemo<number[]>(() => [], []);
  const lastFreeHitGameweek: number | null = null;

  const maxPossibleHorizon = Math.max(1, 38 - (snapshot?.gameweek ?? 1) + 1);
  const effectiveHorizon = Math.min(horizon, maxPossibleHorizon);
  const requestIdRef = React.useRef(0);

  const loadChips = React.useCallback(
    async (squadList: string[], h: number) => {
      const requestId = ++requestIdRef.current;
      setFetching(true);
      setFetchError(null);
      try {
        const res = await api.chips({
          squad: squadList.length === 15 ? squadList : undefined,
          horizon: h,
          chip_inventory: inventory ?? undefined,
          scheduled_gameweeks: scheduledGameweeks,
          last_free_hit_gameweek: lastFreeHitGameweek,
        });
        if (requestId !== requestIdRef.current) return;
        if (res && res.ok) {
          setData(res);
        } else {
          setData(null);
          setFetchError("Unable to compute chip optimization recommendations.");
        }
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        setData(null);
        setFetchError((err as Error).message || "Failed to load chip advice.");
      } finally {
        if (requestId === requestIdRef.current) setFetching(false);
      }
    },
    [inventory, scheduledGameweeks],
  );

  React.useEffect(() => {
    if (!snapshot?.prediction_available || !inventoryLoaded) return;
    const names = useSquad ? squadNames : [];
    const timer = window.setTimeout(() => {
      void loadChips(names, effectiveHorizon);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [snapshot?.prediction_available, inventoryLoaded, useSquad, squadNames, effectiveHorizon, loadChips]);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      setInventory(readInventory());
      setInventoryLoaded(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  React.useEffect(() => {
    if (!inventoryLoaded) return;
    if (typeof window !== "undefined" && inventory) {
      window.localStorage.setItem("fpl-assistant-chip-inventory", JSON.stringify(inventory));
    } else if (typeof window !== "undefined") {
      window.localStorage.removeItem("fpl-assistant-chip-inventory");
    }
  }, [inventory, inventoryLoaded]);

  function updateChipState(half: "first_half" | "second_half", chip: ChipId) {
    setInventory((current) => {
      if (!current) return current;
      return {
        ...current,
        [half]: {
          ...current[half],
          [chip]: nextInventoryState(current[half][chip]),
        },
      };
    });
  }

  if (loading || !snapshot) {
    return (
      <section className="page">
        <div className="shell">
          <Loading label="Loading season data…" />
        </div>
      </section>
    );
  }

  if (!snapshot.prediction_available) {
    return (
      <section className="page">
        <div className="shell shell--padded">
          <EmptyState
            title="Predictions Unavailable"
            message={`The Chip Advisor requires model projections to evaluate optimal play windows.${snapshot.prediction_error ? ` (${snapshot.prediction_error})` : ""} Run the prediction pipeline or click Refresh in the header.`}
          />
        </div>
      </section>
    );
  }

  const recsByChip = new Map<string, ChipRecommendation>();
  for (const rec of data?.recommendations ?? []) {
    recsByChip.set(rec.chip, rec);
  }

  const orderedRecommendations = CHIP_IDS.map((chip) => recsByChip.get(chip)).filter(
    (rec): rec is ChipRecommendation => rec != null,
  );
  const nextDecision = orderedRecommendations.find((rec) => rec.status === "play")
    ?? orderedRecommendations.find((rec) => rec.status === "watch")
    ?? orderedRecommendations[0]
    ?? null;

  return (
    <section className="page chips-page" aria-label="Chip advisor">
      <div className="shell">
        <header className="section-head section-head--mt">
          <div>
            <span className="badge lime">Chip planning desk</span>
            <h1>Chip Advisor</h1>
            <p>
              Player-level projected gains with candidate weeks, inventory state, and supporting evidence.
            </p>
          </div>

          <div className="section-head-actions">
            <div className="filter-row">
              <label
                htmlFor="chips-horizon"
                className="kicker kicker-row"
              >
                Horizon:
                <select
                  id="chips-horizon"
                  value={effectiveHorizon}
                  onChange={(e) => setHorizon(Number(e.target.value))}
                  className="ctrl-select"
                >
                  {[4, 6, 8, 10, 12, 16].filter((h) => h <= maxPossibleHorizon).map((h) => (
                    <option key={h} value={h}>{h} Gameweeks</option>
                  ))}
                </select>
              </label>
            </div>

            <button
              type="button"
              className={`btn sm ${useSquad ? "" : "ghost"}`}
              onClick={() => setUseSquad((prev) => !prev)}
              title={
                squadNames.length === 15
                  ? "Evaluate with your active 15-player squad"
                  : "Build a squad in My Team for squad-specific advice"
              }
            >
              {useSquad && squadNames.length === 15 ? "Squad Tailored" : "League Generic"}
            </button>
          </div>
        </header>

        {useSquad && squadNames.length < 15 && (
          <div className="chip-squad-notice">
            <span className="chip-squad-notice-icon" aria-hidden="true">i</span>
            <span>
              Your squad has {squadNames.length}/15 players. Using league-wide fixture signals.
              Head to <strong>My Team</strong> to complete your squad for tailored analysis.
            </span>
          </div>
        )}

        <section className={`chip-inventory inventory-${inventory ? "synced" : "not-synced"}`} aria-label="Chip inventory">
          <div>
            <span className="kicker">Manager inventory</span>
            <h2>{inventory ? "Local chip history synced" : "Chip history not synced"}</h2>
            <p>
              {inventory
                ? "Cycle a chip through available, used, and expired to keep recommendations within the correct half-season set."
                : "Recommendations are provisional until you mark the two half-season sets as available. No private FPL account data is connected."}
            </p>
          </div>
          <span className={`chip-inventory-state state-${inventory ? "synced" : "not-synced"}`}>
            {inventory ? "Synced" : "Not synced"}
          </span>
          <button type="button" className="btn secondary sm" onClick={() => setInventory(inventory ? null : blankInventory())}>
            {inventory ? "Reset to not synced" : "Mark chips available"}
          </button>
          {inventory && (
            <div className="chip-inventory-grid">
              {(["first_half", "second_half"] as const).map((half) => (
                <div className="chip-inventory-set" key={half}>
                  <span className="kicker">{half === "first_half" ? "Set 1 · through GW19" : "Set 2 · GW20 onward"}</span>
                  <div className="chip-inventory-items">
                    {CHIP_IDS.map((chip) => (
                      <button
                        type="button"
                        className={`chip-inventory-item state-${inventory[half][chip]}`}
                        key={`${half}-${chip}`}
                        onClick={() => updateChipState(half, chip)}
                        aria-label={`${CHIP_LABELS[chip]} ${half} status: ${inventoryStatusLabel(inventory[half][chip])}. Change status.`}
                      >
                        <ChipIcon id={chip} />
                        <span>{CHIP_LABELS[chip]}</span>
                        <b>{inventoryStatusLabel(inventory[half][chip])}</b>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {fetching && <Loading label="Calculating schedule matrices and fixture difficulty…" />}

        {fetchError && (
          <div className="chip-error">
            <span>{fetchError}</span>
            <button
              type="button"
              className="btn sm"
              onClick={() => void loadChips(useSquad ? squadNames : [], effectiveHorizon)}
            >
              Retry
            </button>
          </div>
        )}

        <section className={`chip-next-decision${nextDecision ? ` status-${nextDecision.status}` : ""}`} aria-live="polite">
          <div className="chip-next-decision-copy">
            <span className="kicker">Next chip decision</span>
            <h2>{nextDecision ? CHIP_LABELS[nextDecision.chip] : "No chip data yet"}</h2>
            <p>
              {nextDecision?.reasons[0] ?? "Adjust the horizon or add a complete squad to calculate a decision."}
            </p>
            {nextDecision && data && (
              <small className="chip-decision-context">
                {data.projection_mode === "fixture_signal" || !data.has_squad ? "Fixture signal" : "Player projections"} · {data.inventory_sync_state === "synced" ? "inventory synced" : "inventory not synced"}
              </small>
            )}
            {nextDecision?.warnings.map((warning) => <small key={warning}>{warning}</small>)}
            {nextDecision && data && <WhyThisChoice recommendation={nextDecision} data={data} />}
          </div>
          {nextDecision && (
            <div className={`chip-decision-score status-${nextDecision.status}`}>
              <ChipIcon id={nextDecision.chip} size="large" />
              <strong>
                {nextDecision.status === "play" && nextDecision.gw
                  ? `GW${nextDecision.gw}`
                  : nextDecision.candidate_gw
                    ? `Candidate GW${nextDecision.candidate_gw}`
                    : "Hold"}
              </strong>
              <span>{nextDecision.status}</span>
              {nextDecision.projected_gain != null && <small>+{num(nextDecision.projected_gain, 1)} projected pts</small>}
              {nextDecision.fixture_signal_index != null && <small>Fixture index {num(nextDecision.fixture_signal_index, 1)}</small>}
            </div>
          )}
        </section>

        <div className="chip-advisor-grid">
          {orderedRecommendations.filter((rec) => rec.chip !== nextDecision?.chip).map((rec) => (
            <article key={rec.chip} className={`chip-advisor-card status-${rec.status}`}>
              <div className="chip-advisor-header">
                <div className="chip-advisor-name">
                  <ChipIcon id={rec.chip} />
                  {CHIP_LABELS[rec.chip]}
                </div>
                <span className={`chip-conf ${rec.confidence} status-${rec.status}`}>{rec.status}</span>
              </div>
              <div>
                <div className={`chip-advisor-target${rec.status === "hold" ? " hold" : ""}`}>
                  {rec.gw ? `GW${rec.gw}` : rec.candidate_gw ? `Candidate GW${rec.candidate_gw}` : rec.status}
                </div>
                <p className="chip-advisor-sub">
                  {rec.status === "play" ? "Policy margin met" : rec.status === "watch" ? "Candidate week" : rec.status}
                </p>
              </div>
              <p className="chip-advisor-desc">{rec.reasons[0]}</p>
              {rec.projected_gain != null && <p className="chip-advisor-gain">Projected gain +{num(rec.projected_gain, 1)} pts</p>}
              {rec.fixture_signal_index != null && <p className="chip-advisor-note">Fixture signal index {num(rec.fixture_signal_index, 1)} (not points)</p>}
              <WhyThisChoice recommendation={rec} data={data!} />
              <div className="chip-advisor-footer">{CHIP_DESCRIPTIONS[rec.chip]}</div>
            </article>
          ))}
        </div>

        {data && <ChipOpportunityMatrix rows={data.rows} recommendations={data.recommendations} projectionMode={data.projection_mode} hasSquad={data.has_squad} />}

        <div className="chip-heatmap-section">
          <div className="sub-head">
            <h3>Fixture context</h3>
            <span className="rule" />
            <small>
              Fixture signal GW{data?.first_gw ?? snapshot.gameweek}–GW
              {data?.last_gw ?? ((snapshot.gameweek ?? 1) + effectiveHorizon - 1)}
            </small>
          </div>

          <div className="chip-heatmap-scroll">
            <table className="chip-advisor-heatmap">
              <thead>
                <tr>
                  <th className="col-gw">GW</th>
                  <th>Fixtures</th>
                  {data?.has_squad && <th>Squad Active</th>}
                  <th>DGW Teams</th>
                  <th>Blank Teams</th>
                  <th>Avg FDR</th>
                  <th>Signal</th>
                </tr>
              </thead>
              <tbody>
                {data?.rows.map((row: ChipRow) => {
                  const isDgw = row.dgw_teams > 0;
                  const isBgw = row.blank_teams > 0;
                  const avgFdr = row.avg_fdr;
                  const hasSquad = data.has_squad;

                  let signal = "Standard run";
                  let signalClass = "trend flat";
                  if (isDgw) {
                    signal = `Double GW (${row.dgw_teams} teams)`;
                    signalClass = "trend up";
                  } else if (isBgw) {
                    signal = `Blank GW (${row.blank_teams} teams)`;
                    signalClass = "trend down";
                  } else if (avgFdr <= 2.8) {
                    signal = "Favourable Matchups";
                    signalClass = "trend up";
                  } else if (avgFdr >= 3.4) {
                    signal = "High Difficulty";
                    signalClass = "trend flat";
                  }

                  return (
                    <tr
                      key={row.gw}
                      className={isDgw ? "is-dgw" : isBgw ? "is-bgw" : undefined}
                    >
                      <td className="chip-row-gw">
                        GW{row.gw}
                      </td>
                      <td>
                        {row.matches} matches
                      </td>
                      {hasSquad && (
                        <td>
                          <span className={(row.squad_blanks ?? 0) > 0 ? "chip-squad-active is-blank" : "chip-squad-active"}>
                            {row.squad_playing ?? 15}/15
                          </span>
                          {(row.squad_blanks ?? 0) > 0 && (
                            <small className="chip-squad-blank">
                              ({row.squad_blanks} blank)
                            </small>
                          )}
                        </td>
                      )}
                      <td className={row.dgw_teams > 0 ? "chip-count chip-count--dgw" : "chip-count"}>
                        {row.dgw_teams > 0 ? `+${row.dgw_teams}` : "0"}
                      </td>
                      <td className={row.blank_teams > 0 ? "chip-count chip-count--blank" : "chip-count"}>
                        {row.blank_teams > 0 ? row.blank_teams : "0"}
                      </td>
                      <td>
                        <div className="chip-fdr-readout">
                          <span
                            className={`fdr`}
                            data-fdr={Math.round(avgFdr)}
                          />
                          <span className="chip-fdr-value">
                            {num(avgFdr, 1)}
                          </span>
                        </div>
                      </td>
                      <td>
                        <span className={signalClass}>
                          {signal}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {data && (
          <details className="chip-method">
            <summary>Projection and decision policy</summary>
            <p>Source: {data.projection_source}. Coverage: {data.projection_gameweeks.length ? data.projection_gameweeks.map((gw) => "GW" + gw).join(", ") : "none"}. Evaluated: {data.evaluated_horizon} of {data.requested_horizon} requested weeks. Data quality: {data.data_quality}. Method: {data.methodology_version}.</p>
            <p>Generated: {data.projection_generated_at ?? "timestamp unavailable"}. {data.decision_policy.basis}. {data.decision_policy.uncertainty_note}</p>
            {data.coverage_warning && <p>{data.coverage_warning}</p>}
          </details>
        )}
      </div>
    </section>
  );
}
