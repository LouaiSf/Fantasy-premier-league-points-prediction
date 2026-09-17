"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { ClubCrest } from "@/components/club-crest";
import { clubStyle } from "@/lib/club-colors";
import { num } from "@/lib/format";
import type { PlayerRecord } from "@/lib/types";
import { Loading } from "@/components/loading";

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
  if (player.status === "n") return "Not in squad";
  if (player.status === "d" || (player.chance_of_playing_next_round ?? 100) < 100) return "Doubtful";
  return "Availability note";
}

// FPL publishes a chance of playing as 25, 50 or 75. Red through orange to
// yellow, so the badge reads as a risk level at a glance rather than as a
// number the reader has to interpret.
function chanceTone(chance: number): "bad" | "mid" | "ok" {
  if (chance <= 25) return "bad";
  if (chance <= 50) return "mid";
  return "ok";
}

function ChanceBadge({ player }: { player: PlayerRecord }) {
  const chance = player.chance_of_playing_next_round;
  // Only the partial cases. 100 is not news, and 0 already reads as Injured or
  // Unavailable beside it -- a "0% fit" badge on a player who has left the club
  // is noise, not a risk level.
  if (chance == null || chance <= 0 || chance >= 100) return null;
  return <span className={`chance-badge is-${chanceTone(chance)}`}>{chance}% fit</span>;
}

export default function NewsPage() {
  const { snapshot, loading, squadElements, openProfile } = useApp();
  const [filter, setFilter] = React.useState<Filter>("all");
  const [view, setView] = React.useState<View>("desk");
  const [query, setQuery] = React.useState("");
  const [club, setClub] = React.useState("ALL");
  const [position, setPosition] = React.useState("ALL");
  const [showAll, setShowAll] = React.useState(false);

  if (loading || !snapshot) {
    return (
      <section className="page">
        <div className="shell">
          <Loading label="Loading season data…" />
        </div>
      </section>
    );
  }

  // Ownership is an identity question, so it is asked by element id. The two
  // name spellings in this app do not line up and never matched here.
  const squadIdSet = new Set(squadElements);
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
        return squadIdSet.has(player.element);
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
  // A busy week produces far more than two dozen notes, and the cap silently
  // hid the rest; the count and the toggle make the limit visible instead.
  const allRest = filtered.slice(1);
  const rest = showAll ? allRest : allRest.slice(0, 24);

  return (
    <section className="page news-page paper-scope" aria-label="Team news">
      <div className="shell">
        <div className="section-head on-paper">
          <div>
            <p className="eyebrow alert">
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
            <ClubCrest
              className="lead-crest"
              code={teamCodeByName.get(lead.team)}
              team={lead.team}
              aria-hidden="true"
            />
            <div className="lead-copy">
              <div className="lead-badges">
                <span className="sev">{statusLabel(lead)}</span>
                <ChanceBadge player={lead} />
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
            <div className="lead-shot">
              <PlayerPhoto src={lead.photo ?? undefined} alt={lead.name} name={lead.name} />
            </div>
            <div className="lead-panel">
              <h3>Squad relevance</h3>
              <ul className="lead-impact">
                <li>
                  <i>{num(lead.selected_by)}%</i>
                  <span>Owned by managers in the local snapshot</span>
                </li>
                <li>
                  <i className={squadIdSet.has(lead.element) ? "" : "neg"}>
                    {squadIdSet.has(lead.element) ? "In squad" : "Not owned"}
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
                League wire<small>
                  {rest.length} of {allRest.length} stories
                </small>
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
                    <PlayerPhoto src={player.photo ?? undefined} alt={player.name} name={player.name} loading="lazy" />
                    <ClubCrest
                      className="wire-badge"
                      code={teamCodeByName.get(player.team)}
                      team={player.team}
                      aria-hidden="true"
                    />
                  </span>
                  <span>
                    <h4>{player.web_name}</h4>
                    <p>{noteFor(player)}</p>
                    <div className="tagline">
                      <span>{statusLabel(player)}</span>
                      <ChanceBadge player={player} />
                      <span>{player.team}</span>
                      <span>{player.position}</span>
                      {squadIdSet.has(player.element) && <span className="owned">Owned</span>}
                    </div>
                  </span>
                  <time>{freshness}</time>
                </button>
              ))}
              {allRest.length > rest.length && (
                <button
                  type="button"
                  className="btn sm secondary wire-more"
                  onClick={() => setShowAll(true)}
                >
                  Show all {allRest.length} stories
                </button>
              )}
              {showAll && allRest.length > 24 && (
                <button
                  type="button"
                  className="btn sm secondary wire-more"
                  onClick={() => setShowAll(false)}
                >
                  Show fewer
                </button>
              )}
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
                  <ClubCrest
                    className="crest"
                    code={teamCodeByName.get(player.team)}
                    team={player.team}
                    aria-hidden="true"
                  />
                  <div className="shot">
                    <PlayerPhoto src={player.photo ?? undefined} alt={player.name} name={player.name} loading="lazy" />
                  </div>
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
                  {squadIdSet.has(player.element) && <span className="news-card-tag owned">Owned</span>}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
