"use client";

import * as React from "react";
import { api } from "@/lib/api";
import {
  applyOwnershipDiff,
  computeFinanceSummary,
  fromTenths,
  toTenths,
  type FinanceSummary,
} from "@/lib/finance";
import type {
  ManagerLineup,
  OwnedPrice,
  PlatformSnapshot,
  PlayerRecord,
  SquadFinance,
  SquadResult,
  StoredSquad,
} from "@/lib/types";
import { SQUAD_STORAGE_KEY } from "@/lib/storage-keys";

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
  // "reset" treats the result as a brand-new squad bought fresh against a
  // full £100.0m budget (auto-pick). "lineup" reorders/recaptains the same
  // 15 and must not touch bank or purchase prices (lineup optimise).
  // "transfer" diffs the composition change against the owned squad's
  // finance block, crediting selling proceeds and charging purchase prices
  // (an applied transfer-plan row). Defaults to "transfer", the safest
  // assumption when composition may have changed.
  setTeamResult: (result: SquadResult | null, mode?: "reset" | "lineup" | "transfer", bankTenthsOverride?: number) => void;
  setImportedTeam: (lineup: ManagerLineup) => boolean;
  storedSquad: StoredSquad | null;
  // Bank + market/selling value for the current squad, computed once here so
  // My Team and Transfer Studio never derive it independently.
  financeSummary: FinanceSummary;

  selectedPlayer: PlayerRecord | null;
  openProfile: (player: PlayerRecord) => void;
  closeProfile: () => void;

  toastMessage: string | null;
  toast: (message: string) => void;
  dismissToast: () => void;
}

const AppContext = React.createContext<AppState | null>(null);

function isValidFinance(value: unknown): value is SquadFinance {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  if (v.version !== 2) return false;
  if (typeof v.bankTenths !== "number" || !Number.isFinite(v.bankTenths)) return false;
  if (v.priceBasis !== "imported" && v.priceBasis !== "manual" && v.priceBasis !== "estimated") return false;
  if (typeof v.ownedPrices !== "object" || v.ownedPrices === null) return false;
  return Object.values(v.ownedPrices as Record<string, unknown>).every(
    (entry) =>
      typeof entry === "object" &&
      entry !== null &&
      typeof (entry as Record<string, unknown>).purchaseTenths === "number",
  );
}

interface ParsedSquad {
  squad: StoredSquad | null;
  financeWasInvalid: boolean;
}

