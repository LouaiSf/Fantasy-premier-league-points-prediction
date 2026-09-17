"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { api } from "@/lib/api";
import { PlayerPhoto } from "@/components/player-photo";
import { ClubCrest } from "@/components/club-crest";
import { clubStyle } from "@/lib/club-colors";
import { money, num, signed } from "@/lib/format";
import type { PlayerRecord, TransferResult } from "@/lib/types";
import { Loading } from "@/components/loading";
import { ModelInfo } from "@/components/model-info";

const OUT_FILTERS = ["ALL", "GK", "DEF", "MID", "FWD", "FLAG"] as const;
const IN_FILTERS = ["ALL", "GK", "DEF", "MID", "FWD"] as const;
const PRICE_FILTERS = [
  { label: "Any price", max: 99 },
  { label: "Under £6.0m", max: 6 },
  { label: "Under £9.0m", max: 9 },
  { label: "Under £12.0m", max: 12 },
] as const;

function isFlagged(player: PlayerRecord) {
  return player.status !== "a" || (player.chance_of_playing_next_round ?? 100) < 100;
}

function DeskRow({
  player,
  selected,
  teamCode,
  onClick,
}: {
  player: PlayerRecord;
  selected: boolean;
  teamCode?: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`prow${selected ? " is-picked" : ""}`}
      data-player-id={player.element}
      onClick={onClick}
      style={clubStyle(player.team)}
    >
      <span className="shot" style={{ position: "relative" }}>
        <PlayerPhoto
          src={player.photo ?? undefined}
          alt={player.name}
          name={player.name}
          loading="lazy"
        />
        {teamCode && (
          <ClubCrest
            className="badge-mini"
            code={teamCode}
            team={player.team}
            shortName={player.team_short}
            aria-hidden="true"
          />
        )}
      </span>
      <span className="prow-id">
        <b>
          {player.web_name || player.name}
          {player.has_prior_history === false && <span className="badge new">New</span>}
        </b>
        <span>
          {player.team_short} · {money(player.value_m)}
          {player.cost_change_event > 0 && (
            <span className="price-tick rising" aria-label="Price rising">▲</span>
          )}
          {player.cost_change_event < 0 && (
            <span className="price-tick falling" aria-label="Price falling">▼</span>
          )}
        </span>
      </span>
      <span className="prow-num">
        <em>
          {num(player.predicted_points ?? player.form)}
          <small>{player.position}</small>
        </em>
      </span>
    </button>
  );
}

