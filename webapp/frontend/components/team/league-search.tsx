"use client";

import * as React from "react";
import { api, ApiRequestError } from "@/lib/api";
import type { LeagueNameSearchResult, LeagueStandingsEntry, ManagerSearchCandidate } from "@/lib/types";

const pageSize = 50;

function checkedPageLabel(pages: readonly number[]): string {
  const sorted = [...new Set(pages)].sort((left, right) => left - right);
  const ranges: Array<{ start: number; end: number }> = [];
  for (const page of sorted) {
    const last = ranges.at(-1);
    if (last && page === last.end + 1) last.end = page;
    else ranges.push({ start: page, end: page });
  }
  return ranges
    .map((range) => range.start === range.end
      ? String(range.start)
      : String(range.start) + "–" + String(range.end))
    .join(", ");
}

function searchErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.code === "league_not_found") return "That league was not found.";
    if (error.code === "upstream_rate_limited") return "Search paused by FPL; try again.";
    if (error.code === "upstream_unavailable") return "FPL standings are unavailable; try again.";
  }
  return error instanceof Error ? error.message : "League search failed.";
}

function candidateFromEntry(entry: LeagueStandingsEntry): ManagerSearchCandidate {
  return {
    entry_id: entry.entry_id,
    manager_name: entry.manager_name,
    team_name: entry.team_name,
    overall_rank: entry.rank,
    total_points: entry.total_points,
  };
}

interface LeagueSearchPanelProps {
  readonly query: string;
  readonly onQueryChange: (query: string) => void;
  readonly onCriteriaChange: () => void;
  readonly onSelect: (candidate: ManagerSearchCandidate) => void;
}

