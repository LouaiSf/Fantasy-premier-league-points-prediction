"use client";

import * as React from "react";
import { api, ApiRequestError } from "@/lib/api";
import type { LeagueStandingsEntry, ManagerLineup, ManagerSearchCandidate, PlatformSnapshot } from "@/lib/types";
import { ManagerLineupPreview } from "@/components/team/manager-lineup-preview";

const NAME_SEARCH_UNAVAILABLE = "Name search is not configured; enter a numeric FPL entry ID.";

function describeSearchError(err: unknown, fallback: string): string {
  if (err instanceof ApiRequestError && err.code === "search_not_configured") {
    return NAME_SEARCH_UNAVAILABLE;
  }
  return err instanceof Error ? err.message : fallback;
}

function candidateFromLeagueEntry(entry: LeagueStandingsEntry): ManagerSearchCandidate {
  return {
    entry_id: entry.entry_id,
    manager_name: entry.manager_name,
    team_name: entry.team_name,
    overall_rank: entry.rank,
    total_points: entry.total_points,
  };
}

// There's no FPL endpoint to search all managers by name -- that would mean
// crawling every one of the ~11M entry IDs. A classic league's standings
// (public, no auth) are the smallest surface that actually supports name
// search: enumerate a league the manager already knows the ID of -- their
// own mini-league, or a big public one like "Overall" (314) -- and filter
// it client-side.
function LeagueSearchPanel({
  onSelect,
}: {
  readonly onSelect: (candidate: ManagerSearchCandidate) => void;
}) {
  const [leagueIdInput, setLeagueIdInput] = React.useState("");
  const [leagueId, setLeagueId] = React.useState<number | null>(null);
  const [leagueName, setLeagueName] = React.useState<string | null>(null);
  const [entries, setEntries] = React.useState<LeagueStandingsEntry[]>([]);
  const [page, setPage] = React.useState(1);
  const [hasNext, setHasNext] = React.useState(false);
  const [nameFilter, setNameFilter] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function loadPage(id: number, targetPage: number, append: boolean) {
    setLoading(true);
    setError(null);
    try {
      const res = await api.leagueStandings(id, targetPage);
      setLeagueName(res.league_name);
      setEntries((prev) => (append ? [...prev, ...res.entries] : res.entries));
      setPage(res.page);
      setHasNext(res.has_next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "League lookup failed.");
      if (!append) {
        setEntries([]);
        setLeagueName(null);
      }
    } finally {
      setLoading(false);
    }
  }

  function submitLeague(event: React.FormEvent) {
    event.preventDefault();
    const parsed = Number(leagueIdInput.trim());
    if (!Number.isInteger(parsed) || parsed <= 0) {
      setError("Enter a numeric league ID.");
      return;
    }
    setLeagueId(parsed);
    void loadPage(parsed, 1, false);
  }

  const filtered = nameFilter.trim()
    ? entries.filter((entry) =>
        `${entry.manager_name} ${entry.team_name}`.toLowerCase().includes(nameFilter.trim().toLowerCase()))
    : entries;

  return (
    <div className="league-search">
      <form className="manager-search-form" onSubmit={submitLeague}>
        <label htmlFor="league-id-input">League ID</label>
        <div className="manager-search-input-row">
          <input
            id="league-id-input"
            value={leagueIdInput}
            onChange={(event) => setLeagueIdInput(event.target.value)}
            placeholder="e.g. 314 (Overall)"
            inputMode="numeric"
            autoComplete="off"
          />
          <button className="btn sm" type="submit" disabled={loading}>
            {loading && page === 1 ? "Loading…" : "Load league"}
          </button>
        </div>
      </form>
      {error && <p className="manager-search-error" role="alert">{error}</p>}
      {leagueName && (
        <>
          <label className="league-search-filter">
            <span className="sr-only">Filter loaded members by name</span>
            <input
              type="search"
              placeholder={`Filter ${leagueName} members by name or team`}
              value={nameFilter}
              onChange={(event) => setNameFilter(event.target.value)}
              autoComplete="off"
            />
          </label>
          <p className="league-search-note">
            Showing {entries.length} loaded member{entries.length === 1 ? "" : "s"} of {leagueName}.
            {hasNext ? " Load more to search further down the standings." : " That's everyone."}
          </p>
          <div className="manager-search-results" role="listbox" aria-label="League members">
            {filtered.map((entry) => (
              <button
                key={entry.entry_id}
                type="button"
                role="option"
                aria-selected={false}
                className="manager-search-result"
                onClick={() => onSelect(candidateFromLeagueEntry(entry))}
              >
                <span><strong>{entry.manager_name || "Unnamed manager"}</strong><small>{entry.team_name || "Unnamed team"}</small></span>
                <span><b>Entry {entry.entry_id}</b><small>Rank {entry.rank ?? "--"} · {entry.total_points ?? "--"} pts</small></span>
              </button>
            ))}
            {filtered.length === 0 && (
              <p className="manager-search-empty">No loaded member matches that filter.</p>
            )}
          </div>
          {hasNext && (
            <button
              type="button"
              className="btn secondary sm"
              disabled={loading}
              onClick={() => leagueId != null && void loadPage(leagueId, page + 1, true)}
            >
              {loading ? "Loading…" : "Load more"}
            </button>
          )}
        </>
      )}
    </div>
  );
}

interface ManagerSearchProps {
  readonly snapshot: PlatformSnapshot;
  readonly onImport: (lineup: ManagerLineup) => void;
}

