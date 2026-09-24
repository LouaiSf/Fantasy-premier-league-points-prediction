# FPL Platform v2 implementation handoff

This handoff tracks execution of `PLATFORM_V2_IMPLEMENTATION_PLAN.md`. The planning audit is complete; continue implementing the ordered product slices. Read the plan and inspect `git status` before every resumed work session.

## Workspace and preservation

- Workspace: `C:\Users\pc\Desktop\Projects\Fantasy-premier-league-points-prediction` (previously `C:\Users\HP\...`)
- Branch/remote: `main` / `origin` (`LouaiSf/Fantasy-premier-league-points-prediction`)
- Preserve the pre-existing dirty/untracked files: `data/2026-27/players_raw.csv`, `predictions_next_gw.csv`, `predictions_next_gw.manifest.json`, `CONTINUE_PROGRESS.md`, `CONTINUE_PROMPT.md`, `IMPLEMENTATION_PROMPT.md`, `debug.log`, and `webapp/frontend/.agents/`, `.claude/`, `.continue/`, `.kilocode/`, `.qwen/`, `.windsurf/`.
- Do not stage those files. Stage only files owned by the current product increment and its handoff/evidence.
- Use OMO `mcp__git_bash__run` for Windows shell commands. Do not add a Co-authored-by trailer to commits.

## Delivery order

Follow the plan slices: (1) manager direct import and bounded league search; (2) actual multi-transfer staging and comparison; (3) Chip Advisor rules and evidence-based decisions; (4) adjacent wording, GK captain eligibility, and mobile fixes; (5) prioritized deadline board and saved scenarios. The final definition of done and acceptance matrix are in the implementation plan.

## Slice 1: manager import and league-name search

### Implemented

- Replaced the old entry/name lookup with direct entry ID or official FPL profile URL lookup, immediate public lineup preview, explicit import, and up to five season-scoped recent teams in local storage.
- Plain names route to a known-league search instead of the unsupported global name endpoint. The UI explains the search scope and shows progress, scanned standings pages/member count, partial results, and a manual rank/page starting point. Requests cancel on criteria changes.
- Added `GET /api/managers/leagues/<league_id>/search` with accent-insensitive matching, cursor/page scanning capped at five pages per request, deduplication, partial results on upstream failure, and typed range/limit errors. League standings responses use a short cache.
- Moved manager lookup above the My Team hero.
- Corrected URL validation to reject negative numeric IDs, non-FPL hosts/protocols, custom ports, and embedded credentials.

### Verification evidence

- `npm exec tsc -- --noEmit` passed.
- `npm run build` passed on Next.js 16.3.5 after the final URL-boundary and import-cleanup edits; optimized compilation, TypeScript, and static page generation all completed.
- `python -m pytest -q tests/test_manager_search.py tests/test_fpl_client.py`: 13 passed. `python -m py_compile webapp/manager_routes.py webapp/fpl_client.py` passed. `git diff --check` passed.
- Real browser at `/team`: entry ID `1` returned its live public manager and GW5 lineup preview; clicking “Set as my team” persisted that manager into the season-scoped Recent teams list. A full `https://fantasy.premierleague.com/entry/1/event/5` URL also resolved to that preview.
- Real browser search for `Chris` in league `314` (“Overall”) reported “Checked pages 1–5 · 250 members checked” and returned matching actual managers. This is bounded standings search, not global FPL search.
- Desktop viewport 1440×1000 and 375×812 were inspected. No document-level horizontal overflow at 375px; the manager lookup is above the hero. Browser console had 0 errors (one development warning).
- Screenshots: `artifacts/manager-search-desktop.png`, `artifacts/manager-search-mobile-375.png`.

### Commit/push

- Slice 1 implementation, handoff, and browser evidence: `17bcad95` (full SHA is in Git history), pushed to `origin/main`.
- Push verified: `origin/main` advanced from `9aa20df7` to `17bcad95`; the commit has no Co-authored-by trailer.

## Slice 2: multi-transfer Studio

