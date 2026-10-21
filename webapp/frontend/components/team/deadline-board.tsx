"use client";

import * as React from "react";
import Link from "next/link";
import { useApp } from "@/components/providers/app-provider";
import { fromTenths } from "@/lib/finance";
import { money } from "@/lib/format";
import { Icon } from "@/components/icons";
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
    ? { key: "squad", label: "Squad", state: "ready", detail: "All 15 picked.", href: "/team", action: "Open" }
    : { key: "squad", label: "Squad", state: "missing", detail: `${squadPlayers.length} of 15 picked. Bring in your FPL team or build one.`, href: "/team", action: "Set up" });

  if (!hasSquad) {
    rows.push({ key: "captain", label: "Captain", state: "missing", detail: "Pick all 15 first.", href: "/captain", action: "Open" });
  } else if (!captain) {
    rows.push({ key: "captain", label: "Captain", state: "missing", detail: "Nobody has the armband yet.", href: "/captain", action: "Choose" });
  } else if (flagged.some((player) => player.element === captain.element)) {
    rows.push({ key: "captain", label: "Captain", state: "review", detail: `${captain.web_name || captain.name} has an availability flag.`, href: "/captain", action: "Review" });
  } else {
    rows.push({ key: "captain", label: "Captain", state: "ready", detail: `${captain.web_name || captain.name} has the armband.`, href: "/captain", action: "Open" });
  }

  if (facts.held) {
    rows.push({ key: "transfers", label: "Transfers", state: "ready", detail: "Holding this week.", href: "/transfers", action: "Open" });
  } else if (facts.savedMoves) {
    rows.push({ key: "transfers", label: "Transfers", state: "review", detail: `A saved plan with ${facts.savedMoves} move${facts.savedMoves === 1 ? "" : "s"} is not applied to My Team.`, href: "/transfers", action: "Review" });
  } else {
    rows.push({ key: "transfers", label: "Transfers", state: "missing", detail: "Make a move, or decide to hold.", href: "/transfers", action: "Plan" });
  }

  if (facts.plannedThisWeek) {
    rows.push({ key: "chips", label: "Chips", state: "ready", detail: `${facts.plannedThisWeek} planned for GW${gameweek}.`, href: "/chips", action: "Open" });
  } else if (facts.inventoryEntered) {
    rows.push({ key: "chips", label: "Chips", state: "ready", detail: "None planned this week.", href: "/chips", action: "Open" });
  } else {
    rows.push({ key: "chips", label: "Chips", state: "missing", detail: "Tell us which chips you have left.", href: "/chips", action: "Enter" });
  }

  rows.push(!hasSquad
    ? { key: "money", label: "Money", state: "missing", detail: "Pick all 15 first.", href: "/team", action: "Open" }
    : financeSummary.priceBasis === "imported"
      ? { key: "money", label: "Money", state: "ready", detail: `${money(fromTenths(financeSummary.bankTenths))} in the bank.`, href: "/team", action: "Open" }
      : { key: "money", label: "Money", state: "review", detail: `${money(fromTenths(financeSummary.bankTenths))} in the bank; sale prices are estimates.`, href: "/team", action: "Review" });

  rows.push(!hasSquad
    ? { key: "alerts", label: "Availability", state: "missing", detail: "Pick all 15 first.", href: "/news", action: "Open" }
    : flagged.length
      ? { key: "alerts", label: "Availability", state: "review", detail: `${flagged.length} of your 15 flagged: ${flagged.slice(0, 3).map((player) => player.web_name || player.name).join(", ")}${flagged.length > 3 ? "…" : ""}.`, href: "/news", action: "Review" }
      : { key: "alerts", label: "Availability", state: "ready", detail: "Everyone is fit.", href: "/news", action: "Open" });

  rows.push(!snapshot.prediction_available
    ? { key: "data", label: "Latest data", state: "review", detail: "Projections aren't ready yet.", href: "/team", action: "Open" }
    : staleData
      ? { key: "data", label: "Latest data", state: "review", detail: "Prices are over a day old. Get the latest before you decide.", href: "/team", action: "Open" }
      : { key: "data", label: "Latest data", state: "ready", detail: "Prices and projections are current.", href: "/team", action: "Open" });

  const open = rows.filter((row) => row.state !== "ready").length;

  return (
    <section className="panel deadline-board" aria-label={`Gameweek ${gameweek ?? ""} checklist`}>
      <div className="panel-head">
        <div>
          <h2>Before the deadline</h2>
          <p role="status">{open === 0 ? "You're all set." : `${open} thing${open === 1 ? "" : "s"} still to sort.`}</p>
        </div>
      </div>
      <ul className="checklist stagger">
        {rows.map((row, index) => (
          <li key={row.key} className={`check is-${row.state}`} style={{ "--i": index } as React.CSSProperties}>
            <span className="check-mark" aria-hidden="true">
              {row.state === "ready" ? <Icon name="check" size={16} /> : row.state === "review" ? <Icon name="alert" size={16} /> : null}
            </span>
            <span className="check-copy">
              <b>{row.label}</b>
              <span>{row.detail}</span>
              <span className="sr-only">{STATE_LABELS[row.state]}</span>
            </span>
            <Link className="check-go" href={row.href} aria-label={`${row.action}: ${row.label}`}>
              {row.action}
              <Icon name="chevron-right" size={16} />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
