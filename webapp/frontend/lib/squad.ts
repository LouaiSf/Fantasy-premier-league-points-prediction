import type { PlayerRecord } from "./types";

export const SQUAD_SHAPE = { GK: 2, DEF: 5, MID: 5, FWD: 3 } as const;

export function playerScore(player: PlayerRecord): number {
  return Number(player.predicted_points ?? player.form ?? 0);
}

export interface PreviewSquad {
  xi: PlayerRecord[];
  bench: PlayerRecord[];
  captain: PlayerRecord | null;
  vice_captain: PlayerRecord | null;
  formation: string;
  xiPoints: number;
  spend: number;
}

// Client-side best-guess XI from a saved 15, used until the optimiser (which
// factors in the real prediction model) has been run via /api/squad.
export function previewSquad(players: PlayerRecord[]): PreviewSquad | null {
  if (players.length !== 15) return null;
  const sorted = [...players].sort((a, b) => playerScore(b) - playerScore(a));
  const minimums: Record<string, number> = { GK: 1, DEF: 3, MID: 2, FWD: 1 };
  const xi: PlayerRecord[] = [];
  for (const [position, count] of Object.entries(minimums)) {
    xi.push(...sorted.filter((player) => player.position === position).slice(0, count));
  }
  for (const player of sorted) {
    if (xi.length >= 11) break;
    if (!xi.includes(player) && player.position !== "GK") xi.push(player);
  }
  const benchPool = sorted.filter((player) => !xi.includes(player));
  const bench = [
    ...benchPool.filter((player) => player.position !== "GK"),
    ...benchPool.filter((player) => player.position === "GK"),
  ];
  const armbandOrder = xi
    .filter((player) => player.position !== "GK")
    .sort((a, b) => playerScore(b) - playerScore(a));
  const formation = (["DEF", "MID", "FWD"] as const)
    .map((position) => xi.filter((player) => player.position === position).length)
    .join("-");
  return {
    xi,
    bench,
    captain: armbandOrder[0] ?? null,
    vice_captain: armbandOrder[1] ?? null,
    formation,
    xiPoints: xi.reduce((total, player) => total + playerScore(player), 0),
    spend: players.reduce((total, player) => total + Number(player.value_m), 0),
  };
}

export function validateSquad(selected: PlayerRecord[]): string {
  if (selected.length !== 15) return `Choose exactly 15 players. ${selected.length} selected.`;
  for (const [position, required] of Object.entries(SQUAD_SHAPE)) {
    if (selected.filter((player) => player.position === position).length !== required) {
      return "Squad shape must be 2 GK, 5 DEF, 5 MID and 3 FWD.";
    }
  }
  const clubCounts = new Map<string, number>();
  for (const player of selected) {
    clubCounts.set(player.team, (clubCounts.get(player.team) ?? 0) + 1);
  }
  if ([...clubCounts.values()].some((count) => count > 3)) {
    return "A squad can contain no more than three players from one club.";
  }
  return "";
}