export function LeagueSearchPanel({
  query,
  onQueryChange,
  onCriteriaChange,
  onSelect,
}: LeagueSearchPanelProps) {
  const [leagueIdInput, setLeagueIdInput] = React.useState("");
  const [leagueId, setLeagueId] = React.useState<number | null>(null);
  const [leagueName, setLeagueName] = React.useState<string | null>(null);
  const [rankInput, setRankInput] = React.useState("");
  const [pageJumpInput, setPageJumpInput] = React.useState("");
  const [results, setResults] = React.useState<LeagueStandingsEntry[]>([]);
  const [checkedPages, setCheckedPages] = React.useState<number[]>([]);
  const [scannedEntries, setScannedEntries] = React.useState(0);
  const [nextCursor, setNextCursor] = React.useState<number | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [interrupted, setInterrupted] = React.useState(false);
  const requestId = React.useRef(0);
  const controller = React.useRef<AbortController | null>(null);

  React.useEffect(() => () => {
    controller.current?.abort();
    requestId.current += 1;
  }, []);

  function cancelAndReset(): void {
    controller.current?.abort();
    controller.current = null;
    requestId.current += 1;
    setLeagueId(null);
    setLeagueName(null);
    setResults([]);
    setCheckedPages([]);
    setScannedEntries(0);
    setNextCursor(null);
    setInterrupted(false);
    setError(null);
    setLoading(false);
    onCriteriaChange();
  }

  function updateLeagueId(value: string): void {
    setLeagueIdInput(value);
    cancelAndReset();
  }

  function updateQuery(value: string): void {
    onQueryChange(value);
    cancelAndReset();
  }

  async function search(cursor: number): Promise<void> {
    const parsedLeagueId = Number(leagueIdInput.trim());
    const trimmedQuery = query.trim();
    if (!Number.isSafeInteger(parsedLeagueId) || parsedLeagueId <= 0) {
      setError("Enter a positive numeric league ID.");
      return;
    }
    if (trimmedQuery.length < 2 || trimmedQuery.length > 80) {
      setError("Enter 2 to 80 characters to search a league.");
      return;
    }

    controller.current?.abort();
    const activeController = new AbortController();
    controller.current = activeController;
    requestId.current += 1;
    const activeRequestId = requestId.current;
    setLeagueId(parsedLeagueId);
    setLoading(true);
    setError(null);
    setInterrupted(false);

    try {
      const response = await api.searchLeagueManagers(
        parsedLeagueId,
        trimmedQuery,
        cursor,
        5,
        activeController.signal,
      );
      if (requestId.current !== activeRequestId) return;
      acceptResponse(response, cursor);
    } catch (cause) {
      if (requestId.current !== activeRequestId || activeController.signal.aborted) return;
      setError(searchErrorMessage(cause));
    } finally {
      if (requestId.current === activeRequestId) setLoading(false);
    }
  }

  function acceptResponse(response: LeagueNameSearchResult, cursor: number): void {
    setLeagueName(response.league_name);
    setResults((previous) => {
      const entries = cursor === 1 ? [] : previous;
      const byId = new Map(entries.map((entry) => [entry.entry_id, entry]));
      for (const entry of response.results) byId.set(entry.entry_id, entry);
      return [...byId.values()];
    });
    const pageNumbers: number[] = [];
    for (
      let page = response.scanned_from_page;
      page <= response.scanned_through_page;
      page += 1
    ) {
      pageNumbers.push(page);
    }
    setCheckedPages((previous) => [...new Set([...previous, ...pageNumbers])]);
    setScannedEntries((previous) => previous + response.scanned_entries);
    setNextCursor(response.next_cursor);
    setInterrupted(response.interrupted === true);
    if (response.interrupted) {
      setError(response.interrupted_code === "upstream_rate_limited"
        ? "Search paused by FPL; try again."
        : "FPL standings stopped responding; keep your results and try again.");
    }
  }

  function submitSearch(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const rank = rankInput.trim() ? Number(rankInput) : null;
    if (rank !== null && (!Number.isSafeInteger(rank) || rank <= 0)) {
      setError("Enter a positive rank, or leave it blank.");
      return;
    }
    const startPage = rank === null ? 1 : Math.max(1, Math.ceil(rank / pageSize) - 1);
    cancelAndReset();
    void search(startPage);
  }

  function submitPageJump(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const page = Number(pageJumpInput.trim());
    if (!Number.isSafeInteger(page) || page < 1) {
      setError("Enter a page number of 1 or more.");
      return;
    }
    cancelAndReset();
    void search(page);
  }

  const rangeLabel = checkedPages.length
    ? "Checked pages " + checkedPageLabel(checkedPages)
    : null;

  return (
    <div className="league-search">
      <form className="manager-search-form" onSubmit={submitSearch}>
        <label htmlFor="league-id-input">Mini-league ID</label>
        <div className="manager-search-input-row">
          <input
            id="league-id-input"
            value={leagueIdInput}
            onChange={(event) => updateLeagueId(event.target.value)}
            placeholder="e.g. 314"
            inputMode="numeric"
            autoComplete="off"
          />
          <button className="btn sm" type="submit" disabled={loading}>
            {loading ? "Searching…" : "Search league"}
          </button>
        </div>
        <label htmlFor="league-name-input">Manager or team name</label>
        <input
          id="league-name-input"
          value={query}
          onChange={(event) => updateQuery(event.target.value)}
          placeholder="Search within a known league"
          autoComplete="off"
        />
        <label htmlFor="league-rank-input">Approximate rank (optional)</label>
        <input
          id="league-rank-input"
          value={rankInput}
          onChange={(event) => {
            setRankInput(event.target.value);
            cancelAndReset();
          }}
          placeholder="Start near a rank"
          inputMode="numeric"
          autoComplete="off"
        />
      </form>
      {leagueName && <p className="league-search-note">Searching {leagueName} · {rangeLabel ?? "No pages checked yet"} · {scannedEntries} members checked.</p>}
      {leagueId !== null && rankInput.trim() && (
        <p className="league-search-note">
          Search starts near rank {rankInput}; earlier pages are not included unless searched.
        </p>
      )}
      {loading && (
        <p className="manager-search-loading" aria-live="polite">
          Scanning standings from page {nextCursor ?? (checkedPages.at(-1) ?? 0) + 1}, up to five pages…
        </p>
      )}
      {error && <p className="manager-search-error" role="alert">{error}</p>}
      {interrupted && rangeLabel && (
        <p className="league-search-note">Partial results are kept. {rangeLabel}.</p>
      )}
      {results.length > 0 && (
        <ul className="manager-search-results" aria-label="League name search results">
          {results.map((entry) => (
            <li key={entry.entry_id}>
              <button
                className="manager-search-result"
                type="button"
                onClick={() => onSelect(candidateFromEntry(entry))}
              >
                <span><strong>{entry.manager_name || "Unnamed manager"}</strong><small>{entry.team_name || "Unnamed team"}</small></span>
                <span><b>Entry {entry.entry_id}</b><small>Rank {entry.rank ?? "--"} · {entry.total_points ?? "--"} pts</small></span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {checkedPages.length > 0 && results.length === 0 && (
        <p className="manager-search-empty">
          No match in pages {checkedPageLabel(checkedPages)}. Continue searching this league or paste your team link.
        </p>
      )}
      {nextCursor !== null && (
        <button
          className="btn secondary sm"
          type="button"
          disabled={loading}
          onClick={() => void search(nextCursor)}
        >
          {loading ? "Searching…" : "Search next 250 members"}
        </button>
      )}
      <details className="league-search-advanced">
        <summary>Advanced: start at a standings page</summary>
        <form className="league-search-jump" onSubmit={submitPageJump}>
          <label htmlFor="league-page-jump">Page</label>
          <input
            id="league-page-jump"
            value={pageJumpInput}
            onChange={(event) => setPageJumpInput(event.target.value)}
            placeholder="e.g. 25"
            inputMode="numeric"
            autoComplete="off"
          />
          <button className="btn secondary sm" type="submit" disabled={loading}>Start here</button>
        </form>
      </details>
      {leagueId === null && query.trim().length < 2 && (
        <p className="league-search-note">
          Search is limited to this league’s standings. FPL does not provide a public global name search here.
        </p>
      )}
    </div>
  );
}
