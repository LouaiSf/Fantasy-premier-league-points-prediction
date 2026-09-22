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

// FPL states the figure twice: in two structured fields, one per round, and
// in the note itself. They disagree often enough to matter.
//
// The note wins where it gives a number. It is FPL's own editorial line, it
// is the text the reader is looking at, and showing "0% fit" beside "50%
// chance of playing" is indefensible whichever number is right. Four players
// currently read that way: marked doubtful, this-round set to 0, note saying
// 50 or 75.
//
// Failing that, this round before next. Reading next_round alone showed a
// player who is 25% for Saturday as fully fit.
const STATED_CHANCE = /(\d+)% chance of playing/;

function chanceFor(player: PlayerRecord): number | null {
  const stated = player.news?.match(STATED_CHANCE);
  if (stated) return Number(stated[1]);
  return player.chance_of_playing_this_round ?? player.chance_of_playing_next_round ?? null;
}

function hasNote(player: PlayerRecord): boolean {
  return Boolean(player.news) || player.status !== "a" || (chanceFor(player) ?? 100) < 100;
}

function noteFor(player: PlayerRecord): string {
  if (player.news) return player.news;
  const chance = chanceFor(player);
  if (chance != null && chance < 100) {
    return `FPL lists a ${chance}% chance of playing this round.`;
  }
  return `Current availability status: ${player.status}.`;
}

// What a note is worth reading first is not how low the chance is. A player
// who has left the league is a certainty, not a risk, and there are 105 of
// them against 24 real doubts -- sorted on chance alone they took the lead
// story and the nine behind it. Selectable-but-doubtful leads, then out,
// then gone.
function tier(player: PlayerRecord): number {
  if (player.status === "u" || player.status === "n") return 2;
  if (player.status === "i" || player.status === "s") return 1;
  return 0;
}

function severity(player: PlayerRecord): number {
  return chanceFor(player) ?? (player.status === "a" ? 100 : 50);
}

// Within a tier, the note that matters is the one on a player worth owning.
function byUrgency(a: PlayerRecord, b: PlayerRecord): number {
  if (tier(a) !== tier(b)) return tier(a) - tier(b);
  const points = (b.predicted_points ?? -1) - (a.predicted_points ?? -1);
  if (points !== 0) return points;
  return severity(a) - severity(b);
}

// Gameweek, not a timestamp: FPL publishes news_added and olbauday carries
// the column, but it is empty for every row upstream. The gameweek a note
// first appeared is recovered from the per-gameweek history instead.
function noteAge(player: PlayerRecord, newest: number | null): string | null {
  if (player.news_since_gw == null) return null;
  if (newest != null && player.news_since_gw >= newest) return "New this week";
  return `Since GW${player.news_since_gw}`;
}

function statusLabel(player: PlayerRecord): string {
  if (player.status === "i") return "Injured";
  if (player.status === "s") return "Suspended";
  if (player.status === "u") return "Unavailable";
  if (player.status === "n") return "Not in squad";
  if (player.status === "d" || (chanceFor(player) ?? 100) < 100) return "Doubtful";
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
  const chance = chanceFor(player);
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
  const allNotes = snapshot.players.filter(hasNote).sort(byUrgency);
  const newestNoteGw = allNotes.reduce<number | null>(
    (seen, player) => (player.news_since_gw != null && (seen == null || player.news_since_gw > seen)
      ? player.news_since_gw
      : seen),
    null,
  );
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
        return player.status !== "a" || (chanceFor(player) ?? 100) < 100;
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
            Every availability note in the local FPL snapshot, ordered by what changes your
            team first: players still selectable but in doubt, then those ruled out, then
            those who have left the league.
          </p>
        </div>

        {filtered.length > 0 && (
          <div className="ticker-strip" aria-label="Availability headlines">
            <span className="tag">Notes</span>
            <div
              className="ticker-track"
              aria-hidden="true"
              style={{ "--ticker-duration": `${Math.max(60, filtered.length * 4)}s` } as React.CSSProperties}
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
          <p className="kicker muted">
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
                <span className="sev" data-status={lead.status}>{statusLabel(lead)}</span>
                <ChanceBadge player={lead} />
                <span className="club">{lead.team}</span>
              </div>
              <h2>{lead.web_name}</h2>
              <p className="lead-note">{noteFor(lead)}</p>
              <p className="wire-fresh">
                {noteAge(lead, newestNoteGw) ?? freshness} · Official FPL player status,
                not third-party reporting
              </p>
              <div className="lead-actions">
                <button className="btn sm secondary" type="button" onClick={() => openProfile(lead)}>
                  View player
                </button>
              </div>
            </div>
            <div className="lead-shot">
              <PlayerPhoto src={lead.photo ?? undefined} alt={lead.name} name={lead.name} variant="hero" />
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
          <div className="wire-layout wire-layout--single">
            <div className="wire-col">
              <h3 className="col-title">
                League wire<small>
                  {rest.length} of {allRest.length} stories
                </small>
              </h3>
              {rest.map((player, idx) => (
                <button
                  key={player.element}
                  type="button"
                  className="wire-item"
                  data-pri={player.status !== "a" ? "high" : "med"}
                  onClick={() => openProfile(player)}
                  style={{ "--i": idx } as React.CSSProperties}
                >
                  <span className="wire-shot" style={clubStyle(player.team)}>
                    <PlayerPhoto src={player.photo ?? undefined} alt={player.name} name={player.name} variant="avatar" loading="lazy" />
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
                      <span className="tagline-status" data-status={player.status}>{statusLabel(player)}</span>
                      <ChanceBadge player={player} />
                      <span>{player.team}</span>
                      <span>{player.position}</span>
                      {squadIdSet.has(player.element) && <span className="owned">Owned</span>}
                    </div>
                  </span>
                  <time>{noteAge(player, newestNoteGw) ?? freshness}</time>
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
                    <PlayerPhoto src={player.photo ?? undefined} alt={player.name} name={player.name} variant="card" loading="lazy" />
                  </div>
                </div>
                <div className="news-card-copy">
                  <div className="news-card-meta">
                    <span className="news-status" data-status={player.status}>{statusLabel(player)}</span>
                    <span>{player.team}</span>
                    <span>{player.position}</span>
                  </div>
                  <h3>{player.web_name}</h3>
                  <p>{noteFor(player)}</p>
                  <span className="wire-fresh">{noteAge(player, newestNoteGw) ?? freshness}</span>
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
