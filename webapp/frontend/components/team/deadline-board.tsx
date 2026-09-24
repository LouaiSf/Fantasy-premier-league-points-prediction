"use client";

import * as React from "react";
import Link from "next/link";
import { useApp } from "@/components/providers/app-provider";
import { fromTenths } from "@/lib/finance";
import { money } from "@/lib/format";
import { CHIP_INVENTORY_KEY } from "@/lib/storage-keys";
import {
  heldWeekKey, isHeldWeek, isSavedTransferDraft, squadFingerprint, transferDraftKey,
} from "@/lib/transfer-planning";

type RowState = "ready" | "review" | "missing";

interface BoardRow {
  key: string;
  label: string;
  state: RowState;
  detail: string;
  href: string;
  action: string;
}

const STATE_LABELS: Record<RowState, string> = {
  ready: "Ready",
  review: "Needs review",
  missing: "Missing input",
};

// Local-only facts the board cannot get from the snapshot. Each is read once
// per season/squad change and tolerates storage being blocked or corrupt.
interface LocalFacts {
  held: boolean;
  savedMoves: number | null;
  inventoryEntered: boolean;
  plannedThisWeek: string | null;
}

const CHIP_NAMES: Record<string, string> = {
  triple_captain: "Triple Captain",
  bench_boost: "Bench Boost",
  free_hit: "Free Hit",
  wildcard: "Wildcard",
};

