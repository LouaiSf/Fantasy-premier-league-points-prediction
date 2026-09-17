"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { ClubCrest } from "@/components/club-crest";
import { money, num } from "@/lib/format";
import { api } from "@/lib/api";
import { Loading } from "@/components/loading";
import { EmptyState } from "@/components/empty-state";
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
            message={`The Watchlist requires model projections to calculate value ratios, differentials, and overpriced assets.${snapshot.prediction_error ? ` (${snapshot.prediction_error})` : ""} Run the prediction pipeline or click Refresh.`}
          />
        </div>
      </section>
    );
  }

  const teamsByName = new Map(snapshot.teams.map((t) => [t.name, t]));
  const playersByElement = new Map(snapshot.players.map((p) => [p.element, p]));

  const filterList = (list: WatchlistPlayer[] = []) => {
    if (!search.trim()) return list;
    const q = search.trim().toLowerCase();
    return list.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.team.toLowerCase().includes(q) ||
        p.position.toLowerCase().includes(q),
    );
  };

  const renderPlayerCard = (
    player: WatchlistPlayer,
    tagClass: "value" | "diff" | "trap" | "new",
    tagLabel: string,
  ) => {
    const fullPlayer =
      (player.element ? playersByElement.get(player.element) : undefined) ??
      snapshot.players.find((p) => p.name === player.name);
    const team = teamsByName.get(player.team);
    const photo = fullPlayer?.photo;

    return (
      <button
        key={`${player.element ?? player.name}-${tagLabel}`}
        type="button"
        className="watch-card"
        onClick={() => fullPlayer && openProfile(fullPlayer)}
      >
        <div className="watch-photo-wrap">
          <PlayerPhoto
            src={photo ?? undefined}
            name={player.name}
            alt={player.name}
            width={48}
            height={48}
          />
          {team && (
            <div className="watch-crest-badge">
              <ClubCrest code={team.code} team={team.name} shortName={team.short_name} />
            </div>
          )}
        </div>

        <div className="watch-info">
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", marginBottom: "2px" }}>
            <span className="watch-name">{player.name}</span>
            <span className="watch-pos-badge">{player.position}</span>
          </div>
          <div className="watch-meta">
            <span>{player.team}</span>
            {player.opponent_team && (
              <span>vs {player.opponent_team} ({player.was_home ? "H" : "A"})</span>
            )}
            {player.selected_by != null && (
              <span style={{ marginLeft: "auto", fontFamily: "var(--data)", fontSize: "11px" }}>
                {num(player.selected_by, 1)}% owned
              </span>
            )}
          </div>
        </div>

        <div className="watch-pts-wrap">
          <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-1)" }}>
            <span className="watch-pts">{num(player.predicted_points, 1)}</span>
            <span style={{ fontSize: "10px", color: "var(--muted-mid)", textTransform: "uppercase" }}>pts</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
            <span className="watch-price">{money(player.value_m)}</span>
            <span className={`watch-tag ${tagClass}`}>{tagLabel}</span>
          </div>
        </div>
      </button>
    );
  };

  const valList = filterList(data?.value);
  const diffList = filterList(data?.differentials);
  const overList = filterList(data?.overpriced);
  const noHistList = filterList(data?.no_history);

  const tabs: { key: SectionTab; label: string; count: number }[] = [
    { key: "all", label: "All Insights", count: (valList?.length ?? 0) + (diffList?.length ?? 0) + (overList?.length ?? 0) + (noHistList?.length ?? 0) },
    { key: "value", label: "Top Value", count: valList?.length ?? 0 },
    { key: "differentials", label: `Differentials (≤${maxOwnership}%)`, count: diffList?.length ?? 0 },
    { key: "overpriced", label: "Price Traps", count: overList?.length ?? 0 },
    { key: "no_history", label: "Promoted / New", count: noHistList?.length ?? 0 },
  ];

  return (
    <section className="page watchlist-page">
      <div className="shell">
        <header className="section-head" style={{ marginTop: "var(--space-6)" }}>
          <div>
            <span className="badge cyan">
              Tactical Market Wire
            </span>
            <h1>Watchlist &amp; Differentials</h1>
            <p>
              Automated high-value targets, mini-league differentials, price traps, and newly promoted talent for GW{snapshot.gameweek}.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
            <label
              htmlFor="diff-threshold"
              className="kicker"
              style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}
            >
              Diff Max:
              <select
                id="diff-threshold"
                value={maxOwnership}
                onChange={(e) => setMaxOwnership(Number(e.target.value))}
                style={{
                  background: "rgba(255,255,255,0.08)",
                  border: "1px solid rgba(255,255,255,0.16)",
                  color: "inherit",
                  padding: "4px 8px",
                  fontSize: "12px",
                }}
              >
                <option value={5}>≤ 5% owned</option>
                <option value={10}>≤ 10% owned</option>
                <option value={15}>≤ 15% owned</option>
              </select>
            </label>

            <label
              htmlFor="top-count"
              className="kicker"
              style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}
            >
              Count:
              <select
                id="top-count"
                value={topCount}
                onChange={(e) => setTopCount(Number(e.target.value))}
                style={{
                  background: "rgba(255,255,255,0.08)",
                  border: "1px solid rgba(255,255,255,0.16)",
                  color: "inherit",
                  padding: "4px 8px",
                  fontSize: "12px",
                }}
              >
                <option value={8}>8 per list</option>
                <option value={12}>12 per list</option>
                <option value={16}>16 per list</option>
              </select>
            </label>

            <div className="search" style={{ minWidth: "180px" }}>
              <input
                type="search"
                placeholder="Search player, club, position…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>
        </header>

        {/* Tab switcher */}
        <div className="filter-row" style={{ marginBlock: "var(--space-6)" }}>
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`btn sm ${activeSection === tab.key ? "" : "ghost"}`}
              onClick={() => setActiveSection(tab.key)}
            >
              {tab.label}
              <span className="tab-count">{tab.count}</span>
            </button>
          ))}
        </div>

        {fetching && <Loading label="Updating market metrics…" />}

        {fetchError && (
          <div className="watch-error">{fetchError}</div>
        )}

        <div
          style={{
            display: "grid",
            gridTemplateColumns: activeSection === "all" ? "repeat(auto-fit, minmax(420px, 1fr))" : "1fr",
            gap: "var(--space-8)",
            paddingBottom: "var(--space-16)",
          }}
        >
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
              <div className="watch-grid" style={{ marginTop: "var(--space-2)" }}>
                {valList.map((player) =>
                  renderPlayerCard(player, "value", `${num(player.points_per_million, 2)} PPM`),
                )}
                {valList.length === 0 && (
                  <p className="empty-copy">No matching players found.</p>
                )}
              </div>
            </div>
          )}

          {/* 2. Differentials */}
          {(activeSection === "all" || activeSection === "differentials") && (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <div className="sub-head">
                <h3 style={{ color: "var(--cyan)" }}>Differentials (≤{maxOwnership}%)</h3>
                <span className="rule" />
                <small>Mini-League Edge</small>
              </div>
              <p style={{ fontSize: "var(--type-small)", color: "var(--muted-light)", margin: 0 }}>
                Low-ownership assets capable of propelling your rank without templates.
              </p>
              <div className="watch-grid" style={{ marginTop: "var(--space-2)" }}>
                {diffList.map((player) =>
                  renderPlayerCard(player, "diff", `${num(player.selected_by, 1)}% own`),
                )}
                {diffList.length === 0 && (
                  <p className="empty-copy">No matching differentials found.</p>
                )}
              </div>
            </div>
          )}

          {/* 3. Overpriced / Traps */}
          {(activeSection === "all" || activeSection === "overpriced") && (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <div className="sub-head">
                <h3 style={{ color: "var(--pink)" }}>Overpriced Traps (≥£8.0m)</h3>
                <span className="rule" />
                <small>Lowest PPM Premium</small>
              </div>
              <p style={{ fontSize: "var(--type-small)", color: "var(--muted-light)", margin: 0 }}>
                Expensive assets whose current fixture/projection profile does not justify premium allocation.
              </p>
              <div className="watch-grid" style={{ marginTop: "var(--space-2)" }}>
                {overList.map((player) =>
                  renderPlayerCard(player, "trap", `${num(player.points_per_million, 2)} PPM`),
                )}
                {overList.length === 0 && (
                  <p className="empty-copy">No overpriced players found.</p>
                )}
              </div>
            </div>
          )}

          {/* 4. No History */}
          {(activeSection === "all" || activeSection === "no_history") && (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <div className="sub-head">
                <h3 style={{ color: "var(--gold)" }}>Promoted &amp; New Signings</h3>
                <span className="rule" />
                <small>Baseline Projection</small>
              </div>
              <p style={{ fontSize: "var(--type-small)", color: "var(--muted-light)", margin: 0 }}>
                Talent without previous Premier League game logs. Forecasted using baseline position priors.
              </p>
              <div className="watch-grid" style={{ marginTop: "var(--space-2)" }}>
                {noHistList.map((player) =>
                  renderPlayerCard(player, "new", "New to PL"),
                )}
                {noHistList.length === 0 && (
                  <p className="empty-copy">No new/promoted players with predictions.</p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
