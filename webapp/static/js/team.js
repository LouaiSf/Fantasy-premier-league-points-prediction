import { escapeHtml, postJson, money, number } from "./api.js";
import { $, openProfile, playerRow, toast } from "./ui.js";

const SQUAD_SHAPE = { GK: 2, DEF: 5, MID: 5, FWD: 3 };

function squadPlayers(state) {
  const wanted = new Set(state.squadNames);
  return state.players.filter(player => wanted.has(player.name));
}

function score(player) {
  return Number(player.predicted_points ?? player.form ?? 0);
}

function previewSquad(players) {
  const sorted = [...players].sort((a, b) => score(b) - score(a));
  const xi = [];
  const minimums = { GK: 1, DEF: 3, MID: 2, FWD: 1 };
  Object.entries(minimums).forEach(([position, count]) => {
    xi.push(...sorted.filter(player => player.position === position).slice(0, count));
  });
  sorted.forEach(player => {
    if (xi.length < 11 && !xi.includes(player) && player.position !== "GK") xi.push(player);
  });
  const bench = sorted.filter(player => !xi.includes(player));
  const formation = ["DEF", "MID", "FWD"].map(position => xi.filter(player => player.position === position).length).join("-");
  return { xi, bench, captain: xi[0] ?? null, formation, xi_points: xi.reduce((total, player) => total + score(player), 0), spend: players.reduce((total, player) => total + Number(player.value_m), 0) };
}

function marker(player, captain, predictionAvailable) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "player-marker";
  button.setAttribute("aria-label", `Open ${player.name} profile`);
  button.innerHTML = `${player.photo ? `<img src="${escapeHtml(player.photo)}" width="52" height="60" alt="">` : "<span></span>"}
    <span><b>${escapeHtml(player.web_name || player.name)}</b><small>${escapeHtml(player.team_short || player.team)}</small></span>
    <span class="points-chip">${number(player.predicted_points ?? player.form)}</span>${captain ? '<span class="armband">C</span>' : ""}`;
  button.querySelector("img")?.addEventListener("error", event => event.currentTarget.remove());
  button.addEventListener("click", () => openProfile(player, predictionAvailable));
  return button;
}

export function renderTeam(state) {
  const players = squadPlayers(state);
  const result = state.teamResult || (players.length === 15 ? previewSquad(players) : null);
  $("#squadCount").textContent = `${players.length} / 15`;
  $("#autoPick").disabled = !state.predictionAvailable;
  $("#teamSource").textContent = state.teamResult ? "Optimised by scripts/optimise.py" : players.length ? "Saved squad preview" : "No squad selected";
  const pitch = $("#pitch");
  pitch.replaceChildren();
  if (!result) {
    pitch.innerHTML = `<div class="pitch-empty"><span class="eyebrow">Squad required</span><h2>Build your 15</h2><p>Use the squad editor, or restore the local prediction export to run the optimiser.</p></div>`;
    $("#benchList").replaceChildren();
    $("#teamProjection").textContent = "--";
    $("#formationValue").textContent = "--";
    $("#squadCost").textContent = players.length ? money(players.reduce((total, player) => total + player.value_m, 0)) : "--";
    $("#availabilityValue").textContent = "--";
    $("#captainRead").textContent = "Choose a squad to see the captain call.";
    $("#squadAlerts").textContent = "No squad loaded.";
    return;
  }
  ["GK", "DEF", "MID", "FWD"].forEach(position => {
    const line = document.createElement("div");
    line.className = "formation-line";
    result.xi.filter(player => player.position === position).forEach(player => line.append(marker(player, result.captain?.name === player.name, state.predictionAvailable)));
    if (line.childElementCount) pitch.append(line);
  });
  const bench = $("#benchList");
  bench.replaceChildren(...result.bench.map(player => playerRow(player, { onClick: item => openProfile(item, state.predictionAvailable) })));
  const flagged = players.filter(player => player.status !== "a" || (player.chance_of_playing_next_round ?? 100) < 100);
  $("#teamProjection").textContent = state.predictionAvailable ? number(result.xi_points) : "N/A";
  $("#formationValue").textContent = result.formation;
  $("#squadCost").textContent = money(result.spend);
  $("#availabilityValue").textContent = `${players.length - flagged.length}/${players.length}`;
  $("#captainRead").innerHTML = result.captain
    ? `<strong>${escapeHtml(result.captain.name)}</strong><span>${state.predictionAvailable ? `${number(result.captain.predicted_points)} projected points` : `${number(result.captain.form)} form`}</span>`
    : "No captain recommendation available.";
  $("#squadAlerts").innerHTML = flagged.length
    ? flagged.map(player => `<p><strong>${escapeHtml(player.web_name)}</strong><br>${escapeHtml(player.news || `${player.chance_of_playing_next_round ?? 0}% chance of playing`)}</p>`).join("")
    : "All selected players are currently marked available in the local snapshot.";
}

