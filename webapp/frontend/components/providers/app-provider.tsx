"use client";

import * as React from "react";
import { api } from "@/lib/api";
import type { PlatformSnapshot, PlayerRecord, SquadResult } from "@/lib/types";

const SQUAD_STORAGE_KEY = "fpl-assistant-squad";

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
}

const AppContext = React.createContext<AppState | null>(null);

function readStoredSquad(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(SQUAD_STORAGE_KEY) ?? "[]");
    return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [snapshot, setSnapshot] = React.useState<PlatformSnapshot | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [squadNames, setSquadNamesState] = React.useState<string[]>([]);
  const [teamResult, setTeamResult] = React.useState<SquadResult | null>(null);
  const [selectedPlayer, setSelectedPlayer] = React.useState<PlayerRecord | null>(null);
  const [toastMessage, setToastMessage] = React.useState<string | null>(null);
  const toastTimer = React.useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const fetchSnapshot = React.useCallback(() => {
    return api.platform().then((data) => {
      setSnapshot(data);
      const known = new Set(data.players.map((player) => player.name));
      setSquadNamesState(readStoredSquad().filter((name) => known.has(name)));
    });
  }, []);

  // Manual reload (e.g. a future "reload predictions" action): show the
  // loading state immediately since it is driven by a user event, not by
  // an effect running on render.
  const load = React.useCallback(() => {
    setLoading(true);
    setError(null);
    fetchSnapshot()
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [fetchSnapshot]);

  // Initial fetch on mount. `loading`/`error` already start correct
  // (true/null), so this only needs to settle them once the request
  // resolves -- no synchronous setState in the effect body itself.
  React.useEffect(() => {
    fetchSnapshot()
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [fetchSnapshot]);

  const setSquadNames = React.useCallback((names: string[]) => {
    setSquadNamesState(names);
    setTeamResult(null);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SQUAD_STORAGE_KEY, JSON.stringify(names));
    }
  }, []);

  const squadPlayers = React.useMemo(() => {
    if (!snapshot) return [];
    const wanted = new Set(squadNames);
    return snapshot.players.filter((player) => wanted.has(player.name));
  }, [snapshot, squadNames]);

  const toast = React.useCallback((message: string) => {
    setToastMessage(message);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToastMessage(null), 2800);
  }, []);

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
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const ctx = React.useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
