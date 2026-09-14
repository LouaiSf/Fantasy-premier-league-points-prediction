"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { clubStyle } from "@/lib/club-colors";
import { crestUrl, num } from "@/lib/format";
import type { PlayerRecord } from "@/lib/types";

type Filter = "all" | "squad" | "injury" | "suspension" | "doubt";
type View = "desk" | "cards";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All notes" },
  { key: "squad", label: "My squad" },
  { key: "injury", label: "Injuries" },
  { key: "suspension", label: "Suspensions" },
  { key: "doubt", label: "Doubtful" },
];

function hasNote(player: PlayerRecord): boolean {
  return Boolean(player.news) || player.status !== "a" || (player.chance_of_playing_next_round ?? 100) < 100;
}

function noteFor(player: PlayerRecord): string {
  if (player.news) return player.news;
  if ((player.chance_of_playing_next_round ?? 100) < 100) {
    return `FPL lists a ${player.chance_of_playing_next_round}% chance of playing next round.`;
  }
  return `Current availability status: ${player.status}.`;
}

function severity(player: PlayerRecord): number {
  return player.chance_of_playing_next_round ?? (player.status === "a" ? 100 : 50);
}

function statusLabel(player: PlayerRecord): string {
  if (player.status === "i") return "Injured";
  if (player.status === "s") return "Suspended";
  if (player.status === "u") return "Unavailable";
  if ((player.chance_of_playing_next_round ?? 100) < 100) return "Doubtful";
  return "Availability note";
}

