"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import type { ChipRecommendation, ChipRow, ChipsResult } from "@/lib/types";

function fdrColor(fdr: number): string {
  if (fdr <= 2.2) return "var(--fdr-2)";
  if (fdr <= 3.2) return "var(--fdr-3)";
  if (fdr <= 4.0) return "var(--fdr-4)";
  return "var(--fdr-5)";
}

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
        <div className="shell" style={{ paddingBlock: "var(--space-16)" }}>
          <p>Loading the local season data…</p>
        </div>
      </section>
    );
  }

  if (!snapshot.prediction_available) {
    return (
      <section className="page">
        <div className="shell" style={{ paddingBlock: "var(--space-12)" }}>
          <div className="empty-state" style={{ maxWidth: "640px", margin: "0 auto", textAlign: "center" }}>
            <h2 style={{ fontSize: "var(--type-h2)", textTransform: "uppercase", marginBottom: "var(--space-3)" }}>
              Predictions Unavailable
            </h2>
            <p style={{ color: "var(--muted-light)", marginBottom: "var(--space-6)" }}>
              The Chip Advisor requires model projections and current gameweek schedule data to evaluate optimal play windows.
              {snapshot.prediction_error ? ` (${snapshot.prediction_error})` : ""}
            </p>
            <p style={{ fontSize: "var(--type-small)", color: "var(--muted-mid)" }}>
              Run the prediction pipeline or click <strong>↻ Refresh</strong> in the top header once the model output is ready.
            </p>
          </div>
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

  const CHIP_METAS = [
    {
      id: "3xc",
      title: "Triple Captain",
      accent: "var(--cyan)",
      badgeClass: "badge-cyan",
      desc: "Multiplies captain points by 3. Best deployed on favourable double gameweeks or standout home fixtures.",
      icon: "⚡",
    },
    {
      id: "bboost",
      title: "Bench Boost",
      accent: "var(--lime)",
      badgeClass: "badge-lime",
      desc: "Points scored by all 4 bench substitutes are added to your overall gameweek total.",
      icon: "👥",
    },
    {
      id: "freehit",
      title: "Free Hit",
      accent: "var(--pink)",
      badgeClass: "badge-pink",
      desc: "Make unlimited free transfers for a single gameweek. Your previous squad returns immediately the following week.",
      icon: "🎯",
    },
    {
      id: "wildcard",
      title: "Wildcard",
      accent: "#FFD700",
      badgeClass: "badge-gold",
      desc: "Permanently restructure your entire 15-player squad without incurring point hit penalties.",
      icon: "🃏",
    },
  ];

  return (
    <section className="page chips-page">
      <div className="shell">
        <header className="section-head" style={{ marginTop: "var(--space-6)" }}>
          <div>
            <span className="badge" style={{ marginBottom: "var(--space-2)", background: "rgba(0,255,135,0.15)", color: "var(--lime)" }}>
              Tactical Strategy Engine
            </span>
            <h1>Chip Advisor & Timing</h1>
            <p>
              Fixture congestion, double gameweeks, blank postponements, and schedule difficulty evaluated across the horizon.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
              <label htmlFor="chips-horizon" style={{ fontSize: "12px", color: "var(--muted-mid)", textTransform: "uppercase", letterSpacing: ".05em" }}>
                Horizon:
              </label>
              <select
                id="chips-horizon"
                value={effectiveHorizon}
                onChange={(e) => setHorizon(Number(e.target.value))}
                style={{
                  background: "rgba(255,255,255,0.08)",
                  border: "1px solid rgba(255,255,255,0.16)",
                  color: "inherit",
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "12px",
                }}
              >
                {[4, 6, 8, 10, 12, 16].filter((h) => h <= maxPossibleHorizon).map((h) => (
                  <option key={h} value={h}>
                    {h} Gameweeks
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              className={`btn sm ${useSquad ? "" : "ghost"}`}
              onClick={() => setUseSquad((prev) => !prev)}
              title={squadNames.length === 15 ? "Evaluate with your active 15-player squad" : "Build a 15-player squad in My Team for squad-specific advice"}
            >
              {useSquad && squadNames.length === 15 ? "✓ Squad Tailored" : "League Generic"}
            </button>
          </div>
        </header>

        {useSquad && squadNames.length < 15 && (
          <div
            style={{
              padding: "var(--space-3) var(--space-4)",
              background: "rgba(255, 215, 0, 0.1)",
              border: "1px solid rgba(255, 215, 0, 0.3)",
              borderRadius: "4px",
              color: "#FFD700",
              fontSize: "13px",
              marginBottom: "var(--space-6)",
              display: "flex",
              alignItems: "center",
              gap: "var(--space-3)",
            }}
          >
            <span>ℹ</span>
            <span>
              Your saved squad currently has {squadNames.length}/15 players. Chip recommendations are using league-wide fixture trends. Head to <strong>My Team</strong> to complete your 15 players for squad-specific fixture analysis.
            </span>
          </div>
        )}

        {fetching && (
          <div style={{ paddingBlock: "var(--space-6)", color: "var(--muted-light)" }}>
            Calculating schedule matrices and fixture difficulty…
          </div>
        )}

        {fetchError && (
          <div style={{ padding: "var(--space-4)", background: "rgba(255,40,130,0.1)", border: "1px solid var(--pink)", borderRadius: "4px", color: "var(--pink)", marginBottom: "var(--space-6)" }}>
            {fetchError}
          </div>
        )}

        {/* Four Chip Cards */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: "var(--space-4)",
            marginBottom: "var(--space-8)",
          }}
        >
          {CHIP_METAS.map((meta) => {
            const rec = recsByChip.get(meta.id);
            const targetGw = rec?.gw ? `GW${rec.gw}` : "Hold";
            const isHold = !rec?.gw;
            const confidence = rec?.confidence ?? "low";

            return (
              <div
                key={meta.id}
                style={{
                  background: "rgba(255, 255, 255, 0.04)",
                  border: `1px solid ${rec?.gw ? meta.accent : "rgba(255, 255, 255, 0.12)"}`,
                  borderTop: `4px solid ${meta.accent}`,
                  borderRadius: "4px",
                  padding: "var(--space-5)",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  gap: "var(--space-4)",
                  transition: "transform 0.15s ease",
                }}
              >
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-2)" }}>
                    <span style={{ fontSize: "12px", fontFamily: "var(--data)", fontWeight: 700, color: meta.accent, textTransform: "uppercase", letterSpacing: ".06em" }}>
                      {meta.icon} {meta.title}
                    </span>
                    <span
                      style={{
                        fontSize: "10px",
                        fontFamily: "var(--data)",
                        fontWeight: 700,
                        padding: "2px 6px",
                        borderRadius: "2px",
                        textTransform: "uppercase",
                        background:
                          confidence === "high"
                            ? "rgba(0, 255, 135, 0.2)"
                            : confidence === "medium"
                            ? "rgba(2, 227, 247, 0.2)"
                            : "rgba(255, 255, 255, 0.1)",
                        color:
                          confidence === "high"
                            ? "var(--lime)"
                            : confidence === "medium"
                            ? "var(--cyan)"
                            : "var(--muted-light)",
                      }}
                    >
                      {confidence} confidence
                    </span>
                  </div>

                  <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-2)", marginBlock: "var(--space-2)" }}>
                    <span style={{ fontSize: "clamp(1.8rem, 2.8vw, 2.4rem)", fontWeight: 900, fontFamily: "var(--display)", color: isHold ? "var(--muted-light)" : "var(--white)" }}>
                      {targetGw}
                    </span>
                    <span style={{ fontSize: "11px", color: "var(--muted-mid)", textTransform: "uppercase" }}>
                      {isHold ? "Preserve for future" : "Recommended window"}
                    </span>
                  </div>

                  <p style={{ fontSize: "13px", color: "var(--muted-light)", lineHeight: 1.4, margin: "0 0 var(--space-2) 0" }}>
                    {rec?.reason ?? meta.desc}
                  </p>

                  {rec?.note && (
                    <p style={{ fontSize: "11px", color: "#FFD700", margin: 0, fontStyle: "italic" }}>
                      ℹ {rec.note}
                    </p>
                  )}
                </div>

                <div
                  style={{
                    paddingTop: "var(--space-3)",
                    borderTop: "1px solid rgba(255, 255, 255, 0.08)",
                    fontSize: "11px",
                    color: "var(--muted-mid)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <span>{meta.desc}</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Schedule & Congestion Matrix */}
        <div style={{ marginBottom: "var(--space-12)" }}>
          <div className="sub-head">
            <h3>Gameweek Fixture & FDR Heatmap</h3>
            <span className="rule" />
            <small>Schedule Congestion GW{data?.first_gw ?? snapshot.gameweek}–GW{data?.last_gw ?? ((snapshot.gameweek ?? 1) + effectiveHorizon - 1)}</small>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table className="stable" style={{ width: "100%", textAlign: "left", fontSize: "13px" }}>
              <thead>
                <tr>
                  <th style={{ width: "90px" }}>GW</th>
                  <th>Fixtures</th>
                  {data?.has_squad && <th>Squad Active</th>}
                  <th>DGW Teams</th>
                  <th>Blank Teams</th>
                  <th>Average FDR</th>
                  <th>Key Signal</th>
                </tr>
              </thead>
              <tbody>
                {data?.rows.map((row: ChipRow) => {
                  const isDgw = row.dgw_teams > 0;
                  const isBgw = row.blank_teams > 0;
                  const avgFdr = row.avg_fdr;
                  const hasSquad = data.has_squad;

                  let signal = "Standard run";
                  let signalColor = "var(--muted-light)";
                  if (isDgw) {
                    signal = `🔥 Double GW (${row.dgw_teams} teams)`;
                    signalColor = "var(--lime)";
                  } else if (isBgw) {
                    signal = `⚠️ Blank GW (${row.blank_teams} teams)`;
                    signalColor = "var(--pink)";
                  } else if (avgFdr <= 2.8) {
                    signal = "⭐ Favourable Matchups";
                    signalColor = "var(--cyan)";
                  } else if (avgFdr >= 3.4) {
                    signal = "⚡ High Difficulty";
                    signalColor = "#FFD700";
                  }

                  return (
                    <tr key={row.gw} style={{ background: isDgw ? "rgba(0, 255, 135, 0.05)" : isBgw ? "rgba(255, 40, 130, 0.05)" : undefined }}>
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
                      <td>
                        {row.dgw_teams > 0 ? (
                          <span style={{ color: "var(--lime)", fontWeight: 700, fontFamily: "var(--data)" }}>
                            +{row.dgw_teams}
                          </span>
                        ) : (
                          <span style={{ color: "var(--muted-mid)" }}>0</span>
                        )}
                      </td>
                      <td>
                        {row.blank_teams > 0 ? (
                          <span style={{ color: "var(--pink)", fontWeight: 700, fontFamily: "var(--data)" }}>
                            {row.blank_teams}
                          </span>
                        ) : (
                          <span style={{ color: "var(--muted-mid)" }}>0</span>
                        )}
                      </td>
                      <td>
                        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                          <span
                            style={{
                              display: "inline-block",
                              width: "12px",
                              height: "12px",
                              borderRadius: "2px",
                              background: fdrColor(avgFdr),
                            }}
                          />
                          <span style={{ fontFamily: "var(--data)", fontWeight: 700 }}>
                            {num(avgFdr, 1)}
                          </span>
                        </div>
                      </td>
                      <td style={{ color: signalColor, fontWeight: 600, fontSize: "12px" }}>
                        {signal}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Honest Tactical Caveat */}
        <div
          style={{
            padding: "var(--space-4) var(--space-5)",
            background: "rgba(255, 255, 255, 0.03)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "4px",
            marginBottom: "var(--space-16)",
          }}
        >
          <div style={{ display: "flex", alignItems: "flex-start", gap: "var(--space-3)" }}>
            <span style={{ fontSize: "18px", lineHeight: 1 }}>📐</span>
            <div style={{ fontSize: "12px", color: "var(--muted-light)", lineHeight: 1.5 }}>
              <strong style={{ color: "var(--white)", textTransform: "uppercase", letterSpacing: ".04em", display: "block", marginBottom: "4px" }}>
                Model Architecture Note
              </strong>
              Per-player model predictions do not vary arbitrarily across future gameweeks. Predictions are derived from player form, expected underlying metrics, and team baseline performance. Signal across upcoming gameweeks is generated through fixture count (Double/Blank GWs) and Fixture Difficulty Rating (FDR). Double and Blank gameweeks generally manifest later in the campaign once domestic cups (FA Cup, EFL Cup) and continental ties induce postponements.
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
