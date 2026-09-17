"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { Loading } from "@/components/loading";
import { EmptyState } from "@/components/empty-state";
import type { ChipRecommendation, ChipRow, ChipsResult } from "@/lib/types";

function fdrClass(fdr: number): string {
  if (fdr <= 2.2) return "fdr-2";
  if (fdr <= 3.2) return "fdr-3";
  if (fdr <= 4.0) return "fdr-4";
  return "fdr-5";
}

const CHIP_METAS = [
  {
    id: "3xc",
    title: "Triple Captain",
    iconLabel: "TC",
    iconBg: "var(--gold)",
    iconColor: "var(--ink)",
  },
  {
    id: "bboost",
    title: "Bench Boost",
    iconLabel: "BB",
    iconBg: "var(--cyan)",
    iconColor: "var(--ink)",
  },
  {
    id: "freehit",
    title: "Free Hit",
    iconLabel: "FH",
    iconBg: "var(--pink)",
    iconColor: "var(--white)",
  },
  {
    id: "wildcard",
    title: "Wildcard",
    iconLabel: "WC",
    iconBg: "var(--lime)",
    iconColor: "var(--ink)",
  },
];

export default function ChipsPage() {
  const { snapshot, loading, squadNames } = useApp();
  const [data, setData] = React.useState<ChipsResult | null>(null);
  const [fetching, setFetching] = React.useState(false);
  const [fetchError, setFetchError] = React.useState<string | null>(null);
  const [horizon, setHorizon] = React.useState<number>(8);
  const [useSquad, setUseSquad] = React.useState<boolean>(true);

  const maxPossibleHorizon = Math.max(1, 38 - (snapshot?.gameweek ?? 1) + 1);
  const effectiveHorizon = Math.min(horizon, maxPossibleHorizon);

  const loadChips = React.useCallback(
    async (squadList: string[], h: number) => {
      setFetching(true);
      setFetchError(null);
      try {
        const res = await api.chips({
          squad: squadList.length === 15 ? squadList : undefined,
          horizon: h,
        });
        if (res && res.ok) {
          setData(res);
        } else {
          setFetchError("Unable to compute chip optimization recommendations.");
        }
      } catch (err) {
        setFetchError((err as Error).message || "Failed to load chip advice.");
      } finally {
        setFetching(false);
      }
    },
    [],
  );

  React.useEffect(() => {
    if (!snapshot?.prediction_available) return;
    const names = useSquad ? squadNames : [];
    const timer = window.setTimeout(() => {
      void loadChips(names, effectiveHorizon);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [snapshot?.prediction_available, useSquad, squadNames, effectiveHorizon, loadChips]);

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
        <div className="shell" style={{ paddingBlock: "var(--space-12)" }}>
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
    if (rec.chip.includes("Triple Captain")) recsByChip.set("3xc", rec);
    if (rec.chip.includes("Bench Boost")) recsByChip.set("bboost", rec);
    if (rec.chip.includes("Free Hit")) recsByChip.set("freehit", rec);
    if (rec.chip.includes("Wildcard")) recsByChip.set("wildcard", rec);
  }

  return (
    <section className="page chips-page" aria-label="Chip advisor">
      <div className="shell">
        <header className="section-head" style={{ marginTop: "var(--space-6)" }}>
          <div>
            <span className="badge lime">
              Tactical Strategy Engine
            </span>
            <h1>Chip Advisor &amp; Timing</h1>
            <p>
              Fixture congestion, double gameweeks, blank postponements, and schedule difficulty evaluated across the horizon.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
            <div className="filter-row">
              <label
                htmlFor="chips-horizon"
                className="kicker"
                style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}
              >
                Horizon:
                <select
                  id="chips-horizon"
                  value={effectiveHorizon}
                  onChange={(e) => setHorizon(Number(e.target.value))}
                  style={{
                    background: "rgba(255,255,255,0.08)",
                    border: "1px solid rgba(255,255,255,0.16)",
                    color: "inherit",
                    padding: "4px 8px",
                    fontSize: "12px",
                  }}
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
            <span className="kicker" style={{ color: "var(--gold)" }}>i</span>
            <span>
              Your squad has {squadNames.length}/15 players. Using league-wide fixture trends.
              Head to <strong>My Team</strong> to complete your squad for tailored analysis.
            </span>
          </div>
        )}

        {fetching && <Loading label="Calculating schedule matrices and fixture difficulty…" />}

        {fetchError && (
          <div className="chip-error">{fetchError}</div>
        )}

        {/* Four Chip Cards */}
        <div className="chip-advisor-grid">
          {CHIP_METAS.map((meta) => {
            const rec = recsByChip.get(meta.id);
            const targetGw = rec?.gw ? `GW${rec.gw}` : "Hold";
            const isHold = !rec?.gw;
            const confidence = rec?.confidence ?? "low";

            return (
              <div
                key={meta.id}
                className={`chip-advisor-card${rec?.gw ? " is-active" : ""}`}
              >
                <div className="chip-advisor-header">
                  <div className="chip-advisor-name">
                    <span
                      className="chip-advisor-icon"
                      style={{ background: meta.iconBg, color: meta.iconColor }}
                    >
                      {meta.iconLabel}
                    </span>
                    {meta.title}
                  </div>
                  <span className={`chip-conf ${confidence}`}>
                    {confidence} conf
                  </span>
                </div>

                <div>
                  <div className={`chip-advisor-target${isHold ? " hold" : ""}`}>
                    {targetGw}
                  </div>
                  <p className="chip-advisor-sub">
                    {isHold ? "Preserve for future" : "Recommended window"}
                  </p>
                </div>

                <p className="chip-advisor-desc">
                  {rec?.reason ?? "No recommendation yet — adjust the horizon or add your squad."}
                </p>

                {rec?.note && (
                  <p className="chip-advisor-note">{rec.note}</p>
                )}

                <div className="chip-advisor-footer">
                  {meta.title === "Triple Captain" && "Multiplies captain points by 3."}
                  {meta.title === "Bench Boost" && "Points scored by all 4 bench players are counted."}
                  {meta.title === "Free Hit" && "Unlimited free transfers for one gameweek."}
                  {meta.title === "Wildcard" && "Permanently restructure your squad without penalties."}
                </div>
              </div>
            );
          })}
        </div>

        {/* Schedule & Congestion Matrix */}
        <div style={{ marginBottom: "var(--space-12)" }}>
          <div className="sub-head">
            <h3>Gameweek Fixture &amp; FDR Heatmap</h3>
            <span className="rule" />
            <small>
              Schedule Congestion GW{data?.first_gw ?? snapshot.gameweek}–GW
              {data?.last_gw ?? ((snapshot.gameweek ?? 1) + effectiveHorizon - 1)}
            </small>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table className="chip-advisor-heatmap">
              <thead>
                <tr>
                  <th style={{ width: "80px" }}>GW</th>
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
                      <td style={{ fontWeight: 800, fontFamily: "var(--data)" }}>
                        GW{row.gw}
                      </td>
                      <td style={{ fontFamily: "var(--data)" }}>
                        {row.matches} matches
                      </td>
                      {hasSquad && (
                        <td style={{ fontFamily: "var(--data)" }}>
                          <span style={{ color: (row.squad_blanks ?? 0) > 0 ? "var(--pink)" : "var(--lime)", fontWeight: 700 }}>
                            {row.squad_playing ?? 15}/15
                          </span>
                          {(row.squad_blanks ?? 0) > 0 && (
                            <small style={{ color: "var(--pink)", marginLeft: "4px" }}>
                              ({row.squad_blanks} blank)
                            </small>
                          )}
                        </td>
                      )}
                      <td style={{ fontFamily: "var(--data)", color: row.dgw_teams > 0 ? "var(--lime)" : "var(--muted-mid)", fontWeight: row.dgw_teams > 0 ? 700 : 400 }}>
                        {row.dgw_teams > 0 ? `+${row.dgw_teams}` : "0"}
                      </td>
                      <td style={{ fontFamily: "var(--data)", color: row.blank_teams > 0 ? "var(--pink)" : "var(--muted-mid)", fontWeight: row.blank_teams > 0 ? 700 : 400 }}>
                        {row.blank_teams > 0 ? row.blank_teams : "0"}
                      </td>
                      <td>
                        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                          <span
                            className={`fdr`}
                            data-fdr={Math.round(avgFdr)}
                            style={{ minWidth: "12px", height: "12px" }}
                          />
                          <span style={{ fontFamily: "var(--data)", fontWeight: 700 }}>
                            {num(avgFdr, 1)}
                          </span>
                        </div>
                      </td>
                      <td>
                        <span className={signalClass} style={{ fontSize: "12px" }}>
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

        {/* Architecture note */}
        <div className="chip-note-banner">
          <span style={{ fontFamily: "var(--display)", fontWeight: 900, fontSize: "1.1rem", lineHeight: 1, flexShrink: 0 }}>
            i
          </span>
          <div style={{ fontSize: "12px", color: "var(--muted-light)", lineHeight: 1.5 }}>
            <strong style={{ color: "var(--white)", textTransform: "uppercase", letterSpacing: ".04em", display: "block", marginBottom: "4px" }}>
              Model Architecture Note
            </strong>
            Per-player predictions are derived from player form, expected metrics, and team baseline performance. Signal across
            upcoming gameweeks is generated through fixture count (Double/Blank GWs) and Fixture Difficulty Rating (FDR).
          </div>
        </div>
      </div>
    </section>
  );
}
