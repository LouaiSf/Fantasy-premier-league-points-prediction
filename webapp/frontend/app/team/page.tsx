"use client";

import * as React from "react";
import { useApp } from "@/components/providers/app-provider";
import { api, refreshDataAndPredictions } from "@/lib/api";
import { money } from "@/lib/format";
import { fromTenths, sellingPricesTenthsForSquad } from "@/lib/finance";
import { previewSquad } from "@/lib/squad";
import { isFlagged, nextFixtureFor, whyLine } from "@/lib/why";
import { Pitch } from "@/components/team/pitch";
import { SquadEditor } from "@/components/team/squad-editor";
import { Skeleton } from "@/components/skeleton";
import { ManagerSearch } from "@/components/team/manager-search";
import { TeamPlan, planMoves, playerName, recommendationOf } from "@/components/team/team-plan";
import { DeadlineBoard } from "@/components/team/deadline-board";
import { DataPortability } from "@/components/team/data-portability";
import { Face, GateSign, PlateFact, Pos, Proj, Track, VerdictPlate } from "@/components/signage";
import { Icon } from "@/components/icons";
import type { PlayerRecord, TransferResult, TransferRow } from "@/lib/types";

// The FPL budget every manager starts a season with.
const BUDGET = 100.0;

export default function TeamPage() {
  const {
    snapshot,
    loading,
    error,
    squadPlayers,
    squadElements,
    teamResult,
    setTeamResult,
    setImportedTeam,
    storedSquad,
    financeSummary,
    toast,
    openProfile,
    reload,
  } = useApp();
  const [picking, setPicking] = React.useState(false);
  const [liningUp, setLiningUp] = React.useState(false);
  const [refreshingPrices, setRefreshingPrices] = React.useState(false);
  const [freeTransfers, setFreeTransfers] = React.useState(1);
  const [plannerBank, setPlannerBank] = React.useState<number | null>(null);
  const [transferPlan, setTransferPlan] = React.useState<TransferResult | null>(null);
  const [transferPlanError, setTransferPlanError] = React.useState<string | null>(null);
  const [transferPlanLoading, setTransferPlanLoading] = React.useState(false);
  const [importOpen, setImportOpen] = React.useState(false);
  // Date.now() is impure, so it's captured once via a lazy initializer
  // (matching DeadlineClock) rather than called directly in render.
  const [now] = React.useState(() => Date.now());

  const plannerBankValue = plannerBank ?? Math.max(0, fromTenths(financeSummary.bankTenths));

  React.useEffect(() => {
    if (!snapshot?.prediction_available || squadElements.length !== 15) return;

    let active = true;
    const sellingPrices = sellingPricesTenthsForSquad(squadPlayers, storedSquad?.finance ?? null);
    void Promise.resolve().then(() => {
      if (!active) return null;
      setTransferPlanLoading(true);
      setTransferPlanError(null);
      return api.transfers({
        elements: squadElements,
        free: freeTransfers,
        bank: plannerBankValue,
        max: freeTransfers,
        selling_prices_tenths: sellingPrices,
      });
    }).then((result) => {
      if (!result) return;
      if (active) setTransferPlan(result);
    }).catch((err: Error) => {
      if (active) {
        setTransferPlan(null);
        setTransferPlanError(err.message);
      }
    }).finally(() => {
      if (active) setTransferPlanLoading(false);
    });

    return () => {
      active = false;
    };
  }, [snapshot, squadElements, squadPlayers, storedSquad, freeTransfers, plannerBankValue]);

  const byElement = React.useMemo(
    () => new Map((snapshot?.players ?? []).map((player) => [player.element, player])),
    [snapshot],
  );

  if (loading) {
    return (
      <section className="page">
        <div className="skel skel-sign" />
        <Skeleton variant="hero" />
        <div className="cols">
          <Skeleton variant="pitch" />
          <Skeleton variant="row" count={6} />
        </div>
      </section>
    );
  }

  if (error || !snapshot) {
    return (
      <section className="page">
        <div className="empty-state">
          <h2 className="empty-title">We couldn&apos;t load the season</h2>
          <p className="empty-message">The data service didn&apos;t answer. Check it&apos;s running, then try again.</p>
          {error && <p className="note">{error}</p>}
          <button className="btn" type="button" onClick={reload}>Try again</button>
        </div>
      </section>
    );
  }

  const hasSquad = squadPlayers.length === 15;
  const preview = teamResult ?? previewSquad(squadPlayers);
  const predictionAvailable = snapshot.prediction_available;
  // A squad's current market value and its selling value diverge as soon as
  // any player's price moves -- an appreciated squad is not over budget.
  const bank = fromTenths(financeSummary.bankTenths);
  const sellingValue = fromTenths(financeSummary.sellingValueTenths);
  const marketPricesUpdatedAt = snapshot.market_prices_updated_at
    ? new Date(snapshot.market_prices_updated_at)
    : null;
  const marketStale = Boolean(
    marketPricesUpdatedAt && now - marketPricesUpdatedAt.getTime() > 24 * 60 * 60 * 1000,
  );
  const flagged = squadPlayers.filter(isFlagged);
  const clubCounts = new Map<string, number>();
  for (const player of squadPlayers) clubCounts.set(player.team, (clubCounts.get(player.team) ?? 0) + 1);
  const [busiestClub, busiestCount] = [...clubCounts.entries()].sort((a, b) => b[1] - a[1])[0] ?? ["", 0];

  const recommendation = recommendationOf(transferPlan);
  const moves = recommendation && hasSquad ? planMoves(recommendation, squadPlayers, byElement) : null;
  const holding = !recommendation || recommendation.transfers === 0 || !moves || (!moves.outPlayers.length && !moves.inPlayers.length);
  const captain = moves?.captain ?? preview?.captain ?? null;

  async function refreshPrices() {
    setRefreshingPrices(true);
    try {
      toast((await refreshDataAndPredictions()) || "Latest prices, news and projections are in.");
      reload();
    } catch (err) {
      toast(`Couldn't refresh: ${(err as Error).message}`);
    } finally {
      setRefreshingPrices(false);
    }
  }

  async function autoPick() {
    setPicking(true);
    try {
      const result = await api.squad({ budget: BUDGET, lock: [], ban: [] });
      setTeamResult(result, "reset");
      toast("Here's the best £100m squad for this gameweek.");
    } catch (err) {
      toast((err as Error).message);
    } finally {
      setPicking(false);
    }
  }

  async function optimiseLineup() {
    if (!hasSquad) {
      toast("Add all 15 players first.");
      return;
    }
    setLiningUp(true);
    try {
      const result = await api.lineup({ elements: squadElements });
      setTeamResult(result, "lineup");
      toast("Lineup, bench order and armbands updated.");
    } catch (err) {
      toast((err as Error).message);
    } finally {
      setLiningUp(false);
    }
  }

  function applyTransferPlan(row: TransferRow) {
    setTeamResult(row, row.transfers === 0 ? "lineup" : "transfer");
    setPlannerBank(row.bank_after);
    toast(row.transfers === 0 ? "Lineup applied." : "Plan applied to My team.");
  }

  const planUnavailable = !snapshot.prediction_available || !hasSquad;
  const planError = planUnavailable
    ? !snapshot.prediction_available
      ? snapshot.prediction_error ?? "Projections aren't available right now."
      : "Add all 15 players to get a plan."
    : transferPlanError;

  const importedName = storedSquad?.source === "manager" ? storedSquad.sourceTeamName || "Your FPL team" : null;
  const lede = importedName
    ? <>{importedName}, brought in from FPL. Everything here is worked out for this fifteen.</>
    : undefined;

  const showImport = importOpen || !hasSquad;

  return (
    <section className="page team-page" aria-label="My team">
      <GateSign lede={lede}>
        <button
          className="btn btn--line"
          type="button"
          aria-expanded={showImport}
          aria-controls="fpl-import"
          onClick={() => setImportOpen((open) => !open)}
          disabled={!hasSquad}
        >
          {importedName ? "Switch team" : "Bring in my FPL team"}
        </button>
        <SquadEditor />
      </GateSign>

      {showImport && (
        <div id="fpl-import" className="panel import-panel">
          <ManagerSearch
            snapshot={snapshot}
            onImport={(lineup) => {
              if (!setImportedTeam(lineup)) return false;
              setPlannerBank(lineup.bank ?? 0);
              setImportOpen(false);
              toast(`${lineup.manager.team_name || "Your team"} is now your team here.`);
              return true;
            }}
          />
        </div>
      )}

      {!hasSquad ? (
        <VerdictPlate
          tone="night"
          title="Let's get your team in."
          body="Paste your FPL team link or entry ID above, or let us pick the best £100m squad for this gameweek to start from."
          actions={
            <button className="btn btn--go" type="button" disabled={!predictionAvailable || picking} onClick={autoPick}>
              {picking ? "Picking…" : "Pick a squad for me"} <Icon name="arrow-right" size={18} />
            </button>
          }
          label="Getting started"
        />
      ) : !predictionAvailable ? (
        <VerdictPlate
          tone="night"
          title="Projections are on their way."
          body={`${snapshot.prediction_error ?? "This week's projections aren't ready yet."} Your squad, prices and news still work.`}
          label="This week's call"
        />
      ) : transferPlanLoading && !recommendation ? (
        <VerdictPlate tone="matchday" busy title="Working out your best move…" body="Checking every legal transfer against your fifteen." label="This week's call" />
      ) : recommendation && moves ? (
        <VerdictPlate
          tone={holding ? "matchday" : "spotlight"}
          label="This week's call"
          player={holding ? captain : moves.inPlayers[0] ?? captain}
          title={
            holding ? (
              <>Hold your transfer. Captain {playerName(captain)}.</>
            ) : moves.inPlayers.length === 1 ? (
              <>Bring in {playerName(moves.inPlayers[0])} for {playerName(moves.outPlayers[0])}.</>
            ) : (
              <>Make {moves.inPlayers.length} transfers this week.</>
            )
          }
          body={
            holding
              ? "Nothing on the market beats your squad by enough to be worth a transfer. Keep the free one for next week."
              : `It's worth about ${Math.max(0, recommendation.gain).toFixed(1)} more points this week, after any hit. Then give ${playerName(captain)} the armband.`
          }
          facts={
            <>
              <PlateFact label="Your XI this week">{recommendation.xi_points.toFixed(1)} pts</PlateFact>
              <PlateFact label="In the bank after">{money(recommendation.bank_after)}</PlateFact>
              {holding && <PlateFact label="Free transfers next week">{Math.min(5, freeTransfers + 1)}</PlateFact>}
            </>
          }
          actions={
            <>
              <button className="btn btn--go" type="button" onClick={() => applyTransferPlan(recommendation)} disabled={recommendation.squad.length !== 15}>
                {holding ? "Use this lineup" : "Apply this plan"} <Icon name="arrow-right" size={18} />
              </button>
              <a className="btn btn--line" href="#plan">See the full plan</a>
            </>
          }
        />
      ) : (
        <VerdictPlate
          tone="night"
          title="Your team is in."
          body={planError ?? "We couldn't build a plan this time. Your lineup below still works."}
          label="This week's call"
        />
      )}

      <div className="cols team-cols">
        <section className="panel pitch-panel" aria-label="Starting eleven">
          <div className="panel-head">
            <div>
              <h2>Starting XI</h2>
              <p>{preview ? `${preview.formation} · tap a player for their profile` : "Add 15 players to see your lineup"}</p>
            </div>
            <button
              className="btn btn--sm"
              type="button"
              disabled={!predictionAvailable || !hasSquad || liningUp}
              onClick={optimiseLineup}
            >
              {liningUp ? "Picking…" : "Pick my best XI"}
            </button>
          </div>
          <Pitch />
          {preview && "bench" in preview && preview.bench.length > 0 && (
            <div className="bench-strip" aria-label="Bench, in order">
              <span className="bench-strip-label">Bench</span>
              {preview.bench.map((player, index) => (
                <button key={player.element} type="button" className="bench-chip" onClick={() => openProfile(player)}>
                  <span className="bench-order">{index + 1}</span>
                  <Face player={player} size="sm" />
                  <span className="prow-name">
                    <b>{player.web_name || player.name}</b>
                    <span>{player.position}</span>
                  </span>
                  <Proj value={predictionAvailable ? player.predicted_points : player.form} />
                </button>
              ))}
            </div>
          )}
        </section>

        <div className="side-stack">
          <DeadlineBoard />

          {hasSquad && (
            <section className="panel" aria-label="Squad limits">
              <div className="panel-head">
                <h2>Limits</h2>
              </div>
              <div className="panel-body">
                <Track label="Free transfers" value={freeTransfers} max={5} display={`${freeTransfers} of 5`} />
                <Track
                  label={`Most from one club (${busiestClub})`}
                  value={busiestCount}
                  max={3}
                  display={`${busiestCount} of 3`}
                />
                <Track
                  label="Fit to play"
                  value={squadPlayers.length - flagged.length}
                  max={15}
                  display={`${squadPlayers.length - flagged.length} of 15`}
                  warnAt={Infinity}
                />
                <p className="note">
                  <b className="money-line">{money(bank)} in the bank</b> · squad sells for {money(sellingValue)}
                  {financeSummary.priceBasis === "estimated" ? " (estimated: we don't have every purchase price)" : ""}.
                </p>
                {marketStale && (
                  <p className="note note--warn">
                    Prices are more than a day old.{" "}
                    <button type="button" className="text-link" onClick={() => void refreshPrices()} disabled={refreshingPrices}>
                      {refreshingPrices ? "Refreshing…" : "Get the latest"}
                    </button>
                  </p>
                )}
                {snapshot.predictions_older_than_market && (
                  <p className="note">Projections were made before the last price change, so they may lag a little.</p>
                )}
              </div>
            </section>
          )}

          {flagged.length > 0 && (
            <section className="panel" aria-label="Flagged players">
              <div className="panel-head">
                <h2>Flagged</h2>
                <span className="badge badge--alert">{flagged.length}</span>
              </div>
              <div>
                {flagged.map((player: PlayerRecord) => (
                  <button key={player.element} type="button" className="prow" onClick={() => openProfile(player)}>
                    <Face player={player} />
                    <span className="prow-name">
                      <b>{player.web_name || player.name}</b>
                      <span className="why is-flag">{whyLine(player, nextFixtureFor(snapshot, player))}</span>
                    </span>
                    <Pos pos={player.position} />
                    <Icon name="chevron-right" size={18} />
                  </button>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>

      {hasSquad && (
        <TeamPlan
          analysis={transferPlan}
          freeTransfers={freeTransfers}
          onFreeTransfersChange={setFreeTransfers}
          bank={plannerBankValue}
          onBankChange={(value) => setPlannerBank(Math.max(0, Math.min(100, Math.round(value * 10) / 10)))}
          loading={transferPlanLoading}
          error={planError}
          onApply={applyTransferPlan}
        />
      )}

      <details className="disclosure">
        <summary>
          More tools
          <small>Start from scratch, or move your data to another device</small>
          <Icon name="chevron-down" size={18} />
        </summary>
        <div className="disclosure-body tools-grid">
          <div>
            <h3>Start from the best squad</h3>
            <p className="note">Replace your fifteen with the highest-projected £100m squad for this gameweek.</p>
            <button className="btn btn--line btn--sm" type="button" disabled={!predictionAvailable || picking} onClick={autoPick}>
              {picking ? "Picking…" : "Pick a fresh squad"}
            </button>
          </div>
          <div>
            <h3>Your data</h3>
            <DataPortability />
          </div>
        </div>
      </details>
    </section>
  );
}
