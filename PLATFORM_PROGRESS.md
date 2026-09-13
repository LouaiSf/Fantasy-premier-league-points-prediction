# FPL Assistant Platform Progress

Last updated: 2026-09-13
Branch: `web-platform`

## Completed work

- Audited the production Flask app, optimiser integration, prototype, design system, local season data, and Git state.
- Created the `web-platform` branch from `origin/main` at `4dee8080`.
- Confirmed the production app already delegates squad and transfer decisions to `scripts/optimise.py`; that seam is preserved untouched (`/api/squad`, `/api/transfers`, `/api/chips`, `/api/watchlist`).
- Built `webapp/platform_data.py`, a read-only local adapter over `data/<season>/{teams,fixtures,players_raw}.csv` that produces an honest "unavailable" snapshot when those files are missing, and a full player/team/fixture snapshot when they are present.
- Replaced the single-page template with a routed broadcast-style shell (`webapp/templates/base.html` + `index.html`, `webapp/static/css/platform.css`) and six ES modules (`api.js`, `ui.js`, `app.js`, `team.js`, `decisions.js`, `editorial.js`) implementing all seven product surfaces:
  - **My Team** — squad editor dialog with live legality checks (15 players, 2/5/5/3 shape, max 3 per club), pitch rendering, bench, captain read-out, availability desk.
  - **Player Profile** — accessible `<dialog>` opened from any player marker/row, shows stats and an explicit "prediction unavailable" note when there is no model export.
  - **Transfer Studio** — out/in search-and-pick desk, staged swap preview with price/points delta, calls the real `/api/transfers` optimiser (disabled honestly when predictions are unavailable).
  - **Player Comparison** — head-to-head metric table for any two players from the local snapshot.
  - **Captain & Form** — ranked shortlist over squad-only or all-players pool, with an explicit fallback message ("ranked by official FPL form only") when predictions are unavailable.
  - **News Wire** — briefing built from real `status`/`news`/`chance_of_playing_next_round` fields, filterable (all/squad/availability), capped at the top 24 with an overflow notice instead of dumping all 237 items.
  - **Fixture Matrix** — next-8-gameweek difficulty grid per club from `fixtures.csv`, with a squad-only toggle.
- Added `tests/test_platform_data.py` and `tests/test_webapp.py` (pytest).
- Fixed a `/favicon.ico` 404 console-noise issue by serving a 204 for it (the page already ships an inline data-URI icon).
- Added `.playwright-mcp/` to `.gitignore` alongside the existing `.playwright-cli/` (local QA scratch output, not project artifacts).
- Committed and pushed to `origin/web-platform` (commit `77529c82`).

## Current work in progress

None — the seven-surface milestone is implemented, tested, and verified live in a real browser (see evidence below). Next step is the model-retraining decision below, or further visual/accessibility polish if the user prefers to stay on the local-data-only path.

## Remaining work

- Decide whether to regenerate `predictions_next_gw.csv` (requires retraining/restoring `saved_models/*/*.joblib`, out of scope for "web platform" work without explicit sign-off — see blocker below).
- Optional polish: keyboard-navigation pass through squad editor and comparison pickers, dark/light contrast check against `DESIGN.md` tokens, mobile pass at 375px in a live browser (only static screenshots existed from the prior session).

## Known blockers or decisions needed

- `predictions_next_gw.csv` is not present, and `saved_models/direct/<POS>/*.joblib` binaries genuinely do not exist on disk (only `features.json`/`meta.json` metadata is checked in — confirmed by directory listing, not just `.gitignore`). Regenerating them means running the training pipeline, which is a materially different, longer task than building the platform — **needs explicit user go-ahead** before I spend time on it. Until then, all prediction-dependent surfaces (auto-pick, transfer analysis, captain projections) correctly show honest unavailable/fallback states rather than fabricated numbers.
- Premier League player photos and crests are external prototype assets; production publication still needs rights confirmation, as recorded in `DESIGN.md`.

## Test and verification evidence

- `pytest tests/` → 3 passed (Python 3.13, Flask installed via `C:\Python313\python.exe -m pip install flask pandas pytest` — no project venv exists; this is the interpreter used for all verification).
- Flask test-client smoke check of all page and API routes: `/`, `/team`, `/transfers`, `/comparison`, `/captain`, `/news`, `/fixtures` → 200; `/api/meta`, `/api/players` → 400 with the expected "predictions_next_gw.csv not found" message (honest, not a bug).
- Live browser verification (Playwright, real Flask dev server, real local season data — 746 players, 20 clubs, GW10):
  - Built and saved a legal 15-player squad through the actual squad-editor dialog; pitch rendered a 5-3-2 formation, bench populated, captain armband assigned, availability desk listed 5 real injury/suspension notes from the local snapshot.
  - Opened a player profile dialog — correct stats plus the "Prediction unavailable" note.
  - Staged a Transfer Studio swap (Clarke → Gabriel); price delta computed correctly (−2.6); "Run full analysis" correctly disabled with no prediction export.
  - Player Comparison rendered a full head-to-head for two selected players out of 746 options.
  - Captain & Form showed an 8-player runway with the explicit form-only fallback message.
  - News Wire showed a lead story plus 24 capped cards from a 237-item local snapshot.
  - Fixture Matrix rendered 21 rows (header + 20 clubs).
  - Zero JavaScript console errors after the favicon fix (previously one harmless 404).
- Found and killed 4 orphaned Flask server processes left running from the prior (interrupted) session's `uv`-managed interpreters, which were causing inconsistent responses on port 5000 during verification — not a code defect, an artifact of the earlier session being cut off mid-work.

## Next recommended milestone

Get a decision from the user on the prediction-regeneration blocker above. If they want real predictions, the next milestone is restoring/retraining `saved_models/*/*.joblib` and re-running `scripts/predict_gameweek.py`. If they want to stay local-data-only for now, the next milestone is an accessibility/keyboard-navigation and mobile-viewport polish pass on the seven surfaces already shipped.
