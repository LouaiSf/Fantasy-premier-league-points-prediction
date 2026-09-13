import { escapeHtml, money, number, postJson, signed } from "./api.js";
import { $, $$, openProfile, playerRow, toast } from "./ui.js";

function playerById(state, id) {
  return state.players.find(player => player.element === Number(id)) || null;
}

function squadPlayers(state) {
  const names = new Set(state.squadNames);
  return state.players.filter(player => names.has(player.name));
}

function stagePlayer(player) {
  return player ? `<div class="stage-player"><span class="eyebrow">${escapeHtml(player.position)} / ${escapeHtml(player.team_short)}</span><b>${escapeHtml(player.web_name || player.name)}</b><small>${money(player.value_m)}</small></div>` : '<div class="stage-player"><span class="eyebrow">Open seat</span><b>Choose player</b></div>';
}

export function renderTransfers(state) {
  const owned = squadPlayers(state);
  const outgoing = playerById(state, state.transferOut);
  const incoming = playerById(state, state.transferIn);
  const outQuery = $("#outSearch").value.trim().toLowerCase();
  const inQuery = $("#inSearch").value.trim().toLowerCase();
  const market = state.players.filter(player => !state.squadNames.includes(player.name) && (!outgoing || player.position === outgoing.position));
  const outRows = owned.filter(player => player.name.toLowerCase().includes(outQuery));
  const inRows = market.filter(player => `${player.name} ${player.team}`.toLowerCase().includes(inQuery));
  $("#outCount").textContent = `${outRows.length} players`;
  $("#inCount").textContent = outgoing ? `${inRows.length} ${outgoing.position}` : `${inRows.length} players`;
  $("#outList").replaceChildren(...outRows.map(player => playerRow(player, { selected: player.element === state.transferOut, onClick: item => {
    state.transferOut = item.element;
    if (incoming?.position !== item.position) state.transferIn = null;
    renderTransfers(state);
  } })));
  $("#inList").replaceChildren(...inRows.slice(0, 120).map(player => playerRow(player, { selected: player.element === state.transferIn, onClick: item => {
    state.transferIn = item.element;
    renderTransfers(state);
  } })));
  $("#swapStage").innerHTML = `${stagePlayer(outgoing)}<span class="stage-arrow" aria-hidden="true">→</span>${stagePlayer(incoming)}`;
  $("#transferHeadline").textContent = outgoing && incoming ? `${outgoing.web_name} to ${incoming.web_name}` : outgoing ? `Find a ${outgoing.position} replacement` : "Choose an outgoing player";
  $("#priceDelta").textContent = outgoing && incoming ? signed(outgoing.value_m - incoming.value_m) : "--";
  $("#pointsDelta").textContent = outgoing && incoming && state.predictionAvailable ? signed(incoming.predicted_points - outgoing.predicted_points) : "--";
  $("#analyseTransfers").disabled = owned.length !== 15 || !state.predictionAvailable;
  if (!owned.length) $("#outList").innerHTML = '<p class="empty-copy">Build your squad in My Team before staging a transfer.</p>';
}

function renderAnalysis(data) {
  const output = $("#transferAnalysis");
  const best = data.best;
  output.innerHTML = `<strong>${best?.transfers ? `${best.transfers} transfer${best.transfers === 1 ? "" : "s"} lead the model` : "Hold this week"}</strong>
    <p>${best?.transfers ? `${number(best.gain)} net projected points after hits.` : "No move improves the net projection after transfer costs."}</p>
    <div class="analysis-table">${data.rows.map(row => `<div class="analysis-row"><b>${row.transfers}</b><span>${number(row.gross)}</span><span>${row.hit ? `−${row.hit}` : "0"}</span><span>${escapeHtml(row.out.join(", ") || "Hold")} ${row.in.length ? `→ ${escapeHtml(row.in.join(", "))}` : ""}</span></div>`).join("")}</div>`;
}

const METRICS = [
  ["Projected points", "predicted_points", 1], ["Form", "form", 1], ["Total points", "total_points", 0],
  ["Minutes", "minutes", 0], ["Goals", "goals_scored", 0], ["Assists", "assists", 0],
  ["Clean sheets", "clean_sheets", 0], ["Bonus", "bonus", 0], ["ICT index", "ict_index", 1],
  ["Expected goals", "expected_goals", 2], ["Expected assists", "expected_assists", 2], ["Ownership %", "selected_by", 1],
];

