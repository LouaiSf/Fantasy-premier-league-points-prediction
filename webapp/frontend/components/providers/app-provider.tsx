"use client";

import * as React from "react";
import { api } from "@/lib/api";
import type {
  ManagerLineup,
  PlatformSnapshot,
  PlayerRecord,
  SquadResult,
  StoredSquad,
} from "@/lib/types";

const SQUAD_STORAGE_KEY = "fpl-assistant-squad";

interface AppState {
  snapshot: PlatformSnapshot | null;
  loading: boolean;
  error: string | null;
  reload: () => void;

  // A squad is held as element ids -- the FPL player id -- because that is the
  // only identifier both sides of this app agree on. squadNames is derived from
  // them for the API, which matches on the prediction export's own name column.
  squadElements: number[];
  setSquadElements: (elements: number[]) => void;
  squadNames: string[];
  squadPlayers: PlayerRecord[];

  teamResult: SquadResult | null;
  setTeamResult: (result: SquadResult | null, source?: "manual" | "optimizer") => void;
  setImportedTeam: (lineup: ManagerLineup) => void;
  storedSquad: StoredSquad | null;

  selectedPlayer: PlayerRecord | null;
  openProfile: (player: PlayerRecord) => void;
  closeProfile: () => void;

  toastMessage: string | null;
  toast: (message: string) => void;
  dismissToast: () => void;
}

const AppContext = React.createContext<AppState | null>(null);

function parseStoredSquad(): StoredSquad | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(SQUAD_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      // Legacy format: array of strings
      return { ids: [], season: undefined };
    }
    if (isStoredSquad(parsed)) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

function parseLegacyNames(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(SQUAD_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.filter((item) => typeof item === "string");
    }
    return [];
  } catch {
    return [];
  }
}

function isStoredSquad(value: unknown): value is StoredSquad {
  if (typeof value !== "object" || value === null || !("ids" in value)) return false;
  const ids = value.ids;
  return Array.isArray(ids) && ids.every((id) => typeof id === "number");
}

