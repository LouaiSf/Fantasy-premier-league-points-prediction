import { requestJson } from "./api.js";
import { initialiseChrome } from "./ui.js";
import { initialiseTeam, renderTeam } from "./team.js";
import { initialiseDecisions, renderCaptain, renderComparison, renderTransfers } from "./decisions.js";
import { initialiseEditorial, renderFixtures, renderNews } from "./editorial.js";

function savedSquad() {
  try {
    const value = JSON.parse(localStorage.getItem("fpl-assistant-squad") || "[]");
    return Array.isArray(value) ? value.filter(item => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function renderAll(state) {
  renderTeam(state);
  renderTransfers(state);
  renderComparison(state);
  renderCaptain(state);
  renderNews(state);
  renderFixtures(state);
}

async function start() {
  try {
    const snapshot = await requestJson("/api/platform");
    const knownNames = new Set(snapshot.players.map(player => player.name));
    const state = {
      players: snapshot.players,
      teams: snapshot.teams,
      gameweek: snapshot.gameweek,
      squadNames: savedSquad().filter(name => knownNames.has(name)),
      teamResult: null,
      transferOut: null,
      transferIn: null,
      captainPool: "squad",
      newsFilter: "all",
      predictionAvailable: snapshot.prediction_available,
    };
    initialiseChrome(snapshot);
    initialiseTeam(state, () => renderAll(state));
    initialiseDecisions(state);
    initialiseEditorial(state);
    renderAll(state);
  } catch (error) {
    document.querySelector("#dataState span:last-child").textContent = "Local data unavailable";
    document.querySelector("#dataState").classList.add("is-limited");
    document.querySelector("#pitch").innerHTML = `<div class="pitch-empty"><h2>Platform data unavailable</h2><p>${error.message}</p></div>`;
  }
}

start();
