"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { ClubCrest } from "@/components/club-crest";
import type { FixtureRecord, TeamRecord } from "@/lib/types";
import { Skeleton } from "@/components/skeleton";
import { Fdr, GateSign } from "@/components/signage";
import { clubStyle } from "@/lib/club-colors";

// A gameweek can hold more than one fixture for a club. Keying a Map on the
// gameweek keeps only the last of them, which silently hides the other from
// the matrix and drops it from the difficulty average. The current fixture
// list has no doubles -- it is the schedule as first published -- but they
// appear every season once postponements are rearranged.
function groupByGameweek(team: TeamRecord): Map<number, FixtureRecord[]> {
  const byGw = new Map<number, FixtureRecord[]>();
  for (const fixture of team.fixtures) {
    const existing = byGw.get(fixture.gameweek);
    if (existing) existing.push(fixture);
    else byGw.set(fixture.gameweek, [fixture]);
  }
  return byGw;
}

function averageDifficulty(team: TeamRecord, gameweeks: number[]): number | null {
  const byGw = groupByGameweek(team);
  // Every fixture counts, so a club with a double in the window is averaged
  // over nine matches rather than eight.
  const values = gameweeks.flatMap((gw) => (byGw.get(gw) ?? []).map((f) => f.difficulty));
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
          <Skeleton variant="table" count={20} />
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

  const lastGw = gameweeks[gameweeks.length - 1] ?? startGw;
  const runWord = (avg: number) => (avg <= 2.6 ? "a kind run" : avg <= 3 ? "a fair run" : "a mixed run");

  return (
    <section className="page fixtures-page" aria-label="Fixtures">
      <GateSign lede={`Every club's games from gameweek ${startGw} to ${lastGw}, coloured by how hard they are. Greener is easier.`}>
        <span className="switch-row">
          <button
            type="button"
            className="switch"
            role="switch"
            aria-checked={squadOnly}
            aria-labelledby="squad-only-label"
            disabled={squadPlayers.length === 0}
            onClick={() => setSquadOnly((v) => !v)}
          />
          <span id="squad-only-label">Only my squad&apos;s clubs</span>
        </span>
      </GateSign>

      {runs.length > 0 && (
        <section className="section" aria-label="Easiest runs">
          <div className="section-title">
            <div>
              <h2>Easiest runs</h2>
              <p>The clubs whose next {gameweeks.length} games look friendliest. Good places to look for players.</p>
            </div>
          </div>
          <ol className="runs stagger">
            {runs.map(({ team, avg }, index) => {
              const next = team.fixtures
                .filter((fixture) => gameweeks.includes(fixture.gameweek))
                .sort((a, b) => a.gameweek - b.gameweek)
                .slice(0, 4);
              return (
                <li key={team.id} className="run" style={{ ...clubStyle(team.name), "--i": index } as React.CSSProperties}>
                  <span className="run-rank">{index + 1}</span>
                  <ClubCrest code={team.code} team={team.name} shortName={team.short_name} width={56} height={56} className="run-crest" />
                  <div className="run-copy">
                    <b>{team.name}</b>
                    <span>
                      {runWord(avg)}, averaging {avg.toFixed(1)} out of 5
                    </span>
                  </div>
                  <div className="run-next">
                    {next.map((fixture) => (
                      <Fdr key={`${fixture.gameweek}-${fixture.opponent}`} fixture={fixture} />
                    ))}
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      )}

      <section className="section" aria-label="Fixture matrix">
        <div className="section-title">
          <div>
            <h2>All clubs</h2>
            <p>Each cell shows the opponent, H for home or A for away, and the difficulty from 1 (easiest) to 5.</p>
          </div>
          <ul className="fdr-key" aria-label="Difficulty key">
            {[1, 2, 3, 4, 5].map((fdr) => (
              <li key={fdr}>
                <span className={`fdr fdr--${fdr} fdr-key-swatch`}>{fdr}</span>
              </li>
            ))}
            <li>
              <span className="fdr fdr--blank fdr-key-swatch">No game</span>
            </li>
          </ul>
        </div>
        <div className={`matrix-frame${matrixScroll.canScroll && !matrixScroll.atEnd ? " has-more" : ""}`}>
          <div
            className={`matrix-reel${matrixScroll.scrolled ? " is-scrolled" : ""}`}
            ref={matrixReelRef}
            onScroll={(event) => syncMatrixScroll(event.currentTarget)}
            tabIndex={0}
            aria-label="Fixture matrix. Scroll sideways for later gameweeks."
          >
            <table className="matrix" style={{ "--weeks": gameweeks.length } as React.CSSProperties}>
              <thead>
                <tr>
                  <th scope="col" className="matrix-club">Club</th>
                  {gameweeks.map((gw) => (
                    <th scope="col" key={gw}>
                      GW{gw}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {teams.map((team) => {
                  const byGw = groupByGameweek(team);
                  const owned = squadTeamNames.has(team.name);
                  return (
                    <tr key={team.id}>
                      <th scope="row" className="matrix-club">
                        <span className="matrix-club-inner">
                          <ClubCrest code={team.code} team={team.name} shortName={team.short_name} width={24} height={24} />
                          <span>{team.short_name}</span>
                          {owned && <span className="matrix-owned" title="You have players from this club" />}
                        </span>
                      </th>
                      {gameweeks.map((gw) => {
                        const matches = byGw.get(gw) ?? [];
                        if (matches.length === 0) {
                          return (
                            <td key={gw}>
                              <span className="fdr fdr--blank cell">No game</span>
                            </td>
                          );
                        }
                        return (
                          <td key={gw}>
                            <span className={`cell-stack${matches.length > 1 ? " is-double" : ""}`}>
                              {matches.map((fixture, i) => (
                                <span key={`${fixture.opponent}-${i}`} className={`fdr fdr--${fixture.difficulty} cell`}>
                                  {fixture.opponent}
                                  <small>{fixture.venue}</small>
                                  <span className="sr-only">, difficulty {fixture.difficulty}</span>
                                </span>
                              ))}
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </section>
  );
}