function validateSelection(state, selected) {
  const chosen = state.players.filter(player => selected.has(player.name));
  if (chosen.length !== 15) return `Choose exactly 15 players. ${chosen.length} selected.`;
  for (const [position, required] of Object.entries(SQUAD_SHAPE)) {
    if (chosen.filter(player => player.position === position).length !== required) return `Squad shape must be 2 GK, 5 DEF, 5 MID and 3 FWD.`;
  }
  const clubCounts = chosen.reduce((counts, player) => counts.set(player.team, (counts.get(player.team) || 0) + 1), new Map());
  if ([...clubCounts.values()].some(count => count > 3)) return "A squad can contain no more than three players from one club.";
  return "";
}

export function initialiseTeam(state, onSquadChange) {
  let selected = new Set(state.squadNames);
  const drawPicker = () => {
    const query = $("#squadSearch").value.trim().toLowerCase();
    const visible = state.players.filter(player => `${player.name} ${player.team}`.toLowerCase().includes(query));
    $("#squadPicker").replaceChildren(...visible.map(player => playerRow(player, {
      selected: selected.has(player.name),
      onClick: item => {
        if (selected.has(item.name)) selected.delete(item.name);
        else if (selected.size < 15) selected.add(item.name);
        drawPicker();
      },
    })));
    const problem = validateSelection(state, selected);
    $("#pickerStatus").textContent = problem || "Legal 15-player squad ready to save.";
    $("#saveSquad").disabled = Boolean(problem);
  };
  $("#editSquad").addEventListener("click", () => {
    selected = new Set(state.squadNames);
    $("#squadSearch").value = "";
    drawPicker();
    $("#squadDialog").showModal();
  });
  $("#squadSearch").addEventListener("input", drawPicker);
  $("#closeSquadDialog").addEventListener("click", () => $("#squadDialog").close());
  $("#cancelSquad").addEventListener("click", () => $("#squadDialog").close());
  $("#saveSquad").addEventListener("click", () => {
    state.squadNames = [...selected];
    state.teamResult = null;
    localStorage.setItem("fpl-assistant-squad", JSON.stringify(state.squadNames));
    $("#squadDialog").close();
    onSquadChange();
    toast("Squad saved on this device.");
  });
  $("#autoPick").addEventListener("click", async () => {
    const button = $("#autoPick");
    button.disabled = true;
    button.textContent = "Optimising…";
    try {
      const result = await postJson("/api/squad", { budget: 100, lock: [], ban: [] });
      state.teamResult = result;
      state.squadNames = [...result.xi, ...result.bench].map(player => player.name);
      localStorage.setItem("fpl-assistant-squad", JSON.stringify(state.squadNames));
      onSquadChange();
      toast("Optimal squad loaded from the prediction pipeline.");
    } catch (error) {
      toast(error.message);
    } finally {
      button.textContent = "Run auto-pick";
      button.disabled = !state.predictionAvailable;
    }
  });
}
