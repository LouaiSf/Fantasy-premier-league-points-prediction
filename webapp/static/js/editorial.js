import { escapeHtml, number } from "./api.js";
import { $, $$, openProfile } from "./ui.js";

function squadPlayers(state) {
  const names = new Set(state.squadNames);
  return state.players.filter(player => names.has(player.name));
}

function newsItems(state) {
  const squad = new Set(state.squadNames);
  return state.players.filter(player => {
    const hasUpdate = Boolean(player.news) || player.status !== "a" || (player.chance_of_playing_next_round ?? 100) < 100;
    if (!hasUpdate) return false;
    if (state.newsFilter === "squad") return squad.has(player.name);
    if (state.newsFilter === "doubt") return player.status !== "a" || (player.chance_of_playing_next_round ?? 100) < 100;
    return true;
  }).sort((a, b) => Number(a.chance_of_playing_next_round ?? 100) - Number(b.chance_of_playing_next_round ?? 100));
}

function updateCopy(player) {
  if (player.news) return player.news;
  if ((player.chance_of_playing_next_round ?? 100) < 100) return `FPL lists a ${number(player.chance_of_playing_next_round, 0)}% chance of playing next round.`;
  return `Current availability status: ${player.status}.`;
}

export function renderNews(state) {
  const items = newsItems(state);
  $("#newsCount").textContent = String(newsItems({ ...state, newsFilter: "all" }).length);
  const lead = items[0];
  $("#leadStory").innerHTML = lead ? `<div></div><div class="lead-copy"><span class="eyebrow">Lead squad update / ${escapeHtml(lead.team)}</span>
    <h2>${escapeHtml(lead.name)}</h2><p>${escapeHtml(updateCopy(lead))}</p><button class="button button-primary" type="button" data-lead-id="${lead.element}">Open player profile</button></div>`
    : '<div></div><div class="lead-copy"><span class="eyebrow">No active bulletin</span><h2>The wire is clear</h2><p>The local FPL player snapshot contains no news matching this filter.</p></div>';
  $("#leadStory [data-lead-id]")?.addEventListener("click", () => openProfile(lead, state.predictionAvailable));
  $("#newsGrid").innerHTML = items.slice(1, 24).map(player => `<article class="news-card"><span class="eyebrow">${escapeHtml(player.team)} / ${escapeHtml(player.position)}</span>
    <h3>${escapeHtml(player.name)}</h3><p>${escapeHtml(updateCopy(player))}</p><button class="text-button" type="button" data-news-id="${player.element}">Open dossier</button></article>`).join("");
  if (items.length > 24) $("#newsGrid").insertAdjacentHTML("beforeend", `<article class="news-card"><span class="eyebrow">Briefing limit</span><h3>${items.length - 24} further updates</h3><p>Narrow the wire with My squad or Availability to focus the desk.</p></article>`);
  $("#newsGrid").querySelectorAll("[data-news-id]").forEach(button => button.addEventListener("click", () => {
    const player = state.players.find(item => item.element === Number(button.dataset.newsId));
    if (player) openProfile(player, state.predictionAvailable);
  }));
}

export function renderFixtures(state) {
  const squadTeams = new Set(squadPlayers(state).map(player => player.team));
  const squadOnly = $("#fixtureSquadOnly").checked;
  const teams = state.teams.filter(team => !squadOnly || squadTeams.has(team.name));
  const start = state.gameweek || 1;
  const gameweeks = Array.from({ length: 8 }, (_, index) => start + index);
  const header = `<div class="matrix-row"><div class="matrix-cell matrix-club"><span class="eyebrow">Club</span></div>${gameweeks.map(gameweek => `<div class="matrix-cell"><span class="eyebrow">GW${gameweek}</span></div>`).join("")}</div>`;
  const rows = teams.map(team => {
    const fixtures = new Map(team.fixtures.map(fixture => [fixture.gameweek, fixture]));
    return `<div class="matrix-row"><div class="matrix-cell matrix-club">${escapeHtml(team.name)}</div>${gameweeks.map(gameweek => {
      const fixture = fixtures.get(gameweek);
      return fixture ? `<div class="matrix-cell fixture-cell fdr-${fixture.difficulty}" title="${escapeHtml(fixture.opponent_name)} ${fixture.venue}">
        ${escapeHtml(fixture.opponent)}<small>${fixture.venue} · FDR ${fixture.difficulty}</small></div>` : '<div class="matrix-cell fixture-cell"><span>--</span><small>No fixture</small></div>';
    }).join("")}</div>`;
  }).join("");
  $("#fixtureMatrix").innerHTML = teams.length ? header + rows : '<div class="pitch-empty"><h2>No clubs to show</h2><p>Add players to your squad or turn off the squad-only filter.</p></div>';
}

export function initialiseEditorial(state) {
  $$('[data-news-filter]').forEach(button => button.addEventListener("click", () => {
    state.newsFilter = button.dataset.newsFilter;
    $$('[data-news-filter]').forEach(item => item.setAttribute("aria-pressed", String(item === button)));
    renderNews(state);
  }));
  $("#fixtureSquadOnly").addEventListener("change", () => renderFixtures(state));
}
