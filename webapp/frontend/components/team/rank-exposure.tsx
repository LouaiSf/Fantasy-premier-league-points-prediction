"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { TierSelect, useOwnership } from "@/components/providers/ownership-provider";
import { DeltaBar } from "@/components/charts/delta-bar";
import { CountUp } from "@/components/motion/count-up";
import type { PlayerRecord, SquadResult } from "@/lib/types";

interface Exposure {
  player: PlayerRecord;
  mine: number;        // your multiplier: bench 0, XI 1, captain 2
  owned: boolean;
  eo: number;          // percent
  points: number;      // projected this gameweek
  swing: number;       // (mine - eo/100) x points: your gain vs the field if he hits his projection
}

const SHOWN = 5;

/**
 * Where this gameweek's rank is won or lost. Against the field a player moves
 * your rank by (your multiplier - EO) x his points, so an owned-but-benched
 * 150% EO captain choice is a bigger risk than any differential is a chance.
 */
export function RankExposure({ lineup }: { readonly lineup: Pick<SquadResult, "xi" | "bench" | "captain"> | null }) {
  const { snapshot } = useApp();
  const teamResult = lineup;
  const { report, error, forPlayer } = useOwnership();

  const exposures = React.useMemo(() => {
    if (!snapshot || !teamResult || !report) return [];
    const mine = new Map<number, number>();
    for (const player of teamResult.xi) mine.set(player.element, 1);
    for (const player of teamResult.bench) mine.set(player.element, 0);
    if (teamResult.captain) mine.set(teamResult.captain.element, 2);
    const out: Exposure[] = [];
    for (const player of snapshot.players) {
      const ownership = forPlayer(player.element);
      const m = mine.get(player.element) ?? 0;
      const points = player.predicted_points ?? 0;
      if (!ownership || (ownership.eo === 0 && !mine.has(player.element)) || points <= 0) continue;
      out.push({ player, mine: m, owned: mine.has(player.element), eo: ownership.eo, points,
                 swing: (m - ownership.eo / 100) * points });
    }
    return out;
  }, [snapshot, teamResult, report, forPlayer]);

  if (!teamResult) return null;
  if (error && !report) {
    return (
      <section className="rank-exposure shell" aria-label="Rank exposure">
        <div className="rank-exposure-head">
          <h2>Rank exposure</h2>
          <TierSelect />
        </div>
        <p className="rank-exposure-empty">No ownership sample for this tier yet.</p>
      </section>
    );
  }
  if (!report) return null;

  const threats = exposures.filter((e) => e.swing < 0).sort((a, b) => a.swing - b.swing).slice(0, SHOWN);
  const differentials = exposures.filter((e) => e.swing > 0).sort((a, b) => b.swing - a.swing).slice(0, SHOWN);
  const net = exposures.reduce((sum, e) => sum + e.swing, 0);
  const scale = Math.max(1, ...[...threats, ...differentials].map((e) => Math.abs(e.swing)));

  const row = (e: Exposure, index: number) => (
    <li key={e.player.element} className="rank-exposure-row lift" style={{ "--i": index } as React.CSSProperties}>
      <div className="rank-exposure-who">
        <b>{e.player.web_name || e.player.name}</b>
        <span className="kicker">
          EO {Math.round(e.eo)}% · {e.mine === 2 ? "your captain" : e.mine === 1 ? "you start" : e.owned ? "on your bench" : "not owned"}
          {" "}· {e.points.toFixed(1)} pts
        </span>
      </div>
      <DeltaBar value={e.swing} max={scale} />
    </li>
  );

  return (
    <section className="rank-exposure shell" aria-label="Rank exposure">
      <div className="rank-exposure-head">
        <div>
          <p className="eyebrow muted">Against the field</p>
          <h2>Rank exposure</h2>
        </div>
        <TierSelect />
      </div>
      <div className="rank-exposure-net">
        <span>Expected points vs the field this gameweek</span>
        <strong className={net >= 0 ? "is-positive" : "is-negative"}>
          <CountUp value={net} decimals={1} prefix={net >= 0 ? "+" : ""} />
        </strong>
      </div>
      <div className="rank-exposure-grid">
        <div>
          <h3>Threats</h3>
          <p className="rank-exposure-note">
            Owned by the field more than by you.
            {threats[0] && ` If ${threats[0].player.web_name || threats[0].player.name} scores his ${threats[0].points.toFixed(1)}-point projection, you lose ${Math.abs(threats[0].swing).toFixed(1)} on the field.`}
          </p>
          <ol className="stagger">{threats.map(row)}</ol>
        </div>
        <div>
          <h3>Differentials</h3>
          <p className="rank-exposure-note">Yours more than the field&apos;s: where you gain if they return.</p>
          <ol className="stagger">{differentials.map(row)}</ol>
        </div>
      </div>
    </section>
  );
}