export default function TransfersPage() {
  const { snapshot, loading, squadPlayers, squadNames, squadElements, toast } = useApp();
  const [outQuery, setOutQuery] = React.useState("");
  const [inQuery, setInQuery] = React.useState("");
  const [outFilter, setOutFilter] = React.useState<(typeof OUT_FILTERS)[number]>("ALL");
  const [inFilter, setInFilter] = React.useState<(typeof IN_FILTERS)[number]>("ALL");
  const [priceMax, setPriceMax] = React.useState(99);
  const [outId, setOutId] = React.useState<number | null>(null);
  const [inId, setInId] = React.useState<number | null>(null);
  const [free, setFree] = React.useState(1);
  const [bank, setBank] = React.useState(0);
  const [analysis, setAnalysis] = React.useState<TransferResult | null>(null);
  const [analysisError, setAnalysisError] = React.useState<string | null>(null);
  const [analysing, setAnalysing] = React.useState(false);

  if (loading || !snapshot) {
    return (
      <section className="page">
        <div className="shell">
          <Loading label="Loading season data…" />
        </div>
      </section>
    );
  }

  const predictionAvailable = snapshot.prediction_available;
  const teamCodeByName = new Map(snapshot.teams.map((team) => [team.name, team.code]));
  const byElement = new Map(snapshot.players.map((player) => [player.element, player]));
  const outgoing = outId != null ? byElement.get(outId) ?? null : null;
  const incoming = inId != null ? byElement.get(inId) ?? null : null;

  const outRows = squadPlayers.filter((player) => {
    if (outFilter === "FLAG" && !isFlagged(player)) return false;
    if (outFilter !== "ALL" && outFilter !== "FLAG" && player.position !== outFilter) return false;
    return `${player.name} ${player.team}`.toLowerCase().includes(outQuery.trim().toLowerCase());
  });

  const squadIdSet = new Set(squadElements);
  const inRows = snapshot.players.filter((player) => {
    if (squadIdSet.has(player.element)) return false;
    if (outgoing && player.position !== outgoing.position) return false;
    if (inFilter !== "ALL" && player.position !== inFilter) return false;
    if (player.value_m > priceMax) return false;
    return `${player.name} ${player.team}`.toLowerCase().includes(inQuery.trim().toLowerCase());
  });

  function pickOut(player: PlayerRecord) {
    setOutId(player.element);
    if (incoming && incoming.position !== player.position) setInId(null);
    setAnalysis(null);
  }

  function pickIn(player: PlayerRecord) {
    setInId(player.element);
    setAnalysis(null);
  }

  function reset() {
    setOutId(null);
    setInId(null);
    setAnalysis(null);
    setAnalysisError(null);
  }

  const priceDelta = outgoing && incoming ? outgoing.value_m - incoming.value_m : null;
  const pointsDelta =
    outgoing && incoming && predictionAvailable
      ? Number(incoming.predicted_points ?? 0) - Number(outgoing.predicted_points ?? 0)
      : null;
  const hit = free >= 1 ? 0 : (1 - free) * (analysis?.hit_cost ?? 4);
  const runDisabledReason =
    squadPlayers.length !== 15
      ? "Build a full 15-player squad in My Team first."
      : !predictionAvailable
        ? (snapshot.prediction_error ?? "Predictions are unavailable for this snapshot.")
        : null;
  const runDisabled = Boolean(runDisabledReason) || analysing;

  async function runAnalysis() {
    setAnalysing(true);
    setAnalysisError(null);
    try {
      const result = await api.transfers({ squad: squadNames, free, bank, max: 3 });
      setAnalysis(result);
    } catch (err) {
      setAnalysisError((err as Error).message);
    } finally {
      setAnalysing(false);
    }
  }

  const verdict = analysis?.best
    ? analysis.best.transfers === 0
      ? "hold"
      : "go"
    : null;

  return (
    <section className="page studio">
      <div className="shell-wide">
        <div className="section-head">
          <div>
            <p className="eyebrow" style={{ color: "var(--pink)" }}>
              Decision room
            </p>
            <h1>Transfer studio</h1>
          </div>
          <p>
            Stage one move clearly, then ask the existing optimiser how many transfers survive
            the hit.
          </p>
          {predictionAvailable && (
            <ModelInfo model={snapshot.model} timestamp={snapshot.prediction_timestamp} />
          )}
        </div>

        <div className="studio-bar">
          <div className="studio-field">
            <span className="kicker">Free transfers</span>
            <div className="stepper">
              <button
                type="button"
                aria-label="Decrease free transfers"
                disabled={free <= 0}
                onClick={() => setFree((value) => Math.max(0, value - 1))}
              >
                −
              </button>
              <output className="data">{free}</output>
              <button
                type="button"
                aria-label="Increase free transfers"
                disabled={free >= 5}
                onClick={() => setFree((value) => Math.min(5, value + 1))}
              >
                +
              </button>
            </div>
          </div>
          <div className="studio-field">
            <span className="kicker">Bank</span>
            <div className="stepper">
              <button
                type="button"
                aria-label="Decrease bank by £0.1m"
                disabled={bank <= 0}
                onClick={() => setBank((value) => Math.max(0, Math.round((value - 0.1) * 10) / 10))}
              >
                −
              </button>
              <output className="data">{money(bank)}</output>
              <button
                type="button"
                aria-label="Increase bank by £0.1m"
                onClick={() => setBank((value) => Math.round((value + 0.1) * 10) / 10)}
              >
                +
              </button>
            </div>
          </div>
          <span className="spacer" />
          <div className="studio-summary">
            <span className="kicker">Squad size</span>
            <strong className="data">{squadPlayers.length} / 15</strong>
          </div>
        </div>

        <div className="studio-grid">
          <section className="desk out" style={{ "--desk-c": "var(--pink)" } as React.CSSProperties}>
            <div className="desk-head">
              <h2>Player out</h2>
              <span className="count">{outRows.length} squad players</span>
            </div>
            <div className="desk-tools">
              <div className="mini-chips">
                {OUT_FILTERS.map((filter) => (
                  <button
                    key={filter}
                    type="button"
                    className={`mini-chip${outFilter === filter ? " is-active" : ""}`}
                    onClick={() => setOutFilter(filter)}
                  >
                    {filter === "ALL" ? "All" : filter === "FLAG" ? "Flagged" : filter}
                  </button>
                ))}
              </div>
              <label className="search">
                <input
                  type="search"
                  placeholder="Search your squad"
                  value={outQuery}
                  onChange={(event) => setOutQuery(event.target.value)}
                />
              </label>
            </div>
            <div className="desk-list">
              {squadPlayers.length === 0 ? (
                <p className="picker-empty">Build your squad in My Team before staging a transfer.</p>
              ) : (
                outRows.map((player) => (
                  <DeskRow
                    key={player.element}
                    player={player}
                    selected={player.element === outId}
                    teamCode={teamCodeByName.get(player.team)}
                    onClick={() => pickOut(player)}
                  />
                ))
              )}
            </div>
          </section>

          <section className="channel" aria-label="Transfer channel">
            <div className="channel-title">
              <span>Transfer channel</span>
              <span className="kicker">
                {outgoing && incoming ? "Move staged" : outgoing ? "Choose a replacement" : "Awaiting selection"}
              </span>
            </div>
            <div id="slotOut" className={`slot out${outgoing ? " is-filled" : ""}`} style={outgoing ? clubStyle(outgoing.team) : undefined}>
              {outgoing ? (
                <>
                  <div className="slot-id">
                    <span className="kicker">{outgoing.position}</span>
                    <b>{outgoing.web_name}</b>
                    <span>{money(outgoing.value_m)}</span>
                  </div>
                  <div className="slot-photo">
                    <PlayerPhoto
                      className="shot-img"
                      src={outgoing.photo ?? undefined}
                      alt={outgoing.name}
                      name={outgoing.name}
                    />
                    <ClubCrest
                      className="badge-mini"
                      code={teamCodeByName.get(outgoing.team)}
                      team={outgoing.team}
                      aria-hidden="true"
                    />
                  </div>
                </>
              ) : (
                <div className="slot-empty">
                  <b>Select a player to sell</b>
                  <span>Left column</span>
                </div>
              )}
              <span className="slot-tag out">Out</span>
            </div>
            <div className="lane" aria-hidden="true">
              <span className="lane-chev">↓</span>
            </div>
            <div id="slotIn" className={`slot in${incoming ? " is-filled" : ""}`} style={incoming ? clubStyle(incoming.team) : undefined}>
              {incoming ? (
                <>
                  <div className="slot-id">
                    <span className="kicker">{incoming.position}</span>
                    <b>{incoming.web_name}</b>
                    <span>{money(incoming.value_m)}</span>
                  </div>
                  <div className="slot-photo">
                    <PlayerPhoto
                      className="shot-img"
                      src={incoming.photo ?? undefined}
                      alt={incoming.name}
                      name={incoming.name}
                    />
                    <ClubCrest
                      className="badge-mini"
                      code={teamCodeByName.get(incoming.team)}
                      team={incoming.team}
                      aria-hidden="true"
                    />
                  </div>
                </>
              ) : (
                <div className="slot-empty">
                  <b>Select a replacement</b>
                  <span>Right column</span>
                </div>
              )}
              <span className="slot-tag in">In</span>
            </div>
            <div className={`channel-read${outgoing && incoming ? " has-move" : ""}`} aria-live="polite">
              <span className="kicker">Decision read</span>
              <h3>
                {outgoing && incoming
                  ? `${outgoing.web_name} to ${incoming.web_name}`
                  : outgoing
                    ? `Find a ${outgoing.position} replacement`
                    : "Choose an outgoing player"}
              </h3>
              <p>
                {outgoing && incoming
                  ? `${outgoing.web_name} (${money(outgoing.value_m)}) makes way for ${incoming.web_name} (${money(incoming.value_m)}). Run the full analysis to see how this ranks against every transfer count.`
                  : outgoing
                    ? `${inRows.length} ${outgoing.position} options match the current filters.`
                    : "Pick a player to sell from the desk on the left to start staging a move."}
              </p>
              <div className="decision-bugs">
                <div className="bug">
                  <span>Bank after</span>
                  <strong>{priceDelta != null ? money(bank + priceDelta) : money(bank)}</strong>
                </div>
                <div className="bug">
                  <span>Points delta</span>
                  <strong>{pointsDelta != null ? signed(pointsDelta) : "--"}</strong>
                </div>
                <div className="bug">
                  <span>Hit if played now</span>
                  <strong>{outgoing && incoming ? `${hit} pts` : "--"}</strong>
                </div>
              </div>
            </div>
            <div className="channel-foot">
              <button className="btn secondary sm" type="button" onClick={reset}>
                Reset
              </button>
              <button
                className="btn sm"
                type="button"
                disabled={runDisabled}
                title={runDisabledReason ?? undefined}
                onClick={runAnalysis}
              >
                {analysing ? "Running…" : "Run full analysis"}
              </button>
            </div>
            {runDisabledReason && !analysing && (
              <p className="run-reason">
                {runDisabledReason}
              </p>
            )}
            {analysing && (
              <div className="analysis-status" role="status">
                <span className="spinner" aria-hidden="true" />
                Running the optimiser across every transfer count…
              </div>
            )}
            {!analysing && analysisError && (
              <div className="analysis-status is-error" role="alert">
                {analysisError}
              </div>
            )}
            {!analysing && !analysisError && analysis && (
              <div className="analysis-status" role="status">
                {analysis.best
                  ? `Analysis complete: ${analysis.best.transfers} transfer${analysis.best.transfers === 1 ? "" : "s"} lead the model.`
                  : "Analysis complete: no legal squad was found for any transfer count."}
              </div>
            )}
          </section>

          <section className="desk in" style={{ "--desk-c": "var(--lime)" } as React.CSSProperties}>
            <div className="desk-head">
              <h2>Player in</h2>
              <span className="count">{outgoing ? `${inRows.length} ${outgoing.position}` : "Market"}</span>
            </div>
            <div className="desk-tools">
              <label className="search">
                <input
                  type="search"
                  placeholder="Search players or clubs"
                  value={inQuery}
                  onChange={(event) => setInQuery(event.target.value)}
                />
              </label>
              <div className="mini-chips">
                {IN_FILTERS.map((filter) => (
                  <button
                    key={filter}
                    type="button"
                    className={`mini-chip${inFilter === filter ? " is-active" : ""}`}
                    onClick={() => setInFilter(filter)}
                  >
                    {filter === "ALL" ? "All" : filter}
                  </button>
                ))}
              </div>
              <div className="mini-chips">
                {PRICE_FILTERS.map((filter) => (
                  <button
                    key={filter.label}
                    type="button"
                    className={`mini-chip${priceMax === filter.max ? " is-active" : ""}`}
                    onClick={() => setPriceMax(filter.max)}
                  >
                    {filter.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="desk-list">
              {inRows.slice(0, 200).map((player) => (
                <DeskRow
                  key={player.element}
                  player={player}
                  selected={player.element === inId}
                  teamCode={teamCodeByName.get(player.team)}
                  onClick={() => pickIn(player)}
                />
              ))}
            </div>
          </section>
        </div>

        {analysis && (
          <section className="impact" aria-live="polite">
            <div className="impact-head">
              <h3>Transfer impact</h3>
              <span className={`verdict-pill${verdict === "hold" ? " hold" : ""}`}>
                {analysis.best
                  ? analysis.best.transfers === 0
                    ? "Hold this week"
                    : `${analysis.best.transfers} transfer${analysis.best.transfers === 1 ? "" : "s"} lead the model`
                  : "No legal squad found"}
              </span>
            </div>
            <div className="impact-grid">
              {analysis.rows.map((row) => (
                <div className="impact-cell" key={row.transfers}>
                  <p className="kicker">{row.transfers} transfer{row.transfers === 1 ? "" : "s"}</p>
                  <span className={`big ${row.gain >= 0 ? "pos" : "neg"}`}>{signed(row.gain)}</span>
                  <p>
                    {num(row.gross)} gross, {row.hit ? `−${row.hit}` : "0"} hit
                    {row.out.length ? ` · ${row.out.join(", ")} → ${row.in.join(", ")}` : ""}
                  </p>
                </div>
              ))}
              {analysis.failures.map((failure) => (
                <div className="impact-cell" key={`fail-${failure.transfers}`}>
                  <p className="kicker">{failure.transfers} transfers</p>
                  <span className="big neg">N/A</span>
                  <p>{failure.status}</p>
                </div>
              ))}
            </div>
            <div className="impact-foot">
              <p>
                {analysis.best
                  ? `Net projected gain of ${num(analysis.best.gain)} points after transfer costs, budget £${analysis.budget}m.`
                  : "No legal squad was found within the budget for any transfer count."}
              </p>
              <button className="btn secondary" type="button" onClick={() => toast("Hold recorded for this session.")}>
                Hold this week
              </button>
            </div>
          </section>
        )}
      </div>
    </section>
  );
}
