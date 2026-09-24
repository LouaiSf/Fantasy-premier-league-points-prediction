# FPL Platform v2 implementation handoff

This handoff tracks execution of `PLATFORM_V2_IMPLEMENTATION_PLAN.md`. The planning audit is complete; continue implementing the ordered product slices. Read the plan and inspect `git status` before every resumed work session.

## Workspace and preservation

- Workspace: `C:\Users\HP\Desktop\FPL PROJECT - Copy\Fantasy-premier-league-points-prediction`
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

- Implementation commit: pending.
- Handoff/evidence commit: pending.
- Push: pending.

### Blockers and exact next action

No Slice 1 blocker. Implement Slice 2 now: inspect the transfer UI, `/api/transfers` contract, and `compute_transfers`/`solve_squad`; stage ordered outgoing/incoming ID pairs, preserve optimizer choices without inventing pairs, validate exact finance in tenths, constrain the optimizer with staged locks, and add save/hold/apply plus scenario comparison per the plan. Add focused tests and run browser QA once at desktop and 375px after the slice is stable.

## Official FPL rules already checked for later slices

- [2026/27 chip rules](https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627): two chip sets, halves split after GW19, one chip per GW, Free Hit unavailable GW1, and Free Hit in GW19 prevents using it again in GW20.
- [2026/27 rule changes](https://www.premierleague.com/en/news/4679873): free transfers roll up to five; no AFCON bonus transfers.
- [Official FPL FAQ](https://www.premierleague.com/en/news/4661030): Wildcard and Free Hit unavailable GW1; saved free transfers remain after a chip.
- Official rules do not prohibit selecting a goalkeeper as captain or vice-captain. Slice 4 should remove the app’s goalkeeper exclusion in `solve_squad`; preserve starting-XI eligibility and other official squad rules.