function parseStoredSquad(): ParsedSquad {
  if (typeof window === "undefined") return { squad: null, financeWasInvalid: false };
  try {
    const raw = window.localStorage.getItem(SQUAD_STORAGE_KEY);
    if (!raw) return { squad: null, financeWasInvalid: false };
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      // Legacy format: array of strings
      return { squad: { ids: [], season: undefined }, financeWasInvalid: false };
    }
    if (!isStoredSquad(parsed)) return { squad: null, financeWasInvalid: false };
    const rawFinance = parsed.finance;
    if (rawFinance === undefined) return { squad: parsed, financeWasInvalid: false };
    if (isValidFinance(rawFinance)) return { squad: { ...parsed, finance: rawFinance }, financeWasInvalid: false };
    // Corrupt finance block: keep the squad's ids/lineup, drop the bad
    // finance data rather than losing the whole saved squad over it.
    return { squad: { ...parsed, finance: undefined }, financeWasInvalid: true };
  } catch {
    return { squad: null, financeWasInvalid: false };
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

  const persistSquad = React.useCallback((data: StoredSquad) => {
    window.localStorage.setItem(SQUAD_STORAGE_KEY, JSON.stringify(data));
    setStoredSquad(data);
  }, []);

  const fetchSnapshot = React.useCallback(() => {
    return api.platform().then((data) => {
      setSnapshot(data);
      const playerById = new Map(data.players.map((p) => [p.element, p]));
      const playerByName = new Map(data.players.map((p) => [p.name, p]));

      const { squad: parsedStored, financeWasInvalid } = parseStoredSquad();
      let stored = parsedStored;
      if (stored?.finance?.priceBasis === "imported") {
        const missingPriceIds = stored.ids.filter((id) => {
          const purchaseTenths = stored?.finance?.ownedPrices[id]?.purchaseTenths;
          return purchaseTenths === undefined || purchaseTenths <= 0;
        });
        if (missingPriceIds.length > 0 && stored.finance) {
          const ownedPrices = { ...stored.finance.ownedPrices };
          for (const id of missingPriceIds) {
            const player = playerById.get(id);
            if (player) {
              const currentTenths = toTenths(player.value_m);
              ownedPrices[id] = { purchaseTenths: currentTenths, sellingTenths: currentTenths };
            }
          }
          stored = {
            ...stored,
            finance: { ...stored.finance, ownedPrices, priceBasis: "estimated" },
          };
          persistSquad(stored);
          toast("Saved FPL purchase prices were missing; current market values are being used as estimates.");
        } else {
          setStoredSquad(stored);
        }
      } else {
        setStoredSquad(stored);
      }
      const legacyNames = parseLegacyNames();

      if (financeWasInvalid) {
        toast("Saved squad finance data was invalid; prices are shown as estimates.");
      }

      if (stored && stored.ids.length > 0) {
        if (stored.season && stored.season !== data.season) {
          window.localStorage.removeItem(SQUAD_STORAGE_KEY);
          setStoredSquad(null);
          setSquadElementsState([]);
          setTeamResultState(null);
          toast(`New season (${data.season}) — please rebuild your squad.`);
          return;
        }

        if (new Set(stored.ids).size !== stored.ids.length) {
          toast("Saved squad had duplicate players; please re-save your squad.");
        }

        const validPlayers = stored.ids
          .map((id) => playerById.get(id))
          .filter((p): p is PlayerRecord => p != null);

        setSquadElementsState(validPlayers.map((p) => p.element));

        if (validPlayers.length !== stored.ids.length) {
          const missing = stored.ids.length - validPlayers.length;
          toast(
            `${missing} player${missing === 1 ? "" : "s"} from your saved squad ${missing === 1 ? "is" : "are"} missing from this season's data.`,
          );
        }

        const totalValue = validPlayers.reduce((sum, p) => sum + p.value_m, 0);

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
        const { finance } = applyOwnershipDiff(null, [], migrated, playerById, { priceBasis: "estimated" });
        persistSquad({
          season: data.season,
          ids: migrated,
          bank: fromTenths(finance.bankTenths),
          source: "manual",
          finance,
        });
      }
    });
  }, [persistSquad, toast]);

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

  // A manual squad-editor save: diffs against whatever was owned before (if
  // anything) so a save that only swaps a couple of players still charges
  // and credits real purchase/selling prices instead of resetting the bank.
  const setSquadElements = React.useCallback(
    (elements: number[]) => {
      setSquadElementsState(elements);
      setTeamResultState(null);
      if (!snapshot) return;
      const byId = new Map(snapshot.players.map((p) => [p.element, p]));
      const { finance } = applyOwnershipDiff(
        storedSquad?.finance ?? null,
        squadElements,
        elements,
        byId,
        { priceBasis: "manual" },
      );
      persistSquad({
        season: snapshot.season,
        ids: elements,
        bank: fromTenths(finance.bankTenths),
        source: "manual",
        finance,
      });
    },
    [snapshot, squadElements, storedSquad, persistSquad],
  );

  const setTeamResult = React.useCallback(
    (result: SquadResult | null, mode: "reset" | "lineup" | "transfer" = "transfer", bankTenthsOverride?: number) => {
      const normalized = result ? normalizeSquadResult(result, snapshot) : null;
      setTeamResultState(normalized);
      if (!normalized || !snapshot) return;

      const ids = normalized.xi.map((p) => p.element).concat(normalized.bench.map((p) => p.element));
      setSquadElementsState(ids);

      const base: StoredSquad = {
        season: snapshot.season,
        ids,
        formation: normalized.formation,
        captainId: normalized.captain?.element,
        viceCaptainId: normalized.vice_captain?.element,
        xiIds: normalized.xi.map((player) => player.element),
        benchIds: normalized.bench.map((player) => player.element),
        source: "optimizer",
      };

      if (mode === "lineup") {
        // Same 15 players, only XI/bench/captain changed -- finance is untouched.
        const finance = storedSquad?.finance;
        persistSquad({
          ...base,
          bank: finance ? fromTenths(finance.bankTenths) : (storedSquad?.bank ?? 100 - normalized.spend),
          finance,
        });
        return;
      }

      const byId = new Map(snapshot.players.map((p) => [p.element, p]));
      const prevFinance = mode === "reset" ? null : (storedSquad?.finance ?? null);
      const { finance: computedFinance } = applyOwnershipDiff(
        prevFinance,
        squadElements,
        ids,
        byId,
        { priceBasis: "manual" },
      );
      const finance = mode === "transfer" && bankTenthsOverride !== undefined
        ? { ...computedFinance, bankTenths: bankTenthsOverride }
        : computedFinance;
      persistSquad({ ...base, bank: fromTenths(finance.bankTenths), finance });
    },
    [snapshot, squadElements, storedSquad, persistSquad],
  );

  const setImportedTeam = React.useCallback(
    (lineup: ManagerLineup) => {
      if (!snapshot || lineup.missing_elements.length > 0 || lineup.picks.length !== 15) return false;
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

      // Some public picks responses omit account prices. Preserve actual prices
      // when all are present; otherwise price affected players at current market
      // value and label the squad estimate instead of recording £0.0m ownership.
      let hasCompleteAccountPrices = lineup.bank !== null;
      const ownedPrices: Record<number, OwnedPrice> = {};
      for (const pick of lineup.picks) {
        const player = byElement.get(pick.element);
        const validPrices = pick.purchase_price !== null && pick.purchase_price > 0 &&
          pick.selling_price !== null && pick.selling_price > 0 && player !== undefined;
        hasCompleteAccountPrices &&= validPrices;
        const currentTenths = player ? toTenths(player.value_m) : 0;
        ownedPrices[pick.element] = {
          purchaseTenths: pick.purchase_price !== null && pick.purchase_price > 0 ? toTenths(pick.purchase_price) : currentTenths,
          sellingTenths: pick.selling_price !== null && pick.selling_price > 0 ? toTenths(pick.selling_price) : currentTenths,
        };
      }
      const finance: SquadFinance = {
        version: 2,
        bankTenths: toTenths(lineup.bank ?? 0),
        ownedPrices,
        priceBasis: hasCompleteAccountPrices ? "imported" : "estimated",
        marketPriceAsOf: lineup.fetched_at,
        lineupGameweek: lineup.lineup_gameweek,
      };
      if (!hasCompleteAccountPrices) {
        toast("FPL did not provide purchase prices for every player; transfer prices are estimated from current market values.");
      }

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
        finance,
      };
      persistSquad(data);
      setSquadElementsState(data.ids);
      setTeamResultState(result);
      return true;
    },
    [snapshot, persistSquad],
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

  const financeSummary = React.useMemo(
    () => computeFinanceSummary(squadPlayers, storedSquad?.finance ?? null),
    [squadPlayers, storedSquad],
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
    financeSummary,
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