### Implemented (commit `0d0cd120` "incomplete fixes" plus the follow-up commit)

- Backend: `/api/transfers` accepts optional paired `locked_out_elements`/`locked_in_elements` (max 5, equal length, unique, same position, owned/market membership, bank in tenths, club limit); invalid drafts return 400 `invalid_transfer_draft`. `compute_transfers()` locks incoming and bans outgoing indices, keeps real selling prices, returns `out_elements`/`in_elements` per row and `draft_constraints`. Counts below the staged length are failures ("needs at least N staged moves"). Bank must be in 0.1 steps and selling prices whole tenths.
- Frontend (`app/transfers/transfer-studio.tsx`, `lib/transfer-planning.ts`): ordered draft pairs with add/edit/remove, max-lowering guard, exact tenths finance, final-15 validation, explicit `Evaluate this draft` via `/api/lineup`, separate OUT/IN optimizer lists (never zipped), unconstrained vs staged-constraint comparison, save/reopen keyed by squad fingerprint, `Hold this week`, and a review-then-apply flow that updates local My Team only.
- Slice 4 item done early: goalkeeper captain/vice exclusion removed from `solve_squad` with a regression test.
- Follow-up fix: the storage effect referenced `currentSnapshot` before its declaration (ReferenceError whenever the squad was not 15 players); it now uses `snapshot`.

### Verification evidence

- `python -m pytest -q tests/test_optimise.py tests/test_webapp.py tests/test_fpl_client.py tests/test_manager_search.py`: 68 passed.
- `npm exec tsc -- --noEmit` and `npm run build` passed.
- Playwright run (Flask :5000 + `next start` :3000, squad seeded from `/api/squad`) at 1440x1000 and 375x812: staged 3 moves (3 rows, hit 8 pts with 1 free), edited the middle move, lowering max was refused with the expected message, evaluate showed gross 59.1 / net 51.1 / gain -13.0, the staged-constraint 3-transfer row gave the same -13.0, counts 0-2 showed "needs at least 3 staged moves", save then reload then reopen restored 3 rows, hold showed "Holding GW6", review listed all outs/ins/bank/hit/XI and apply navigated to /team. No horizontal overflow, 0 console errors.
- Screenshots: `artifacts/transfer-studio-desktop.png`, `artifacts/transfer-studio-mobile-375.png`.

### Not done / caveats

- No frontend unit-test runner exists in this repo (no vitest/jest), so the plan's client-level draft add/edit/remove test was covered by the browser run only. The draft logic lives inline in the page component.
- Transfer edge scenarios (club >3, negative bank, unavailable owned player) are covered by backend tests and the client validator, but were not each replayed in the browser.
- The follow-up commit is local; nothing was pushed in this session.

### Exact next action

Implement Slice 3 (Chip Advisor). Order: (1) single appearance weighting in `_projection_matrix()` with the p_plays=0.5 / 4.0 regression fixture; (2) owned unavailable players via `s['everyone']` and typed `unknown_player` 400; (3) per-GW chip eligibility across the GW19/20 boundary, GW1 and FH19->FH20, plus duplicate-planned-chip rejection; (4) status vocabulary `watch/consider/hold/unavailable/compare`, backend `primary_decision`, `inventory_source`, and null gains where counterfactuals are not implemented. Then Slice 4 remainder and Slice 5.

## Official FPL rules already checked for later slices

- [2026/27 chip rules](https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627): two chip sets, halves split after GW19, one chip per GW, Free Hit unavailable GW1, and Free Hit in GW19 prevents using it again in GW20.
- [2026/27 rule changes](https://www.premierleague.com/en/news/4679873): free transfers roll up to five; no AFCON bonus transfers.
- [Official FPL FAQ](https://www.premierleague.com/en/news/4661030): Wildcard and Free Hit unavailable GW1; saved free transfers remain after a chip.
- Official rules do not prohibit selecting a goalkeeper as captain or vice-captain. Slice 4 should remove the app’s goalkeeper exclusion in `solve_squad`; preserve starting-XI eligibility and other official squad rules.
