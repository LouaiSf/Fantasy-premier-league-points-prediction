"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { ClubCrest } from "@/components/club-crest";
import { money, num } from "@/lib/format";
import { api } from "@/lib/api";
import type { WatchlistPlayer, WatchlistResult } from "@/lib/types";

type SectionTab = "all" | "value" | "differentials" | "overpriced" | "no_history";

export default function WatchlistPage() {
  const { snapshot, loading, openProfile } = useApp();
  const [data, setData] = React.useState<WatchlistResult | null>(null);
  const [fetching, setFetching] = React.useState(false);
  const [fetchError, setFetchError] = React.useState<string | null>(null);
  const [activeSection, setActiveSection] = React.useState<SectionTab>("all");
  const [maxOwnership, setMaxOwnership] = React.useState<number>(10);
  const [topCount, setTopCount] = React.useState<number>(12);
  const [search, setSearch] = React.useState<string>("");

  const loadWatchlist = React.useCallback(async (ownership: number, top: number) => {
    setFetching(true);
    setFetchError(null);
    try {
      const res = await api.watchlist(ownership, top);
      if (res && res.ok) {
        setData(res);
      } else {
        setFetchError("Could not retrieve watchlist from the optimization engine.");
      }
    } catch (err) {
      setFetchError((err as Error).message || "Failed to load watchlist data.");
    } finally {
      setFetching(false);
    }
  }, []);

  React.useEffect(() => {
    if (!snapshot?.prediction_available) return;
    const timer = window.setTimeout(() => {
      void loadWatchlist(maxOwnership, topCount);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [snapshot?.prediction_available, maxOwnership, topCount, loadWatchlist]);

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
              The Watchlist requires model projections to calculate value ratios, differentials, and underperforming assets.
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

  const teamsByName = new Map(snapshot.teams.map((t) => [t.name, t]));
  const playersByElement = new Map(snapshot.players.map((p) => [p.element, p]));

  const filterList = (list: WatchlistPlayer[] = []) => {
    if (!search.trim()) return list;
    const q = search.trim().toLowerCase();
    return list.filter((p) =>
      p.name.toLowerCase().includes(q) || p.team.toLowerCase().includes(q) || p.position.toLowerCase().includes(q)
    );
  };

  const renderPlayerCard = (player: WatchlistPlayer, tagVariant: "lime" | "cyan" | "pink" | "gold", tagLabel: string) => {
    const fullPlayer = (player.element ? playersByElement.get(player.element) : undefined) ??
      snapshot.players.find((p) => p.name === player.name);
    const team = teamsByName.get(player.team);
    const photo = fullPlayer?.photo;

    return (
      <button
        key={`${player.element || player.name}-${tagLabel}`}
        type="button"
        className="desk-row"
        onClick={() => fullPlayer && openProfile(fullPlayer)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-4)",
          padding: "var(--space-3) var(--space-4)",
          background: "rgba(255, 255, 255, 0.04)",
          border: "1px solid rgba(255, 255, 255, 0.08)",
          borderRadius: "4px",
          width: "100%",
          textAlign: "left",
          cursor: "pointer",
          transition: "all 0.15s ease",
          position: "relative",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255, 255, 255, 0.09)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "rgba(255, 255, 255, 0.04)")}
      >
        <div style={{ position: "relative", width: "48px", height: "48px", flexShrink: 0 }}>
          <div style={{ borderRadius: "50%", overflow: "hidden", width: "100%", height: "100%" }}>
            <PlayerPhoto
              src={photo || undefined}
              name={player.name}
              alt={player.name}
              width={48}
              height={48}
            />
          </div>
          {team && (
            <div
              style={{
                position: "absolute",
                bottom: "-2px",
                right: "-4px",
                width: "18px",
                height: "18px",
                background: "var(--ink)",
                borderRadius: "50%",
                padding: "2px",
              }}
            >
              <ClubCrest code={team.code} team={team.name} shortName={team.short_name} />
            </div>
          )}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", marginBottom: "2px" }}>
            <span
              style={{
                fontWeight: 700,
                fontSize: "var(--type-body)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {player.name}
            </span>
            <span
              style={{
                fontSize: "10px",
                fontFamily: "var(--data)",
                padding: "1px 5px",
                borderRadius: "2px",
                background: "rgba(255,255,255,0.12)",
                color: "var(--muted-light)",
              }}
            >
              {player.position}
            </span>
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--space-3)",
              fontSize: "var(--type-small)",
              color: "var(--muted-light)",
            }}
          >
            <span>{player.team}</span>
            {player.opponent_team && (
              <span style={{ opacity: 0.8 }}>
                vs {player.opponent_team} ({player.was_home ? "H" : "A"})
              </span>
            )}
            {player.selected_by != null && (
              <span style={{ marginLeft: "auto", fontFamily: "var(--data)", fontSize: "11px" }}>
                {num(player.selected_by, 1)}% owned
              </span>
            )}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-2)" }}>
            <span style={{ fontSize: "var(--type-h3)", fontWeight: 800, fontFamily: "var(--data)" }}>
              {num(player.predicted_points, 1)}
            </span>
            <span style={{ fontSize: "10px", color: "var(--muted-mid)", textTransform: "uppercase" }}>pts</span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", marginTop: "2px" }}>
            <span style={{ fontSize: "11px", color: "var(--muted-light)", fontFamily: "var(--data)" }}>
              {money(player.value_m)}
            </span>
            <span
              style={{
                fontSize: "10px",
                fontFamily: "var(--data)",
                fontWeight: 700,
                padding: "1px 5px",
                borderRadius: "3px",
                background:
                  tagVariant === "lime"
                    ? "rgba(0, 255, 135, 0.15)"
                    : tagVariant === "cyan"
                    ? "rgba(2, 227, 247, 0.15)"
                    : tagVariant === "pink"
                    ? "rgba(255, 40, 130, 0.15)"
                    : "rgba(255, 215, 0, 0.15)",
                color:
                  tagVariant === "lime"
                    ? "var(--lime)"
                    : tagVariant === "cyan"
                    ? "var(--cyan)"
                    : tagVariant === "pink"
                    ? "var(--pink)"
                    : "#FFD700",
              }}
            >
              {tagLabel}
            </span>
          </div>
        </div>
      </button>
    );
  };

  const valList = filterList(data?.value);
  const diffList = filterList(data?.differentials);
  const overList = filterList(data?.overpriced);
  const noHistList = filterList(data?.no_history);

  return (
    <section className="page watchlist-page">
      <div className="shell">
        <header className="section-head" style={{ marginTop: "var(--space-6)" }}>
          <div>
            <span className="badge" style={{ marginBottom: "var(--space-2)", background: "rgba(2,227,247,0.15)", color: "var(--cyan)" }}>
              Tactical Market Wire
            </span>
            <h1>Watchlist & Differentials</h1>
            <p>
              Automated high-value targets, mini-league differentials, price traps, and newly promoted talent for GW{snapshot.gameweek}.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
              <label htmlFor="diff-threshold" style={{ fontSize: "12px", color: "var(--muted-mid)", textTransform: "uppercase", letterSpacing: ".05em" }}>
                Diff Max:
              </label>
              <select
                id="diff-threshold"
                value={maxOwnership}
                onChange={(e) => setMaxOwnership(Number(e.target.value))}
                style={{
                  background: "rgba(255,255,255,0.08)",
                  border: "1px solid rgba(255,255,255,0.16)",
                  color: "inherit",
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "12px",
                }}
              >
                <option value={5}>&le; 5% owned</option>
                <option value={10}>&le; 10% owned</option>
                <option value={15}>&le; 15% owned</option>
              </select>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
              <label htmlFor="top-count" style={{ fontSize: "12px", color: "var(--muted-mid)", textTransform: "uppercase", letterSpacing: ".05em" }}>
                Count:
              </label>
              <select
                id="top-count"
                value={topCount}
                onChange={(e) => setTopCount(Number(e.target.value))}
                style={{
                  background: "rgba(255,255,255,0.08)",
                  border: "1px solid rgba(255,255,255,0.16)",
                  color: "inherit",
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "12px",
                }}
              >
                <option value={8}>8 per list</option>
                <option value={12}>12 per list</option>
                <option value={16}>16 per list</option>
              </select>
            </div>

            <input
              type="search"
              placeholder="Search player, club, position…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                background: "rgba(255,255,255,0.08)",
                border: "1px solid rgba(255,255,255,0.16)",
                color: "inherit",
                padding: "6px 12px",
                borderRadius: "4px",
                fontSize: "12px",
                minWidth: "180px",
              }}
            />
          </div>
        </header>

        {/* Tab switcher */}
        <div style={{ display: "flex", gap: "var(--space-2)", marginBlock: "var(--space-6)", flexWrap: "wrap" }}>
          {[
            { key: "all", label: "All Insights", count: (valList.length + diffList.length + overList.length + noHistList.length) },
            { key: "value", label: "Top Value", count: valList.length },
            { key: "differentials", label: `Differentials (≤${maxOwnership}%)`, count: diffList.length },
            { key: "overpriced", label: "Price Traps", count: overList.length },
            { key: "no_history", label: "Promoted / New", count: noHistList.length },
          ].map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`btn sm ${activeSection === tab.key ? "" : "ghost"}`}
              onClick={() => setActiveSection(tab.key as SectionTab)}
              style={{ textTransform: "uppercase", fontSize: "11px", display: "inline-flex", alignItems: "center", gap: "var(--space-2)" }}
            >
              <span>{tab.label}</span>
              <span style={{ opacity: 0.7, fontSize: "10px" }}>({tab.count})</span>
            </button>
          ))}
        </div>

        {fetching && (
          <div style={{ paddingBlock: "var(--space-8)", color: "var(--muted-light)" }}>
            Updating market metrics…
          </div>
        )}

        {fetchError && (
          <div style={{ padding: "var(--space-4)", background: "rgba(255,40,130,0.1)", border: "1px solid var(--pink)", borderRadius: "4px", color: "var(--pink)", marginBottom: "var(--space-6)" }}>
            {fetchError}
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: activeSection === "all" ? "repeat(auto-fit, minmax(420px, 1fr))" : "1fr", gap: "var(--space-8)", paddingBottom: "var(--space-16)" }}>
          {/* 1. Best Value */}
          {(activeSection === "all" || activeSection === "value") && (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <div className="sub-head">
                <h3 style={{ color: "var(--lime)" }}>Best Value (Pts / £m)</h3>
                <span className="rule" />
                <small>Top PPM Efficiency</small>
              </div>
              <p style={{ fontSize: "var(--type-small)", color: "var(--muted-light)", margin: 0 }}>
                Budget stretchers who yield the highest projected output per million spent.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
                {valList.map((player) =>
                  renderPlayerCard(
                    player,
                    "lime",
                    `${num(player.points_per_million, 2)} PPM`
                  )
                )}
                {valList.length === 0 && <p style={{ color: "var(--muted-mid)", fontSize: "13px" }}>No matching players found.</p>}
              </div>
            </div>
          )}

          {/* 2. Differentials */}
          {(activeSection === "all" || activeSection === "differentials") && (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <div className="sub-head">
                <h3 style={{ color: "var(--cyan)" }}>Differentials (&le;{maxOwnership}%)</h3>
                <span className="rule" />
                <small>Mini-League Edge</small>
              </div>
              <p style={{ fontSize: "var(--type-small)", color: "var(--muted-light)", margin: 0 }}>
                Low-ownership assets capable of propelling your rank without templates.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
                {diffList.map((player) =>
                  renderPlayerCard(
                    player,
                    "cyan",
                    `${num(player.selected_by, 1)}% own`
                  )
                )}
                {diffList.length === 0 && <p style={{ color: "var(--muted-mid)", fontSize: "13px" }}>No matching differentials found.</p>}
              </div>
            </div>
          )}

          {/* 3. Overpriced / Traps */}
          {(activeSection === "all" || activeSection === "overpriced") && (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <div className="sub-head">
                <h3 style={{ color: "var(--pink)" }}>Overpriced Traps (&ge;£8.0m)</h3>
                <span className="rule" />
                <small>Lowest PPM Premium</small>
              </div>
              <p style={{ fontSize: "var(--type-small)", color: "var(--muted-light)", margin: 0 }}>
                Expensive assets whose current fixture/projection profile does not justify premium allocation.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
                {overList.map((player) =>
                  renderPlayerCard(
                    player,
                    "pink",
                    `${num(player.points_per_million, 2)} PPM`
                  )
                )}
                {overList.length === 0 && <p style={{ color: "var(--muted-mid)", fontSize: "13px" }}>No overpriced players found.</p>}
              </div>
            </div>
          )}

          {/* 4. No History */}
          {(activeSection === "all" || activeSection === "no_history") && (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <div className="sub-head">
                <h3 style={{ color: "#FFD700" }}>Promoted & New Signings</h3>
                <span className="rule" />
                <small>Baseline Projection</small>
              </div>
              <p style={{ fontSize: "var(--type-small)", color: "var(--muted-light)", margin: 0 }}>
                Talent without previous Premier League game logs. Forecasted using baseline position priors.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
                {noHistList.map((player) =>
                  renderPlayerCard(
                    player,
                    "gold",
                    "New to PL"
                  )
                )}
                {noHistList.length === 0 && <p style={{ color: "var(--muted-mid)", fontSize: "13px" }}>No new/promoted players with predictions.</p>}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
