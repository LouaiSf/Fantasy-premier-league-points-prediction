"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { clubStyle } from "@/lib/club-colors";
import { money, num } from "@/lib/format";
import type { PlayerRecord } from "@/lib/types";
import { Loading } from "@/components/loading";
import { Face, GateSign, Pos, Proj, Segmented, VerdictPlate } from "@/components/signage";
import { Icon } from "@/components/icons";

const POSITIONS = ["ALL", "GK", "DEF", "MID", "FWD"] as const;
const POOLS = [
  { key: "all", label: "All" },
  { key: "squad", label: "My squad" },
  { key: "market", label: "Not in my squad" },
] as const;

const METRICS: [string, keyof PlayerRecord, number][] = [
  ["Expected points this week", "predicted_points", 1],
  ["Form", "form", 1],
  ["Points this season", "total_points", 0],
  ["Minutes", "minutes", 0],
  ["Goals", "goals_scored", 0],
  ["Assists", "assists", 0],
  ["Clean sheets", "clean_sheets", 0],
  ["Bonus", "bonus", 0],
  ["ICT index", "ict_index", 1],
  ["Expected goals", "expected_goals", 2],
  ["Expected assists", "expected_assists", 2],
  ["Owned by (%)", "selected_by", 1],
];


export default function ComparisonPage() {
  return (
    <React.Suspense fallback={<Loading label="Loading players…" />}>
      <ComparisonPageInner />
    </React.Suspense>
  );
}

