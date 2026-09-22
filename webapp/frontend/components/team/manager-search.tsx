"use client";

import * as React from "react";
import { api } from "@/lib/api";
import type { ManagerLineup, ManagerSearchCandidate, PlatformSnapshot } from "@/lib/types";
import { ManagerLineupPreview } from "@/components/team/manager-lineup-preview";

interface ManagerSearchProps {
  readonly snapshot: PlatformSnapshot;
  readonly onImport: (lineup: ManagerLineup) => void;
}

export function ManagerSearch({ snapshot, onImport }: ManagerSearchProps) {
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
      setError(err instanceof Error ? err.message : "Manager search failed.");
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
          <p>Use an entry ID to load the latest public XI, bench, and armbands. Viewing is read-only until you choose to import.</p>
        </div>
        <span className="manager-search-source">FPL public API</span>
      </div>
      <form className="manager-search-form" onSubmit={(event) => { event.preventDefault(); void runSearch(query); }}>
        <label htmlFor="manager-search-input">Entry ID or manager name</label>
        <div className="manager-search-input-row">
          <input
            id="manager-search-input"
            value={query}
            onChange={(event) => updateQuery(event.target.value)}
            placeholder="e.g. 123456"
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
      {status === "loading" && <p className="manager-search-loading" aria-live="polite">Loading latest public lineup…</p>}
      {lineup && <ManagerLineupPreview lineup={lineup} snapshot={snapshot} importing={importing} onImport={() => void importLineup()} onClose={() => { setLineup(null); setSelected(null); }} />}
    </section>
  );
}
