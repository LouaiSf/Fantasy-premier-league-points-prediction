"use client";

import * as React from "react";
import { api } from "@/lib/api";
import type { PlatformSnapshot, PlayerRecord, SquadResult } from "@/lib/types";

const SQUAD_STORAGE_KEY = "fpl-assistant-squad";

interface StoredSquadData {
  season?: string;
  ids: number[];
  formation?: string;
  captainId?: number;
  xiIds?: number[];
  benchIds?: number[];
}

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
  setTeamResult: (result: SquadResult | null) => void;

  selectedPlayer: PlayerRecord | null;
  openProfile: (player: PlayerRecord) => void;
  closeProfile: () => void;

  toastMessage: string | null;
  toast: (message: string) => void;
  dismissToast: () => void;
}

const AppContext = React.createContext<AppState | null>(null);

function parseStoredSquad(): StoredSquadData | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(SQUAD_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      // Legacy format: array of strings
      return { ids: [], season: undefined };
    }
    if (parsed && typeof parsed === "object" && Array.isArray(parsed.ids)) {
      return parsed as StoredSquadData;
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

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [snapshot, setSnapshot] = React.useState<PlatformSnapshot | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [squadElements, setSquadElementsState] = React.useState<number[]>([]);
  const [teamResult, setTeamResultState] = React.useState<SquadResult | null>(null);
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
      const data: StoredSquadData = {
        season: currentSnapshot.season,
        ids,
        formation: result?.formation,
        captainId: result?.captain?.element,
        xiIds: result?.xi.map((p) => p.element),
        benchIds: result?.bench.map((p) => p.element),
      };
      window.localStorage.setItem(SQUAD_STORAGE_KEY, JSON.stringify(data));
    },
    [],
  );

  const fetchSnapshot = React.useCallback(() => {
    return api.platform().then((data) => {
      setSnapshot(data);
      const playerById = new Map(data.players.map((p) => [p.element, p]));
      const playerByName = new Map(data.players.map((p) => [p.name, p]));

      const stored = parseStoredSquad();
      const legacyNames = parseLegacyNames();

      if (stored && stored.ids.length > 0) {
        if (stored.season && stored.season !== data.season) {
          window.localStorage.removeItem(SQUAD_STORAGE_KEY);
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
          const captain = (stored.captainId && playerById.get(stored.captainId)) || xi[0] || null;
          if (xi.length === 11 && bench.length === 4) {
            setTeamResultState({
              ok: true,
              budget: 100.0,
              spend: totalValue,
              xi,
              bench,
              captain,
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
    (result: SquadResult | null) => {
      setTeamResultState(result);
      if (result) {
        const ids = result.xi.map((p) => p.element).concat(result.bench.map((p) => p.element));
        setSquadElementsState(ids);
        saveSquadData(ids, snapshot, result);
      }
    },
    [saveSquadData, snapshot],
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