export function ManagerSearch({ snapshot, onImport }: ManagerSearchProps) {
  const [mode, setMode] = React.useState<"entry" | "league">("entry");
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<ManagerSearchCandidate[]>([]);
  const [selected, setSelected] = React.useState<ManagerSearchCandidate | null>(null);
  const [lineup, setLineup] = React.useState<ManagerLineup | null>(null);
  const [status, setStatus] = React.useState<"idle" | "searching" | "loading" | "ready">("idle");
  const [error, setError] = React.useState<string | null>(null);
  const [importing, setImporting] = React.useState(false);
  const sequence = React.useRef(0);
  const timer = React.useRef<number | null>(null);

  React.useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  }, []);

  const runSearch = React.useCallback(async (rawQuery: string) => {
    const nextQuery = rawQuery.trim();
    const currentSequence = sequence.current + 1;
    sequence.current = currentSequence;
    if (!nextQuery) {
      setResults([]);
      setSelected(null);
      setLineup(null);
      setError(null);
      setStatus("idle");
      return;
    }
    setStatus("searching");
    setError(null);
    setSelected(null);
    setLineup(null);
    try {
      const response = await api.searchManagers(nextQuery);
      if (sequence.current !== currentSequence) return;
      setResults(response.results);
      setStatus("ready");
    } catch (err) {
      if (sequence.current !== currentSequence) return;
      setResults([]);
      setStatus("ready");
      setError(describeSearchError(err, "Manager search failed."));
    }
  }, []);

  function updateQuery(nextQuery: string) {
    setQuery(nextQuery);
    sequence.current += 1;
    if (timer.current !== null) window.clearTimeout(timer.current);
    if (nextQuery.trim() && !/^\d+$/.test(nextQuery.trim())) {
      timer.current = window.setTimeout(() => void runSearch(nextQuery), 300);
    }
  }

  async function selectCandidate(candidate: ManagerSearchCandidate) {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
    const currentSequence = sequence.current + 1;
    sequence.current = currentSequence;
    setSelected(candidate);
    setLineup(null);
    setStatus("loading");
    setError(null);
    try {
      const response = await api.managerLineup(candidate.entry_id);
      if (sequence.current !== currentSequence) return;
      setLineup(response);
      setStatus("ready");
    } catch (err) {
      if (sequence.current !== currentSequence) return;
      setStatus("ready");
      setError(err instanceof Error ? err.message : "Lineup preview failed.");
    }
  }

  async function importLineup() {
    if (!lineup) return;
    setImporting(true);
    try {
      onImport(lineup);
    } finally {
      setImporting(false);
    }
  }

  return (
    <section className="manager-search" aria-label="Find a public FPL manager">
      <div className="manager-search-head">
        <div>
          <span className="eyebrow muted">Manager lookup</span>
          <h2>Inspect a public team</h2>
          <p>
            {mode === "entry"
              ? "Use an entry ID to load the latest public XI, bench, and armbands. Viewing is read-only until you choose to import."
              : "Load a classic league's standings (your own mini-league, or a public one) and search its members by name."}
          </p>
        </div>
        <span className="manager-search-source">FPL public API</span>
      </div>
      <div className="manager-search-mode" role="tablist" aria-label="Search mode">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "entry"}
          className={`mini-chip${mode === "entry" ? " is-active" : ""}`}
          onClick={() => setMode("entry")}
        >
          By entry ID
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "league"}
          className={`mini-chip${mode === "league" ? " is-active" : ""}`}
          onClick={() => setMode("league")}
        >
          By league (name search)
        </button>
      </div>

      {mode === "entry" ? (
        <>
          <form className="manager-search-form" onSubmit={(event) => { event.preventDefault(); void runSearch(query); }}>
            <label htmlFor="manager-search-input">FPL entry ID</label>
            <div className="manager-search-input-row">
              <input
                id="manager-search-input"
                value={query}
                onChange={(event) => updateQuery(event.target.value)}
                placeholder="e.g. 123456"
                inputMode="numeric"
                autoComplete="off"
              />
              <button className="btn sm" type="submit" disabled={status === "searching" || status === "loading"}>
                {status === "searching" ? "Searching…" : "Search"}
              </button>
            </div>
          </form>
          {error && <p className="manager-search-error" role="alert">{error}</p>}
          {status === "ready" && !error && results.length === 0 && !lineup && (
            <p className="manager-search-empty">No public manager matched that query.</p>
          )}
          {results.length > 0 && (
            <div className="manager-search-results" role="listbox" aria-label="Manager search results">
              {results.map((candidate) => (
                <button
                  key={candidate.entry_id}
                  type="button"
                  role="option"
                  aria-selected={selected?.entry_id === candidate.entry_id}
                  className={`manager-search-result${selected?.entry_id === candidate.entry_id ? " is-selected" : ""}`}
                  onClick={() => void selectCandidate(candidate)}
                >
                  <span><strong>{candidate.manager_name || "Unnamed manager"}</strong><small>{candidate.team_name || "Unnamed team"}</small></span>
                  <span><b>Entry {candidate.entry_id}</b><small>Rank {candidate.overall_rank ?? "--"} · {candidate.total_points ?? "--"} pts</small></span>
                </button>
              ))}
            </div>
          )}
        </>
      ) : (
        <LeagueSearchPanel onSelect={(candidate) => void selectCandidate(candidate)} />
      )}
      {status === "loading" && <p className="manager-search-loading" aria-live="polite">Loading latest public lineup…</p>}
      {lineup && <ManagerLineupPreview lineup={lineup} snapshot={snapshot} importing={importing} onImport={() => void importLineup()} onClose={() => { setLineup(null); setSelected(null); }} />}
    </section>
  );
}
