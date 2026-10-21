"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { fromTenths, sellingPricesTenthsForSquad } from "@/lib/finance";
import { Skeleton } from "@/components/skeleton";
import { EmptyState } from "@/components/empty-state";
import { GateSign, PlateFact, Segmented, VerdictPlate } from "@/components/signage";
import { Icon } from "@/components/icons";
import { ChipIcon } from "@/components/chips/chip-icon";
import { ChipOpportunityMatrix } from "@/components/chips/chip-opportunity-matrix";
import { ChipPlanTimeline } from "@/components/chips/chip-plan-timeline";
import { BarStrip } from "@/components/charts/bar-strip";
import { m, AnimatePresence } from "motion/react";
import { CHIP_IDS, type ChipId, type ChipInventory, type ChipRecommendation, type ChipRow, type ChipsResult, type ChipState, type ChipStatus } from "@/lib/types";
import { CHIP_INVENTORY_KEY } from "@/lib/storage-keys";

// The last gameweek of each half-season set, per the official 2026/27 chip
// rules (two sets, split at the GW19 deadline).
const FIRST_HALF_LAST_GW = 19;
const SECOND_HALF_LAST_GW = 38;

const CHIP_LABELS: Record<ChipId, string> = {
  triple_captain: "Triple Captain",
  bench_boost: "Bench Boost",
  free_hit: "Free Hit",
  wildcard: "Wildcard",
};

const CHIP_DESCRIPTIONS: Record<ChipId, string> = {
  triple_captain: "Captain points are tripled instead of doubled.",
  bench_boost: "All four bench players count in the gameweek total.",
  free_hit: "Build a one-week squad, then return to the original team.",
  wildcard: "Make unlimited permanent transfers in the gameweek.",
};

const STATUS_LABELS: Record<ChipStatus, string> = {
  play_now: "Play now",
  planned: "Planned",
  hold: "Hold",
  unavailable: "Unavailable",
  no_squad: "Fixtures only",
};


const BAR_STRIP_MAX_WEEKS = 8;

// A small, meaningful window for the per-card BarStrip: the next few
// upcoming eligible weeks, plus the assigned ("best") and current ("now")
// weeks even if they'd otherwise fall outside that window.
function pickBarWeeks(candidates: number[], now: number, best: number | null): number[] {
  const upcoming = candidates.filter((gw) => gw >= now).sort((a, b) => a - b);
  let picked = upcoming.slice(0, BAR_STRIP_MAX_WEEKS);
  if (best != null && candidates.includes(best) && !picked.includes(best)) {
    picked = [...picked, best];
  }
  if (candidates.includes(now) && !picked.includes(now)) {
    picked = [...picked, now];
  }
  return Array.from(new Set(picked)).sort((a, b) => a - b);
}


function blankInventory(): ChipInventory {
  return {
    first_half: {
      triple_captain: "unused",
      bench_boost: "unused",
      free_hit: "unused",
      wildcard: "unused",
    },
    second_half: {
      triple_captain: "unused",
      bench_boost: "unused",
      free_hit: "unused",
      wildcard: "unused",
    },
  };
}

function inventoryStatusLabel(state: ChipState): string {
  if (state === "used") return "Used";
  if (state === "expired") return "Expired";
  return "Available";
}

// Stored state is only ever "unused" or "used" -- expiry isn't something a
// manager declares, it's a fact of the calendar. A first-half chip that was
// never used becomes "Expired" the moment GW19 passes, worked out fresh on
// every render rather than requiring a click to "mark it expired".
function effectiveChipState(
  stored: ChipState,
  half: "first_half" | "second_half",
  gameweek: number | null,
): ChipState {
  if (stored === "used") return "used";
  const boundary = half === "first_half" ? FIRST_HALF_LAST_GW : SECOND_HALF_LAST_GW;
  if (gameweek != null && gameweek > boundary) return "expired";
  return "unused";
}

function effectiveInventory(inventory: ChipInventory, gameweek: number | null): ChipInventory {
  const map = (half: "first_half" | "second_half") =>
    Object.fromEntries(
      CHIP_IDS.map((chip) => [chip, effectiveChipState(inventory[half][chip], half, gameweek)]),
    ) as ChipInventory["first_half"];
  return { first_half: map("first_half"), second_half: map("second_half") };
}

// A stale "expired" value from before expiry was calendar-derived is
// welcomed back as "unused" and re-evaluated against the current gameweek,
// rather than being permanently frozen from a previous session's clicking.
function normalizeStoredState(state: ChipState): ChipState {
  return state === "expired" ? "unused" : state;
}