function normalizeSquadResult(result: SquadResult, snapshot: PlatformSnapshot | null): SquadResult {
  if (!snapshot) return result;
  const byElement = new Map(snapshot.players.map((player) => [player.element, player]));
  const merge = (player: PlayerRecord): PlayerRecord => ({
    ...player,
    ...(byElement.get(player.element) ?? {}),
  });
  return {
    ...result,
    xi: result.xi.map(merge),
    bench: result.bench.map(merge),
    captain: result.captain ? merge(result.captain) : null,
    vice_captain: result.vice_captain ? merge(result.vice_captain) : null,
  };
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [snapshot, setSnapshot] = React.useState<PlatformSnapshot | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [squadElements, setSquadElementsState] = React.useState<number[]>([]);
  const [teamResult, setTeamResultState] = React.useState<SquadResult | null>(null);
  const [storedSquad, setStoredSquad] = React.useState<StoredSquad | null>(null);
  const [selectedPlayer, setSelectedPlayer] = React.useState<PlayerRecord | null>(null);

  const [toastQueue, setToastQueue] = React.useState<string[]>([]);
  const [toastMessage, setToastMessage] = React.useState<string | null>(null);
  const toastTimer = React.useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const dismissToast = React.useCallback(() => {
    window.clearTimeout(toastTimer.current);
    setToastMessage(null);
  }, []);

  const toast = React.useCallback((message: string) => {
    setToastQueue((prev) => [...prev, message]);
  }, []);

  // Process toast queue
  React.useEffect(() => {
    if (toastMessage || toastQueue.length === 0) return;
    const next = toastQueue[0];
    const timer = window.setTimeout(() => {
      setToastQueue((prev) => prev.slice(1));
      setToastMessage(next);
      window.clearTimeout(toastTimer.current);
      toastTimer.current = setTimeout(() => {
        setToastMessage(null);
      }, 3500);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [toastMessage, toastQueue]);

  const saveSquadData = React.useCallback(
    (ids: number[], currentSnapshot: PlatformSnapshot | null, result: SquadResult | null) => {
      if (typeof window === "undefined" || !currentSnapshot) return;
      const data: StoredSquad = {
        season: currentSnapshot.season,
        ids,
        formation: result?.formation,
        captainId: result?.captain?.element,
        viceCaptainId: result?.vice_captain?.element,
        xiIds: result?.xi.map((p) => p.element),
        benchIds: result?.bench.map((p) => p.element),
        bank: currentSnapshot.players.length ? 100 - (result?.spend ?? 0) : 0,
        source: "manual",
      };
      window.localStorage.setItem(SQUAD_STORAGE_KEY, JSON.stringify(data));
      setStoredSquad(data);
    },
    [],
  );

  const fetchSnapshot = React.useCallback(() => {
    return api.platform().then((data) => {
      setSnapshot(data);
      const playerById = new Map(data.players.map((p) => [p.element, p]));
      const playerByName = new Map(data.players.map((p) => [p.name, p]));

      const stored = parseStoredSquad();
      setStoredSquad(stored);
      const legacyNames = parseLegacyNames();

      if (stored && stored.ids.length > 0) {
        if (stored.season && stored.season !== data.season) {
          window.localStorage.removeItem(SQUAD_STORAGE_KEY);
          setStoredSquad(null);
          setSquadElementsState([]);
          setTeamResultState(null);
          toast(`New season (${data.season}) — please rebuild your squad.`);
          return;
        }

        const validPlayers = stored.ids
          .map((id) => playerById.get(id))
          .filter((p): p is PlayerRecord => p != null);

        setSquadElementsState(validPlayers.map((p) => p.element));

        // Budget check
        const totalValue = validPlayers.reduce((sum, p) => sum + p.value_m, 0);
        if (totalValue > 100.0) {
          toast(`Squad over budget (£${totalValue.toFixed(1)}m) — prices may have changed.`);
        }

        // Restore teamResult if stored
        if (stored.xiIds && stored.benchIds && stored.formation) {
          const xi = stored.xiIds.map((id) => playerById.get(id)).filter((p): p is PlayerRecord => p != null);
          const bench = stored.benchIds.map((id) => playerById.get(id)).filter((p): p is PlayerRecord => p != null);
          const armbandCandidates = xi
            .filter((player) => player.position !== "GK")
            .sort((a, b) =>
              Number(b.predicted_points ?? b.form ?? 0) - Number(a.predicted_points ?? a.form ?? 0),
            );
          const captain =
            (stored.captainId && playerById.get(stored.captainId)) || armbandCandidates[0] || null;
          const viceCaptain =
            (stored.viceCaptainId && playerById.get(stored.viceCaptainId)) ||
            armbandCandidates.find((player) => player.element !== captain?.element) ||
            null;
          if (xi.length === 11 && bench.length === 4) {
            setTeamResultState({
              ok: true,
              budget: 100.0,
              spend: totalValue,
              xi,
              bench,
              captain,
              vice_captain: viceCaptain,
              xi_points: xi.reduce((sum, p) => sum + (p.predicted_points ?? p.form ?? 0), 0),
              formation: stored.formation,
            });
          }
        }
      } else if (legacyNames.length > 0) {
        // A store written before squads were keyed on ids. Those names could be
        // either spelling depending on where they were set, so try both.
        const playerByWebName = new Map(data.players.map((p) => [p.web_name, p]));
        const migrated = legacyNames
          .map((name) => playerByName.get(name) ?? playerByWebName.get(name))
          .filter((p): p is PlayerRecord => p != null)
          .map((p) => p.element);
        setSquadElementsState(migrated);
        saveSquadData(migrated, data, null);
      }
    });
  }, [saveSquadData, toast]);

  const load = React.useCallback(() => {
    setLoading(true);
    setError(null);
    fetchSnapshot()
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [fetchSnapshot]);

  React.useEffect(() => {
    fetchSnapshot()
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [fetchSnapshot]);

  const setSquadElements = React.useCallback(
    (elements: number[]) => {
      setSquadElementsState(elements);
      setTeamResultState(null);
      saveSquadData(elements, snapshot, null);
    },
    [saveSquadData, snapshot],
  );

  const setTeamResult = React.useCallback(
    (result: SquadResult | null, source: "manual" | "optimizer" = "optimizer") => {
      const normalized = result ? normalizeSquadResult(result, snapshot) : null;
      setTeamResultState(normalized);
      if (normalized) {
        const ids = normalized.xi.map((p) => p.element).concat(normalized.bench.map((p) => p.element));
        setSquadElementsState(ids);
        if (snapshot) {
          const data: StoredSquad = {
            season: snapshot.season,
            ids,
            formation: normalized.formation,
            captainId: normalized.captain?.element,
            viceCaptainId: normalized.vice_captain?.element,
            xiIds: normalized.xi.map((player) => player.element),
            benchIds: normalized.bench.map((player) => player.element),
            bank: 100 - normalized.spend,
            source,
          };
          window.localStorage.setItem(SQUAD_STORAGE_KEY, JSON.stringify(data));
          setStoredSquad(data);
        }
      }
    },
    [snapshot],
  );

  const setImportedTeam = React.useCallback(
    (lineup: ManagerLineup) => {
      if (!snapshot || lineup.missing_elements.length > 0 || lineup.picks.length !== 15) return;
      const byElement = new Map(snapshot.players.map((player) => [player.element, player]));
      const picks = [...lineup.picks].sort((a, b) => a.position - b.position);
      const selected = picks
        .map((pick) => byElement.get(pick.element))
        .filter((player): player is PlayerRecord => player != null);
      const xi = selected.slice(0, 11);
      const bench = selected.slice(11);
      const captain = selected.find((player) => picks.find((pick) => pick.element === player.element)?.is_captain) ?? null;
      const viceCaptain = selected.find((player) => picks.find((pick) => pick.element === player.element)?.is_vice_captain) ?? null;
      const counts = xi.reduce<Record<string, number>>((result, player) => {
        result[player.position] = (result[player.position] ?? 0) + 1;
        return result;
      }, {});
      const result: SquadResult = {
        ok: true,
        budget: 100,
        spend: selected.reduce((total, player) => total + player.value_m, 0),
        xi,
        bench,
        captain,
        vice_captain: viceCaptain,
        xi_points: xi.reduce((total, player) => total + (player.predicted_points ?? 0), 0),
        formation: `${counts.DEF ?? 0}-${counts.MID ?? 0}-${counts.FWD ?? 0}`,
      };
      const data: StoredSquad = {
        season: snapshot.season,
        ids: selected.map((player) => player.element),
        formation: result.formation,
        captainId: captain?.element,
        viceCaptainId: viceCaptain?.element,
        xiIds: xi.map((player) => player.element),
        benchIds: bench.map((player) => player.element),
        bank: lineup.bank ?? 0,
        source: "manager",
        sourceEntryId: lineup.manager.entry_id,
        sourceManagerName: lineup.manager.manager_name,
        sourceTeamName: lineup.manager.team_name,
        sourceGameweek: lineup.lineup_gameweek,
      };
      window.localStorage.setItem(SQUAD_STORAGE_KEY, JSON.stringify(data));
      setStoredSquad(data);
      setSquadElementsState(data.ids);
      setTeamResultState(result);
    },
    [snapshot],
  );

  const squadPlayers = React.useMemo(() => {
    if (!snapshot) return [];
    const byElement = new Map(snapshot.players.map((player) => [player.element, player]));
    return squadElements
      .map((element) => byElement.get(element))
      .filter((player): player is PlayerRecord => player != null);
  }, [snapshot, squadElements]);

  // What /api/squad, /api/transfers and /api/chips match on: the name in the
  // prediction export, which is the player's web_name and not the full name
  // the snapshot lists him under.
  const squadNames = React.useMemo(
    () => squadPlayers.map((player) => player.web_name),
    [squadPlayers],
  );

  const value: AppState = {
    snapshot,
    loading,
    error,
    reload: load,
    squadElements,
    setSquadElements,
    squadNames,
    squadPlayers,
    teamResult,
    setTeamResult,
    setImportedTeam,
    storedSquad,
    selectedPlayer,
    openProfile: setSelectedPlayer,
    closeProfile: () => setSelectedPlayer(null),
    toastMessage,
    toast,
    dismissToast,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const ctx = React.useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
