"use client";

import * as React from "react";
import { api } from "@/lib/api";
import type { OwnershipReport, OwnershipTier } from "@/lib/types";

const TIER_STORAGE_KEY = "fpl-assistant-eo-tier";
export const OWNERSHIP_TIERS: { key: OwnershipTier; label: string }[] = [
  { key: "top10k", label: "Top 10k" },
  { key: "top1k", label: "Top 1k" },
  { key: "overall", label: "Overall" },
];

export interface PlayerOwnership {
  /** EO for the gameweek ahead: the estimate when the sample is from an earlier one. */
  eo: number;
  captain: number;
  owned: number;
}

interface OwnershipContextValue {
  tier: OwnershipTier;
  setTier: (tier: OwnershipTier) => void;
  report: OwnershipReport | null;
  error: string | null;
  loading: boolean;
  /** null when there is no sample, or the player is in no sampled team (EO 0). */
  forPlayer: (element: number) => PlayerOwnership | null;
}

const OwnershipContext = React.createContext<OwnershipContextValue | null>(null);

function readTier(): OwnershipTier {
  try {
    const stored = window.localStorage.getItem(TIER_STORAGE_KEY);
    if (stored && OWNERSHIP_TIERS.some((tier) => tier.key === stored)) return stored as OwnershipTier;
  } catch {
    /* storage blocked: default tier */
  }
  return "top10k";
}

export function OwnershipProvider({ children }: { children: React.ReactNode }) {
  const [tier, setTierState] = React.useState<OwnershipTier>("top10k");
  const [report, setReport] = React.useState<OwnershipReport | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => setTierState(readTier()), []);

  React.useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    api.ownership(tier, controller.signal).then(
      (result) => {
        setReport(result);
        setError(null);
        setLoading(false);
      },
      (err: Error) => {
        if (controller.signal.aborted) return;
        setReport(null);
        setError(err.message);
        setLoading(false);
      },
    );
    return () => controller.abort();
  }, [tier]);

  const setTier = React.useCallback((next: OwnershipTier) => {
    setTierState(next);
    try {
      window.localStorage.setItem(TIER_STORAGE_KEY, next);
    } catch {
      /* storage blocked: the choice lasts this visit */
    }
  }, []);

  const forPlayer = React.useCallback(
    (element: number): PlayerOwnership | null => {
      if (!report) return null;
      const row = report.players[String(element)];
      if (!row) return { eo: 0, captain: 0, owned: 0 };
      return { eo: row.eo_estimate_pct ?? row.eo_pct, captain: row.captain_pct, owned: row.owned_pct };
    },
    [report],
  );

  const value = React.useMemo(
    () => ({ tier, setTier, report, error, loading, forPlayer }),
    [tier, setTier, report, error, loading, forPlayer],
  );
  return <OwnershipContext.Provider value={value}>{children}</OwnershipContext.Provider>;
}

export function useOwnership(): OwnershipContextValue {
  const context = React.useContext(OwnershipContext);
  if (!context) throw new Error("useOwnership must be used inside OwnershipProvider");
  return context;
}

/** "Top 10k · 999 managers · GW7 teams, estimated for GW8" */
export function ownershipCaption(report: OwnershipReport | null, tierLabel: string): string {
  if (!report) return `${tierLabel} · no sample yet`;
  const basis = `GW${report.basis_gw} teams`;
  const estimate = report.is_estimate ? `, estimated for GW${report.target_gw}` : "";
  return `${tierLabel} · ${report.sample_size.toLocaleString()} managers · ${basis}${estimate}`;
}

export function TierSelect() {
  const { tier, setTier, report } = useOwnership();
  const label = OWNERSHIP_TIERS.find((item) => item.key === tier)?.label ?? tier;
  return (
    <div className="eo-tier">
      <div className="horizon-tabs" role="group" aria-label="Ownership sample">
        {OWNERSHIP_TIERS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={tier === item.key ? "is-active" : ""}
            aria-pressed={tier === item.key}
            onClick={() => setTier(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <span className="kicker">{ownershipCaption(report, label)}</span>
    </div>
  );
}