function ComparisonPageInner() {
  const { snapshot, loading, squadElements } = useApp();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [seatA, setSeatA] = React.useState<number | null>(null);
  const [seatB, setSeatB] = React.useState<number | null>(null);
  const [activeSeat, setActiveSeat] = React.useState<"A" | "B">("A");
  const [pool, setPool] = React.useState<(typeof POOLS)[number]["key"]>("all");
  const [poolDefaulted, setPoolDefaulted] = React.useState(false);
  const [position, setPosition] = React.useState<(typeof POSITIONS)[number]>("ALL");
  const [club, setClub] = React.useState("ALL");
  const [query, setQuery] = React.useState("");
  const [hydratedFromUrl, setHydratedFromUrl] = React.useState(false);

  // Most comparisons start from a player you already own, so open on the squad
  // pool when there is one. Applied once: after that the pool is the user's
  // choice and must not be reset underneath them when the squad reloads.
  React.useEffect(() => {
    if (poolDefaulted || squadElements.length === 0) return;
    const timer = window.setTimeout(() => {
      setPool("squad");
      setPoolDefaulted(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [poolDefaulted, squadElements.length]);

  // Mirror ?a=/?b= into state once hydrated, and keep the URL in sync
  // thereafter so a comparison can be bookmarked or shared. Reading the URL
  // straight into useState's initializer would mismatch the static-prerendered
  // (always-empty) markup, so this stays a post-mount effect; the write-back
  // effect waits for it so it doesn't clobber ?a=/?b= with the pre-hydration
  // empty state on first paint.
  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      const a = searchParams.get("a");
      const b = searchParams.get("b");
      setSeatA(a ? Number(a) : null);
      setSeatB(b ? Number(b) : null);
      setHydratedFromUrl(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [searchParams]);

  React.useEffect(() => {
    if (!hydratedFromUrl) return;
    const params = new URLSearchParams();
    if (seatA != null) params.set("a", String(seatA));
    if (seatB != null) params.set("b", String(seatB));
    const qs = params.toString();
    router.replace(qs ? `?${qs}` : "?", { scroll: false });
  }, [seatA, seatB, hydratedFromUrl, router]);

  if (loading || !snapshot) {
    return (
      <section className="page">
        <div className="shell">
          <Loading label="Loading players…" />
        </div>
      </section>
    );
  }

  const byElement = new Map(snapshot.players.map((player) => [player.element, player]));
  const playerA = seatA != null ? byElement.get(seatA) ?? null : null;
  const playerB = seatB != null ? byElement.get(seatB) ?? null : null;
  const squadIdSet = new Set(squadElements);
  const allSorted = [...snapshot.players].sort((a, b) =>
    (a.web_name || a.name).localeCompare(b.web_name || b.name),
  );

  const candidates = snapshot.players.filter((player) => {
    if (pool === "squad" && !squadIdSet.has(player.element)) return false;
    if (pool === "market" && squadIdSet.has(player.element)) return false;
    if (position !== "ALL" && player.position !== position) return false;
    if (club !== "ALL" && player.team !== club) return false;
    return `${player.name} ${player.team}`.toLowerCase().includes(query.trim().toLowerCase());
  });

  function fillSeat(player: PlayerRecord) {
    if (activeSeat === "A") {
      setSeatA(player.element);
      setActiveSeat("B");
    } else {
      setSeatB(player.element);
      setActiveSeat("A");
    }
  }

  function swap() {
    setSeatA(seatB);
    setSeatB(seatA);
  }

  const bothFilled = Boolean(playerA && playerB);
  let aWins = 0;
  let bWins = 0;
  if (playerA && playerB) {
    for (const [, key] of METRICS) {
      const a = Number(playerA[key] ?? 0);
      const b = Number(playerB[key] ?? 0);
      if (a > b) aWins++;
      else if (b > a) bWins++;
    }
  }


  const winner = playerA && playerB && aWins !== bWins ? (aWins > bWins ? playerA : playerB) : null;
  const loser = winner && playerA && playerB ? (winner === playerA ? playerB : playerA) : null;

  function Seat({ seat, player }: { seat: "A" | "B"; player: PlayerRecord | null }) {
    const target = activeSeat === seat;
    return (
      <div className={`seat${player ? " is-filled" : ""}${target ? " is-target" : ""}`} style={player ? clubStyle(player.team) : undefined}>
        <button type="button" className="seat-face" onClick={() => setActiveSeat(seat)} aria-pressed={target}>
          {player ? (
            <>
              <span className="seat-cutout" aria-hidden="true">
                <PlayerPhoto
                  key={player.element}
                  src={player.photo_large ?? player.photo ?? undefined}
                  fallbackSrc={player.photo ?? undefined}
                  alt=""
                  name={player.name}
                  variant="hero"
                />
              </span>
              <span className="seat-copy">
                <Pos pos={player.position} />
                <b>{player.web_name}</b>
                <span>
                  {player.team} · {money(player.value_m)}
                </span>
              </span>
            </>
          ) : (
            <span className="seat-copy seat-empty">
              <b>Player {seat}</b>
              <span>{target ? "Pick someone from the list below." : "Tap here, then pick from the list."}</span>
            </span>
          )}
          {target && <span className="seat-flag">Choosing</span>}
        </button>
        <label className="seat-select">
          <span className="sr-only">Player {seat}</span>
          <select
            className="select select--sm"
            value={(seat === "A" ? seatA : seatB) ?? ""}
            onChange={(event) => (seat === "A" ? setSeatA : setSeatB)(event.target.value ? Number(event.target.value) : null)}
          >
            <option value="">Choose a player…</option>
            {allSorted.map((option) => (
              <option key={option.element} value={option.element}>
                {option.web_name || option.name} · {option.team_short}
              </option>
            ))}
          </select>
        </label>
      </div>
    );
  }

  return (
    <section className="page compare-page" aria-label="Compare">
      <GateSign />

      <div className="seats">
        {Seat({ seat: "A", player: playerA })}
        <button className="seat-swap" type="button" onClick={swap} aria-label="Swap the two players" disabled={!playerA && !playerB}>
          <Icon name="swap" size={22} />
        </button>
        {Seat({ seat: "B", player: playerB })}
      </div>

      {bothFilled && playerA && playerB && (
        <>
          <VerdictPlate
            tone="stats"
            label="Verdict"
            player={winner}
            title={
              winner && loser ? (
                <>
                  {winner.web_name} edges it, {Math.max(aWins, bWins)} to {Math.min(aWins, bWins)}.
                </>
              ) : (
                <>Too close to call.</>
              )
            }
            body={
              winner && loser
                ? `He comes out ahead on ${Math.max(aWins, bWins)} of ${METRICS.length} measures. ${loser.web_name} still wins ${Math.min(aWins, bWins)}, so check which ones matter to you below.`
                : `They split the ${METRICS.length} measures evenly. Fixtures and form are the tie-breakers.`
            }
          />
          <section className="panel metrics" aria-label="Side by side">
            <div className="metrics-head">
              <span>{playerA.web_name}</span>
              <span>{playerB.web_name}</span>
            </div>
            {METRICS.map(([label, key, digits]) => {
              const a = Number(playerA[key] ?? 0);
              const b = Number(playerB[key] ?? 0);
              const total = Math.abs(a) + Math.abs(b) || 1;
              const leader = a > b ? "a" : b > a ? "b" : null;
              return (
                <div className="duel-row" key={label}>
                  <b className={leader === "a" ? "is-lead" : undefined}>{num(a, digits)}</b>
                  <div className="duel-mid">
                    <span>{label}</span>
                    <div className="duel-bars">
                      <i className={leader === "a" ? "is-lead" : undefined} style={{ width: `${(Math.abs(a) / total) * 100}%` }} />
                      <i className={leader === "b" ? "is-lead" : undefined} style={{ width: `${(Math.abs(b) / total) * 100}%` }} />
                    </div>
                  </div>
                  <b className={leader === "b" ? "is-lead" : undefined}>{num(b, digits)}</b>
                </div>
              );
            })}
          </section>
        </>
      )}

      <section className="panel picker" aria-label={`Choose player ${activeSeat}`}>
        <div className="panel-head picker-bar">
          <h2>Choose player {activeSeat}</h2>
          <label className="searchbox">
            <span className="sr-only">Search</span>
            <Icon name="search" size={18} />
            <input className="input input--sm" type="search" placeholder="Player or club" value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
        </div>
        <div className="toolbar picker-filters">
          <Segmented label="From" value={pool} onChange={setPool} options={POOLS.map((item) => ({ value: item.key, label: item.label }))} />
          <Segmented label="Position" value={position} onChange={setPosition} options={POSITIONS.map((item) => ({ value: item, label: item === "ALL" ? "All" : item }))} />
          <label>
            <span className="sr-only">Club</span>
            <select className="select select--sm" value={club} onChange={(event) => setClub(event.target.value)}>
              <option value="ALL">All clubs</option>
              {snapshot.teams.map((team) => (
                <option key={team.id} value={team.name}>
                  {team.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="teamsheet">
          {POSITIONS.slice(1).map((pos) => {
            const rows = candidates.filter((player) => player.position === pos);
            if (!rows.length) return null;
            return (
              <div key={pos}>
                <div className="ts-head">
                  <Pos pos={pos} />
                  <b>{rows.length > 60 ? `Top 60 of ${rows.length}` : `${rows.length} players`}</b>
                </div>
                <div className="ts-rows">
                  {rows.slice(0, 60).map((player) => (
                    <button
                      key={player.element}
                      type="button"
                      className={`ts-row${player.element === seatA || player.element === seatB ? " is-chosen" : ""}`}
                      onClick={() => fillSeat(player)}
                    >
                      {player.element === seatA && <span className="ts-seat">A</span>}
                      {player.element === seatB && <span className="ts-seat">B</span>}
                      <Face player={player} size="sm" />
                      <span className="ts-name">
                        <b>{player.web_name || player.name}</b>
                        <span>
                          {player.team_short} · {money(player.value_m)}
                        </span>
                      </span>
                      <Proj value={player.predicted_points ?? player.form} />
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
          {!candidates.length && <p className="picker-empty">Nobody matches. Try another club or position.</p>}
        </div>
      </section>
    </section>
  );
}
