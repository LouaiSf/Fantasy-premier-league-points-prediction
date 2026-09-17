"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { ClubCrest } from "@/components/club-crest";
import type { TeamRecord } from "@/lib/types";
import { Loading } from "@/components/loading";

function averageDifficulty(team: TeamRecord, gameweeks: number[]): number | null {
  const byGw = new Map(team.fixtures.map((fixture) => [fixture.gameweek, fixture]));
  const values = gameweeks.map((gw) => byGw.get(gw)?.difficulty).filter((v): v is number => v != null);
  if (!values.length) return null;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

export default function FixturesPage() {
  const { snapshot, loading, squadPlayers } = useApp();
  const [squadOnly, setSquadOnly] = React.useState(false);
  const matrixReelRef = React.useRef<HTMLDivElement>(null);
  const [matrixScroll, setMatrixScroll] = React.useState({
    canScroll: false,
    atEnd: true,
    scrolled: false,
  });

  const syncMatrixScroll = React.useCallback((reel: HTMLDivElement) => {
    const next = {
      canScroll: reel.scrollWidth > reel.clientWidth + 1,
      atEnd: reel.scrollLeft + reel.clientWidth >= reel.scrollWidth - 1,
      scrolled: reel.scrollLeft > 1,
    };
    setMatrixScroll((current) =>
      current.canScroll === next.canScroll &&
      current.atEnd === next.atEnd &&
      current.scrolled === next.scrolled
        ? current
        : next,
    );
  }, []);

  React.useEffect(() => {
    const reel = matrixReelRef.current;
    if (!reel) return;
    syncMatrixScroll(reel);
    const observer = new ResizeObserver(() => syncMatrixScroll(reel));
    observer.observe(reel);
    return () => observer.disconnect();
  }, [snapshot, squadOnly, syncMatrixScroll]);

  if (loading || !snapshot) {
    return (
      <section className="page">
        <div className="shell">
          <Loading label="Loading season data…" />
        </div>
      </section>
    );
  }

  const startGw = snapshot.gameweek ?? 1;
  const gameweeks = Array.from({ length: 8 }, (_, index) => startGw + index).filter(
    (gw) => gw <= 38,
  );
  const squadTeamNames = new Set(squadPlayers.map((player) => player.team));
  const teams = snapshot.teams.filter((team) => !squadOnly || squadTeamNames.has(team.name));

  const runs = [...snapshot.teams]
    .map((team) => ({ team, avg: averageDifficulty(team, gameweeks) }))
    .filter((entry): entry is { team: TeamRecord; avg: number } => entry.avg != null)
    .sort((a, b) => a.avg - b.avg)
    .slice(0, 4);

  return (
    <section className="page fix-page">
      <div className="shell">
        <div className="section-head">
          <div>
            <p className="eyebrow" style={{ color: "var(--lime)" }}>
              {gameweeks.length}-week horizon // GW{startGw}–{gameweeks[gameweeks.length - 1] ?? startGw}
            </p>
            <h1>Fixture matrix</h1>
          </div>
          <p>
            Difficulty and venue for every club in one field of colour, straight from the
            season&apos;s fixture list.
          </p>
        </div>

        <div className="fix-toolbar">
          <label className="switch-wrap">
            <button
              type="button"
              className="switch"
              role="switch"
              aria-checked={squadOnly}
              aria-label="Show only my squad clubs"
              disabled={squadPlayers.length === 0}
              onClick={() => setSquadOnly((v) => !v)}
            />
            <span>
              Show only my squad clubs{squadPlayers.length === 0 ? " (set a squad first)" : ""}
            </span>
          </label>
        </div>

        {runs.length > 0 && (
          <div className="runs">
            {runs.map(({ team, avg }) => (
              <div className="run-card" key={team.id}>
                <p className="kicker">Easiest run</p>
                <b>
                  <ClubCrest
                    code={team.code}
                    team={team.name}
                    shortName={team.short_name}
                    width={24}
                    height={24}
                  />
                  {team.short_name}
                </b>
                <p>Average FDR {avg.toFixed(1)} across the next {gameweeks.length} gameweeks.</p>
              </div>
            ))}
          </div>
        )}

        <div
          className={`matrix-frame${matrixScroll.canScroll ? " can-scroll" : ""}${matrixScroll.atEnd ? " at-end" : ""}`}
        >
          {matrixScroll.canScroll && <span className="scroll-cue">Scroll for later GWs →</span>}
          <div
            className={`matrix-reel${matrixScroll.scrolled ? " is-scrolled" : ""}`}
            ref={matrixReelRef}
            onScroll={(event) => syncMatrixScroll(event.currentTarget)}
            tabIndex={0}
            aria-label="Fixture difficulty matrix. Scroll horizontally for later gameweeks."
          >
            <div className="matrix" style={{ "--weeks": gameweeks.length } as React.CSSProperties}>
              <div className="mhead">
                <span>Club</span>
              </div>
              {gameweeks.map((gw) => (
                <div className="mhead" key={gw}>
                  GW{gw}
                </div>
              ))}
              {teams.map((team) => {
                const byGw = new Map(team.fixtures.map((fixture) => [fixture.gameweek, fixture]));
                return (
                  <React.Fragment key={team.id}>
                    <div className="club-cell">
                      <ClubCrest
                        code={team.code}
                        team={team.name}
                        shortName={team.short_name}
                        width={24}
                        height={24}
                      />
                      <span>{team.short_name}</span>
                    </div>
                    {gameweeks.map((gw) => {
                      const fixture = byGw.get(gw);
                      if (!fixture) {
                        return (
                          <div className="fcell blank" key={gw}>
                            <span>–</span>
                            <small>Blank</small>
                          </div>
                        );
                      }
                      return (
                        <div className="fcell" data-fdr={fixture.difficulty} key={gw}>
                          {fixture.opponent}
                          <small>{fixture.venue}</small>
                        </div>
                      );
                    })}
                  </React.Fragment>
                );
              })}
            </div>
          </div>
        </div>

        <div className="fix-legend">
          {[1, 2, 3, 4, 5].map((fdr) => (
            <span className="legend-item" key={fdr}>
              <i className="legend-dot" style={{ background: `var(--fdr-${fdr})` }} />
              {fdr} {fdr === 1 ? "easiest" : fdr === 5 ? "hardest" : ""}
            </span>
          ))}
          <span className="legend-item">
            <i
              className="legend-dot"
              style={{ background: "repeating-linear-gradient(135deg,#8a858b 0 4px,#aaa5ab 4px 8px)" }}
            />
            Blank
          </span>
        </div>
      </div>
    </section>
  );
}
