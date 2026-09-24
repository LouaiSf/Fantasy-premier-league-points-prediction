"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { ClubCrest } from "@/components/club-crest";
import { clubStyle } from "@/lib/club-colors";
import { api } from "@/lib/api";
import { fromTenths, sellingPricesTenthsForSquad, toTenths } from "@/lib/finance";
import { money, num, signed } from "@/lib/format";
import { isHeldWeek, isSavedTransferDraft, heldWeekKey, squadFingerprint, transferDraftKey, type HeldWeek, type SavedTransferDraft, type TransferDraftPair } from "@/lib/transfer-planning";
import { validateSquad } from "@/lib/squad";
import type { PlayerRecord, SquadResult, TransferResult, TransferRow } from "@/lib/types";
import { Loading } from "@/components/loading";
import { ModelInfo } from "@/components/model-info";

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
function PlayerRow({ player, selected, teamCode, onClick }: {
  player: PlayerRecord; selected: boolean; teamCode?: number; onClick: () => void;
}) {
  return (
    <button type="button" className={"prow" + (selected ? " is-picked" : "")}
      data-player-id={player.element} onClick={onClick} style={clubStyle(player.team)}>
      <span className="shot">
        <PlayerPhoto src={player.photo ?? undefined} alt={player.name} name={player.name} variant="card" loading="lazy" />
        {teamCode ? <ClubCrest className="badge-mini" code={teamCode} team={player.team} shortName={player.team_short} aria-hidden="true" /> : null}
      </span>
      <span className="prow-id">
        <b>{nameOf(player)}</b>
        <span>{player.team_short} · {money(player.value_m)} · #{player.element}</span>
      </span>
      <span className="prow-num"><em>{num(player.predicted_points ?? player.form)}<small>{player.position}</small></em></span>
    </button>
  );
}

