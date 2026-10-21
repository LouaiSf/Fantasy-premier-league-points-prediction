"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useApp } from "@/components/providers/app-provider";
import { api } from "@/lib/api";
import { fromTenths, sellingPricesTenthsForSquad, toTenths } from "@/lib/finance";
import { money, num, signed } from "@/lib/format";
import { isHeldWeek, isSavedScenario, isSavedTransferDraft, heldWeekKey, MAX_SCENARIOS, scenarioKey, scenarioStaleReason, squadFingerprint, transferDraftKey, type HeldWeek, type SavedScenario, type SavedTransferDraft, type TransferDraftPair } from "@/lib/transfer-planning";
import { validateSquad } from "@/lib/squad";
import type { PlayerRecord, SquadResult, TransferResult, TransferRow } from "@/lib/types";
import { Skeleton } from "@/components/skeleton";
import { Face, GateSign, Pos, Proj, Segmented } from "@/components/signage";
import { Icon } from "@/components/icons";
import { CountUp } from "@/components/motion/count-up";
import { m, AnimatePresence } from "motion/react";

const OUT_FILTERS = ["ALL", "GK", "DEF", "MID", "FWD", "FLAG"] as const;
const IN_FILTERS = ["ALL", "GK", "DEF", "MID", "FWD"] as const;

function flagged(player: PlayerRecord): boolean {
  return player.status !== "a" || (player.chance_of_playing_next_round ?? 100) < 100;
}
function nameOf(player: PlayerRecord | undefined): string {
  return player ? (player.web_name || player.name) : "Unknown player";
}
function score(result: SquadResult): number {
  return result.xi_points + Number(result.captain?.predicted_points ?? 0);
}
function PlayerRow({ player, selected, index, onClick }: {
  player: PlayerRecord; selected: boolean; index: number; onClick: () => void;
}) {
  return (
    <button type="button" className={"prow" + (selected ? " is-picked" : "")} aria-pressed={selected}
      data-player-id={player.element} onClick={onClick} style={{ "--i": index } as React.CSSProperties}>
      <Face player={player} />
      <span className="prow-name">
        <b>{nameOf(player)}</b>
        <span className={flagged(player) ? "why is-flag" : undefined}>
          {player.team_short} · {money(player.value_m)}{flagged(player) && player.news ? ` · ${player.news.split(" - ")[0]}` : ""}
        </span>
      </span>
      <Pos pos={player.position} />
      <Proj value={player.predicted_points ?? player.form} />
    </button>
  );
}

interface ScenarioResult { gross: number; net: number; hit: number; bank: number; captain: string }

function OptimizerCard({ row, byElement, onView, active }: {
  row: TransferRow; byElement: Map<number, PlayerRecord>; onView: () => void; active: boolean;
}) {
  return (
    <article className={"panel option" + (active ? " is-active" : "")}>
      <div className="option-head">
        <h3>{row.transfers} transfer{row.transfers === 1 ? "" : "s"}</h3>
        <b className={row.gain > 0 ? "is-up" : row.gain < 0 ? "is-down" : undefined}>{signed(row.gain)} pts</b>
      </div>
      <p className="note">
        {row.hit > 0 ? `Includes a ${row.hit}-point hit. ` : ""}
        {money(row.bank_after)} left in the bank.
      </p>
      {row.transfers > 0 && (
        <div className="option-moves">
          <span className="is-out"><small>Out</small>{row.out_elements.map((id) => nameOf(byElement.get(id))).join(", ")}</span>
          <span className="is-in"><small>In</small>{row.in_elements.map((id) => nameOf(byElement.get(id))).join(", ")}</span>
        </div>
      )}
      <button className="btn btn--line btn--sm" type="button" onClick={onView}>{active ? "Showing lineup" : "See the lineup"}</button>
    </article>
  );
}

