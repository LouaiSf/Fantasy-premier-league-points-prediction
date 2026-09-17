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

  squadNames: string[];
  setSquadNames: (names: string[]) => void;
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
  const [squadNames, setSquadNamesState] = React.useState<string[]>([]);
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
    (names: string[], currentSnapshot: PlatformSnapshot | null, result: SquadResult | null) => {
      if (typeof window === "undefined" || !currentSnapshot) return;
      const playerMap = new Map(currentSnapshot.players.map((p) => [p.name, p]));
      const ids = names.map((n) => playerMap.get(n)?.element).filter((id): id is number => id != null);
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
          setSquadNamesState([]);
          setTeamResultState(null);
          toast(`New season (${data.season}) — please rebuild your squad.`);
          return;
        }

        const validPlayers = stored.ids
          .map((id) => playerById.get(id))
          .filter((p): p is PlayerRecord => p != null);

        const loadedNames = validPlayers.map((p) => p.name);
        setSquadNamesState(loadedNames);

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
        // Migrate legacy names
        const validNames = legacyNames.filter((name) => playerByName.has(name));
        setSquadNamesState(validNames);
        saveSquadData(validNames, data, null);
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

  const setSquadNames = React.useCallback(
    (names: string[]) => {
      setSquadNamesState(names);
      setTeamResultState(null);
      saveSquadData(names, snapshot, null);
    },
    [saveSquadData, snapshot],
  );

  const setTeamResult = React.useCallback(
    (result: SquadResult | null) => {
      setTeamResultState(result);
      if (result) {
        const names = result.xi.map((p) => p.name).concat(result.bench.map((p) => p.name));
        saveSquadData(names, snapshot, result);
      }
    },
    [saveSquadData, snapshot],
  );

  const squadPlayers = React.useMemo(() => {
    if (!snapshot) return [];
    const wanted = new Set(squadNames);
    return snapshot.players.filter((player) => wanted.has(player.name));
  }, [snapshot, squadNames]);

  const value: AppState = {
    snapshot,
    loading,
    error,
    reload: load,
    squadNames,
    setSquadNames,
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
