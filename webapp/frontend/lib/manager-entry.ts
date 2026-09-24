export type ManagerEntryInput =
  | { readonly kind: "entry"; readonly entryId: number }
  | { readonly kind: "name"; readonly query: string }
  | { readonly kind: "invalid"; readonly message: string };

export interface RecentManager {
  readonly season: string;
  readonly entry_id: number;
  readonly manager_name: string;
  readonly team_name: string;
  readonly imported_at: string;
}

const recentManagerLimit = 5;

function looksLikeUrl(value: string): boolean {
  return (
    /^[a-z][a-z\d+.-]*:/i.test(value) ||
    /^(?:www\.)?[^/\s]+\.[a-z]{2,}(?:[/:?#]|$)/i.test(value)
  );
}

export function parseManagerEntryInput(rawValue: string): ManagerEntryInput {
  const value = rawValue.trim();
  if (!value) {
    return { kind: "invalid", message: "Enter an FPL entry ID, team link, or manager name." };
  }

  if (/^-?\d+$/.test(value)) {
    const entryId = Number(value);
    if (!Number.isSafeInteger(entryId) || entryId <= 0) {
      return { kind: "invalid", message: "Enter a positive FPL entry ID." };
    }
    return { kind: "entry", entryId };
  }

  if (looksLikeUrl(value)) {
    let url: URL;
    try {
      url = new URL(value);
    } catch (error) {
      if (error instanceof TypeError) {
        return { kind: "invalid", message: "Paste a complete FPL team link." };
      }
      throw error;
    }
    const segments = url.pathname.split("/").filter(Boolean);
    const entryId = segments[1] ? Number(segments[1]) : Number.NaN;
    if (
      url.protocol !== "https:" ||
      url.hostname !== "fantasy.premierleague.com" ||
      url.port !== "" ||
      url.username !== "" ||
      url.password !== "" ||
      segments[0] !== "entry" ||
      !Number.isSafeInteger(entryId) ||
      entryId <= 0
    ) {
      return {
        kind: "invalid",
        message: "Use a team link from fantasy.premierleague.com/entry/<ID>.",
      };
    }
    return { kind: "entry", entryId };
  }

  return { kind: "name", query: value };
}

export function isRecentManager(value: unknown, season: string): value is RecentManager {
  if (typeof value !== "object" || value === null) return false;
  if (!("season" in value) || !("entry_id" in value) || !("manager_name" in value) ||
      !("team_name" in value) || !("imported_at" in value)) {
    return false;
  }
  return (
    value.season === season &&
    typeof value.entry_id === "number" &&
    Number.isSafeInteger(value.entry_id) &&
    value.entry_id > 0 &&
    typeof value.manager_name === "string" &&
    typeof value.team_name === "string" &&
    typeof value.imported_at === "string"
  );
}

export function upsertRecentManager(
  recent: readonly RecentManager[],
  manager: Omit<RecentManager, "imported_at">,
  importedAt: string,
): RecentManager[] {
  const next = [
    {
      ...manager,
      imported_at: importedAt,
    },
    ...recent.filter((item) => item.entry_id !== manager.entry_id),
  ];
  return next.slice(0, recentManagerLimit);
}