export default function TransfersPage() {
  const router = useRouter();
  const { snapshot, loading, squadPlayers, squadElements, storedSquad, financeSummary, setTeamResult } = useApp();
  const [outQuery, setOutQuery] = React.useState("");
  const [inQuery, setInQuery] = React.useState("");
  const [outFilter, setOutFilter] = React.useState<(typeof OUT_FILTERS)[number]>("ALL");
  const [inFilter, setInFilter] = React.useState<(typeof IN_FILTERS)[number]>("ALL");
  const [draft, setDraft] = React.useState<TransferDraftPair[]>([]);
  const [pendingOut, setPendingOut] = React.useState<number | null>(null);
  const [pendingIn, setPendingIn] = React.useState<number | null>(null);
  const [editingIndex, setEditingIndex] = React.useState<number | null>(null);
  const [free, setFree] = React.useState(1);
  const [maxTransfers, setMaxTransfers] = React.useState(3);
  const [bankOverride, setBankOverride] = React.useState<number | null>(null);
  const [message, setMessage] = React.useState<string | null>(null);
  const [persistError, setPersistError] = React.useState<string | null>(null);
  const [evaluation, setEvaluation] = React.useState<{ lineup: SquadResult; baseline: SquadResult | null; hasPoints: boolean } | null>(null);
  const [bestAnalysis, setBestAnalysis] = React.useState<TransferResult | null>(null);
  const [lockedAnalysis, setLockedAnalysis] = React.useState<TransferResult | null>(null);
  const [analysisError, setAnalysisError] = React.useState<string | null>(null);
  const [analysing, setAnalysing] = React.useState(false);
  const [resultTab, setResultTab] = React.useState<"draft" | "best" | "scenarios">("draft");
  const [scenarios, setScenarios] = React.useState<SavedScenario[]>([]);
  const [scenarioResults, setScenarioResults] = React.useState<Record<string, ScenarioResult> | null>(null);
  const [comparing, setComparing] = React.useState(false);
  const [viewedRow, setViewedRow] = React.useState<TransferRow | null>(null);
  const [marketLimit, setMarketLimit] = React.useState(200);
  const [savedPlan, setSavedPlan] = React.useState<SavedTransferDraft | null>(null);
  const [heldWeek, setHeldWeek] = React.useState<HeldWeek | null>(null);
  const [showReview, setShowReview] = React.useState(false);

  const bankTenths = bankOverride ?? financeSummary.bankTenths;
  const fingerprint = snapshot ? squadFingerprint(snapshot.season, squadElements, storedSquad?.finance ?? null) : "";
  const sellPrices = sellingPricesTenthsForSquad(squadPlayers, storedSquad?.finance ?? null);
  const byElement = new Map((snapshot?.players ?? []).map((player) => [player.element, player]));
  const bankAfterTenths = bankTenths + draft.reduce((total, pair) => {
    const incoming = byElement.get(pair.in_element);
    return total + (sellPrices[pair.out_element] ?? 0) - (incoming ? toTenths(incoming.value_m) : 0);
  }, 0);
  const finalElements = squadElements.map((id) => draft.find((pair) => pair.out_element === id)?.in_element ?? id);
  const finalPlayers = finalElements.map((id) => byElement.get(id)).filter((player): player is PlayerRecord => player != null);
  const shapeError = validateSquad(finalPlayers);
  const duplicateDraft = new Set(draft.map((pair) => pair.out_element)).size !== draft.length ||
    new Set(draft.map((pair) => pair.in_element)).size !== draft.length ||
    draft.some((pair) => squadElements.includes(pair.in_element) || !squadElements.includes(pair.out_element));
  const draftError = pendingOut !== null ? (pendingIn === null ? "Pick a replacement on the right, then add the move." : "Add the move to line it up.") :
    draft.length > maxTransfers ? "Remove a move first to lower the limit." :
    duplicateDraft ? "Each player can only be in one move." :
    shapeError || (bankAfterTenths < 0 ? "These moves cost more than you have." : "");
  const canEvaluate = !draftError && pendingOut === null && draft.length <= maxTransfers && finalPlayers.length === 15;

  React.useEffect(() => {
    if (!snapshot || !fingerprint) return;
    try {
      const rawDraft = window.localStorage.getItem(transferDraftKey(snapshot.season));
      const parsedDraft: unknown = rawDraft ? JSON.parse(rawDraft) : null;
      setSavedPlan(isSavedTransferDraft(parsedDraft) && parsedDraft.season === snapshot.season ? parsedDraft : null);
      const rawHold = window.localStorage.getItem(heldWeekKey(snapshot.season));
      const parsedHold: unknown = rawHold ? JSON.parse(rawHold) : null;
      if (isHeldWeek(parsedHold) && parsedHold.season === snapshot.season &&
          (snapshot.gameweek == null || parsedHold.gameweek >= snapshot.gameweek)) {
        setHeldWeek(parsedHold);
      } else {
        window.localStorage.removeItem(heldWeekKey(snapshot.season));
        setHeldWeek(null);
      }
      const rawScenarios = window.localStorage.getItem(scenarioKey(snapshot.season));
      const parsedScenarios: unknown = rawScenarios ? JSON.parse(rawScenarios) : [];
      setScenarios(Array.isArray(parsedScenarios) ? parsedScenarios.filter(isSavedScenario).slice(0, MAX_SCENARIOS) : []);
    } catch {
      setPersistError("Saved transfer data could not be read. You can clear it from this device.");
    }
  }, [snapshot?.season, snapshot?.gameweek, fingerprint]);

  if (loading || !snapshot) return <section className="page">
    <div className="skel skel-sign" />
    <div className="skel-columns" style={{ "--cols": 2 } as React.CSSProperties}>
      <Skeleton variant="row" count={8} />
      <Skeleton variant="row" count={8} />
    </div>
  </section>;
  if (squadPlayers.length !== 15) return (
    <section className="page">
      <GateSign />
      <div className="empty-state">
        <h2 className="empty-title">Your squad comes first</h2>
        <p className="empty-message">Transfers work from a full fifteen. You have {squadPlayers.length} of 15 so far.</p>
        <a className="btn btn--go" href="/team">Go to My team <Icon name="arrow-right" size={18} /></a>
      </div>
    </section>
  );

  const currentSnapshot = snapshot;
  const excludedOut = new Set(draft.filter((_, index) => index !== editingIndex).map((pair) => pair.out_element));
  const excludedIn = new Set(draft.filter((_, index) => index !== editingIndex).map((pair) => pair.in_element));
  const outgoing = pendingOut === null ? null : byElement.get(pendingOut) ?? null;
  const incoming = pendingIn === null ? null : byElement.get(pendingIn) ?? null;
  const outRows = squadPlayers.filter((player) =>
    (outFilter === "ALL" || (outFilter === "FLAG" ? flagged(player) : player.position === outFilter)) &&
    !excludedOut.has(player.element) &&
    (player.name + " " + player.team).toLowerCase().includes(outQuery.trim().toLowerCase()));
  const marketRows = snapshot.players.filter((player) =>
    !squadElements.includes(player.element) && !excludedIn.has(player.element) &&
    (!outgoing || player.position === outgoing.position) &&
    (inFilter === "ALL" || player.position === inFilter) &&
    (player.name + " " + player.team).toLowerCase().includes(inQuery.trim().toLowerCase()))
    .sort((a, b) => Number(b.predicted_points ?? b.form ?? 0) - Number(a.predicted_points ?? a.form ?? 0));
  const hit = Math.max(0, draft.length - free) * 4;
  const sellTenths = outgoing ? sellPrices[outgoing.element] ?? toTenths(outgoing.value_m) : null;
  const previewDelta = sellTenths !== null && incoming ? sellTenths - toTenths(incoming.value_m) : null;
  const shownMarketRows = marketRows.slice(0, marketLimit);
  const holdMatches = heldWeek?.fingerprint === fingerprint && heldWeek.gameweek === snapshot.gameweek;

  function invalidate() {
    setEvaluation(null); setBestAnalysis(null); setLockedAnalysis(null);
    setViewedRow(null); setAnalysisError(null); setMessage(null);
  }
  function pickOut(player: PlayerRecord) {
    setPendingOut(player.element); setPendingIn(null); invalidate();
  }
  function pickIn(player: PlayerRecord) {
    setPendingIn(player.element); invalidate();
  }
  function stageMove() {
    if (pendingOut === null || pendingIn === null) { setMessage("Pick a player to sell and one to buy first."); return; }
    const pair = { out_element: pendingOut, in_element: pendingIn };
    setDraft((current) => editingIndex === null
      ? [...current, pair]
      : current.map((old, index) => index === editingIndex ? pair : old));
    setPendingOut(null); setPendingIn(null); setEditingIndex(null); invalidate();
  }
  function editMove(index: number) {
    const pair = draft[index]; setEditingIndex(index);
    setPendingOut(pair.out_element); setPendingIn(pair.in_element); setMessage(null);
    setEvaluation(null); setBestAnalysis(null); setLockedAnalysis(null);
  }
  function removeMove(index: number) {
    setDraft((current) => current.filter((_, i) => i !== index));
    if (editingIndex === index) { setEditingIndex(null); setPendingOut(null); setPendingIn(null); }
    invalidate();
  }
  function changeMax(next: number) {
    if (draft.length > next) { setMessage("Remove a move first to lower the limit."); return; }
    setMaxTransfers(next); invalidate();
  }
  function clearDraft() {
    setDraft([]); setPendingOut(null); setPendingIn(null); setEditingIndex(null); invalidate();
  }
  function reopenSaved() {
    if (!savedPlan || savedPlan.fingerprint !== fingerprint) return;
    setDraft(savedPlan.pairs); setMaxTransfers(savedPlan.max_transfers);
    setFree(savedPlan.free_transfers); setBankOverride(savedPlan.bank_tenths);
    setPendingOut(null); setPendingIn(null); invalidate();
  }
  function saveDraft() {
    const value: SavedTransferDraft = {
      version: 1, season: currentSnapshot.season, gameweek: currentSnapshot.gameweek, fingerprint,
      pairs: draft, max_transfers: maxTransfers, free_transfers: free, bank_tenths: bankTenths,
      saved_at: new Date().toISOString(),
    };
    try {
      window.localStorage.setItem(transferDraftKey(currentSnapshot.season), JSON.stringify(value));
      setSavedPlan(value); setPersistError(null); setMessage("Plan saved.");
    } catch { setPersistError("This device could not save the draft. Check its local storage space."); }
  }
  function persistScenarios(next: SavedScenario[]): boolean {
    try {
      window.localStorage.setItem(scenarioKey(currentSnapshot.season), JSON.stringify(next));
      setScenarios(next); setScenarioResults(null); setPersistError(null);
      return true;
    } catch {
      setPersistError("This device could not save the scenario. Check its local storage space.");
      return false;
    }
  }
  function saveScenario() {
    if (!canEvaluate || !draft.length || scenarios.length >= MAX_SCENARIOS) return;
    const used = new Set(scenarios.map((scenario) => scenario.name));
    const name = ["A", "B", "C"].map((letter) => "Scenario " + letter).find((label) => !used.has(label)) ?? "Scenario";
    const value: SavedScenario = {
      id: String(Date.now()), name, pairs: draft, free_transfers: free, bank_tenths: bankTenths,
      fingerprint, prediction_timestamp: currentSnapshot.prediction_timestamp, saved_at: new Date().toISOString(),
    };
    if (persistScenarios([...scenarios, value])) { setMessage(name.replace("Scenario", "Option") + " kept."); setResultTab("scenarios"); }
  }
  function loadScenario(scenario: SavedScenario) {
    setDraft(scenario.pairs); setFree(scenario.free_transfers); setBankOverride(scenario.bank_tenths);
    setMaxTransfers(Math.max(maxTransfers, scenario.pairs.length));
    setPendingOut(null); setPendingIn(null); setEditingIndex(null); invalidate();
    setMessage(scenario.name.replace("Scenario", "Option") + " loaded.");
  }
  async function compareScenarios() {
    const comparable = scenarios.filter((scenario) => !scenarioStaleReason(scenario, fingerprint, currentSnapshot.prediction_timestamp));
    if (!comparable.length || !currentSnapshot.prediction_available) return;
    setComparing(true); setAnalysisError(null);
    try {
      const results: Record<string, ScenarioResult> = {};
      const base = await api.lineup({ elements: squadElements });
      results.baseline = { gross: score(base), net: score(base), hit: 0, bank: fromTenths(scenarioBank(bankTenths, [])), captain: nameOf(base.captain ?? undefined) };
      for (const scenario of comparable) {
        const finalIds = squadElements.map((id) => scenario.pairs.find((pair) => pair.out_element === id)?.in_element ?? id);
        const lineup = await api.lineup({ elements: finalIds });
        const scenarioHit = Math.max(0, scenario.pairs.length - scenario.free_transfers) * 4;
        results[scenario.id] = {
          gross: score(lineup), net: score(lineup) - scenarioHit, hit: scenarioHit,
          bank: fromTenths(scenarioBank(scenario.bank_tenths, scenario.pairs)), captain: nameOf(lineup.captain ?? undefined),
        };
      }
      setScenarioResults(results);
    } catch (error) {
      setAnalysisError((error as Error).message);
    } finally {
      setComparing(false);
    }
  }
  function scenarioBank(startTenths: number, pairs: readonly TransferDraftPair[]): number {
    return startTenths + pairs.reduce((total, pair) => {
      const incomingPlayer = byElement.get(pair.in_element);
      return total + (sellPrices[pair.out_element] ?? 0) - (incomingPlayer ? toTenths(incomingPlayer.value_m) : 0);
    }, 0);
  }
  function toggleHold() {
    try {
      if (holdMatches) {
        window.localStorage.removeItem(heldWeekKey(currentSnapshot.season)); setHeldWeek(null); setMessage("No longer holding.");
      } else if (currentSnapshot.gameweek !== null) {
        const value: HeldWeek = { version: 1, season: currentSnapshot.season, gameweek: currentSnapshot.gameweek, fingerprint, created_at: new Date().toISOString() };
        window.localStorage.setItem(heldWeekKey(currentSnapshot.season), JSON.stringify(value));
        setHeldWeek(value); setMessage("Holding this week.");
      }
      setPersistError(null);
    } catch { setPersistError("This device could not save the hold. Check its local storage space."); }
  }
  async function evaluateDraft() {
    if (!canEvaluate) return;
    setMessage(null); setAnalysisError(null);
    try {
      const lineup = await api.lineup({ elements: finalElements });
      const baseline = currentSnapshot.prediction_available ? await api.lineup({ elements: squadElements }) : null;
      setEvaluation({ lineup, baseline, hasPoints: currentSnapshot.prediction_available && baseline !== null });
      setResultTab("draft");
    } catch (error) { setAnalysisError((error as Error).message); }
  }
  async function compareTransfers(constrained: boolean) {
    setAnalysing(true); setAnalysisError(null); setResultTab("best");
    try {
      const args = {
        elements: squadElements, free, bank: fromTenths(bankTenths), max: maxTransfers,
        selling_prices_tenths: sellPrices,
        ...(constrained ? {
          locked_out_elements: draft.map((pair) => pair.out_element),
          locked_in_elements: draft.map((pair) => pair.in_element),
        } : {}),
      };
      const result = await api.transfers(args);
      if (constrained) setLockedAnalysis(result); else setBestAnalysis(result);
    } catch (error) { setAnalysisError((error as Error).message); }
    finally { setAnalysing(false); }
  }
  function applyReviewedDraft() {
    if (!evaluation) return;
    setTeamResult(evaluation.lineup, "transfer", bankAfterTenths);
    setShowReview(false); router.push("/team");
  }
  const baseline = evaluation?.baseline ?? bestAnalysis?.current_lineup ?? lockedAnalysis?.current_lineup ?? null;
  const finalGross = evaluation ? score(evaluation.lineup) : null;
  const baselineGross = baseline ? score(baseline) : null;
  const draftNet = finalGross === null ? null : finalGross - hit;
  const draftGain = draftNet !== null && baselineGross !== null ? draftNet - baselineGross : null;

  return (
    <section className="page transfers-page" aria-label="Transfers">
      <GateSign>
        <div className="steppers">
          <div className="field">
            <span id="ft-label">Free transfers</span>
            <div className="stepper" role="group" aria-labelledby="ft-label">
              <button type="button" aria-label="One fewer free transfer" disabled={free <= 0} onClick={() => { setFree(free - 1); invalidate(); }}><Icon name="minus" size={16} /></button>
              <output>{free}</output>
              <button type="button" aria-label="One more free transfer" disabled={free >= 5} onClick={() => { setFree(free + 1); invalidate(); }}><Icon name="plus" size={16} /></button>
            </div>
          </div>
          <div className="field">
            <span id="bank-label">In the bank</span>
            <div className="stepper" role="group" aria-labelledby="bank-label">
              <button type="button" aria-label="£0.1m less in the bank" disabled={bankTenths <= 0} onClick={() => { setBankOverride(Math.max(0, bankTenths - 1)); invalidate(); }}><Icon name="minus" size={16} /></button>
              <output>{money(fromTenths(bankTenths))}</output>
              <button type="button" aria-label="£0.1m more in the bank" onClick={() => { setBankOverride(bankTenths + 1); invalidate(); }}><Icon name="plus" size={16} /></button>
            </div>
          </div>
          <div className="field">
            <span id="max-label">Most moves</span>
            <div className="stepper" role="group" aria-labelledby="max-label">
              <button type="button" aria-label="Allow one fewer move" disabled={maxTransfers <= 0} onClick={() => changeMax(maxTransfers - 1)}><Icon name="minus" size={16} /></button>
              <output>{maxTransfers}</output>
              <button type="button" aria-label="Allow one more move" disabled={maxTransfers >= 5} onClick={() => changeMax(maxTransfers + 1)}><Icon name="plus" size={16} /></button>
            </div>
          </div>
        </div>
      </GateSign>

      {holdMatches ? (
        <div className="callout" role="status">
          <span className="callout-mark"><Icon name="check" size={16} /></span>
          <p>You&apos;re holding this week: no transfers planned.</p>
          <button type="button" className="btn btn--ghost btn--sm" onClick={toggleHold}>Change my mind</button>
        </div>
      ) : null}
      {persistError ? <p className="status-line is-error" role="alert">{persistError}</p> : null}
      {savedPlan ? (
        <div className="callout" role="status">
          <span className="callout-mark"><Icon name="download" size={16} /></span>
          {savedPlan.fingerprint === fingerprint ? (
            <>
              <p>You saved a plan on {new Date(savedPlan.saved_at).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" })}.</p>
              <button type="button" className="btn btn--line btn--sm" onClick={reopenSaved}>Open it</button>
            </>
          ) : (
            <>
              <p>Your saved plan was for a different squad.</p>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => {
                try { window.localStorage.removeItem(transferDraftKey(currentSnapshot.season)); setSavedPlan(null); setMessage("Old plan cleared."); }
                catch { setPersistError("Couldn't clear the saved plan."); }
              }}>Clear it</button>
            </>
          )}
        </div>
      ) : null}

      <section className={"panel channel" + (draft.length || pendingOut !== null ? " is-live" : "")} aria-label="Your moves">
        <div className="channel-head">
          <div>
            <h2>Your moves</h2>
            <p>{draft.length ? `${draft.length} of ${maxTransfers} lined up` : "Pick someone to sell on the left, then a replacement on the right."}</p>
          </div>
          <div className="channel-sums">
            <span><small>Bank after</small><b className={bankAfterTenths < 0 ? "is-down" : undefined}>{money(fromTenths(bankAfterTenths))}</b></span>
            <span><small>Points hit</small><b className={hit > 0 ? "is-down" : undefined}>{hit ? `−${hit}` : "0"}</b></span>
          </div>
        </div>

        {draft.length > 0 && (
          <ol className="moves">
            <AnimatePresence>
              {draft.map((pair, index) => {
                const out = byElement.get(pair.out_element);
                const inPlayer = byElement.get(pair.in_element);
                const sale = sellPrices[pair.out_element] ?? 0;
                const purchase = inPlayer ? toTenths(inPlayer.value_m) : 0;
                return (
                  <m.li key={pair.out_element + "-" + pair.in_element} className="move"
                    layout="position" transition={{ layout: { duration: 0.32, ease: [0.22, 1, 0.36, 1] } }}
                    initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: -12 }}>
                    <span className="move-num">{index + 1}</span>
                    <span className="move-side is-out">
                      {out && <Face player={out} size="sm" />}
                      <span className="prow-name"><b>{nameOf(out)}</b><span>sells for {money(fromTenths(sale))}</span></span>
                    </span>
                    <Icon className="move-arrow" name="arrow-right" size={22} />
                    <span className="move-side is-in">
                      {inPlayer && <Face player={inPlayer} size="sm" />}
                      <span className="prow-name"><b>{nameOf(inPlayer)}</b><span>costs {money(fromTenths(purchase))}</span></span>
                    </span>
                    <span className="move-actions">
                      <button type="button" className="btn btn--ghost btn--sm" onClick={() => editMove(index)}>Change</button>
                      <button type="button" className="btn btn--ghost btn--sm" onClick={() => removeMove(index)} aria-label={`Remove move ${index + 1}`}><Icon name="close" size={16} /></button>
                    </span>
                  </m.li>
                );
              })}
            </AnimatePresence>
          </ol>
        )}

        {pendingOut !== null ? (
          <div className="pending" aria-live="polite">
            <span className="move-side is-out">
              {outgoing && <Face player={outgoing} size="sm" />}
              <span className="prow-name"><b>{nameOf(outgoing ?? undefined)}</b><span>{editingIndex === null ? "Selling" : `Changing move ${editingIndex + 1}`}</span></span>
            </span>
            <Icon className="move-arrow" name="arrow-right" size={22} />
            <span className="move-side is-in">
              {incoming ? <Face player={incoming} size="sm" /> : <span className="face face--sm face--empty" />}
              <span className="prow-name">
                <b>{pendingIn === null ? `Pick a ${outgoing?.position ?? ""} on the right` : nameOf(incoming ?? undefined)}</b>
                {previewDelta !== null && <span>{previewDelta >= 0 ? `frees up ${money(fromTenths(previewDelta))}` : `costs ${money(fromTenths(-previewDelta))} more`}</span>}
              </span>
            </span>
            <span className="move-actions">
              <button className="btn btn--go btn--sm" type="button" disabled={pendingIn === null || (draft.length >= maxTransfers && editingIndex === null)} onClick={stageMove}>
                {editingIndex === null ? "Add this move" : "Update move"}
              </button>
              <button className="btn btn--ghost btn--sm" type="button" onClick={() => { setPendingOut(null); setPendingIn(null); setEditingIndex(null); }}>Cancel</button>
            </span>
          </div>
        ) : null}

        {(draftError && (draft.length > 0 || pendingOut !== null)) || message ? (
          <p className={"status-line channel-status" + (draftError && !message ? " is-error" : "")} role="status">{message ?? draftError}</p>
        ) : null}

        <div className="channel-foot">
          <span className="note">
            {financeSummary.priceBasis === "estimated" ? "Sale prices are estimates: we don't have every purchase price." : "Sale prices use what you paid and FPL's half-rise rule."}
          </span>
          <span className="channel-buttons">
            <button className="btn btn--ghost btn--sm" type="button" onClick={toggleHold}>{holdMatches ? "Stop holding" : "Hold this week"}</button>
            <button className="btn btn--ghost btn--sm" type="button" disabled={!draft.length && pendingOut === null} onClick={clearDraft}>Clear</button>
            <button className="btn btn--line btn--sm" type="button" disabled={pendingOut !== null || !draft.length} onClick={saveDraft}>Save</button>
            <button className="btn btn--line btn--sm" type="button" disabled={!canEvaluate || !draft.length || scenarios.length >= MAX_SCENARIOS} onClick={saveScenario}
              title={scenarios.length >= MAX_SCENARIOS ? "Remove a saved option to keep another" : "Keep this as an option to compare"}>Keep as option</button>
            <button className="btn btn--go btn--sm" type="button" disabled={!canEvaluate || !draft.length} onClick={evaluateDraft}>Check these moves <Icon name="arrow-right" size={16} /></button>
          </span>
        </div>
      </section>

      <div className="desks">
        <section className="panel desk desk--out" aria-label="Your squad">
          <div className="desk-head">
            <h2><Icon name="arrow-left" size={18} /> Sell</h2>
            <span className="note">{outRows.length} players</span>
          </div>
          <div className="desk-tools">
            <Segmented label="Filter your squad" value={outFilter} onChange={setOutFilter}
              options={OUT_FILTERS.map((filter) => ({ value: filter, label: filter === "ALL" ? "All" : filter === "FLAG" ? "Flagged" : filter }))} />
            <label className="searchbox">
              <span className="sr-only">Search your squad</span>
              <Icon name="search" size={18} />
              <input className="input input--sm" type="search" placeholder="Search your squad" value={outQuery} onChange={(event) => setOutQuery(event.target.value)} />
            </label>
          </div>
          <div className="desk-list stagger">
            {outRows.map((player, index) => <PlayerRow key={player.element} player={player} selected={player.element === pendingOut} index={index} onClick={() => pickOut(player)} />)}
            {!outRows.length && <p className="panel-body note">Nobody in your squad matches.</p>}
          </div>
        </section>

        <section className="panel desk desk--in" aria-label="Players to buy">
          <div className="desk-head">
            <h2>Buy <Icon name="arrow-right" size={18} /></h2>
            <span className="note">{outgoing ? `${outgoing.position}s you can afford a look at` : `${marketRows.length} players`}</span>
          </div>
          <div className="desk-tools">
            <Segmented label="Filter by position" value={outgoing ? outgoing.position : inFilter} onChange={(value) => { setInFilter(value); setMarketLimit(200); }}
              options={IN_FILTERS.map((filter) => ({ value: filter, label: filter === "ALL" ? "All" : filter, disabled: Boolean(outgoing) && filter !== outgoing?.position }))} />
            <label className="searchbox">
              <span className="sr-only">Search all players</span>
              <Icon name="search" size={18} />
              <input className="input input--sm" type="search" placeholder="Search players or clubs" value={inQuery} onChange={(event) => { setInQuery(event.target.value); setMarketLimit(200); }} />
            </label>
          </div>
          <div className="desk-list stagger">
            {shownMarketRows.map((player, index) => <PlayerRow key={player.element} player={player} selected={player.element === pendingIn} index={index} onClick={() => pickIn(player)} />)}
            {!shownMarketRows.length && <p className="panel-body note">Nobody matches that search.</p>}
          </div>
          {marketRows.length > marketLimit ? <button className="btn btn--ghost btn--block" type="button" onClick={() => setMarketLimit((value) => value + 200)}>Show more players</button> : null}
        </section>
      </div>

      <section className="section" aria-label="Results">
        <div className="section-title">
          <div>
            <h2>How do they stack up?</h2>
            <p>Your moves, the best available moves, and any options you&apos;ve kept.</p>
          </div>
          <Segmented label="Results" value={resultTab} onChange={setResultTab} options={[
            { value: "draft", label: "My moves" },
            { value: "best", label: "Best available" },
            { value: "scenarios", label: `Kept options (${scenarios.length}/${MAX_SCENARIOS})` },
          ]} />
        </div>
        {analysisError ? <p className="status-line is-error" role="alert">{analysisError}</p> : null}

        {resultTab === "draft" && (
          <div className="panel results">
            {!evaluation ? (
              <p className="panel-body note">Line up your moves above, then press Check these moves to see the new XI and what it&apos;s worth.</p>
            ) : (
              <div className="panel-body">
                <div className="plan-summary plan-summary--flush">
                  <span><small>Bank after</small><b>{money(fromTenths(bankAfterTenths))}</b></span>
                  <span><small>Points hit</small><b>{hit ? `−${hit}` : "0"}</b></span>
                  {evaluation.hasPoints && draftNet !== null && <span><small>New XI this week</small><b><CountUp value={draftNet} decimals={1} /> pts</b></span>}
                  {evaluation.hasPoints && draftGain !== null && <span><small>Versus no moves</small><b className={draftGain > 0 ? "is-up" : draftGain < 0 ? "is-down" : undefined}>{signed(draftGain)} pts</b></span>}
                </div>
                {!evaluation.hasPoints && <p className="note">Projections aren&apos;t ready, so we&apos;ve only checked the squad is legal and affordable.</p>}
                <div className="xi-list">
                  <h3>Starting XI</h3>
                  <ol>{evaluation.lineup.xi.map((player) => <li key={player.element}><Pos pos={player.position} /> {nameOf(player)}{player.element === evaluation.lineup.captain?.element ? <span className="armband">C</span> : null}</li>)}</ol>
                  <h3>Bench</h3>
                  <ol>{evaluation.lineup.bench.map((player) => <li key={player.element}><Pos pos={player.position} /> {nameOf(player)}</li>)}</ol>
                </div>
                <div className="results-foot">
                  <p className="note">Applying this changes your team here only. Make the transfers on the FPL site too.</p>
                  <button className="btn btn--go" type="button" onClick={() => setShowReview(true)}>Use these moves <Icon name="arrow-right" size={18} /></button>
                </div>
              </div>
            )}
          </div>
        )}

        {resultTab === "best" && (
          <div className="results">
            <div className="toolbar">
              <button className="btn" type="button" disabled={!snapshot.prediction_available || analysing} onClick={() => compareTransfers(false)}>
                {analysing ? "Working it out…" : "Find the best moves"}
              </button>
              <button className="btn btn--line" type="button" disabled={!snapshot.prediction_available || analysing || !draft.length || !canEvaluate} onClick={() => compareTransfers(true)}>
                Best moves that include mine
              </button>
            </div>
            {!snapshot.prediction_available && <p className="note">Projections aren&apos;t ready, so we can&apos;t compare points yet.</p>}
            {bestAnalysis ? (
              <>
                <div className="options">
                  <article className={"panel option" + (viewedRow === null ? " is-active" : "")}>
                    <div className="option-head"><h3>No transfers</h3><b>{num(score(bestAnalysis.current_lineup))} pts</b></div>
                    <p className="note">Your squad as it is.</p>
                    <button className="btn btn--line btn--sm" type="button" onClick={() => setViewedRow(null)}>See the lineup</button>
                  </article>
                  {bestAnalysis.rows.map((row) => <OptimizerCard key={"best-" + row.transfers} row={row} byElement={byElement} active={viewedRow === row} onView={() => setViewedRow(row)} />)}
                  {bestAnalysis.failures.map((failure) => <article className="panel option" key={"best-fail-" + failure.transfers}><div className="option-head"><h3>{failure.transfers} transfers</h3><b>–</b></div><p className="note">No legal option within budget.</p></article>)}
                </div>
                {lockedAnalysis ? (
                  <>
                    <h3 className="results-sub">Including your {draft.length} move{draft.length === 1 ? "" : "s"}</h3>
                    <div className="options">
                      {lockedAnalysis.rows.map((row) => <OptimizerCard key={"locked-" + row.transfers} row={row} byElement={byElement} active={viewedRow === row} onView={() => setViewedRow(row)} />)}
                      {lockedAnalysis.failures.map((failure) => <article className="panel option" key={"lock-fail-" + failure.transfers}><div className="option-head"><h3>{failure.transfers} transfers</h3><b>–</b></div><p className="note">No legal option within budget.</p></article>)}
                    </div>
                  </>
                ) : null}
                {viewedRow ? (
                  <div className="panel xi-list xi-list--panel">
                    <h3>{viewedRow.transfers} transfer lineup · {viewedRow.formation}</h3>
                    <ol>{viewedRow.xi.map((player) => <li key={player.element}><Pos pos={player.position} /> {nameOf(byElement.get(player.element) ?? player)}{player.element === viewedRow.captain?.element ? <span className="armband">C</span> : null}</li>)}</ol>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="note">We&apos;ll try every combination from 0 to {maxTransfers} transfers and show what each is worth this week.</p>
            )}
          </div>
        )}

        {resultTab === "scenarios" && (
          <div className="panel results">
            {scenarios.length === 0 ? (
              <p className="panel-body note">Line up some moves and press Keep as option. You can keep up to {MAX_SCENARIOS} and compare them side by side.</p>
            ) : (
              <div className="panel-body">
                <ul className="kept">
                  <AnimatePresence>
                    {scenarios.map((scenario) => {
                      const stale = scenarioStaleReason(scenario, fingerprint, currentSnapshot.prediction_timestamp);
                      return (
                        <m.li key={scenario.id} className={"kept-item" + (stale ? " is-stale" : "")}
                          layout="position" transition={{ layout: { duration: 0.32, ease: [0.22, 1, 0.36, 1] } }} exit={{ opacity: 0, x: -12 }}>
                          <b>{scenario.name.replace("Scenario", "Option")}</b>
                          <span>{scenario.pairs.map((pair) => nameOf(byElement.get(pair.out_element)) + " → " + nameOf(byElement.get(pair.in_element))).join(", ")}</span>
                          {stale ? <em className="note">Out of date ({stale}), so it&apos;s left out of the comparison.</em> : null}
                          <span className="kept-actions">
                            <button type="button" className="btn btn--ghost btn--sm" disabled={Boolean(stale)} onClick={() => loadScenario(scenario)}>Load</button>
                            <button type="button" className="btn btn--ghost btn--sm" onClick={() => persistScenarios(scenarios.filter((other) => other.id !== scenario.id))}>Remove</button>
                          </span>
                        </m.li>
                      );
                    })}
                  </AnimatePresence>
                </ul>
                <button className="btn" type="button" disabled={comparing || !currentSnapshot.prediction_available} onClick={compareScenarios}>{comparing ? "Comparing…" : "Compare them"}</button>
                {scenarioResults ? (
                  <div className="table-wrap">
                    <table className="table">
                      <caption className="note">This gameweek only. Net is the XI&apos;s points minus any hit.</caption>
                      <thead><tr><th scope="col">Option</th><th scope="col" className="num">Points</th><th scope="col" className="num">Hit</th><th scope="col" className="num">Net</th><th scope="col" className="num">Bank after</th><th scope="col">Captain</th></tr></thead>
                      <tbody>
                        <tr><th scope="row">No transfers</th><td className="num">{num(scenarioResults.baseline.gross)}</td><td className="num">0</td><td className="num">{num(scenarioResults.baseline.net)}</td><td className="num">{money(scenarioResults.baseline.bank)}</td><td>{scenarioResults.baseline.captain}</td></tr>
                        {scenarios.filter((scenario) => scenarioResults[scenario.id]).map((scenario) => {
                          const result = scenarioResults[scenario.id];
                          return <tr key={scenario.id}><th scope="row">{scenario.name.replace("Scenario", "Option")}</th><td className="num">{num(result.gross)}</td><td className="num">{result.hit}</td><td className="num">{num(result.net)} <small>({signed(result.net - scenarioResults.baseline.net)})</small></td><td className="num">{money(result.bank)}</td><td>{result.captain}</td></tr>;
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        )}
      </section>

      {showReview && evaluation ? (
        <div className="review-backdrop" role="presentation" onClick={() => setShowReview(false)}>
          <section className="review-panel" role="dialog" aria-modal="true" aria-labelledby="transfer-review-title" onClick={(event) => event.stopPropagation()}>
            <h2 id="transfer-review-title">Use these moves?</h2>
            <p><b>Out:</b> {draft.map((pair) => nameOf(byElement.get(pair.out_element))).join(", ") || "Nobody"}</p>
            <p><b>In:</b> {draft.map((pair) => nameOf(byElement.get(pair.in_element))).join(", ") || "Nobody"}</p>
            <p>{money(fromTenths(bankAfterTenths))} left in the bank{hit ? `, and a ${hit}-point hit` : ""}.</p>
            <p className="note">This updates your team here. It doesn&apos;t make the transfers on the FPL site.</p>
            <div className="review-actions">
              <button className="btn btn--go" type="button" onClick={applyReviewedDraft}>Yes, use them <Icon name="arrow-right" size={18} /></button>
              <button className="btn btn--ghost" type="button" onClick={() => setShowReview(false)}>Go back</button>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}