export function renderComparison(state) {
  const first = playerById(state, $("#compareA").value);
  const second = playerById(state, $("#compareB").value);
  const arena = $("#comparisonArena");
  if (!first || !second) {
    arena.innerHTML = '<p class="empty-copy">Choose two players to unlock the head-to-head.</p>';
    return;
  }
  arena.innerHTML = `<div class="duel-header"><div class="duel-player"><span class="eyebrow">${escapeHtml(first.team)}</span><strong>${escapeHtml(first.web_name)}</strong></div>
      <span class="versus">VS</span><div class="duel-player"><span class="eyebrow">${escapeHtml(second.team)}</span><strong>${escapeHtml(second.web_name)}</strong></div></div>
    ${METRICS.map(([label, key, digits]) => {
      const a = Number(first[key]);
      const b = Number(second[key]);
      return `<div class="metric-row"><b class="${a > b ? "leads" : ""}">${number(first[key], digits)}</b><span>${escapeHtml(label)}</span><b class="${b > a ? "leads" : ""}">${number(second[key], digits)}</b></div>`;
    }).join("")}`;
  arena.querySelectorAll(".duel-player").forEach((node, index) => node.addEventListener("click", () => openProfile(index ? second : first, state.predictionAvailable)));
}

function captainScore(player, predictionAvailable) {
  return predictionAvailable ? Number(player.predicted_points ?? 0) : Number(player.form ?? 0);
}

export function renderCaptain(state) {
  const squad = squadPlayers(state);
  const pool = state.captainPool === "squad" ? squad : state.players;
  const ranked = [...pool].filter(player => player.status === "a").sort((a, b) => captainScore(b, state.predictionAvailable) - captainScore(a, state.predictionAvailable)).slice(0, 8);
  const lead = ranked[0];
  $("#captainSummary").textContent = state.predictionAvailable ? "Ranked by the current model projection, with form alongside." : "Prediction export unavailable. Ranked by official FPL form only.";
  $("#captainSpotlight").innerHTML = lead ? `<span class="eyebrow">Lead candidate</span><strong>${escapeHtml(lead.web_name || lead.name)}</strong>
    <span class="spot-points">${number(captainScore(lead, state.predictionAvailable))}</span><p>${state.predictionAvailable ? "projected points" : "official form"} · ${escapeHtml(lead.team)}</p>` : '<p>No available candidates in this pool.</p>';
  $("#captainRunway").innerHTML = ranked.map((player, index) => `<button class="runway-row" type="button" data-player-id="${player.element}">
    <span class="runway-rank">${String(index + 1).padStart(2, "0")}</span><span><b>${escapeHtml(player.name)}</b><small>${escapeHtml(player.team)} · ${escapeHtml(player.position)}</small></span>
    <b>${number(player.predicted_points)}</b><b>${number(player.form)}</b><b>${money(player.value_m)}</b></button>`).join("");
  $("#captainRunway").querySelectorAll("[data-player-id]").forEach(button => button.addEventListener("click", () => {
    const player = playerById(state, button.dataset.playerId);
    if (player) openProfile(player, state.predictionAvailable);
  }));
}

export function initialiseDecisions(state) {
  $("#outSearch").addEventListener("input", () => renderTransfers(state));
  $("#inSearch").addEventListener("input", () => renderTransfers(state));
  $("#resetTransfer").addEventListener("click", () => {
    state.transferOut = null;
    state.transferIn = null;
    $("#transferAnalysis").replaceChildren();
    renderTransfers(state);
  });
  $("#analyseTransfers").addEventListener("click", async () => {
    try {
      $("#transferAnalysis").textContent = "Running the existing transfer optimiser…";
      renderAnalysis(await postJson("/api/transfers", { squad: state.squadNames, free: 1, bank: 0, max: 3 }));
    } catch (error) {
      $("#transferAnalysis").textContent = error.message;
    }
  });
  const options = ['<option value="">Choose a player</option>', ...state.players.map(player => `<option value="${player.element}">${escapeHtml(player.name)} · ${escapeHtml(player.team_short)}</option>`)].join("");
  $("#compareA").innerHTML = options;
  $("#compareB").innerHTML = options;
  $("#compareA").addEventListener("change", () => renderComparison(state));
  $("#compareB").addEventListener("change", () => renderComparison(state));
  $("#swapCompare").addEventListener("click", () => {
    const first = $("#compareA").value;
    $("#compareA").value = $("#compareB").value;
    $("#compareB").value = first;
    renderComparison(state);
  });
  $$('[data-captain-pool]').forEach(button => button.addEventListener("click", () => {
    state.captainPool = button.dataset.captainPool;
    $$('[data-captain-pool]').forEach(item => item.setAttribute("aria-pressed", String(item === button)));
    renderCaptain(state);
  }));
}
