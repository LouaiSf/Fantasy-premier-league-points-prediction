"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { ClubCrest } from "@/components/club-crest";
import { clubStyle } from "@/lib/club-colors";
import { money, num } from "@/lib/format";
import type { PlayerRecord } from "@/lib/types";
import { Loading } from "@/components/loading";

const POSITIONS = ["ALL", "GK", "DEF", "MID", "FWD"] as const;
const POOLS = [
  { key: "all", label: "All" },
  { key: "squad", label: "My squad" },
  { key: "market", label: "Market targets" },
] as const;

const METRICS: [string, keyof PlayerRecord, number][] = [
  ["Projected points", "predicted_points", 1],
  ["Form", "form", 1],
  ["Total points", "total_points", 0],
  ["Minutes", "minutes", 0],
  ["Goals", "goals_scored", 0],
  ["Assists", "assists", 0],
  ["Clean sheets", "clean_sheets", 0],
  ["Bonus", "bonus", 0],
  ["ICT index", "ict_index", 1],
  ["Expected goals", "expected_goals", 2],
  ["Expected assists", "expected_assists", 2],
  ["Ownership %", "selected_by", 1],
];


export default function ComparisonPage() {
  return (
    <React.Suspense fallback={<Loading label="Loading season data…" />}>
      <ComparisonPageInner />
    </React.Suspense>
  );
}

