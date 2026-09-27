"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { fromTenths, sellingPricesTenthsForSquad } from "@/lib/finance";
import { Loading } from "@/components/loading";
import { Skeleton } from "@/components/skeleton";
import { EmptyState } from "@/components/empty-state";
import { ChipIcon } from "@/components/chips/chip-icon";
import { ChipOpportunityMatrix } from "@/components/chips/chip-opportunity-matrix";
import { ChipPlanTimeline } from "@/components/chips/chip-plan-timeline";
import { BarStrip } from "@/components/charts/bar-strip";
import { CountUp } from "@/components/motion/count-up";
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

const PROJECTION_STATE_LABELS: Record<string, string> = {
  projected: "Projected",
  extrapolated: "Extrapolated",
  no_fixtures: "No fixtures",
  complete: "Complete",
  unknown: "No confirmed fixtures",
};

function formatGeneratedAt(value: string | null): string {
  if (!value) return "time unknown";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "time unknown" : date.toLocaleString();
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
      <span className="kicker">Planned chips</span>
      <p className="chip-planned-note">
        A chip you&apos;ve already committed to for a specific future week. Recommendations won&apos;t suggest
        a different chip for that same gameweek, since only one can be played per week.
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
                <span>{CHIP_LABELS[planned.chip]} · GW{planned.gw}</span>
                <button
                  type="button"
                  className="btn ghost sm"
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
        <select value={chip} onChange={(event) => setChip(event.target.value as ChipId)}>
          {CHIP_IDS.map((id) => (
            <option key={id} value={id}>{CHIP_LABELS[id]}</option>
          ))}
        </select>
        <input
          type="number"
          min={currentGw}
          max={maxGw}
          placeholder={`GW${currentGw}-${maxGw}`}
          value={gwInput}
          onChange={(event) => setGwInput(event.target.value)}
        />
        <button type="submit" className="btn secondary sm">Add</button>
      </form>
    </div>
  );
}

