"use client";

import * as React from "react";
import { LeagueSearchPanel } from "@/components/team/league-search";
import { ManagerLineupPreview } from "@/components/team/manager-lineup-preview";
import { api, ApiRequestError } from "@/lib/api";
import { isRecentManager, parseManagerEntryInput, upsertRecentManager, type RecentManager } from "@/lib/manager-entry";
import type { ManagerLineup, ManagerSearchCandidate, PlatformSnapshot } from "@/lib/types";

interface ManagerSearchProps {
  readonly snapshot: PlatformSnapshot;
  readonly onImport: (lineup: ManagerLineup) => boolean;
}

type SearchMode = "entry" | "league";
type SearchStatus = "idle" | "searching" | "loading" | "ready";

function describeError(error: unknown): string {
  if (error instanceof ApiRequestError && error.code === "manager_not_found") {
    return "No public FPL team was found for that entry ID.";
  }
  if (error instanceof ApiRequestError && error.code === "lineup_not_found") {
    return "This team has no public lineup available for preview.";
  }
  return error instanceof Error ? error.message : "Manager lookup failed.";
}

export function ManagerSearch({ snapshot, onImport }: ManagerSearchProps) {
  const [mode, setMode] = React.useState<SearchMode>("entry");
  const [entryQuery, setEntryQuery] = React.useState("");
  const [leagueQuery, setLeagueQuery] = React.useState("");
  const [results, setResults] = React.useState<ManagerSearchCandidate[]>([]);
  const [selected, setSelected] = React.useState<ManagerSearchCandidate | null>(null);
  const [lineup, setLineup] = React.useState<ManagerLineup | null>(null);
  const [status, setStatus] = React.useState<SearchStatus>("idle");
  const [error, setError] = React.useState<string | null>(null);
  const [recent, setRecent] = React.useState<RecentManager[]>([]);
  const [recentError, setRecentError] = React.useState<string | null>(null);
  const [importing, setImporting] = React.useState(false);
  const requestSequence = React.useRef(0);
  const requestController = React.useRef<AbortController | null>(null);
  const recentStorageKey = "fpl-assistant-recent-managers:" + snapshot.season;

  React.useEffect(() => () => {
    requestController.current?.abort();
    requestSequence.current += 1;
  }, []);

  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(recentStorageKey);
      if (!raw) {
        setRecent([]);
        return;
      }
      const stored: unknown = JSON.parse(raw);
      const next = Array.isArray(stored)
        ? stored.filter((item): item is RecentManager => isRecentManager(item, snapshot.season)).slice(0, 5)
        : [];
      setRecent(next);
    } catch (cause) {
      if (cause instanceof SyntaxError) {
        window.localStorage.removeItem(recentStorageKey);
        setRecent([]);
        return;
      }
      if (cause instanceof DOMException) {
        setRecentError("Recent teams could not be read from this device.");
        return;
      }
      throw cause;
    }
  }, [recentStorageKey, snapshot.season]);

  function cancelRequest(): number {
    requestController.current?.abort();
    requestController.current = null;
    requestSequence.current += 1;
    return requestSequence.current;
  }

  function startRequest(): { readonly sequence: number; readonly controller: AbortController } {
    const sequence = cancelRequest();
    const controller = new AbortController();
    requestController.current = controller;
    return { sequence, controller };
  }

  function clearSelection(clearResults: boolean): void {
    cancelRequest();
    setSelected(null);
    setLineup(null);
    setStatus("idle");
    setError(null);
    if (clearResults) setResults([]);
  }

  async function runEntrySearch(rawQuery: string): Promise<void> {
    const parsed = parseManagerEntryInput(rawQuery);
    if (parsed.kind === "invalid") {
      setError(parsed.message);
      setStatus("ready");
      return;
    }
    if (parsed.kind === "name") {
      setLeagueQuery(parsed.query);
      setMode("league");
      clearSelection(true);
      return;
    }

    const active = startRequest();
    setEntryQuery(rawQuery);
    setSelected(null);
    setLineup(null);
    setResults([]);
    setStatus("searching");
    setError(null);
    try {
      const response = await api.searchManagers(String(parsed.entryId), active.controller.signal);
      if (requestSequence.current !== active.sequence) return;
      setResults(response.results);
      setStatus("ready");
      if (response.results.length === 0) setError("No public FPL team was found for that entry ID.");
      if (response.results.length === 1) await selectCandidate(response.results[0]);
    } catch (cause) {
      if (requestSequence.current !== active.sequence || active.controller.signal.aborted) return;
      setResults([]);
      setStatus("ready");
      setError(describeError(cause));
    }
  }

  async function selectCandidate(candidate: ManagerSearchCandidate): Promise<void> {
    const active = startRequest();
    setSelected(candidate);
    setLineup(null);
    setStatus("loading");
    setError(null);
    try {
      const response = await api.managerLineup(
        candidate.entry_id,
        undefined,
        active.controller.signal,
      );
      if (requestSequence.current !== active.sequence) return;
      setLineup(response);
      setStatus("ready");
    } catch (cause) {
      if (requestSequence.current !== active.sequence || active.controller.signal.aborted) return;
      setStatus("ready");
      setError(describeError(cause));
    }
  }

  async function openRecentTeam(manager: RecentManager): Promise<void> {
    const active = startRequest();
    const candidate: ManagerSearchCandidate = {
      entry_id: manager.entry_id,
      manager_name: manager.manager_name,
      team_name: manager.team_name,
      overall_rank: null,
      total_points: null,
    };
    setMode("entry");
    setEntryQuery(String(manager.entry_id));
    setResults([]);
    setSelected(candidate);
    setLineup(null);
    setStatus("searching");
    setError(null);
    try {
      const response = await api.searchManagers(
        String(manager.entry_id),
        active.controller.signal,
      );
      if (requestSequence.current !== active.sequence) return;
      const current = response.results.find((item) => item.entry_id === manager.entry_id);
      if (!current) {
        setSelected(null);
        setStatus("ready");
        setError("This saved entry is no longer public. Search again or remove it from Recent teams.");
        return;
      }
      setResults(response.results);
      setSelected(current);
      setStatus("loading");
      const preview = await api.managerLineup(
        manager.entry_id,
        undefined,
        active.controller.signal,
      );
      if (requestSequence.current !== active.sequence) return;
      setLineup(preview);
      setStatus("ready");
    } catch (cause) {
      if (requestSequence.current !== active.sequence || active.controller.signal.aborted) return;
      setStatus("ready");
      setError(describeError(cause));
    }
  }

  function handleEntryInput(value: string): void {
    setEntryQuery(value);
    clearSelection(true);
    const parsed = parseManagerEntryInput(value);
    if (parsed.kind === "name") {
      setLeagueQuery(parsed.query);
      setMode("league");
    }
  }

  function changeMode(nextMode: SearchMode): void {
    setMode(nextMode);
    clearSelection(true);
  }

  function importLineup(): void {
    if (!lineup) return;
    setImporting(true);
    try {
      if (!onImport(lineup)) {
        setError("This lineup could not be imported into the current season.");
        return;
      }
      const next = upsertRecentManager(
        recent,
        {
          season: snapshot.season,
          entry_id: lineup.manager.entry_id,
          manager_name: lineup.manager.manager_name,
          team_name: lineup.manager.team_name,
        },
        new Date().toISOString(),
      );
      setRecent(next);
      setRecentError(null);
      try {
        window.localStorage.setItem(recentStorageKey, JSON.stringify(next));
      } catch (cause) {
        if (cause instanceof DOMException) {
          setRecentError("Team imported, but Recent teams could not be saved on this device.");
          return;
        }
        throw cause;
      }
    } finally {
      setImporting(false);
    }
  }

  function clearRecent(): void {
    window.localStorage.removeItem(recentStorageKey);
    setRecent([]);
    setRecentError(null);
  }

  return (
    <section className="manager-search" aria-label="Find your FPL team">
      <div className="manager-search-head">
        <div>
          <span className="eyebrow muted">Team lookup</span>
          <h2>Find your FPL team</h2>
          <p>Paste the link to your FPL team, or enter its entry ID. For a name, search a mini-league.</p>
        </div>
        <span className="manager-search-source">FPL public API</span>
      </div>

      <div className="manager-search-mode" aria-label="Team search mode">
        <button
          className={"mini-chip" + (mode === "entry" ? " is-active" : "")}
          type="button"
          aria-pressed={mode === "entry"}
          onClick={() => changeMode("entry")}
        >
          Entry ID or link
        </button>
        <button
          className={"mini-chip" + (mode === "league" ? " is-active" : "")}
          type="button"
          aria-pressed={mode === "league"}
          onClick={() => changeMode("league")}
        >
          Search a mini-league
        </button>
      </div>

      {mode === "entry" ? (
        <form
          className="manager-search-form"
          onSubmit={(event) => {
            event.preventDefault();
            void runEntrySearch(entryQuery);
          }}
        >
          <label htmlFor="manager-search-input">FPL entry ID or team link</label>
          <div className="manager-search-input-row">
            <input
              id="manager-search-input"
              value={entryQuery}
              onChange={(event) => handleEntryInput(event.target.value)}
              placeholder="Entry ID or https://fantasy.premierleague.com/entry/…"
              autoComplete="off"
            />
            <button
              className="btn sm"
              type="submit"
              disabled={status === "searching" || status === "loading"}
            >
              {status === "searching" ? "Searching…" : "Find team"}
            </button>
          </div>
          <p className="manager-search-help">
            Open your team on the official FPL site and copy its URL.{" "}
            <a href="https://fantasy.premierleague.com/" target="_blank" rel="noreferrer">
              Open FPL
            </a>
          </p>
        </form>
      ) : (
        <LeagueSearchPanel
          query={leagueQuery}
          onQueryChange={setLeagueQuery}
          onCriteriaChange={() => clearSelection(true)}
          onSelect={(candidate) => void selectCandidate(candidate)}
        />
      )}

      {recent.length > 0 && (
        <section className="recent-manager-list" aria-label="Recent teams">
          <div className="recent-manager-head">
            <div>
              <span className="kicker">Recent teams</span>
              <p>Saved on this device · {snapshot.season}</p>
            </div>
            <button className="btn secondary sm" type="button" onClick={clearRecent}>
              Clear
            </button>
          </div>
          <ul>
            {recent.map((manager) => (
              <li key={manager.entry_id}>
                <button
                  className="recent-manager"
                  type="button"
                  onClick={() => void openRecentTeam(manager)}
                >
                  <strong>{manager.team_name || manager.manager_name || "Public FPL team"}</strong>
                  <span>{manager.manager_name} · Entry {manager.entry_id}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {recentError && <p className="manager-search-error" role="status">{recentError}</p>}
      {error && <p className="manager-search-error" role="alert">{error}</p>}
      {status === "ready" && !error && results.length === 0 && !lineup && mode === "entry" && (
        <p className="manager-search-empty">Enter a public entry ID or team link to preview its lineup.</p>
      )}
      {results.length > 0 && mode === "entry" && (
        <ul className="manager-search-results" aria-label="Manager search results">
          {results.map((candidate) => (
            <li key={candidate.entry_id}>
              <button
                className={"manager-search-result" + (selected?.entry_id === candidate.entry_id ? " is-selected" : "")}
                type="button"
                aria-current={selected?.entry_id === candidate.entry_id ? "true" : undefined}
                onClick={() => void selectCandidate(candidate)}
              >
                <span>
                  <strong>{candidate.manager_name || "Unnamed manager"}</strong>
                  <small>{candidate.team_name || "Unnamed team"}</small>
                </span>
                <span>
                  <b>Entry {candidate.entry_id}</b>
                  <small>Rank {candidate.overall_rank ?? "--"} · {candidate.total_points ?? "--"} pts</small>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {status === "loading" && (
        <p className="manager-search-loading" aria-live="polite">Loading latest public lineup…</p>
      )}
      {lineup && (
        <ManagerLineupPreview
          lineup={lineup}
          snapshot={snapshot}
          importing={importing}
          onImport={importLineup}
          onClose={() => {
            setLineup(null);
            setSelected(null);
            setStatus("idle");
          }}
        />
      )}
    </section>
  );
}
