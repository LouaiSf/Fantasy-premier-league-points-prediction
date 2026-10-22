"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { ClubCrest } from "@/components/club-crest";
import { PlayerPhoto } from "@/components/player-photo";
import { Scatter } from "@/components/charts/scatter";
import { Skeleton } from "@/components/skeleton";
import { EmptyState } from "@/components/empty-state";
import { api } from "@/lib/api";
import type { StatsPlayerRow, StatsPlayersResult, StatsPreset, StatsWindow, TeamRecord } from "@/lib/types";

type Position = "GK" | "DEF" | "MID" | "FWD" | null;

const POSITIONS: { key: Position; label: string }[] = [
  { key: null, label: "All" },
  { key: "GK", label: "GK" },
  { key: "DEF", label: "DEF" },
  { key: "MID", label: "MID" },
  { key: "FWD", label: "FWD" },
];
const WINDOWS: { key: StatsWindow; label: string }[] = [
  { key: "last4", label: "Last 4" },
  { key: "last6", label: "Last 6" },
  { key: "season", label: "Season" },
];
const MIN_MINUTES = [90, 270, 450];
const PAGE = 50;

// label, number of decimals, and whether the value is a 0-1 share.
const METRICS: Record<string, { label: string; title: string; decimals: number; percent?: boolean }> = {
  minutes: { label: "Mins", title: "Minutes played", decimals: 0 },
  points: { label: "Pts", title: "FPL points", decimals: 0 },
  goals: { label: "G", title: "Goals", decimals: 0 },
  assists: { label: "A", title: "Assists", decimals: 0 },
  xg: { label: "xG", title: "Expected goals", decimals: 2 },
  xa: { label: "xA", title: "Expected assists", decimals: 2 },
  xgot: { label: "xGOT", title: "Expected goals on target", decimals: 2 },
  xg_p90: { label: "xG/90", title: "Expected goals per 90", decimals: 2 },
  xa_p90: { label: "xA/90", title: "Expected assists per 90", decimals: 2 },
  xgi_p90: { label: "xGI/90", title: "Expected goal involvements per 90", decimals: 2 },
  xgi_p90_last4: { label: "xGI/90 L4", title: "xGI per 90 over the last 4 gameweeks", decimals: 2 },
  xgi_p90_trend: { label: "xGI trend", title: "Last-4 xGI/90 minus season xGI/90", decimals: 2 },
  xgot_p90: { label: "xGOT/90", title: "xGOT per 90", decimals: 2 },
  goals_minus_xg: { label: "G − xG", title: "Goals minus xG: finishing against chance quality", decimals: 2 },
  xg_minus_goals: { label: "xG − G", title: "xG minus goals: chances that have not gone in yet", decimals: 2 },
  xgot_minus_xg: { label: "xGOT − xG", title: "Shot placement: positive means hitting the target well", decimals: 2 },
  goals_minus_xgot: { label: "G − xGOT", title: "Goals minus xGOT: luck against the keeper", decimals: 2 },
  xa_minus_assists: { label: "xA − A", title: "Expected assists not yet converted by team-mates", decimals: 2 },
  shots: { label: "Shots", title: "Shots", decimals: 0 },
  shots_p90: { label: "Sh/90", title: "Shots per 90", decimals: 2 },
  shots_in_box_p90: { label: "Box sh/90", title: "Shots inside the box per 90", decimals: 2 },
  touches_opp_box_p90: { label: "Box tch/90", title: "Touches in the opposition box per 90", decimals: 1 },
  chances_created_p90: { label: "CC/90", title: "Chances created per 90", decimals: 2 },
  big_chances_created_p90: { label: "BCC/90", title: "Big chances created per 90", decimals: 2 },
  tackles_p90: { label: "Tkl/90", title: "Tackles per 90", decimals: 2 },
  interceptions_p90: { label: "Int/90", title: "Interceptions per 90", decimals: 2 },
  blocks_p90: { label: "Blk/90", title: "Blocks per 90", decimals: 2 },
  clearances_p90: { label: "Clr/90", title: "Clearances per 90", decimals: 2 },
  recoveries_p90: { label: "Rec/90", title: "Ball recoveries per 90", decimals: 2 },
  defcon_p90: { label: "DefCon/90", title: "FPL defensive contribution per 90", decimals: 1 },
  defcon_hit_rate: { label: "DefCon hit", title: "Share of 60+ minute matches reaching the DefCon threshold", decimals: 0, percent: true },
  defcon_prob_next: { label: "DefCon next", title: "Chance of the DefCon bonus next match", decimals: 0, percent: true },
  saves_p90: { label: "Sv/90", title: "Saves per 90", decimals: 2 },
  save_pct: { label: "Save %", title: "Saves over shots on target faced", decimals: 0, percent: true },
  xgot_faced_p90: { label: "xGOT faced/90", title: "xGOT faced per 90", decimals: 2 },
  goals_prevented: { label: "GP", title: "Goals prevented: xGOT faced minus goals conceded", decimals: 2 },
  goals_prevented_p90: { label: "GP/90", title: "Goals prevented per 90", decimals: 2 },
  saves_inside_box_p90: { label: "Box sv/90", title: "Saves from inside the box per 90", decimals: 2 },
  clean_sheet_pct: { label: "CS %", title: "Clean sheets in 60+ minute matches", decimals: 0, percent: true },
};

