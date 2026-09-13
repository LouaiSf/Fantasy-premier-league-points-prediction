import type {
  ApiError,
  PlatformSnapshot,
  SquadResult,
  TransferResult,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:5000";

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
  platform: () => requestJson<PlatformSnapshot>("/api/platform"),
  squad: (body: { budget: number; lock?: string[]; ban?: string[] }) =>
    postJson<SquadResult>("/api/squad", body),
  transfers: (body: { squad: string[]; free?: number; bank?: number; max?: number }) =>
    postJson<TransferResult>("/api/transfers", body),
};
