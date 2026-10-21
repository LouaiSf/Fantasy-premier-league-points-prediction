"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { ClubCrest } from "@/components/club-crest";
import { clubStyle } from "@/lib/club-colors";
import { num } from "@/lib/format";
import type { PlayerRecord } from "@/lib/types";
import { Skeleton } from "@/components/skeleton";
import { Face, GateSign, PlateFact, Segmented, VerdictPlate } from "@/components/signage";
import { Icon } from "@/components/icons";

type Filter = "all" | "squad" | "injury" | "suspension" | "doubt";
type View = "desk" | "cards";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
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
    return `${chance}% chance of playing this week.`;
  }
  return "Availability unclear.";
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
  return `Since gameweek ${player.news_since_gw}`;
}

function statusLabel(player: PlayerRecord): string {
  if (player.status === "i") return "Injured";
  if (player.status === "s") return "Suspended";
  if (player.status === "u") return "Unavailable";
  if (player.status === "n") return "Not in squad";
  if (player.status === "d" || (chanceFor(player) ?? 100) < 100) return "Doubtful";
  return "Update";
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
          <Skeleton variant="row" count={8} />
        </div>
      </section>
    );
  }

  // Ownership is an identity question, so it is asked by element id. The two
  // name spellings in this app do not line up and never matched here.
  const squadIdSet = new Set(squadElements);
  const teamCodeByName = new Map(snapshot.teams.map((team) => [team.name, team.code]));
  const clubOptions = snapshot.teams.map((team) => team.name);
  const freshness = snapshot.gameweek ? `Gameweek ${snapshot.gameweek}` : "This season";
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

  const squadNotes = allNotes.filter((player) => squadIdSet.has(player.element)).length;
  const lede = squadElements.length
    ? squadNotes
      ? `${squadNotes} of your players ${squadNotes === 1 ? "has" : "have"} a note this week. The ones that could still play come first.`
      : "None of your players has a note this week. Here's the rest of the league, the ones that could still play first."
    : undefined;

  return (
    <section className="page news-page" aria-label="News">
      <GateSign lede={lede} />

      {lead ? (
        <VerdictPlate
          tone={tier(lead) === 0 ? "spotlight" : "matchday"}
          label="Top story"
          player={lead}
          title={
            <>
              {lead.web_name}: {statusLabel(lead).toLowerCase()}.
            </>
          }
          body={noteFor(lead)}
          facts={
            <>
              <PlateFact label="Club">{lead.team_short}</PlateFact>
              <PlateFact label="Owned by">{num(lead.selected_by)}%</PlateFact>
              <PlateFact label="Your squad">{squadIdSet.has(lead.element) ? "He's in it" : "Not in it"}</PlateFact>
            </>
          }
          actions={
            <button className="btn btn--go" type="button" onClick={() => openProfile(lead)}>
              See his profile <Icon name="arrow-right" size={18} />
            </button>
          }
        />
      ) : (
        <div className="empty-state">
          <h2 className="empty-title">Nothing matches</h2>
          <p className="empty-message">No notes fit these filters. Try All, or clear the search.</p>
        </div>
      )}

      <div className="toolbar">
        <Segmented label="Show" value={filter} onChange={setFilter} options={FILTERS.map((item) => ({ value: item.key, label: item.label }))} />
        <label className="searchbox">
          <span className="sr-only">Search player or club</span>
          <Icon name="search" size={18} />
          <input className="input input--sm" type="search" placeholder="Player or club" value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label>
          <span className="sr-only">Club</span>
          <select className="select select--sm" value={club} onChange={(event) => setClub(event.target.value)}>
            <option value="ALL">All clubs</option>
            {clubOptions.map((team) => (
              <option key={team} value={team}>
                {team}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Position</span>
          <select className="select select--sm" value={position} onChange={(event) => setPosition(event.target.value)}>
            <option value="ALL">All positions</option>
            {(["GK", "DEF", "MID", "FWD"] as const).map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <span className="toolbar-spacer" />
        <Segmented
          label="Layout"
          value={view}
          onChange={setView}
          options={[
            { value: "desk", label: "List" },
            { value: "cards", label: "Cards" },
          ]}
        />
      </div>

      {rest.length > 0 && view === "desk" && (
        <ul className="panel wire stagger">
          {rest.map((player, idx) => (
            <li key={player.element} style={{ "--i": idx } as React.CSSProperties}>
              <button type="button" className="prow wire-row" onClick={() => openProfile(player)}>
                <Face player={player} />
                <span className="prow-name">
                  <b>
                    {player.web_name}
                    {squadIdSet.has(player.element) && <span className="badge badge--dark">Yours</span>}
                  </b>
                  <span className="why">{noteFor(player)}</span>
                </span>
                <span className="wire-tags">
                  <span className={`badge ${tier(player) === 0 ? "badge--warn" : "badge--alert"}`}>{statusLabel(player)}</span>
                </span>
                <span className="wire-meta">
                  <span>{player.team_short} · {player.position}</span>
                  <small>{noteAge(player, newestNoteGw) ?? freshness}</small>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {rest.length > 0 && view === "cards" && (
        <ul className="news-cards stagger">
          {rest.map((player, index) => (
            <li key={player.element} style={{ "--i": index } as React.CSSProperties}>
              <button type="button" className="news-card" onClick={() => openProfile(player)}>
                <span className="news-card-art" style={clubStyle(player.team)}>
                  <ClubCrest className="news-card-crest" code={teamCodeByName.get(player.team)} team={player.team} aria-hidden="true" />
                  <PlayerPhoto src={player.photo ?? undefined} alt="" name={player.name} variant="card" loading="lazy" />
                  <span className={`badge ${tier(player) === 0 ? "badge--warn" : "badge--alert"} news-card-status`}>{statusLabel(player)}</span>
                </span>
                <span className="news-card-copy">
                  <b>{player.web_name}</b>
                  <span className="note">
                    {player.team} · {player.position}
                    {squadIdSet.has(player.element) ? " · yours" : ""}
                  </span>
                  <span className="news-card-note">{noteFor(player)}</span>
                  <small className="note">{noteAge(player, newestNoteGw) ?? freshness}</small>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {allRest.length > 24 && (
        <button type="button" className="btn btn--line wire-more" onClick={() => setShowAll((value) => !value)}>
          {showAll ? "Show fewer" : `Show all ${allRest.length + 1} notes`}
        </button>
      )}
    </section>
  );
}