const DEFAULT_COLUMNS: Record<string, string[]> = {
  all: ["minutes", "points", "xgi_p90", "xg_p90", "xa_p90", "goals_minus_xg", "defcon_p90"],
  GK: ["minutes", "points", "saves_p90", "save_pct", "xgot_faced_p90", "goals_prevented_p90", "clean_sheet_pct"],
  DEF: ["minutes", "points", "defcon_p90", "defcon_hit_rate", "xgi_p90", "tackles_p90", "clearances_p90"],
  MID: ["minutes", "points", "xgi_p90", "defcon_p90", "chances_created_p90", "touches_opp_box_p90", "xgot_minus_xg"],
  FWD: ["minutes", "points", "xg_p90", "xgot_p90", "shots_in_box_p90", "touches_opp_box_p90", "goals_minus_xg"],
};

const DEFAULT_SCATTER = { x: "xg", y: "goals", diagonal: true };

function format(value: number | null | undefined, key: string): string {
  if (value == null) return "—";
  const spec = METRICS[key];
  if (spec?.percent) return `${Math.round(value * 100)}%`;
  return value.toFixed(spec?.decimals ?? 2);
}

function updatedLabel(iso: string | null): string {
  if (!iso) return "not synced";
  const when = new Date(iso);
  return Number.isNaN(when.getTime())
    ? "not synced"
    : when.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function StatsPage() {
  const { snapshot, squadPlayers, openProfile } = useApp();
  const [position, setPosition] = React.useState<Position>(null);
  const [windowKey, setWindowKey] = React.useState<StatsWindow>("season");
  const [minMinutes, setMinMinutes] = React.useState(270);
  const [preset, setPreset] = React.useState<string | null>(null);
  const [query, setQuery] = React.useState("");
  const [sort, setSort] = React.useState<{ key: string; desc: boolean } | null>(null);
  const [shown, setShown] = React.useState(PAGE);
  const [data, setData] = React.useState<StatsPlayersResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  // The chart is drawn at its container's width rather than scaled down to
  // it, so the axis labels keep their size on a phone.
  const scatterFrame = React.useRef<HTMLDivElement>(null);
  const [scatterWidth, setScatterWidth] = React.useState(720);
  React.useEffect(() => {
    const frame = scatterFrame.current;
    if (!frame) return;
    const observer = new ResizeObserver(([entry]) =>
      setScatterWidth(Math.max(280, Math.min(720, Math.floor(entry.contentRect.width)))));
    observer.observe(frame);
    return () => observer.disconnect();
  }, [data]);

  React.useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api.statsPlayers({ window: windowKey, position, minMinutes, preset }, controller.signal).then(
      (result) => {
        setData(result);
        setLoading(false);
      },
      (err: Error) => {
        if (controller.signal.aborted) return;
        setError(err.message);
        setLoading(false);
      },
    );
    return () => controller.abort();
  }, [windowKey, position, minMinutes, preset]);

  const presetSpec: StatsPreset | null = data?.presets.find((p) => p.id === preset) ?? null;
  const columns = presetSpec?.columns ?? DEFAULT_COLUMNS[position ?? "all"];
  const owned = React.useMemo(() => new Set(squadPlayers.map((p) => p.element)), [squadPlayers]);
  const byElement = React.useMemo(
    () => new Map((snapshot?.players ?? []).map((p) => [p.element, p])),
    [snapshot],
  );

  const rows = React.useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    const filtered = (data?.rows ?? []).filter(
      (row) => !needle || row.name.toLocaleLowerCase().includes(needle) || row.team.toLocaleLowerCase().includes(needle),
    );
    if (!sort) return filtered;
    return [...filtered].sort((a, b) => {
      const av = a.metrics[sort.key];
      const bv = b.metrics[sort.key];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return sort.desc ? bv - av : av - bv;
    });
  }, [data, query, sort]);

  // Each metric cell carries a bar for its rank within the rows on screen.
  const percentiles = React.useMemo(() => {
    const out: Record<string, Map<number, number>> = {};
    for (const key of columns) {
      const values = rows
        .map((row) => [row.id, row.metrics[key]] as const)
        .filter((entry): entry is readonly [number, number] => entry[1] != null)
        .sort((a, b) => a[1] - b[1]);
      out[key] = new Map(values.map(([id], index) => [id, values.length > 1 ? index / (values.length - 1) : 1]));
    }
    return out;
  }, [rows, columns]);

  const activeSort = sort?.key ?? data?.sort;
  const scatterSpec = presetSpec?.scatter ?? DEFAULT_SCATTER;
  const scatterPoints = rows
    .filter((row) => row.metrics[scatterSpec.x] != null && row.metrics[scatterSpec.y] != null)
    .slice(0, 150)
    .map((row) => ({
      id: row.id,
      x: Number((row.metrics[scatterSpec.x] as number).toFixed(3)),
      y: Number((row.metrics[scatterSpec.y] as number).toFixed(3)),
      label: row.name,
      highlight: owned.has(row.id),
    }));

  const openPlayer = (id: number) => {
    const player = byElement.get(id);
    if (player) openProfile(player);
  };

  const fotmobMissing = data && !data.has_fotmob;

  return (
    <section className="page stats-page" aria-label="Stats Lab">
      <div className="shell">
        <div className="section-head">
          <div>
            <p className="eyebrow lime">
              Match data: FotMob · FPL official · updated {updatedLabel(data?.fotmob_updated_at ?? null)}
            </p>
            <h1 className="display-hero">Stats Lab</h1>
          </div>
          <p>
            The numbers under the points: chance quality, finishing, defensive work and
            shot-stopping, per 90 minutes.
            {data?.window ? ` GW${data.window.gw_from}–GW${data.window.gw_to}.` : ""}
          </p>
        </div>

        <div className="stats-controls">
          <div className="horizon-tabs" role="group" aria-label="Position">
            {POSITIONS.map((item) => (
              <button
                key={item.label}
                type="button"
                className={position === item.key ? "is-active" : ""}
                aria-pressed={position === item.key}
                onClick={() => {
                  setPosition(item.key);
                  setSort(null);
                  if (presetSpec && item.key && !presetSpec.positions.includes(item.key)) setPreset(null);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="horizon-tabs" role="group" aria-label="Gameweek window">
            {WINDOWS.map((item) => (
              <button
                key={item.key}
                type="button"
                className={windowKey === item.key ? "is-active" : ""}
                aria-pressed={windowKey === item.key}
                onClick={() => setWindowKey(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="horizon-tabs" role="group" aria-label="Minimum minutes">
            {MIN_MINUTES.map((value) => (
              <button
                key={value}
                type="button"
                className={minMinutes === value ? "is-active" : ""}
                aria-pressed={minMinutes === value}
                onClick={() => setMinMinutes(value)}
              >
                {value}+ min
              </button>
            ))}
          </div>
          <label className="search stats-search">
            <span className="sr-only">Search players</span>
            <input
              type="search"
              placeholder="Search player or club"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setShown(PAGE);
              }}
            />
          </label>
        </div>

        <div className="mini-chips stats-presets" role="group" aria-label="Presets">
          <button
            type="button"
            className={`mini-chip${preset === null ? " is-active" : ""}`}
            aria-pressed={preset === null}
            onClick={() => {
              setPreset(null);
              setSort(null);
            }}
          >
            Overview
          </button>
          {(data?.presets ?? []).map((item) => (
            <button
              key={item.id}
              type="button"
              className={`mini-chip${preset === item.id ? " is-active" : ""}`}
              aria-pressed={preset === item.id}
              onClick={() => {
                setPreset(item.id);
                setSort(null);
                setShown(PAGE);
                if (position && !item.positions.includes(position)) setPosition(null);
              }}
            >
              {item.label}
            </button>
          ))}
        </div>

        {fotmobMissing && (
          <p className="stats-note">
            FotMob data isn&apos;t synced on this server, so xGOT, box touches, blocks,
            interceptions and goals prevented show as —. FPL&apos;s own numbers are complete.
          </p>
        )}

        {error ? (
          <EmptyState title="Stats unavailable" message={error} />
        ) : loading && !data ? (
          <Skeleton variant="table" count={12} />
        ) : (
          <>
            <div className="stats-overview">
            {scatterPoints.length > 2 && (
              <figure className="stats-scatter">
                <figcaption className="kicker">
                  {METRICS[scatterSpec.x]?.title ?? scatterSpec.x} vs{" "}
                  {METRICS[scatterSpec.y]?.title ?? scatterSpec.y}
                  {owned.size > 0 ? " · your players in lime" : ""}
                </figcaption>
                <div className="stats-scatter-frame" ref={scatterFrame}>
                  <Scatter
                    points={scatterPoints}
                    xLabel={METRICS[scatterSpec.x]?.label ?? scatterSpec.x}
                    yLabel={METRICS[scatterSpec.y]?.label ?? scatterSpec.y}
                    diagonal={scatterSpec.diagonal}
                    width={scatterWidth}
                    height={Math.round(Math.max(240, scatterWidth * 0.5))}
                    onSelect={(id) => openPlayer(Number(id))}
                  />
                </div>
              </figure>
            )}
            {data && data.teams.length > 0 && <TeamTable data={data} teams={snapshot?.teams ?? []} />}
            </div>

            <p className="stats-count kicker">
              {rows.length} players{loading ? " · updating…" : ""}
            </p>
            <div className="stats-table-frame" tabIndex={0} role="region" aria-label="Stats table">
              <table className="stats-table">
                <thead>
                  <tr>
                    <th scope="col" className="stats-player-col">Player</th>
                    {columns.map((key) => {
                      const isSorted = activeSort === key;
                      const desc = isSorted ? (sort ? sort.desc : presetSpec?.desc ?? true) : true;
                      return (
                        <th
                          key={key}
                          scope="col"
                          className={isSorted ? "is-sorted" : ""}
                          aria-sort={isSorted ? (desc ? "descending" : "ascending") : "none"}
                        >
                          <button
                            type="button"
                            title={METRICS[key]?.title ?? key}
                            onClick={() =>
                              setSort((current) =>
                                current?.key === key ? { key, desc: !current.desc } : { key, desc: true },
                              )
                            }
                          >
                            {METRICS[key]?.label ?? key}
                            {isSorted ? (desc ? " ↓" : " ↑") : ""}
                          </button>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody className="stagger">
                  {rows.slice(0, shown).map((row, index) => (
                    <StatsRow
                      key={row.id}
                      row={row}
                      index={index}
                      columns={columns}
                      percentiles={percentiles}
                      owned={owned.has(row.id)}
                      photo={byElement.get(row.id)?.photo ?? null}
                      teamCode={byElement.get(row.id)?.team_code ?? null}
                      teamShort={byElement.get(row.id)?.team_short ?? row.team.slice(0, 3).toUpperCase()}
                      onOpen={() => openPlayer(row.id)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            {rows.length === 0 && (
              <EmptyState title="No players match" message="Lower the minimum minutes or clear the search." />
            )}
            {rows.length > shown && (
              <button type="button" className="btn ghost stats-more" onClick={() => setShown((n) => n + PAGE)}>
                Show {Math.min(PAGE, rows.length - shown)} more
              </button>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function StatsRow({
  row, index, columns, percentiles, owned, photo, teamCode, teamShort, onOpen,
}: {
  readonly row: StatsPlayerRow;
  readonly index: number;
  readonly columns: string[];
  readonly percentiles: Record<string, Map<number, number>>;
  readonly owned: boolean;
  readonly photo: string | null;
  readonly teamCode: number | null;
  readonly teamShort: string;
  readonly onOpen: () => void;
}) {
  return (
    <tr className={owned ? "is-owned" : ""} style={{ "--i": Math.min(index, 12) } as React.CSSProperties}>
      <th scope="row" className="stats-player-col">
        <button type="button" className="stats-player" onClick={onOpen}>
          <PlayerPhoto src={photo ?? undefined} alt="" name={row.name} variant="avatar" loading="lazy" />
          <span className="stats-player-name">{row.name}</span>
          <span className="stats-player-meta">
            {teamCode != null && (
              <ClubCrest code={teamCode} team={row.team} shortName={teamShort} width={16} height={16} />
            )}
            {teamShort} · {row.position}
          </span>
        </button>
      </th>
      {columns.map((key) => {
        const value = row.metrics[key];
        const pct = percentiles[key]?.get(row.id);
        return (
          <td key={key} className={value == null ? "is-empty" : ""}>
            <span className="data">{format(value, key)}</span>
            {pct != null && (
              <span className="stats-bar" aria-hidden="true">
                <i
                  style={{ transform: `scaleX(${Math.max(0.04, pct)})` }}
                  className={pct >= 0.9 ? "is-top" : ""}
                />
              </span>
            )}
          </td>
        );
      })}
    </tr>
  );
}

// Rolling team chance quality: what a defender's clean-sheet odds and an
// attacker's returns are built on. xGOT against needs FotMob.
function TeamTable({ data, teams }: { readonly data: StatsPlayersResult; readonly teams: TeamRecord[] }) {
  const [sortKey, setSortKey] = React.useState<"xg_for_6" | "xg_against_6">("xg_for_6");
  const byName = new Map(teams.map((team) => [team.name, team]));
  const rows = [...data.teams].sort((a, b) =>
    sortKey === "xg_for_6"
      ? (b.xg_for_6 ?? 0) - (a.xg_for_6 ?? 0)
      : (a.xg_against_6 ?? 0) - (b.xg_against_6 ?? 0),
  );
  return (
    <section className="stats-teams" aria-label="Team expected goals, last 6 matches">
      <p className="kicker">Teams · last 6 matches, per game</p>
      <div className="stats-teams-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Club</th>
              <th scope="col" aria-sort={sortKey === "xg_for_6" ? "descending" : "none"}>
                <button type="button" className="text-button" onClick={() => setSortKey("xg_for_6")}>xG for</button>
              </th>
              <th scope="col" aria-sort={sortKey === "xg_against_6" ? "ascending" : "none"}>
                <button type="button" className="text-button" onClick={() => setSortKey("xg_against_6")}>xG ag</button>
              </th>
              {data.has_fotmob && <th scope="col">xGOT ag</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const team = byName.get(row.team);
              return (
                <tr key={row.team}>
                  <td>
                    <span className="stats-teams-club">
                      {team && <ClubCrest code={team.code} team={team.name} shortName={team.short_name} width={16} height={16} />}
                      {team?.short_name ?? row.team}
                    </span>
                  </td>
                  <td>{row.xg_for_6?.toFixed(2) ?? "—"}</td>
                  <td>{row.xg_against_6?.toFixed(2) ?? "—"}</td>
                  {data.has_fotmob && <td>{row.xgot_against_6?.toFixed(2) ?? "—"}</td>}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