function ComparisonPageInner() {
  const { snapshot, loading, squadNames } = useApp();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [seatA, setSeatA] = React.useState<number | null>(null);
  const [seatB, setSeatB] = React.useState<number | null>(null);
  const [activeSeat, setActiveSeat] = React.useState<"A" | "B">("A");
  const [pool, setPool] = React.useState<(typeof POOLS)[number]["key"]>("all");
  const [position, setPosition] = React.useState<(typeof POSITIONS)[number]>("ALL");
  const [club, setClub] = React.useState("ALL");
  const [query, setQuery] = React.useState("");
  const [hydratedFromUrl, setHydratedFromUrl] = React.useState(false);

  // Mirror ?a=/?b= into state once hydrated, and keep the URL in sync
  // thereafter so a comparison can be bookmarked or shared. Reading the URL
  // straight into useState's initializer would mismatch the static-prerendered
  // (always-empty) markup, so this stays a post-mount effect; the write-back
  // effect waits for it so it doesn't clobber ?a=/?b= with the pre-hydration
  // empty state on first paint.
  React.useEffect(() => {
    const a = searchParams.get("a");
    const b = searchParams.get("b");
    setSeatA(a ? Number(a) : null);
    setSeatB(b ? Number(b) : null);
    setHydratedFromUrl(true);
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
          <Loading label="Loading season data…" />
        </div>
      </section>
    );
  }

  const byElement = new Map(snapshot.players.map((player) => [player.element, player]));
  const teamCodeByName = new Map(snapshot.teams.map((team) => [team.name, team.code]));
  const playerA = seatA != null ? byElement.get(seatA) ?? null : null;
  const playerB = seatB != null ? byElement.get(seatB) ?? null : null;
  const squadNameSet = new Set(squadNames);
  const allSorted = [...snapshot.players].sort((a, b) =>
    (a.web_name || a.name).localeCompare(b.web_name || b.name),
  );

  const candidates = snapshot.players.filter((player) => {
    if (pool === "squad" && !squadNameSet.has(player.name)) return false;
    if (pool === "market" && squadNameSet.has(player.name)) return false;
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

  return (
    <section className="page cmp-page">
      <div className="shell">
        <div className="section-head">
          <div>
            <p className="eyebrow" style={{ color: "var(--cyan)" }}>
              Head to head
            </p>
            <h1>Select the duel</h1>
          </div>
          <p>
            Choose Player A and Player B from the local snapshot. The arena and category
            breakdown unlock once both seats are filled.
          </p>
        </div>

        <div className="duel-stage">
          <div className="seat-select-row">
            <div className="seat-select">
              <label htmlFor="seatASelect">Player A</label>
              <select
                id="seatASelect"
                value={seatA ?? ""}
                onChange={(event) => setSeatA(event.target.value ? Number(event.target.value) : null)}
              >
                <option value="">Choose a player…</option>
                {allSorted.map((player) => (
                  <option key={player.element} value={player.element}>
                    {player.web_name || player.name} · {player.team_short}
                  </option>
                ))}
              </select>
            </div>
            <span className="vs" aria-hidden="true">
              VS
            </span>
            <div className="seat-select">
              <label htmlFor="seatBSelect">Player B</label>
              <select
                id="seatBSelect"
                value={seatB ?? ""}
                onChange={(event) => setSeatB(event.target.value ? Number(event.target.value) : null)}
              >
                <option value="">Choose a player…</option>
                {allSorted.map((player) => (
                  <option key={player.element} value={player.element}>
                    {player.web_name || player.name} · {player.team_short}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="plinth-row">
            <button
              type="button"
              className={`plinth${activeSeat === "A" ? " is-target" : ""}${playerA ? " is-filled" : ""}`}
              style={playerA ? clubStyle(playerA.team) : undefined}
              onClick={() => setActiveSeat("A")}
            >
              <span className="ghost-num" aria-hidden="true">
                A
              </span>
              {playerA ? (
                <>
                  <div className="shot">
                    <PlayerPhoto src={playerA.photo ?? undefined} alt={playerA.name} name={playerA.name} />
                  </div>
                  <span className="plinth-copy">
                    <span className="slotlabel">Player A</span>
                    <h3>{playerA.web_name}</h3>
                    <span className="meta">
                      {playerA.team} · {money(playerA.value_m)}
                    </span>
                  </span>
                </>
              ) : (
                <span className="plinth-copy">
                  <span className="slotlabel">Player A</span>
                  <span className="plinth-empty">
                    <b>Empty seat</b>
                    <span>Pick from your squad or the wider market below.</span>
                  </span>
                </span>
              )}
            </button>
            <div className="duel-vs">
              <span className="vs">VS</span>
              <button className="swapper" type="button" onClick={swap} aria-label="Swap comparison sides">
                ⇄
              </button>
            </div>
            <button
              type="button"
              className={`plinth${activeSeat === "B" ? " is-target" : ""}${playerB ? " is-filled" : ""}`}
              style={playerB ? clubStyle(playerB.team) : undefined}
              onClick={() => setActiveSeat("B")}
            >
              <span className="ghost-num" aria-hidden="true">
                B
              </span>
              {playerB ? (
                <>
                  <div className="shot">
                    <PlayerPhoto src={playerB.photo ?? undefined} alt={playerB.name} name={playerB.name} />
                  </div>
                  <span className="plinth-copy">
                    <span className="slotlabel">Player B</span>
                    <h3>{playerB.web_name}</h3>
                    <span className="meta">
                      {playerB.team} · {money(playerB.value_m)}
                    </span>
                  </span>
                </>
              ) : (
                <span className="plinth-copy">
                  <span className="slotlabel">Player B</span>
                  <span className="plinth-empty">
                    <b>Empty seat</b>
                    <span>Compare an owned player against a target.</span>
                  </span>
                </span>
              )}
            </button>
          </div>

          <div className="picker">
            <div className="picker-head">
              <h3>Filling seat {activeSeat}</h3>
              <label className="search">
                <input
                  type="search"
                  placeholder="Search by player or club"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
            </div>
            <div className="picker-filters">
              <div className="group">
                <span>Pool</span>
                {POOLS.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    className={`mini-chip${pool === item.key ? " is-active" : ""}`}
                    onClick={() => setPool(item.key)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <div className="group">
                <span>Position</span>
                {POSITIONS.map((item) => (
                  <button
                    key={item}
                    type="button"
                    className={`mini-chip${position === item ? " is-active" : ""}`}
                    onClick={() => setPosition(item)}
                  >
                    {item === "ALL" ? "All" : item}
                  </button>
                ))}
              </div>
              <div className="group">
                <span>Club</span>
                <select
                  className="mini-chip"
                  style={{ minHeight: 30 }}
                  value={club}
                  onChange={(event) => setClub(event.target.value)}
                >
                  <option value="ALL">All clubs</option>
                  {snapshot.teams.map((team) => (
                    <option key={team.id} value={team.name}>
                      {team.short_name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="teamsheet">
              {POSITIONS.slice(1).map((pos) => {
                const rows = candidates.filter((player) => player.position === pos);
                if (!rows.length) return null;
                return (
                  <div key={pos}>
                    <div className="ts-head">
                      <span className="mark">{pos}</span>
                      <b>{pos}</b>
                      <span className="rule" />
                    </div>
                    <div className="ts-rows">
                      {rows.slice(0, 60).map((player) => (
                        <button
                          key={player.element}
                          type="button"
                          className={`ts-row${player.element === seatA || player.element === seatB ? " is-chosen" : ""}`}
                          onClick={() => fillSeat(player)}
                        >
                          {player.element === seatA && <span className="ts-seat">Seat A</span>}
                          {player.element === seatB && <span className="ts-seat">Seat B</span>}
                          <span className="shot">
                            {player.photo && <PlayerPhoto src={player.photo} alt="" loading="lazy" />}
                          </span>
                          <span className="ts-name">
                            <b>{player.web_name || player.name}</b>
                            <span>{player.team_short}</span>
                          </span>
                          <span className="ts-num">
                            <span className="price">{money(player.value_m)}</span>
                            <span className="proj">{num(player.predicted_points ?? player.form)}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
              {!candidates.length && <p className="picker-empty">No players match that search.</p>}
            </div>
          </div>
        </div>
      </div>

      {bothFilled && playerA && playerB && (
        <div className="cmp-arena">
          <div className="shell">
            <div className="horizon">
              <span className="kicker">Comparison basis</span>
              <span style={{ fontSize: 12, color: "var(--muted-light)" }}>
                Season-to-date totals and current form from the local snapshot.
              </span>
            </div>
            <div className="cmp-cards">
              <div className="cmp-card left" style={clubStyle(playerA.team)}>
                <ClubCrest
                  className="cmp-crest"
                  code={teamCodeByName.get(playerA.team)}
                  team={playerA.team}
                  aria-hidden="true"
                />
                <span className="ghost-num" aria-hidden="true">
                  A
                </span>
                <div className="shot">
                  <PlayerPhoto src={playerA.photo ?? undefined} alt={playerA.name} name={playerA.name} />
                </div>
                <div className="cmp-copy">
                  <span className="kicker">
                    {playerA.team} / {playerA.position}
                  </span>
                  <h2>{playerA.web_name}</h2>
                  <span className="meta">{num(playerA.selected_by)}% owned</span>
                  <span className="price">{money(playerA.value_m)}</span>
                </div>
              </div>
              <div className="cmp-card right" style={clubStyle(playerB.team)}>
                <ClubCrest
                  className="cmp-crest"
                  code={teamCodeByName.get(playerB.team)}
                  team={playerB.team}
                  aria-hidden="true"
                />
                <span className="ghost-num" aria-hidden="true">
                  B
                </span>
                <div className="shot">
                  <PlayerPhoto src={playerB.photo ?? undefined} alt={playerB.name} name={playerB.name} />
                </div>
                <div className="cmp-copy">
                  <span className="kicker">
                    {playerB.team} / {playerB.position}
                  </span>
                  <h2>{playerB.web_name}</h2>
                  <span className="meta">{num(playerB.selected_by)}% owned</span>
                  <span className="price">{money(playerB.value_m)}</span>
                </div>
              </div>
            </div>
            <div className="cmp-ribbon">
              <div className="side">
                <div>
                  <span>Form</span>
                  <b>{num(playerA.form)}</b>
                </div>
              </div>
              <button className="swapper" type="button" onClick={swap} aria-label="Swap comparison sides">
                ⇄
              </button>
              <div className="side right">
                <div>
                  <span>Form</span>
                  <b>{num(playerB.form)}</b>
                </div>
              </div>
            </div>
          </div>
          <div className="cmp-data paper-scope">
            <div className="shell">
              <div className="acc">
                {METRICS.map(([label, key, digits]) => {
                  const a = Number(playerA[key] ?? 0);
                  const b = Number(playerB[key] ?? 0);
                  const total = a + b || 1;
                  const leader = a > b ? "l" : b > a ? "r" : null;
                  return (
                    <div className="acc-item" key={label}>
                      <div className="mrow">
                        <strong className={leader === "l" ? "leader l" : ""}>{num(a, digits)}</strong>
                        <div className="barcell">
                          <span>{label}</span>
                          <div className="dualbar">
                            <i style={{ width: `${(a / total) * 100}%`, background: "var(--pl-purple)" }} />
                            <i style={{ width: `${(b / total) * 100}%`, background: "var(--pink)" }} />
                          </div>
                        </div>
                        <strong className={leader === "r" ? "leader r" : ""}>{num(b, digits)}</strong>
                      </div>
                    </div>
                  );
                })}
              </div>
              {(() => {
                const tie = aWins === bWins;
                const winner = tie ? null : aWins > bWins ? playerA : playerB;
                const loser = tie ? null : aWins > bWins ? playerB : playerA;
                const winnerWins = tie ? 0 : Math.max(aWins, bWins);
                const loserWins = tie ? 0 : Math.min(aWins, bWins);
                return (
                  <div className={`verdict split${tie ? " is-tie" : ""}`}>
                    <div className="verdict-split-grid">
                      <div
                        className={`verdict-side${tie ? "" : winner === playerB ? " right" : ""}`}
                        style={clubStyle((tie ? playerA : winner!).team)}
                      >
                        <ClubCrest
                          className="verdict-crest"
                          code={teamCodeByName.get((tie ? playerA : winner!).team)}
                          team={(tie ? playerA : winner!).team}
                          aria-hidden="true"
                        />
                        <div className="shot">
                          <PlayerPhoto
                            src={(tie ? playerA : winner!).photo ?? undefined}
                            alt={(tie ? playerA : winner!).name}
                            name={(tie ? playerA : winner!).name}
                          />
                        </div>
                        <div className="verdict-side-copy">
                          <span className="win-tag">{tie ? "Even" : "Leads on the numbers"}</span>
                          <h3>{(tie ? playerA : winner!).web_name}</h3>
                          <p>
                            {tie ? aWins : winnerWins} of {METRICS.length} categories
                          </p>
                        </div>
                      </div>
                      <div
                        className={`verdict-side${tie ? "" : winner === playerB ? "" : " right"}${tie ? "" : " is-loser"}`}
                        style={clubStyle((tie ? playerB : loser!).team)}
                      >
                        <ClubCrest
                          className="verdict-crest"
                          code={teamCodeByName.get((tie ? playerB : loser!).team)}
                          team={(tie ? playerB : loser!).team}
                          aria-hidden="true"
                        />
                        <div className="shot">
                          <PlayerPhoto
                            src={(tie ? playerB : loser!).photo ?? undefined}
                            alt={(tie ? playerB : loser!).name}
                            name={(tie ? playerB : loser!).name}
                          />
                        </div>
                        <div className="verdict-side-copy">
                          <span className="win-tag" style={{ background: "rgba(255,255,255,.24)", color: "var(--white)" }}>
                            {tie ? "Even" : "Runner-up"}
                          </span>
                          <h3>{(tie ? playerB : loser!).web_name}</h3>
                          <p>
                            {tie ? bWins : loserWins} of {METRICS.length} categories
                          </p>
                        </div>
                      </div>
                      <div className="verdict-mid">
                        <h3>{tie ? "Split decision" : `${winner!.web_name} leads on the numbers`}</h3>
                        <p>
                          {playerA.web_name} leads {aWins} of {METRICS.length} categories; {playerB.web_name} leads{" "}
                          {bWins}.{" "}
                          {tie
                            ? "Too close to call from season data alone — check form and fixtures below before deciding."
                            : "Full category breakdown is above; the accordion below has the detail."}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
