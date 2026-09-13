import { escapeHtml, money, number } from "./api.js";

export const $ = selector => document.querySelector(selector);
export const $$ = selector => [...document.querySelectorAll(selector)];

let toastTimer = 0;

export function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("is-visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => node.classList.remove("is-visible"), 2800);
}

export function playerRow(player, options = {}) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `list-player${options.selected ? " is-selected" : ""}`;
  button.dataset.playerId = String(player.element);
  button.innerHTML = `${player.photo ? `<img src="${escapeHtml(player.photo)}" width="40" height="48" alt="">` : "<span></span>"}
    <span><b>${escapeHtml(player.web_name || player.name)}</b><small>${escapeHtml(player.team_short || player.team)} · ${escapeHtml(player.position)} · ${money(player.value_m)}</small></span>
    <strong>${number(player.predicted_points ?? player.form)}</strong>`;
  button.querySelector("img")?.addEventListener("error", event => event.currentTarget.remove());
  if (options.onClick) button.addEventListener("click", () => options.onClick(player));
  return button;
}

export function openProfile(player, predictionAvailable) {
  const dialog = $("#playerDialog");
  const metrics = [
    [predictionAvailable ? "Projection" : "Projection", player.predicted_points],
    ["Form", player.form], ["Total points", player.total_points], ["Minutes", player.minutes],
    ["Goals", player.goals_scored], ["Assists", player.assists], ["Clean sheets", player.clean_sheets],
    ["Bonus", player.bonus], ["ICT index", player.ict_index], ["xG", player.expected_goals],
    ["xA", player.expected_assists], ["Owned", `${number(player.selected_by)}%`],
  ];
  $("#playerProfile").innerHTML = `<div class="profile-hero">
      ${player.photo ? `<img src="${escapeHtml(player.photo)}" width="160" height="192" alt="">` : "<span></span>"}
      <div><span class="eyebrow">${escapeHtml(player.team)} / ${escapeHtml(player.position)}</span>
      <h2 id="dialogName">${escapeHtml(player.name)}</h2><strong>${money(player.value_m)}</strong></div></div>
    <div class="profile-body"><div class="profile-stats">${metrics.map(([label, value]) => `<div class="profile-stat"><span>${escapeHtml(label)}</span><strong>${typeof value === "string" ? escapeHtml(value) : number(value)}</strong></div>`).join("")}</div>
    ${player.news ? `<div class="profile-note"><strong>Team news</strong><br>${escapeHtml(player.news)}</div>` : ""}
    ${predictionAvailable ? "" : "<div class=\"profile-note\"><strong>Prediction unavailable</strong><br>Restore or regenerate the local prediction export to populate forecast metrics.</div>"}</div>`;
  $("#playerProfile img")?.addEventListener("error", event => event.currentTarget.remove());
  dialog.showModal();
}

function positionBlade() {
  const nav = $(".primary-nav");
  const active = nav.querySelector("[aria-current='page']");
  const blade = $(".nav-blade");
  if (!active) return;
  blade.style.inlineSize = `${active.offsetWidth}px`;
  blade.style.transform = `translateX(${active.offsetLeft}px)`;
}

export function showPage(page, push = false) {
  $$("[data-page]").forEach(section => { section.hidden = section.dataset.page !== page; });
  $$("[data-route]").forEach(link => {
    if (link.dataset.route === page) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  positionBlade();
  if (push) history.pushState({ page }, "", `/${page}`);
  document.title = `${$("[data-page]:not([hidden]) h1")?.textContent || "FPL Assistant"} · FPL Assistant`;
}

export function initialiseChrome(snapshot) {
  const ticker = $("#clubTicker");
  snapshot.teams.forEach(team => {
    const item = document.createElement("span");
    item.className = "ticker-club";
    item.innerHTML = `<span>${escapeHtml(team.short_name)}</span>`;
    ticker.append(item);
  });
  $$('[data-gameweek]').forEach(node => { node.textContent = snapshot.gameweek ? `GW${snapshot.gameweek}` : "GW--"; });
  const state = $("#dataState");
  state.classList.add(snapshot.prediction_available ? "is-ready" : "is-limited");
  state.querySelector("span:last-child").textContent = snapshot.prediction_available
    ? `${snapshot.season} · predictions ready`
    : `${snapshot.season} · local data only`;
  $$("[data-route]").forEach(link => link.addEventListener("click", event => {
    event.preventDefault();
    showPage(link.dataset.route, true);
    $("#main").focus({ preventScroll: true });
  }));
  window.addEventListener("popstate", event => showPage(event.state?.page || location.pathname.slice(1) || "team"));
  window.addEventListener("resize", positionBlade);
  $("#closeDialog").addEventListener("click", () => $("#playerDialog").close());
  $("#playerDialog").addEventListener("click", event => {
    if (event.target === $("#playerDialog")) $("#playerDialog").close();
  });
  showPage(document.body.dataset.initialPage || "team");
}