function WhyThisChoice({ recommendation, data }: { recommendation: ChipRecommendation; data: ChipsResult }) {
  const evidence = recommendation.evidence;
  return (
    <details className="chip-method chip-why">
      <summary>Why this choice</summary>
      {evidence?.chip === "triple_captain" && (
        <p>
          {evidence.captain.name} ({evidence.captain.team}, {evidence.captain.position}) projects {num(evidence.captain.projected_points, 1)} points
          as the extra copy of the armband. Projections already include the chance of playing.
        </p>
      )}
      {evidence?.chip === "bench_boost" && (
        <>
          <ul>{evidence.ordered_bench.map((player) => (
            <li key={player.element}>{player.player}: {num(player.points, 1)} pts</li>
          ))}</ul>
          <p>
            Gross bench projection {num(evidence.bench_total, 1)}, minus {num(evidence.expected_autosub_points, 1)} points
            the bench would score anyway through a normal week&apos;s autosubs.
          </p>
        </>
      )}
      {evidence?.chip === "free_hit" && (
        <p>
          A one-week squad projects {num(evidence.free_hit_total, 1)} points, against {num(evidence.no_chip_total, 1)} for
          the best transfer you could make instead with {evidence.no_chip_free_transfers} free transfer{evidence.no_chip_free_transfers === 1 ? "" : "s"}
          {" "}({evidence.changed_player_count} changed player{evidence.changed_player_count === 1 ? "" : "s"} on the one-week squad).
        </p>
      )}
      {evidence?.chip === "wildcard" && (
        <p>
          Rebuilding the squad projects {evidence.wildcard_total != null ? num(evidence.wildcard_total, 1) : "—"} points
          across GW{evidence.window_gameweeks[0]}–GW{evidence.window_gameweeks[evidence.window_gameweeks.length - 1]}
          {evidence.truncated ? " (season ends before a full 6-week window)" : ""}, against the best you could do with rolling free
          transfers over the same weeks ({evidence.changed_player_count} changed players).
        </p>
      )}
      {recommendation.candidate_gameweeks.length > 0 && (
        <p>
          Every eligible week: {recommendation.candidate_gameweeks.map((gw) => {
            const value = recommendation.gains_by_week[String(gw)];
            return "GW" + gw + " " + (value != null ? "+" + num(value, 1) : "—");
          }).join(" · ")}.
        </p>
      )}
      <p>
        Source: {data.projection_source}; coverage: {data.projection_gameweeks.length ? data.projection_gameweeks.map((gw) => "GW" + gw).join(", ") : "none"}.
        Inventory: {data.inventory_source === "local_user_reported" ? "entered by you on this device" : "not entered"}. {data.decision_policy.uncertainty_note}
      </p>
      {recommendation.warnings.map((warning) => <p key={warning}>{warning}</p>)}
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
          setFetchError("Unable to compute chip optimization recommendations.");
        }
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        setData(null);
        setFetchError((err as Error).message || "Failed to load chip advice.");
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
        <div className="shell">
          <Skeleton variant="hero" />
          <Skeleton variant="card" count={4} />
        </div>
      </section>
    );
  }

  if (!snapshot.prediction_available) {
    return (
      <section className="page">
        <div className="shell shell--padded">
          <EmptyState
            title="Predictions Unavailable"
            message={`The Chip Advisor requires model projections to evaluate optimal play windows.${snapshot.prediction_error ? ` (${snapshot.prediction_error})` : ""} Run the prediction pipeline or click Refresh in the header.`}
          />
        </div>
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
    <section className="page chips-page" aria-label="Chip advisor">
      <div className="shell">
        <header className="section-head section-head--mt">
          <div>
            <span className="badge lime">Chip planning desk</span>
            <h1 className="display-hero">Chip Advisor</h1>
            <p>
              {data && data.has_squad
                ? "A squad-specific, horizon-independent chip plan through the end of the season."
                : "Fixture signals only; build a 15-player squad in My Team for a player-based plan."}
            </p>
          </div>

          <div className="section-head-actions">
            <div className="chip-mode-toggle" role="group" aria-label="Evaluation mode">
              <button
                type="button"
                className={`btn sm${useSquad ? " active" : ""}`}
                onClick={() => setUseSquad(true)}
                disabled={squadNames.length < 15}
                title={squadReasonNeeded ?? "Evaluate with your active 15-player squad"}
              >
                My squad
              </button>
              <button
                type="button"
                className={`btn sm${!useSquad ? " active" : ""}`}
                onClick={() => setUseSquad(false)}
                title="League-wide fixture signals only, no squad required"
              >
                Fixtures only
              </button>
            </div>
          </div>
        </header>

        {useSquad && squadReasonNeeded && (
          <div className="chip-squad-notice">
            <span className="chip-squad-notice-icon" aria-hidden="true">i</span>
            <span>
              {squadReasonNeeded}. Using league-wide fixture signals.
              Head to <strong>My Team</strong> to complete your squad for a squad-specific plan.
            </span>
          </div>
        )}

        {fetching && <Loading label="Calculating the chip plan…" />}

        {fetchError && (
          <div className="chip-error">
            <span>{fetchError}</span>
            <button
              type="button"
              className="btn sm"
              onClick={() => void loadChips(useSquad ? squadElements : [])}
            >
              Retry
            </button>
          </div>
        )}

        {data && (
          <p className="chip-data-bar" role="status">
            <b>GW{data.first_gw}–{data.last_gw}</b>
            <span>{data.has_squad ? "Player projections" : "Fixture signal only"}</span>
            <span>Generated {formatGeneratedAt(data.projection_generated_at)}</span>
            <small>{data.projection_note} Use Refresh in the header to reload predictions.</small>
          </p>
        )}

        <section className={`chip-next-decision${heroRec ? ` status-${heroRec.status}` : ""}`} aria-live="polite">
          <div className="chip-next-decision-copy">
            <span className="kicker">This week&apos;s chip decision</span>
            <h2>
              {playNow
                ? `Play ${CHIP_LABELS[playNow.chip]}`
                : bestPlanned
                  ? `No chip this week: best plan uses ${CHIP_LABELS[bestPlanned.chip]} in GW${bestPlanned.gw}`
                  : data
                    ? "No chip stands out this week"
                    : "No chip data yet"}
            </h2>
            <p>
              {heroRec?.reasons[0] ?? (data
                ? (data.inventory_source === "unknown"
                  ? "Open Manage my chips and mark which chips you still have; suggestions stay provisional until then."
                  : "Build a complete squad in My Team to calculate a decision.")
                : "Build a complete squad in My Team to calculate a decision.")}
            </p>
            {data && (
              <small className="chip-decision-context">
                {data.has_squad ? "Player projections" : "Fixture signal"} · {data.inventory_source === "local_user_reported" ? "chips entered by you" : "chips not entered"}
              </small>
            )}
            {heroRec?.close_call && <small className="chip-close-call-badge">Close call vs the alternative week</small>}
            {heroRec?.warnings.map((warning) => <small key={warning}>{warning}</small>)}
            {heroRec && data && <WhyThisChoice recommendation={heroRec} data={data} />}
          </div>
          {heroRec && (
            <div className={`chip-decision-score status-${heroRec.status}`}>
              <ChipIcon id={heroRec.chip} size="large" />
              <strong>{heroRec.gw ? `GW${heroRec.gw}` : STATUS_LABELS[heroRec.status]}</strong>
              <span>{STATUS_LABELS[heroRec.status]}</span>
              {heroRec.gain != null && <small>+<CountUp value={heroRec.gain} decimals={1} /> extra points vs your best normal week</small>}
            </div>
          )}
        </section>

        {data && (data.rows?.length ?? 0) > 0 && (
          <ChipPlanTimeline rows={data.rows} chipPlan={data.chip_plan} currentGameweek={data.current_gameweek} />
        )}

        <div className="chip-advisor-grid stagger">
          {orderedRecommendations.filter((rec) => rec.chip !== heroRec?.chip).map((rec, index) => {
            const nowGain = data ? rec.gains_by_week[String(data.current_gameweek)] ?? null : null;
            const barItems = rec.candidate_gameweeks.map((gw) => ({
              key: String(gw),
              label: `GW${gw}`,
              value: rec.gains_by_week[String(gw)] ?? null,
              state: (gw === data?.current_gameweek ? "now" : gw === rec.gw ? "best" : "default") as "now" | "best" | "default",
            }));
            return (
              <article key={rec.chip} className={`chip-advisor-card lift status-${rec.status}`} style={{ "--i": index } as React.CSSProperties}>
                <div className="chip-advisor-header">
                  <div className="chip-advisor-name">
                    <ChipIcon id={rec.chip} />
                    {CHIP_LABELS[rec.chip]}
                  </div>
                  <span className={`chip-conf status-${rec.status}`}>
                    {STATUS_LABELS[rec.status]}
                    {rec.close_call && " · Close call"}
                  </span>
                </div>
                <div>
                  <div className={`chip-advisor-target${rec.status === "hold" ? " hold" : ""}`}>
                    {rec.gw ? `GW${rec.gw}` : STATUS_LABELS[rec.status]}
                  </div>
                  {rec.gain != null && (
                    <p className="chip-advisor-sub">
                      Now {nowGain != null ? num(nowGain, 1) : "—"} vs best +<CountUp value={rec.gain} decimals={1} />
                    </p>
                  )}
                </div>
                {barItems.length > 0 && <BarStrip items={barItems} height={36} />}
                <p className="chip-advisor-desc">{rec.reasons[0]}</p>
                {rec.use_or_lose && <p className="chip-advisor-note">Few eligible weeks remain this half: use it or lose it.</p>}
                <WhyThisChoice recommendation={rec} data={data!} />
                <div className="chip-advisor-footer">{CHIP_DESCRIPTIONS[rec.chip]}</div>
              </article>
            );
          })}
        </div>

        <details className="chip-manage">
          <summary>Manage my chips <small>{inventory ? "entered on this device" : "not entered"}</small></summary>
        <section className={`chip-inventory inventory-${inventory ? "synced" : "not-synced"}`} aria-label="Chip inventory">
          <div>
            <span className="kicker">Entered by you · not linked to FPL</span>
            <h2>{inventory ? "Chips you entered on this device" : "Chip history not entered"}</h2>
            <p>
              {inventory
                ? "Mark a chip used as you play it. An unused first-half chip is shown Expired automatically once GW19 passes -- no private FPL account data is connected, and this device is the only place this is saved."
                : "Suggestions stay provisional until you mark the two half-season sets. Nothing here is verified against your FPL account."}
            </p>
          </div>
          <span className={`chip-inventory-state state-${inventory ? "synced" : "not-synced"}`}>
            {inventory ? "Entered" : "Not entered"}
          </span>
          <button
            type="button"
            className="btn secondary sm"
            onClick={() => {
              setInventory(inventory ? null : blankInventory());
              setInventorySource(inventory ? null : "local_user_reported");
            }}
          >
            {inventory ? "Clear my chip entries" : "Mark chips available"}
          </button>
          {managerEntryId != null && (
            <div className="chip-sync-status">
              {syncState === "loading" && <small>Syncing from FPL…</small>}
              {syncState === "idle" && inventorySource === "fpl_sync" && (
                <small>Synced from FPL{syncedGameweek != null ? ` · GW${syncedGameweek}` : ""}</small>
              )}
              {syncState === "error" && <small>Could not sync from FPL; showing entries from this device.</small>}
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => {
                  setInventorySource(null);
                  syncedEntryRef.current = null;
                  void syncFromFpl(managerEntryId);
                }}
              >
                Re-sync from FPL
              </button>
            </div>
          )}
          <label className="chip-free-transfers-input" htmlFor="chip-free-transfers">
            <span className="kicker">Free transfers</span>
            <input
              id="chip-free-transfers"
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
            {storedSquad?.freeTransfersSource === "fpl_sync" && <small>Synced from FPL</small>}
          </label>
          {inventory && (
            <div className="chip-inventory-grid">
              {(["first_half", "second_half"] as const).map((half) => (
                <div className="chip-inventory-set" key={half}>
                  <span className="kicker">{half === "first_half" ? "Set 1 · through GW19" : "Set 2 · GW20 onward"}</span>
                  <div className="chip-inventory-items">
                    {CHIP_IDS.map((chip) => {
                      const effective = effectiveChipState(inventory[half][chip], half, snapshot.gameweek ?? null);
                      const expired = effective === "expired";
                      return (
                        <button
                          type="button"
                          className={`chip-inventory-item state-${effective}`}
                          key={`${half}-${chip}`}
                          onClick={() => updateChipState(half, chip)}
                          disabled={expired}
                          aria-label={`${CHIP_LABELS[chip]} ${half} status: ${inventoryStatusLabel(effective)}.${expired ? "" : " Change status."}`}
                        >
                          <ChipIcon id={chip} />
                          <span>{CHIP_LABELS[chip]}</span>
                          <b>{inventoryStatusLabel(effective)}</b>
                        </button>
                      );
                    })}
                  </div>
                  {half === "first_half" && inventory.first_half.free_hit === "used" && (
                    <label className="chip-inventory-gw-input" htmlFor="chip-free-hit-gw">
                      <span className="kicker">Free Hit played in GW</span>
                      <input
                        id="chip-free-hit-gw"
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
        </section>

        </details>

        {data && (
          <ChipOpportunityMatrix
            recommendations={data.recommendations}
            chipPlan={data.chip_plan}
            currentGameweek={data.current_gameweek}
            hasSquad={data.has_squad}
          />
        )}

        <div className="chip-heatmap-section">
          <div className="sub-head">
            <h3>Fixture context</h3>
            <span className="rule" />
            <small>
              GW{data?.first_gw ?? snapshot.gameweek}–GW{data?.last_gw ?? 38}
            </small>
          </div>

          <div className="chip-heatmap-scroll">
            <table className="chip-advisor-heatmap">
              <thead>
                <tr>
                  <th className="col-gw">GW</th>
                  <th>Fixtures</th>
                  {data?.has_squad && <th>Squad Active</th>}
                  <th>DGW Teams</th>
                  <th>Blank Teams</th>
                  <th>Avg FDR</th>
                  <th>Signal</th>
                  <th>Projection</th>
                </tr>
              </thead>
              <tbody>
                {data?.rows.map((row: ChipRow) => {
                  const isDgw = row.dgw_teams > 0;
                  const isBgw = row.blank_teams > 0;
                  const avgFdr = row.avg_fdr;
                  const hasSquad = data.has_squad;

                  let signal = "Standard run";
                  let signalClass = "trend flat";
                  if (isDgw) {
                    signal = `Double GW (${row.dgw_teams} teams)`;
                    signalClass = "trend up";
                  } else if (isBgw) {
                    signal = `Blank GW (${row.blank_teams} teams)`;
                    signalClass = "trend down";
                  } else if (avgFdr <= 2.8) {
                    signal = "Favourable Matchups";
                    signalClass = "trend up";
                  } else if (avgFdr >= 3.4) {
                    signal = "High Difficulty";
                    signalClass = "trend flat";
                  }

                  return (
                    <tr
                      key={row.gw}
                      className={isDgw ? "is-dgw" : isBgw ? "is-bgw" : undefined}
                    >
                      <td className="chip-row-gw">
                        GW{row.gw}
                      </td>
                      <td>
                        {row.matches} matches
                      </td>
                      {hasSquad && (
                        <td>
                          <span className={(row.squad_blanks ?? 0) > 0 ? "chip-squad-active is-blank" : "chip-squad-active"}>
                            {row.squad_playing ?? 15}/15
                          </span>
                          {(row.squad_blanks ?? 0) > 0 && (
                            <small className="chip-squad-blank">
                              ({row.squad_blanks} blank)
                            </small>
                          )}
                        </td>
                      )}
                      <td className={row.dgw_teams > 0 ? "chip-count chip-count--dgw" : "chip-count"}>
                        {row.dgw_teams > 0 ? `+${row.dgw_teams}` : "0"}
                      </td>
                      <td className={row.blank_teams > 0 ? "chip-count chip-count--blank" : "chip-count"}>
                        {row.blank_teams > 0 ? row.blank_teams : "0"}
                      </td>
                      <td>
                        <div className="chip-fdr-readout">
                          <span
                            className={`fdr`}
                            data-fdr={Math.round(avgFdr)}
                          />
                          <span className="chip-fdr-value">
                            {num(avgFdr, 1)}
                          </span>
                        </div>
                      </td>
                      <td>
                        <span className={signalClass}>
                          {signal}
                        </span>
                      </td>
                      <td>{PROJECTION_STATE_LABELS[row.projection_state] ?? row.projection_state}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {data && (
          <details className="chip-method">
            <summary>Projection and decision policy</summary>
            <p>Source: {data.projection_source}. Coverage: {data.projection_gameweeks.length ? data.projection_gameweeks.map((gw) => "GW" + gw).join(", ") : "none"}. Evaluated: {data.evaluated_horizon} of {data.requested_horizon} requested weeks. Data quality: {data.data_quality}. Method: {data.methodology_version}.</p>
            <p>Generated: {data.projection_generated_at ?? "timestamp unavailable"}. {data.decision_policy.basis}. {data.decision_policy.uncertainty_note}</p>
            {data.coverage_warning && <p>{data.coverage_warning}</p>}
          </details>
        )}
      </div>
    </section>
  );
}
