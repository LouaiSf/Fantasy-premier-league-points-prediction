# Starting Prompt for Luna

Implement the repository plan in `FPL_MANAGER_PLANNER_CHIPS_PLAN.md` end to end. Treat that file as the binding specification and `FPL_MANAGER_PLANNER_CHIPS_PROGRESS.md` as the only continuity ledger.

Start by reading, in this order:

1. `FPL_MANAGER_PLANNER_CHIPS_PLAN.md`
2. `FPL_MANAGER_PLANNER_CHIPS_PROGRESS.md`
3. `DESIGN.md`
4. `webapp/frontend/AGENTS.md`
5. `webapp/app.py`
6. `webapp/platform_data.py`
7. `scripts/optimise.py`, especially `load_predictions`, `load_horizon`, `solve_squad`, `compute_transfers`, and `compute_chips`
8. `scripts/predict_gameweek.py`, especially `predict_horizon`
9. `webapp/frontend/components/providers/app-provider.tsx`
10. `webapp/frontend/app/team/page.tsx`, `app/transfers/page.tsx`, `app/chips/page.tsx`, `lib/api.ts`, and `lib/types.ts`
11. `tests/test_webapp.py`, `tests/test_optimise.py`, and `tests/test_chip_advisor.py`

Then inspect `git status --short --branch`, the current HEAD/upstream, and the latest progress entry. Preserve every unrelated dirty or untracked file. In particular, do not stage the pre-existing CSV changes, `debug.log`, existing continuation/prompt notes, or generated frontend agent directories.

Execution rules:

- Follow the phases and acceptance criteria in the plan in order. Do not redesign the architecture or invent alternative product behavior.
- Reuse `compute_transfers` and `solve_squad`; Flask and React must not calculate their own transfer, XI, bench, or captain recommendations.
- Use FPL element IDs at boundaries and in storage. Names are display data only.
- Numeric manager lookup uses the public FPL entry/picks API. Text lookup must use the actual configured manager-search API contract. Search the repo/config/docs for that contract before coding. If it is absent, do not guess: complete ID lookup, return typed `search_not_configured` for text, and record the exact blocker in the progress ledger.
- Viewing another manager is read-only. Only the explicit “Set as my team” action mutates local state.
- The compact My Team planner considers only `0..free_transfers`; Transfer Studio remains the place for deliberate hits.
- Wire the existing multi-gameweek prediction matrix into Chip Advisor. A one-gameweek baseline adjusted by fixtures is never allowed to appear as a player-level future projection or point-labelled gain.
- Future chip candidates are `watch`, not `play`. `play` can describe only the current gameweek with complete model, squad, inventory, and policy evidence.
- Every chip recommendation must expose its formula inputs, runner-up, projection source, coverage, and uncertainty. Do not duplicate those formulas in TypeScript.
- Follow `DESIGN.md` and existing broadcast components. No inline static styles, raw new color system, emojis as icons, or generic card-grid redesign.
- Keep changes surgical. Add focused modules/components instead of growing already oversized files, but do not perform unrelated cleanup.
- Write a failing behavior test first for every backend/model boundary, then implement the smallest passing change. Do not delete or weaken tests.
- TypeScript remains strict: no `any`, `@ts-ignore`, `@ts-expect-error`, or unsafe assertion used to bypass a contract.

Progress and Git rules are mandatory:

- At the end of every meaningful phase, update `FPL_MANAGER_PLANNER_CHIPS_PROGRESS.md` with completed work, evidence, risks, and the next exact action.
- Run the phase's tests before committing.
- Stage explicit paths only, inspect the staged diff, commit in the repository's imperative sentence style, and push immediately to the configured upstream.
- Never add a co-author or attribution trailer and never override the repository owner's author identity.
- If push fails, record the failure and resolve it before starting another phase.
- On a resumed session, verify the recorded SHA locally and upstream, then continue from “Next exact action” without repeating completed work.

Verification is part of implementation, not a final suggestion. Before stopping, run the Python tests, frontend lint/build, and the manual browser scenarios in Phase 6 at 375, 768, and 1280 px. Use the real running UI to verify search, preview, import, persistence, 0/1/2-transfer plans, applying a plan, single-GW chip degradation, multi-GW chip evidence, keyboard focus, errors, and responsive layout.

Stop only when every acceptance criterion in the plan is complete, every phase commit is pushed, the progress ledger is current, automated gates pass, and the three changed user journeys have been observed working in the browser. If the only blocker is the missing text-search provider contract, finish and verify all non-blocked work, record the exact required contract, and report that one blocker without inventing it.