function OptimizerCard({ row, byElement, onView }: {
  row: TransferRow; byElement: Map<number, PlayerRecord>; onView: () => void;
}) {
  return (
    <article className="impact-cell">
      <p className="kicker">{row.transfers} transfer{row.transfers === 1 ? "" : "s"}</p>
      <strong className={"big " + (row.gain >= 0 ? "pos" : "neg")}>{signed(row.gain)}</strong>
      <p>{num(row.gross)} gross · {row.hit} hit · bank after {money(row.bank_after)}</p>
      <div className="optimizer-diff">
        <div><b>OUT</b><ul>{row.out_elements.map((id) => <li key={id}>{nameOf(byElement.get(id))} <small>#{id}</small></li>)}</ul></div>
        <div><b>IN</b><ul>{row.in_elements.map((id) => <li key={id}>{nameOf(byElement.get(id))} <small>#{id}</small></li>)}</ul></div>
      </div>
      <button className="btn secondary sm" type="button" onClick={onView}>View XI</button>
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
  const [resultTab, setResultTab] = React.useState<"draft" | "best">("draft");
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
  const draftError = pendingOut !== null ? (pendingIn === null ? "Choose an incoming player, then add the move." : "Add or update the selected move.") :
    draft.length > maxTransfers ? "Remove moves to lower the transfer limit." :
    duplicateDraft ? "Each outgoing and incoming player can appear once." :
    shapeError || (bankAfterTenths < 0 ? "This draft is over budget." : "");
  const canEvaluate = !draftError && pendingOut === null && draft.length <= maxTransfers && finalPlayers.length === 15;

  React.useEffect(() => {
    if (!snapshot || !fingerprint) return;
    try {
      const rawDraft = window.localStorage.getItem(transferDraftKey(currentSnapshot.season));
      const parsedDraft: unknown = rawDraft ? JSON.parse(rawDraft) : null;
      setSavedPlan(isSavedTransferDraft(parsedDraft) && parsedDraft.season === snapshot.season ? parsedDraft : null);
      const rawHold = window.localStorage.getItem(heldWeekKey(currentSnapshot.season));
      const parsedHold: unknown = rawHold ? JSON.parse(rawHold) : null;
      if (isHeldWeek(parsedHold) && parsedHold.season === snapshot.season &&
          (snapshot.gameweek == null || parsedHold.gameweek >= snapshot.gameweek)) {
        setHeldWeek(parsedHold);
      } else {
        window.localStorage.removeItem(heldWeekKey(currentSnapshot.season));
        setHeldWeek(null);
      }
    } catch {
      setPersistError("Saved transfer data could not be read. You can clear it from this device.");
    }
  }, [snapshot?.season, snapshot?.gameweek, fingerprint]);

  if (loading || !snapshot) return <section className="page"><div className="shell"><Loading label="Loading season data…" /></div></section>;
  if (squadPlayers.length !== 15) return (
    <section className="page studio"><div className="shell shell--padded transfer-onboarding">
      <span className="eyebrow alert">Decision room</span><h1>Build your squad first</h1>
      <p>Transfer Studio compares legal 15-player squads. Your saved team has {squadPlayers.length}/15 players.</p>
      <a className="btn" href="/team">Go to My Team</a>
    </div></section>
  );

  const currentSnapshot = snapshot;
  const teamCodeByName = new Map(snapshot.teams.map((team) => [team.name, team.code]));
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
    if (pendingOut === null || pendingIn === null) { setMessage("Choose one OUT and one IN player first."); return; }
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
    if (draft.length > next) { setMessage("Remove moves to lower the transfer limit."); return; }
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
      setSavedPlan(value); setPersistError(null); setMessage("Draft saved on this device.");
    } catch { setPersistError("This device could not save the draft. Check its local storage space."); }
  }
  function toggleHold() {
    try {
      if (holdMatches) {
        window.localStorage.removeItem(heldWeekKey(currentSnapshot.season)); setHeldWeek(null); setMessage("Hold cleared.");
      } else if (currentSnapshot.gameweek !== null) {
        const value: HeldWeek = { version: 1, season: currentSnapshot.season, gameweek: currentSnapshot.gameweek, fingerprint, created_at: new Date().toISOString() };
        window.localStorage.setItem(heldWeekKey(currentSnapshot.season), JSON.stringify(value));
        setHeldWeek(value); setMessage("Holding GW" + currentSnapshot.gameweek + " on this device.");
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
    <section className="page studio" aria-label="Transfer studio">
      <div className="shell-wide">
        <div className="section-head">
          <div><p className="eyebrow alert">Decision room</p><h1>Transfer studio</h1></div>
          <p>Stage real moves, check the final squad and compare the best available options.</p>
          {snapshot.prediction_available ? <ModelInfo model={snapshot.model} timestamp={snapshot.prediction_timestamp} /> : null}
        </div>
        <div className="studio-bar">
          <div className="studio-field"><span className="kicker">Free transfers</span><div className="stepper">
            <button type="button" aria-label="Decrease free transfers" disabled={free <= 0} onClick={() => { setFree(free - 1); invalidate(); }}>−</button>
            <output className="data">{free}</output>
            <button type="button" aria-label="Increase free transfers" disabled={free >= 5} onClick={() => { setFree(free + 1); invalidate(); }}>+</button>
          </div></div>
          <div className="studio-field"><span className="kicker">Bank</span><div className="stepper">
            <button type="button" aria-label="Decrease bank by £0.1m" disabled={bankTenths <= 0} onClick={() => { setBankOverride(Math.max(0, bankTenths - 1)); invalidate(); }}>−</button>
            <output className="data">{money(fromTenths(bankTenths))}</output>
            <button type="button" aria-label="Increase bank by £0.1m" onClick={() => { setBankOverride(bankTenths + 1); invalidate(); }}>+</button>
          </div></div>
          <div className="studio-field"><span className="kicker">Max transfers</span><div className="stepper">
            <button type="button" aria-label="Decrease maximum transfers" disabled={maxTransfers <= 0} onClick={() => changeMax(maxTransfers - 1)}>−</button>
            <output className="data">{draft.length}/{maxTransfers}</output>
            <button type="button" aria-label="Increase maximum transfers" disabled={maxTransfers >= 5} onClick={() => changeMax(maxTransfers + 1)}>+</button>
          </div></div>
          <span className="spacer" />
          <div className="studio-summary"><span className="kicker">Draft bank / hit</span><strong className="data">{money(fromTenths(bankAfterTenths))} / {hit} pts</strong></div>
        </div>

        {holdMatches ? <p className="analysis-status" role="status">Holding GW{heldWeek?.gameweek}. <button type="button" className="text-button" onClick={toggleHold}>Clear hold</button></p> : null}
        {persistError ? <p className="analysis-status is-error" role="alert">{persistError}</p> : null}
        {savedPlan ? <div className="saved-plan-note" role="status">
          {savedPlan.fingerprint === fingerprint
            ? <>Saved draft from {new Date(savedPlan.saved_at).toLocaleString()}. <button type="button" className="text-button" onClick={reopenSaved}>Reopen saved draft</button></>
            : <>Saved plan is for another squad. <button type="button" className="text-button" onClick={() => {
              try { window.localStorage.removeItem(transferDraftKey(currentSnapshot.season)); setSavedPlan(null); setMessage("Saved plan cleared."); }
              catch { setPersistError("Could not clear the saved plan."); }
            }}>Clear saved plan</button></>}
        </div> : null}

        <div className="draft-actions mobile-draft-actions">
          <strong>Draft {draft.length} of {maxTransfers}</strong>
          <button className="btn secondary sm" type="button" disabled={draft.length >= maxTransfers} onClick={() => { setPendingOut(null); setPendingIn(null); setEditingIndex(null); setMessage("Choose a player in OUT, then a replacement in IN."); }}>Add move</button>
          <button className="btn sm" type="button" disabled={!canEvaluate} onClick={evaluateDraft}>Evaluate this draft</button>
        </div>

        <div className="studio-grid transfer-v2-grid">
          <section className="desk out" aria-label="Your squad OUT">
            <div className="desk-head"><h2>Your squad / OUT</h2><span className="count">{outRows.length} players</span></div>
            <div className="desk-tools">
              <div className="mini-chips">{OUT_FILTERS.map((filter) => <button key={filter} type="button"
                className={"mini-chip" + (outFilter === filter ? " is-active" : "")} onClick={() => setOutFilter(filter)}>
                {filter === "ALL" ? "All" : filter === "FLAG" ? "Flagged" : filter}</button>)}</div>
              <label className="search"><input type="search" placeholder="Search your squad" value={outQuery} onChange={(event) => setOutQuery(event.target.value)} /></label>
            </div>
            <div className="desk-list">{outRows.map((player) => <PlayerRow key={player.element} player={player}
              selected={player.element === pendingOut} teamCode={teamCodeByName.get(player.team)} onClick={() => pickOut(player)} />)}</div>
          </section>

          <section className="draft-panel" aria-label="Staged transfer draft">
            <div className="desk-head"><h2>Draft {draft.length} of {maxTransfers}</h2><span className="count">Unsaved plan</span></div>
            <p className="draft-finance">Bank after <b>{money(fromTenths(bankAfterTenths))}</b> · Hit <b>{hit} pts</b> · {draft.length} staged</p>
            <p className="finance-basis-note">{financeSummary.priceBasis === "estimated" ? "Selling prices are estimated from current market values because complete purchase prices were not available." : "Selling prices use your imported purchase prices and the official half-rise rule."}</p>
            {draft.length ? <ol className="draft-list">{draft.map((pair, index) => {
              const out = byElement.get(pair.out_element); const inPlayer = byElement.get(pair.in_element);
              const sale = sellPrices[pair.out_element] ?? 0;
              const purchase = inPlayer ? toTenths(inPlayer.value_m) : 0;
              return <li key={pair.out_element + "-" + pair.in_element} className="draft-row">
                <span className="draft-ordinal">{index + 1}</span>
                <div className="draft-pair">
                  <b>{nameOf(out)} <small>OUT · #{pair.out_element}</small></b>
                  <span>{out?.team_short} · sell {money(fromTenths(sale))}</span>
                  <b>{nameOf(inPlayer)} <small>IN · #{pair.in_element}</small></b>
                  <span>{inPlayer?.team_short} · buy {money(fromTenths(purchase))} · Δ {signed(fromTenths(sale - purchase))}</span>
                </div>
                <div className="draft-row-actions"><button type="button" onClick={() => editMove(index)}>Edit</button><button type="button" onClick={() => removeMove(index)}>Remove</button></div>
              </li>;
            })}</ol> : <p className="draft-empty">Choose an OUT player, then a same-position IN player to stage a move.</p>}
            {pendingOut !== null ? <div className="pending-move" aria-live="polite">
              <b>{editingIndex === null ? "Add move" : "Edit move " + (editingIndex + 1)}</b>
              <span>OUT: {nameOf(outgoing ?? undefined)} {outgoing ? "(" + outgoing.position + ")" : ""}</span>
              <span>IN: {pendingIn === null ? "Choose a replacement from the market" : nameOf(incoming ?? undefined)}</span>
              <button className="btn sm" type="button" disabled={pendingIn === null || (draft.length >= maxTransfers && editingIndex === null)} onClick={stageMove}>{editingIndex === null ? "Add staged move" : "Update move"}</button>
              <button className="text-button" type="button" onClick={() => { setPendingOut(null); setPendingIn(null); setEditingIndex(null); }}>Cancel</button>
            </div> : null}
            {draftError ? <p className="run-reason" role="status">{draftError}</p> : null}
            {message ? <p className="analysis-status" role="status">{message}</p> : null}
            <div className="draft-buttons">
              <button className="btn secondary sm" type="button" disabled={!draft.length && pendingOut === null} onClick={clearDraft}>Clear draft</button>
              <button className="btn secondary sm" type="button" disabled={pendingOut !== null} onClick={saveDraft}>Save draft</button>
              <button className="btn secondary sm" type="button" onClick={toggleHold}>{holdMatches ? "Clear this week's hold" : "Hold this week"}</button>
              <button className="btn sm" type="button" disabled={!canEvaluate} onClick={evaluateDraft}>Evaluate this draft</button>
            </div>
          </section>

          <section className="desk in" aria-label="Market IN">
            <div className="desk-head"><h2>Market / IN</h2><span className="count">{marketRows.length} eligible</span></div>
            <div className="desk-tools">
              <label className="search"><input type="search" placeholder="Search all players or clubs" value={inQuery} onChange={(event) => { setInQuery(event.target.value); setMarketLimit(200); }} /></label>
              <div className="mini-chips">{IN_FILTERS.map((filter) => <button key={filter} type="button"
                className={"mini-chip" + (inFilter === filter ? " is-active" : "")} onClick={() => { setInFilter(filter); setMarketLimit(200); }}>
                {filter === "ALL" ? "All" : filter}</button>)}</div>
            </div>
            <p className="market-count">Showing {shownMarketRows.length} of {marketRows.length}</p>
            <div className="desk-list">{shownMarketRows.map((player) => <PlayerRow key={player.element} player={player}
              selected={player.element === pendingIn} teamCode={teamCodeByName.get(player.team)} onClick={() => pickIn(player)} />)}</div>
            {marketRows.length > marketLimit ? <button className="btn secondary sm market-more" type="button" onClick={() => setMarketLimit((value) => value + 200)}>More players</button> : null}
          </section>
        </div>

        <section className="transfer-results">
          <div className="result-tabs" role="tablist" aria-label="Transfer comparison">
            <button type="button" role="tab" aria-selected={resultTab === "draft"} className={resultTab === "draft" ? "is-active" : ""} onClick={() => setResultTab("draft")}>My draft</button>
            <button type="button" role="tab" aria-selected={resultTab === "best"} className={resultTab === "best" ? "is-active" : ""} onClick={() => setResultTab("best")}>Best available</button>
          </div>
          {resultTab === "draft" ? <div className="draft-evaluation">
            {!evaluation ? <p>Evaluation runs only when you choose the button above. Check the full 15, bank and hit before applying.</p> :
              <><h2>My draft · {evaluation.hasPoints ? "projected lineup" : "legal squad and finance"}</h2>
                <div className="draft-score-grid">
                  <div><span>Final bank</span><b>{money(fromTenths(bankAfterTenths))}</b></div>
                  <div><span>Transfer hit</span><b>{hit} pts</b></div>
                  {evaluation.hasPoints && finalGross !== null ? <div><span>Gross · net</span><b>{num(finalGross)} · {num(draftNet ?? 0)}</b></div> : null}
                  {evaluation.hasPoints && draftGain !== null ? <div><span>Gain vs 0-transfer baseline</span><b>{signed(draftGain)}</b></div> : null}
                </div>
                {!evaluation.hasPoints ? <p>Prediction data are unavailable, so no points gain is shown. Squad legality and finance are checked.</p> : null}
                {baseline && evaluation.hasPoints ? <p>0-transfer baseline: {num(score(baseline))} gross points with this squad.</p> : null}
                <ol className="final-xi">{evaluation.lineup.xi.map((player) => <li key={player.element}>{nameOf(player)} · {player.position}{player.element === evaluation.lineup.captain?.element ? " · captain" : ""}</li>)}</ol>
                <h3>Bench</h3><ol className="final-xi">{evaluation.lineup.bench.map((player) => <li key={player.element}>{nameOf(player)} · {player.position}</li>)}</ol>
                <p className="local-only-note">This is an unsaved plan until saved. Applying it updates this app only, not your official FPL account.</p>
                <button className="btn" type="button" onClick={() => setShowReview(true)}>Review and apply to My Team</button>
              </>}
          </div> : <div>
            <div className="optimizer-controls">
              <button className="btn" type="button" disabled={!snapshot.prediction_available || analysing} onClick={() => compareTransfers(false)}>
                {analysing ? "Comparing…" : "Compare best available"}
              </button>
              <button className="btn secondary" type="button" disabled={!snapshot.prediction_available || analysing || !draft.length || !canEvaluate}
                onClick={() => compareTransfers(true)}>Compare with staged moves</button>
              <span>Unconstrained and staged constraints are separate optimizer runs.</span>
            </div>
            {analysisError ? <p className="analysis-status is-error" role="alert">{analysisError}</p> : null}
            {!snapshot.prediction_available ? <p>Prediction data are unavailable. Legal and finance checks still work; optimizer point comparisons are hidden.</p> : null}
            {bestAnalysis ? <div className="analysis-block"><h2>Best available options</h2>
              <div className="impact-grid">
                <div className="impact-cell baseline-cell"><p className="kicker">0-transfer baseline</p><strong className="big">{num(score(bestAnalysis.current_lineup))}</strong><p>gross points · net gain 0</p><button className="btn secondary sm" type="button" onClick={() => setViewedRow(null)}>View baseline XI</button></div>
                {bestAnalysis.rows.map((row) => <OptimizerCard key={"best-" + row.transfers} row={row} byElement={byElement} onView={() => setViewedRow(row)} />)}
                {bestAnalysis.failures.map((failure) => <article className="impact-cell" key={"best-fail-" + failure.transfers}><p className="kicker">{failure.transfers} transfers</p><strong className="big neg">N/A</strong><p>{failure.status}</p></article>)}
              </div>
              {lockedAnalysis ? <><h2>Includes your {draft.length} staged moves</h2><div className="impact-grid">
                {lockedAnalysis.rows.map((row) => <OptimizerCard key={"locked-" + row.transfers} row={row} byElement={byElement} onView={() => setViewedRow(row)} />)}
                {lockedAnalysis.failures.map((failure) => <article className="impact-cell" key={"lock-fail-" + failure.transfers}><p className="kicker">{failure.transfers} transfers</p><strong className="big neg">N/A</strong><p>{failure.status}</p></article>)}
              </div></> : null}
              {viewedRow ? <div className="optimizer-xi"><h3>{viewedRow.transfers} transfer full XI · {viewedRow.formation}</h3><ol className="final-xi">{viewedRow.xi.map((player) => <li key={player.element}>{nameOf(player)} · {player.position}{player.element === viewedRow.captain?.element ? " · captain" : ""}</li>)}</ol></div> : null}
            </div> : <p>Run a comparison to see the 0..{maxTransfers} transfer results, with separate OUT and IN IDs.</p>}
          </div>}
        </section>
      </div>

      {showReview && evaluation ? <div className="review-backdrop" role="presentation" onClick={() => setShowReview(false)}>
        <section className="review-panel" role="dialog" aria-modal="true" aria-labelledby="transfer-review-title" onClick={(event) => event.stopPropagation()}>
          <h2 id="transfer-review-title">Review local squad update</h2>
          <p>Outgoing: {draft.map((pair) => nameOf(byElement.get(pair.out_element)) + " (#" + pair.out_element + ")").join(", ") || "None"}</p>
          <p>Incoming: {draft.map((pair) => nameOf(byElement.get(pair.in_element)) + " (#" + pair.in_element + ")").join(", ") || "None"}</p>
          <p>Bank after: {money(fromTenths(bankAfterTenths))} · Hit: {hit} points</p>
          <p>New XI: {evaluation.lineup.xi.map(nameOf).join(", ")}</p>
          <p>This updates this app's My Team only. It does not submit transfers to FPL.</p>
          <button className="btn" type="button" onClick={applyReviewedDraft}>Apply to My Team</button>
          <button className="btn secondary" type="button" onClick={() => setShowReview(false)}>Back to draft</button>
        </section>
      </div> : null}
    </section>
  );
}
