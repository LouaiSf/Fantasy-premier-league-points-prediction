import type {
  ApiError,
  ChipInventory,
  ChipsResult,
  ManagerLineup,
  ManagerSearchCandidate,
  PlatformSnapshot,
  PlayerHistoryRecord,
  SquadResult,
  TransferResult,
  WatchlistResult,
} from "./types";

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

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  const payload = (await response.json().catch(() => ({
    ok: false,
    error: "The server returned an unreadable response.",
  }))) as T | ApiError;
  if (!response.ok || (payload as ApiError).ok === false) {
    throw new Error((payload as ApiError).error || `Request failed with status ${response.status}.`);
  }
  return payload as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
  transfers: (body: { squad: string[]; free?: number; bank?: number; max?: number }) =>
    postJson<TransferResult>("/api/transfers", body),
  watchlist: (maxOwnership = 10, top = 12) =>
    requestJson<WatchlistResult>(
      `/api/watchlist?max_ownership=${maxOwnership}&top=${top}`,
    ),
  chips: (body: {
    squad?: string[];
    horizon?: number;
    chip_inventory?: ChipInventory;
    scheduled_gameweeks?: number[];
    last_free_hit_gameweek?: number | null;
  }) =>
    postJson<ChipsResult>("/api/chips", body),
};