export default function NewsPage() {
  const { snapshot, loading, squadNames, openProfile } = useApp();
  const [filter, setFilter] = React.useState<Filter>("all");
  const [view, setView] = React.useState<View>("desk");
  const [query, setQuery] = React.useState("");
  const [club, setClub] = React.useState("ALL");
  const [position, setPosition] = React.useState("ALL");

  if (loading || !snapshot) {
    return (
      <section className="page">
        <div className="shell" style={{ paddingBlock: "var(--space-16)" }}>
          <p>Loading the local season data…</p>
        </div>
      </section>
    );
  }

  const squadNameSet = new Set(squadNames);
  const teamCodeByName = new Map(snapshot.teams.map((team) => [team.name, team.code]));
  const clubOptions = snapshot.teams.map((team) => team.name);
  const freshness = snapshot.gameweek ? `Local snapshot · GW${snapshot.gameweek}` : "Local snapshot";
  const allNotes = snapshot.players.filter(hasNote).sort((a, b) => severity(a) - severity(b));
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = allNotes.filter((player) => {
    if (normalizedQuery && !`${player.name} ${player.web_name} ${player.team}`.toLowerCase().includes(normalizedQuery)) {
      return false;
    }
    if (club !== "ALL" && player.team !== club) return false;
    if (position !== "ALL" && player.position !== position) return false;
    switch (filter) {
      case "squad":
        return squadNameSet.has(player.name);
      case "injury":
        return player.status === "i";
      case "suspension":
        return player.status === "s";
      case "doubt":
        return player.status !== "a" || (player.chance_of_playing_next_round ?? 100) < 100;
      default:
        return true;
    }
  });

  const lead = filtered[0] ?? null;
  const rest = filtered.slice(1, 25);

  return (
    <section className="page news-page paper-scope">
      <div className="shell">
        <div className="section-head on-paper">
          <div>
            <p className="eyebrow" style={{ color: "var(--pink)" }}>
              Team news // local desk
            </p>
            <h1>Matchday wire</h1>
          </div>
          <p>
            Every availability note carried in the local FPL player snapshot, ordered by what
            changes your team first.
          </p>
        </div>

        {filtered.length > 0 && (
          <div className="ticker-strip" aria-label="Availability headlines">
            <span className="tag">Notes</span>
            <div
              className="ticker-track"
              aria-hidden="true"
              style={{ "--ticker-duration": `${Math.max(72, filtered.length * 0.72)}s` } as React.CSSProperties}
            >
              {[...filtered, ...filtered].map((player, index) => (
                <span key={`${player.element}-${index}`}>
                  <b>{player.web_name}</b> — {noteFor(player)}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="news-toolbar">
          <div className="news-control-stack">
            <div className="filter-row" role="group" aria-label="News filters">
              {FILTERS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`chip on-paper${filter === item.key ? " is-active" : ""}`}
                  onClick={() => setFilter(item.key)}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="news-filter-tools">
              <label className="search">
                <span className="sr-only">Search player or club</span>
                <input
                  type="search"
                  placeholder="Search player or club"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
              <label className="news-select-wrap">
                <span className="sr-only">Filter by club</span>
                <select className="news-select" value={club} onChange={(event) => setClub(event.target.value)}>
                  <option value="ALL">All clubs</option>
                  {clubOptions.map((team) => (
                    <option key={team} value={team}>{team}</option>
                  ))}
                </select>
              </label>
              <label className="news-select-wrap">
                <span className="sr-only">Filter by position</span>
                <select className="news-select" value={position} onChange={(event) => setPosition(event.target.value)}>
                  <option value="ALL">All positions</option>
                  {(["GK", "DEF", "MID", "FWD"] as const).map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="news-view-switch" role="tablist" aria-label="News reading mode">
              <button
                type="button"
                role="tab"
                aria-selected={view === "desk"}
                className="news-view-tab"
                onClick={() => setView("desk")}
              >
                Desk
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={view === "cards"}
                className="news-view-tab"
                onClick={() => setView("cards")}
              >
                Cards
              </button>
            </div>
          </div>
          <p className="kicker" style={{ color: "var(--muted-ink)" }}>
            {filtered.length} note{filtered.length === 1 ? "" : "s"} in this filter
          </p>
        </div>

        {!lead && <p className="wire-empty">No notes match this filter in the local snapshot.</p>}

        {lead && (
          <article className="lead-story" style={clubStyle(lead.team)}>
            <span className="lead-hazard" aria-hidden="true" />
            <div className="lead-mane" aria-hidden="true" />
            {teamCodeByName.get(lead.team) && (
              <img className="lead-crest" src={crestUrl(teamCodeByName.get(lead.team)!)} alt="" aria-hidden="true" />
            )}
            <div className="lead-copy">
              <div className="lead-badges">
                <span className="sev">{statusLabel(lead)}</span>
                {(lead.chance_of_playing_next_round ?? 100) < 100 && (
                  <span className="live">{lead.chance_of_playing_next_round}% chance of playing</span>
                )}
                <span className="club">{lead.team}</span>
              </div>
              <h2>{lead.web_name}</h2>
              <p style={{ maxWidth: "40ch", color: "#f0e4f2", fontSize: 15 }}>{noteFor(lead)}</p>
              <p className="wire-fresh" style={{ color: "rgba(255,255,255,.7)" }}>
                {freshness} · Official FPL player status, not third-party reporting
              </p>
              <div className="lead-actions">
                <button className="btn sm secondary" type="button" onClick={() => openProfile(lead)}>
                  View player
                </button>
              </div>
            </div>
            {lead.photo && (
              <div className="lead-shot">
                <PlayerPhoto src={lead.photo} alt="" />
              </div>
            )}
            <div className="lead-panel">
              <h3>Squad relevance</h3>
              <ul className="lead-impact">
                <li>
                  <i>{num(lead.selected_by)}%</i>
                  <span>Owned by managers in the local snapshot</span>
                </li>
                <li>
                  <i className={squadNameSet.has(lead.name) ? "" : "neg"}>
                    {squadNameSet.has(lead.name) ? "In squad" : "Not owned"}
                  </i>
                  <span>Relevance to your current squad</span>
                </li>
                <li>
                  <i>{lead.position}</i>
                  <span>{lead.team}</span>
                </li>
              </ul>
            </div>
          </article>
        )}

        {view === "desk" && rest.length > 0 && (
          <div className="wire-layout" style={{ gridTemplateColumns: "1fr" }}>
            <div className="wire-col">
              <h3 className="col-title">
                League wire<small>{rest.length} stories</small>
              </h3>
              {rest.map((player) => (
                <button
                  key={player.element}
                  type="button"
                  className="wire-item"
                  data-pri={player.status !== "a" ? "high" : "med"}
                  onClick={() => openProfile(player)}
                  style={{ width: "100%", background: "transparent", font: "inherit", textAlign: "left", cursor: "pointer" }}
                >
                  <span className="wire-shot" style={clubStyle(player.team)}>
                    {player.photo && <PlayerPhoto src={player.photo} alt="" loading="lazy" />}
                    {teamCodeByName.get(player.team) && (
                      <img className="wire-badge" src={crestUrl(teamCodeByName.get(player.team)!)} alt="" aria-hidden="true" />
                    )}
                  </span>
                  <span>
                    <h4>{player.web_name}</h4>
                    <p>{noteFor(player)}</p>
                    <div className="tagline">
                      <span>{statusLabel(player)}</span>
                      <span>{player.team}</span>
                      <span>{player.position}</span>
                      {squadNameSet.has(player.name) && <span className="owned">Owned</span>}
                    </div>
                  </span>
                  <time>{freshness}</time>
                </button>
              ))}
            </div>
          </div>
        )}

        {view === "cards" && rest.length > 0 && (
          <div className="news-cards">
            {rest.map((player) => (
              <button
                key={player.element}
                type="button"
                className="news-card"
                onClick={() => openProfile(player)}
              >
                <div className="news-card-art" style={clubStyle(player.team)}>
                  {teamCodeByName.get(player.team) && (
                    <img className="crest" src={crestUrl(teamCodeByName.get(player.team)!)} alt="" aria-hidden="true" />
                  )}
                  {player.photo && (
                    <div className="shot">
                      <PlayerPhoto src={player.photo} alt="" loading="lazy" />
                    </div>
                  )}
                </div>
                <div className="news-card-copy">
                  <div className="news-card-meta">
                    <span>{statusLabel(player)}</span>
                    <span>{player.team}</span>
                    <span>{player.position}</span>
                  </div>
                  <h3>{player.web_name}</h3>
                  <p>{noteFor(player)}</p>
                  <span className="wire-fresh">{freshness}</span>
                  {squadNameSet.has(player.name) && <span className="news-card-tag owned">Owned</span>}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
