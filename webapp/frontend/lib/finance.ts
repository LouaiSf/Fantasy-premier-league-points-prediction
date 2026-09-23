import type { OwnedPrice, PlayerRecord, PriceBasis, SquadFinance } from "./types";

// FPL prices are integer tenths of a million (e.g. £5.3m). Money enters this
// module as a `value_m` float and is immediately converted, because tenths
// are the only representation in which "half the rise, rounded down" has an
// exact answer -- `(5.3 - 5.0) / 2` in floating point is not reliably `0.15`.
export function toTenths(valueM: number): number {
  return Math.round(valueM * 10);
}

export function fromTenths(tenths: number): number {
  return tenths / 10;
}

export const BUDGET_TENTHS = 1000;

// The official 2026/27 selling-price rule: a manager keeps half of any rise
// (rounded down to the nearest £0.1m) and absorbs a fall in full.
// https://www.premierleague.com/en/news/2174907
export function sellingPriceTenths(purchaseTenths: number, currentTenths: number): number {
  if (currentTenths <= purchaseTenths) return currentTenths;
  return purchaseTenths + Math.floor((currentTenths - purchaseTenths) / 2);
}

export interface FinanceSummary {
  marketValueTenths: number;
  sellingValueTenths: number;
  bankTenths: number;
  priceBasis: PriceBasis;
}

// The two things a squad is worth: what the market would pay to buy it today
// (marketValueTenths, i.e. `sum(now_cost)`) and what selling every player
// today would actually put in the bank (sellingValueTenths, which trails the
// market value upward because of the half-rise rule). Neither is legality --
// only bank + selling value vs. a proposed spend is.
export function computeFinanceSummary(
  players: PlayerRecord[],
  finance: SquadFinance | null,
): FinanceSummary {
  let marketValueTenths = 0;
  let sellingValueTenths = 0;
  for (const player of players) {
    const currentTenths = toTenths(player.value_m);
    marketValueTenths += currentTenths;
    const owned = finance?.ownedPrices[player.element];
    sellingValueTenths += owned
      ? sellingPriceTenths(owned.purchaseTenths, currentTenths)
      : currentTenths;
  }
  return {
    marketValueTenths,
    sellingValueTenths,
    bankTenths: finance?.bankTenths ?? 0,
    priceBasis: finance?.priceBasis ?? "estimated",
  };
}

export interface OwnershipDiffResult {
  finance: SquadFinance;
  proceedsTenths: number;
  costTenths: number;
}

// Applies a squad-composition change (a transfer, or a from-scratch manual
// save treated as buying all 15 against a fresh budget) to a finance block.
// Removed owned players release their selling price into the bank; added
// players are bought at today's market price, which becomes their purchase
// price going forward.
//
// When `prevFinance` is null -- a brand-new squad, or an old squad saved
// before this finance block existed -- there is no ownership history to
// diff against, so every player in `nextIds` is treated as bought fresh
// against a full £100.0m budget, and any `prevIds` not carried over are
// estimated at today's market price rather than a remembered purchase price.
export function applyOwnershipDiff(
  prevFinance: SquadFinance | null,
  prevIds: number[],
  nextIds: number[],
  playersById: Map<number, PlayerRecord>,
  opts?: { priceBasis?: PriceBasis; marketPriceAsOf?: string | null },
): OwnershipDiffResult {
  const prevSet = new Set(prevFinance ? prevIds : []);
  const nextSet = new Set(nextIds);
  const removed = prevFinance ? prevIds.filter((id) => !nextSet.has(id)) : [];
  const added = nextIds.filter((id) => !prevSet.has(id));

  const ownedPrices: Record<number, OwnedPrice> = prevFinance ? { ...prevFinance.ownedPrices } : {};
  let bankTenths = prevFinance ? prevFinance.bankTenths : BUDGET_TENTHS;

  let proceedsTenths = 0;
  for (const id of removed) {
    const player = playersById.get(id);
    const owned = ownedPrices[id];
    const currentTenths = player ? toTenths(player.value_m) : (owned?.purchaseTenths ?? 0);
    const proceeds = owned ? sellingPriceTenths(owned.purchaseTenths, currentTenths) : currentTenths;
    proceedsTenths += proceeds;
    bankTenths += proceeds;
    delete ownedPrices[id];
  }

  let costTenths = 0;
  for (const id of added) {
    const player = playersById.get(id);
    const purchaseTenths = player ? toTenths(player.value_m) : 0;
    costTenths += purchaseTenths;
    bankTenths -= purchaseTenths;
    ownedPrices[id] = { purchaseTenths };
  }

  return {
    finance: {
      version: 2,
      bankTenths,
      ownedPrices,
      priceBasis: prevFinance ? prevFinance.priceBasis : (opts?.priceBasis ?? "manual"),
      marketPriceAsOf: opts?.marketPriceAsOf ?? prevFinance?.marketPriceAsOf,
      lineupGameweek: prevFinance?.lineupGameweek,
    },
    proceedsTenths,
    costTenths,
  };
}

export interface AffordabilityCheck {
  affordable: boolean;
  shortfallTenths: number;
  availableTenths: number;
  costTenths: number;
}

// Whether a proposed set of removals/additions fits inside bank + the
// selling value of what's being sold -- the only thing that makes a squad
// edit legal in FPL. Never used to judge a squad that hasn't changed.
export function checkAffordability(
  finance: SquadFinance,
  removed: PlayerRecord[],
  added: PlayerRecord[],
): AffordabilityCheck {
  let proceedsTenths = 0;
  for (const player of removed) {
    const owned = finance.ownedPrices[player.element];
    const currentTenths = toTenths(player.value_m);
    proceedsTenths += owned ? sellingPriceTenths(owned.purchaseTenths, currentTenths) : currentTenths;
  }
  const costTenths = added.reduce((sum, player) => sum + toTenths(player.value_m), 0);
  const availableTenths = finance.bankTenths + proceedsTenths;
  const shortfallTenths = Math.max(0, costTenths - availableTenths);
  return {
    affordable: shortfallTenths === 0,
    shortfallTenths,
    availableTenths,
    costTenths,
  };
}
