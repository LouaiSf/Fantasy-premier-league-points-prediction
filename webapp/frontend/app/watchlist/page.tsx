"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { money, num } from "@/lib/format";
import { api } from "@/lib/api";
import { clubStyle } from "@/lib/club-colors";
import { Skeleton } from "@/components/skeleton";
import { EmptyState } from "@/components/empty-state";
import { Face, GateSign, PlateFact, Pos, Proj, Segmented, VerdictPlate } from "@/components/signage";
import { Icon } from "@/components/icons";
import type { PlayerRecord, WatchlistPlayer, WatchlistResult } from "@/lib/types";

type SectionKey = "value" | "differentials" | "overpriced" | "no_history";
type SectionTab = "all" | SectionKey;

interface SectionDef {
  readonly key: SectionKey;
  readonly title: string;
  readonly blurb: (maxOwnership: number) => string;
  readonly stat: (player: WatchlistPlayer) => string;
  readonly empty: string;
}

const SECTIONS: readonly SectionDef[] = [
  {
    key: "value",
    title: "Good value",
    blurb: () => "The most expected points for every million you spend.",
    stat: (player) => `${num(player.points_per_million, 2)} pts per £m`,
    empty: "No value picks match that search.",
  },
  {
    key: "differentials",
    title: "Under the radar",
    blurb: (max) => `Owned by ${max}% of managers or fewer. A good week from one of these gains you ground on almost everyone.`,
    stat: (player) => `${num(player.selected_by, 1)}% own him`,
    empty: "No low-owned picks match that search.",
  },
  {
    key: "overpriced",
    title: "Not pulling their weight",
    blurb: () => "Players at £8m or more whose expected points don't justify the price right now.",
    stat: (player) => `${num(player.points_per_million, 2)} pts per £m`,
    empty: "No expensive underperformers match that search.",
  },
  {
    key: "no_history",
    title: "New to the league",
    blurb: () => "No Premier League record to go on yet, so their numbers are a rough guide.",
    stat: () => "Rough guide",
    empty: "No newcomers match that search.",
  },
];

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
        setFetchError("We couldn't build the watchlist this time.");
      }
    } catch (err) {
      setFetchError((err as Error).message || "We couldn't build the watchlist this time.");
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
        <div className="skel skel-sign" />
        <Skeleton variant="hero" />
        <div className="skel-columns" style={{ "--cols": 2 } as React.CSSProperties}>
          <Skeleton variant="row" count={6} />
          <Skeleton variant="row" count={6} />
        </div>
      </section>
    );
  }

  if (!snapshot.prediction_available) {
    return (
      <section className="page">
        <GateSign />
        <EmptyState
          title="Projections aren't ready yet"
          message="The watchlist is built from this week's projections. Use Get latest data in the menu, then come back."
        />
      </section>
    );
  }

  const playersByElement = new Map(snapshot.players.map((p) => [p.element, p]));
  const fullPlayer = (player: WatchlistPlayer): PlayerRecord | undefined =>
    (player.element ? playersByElement.get(player.element) : undefined) ?? snapshot.players.find((p) => p.name === player.name);

  const query = search.trim().toLowerCase();
  const listFor = (key: SectionKey) =>
    (data?.[key] ?? []).filter(
      (p) => !query || p.name.toLowerCase().includes(query) || p.team.toLowerCase().includes(query) || p.position.toLowerCase() === query,
    );

  const bestValue = data?.value?.[0] ?? null;
  const bestValueFull = bestValue ? fullPlayer(bestValue) : undefined;
  const shown = activeSection === "all" ? SECTIONS : SECTIONS.filter((section) => section.key === activeSection);

  return (
    <section className="page watch-page" aria-label="Watchlist">
      <GateSign lede={`Players worth a look for gameweek ${snapshot.gameweek ?? ""}: bargains, hidden gems, and big names to think twice about.`} />

      {bestValue && bestValueFull && (
        <VerdictPlate
          tone="stats"
          label="Best value this week"
          player={bestValueFull}
          title={<>Best bang for your buck: {bestValueFull.web_name}.</>}
          body={`${num(bestValue.predicted_points)} expected points for ${money(bestValue.value_m)}${
            bestValue.selected_by != null ? `, and only ${num(bestValue.selected_by, 1)}% of managers have him` : ""
          }.`}
          facts={
            <>
              <PlateFact label="This week">{num(bestValue.predicted_points)} pts</PlateFact>
              <PlateFact label="Price">{money(bestValue.value_m)}</PlateFact>
              <PlateFact label="Per £1m">{num(bestValue.points_per_million, 2)} pts</PlateFact>
            </>
          }
          actions={
            <button className="btn btn--go" type="button" onClick={() => openProfile(bestValueFull)}>
              See his profile <Icon name="arrow-right" size={18} />
            </button>
          }
        />
      )}

      <div className="toolbar">
        <Segmented
          label="Show"
          value={activeSection}
          onChange={setActiveSection}
          options={[{ value: "all" as SectionTab, label: "Everything" }, ...SECTIONS.map((section) => ({ value: section.key as SectionTab, label: section.title }))]}
        />
        <span className="toolbar-spacer" />
        <label className="searchbox">
          <span className="sr-only">Search</span>
          <Icon name="search" size={18} />
          <input className="input input--sm" type="search" placeholder="Player, club or position" value={search} onChange={(e) => setSearch(e.target.value)} />
        </label>
        <label className="toolbar-field">
          <span>Under the radar means</span>
          <select className="select select--sm" value={maxOwnership} onChange={(e) => setMaxOwnership(Number(e.target.value))}>
            <option value={5}>5% owned or less</option>
            <option value={10}>10% owned or less</option>
            <option value={15}>15% owned or less</option>
          </select>
        </label>
        <label className="toolbar-field">
          <span>Show</span>
          <select className="select select--sm" value={topCount} onChange={(e) => setTopCount(Number(e.target.value))}>
            <option value={8}>8 each</option>
            <option value={12}>12 each</option>
            <option value={16}>16 each</option>
          </select>
        </label>
      </div>

      {fetching && <p className="loading-state"><span className="loading-spinner" />Updating the lists…</p>}
      {fetchError && (
        <div className="callout callout--alert" role="alert">
          <span className="callout-mark"><Icon name="alert" size={16} /></span>
          <p>{fetchError}</p>
          <button className="btn btn--sm" type="button" onClick={() => void loadWatchlist(maxOwnership, topCount)}>Try again</button>
        </div>
      )}

      <div className={`watch-grid${activeSection === "all" ? "" : " is-single"}`}>
        {shown.map((section) => {
          const list = listFor(section.key);
          return (
            <section key={section.key} className={`panel watch-list watch-list--${section.key}`} aria-label={section.title}>
              <div className="panel-head">
                <div>
                  <h2>{section.title}</h2>
                  <p>{section.blurb(maxOwnership)}</p>
                </div>
              </div>
              {list.length === 0 ? (
                <p className="panel-body note">{section.empty}</p>
              ) : activeSection === "all" ? (
                <ol className="stagger">
                  {list.map((player, index) => {
                    const full = fullPlayer(player);
                    return (
                      <li key={`${player.element ?? player.name}`} style={{ "--i": index } as React.CSSProperties}>
                        <button type="button" className="prow watch-row" onClick={() => full && openProfile(full)} disabled={!full}>
                          {full ? <Face player={full} /> : <span className="face face--md" />}
                          <span className="prow-name">
                            <b>{full?.web_name || player.name}</b>
                            <span>
                              {player.team} · {money(player.value_m)}
                              {player.opponent_team ? ` · ${player.was_home ? "home to" : "away at"} ${player.opponent_team}` : ""}
                            </span>
                          </span>
                          <span className="watch-stat">{section.stat(player)}</span>
                          <Proj value={player.predicted_points} />
                        </button>
                      </li>
                    );
                  })}
                </ol>
              ) : (
                <ol className="watch-cards stagger">
                  {list.map((player, index) => {
                    const full = fullPlayer(player);
                    return (
                      <li key={`${player.element ?? player.name}`} style={{ "--i": index } as React.CSSProperties}>
                        <button type="button" className="watch-card" onClick={() => full && openProfile(full)} disabled={!full}>
                          <span className="watch-card-art" style={clubStyle(player.team)}>
                            <PlayerPhoto src={full?.photo ?? undefined} alt="" name={player.name} variant="card" loading="lazy" />
                            <Pos pos={player.position} />
                          </span>
                          <span className="watch-card-copy">
                            <b>{full?.web_name || player.name}</b>
                            <span className="note">{player.team} · {money(player.value_m)}</span>
                            <span className="watch-card-foot">
                              <span className="watch-stat">{section.stat(player)}</span>
                              <Proj value={player.predicted_points} suffix="pts" />
                            </span>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ol>
              )}
            </section>
          );
        })}
      </div>
    </section>
  );
}
