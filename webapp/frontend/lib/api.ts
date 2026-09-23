import type {
  ApiError,
  ChipInventory,
  LeagueStandingsResult,
  ManagerLineup,
  ManagerSearchCandidate,
  PlatformSnapshot,
  PlayerHistoryRecord,
  SquadResult,
  TransferResult,
  WatchlistResult,
} from "./types";
import { parseChipsResult } from "./chips-contract";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:5000";

if (
  typeof window !== "undefined" &&
  !process.env.NEXT_PUBLIC_API_BASE &&
  window.location.hostname !== "localhost" &&
  window.location.hostname !== "127.0.0.1"
) {
  console.warn(
    "NEXT_PUBLIC_API_BASE is not configured. API requests will default to http://127.0.0.1:5000.",
  );
}

// Carries the backend's machine-readable `code` (e.g. "search_not_configured")
// alongside the human-readable message, so a caller can branch on the
// specific failure instead of pattern-matching text meant for display.
export class ApiRequestError extends Error {
  readonly code?: string;
  constructor(message: string, code?: string) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
  }
}

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  const payload = (await response.json().catch(() => ({
    ok: false,
    error: "The server returned an unreadable response.",
  }))) as T | ApiError;
  if (!response.ok || (payload as ApiError).ok === false) {
    const apiError = payload as ApiError;
    throw new ApiRequestError(
      apiError.error || `Request failed with status ${response.status}.`,
      apiError.code,
    );
  }
  return payload as T;
}

function postJson<T>(
  path: string,
  body: unknown,
  headers: Record<string, string> = {},
): Promise<T> {
  return requestJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

// The refresh endpoints need a bearer token when the server has REFRESH_TOKEN
// set. It is asked for once and kept for the tab's session only: a token baked
// into the frontend bundle would be public, which defeats the point of it.
const REFRESH_TOKEN_KEY = "fpl-refresh-token";

function refreshAuthHeaders(): Record<string, string> {
  try {
    const token = window.sessionStorage.getItem(REFRESH_TOKEN_KEY);
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

async function withRefreshAuth<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (err) {
    if (
      !(err instanceof ApiRequestError) ||
      err.code !== "refresh_auth_required" ||
      typeof window === "undefined"
    ) {
      throw err;
    }
    const token = window.prompt("This server requires a refresh token. Enter it to continue:");
    if (!token?.trim()) throw err;
    try {
      window.sessionStorage.setItem(REFRESH_TOKEN_KEY, token.trim());
    } catch {
      /* storage blocked: the token is used for this attempt only */
    }
    return call();
  }
}

export interface PredictionRefreshJob {
  state: "idle" | "running" | "succeeded" | "failed";
  step?: string | null;
  error?: string | null;
  failed_step?: string;
  report?: {
    first_gw: number;
    last_gw: number;
    players: number;
    warnings: string[];
  };
}

const PREDICTION_POLL_MS = 3000;
const PREDICTION_TIMEOUT_MS = 35 * 60 * 1000;

/**
 * Refresh the season data, then regenerate predictions from it.
 *
 * /api/refresh only moves the raw data; the predictions stay as they were until
 * the backend pipeline validates and swaps in a new export, which takes
 * minutes. This starts that job and waits for it, so callers can tell the
 * person what actually happened instead of reporting success on stale numbers.
 */
export async function refreshDataAndPredictions(
  onStep?: (step: string) => void,
): Promise<string> {
  const data = await withRefreshAuth(() => api.refresh());
  if (!data.predictions_stale) return data.message;

  onStep?.("predicting");
  try {
    await withRefreshAuth(() => api.startPredictionRefresh({ fetch: false }));
  } catch (err) {
    // 409: someone else already started it; just wait on that run.
    if (!(err instanceof ApiRequestError) || !/already running/i.test(err.message)) throw err;
  }
  const deadline = Date.now() + PREDICTION_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, PREDICTION_POLL_MS));
    const { job } = await api.predictionRefreshStatus();
    if (job.step) onStep?.(job.step);
    if (job.state === "succeeded") {
      const report = job.report;
      const warning = report?.warnings?.[0];
      return (
        `Data and predictions refreshed (GW${report?.first_gw}–GW${report?.last_gw}).` +
        (warning ? ` ${warning}` : "")
      );
    }
    if (job.state === "failed") {
      throw new Error(
        `${job.error ?? "Prediction refresh failed."} Previous predictions are unchanged.`,
      );
    }
  }
  throw new Error("Prediction refresh is still running; check back shortly.");
}

export const api = {
  searchManagers: (query: string) =>
    requestJson<{ ok: true; query: string; results: ManagerSearchCandidate[] }>(
      `/api/managers/search?q=${encodeURIComponent(query)}`,
    ),
  managerLineup: (entryId: number, gameweek?: number) =>
    requestJson<ManagerLineup>(
      `/api/managers/${entryId}/lineup${gameweek ? `?gameweek=${gameweek}` : ""}`,
    ),
  leagueStandings: (leagueId: number, page = 1) =>
    requestJson<LeagueStandingsResult>(
      `/api/managers/leagues/${leagueId}/standings?page=${page}`,
    ),
  meta: () =>
    requestJson<{
      ok: boolean;
      season: string;
      gameweek: number;
      players: number;
      predictions_updated_at?: string | null;
      model: Record<string, unknown>;
    }>("/api/meta"),
  platform: () => requestJson<PlatformSnapshot>("/api/platform"),
  playerHistory: (elementId: number) =>
    requestJson<{ ok: boolean; history: PlayerHistoryRecord[] }>(
      `/api/player/${elementId}/history`,
    ),
  refresh: () =>
    postJson<{
      ok: boolean;
      message: string;
      season: string;
      gameweek: number;
      players: number;
    }>("/api/refresh", {}),
  squad: (body: { budget: number; lock?: string[]; ban?: string[] }) =>
    postJson<SquadResult>("/api/squad", body),
  lineup: (body: { elements: number[] }) =>
    postJson<SquadResult>("/api/lineup", body),
  transfers: (body: {
    elements: number[];
    free?: number;
    bank?: number;
    max?: number;
    selling_prices_tenths?: Record<number, number>;
  }) => postJson<TransferResult>("/api/transfers", body),
  watchlist: (maxOwnership = 10, top = 12) =>
    requestJson<WatchlistResult>(
      `/api/watchlist?max_ownership=${maxOwnership}&top=${top}`,
    ),
  chips: async (body: {
    squad?: string[];
    horizon?: number;
    chip_inventory?: ChipInventory;
    scheduled_gameweeks?: number[];
    last_free_hit_gameweek?: number | null;
    bank?: number;
    selling_prices_tenths?: Record<number, number>;
  }) => parseChipsResult(await postJson<unknown>("/api/chips", body)),
};