function nextInventoryState(state: ChipState): ChipState {
  return state === "unused" ? "used" : "unused";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isChipState(value: unknown): value is ChipState {
  return value === "unused" || value === "used" || value === "expired";
}

function isInventoryHalf(value: unknown): value is ChipInventory["first_half"] {
  return isRecord(value) && CHIP_IDS.every((chip) => isChipState(value[chip]));
}

function normalizeInventoryHalf(half: ChipInventory["first_half"]): ChipInventory["first_half"] {
  return Object.fromEntries(
    CHIP_IDS.map((chip) => [chip, normalizeStoredState(half[chip])]),
  ) as ChipInventory["first_half"];
}

// Scoped to the season it was saved under: a chip "used" in 2025-26 says
// nothing about a manager's 2026-27 inventory, so a season mismatch is
// treated the same as no saved inventory at all rather than reused.
function readInventory(season: string): ChipInventory | null {
  if (typeof window === "undefined") return null;
  try {
    const stored = window.localStorage.getItem(CHIP_INVENTORY_KEY);
    if (!stored) return null;
    const parsed: unknown = JSON.parse(stored);
    if (!isRecord(parsed) || parsed.season !== season) return null;
    if (!isInventoryHalf(parsed.first_half) || !isInventoryHalf(parsed.second_half)) return null;
    return {
      first_half: normalizeInventoryHalf(parsed.first_half),
      second_half: normalizeInventoryHalf(parsed.second_half),
    };
  } catch {
    return null;
  }
}

type InventorySource = "fpl_sync" | "local_user_reported";

function readInventorySource(season: string): InventorySource | null {
  if (typeof window === "undefined") return null;
  try {
    const stored = window.localStorage.getItem(CHIP_INVENTORY_KEY);
    if (!stored) return null;
    const parsed: unknown = JSON.parse(stored);
    if (!isRecord(parsed) || parsed.season !== season) return null;
    return parsed.source === "fpl_sync" || parsed.source === "local_user_reported"
      ? parsed.source
      : null;
  } catch {
    return null;
  }
}

function readLastFreeHitGameweek(season: string): number | null {
  if (typeof window === "undefined") return null;
  try {
    const stored = window.localStorage.getItem(CHIP_INVENTORY_KEY);
    if (!stored) return null;
    const parsed: unknown = JSON.parse(stored);
    if (!isRecord(parsed) || parsed.season !== season) return null;
    const value = parsed.lastFreeHitGameweek;
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

interface PlannedChip {
  chip: ChipId;
  gw: number;
}

function isPlannedChip(value: unknown): value is PlannedChip {
  return (
    isRecord(value) &&
    (CHIP_IDS as readonly string[]).includes(value.chip as string) &&
    typeof value.gw === "number" &&
    Number.isFinite(value.gw)
  );
}

// A chip a manager has already committed to for a specific future
// gameweek -- the backend excludes that gameweek from every *other* chip's
// candidate window too, since only one chip can be played per week.
function readPlannedChips(season: string): PlannedChip[] {
  if (typeof window === "undefined") return [];
  try {
    const stored = window.localStorage.getItem(CHIP_INVENTORY_KEY);
    if (!stored) return [];
    const parsed: unknown = JSON.parse(stored);
    if (!isRecord(parsed) || parsed.season !== season) return [];
    const value = parsed.plannedChips;
    return Array.isArray(value) ? value.filter(isPlannedChip) : [];
  } catch {
    return [];
  }
}

function PlannedChipsPanel({
  plannedChips,
  maxGw,
  currentGw,
  onAdd,
  onRemove,
}: {
  plannedChips: PlannedChip[];
  maxGw: number;
  currentGw: number;
  onAdd: (chip: ChipId, gw: number) => void;
  onRemove: (chip: ChipId, gw: number) => void;
}) {
  const [chip, setChip] = React.useState<ChipId>(CHIP_IDS[0]);
  const [gwInput, setGwInput] = React.useState("");

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const gw = Number(gwInput);
    if (!Number.isInteger(gw) || gw < currentGw || gw > maxGw) return;
    onAdd(chip, gw);
    setGwInput("");
  }

  return (
    <div className="chip-planned">
      <h3>Chips you&apos;ve already planned</h3>
      <p className="note">
        Lock a chip to a week and the plan won&apos;t suggest another chip for that week. Only one chip can be played per gameweek.
      </p>
      {plannedChips.length > 0 && (
        <ul className="chip-planned-list">
          <AnimatePresence>
            {plannedChips.map((planned) => (
              <m.li
                key={`${planned.chip}-${planned.gw}`}
                layout="position"
                transition={{ layout: { duration: 0.32, ease: [0.22, 1, 0.36, 1] } }}
                exit={{ opacity: 0, x: -12 }}
              >
                <ChipIcon id={planned.chip} />
                <span>{CHIP_LABELS[planned.chip]} in gameweek {planned.gw}</span>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => onRemove(planned.chip, planned.gw)}
                  aria-label={`Remove planned ${CHIP_LABELS[planned.chip]} for GW${planned.gw}`}
                >
                  Remove
                </button>
              </m.li>
            ))}
          </AnimatePresence>
        </ul>
      )}
      <form className="chip-planned-form" onSubmit={submit}>
        <select className="select select--sm" value={chip} onChange={(event) => setChip(event.target.value as ChipId)}>
          {CHIP_IDS.map((id) => (
            <option key={id} value={id}>{CHIP_LABELS[id]}</option>
          ))}
        </select>
        <input
          className="input input--sm"
          aria-label="Gameweek"
          type="number"
          min={currentGw}
          max={maxGw}
          placeholder={`GW${currentGw}-${maxGw}`}
          value={gwInput}
          onChange={(event) => setGwInput(event.target.value)}
        />
        <button type="submit" className="btn btn--line btn--sm">Plan it</button>
      </form>
    </div>
  );
}

// The API states its reasons in decision-policy terms ("above the 5.0-point
// policy margin", "Best window GW7"). Rephrase them for a manager.
function humanReason(text: string | undefined): string {
  if (!text) return "";
  return text
    .replace(/,? ?above the [\d.]+-point (policy )?margin/gi, "")
    .replace(/\(?(below|under) the [\d.]+-point (policy )?margin\)?/gi, "not quite enough to play it yet")
    .replace(/Best window GW(\d+): \+?([\d.]+) points\.?/g, "Best in gameweek $1, worth about $2 extra points.")
    .replace(/\bGW(\d+)/g, "gameweek $1")
    .replace(/\s+\./g, ".")
    .trim();
}

function WhyThisChoice({ recommendation }: { recommendation: ChipRecommendation }) {
  const evidence = recommendation.evidence;
  return (
    <details className="why-more">
      <summary>
        Why <Icon name="chevron-down" size={16} />
      </summary>
      <div className="why-more-body">
        {evidence?.chip === "triple_captain" && (
          <p>
            {evidence.captain.name} ({evidence.captain.team}) is expected to score {num(evidence.captain.projected_points, 1)} points, so a third armband adds about that much.
          </p>
        )}
        {evidence?.chip === "bench_boost" && (
          <>
            <ul>
              {evidence.ordered_bench.map((player) => (
                <li key={player.element}>
                  {player.player}: {num(player.points, 1)} pts
                </li>
              ))}
            </ul>
            <p>
              Your bench is expected to score {num(evidence.bench_total, 1)}, minus about {num(evidence.expected_autosub_points, 1)} you&apos;d get anyway from normal substitutions.
            </p>
          </>
        )}
        {evidence?.chip === "free_hit" && (
          <p>
            A one-week team would score about {num(evidence.free_hit_total, 1)} points, against {num(evidence.no_chip_total, 1)} with your best normal transfer. It swaps {evidence.changed_player_count} player{evidence.changed_player_count === 1 ? "" : "s"}.
          </p>
        )}
        {evidence?.chip === "wildcard" && (
          <p>
            A rebuilt squad scores about {evidence.wildcard_total != null ? num(evidence.wildcard_total, 1) : "–"} points from gameweek {evidence.window_gameweeks[0]} to {evidence.window_gameweeks[evidence.window_gameweeks.length - 1]}, compared with making your usual free transfers. It changes {evidence.changed_player_count} players.
          </p>
        )}
        {recommendation.candidate_gameweeks.length > 0 && (
          <p className="note">
            Other weeks:{" "}
            {recommendation.candidate_gameweeks
              .slice(0, 10)
              .map((gw) => {
                const value = recommendation.gains_by_week[String(gw)];
                return `GW${gw} ${value != null ? "+" + num(value, 1) : "–"}`;
              })
              .join(" · ")}
            {recommendation.candidate_gameweeks.length > 10 ? " …" : ""}
          </p>
        )}
        {recommendation.warnings.map((warning) => (
          <p key={warning} className="note note--warn">
            {humanReason(warning)}
          </p>
        ))}
      </div>
    </details>
  );
}

export default function ChipsPage() {
  const { snapshot, loading, squadElements, squadNames, squadPlayers, storedSquad, financeSummary, setFreeTransfers } = useApp();
  const [data, setData] = React.useState<ChipsResult | null>(null);
  const [fetching, setFetching] = React.useState(false);
  const [fetchError, setFetchError] = React.useState<string | null>(null);
  const [useSquad, setUseSquad] = React.useState<boolean>(true);
  const [inventory, setInventory] = React.useState<ChipInventory | null>(null);
  const [inventoryLoaded, setInventoryLoaded] = React.useState(false);
  // The only per-gameweek planning input the backend contract actually
  // takes: which gameweek the manager's most recent Free Hit was played in,
  // needed to enforce "can't play the second Free Hit the week right after
  // the first" across the GW19/GW20 half-season boundary. Persisted
  // alongside the inventory rather than hardcoded to null, which silently
  // disabled that rule entirely.
  const [lastFreeHitGameweek, setLastFreeHitGameweek] = React.useState<number | null>(null);
  // Chips the manager has already committed to for a specific future
  // gameweek, so a *different* chip isn't freshly recommended for a week
  // that's already spoken for -- only one chip can be played per gameweek.
  const [plannedChips, setPlannedChips] = React.useState<PlannedChip[]>([]);
  const scheduledGameweeks = React.useMemo(
    () => plannedChips.map((planned) => planned.gw),
    [plannedChips],
  );
  // Whether the current inventory came from an FPL account sync or from the
  // manager toggling chips by hand -- a manual edit stops future auto-syncs
  // from silently overwriting it until the manager asks to re-sync.
  const [inventorySource, setInventorySource] = React.useState<InventorySource | null>(null);
  const [syncState, setSyncState] = React.useState<"idle" | "loading" | "error">("idle");
  const [syncedGameweek, setSyncedGameweek] = React.useState<number | null>(null);
  const syncedEntryRef = React.useRef<number | null>(null);
  const managerEntryId = storedSquad?.source === "manager" ? storedSquad.sourceEntryId ?? null : null;

  const syncFromFpl = React.useCallback(
    async (entryId: number) => {
      setSyncState("loading");
      try {
        const status = await api.managerStatus(entryId);
        setInventory({
          first_half: { ...status.chip_inventory.first_half },
          second_half: { ...status.chip_inventory.second_half },
        });
        setLastFreeHitGameweek(status.last_free_hit_gameweek);
        setInventorySource("fpl_sync");
        setSyncedGameweek(status.gameweek);
        if (storedSquad?.freeTransfersSource !== "manual") {
          setFreeTransfers(status.free_transfers, "fpl_sync");
        }
        setSyncState("idle");
      } catch {
        setSyncState("error");
      }
    },
    [storedSquad?.freeTransfersSource, setFreeTransfers],
  );

  const requestIdRef = React.useRef(0);

  const loadChips = React.useCallback(
    async (squadIds: number[]) => {
      const requestId = ++requestIdRef.current;
      setFetching(true);
      setFetchError(null);
      const hasFullSquad = squadIds.length === 15 && squadPlayers.length === 15;
      try {
        const res = await api.chips({
          elements: hasFullSquad ? squadIds : undefined,
          chip_inventory: inventory ? effectiveInventory(inventory, snapshot?.gameweek ?? null) : undefined,
          scheduled_gameweeks: scheduledGameweeks,
          last_free_hit_gameweek: lastFreeHitGameweek,
          // Free Hit/Wildcard candidate squads are only priced from real
          // ownership cost when there's a full squad to key it against.
          bank: hasFullSquad ? Math.max(0, fromTenths(financeSummary.bankTenths)) : undefined,
          selling_prices_tenths: hasFullSquad
            ? sellingPricesTenthsForSquad(squadPlayers, storedSquad?.finance ?? null)
            : undefined,
          free_transfers: hasFullSquad ? storedSquad?.freeTransfers : undefined,
        });
        if (requestId !== requestIdRef.current) return;
        if (res && res.ok) {
          setData(res);
        } else {
          setData(null);
          setFetchError("We couldn't work out a chip plan this time.");
        }
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        setData(null);
        setFetchError((err as Error).message || "We couldn't work out a chip plan this time.");
      } finally {
        if (requestId === requestIdRef.current) setFetching(false);
      }
    },
    [inventory, snapshot, scheduledGameweeks, lastFreeHitGameweek, squadPlayers, storedSquad, financeSummary],
  );

  React.useEffect(() => {
    if (!snapshot?.prediction_available || !inventoryLoaded) return;
    const elements = useSquad ? squadElements : [];
    const timer = window.setTimeout(() => {
      void loadChips(elements);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [snapshot?.prediction_available, inventoryLoaded, useSquad, squadElements, loadChips]);

  React.useEffect(() => {
    if (!snapshot?.season) return;
    const season = snapshot.season;
    const timer = window.setTimeout(() => {
      const stored = readInventory(season);
      setInventory(stored);
      setLastFreeHitGameweek(readLastFreeHitGameweek(season));
      setPlannedChips(readPlannedChips(season));
      setInventorySource(readInventorySource(season));
      setInventoryLoaded(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [snapshot?.season]);

  React.useEffect(() => {
    if (!inventoryLoaded || !snapshot?.season) return;
    if (typeof window !== "undefined" && inventory) {
      window.localStorage.setItem(
        CHIP_INVENTORY_KEY,
        JSON.stringify({
          ...inventory, season: snapshot.season, lastFreeHitGameweek, plannedChips,
          source: inventorySource,
        }),
      );
    } else if (typeof window !== "undefined") {
      window.localStorage.removeItem(CHIP_INVENTORY_KEY);
    }
  }, [inventory, inventoryLoaded, snapshot?.season, lastFreeHitGameweek, plannedChips, inventorySource]);

  // Auto-sync once per imported manager, as long as the manager hasn't
  // manually overridden the inventory since. A manual edit (updateChipState,
  // the Free Hit GW field) sets inventorySource to "local_user_reported" and
  // that sticks until the manager explicitly clicks Re-sync.
  React.useEffect(() => {
    if (!inventoryLoaded || !managerEntryId) return;
    if (inventorySource === "local_user_reported") return;
    if (syncedEntryRef.current === managerEntryId) return;
    syncedEntryRef.current = managerEntryId;
    void syncFromFpl(managerEntryId);
  }, [inventoryLoaded, managerEntryId, inventorySource, syncFromFpl]);

  function addPlannedChip(chip: ChipId, gw: number) {
    // Only one chip can be played in a gameweek, so a second plan for the
    // same week replaces the first, after asking.
    const existing = plannedChips.find((planned) => planned.gw === gw && planned.chip !== chip);
    if (existing && !window.confirm(
      `GW${gw} already has ${CHIP_LABELS[existing.chip]} planned. Replace it with ${CHIP_LABELS[chip]}?`)) {
      return;
    }
    setPlannedChips((current) => {
      const withoutSameWeek = current.filter((planned) => planned.gw !== gw && !(planned.chip === chip && planned.gw === gw));
      return [...withoutSameWeek, { chip, gw }].sort((a, b) => a.gw - b.gw);
    });
  }

  function removePlannedChip(chip: ChipId, gw: number) {
    setPlannedChips((current) => current.filter((planned) => !(planned.chip === chip && planned.gw === gw)));
  }

  function updateChipState(half: "first_half" | "second_half", chip: ChipId) {
    setInventory((current) => {
      if (!current) return current;
      const nextState = nextInventoryState(current[half][chip]);
      return {
        ...current,
        [half]: {
          ...current[half],
          [chip]: nextState,
        },
      };
    });
    setInventorySource("local_user_reported");
    // Marking Free Hit used usually happens right around when it's played;
    // default the GW field to today's rather than leaving it blank and
    // making the manager type a number they were just implicitly stating.
    // Still freely editable for a retroactive correction.
    if (half === "first_half" && chip === "free_hit" && inventory?.first_half.free_hit === "unused") {
      setLastFreeHitGameweek((current) => current ?? snapshot?.gameweek ?? null);
    }
  }

  if (loading || !snapshot) {
    return (
      <section className="page">
        <div className="skel skel-sign" />
        <Skeleton variant="hero" />
        <div className="skel-columns" style={{ "--cols": 2 } as React.CSSProperties}>
          <Skeleton variant="card" count={2} />
          <Skeleton variant="card" count={2} />
        </div>
      </section>
    );
  }

  if (!snapshot.prediction_available) {
    return (
      <section className="page">
        <GateSign />
        <EmptyState
          title="Projections aren't ready yet"
          message="The chip plan is built from this week's projections. Use Get latest data in the menu, then come back."
        />
      </section>
    );
  }

  const recsByChip = new Map<string, ChipRecommendation>();
  for (const rec of data?.recommendations ?? []) {
    recsByChip.set(rec.chip, rec);
  }

  const orderedRecommendations = CHIP_IDS.map((chip) => recsByChip.get(chip)).filter(
    (rec): rec is ChipRecommendation => rec != null,
  );
  // The backend names at most one play-now candidate. Without one, fall back
  // to the plan's best (future) week so the hero always says something.
  const playNow = data?.primary_decision
    ? recsByChip.get(data.primary_decision.chip) ?? null
    : null;
  const bestPlanned = !playNow && data?.chip_plan.length
    ? recsByChip.get(
        [...data.chip_plan].sort(
          (a, b) => (b.discounted_gain ?? -Infinity) - (a.discounted_gain ?? -Infinity),
        )[0].chip,
      ) ?? null
    : null;
  const heroRec = playNow ?? bestPlanned ?? null;
  const squadReasonNeeded = squadNames.length < 15
    ? `Needs 15 players (you have ${squadNames.length})`
    : undefined;

  return (
    <section className="page chips-page" aria-label="Chips">
      <GateSign
        lede={
          data?.has_squad
            ? `When to play each chip, worked out for your squad through to gameweek ${data.last_gw}.`
            : undefined
        }
      >
        <Segmented
          label="Plan using"
          value={useSquad ? "squad" : "fixtures"}
          onChange={(value) => setUseSquad(value === "squad")}
          options={[
            { value: "squad", label: "My squad", disabled: squadNames.length < 15, title: squadReasonNeeded },
            { value: "fixtures", label: "Fixtures only" },
          ]}
        />
      </GateSign>

      {useSquad && squadReasonNeeded && (
        <div className="callout">
          <span className="callout-mark"><Icon name="alert" size={16} /></span>
          <p>
            You have {squadNames.length} of 15 players, so this is based on fixtures alone. Finish your squad on My team for a plan built around your players.
          </p>
        </div>
      )}

      {fetchError && (
        <div className="callout callout--alert" role="alert">
          <span className="callout-mark"><Icon name="alert" size={16} /></span>
          <p>{fetchError}</p>
          <button type="button" className="btn btn--sm" onClick={() => void loadChips(useSquad ? squadElements : [])}>
            Try again
          </button>
        </div>
      )}

      {fetching && !data ? (
        <VerdictPlate tone="night" busy title="Working out your chip plan…" body="Checking every week left in the season. This can take a few seconds." label="This week's chip" />
      ) : (
        <VerdictPlate
          tone={playNow ? "spotlight" : "night"}
          busy={fetching}
          label="This week's chip"
          title={
            playNow
              ? <>Play {CHIP_LABELS[playNow.chip]} this week.</>
              : bestPlanned
                ? <>No chip this week.</>
                : data
                  ? <>No chip stands out yet.</>
                  : <>Chip plan on its way.</>
          }
          body={
            playNow
              ? humanReason(playNow.reasons[0])
              : bestPlanned
                ? `Save them. Your best plan uses ${CHIP_LABELS[bestPlanned.chip]} in gameweek ${bestPlanned.gw}. ${humanReason(bestPlanned.reasons[0])}`
                : data?.inventory_source === "unknown"
                  ? "Tell us which chips you've still got (Your chips, below) and the plan sharpens up."
                  : "Finish your squad on My team to get a plan."
          }
          facts={
            heroRec && (
              <>
                <span className="plate-chip">
                  <ChipIcon id={heroRec.chip} size="large" />
                </span>
                <PlateFact label="Best week">{heroRec.gw ? `GW${heroRec.gw}` : STATUS_LABELS[heroRec.status]}</PlateFact>
                {heroRec.gain != null && <PlateFact label="Extra points">+{num(heroRec.gain, 1)}</PlateFact>}
                {heroRec.close_call && <PlateFact label="Heads up">Close call</PlateFact>}
              </>
            )
          }
          actions={heroRec && <WhyThisChoice recommendation={heroRec} />}
        />
      )}

      {data && (data.rows?.length ?? 0) > 0 && (
        <section className="section" aria-label="Season plan">
          <div className="section-title">
            <div>
              <h2>The plan, week by week</h2>
              <p>Where each chip lands between now and the end of the season. Chips reset after gameweek 19.</p>
            </div>
          </div>
          <ChipPlanTimeline rows={data.rows} chipPlan={data.chip_plan} currentGameweek={data.current_gameweek} />
        </section>
      )}

      {orderedRecommendations.length > 0 && (
        <section className="section" aria-label="Each chip">
          <div className="section-title">
            <div>
              <h2>Each chip</h2>
              <p>
                {data?.inventory_source === "local_user_reported" || inventorySource === "fpl_sync"
                  ? "Based on the chips you still have."
                  : "Assuming you still have every chip. Tell us which you've used in Your chips, below."}
              </p>
            </div>
          </div>
          <div className="chip-grid stagger">
            {orderedRecommendations.map((rec, index) => {
              const barWeeks = data?.has_squad ? pickBarWeeks(rec.candidate_gameweeks, data.current_gameweek, rec.gw) : [];
              const barItems = barWeeks.map((gw) => ({
                key: String(gw),
                label: `GW${gw}`,
                value: rec.gains_by_week[String(gw)] ?? null,
                state: (gw === data?.current_gameweek ? "now" : gw === rec.gw ? "best" : "default") as "now" | "best" | "default",
              }));
              return (
                <article key={rec.chip} className={`panel chip-card status-${rec.status}`} style={{ "--i": index } as React.CSSProperties}>
                  <div className="chip-card-head">
                    <ChipIcon id={rec.chip} />
                    <div>
                      <h3>{CHIP_LABELS[rec.chip]}</h3>
                      <p>{CHIP_DESCRIPTIONS[rec.chip]}</p>
                    </div>
                  </div>
                  <div className="chip-card-call">
                    <span className={`badge chip-status chip-status--${rec.status}`}>{STATUS_LABELS[rec.status]}</span>
                    <b>{rec.gw ? `Gameweek ${rec.gw}` : "No week yet"}</b>
                    {rec.gain != null && <span className="chip-gain">+{num(rec.gain, 1)} pts</span>}
                  </div>
                  {barItems.length > 0 && <BarStrip items={barItems} height={40} />}
                  <p className="chip-card-reason">{humanReason(rec.reasons[0])}</p>
                  {rec.use_or_lose && <p className="note note--warn">Only a few weeks left to use this one before it expires.</p>}
                  <WhyThisChoice recommendation={rec} />
                </article>
              );
            })}
          </div>
        </section>
      )}

      <details className="disclosure chip-manage" open={!inventory}>
        <summary>
          Your chips
          <small>{inventorySource === "fpl_sync" ? "Synced from FPL" : inventory ? "Entered by you" : "Not entered yet"}</small>
          <Icon name="chevron-down" size={18} />
        </summary>
        <div className="disclosure-body">
          <div className="chip-manage-top">
            <p className="note">
              {inventory
                ? "Tap a chip to mark it used. Unused first-half chips expire after gameweek 19 on their own."
                : "Mark which chips you still have so the plan only suggests ones you can play."}
            </p>
            <div className="chip-manage-actions">
              {managerEntryId != null && (
                <button
                  type="button"
                  className="btn btn--line btn--sm"
                  disabled={syncState === "loading"}
                  onClick={() => {
                    setInventorySource(null);
                    syncedEntryRef.current = null;
                    void syncFromFpl(managerEntryId);
                  }}
                >
                  <Icon name="refresh" size={16} /> {syncState === "loading" ? "Syncing…" : "Sync from FPL"}
                </button>
              )}
              <button
                type="button"
                className={inventory ? "btn btn--ghost btn--sm" : "btn btn--sm"}
                onClick={() => {
                  setInventory(inventory ? null : blankInventory());
                  setInventorySource(inventory ? null : "local_user_reported");
                }}
              >
                {inventory ? "Clear my chips" : "I have all my chips"}
              </button>
            </div>
          </div>
          {syncState === "error" && <p className="status-line is-error">Couldn&apos;t reach FPL, so these are the chips saved on this device.</p>}
          {inventorySource === "fpl_sync" && syncedGameweek != null && <p className="note">Synced from FPL in gameweek {syncedGameweek}.</p>}
          <label className="field chip-ft" htmlFor="chip-free-transfers">
            <span>Free transfers you have{storedSquad?.freeTransfersSource === "fpl_sync" ? " (from FPL)" : ""}</span>
            <input
              id="chip-free-transfers"
              className="input input--sm"
              type="number"
              min={0}
              max={5}
              value={storedSquad?.freeTransfers ?? ""}
              placeholder="0-5"
              onChange={(event) => {
                const parsed = Number(event.target.value);
                if (event.target.value !== "" && Number.isFinite(parsed)) {
                  setFreeTransfers(parsed, "manual");
                }
              }}
            />
          </label>
          {inventory && (
            <div className="chip-sets">
              {(["first_half", "second_half"] as const).map((half) => (
                <div className="chip-set" key={half}>
                  <h3>{half === "first_half" ? "First half, to gameweek 19" : "Second half, from gameweek 20"}</h3>
                  <div className="chip-set-items">
                    {CHIP_IDS.map((chip) => {
                      const effective = effectiveChipState(inventory[half][chip], half, snapshot.gameweek ?? null);
                      const expired = effective === "expired";
                      return (
                        <button
                          type="button"
                          className={`chip-token state-${effective}`}
                          key={`${half}-${chip}`}
                          onClick={() => updateChipState(half, chip)}
                          disabled={expired}
                          aria-label={`${CHIP_LABELS[chip]}, ${half === "first_half" ? "first" : "second"} half: ${inventoryStatusLabel(effective)}.${expired ? "" : " Tap to change."}`}
                        >
                          <ChipIcon id={chip} />
                          <span>{CHIP_LABELS[chip]}</span>
                          <b>{inventoryStatusLabel(effective)}</b>
                        </button>
                      );
                    })}
                  </div>
                  {half === "first_half" && inventory.first_half.free_hit === "used" && (
                    <label className="field chip-ft" htmlFor="chip-free-hit-gw">
                      <span>Gameweek you played Free Hit</span>
                      <input
                        id="chip-free-hit-gw"
                        className="input input--sm"
                        type="number"
                        min={2}
                        max={19}
                        placeholder="e.g. 12"
                        value={lastFreeHitGameweek ?? ""}
                        onChange={(event) => {
                          const parsed = Number(event.target.value);
                          setLastFreeHitGameweek(event.target.value === "" || Number.isNaN(parsed) ? null : parsed);
                          setInventorySource("local_user_reported");
                        }}
                      />
                    </label>
                  )}
                </div>
              ))}
            </div>
          )}
          {inventory && (
            <PlannedChipsPanel
              plannedChips={plannedChips}
              maxGw={38}
              currentGw={snapshot.gameweek ?? 1}
              onAdd={addPlannedChip}
              onRemove={removePlannedChip}
            />
          )}
        </div>
      </details>

      {data && data.has_squad && (
        <details className="disclosure">
          <summary>
            Every chip, every week
            <small>Extra points each chip would add, week by week</small>
            <Icon name="chevron-down" size={18} />
          </summary>
          <div className="disclosure-body">
            <ChipOpportunityMatrix
              recommendations={data.recommendations}
              chipPlan={data.chip_plan}
              currentGameweek={data.current_gameweek}
              hasSquad={data.has_squad}
            />
          </div>
        </details>
      )}

      {data && (
        <details className="disclosure">
          <summary>
            Doubles, blanks and difficulty
            <small>The fixture picture behind the plan</small>
            <Icon name="chevron-down" size={18} />
          </summary>
          <div className="disclosure-body table-wrap">
            <table className="table chip-weeks">
              <thead>
                <tr>
                  <th>Week</th>
                  <th className="num">Games</th>
                  {data.has_squad && <th className="num">Your players playing</th>}
                  <th className="num">Clubs playing twice</th>
                  <th className="num">Clubs without a game</th>
                  <th>Average difficulty</th>
                  <th>What stands out</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row: ChipRow) => {
                  const isDgw = row.dgw_teams > 0;
                  const isBgw = row.blank_teams > 0;
                  const signal = isDgw
                    ? "Double gameweek"
                    : isBgw
                      ? "Blank gameweek"
                      : row.avg_fdr <= 2.8
                        ? "Easier week"
                        : row.avg_fdr >= 3.4
                          ? "Harder week"
                          : "";
                  return (
                    <tr key={row.gw} className={isDgw ? "is-dgw" : isBgw ? "is-bgw" : undefined}>
                      <td><b>GW{row.gw}</b></td>
                      <td className="num">{row.matches}</td>
                      {data.has_squad && (
                        <td className="num">
                          {row.squad_playing ?? 15} of 15
                        </td>
                      )}
                      <td className="num">{row.dgw_teams || "–"}</td>
                      <td className="num">{row.blank_teams || "–"}</td>
                      <td>
                        <span className={`fdr fdr--${Math.min(5, Math.max(1, Math.round(row.avg_fdr)))}`}>{num(row.avg_fdr, 1)}</span>
                      </td>
                      <td>{signal && <span className={`badge ${isDgw ? "badge--go" : isBgw ? "badge--alert" : ""}`}>{signal}</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  );
}