function readJson(key: string): unknown {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function readLocalFacts(season: string, gameweek: number | null, fingerprint: string): LocalFacts {
  const hold = readJson(heldWeekKey(season));
  const draft = readJson(transferDraftKey(season));
  const chips = readJson(CHIP_INVENTORY_KEY);
  const chipRecord = typeof chips === "object" && chips !== null ? chips as Record<string, unknown> : null;
  const seasonMatches = chipRecord?.season === season;
  const planned = seasonMatches && Array.isArray(chipRecord?.plannedChips)
    ? (chipRecord.plannedChips as Array<Record<string, unknown>>).find((entry) => entry.gw === gameweek)
    : undefined;
  return {
    held: isHeldWeek(hold) && hold.season === season && hold.gameweek === gameweek &&
      hold.fingerprint === fingerprint,
    savedMoves: isSavedTransferDraft(draft) && draft.season === season && draft.fingerprint === fingerprint
      ? draft.pairs.length
      : null,
    inventoryEntered: seasonMatches && Boolean(chipRecord?.first_half || chipRecord?.second_half),
    plannedThisWeek: typeof planned?.chip === "string" ? CHIP_NAMES[planned.chip] ?? planned.chip : null,
  };
}

export function DeadlineBoard() {
  const { snapshot, squadPlayers, squadElements, storedSquad, financeSummary } = useApp();
  const [facts, setFacts] = React.useState<LocalFacts | null>(null);
  const season = snapshot?.season ?? null;
  const gameweek = snapshot?.gameweek ?? null;
  const fingerprint = season ? squadFingerprint(season, squadElements, storedSquad?.finance ?? null) : "";

  React.useEffect(() => {
    if (!season) return;
    setFacts(readLocalFacts(season, gameweek, fingerprint));
  }, [season, gameweek, fingerprint]);

  if (!snapshot || !facts) return null;

  const hasSquad = squadPlayers.length === 15;
  const captain = storedSquad?.captainId
    ? squadPlayers.find((player) => player.element === storedSquad.captainId)
    : undefined;
  const flagged = squadPlayers.filter(
    (player) => player.status !== "a" || (player.chance_of_playing_next_round ?? 100) < 100,
  );
  const updatedAt = snapshot.market_prices_updated_at ? new Date(snapshot.market_prices_updated_at) : null;
  const staleData = updatedAt !== null && Date.now() - updatedAt.getTime() > 24 * 60 * 60 * 1000;

  const rows: BoardRow[] = [];
  rows.push(hasSquad
    ? { key: "squad", label: "Squad", state: "ready", detail: "15 players saved on this device.", href: "/team", action: "Open" }
    : { key: "squad", label: "Squad", state: "missing", detail: `${squadPlayers.length} of 15 players. Import your team or build one.`, href: "/team", action: "Set up" });

  if (!hasSquad) {
    rows.push({ key: "captain", label: "Captain", state: "missing", detail: "Needs a complete squad.", href: "/captain", action: "Open" });
  } else if (!captain) {
    rows.push({ key: "captain", label: "Captain", state: "missing", detail: "No captain is set for this squad.", href: "/captain", action: "Choose" });
  } else if (flagged.some((player) => player.element === captain.element)) {
    rows.push({ key: "captain", label: "Captain", state: "review", detail: `${captain.web_name || captain.name} has an availability flag.`, href: "/captain", action: "Review" });
  } else {
    rows.push({ key: "captain", label: "Captain", state: "ready", detail: `${captain.web_name || captain.name}, no official availability doubt.`, href: "/captain", action: "Open" });
  }

  if (facts.held) {
    rows.push({ key: "transfers", label: "Transfers", state: "ready", detail: `Holding GW${gameweek} on this device.`, href: "/transfers", action: "Open" });
  } else if (facts.savedMoves) {
    rows.push({ key: "transfers", label: "Transfers", state: "review", detail: `A saved plan with ${facts.savedMoves} move${facts.savedMoves === 1 ? "" : "s"} is not applied to My Team.`, href: "/transfers", action: "Review" });
  } else {
    rows.push({ key: "transfers", label: "Transfers", state: "missing", detail: "No hold or saved plan recorded for this gameweek.", href: "/transfers", action: "Plan" });
  }

  if (facts.plannedThisWeek) {
    rows.push({ key: "chips", label: "Chips", state: "ready", detail: `${facts.plannedThisWeek} planned for GW${gameweek}.`, href: "/chips", action: "Open" });
  } else if (facts.inventoryEntered) {
    rows.push({ key: "chips", label: "Chips", state: "ready", detail: "Chips entered; none planned this week.", href: "/chips", action: "Open" });
  } else {
    rows.push({ key: "chips", label: "Chips", state: "missing", detail: "You have not entered which chips you still have.", href: "/chips", action: "Enter" });
  }

  rows.push(!hasSquad
    ? { key: "money", label: "Bank and prices", state: "missing", detail: "Needs a complete squad.", href: "/team", action: "Open" }
    : financeSummary.priceBasis === "imported"
      ? { key: "money", label: "Bank and prices", state: "ready", detail: `Bank ${money(fromTenths(financeSummary.bankTenths))}, official purchase prices.`, href: "/team", action: "Open" }
      : { key: "money", label: "Bank and prices", state: "review", detail: `Bank ${money(fromTenths(financeSummary.bankTenths))}; selling prices are ${financeSummary.priceBasis}, not official.`, href: "/team", action: "Review" });

  rows.push(!hasSquad
    ? { key: "alerts", label: "Availability", state: "missing", detail: "Needs a complete squad.", href: "/news", action: "Open" }
    : flagged.length
      ? { key: "alerts", label: "Availability", state: "review", detail: `${flagged.length} of your 15 flagged: ${flagged.slice(0, 3).map((player) => player.web_name || player.name).join(", ")}${flagged.length > 3 ? "…" : ""}.`, href: "/news", action: "Review" }
      : { key: "alerts", label: "Availability", state: "ready", detail: "No official availability flags in your 15.", href: "/news", action: "Open" });

  rows.push(!snapshot.prediction_available
    ? { key: "data", label: "Data", state: "review", detail: "Predictions are unavailable for this snapshot.", href: "/team", action: "Open" }
    : staleData
      ? { key: "data", label: "Data", state: "review", detail: `Market prices last updated ${updatedAt?.toLocaleString()}; refresh before deciding.`, href: "/team", action: "Open" }
      : { key: "data", label: "Data", state: "ready", detail: `Predictions ready${updatedAt ? `; prices updated ${updatedAt.toLocaleString()}` : ""}.`, href: "/team", action: "Open" });

  const open = rows.filter((row) => row.state !== "ready").length;

  return (
    <div className="shell">
      <section className="deadline-board" aria-label={`GW${gameweek ?? ""} deadline board`}>
        <div className="deadline-board-head">
          <div>
            <span className="kicker">Deadline board</span>
            <h2>GW{gameweek ?? "--"} checklist</h2>
          </div>
          <p role="status">{open === 0 ? "Everything listed is ready." : `${open} item${open === 1 ? "" : "s"} still open.`}</p>
        </div>
        <ul className="deadline-list">
          {rows.map((row) => (
            <li key={row.key} className={`deadline-row is-${row.state}`}>
              <span className="deadline-state">
                <span aria-hidden="true">{row.state === "ready" ? "✓" : row.state === "review" ? "!" : "–"}</span>
                {STATE_LABELS[row.state]}
              </span>
              <div>
                <b>{row.label}</b>
                <span>{row.detail}</span>
              </div>
              <Link className="text-button" href={row.href}>{row.action}</Link>
            </li>
          ))}
        </ul>
        <p className="deadline-note">Based on what is saved on this device. It is not checked against your FPL account.</p>
      </section>
    </div>
  );
}
