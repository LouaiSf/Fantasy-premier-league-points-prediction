# FPL Manager Planner and Chip Advisor Progress

Last updated: 2026-09-22
Plan status: implementation in progress; Phases 1, 2, 3, 4, and 5 complete

## Repository baseline

- Branch: `main`
- Upstream: `origin/main`
- Starting implementation baseline before the plan commit: `106f6ad9`
- Existing optimizer/API/frontend behavior was inspected and recorded in `FPL_MANAGER_PLANNER_CHIPS_PLAN.md`.

## User-owned worktree state to preserve

The following existed before this plan and must not be staged by feature commits unless the user separately requests it:

- Modified: `all_seasons_data_final.csv`
- Modified: `data/2026-27/fixtures.csv`
- Modified: `data/2026-27/gws/merged_gw.csv`
- Modified: `data/2026-27/players_raw.csv`
- Untracked: existing continuation/prompt notes, `debug.log`, and generated directories under `webapp/frontend/`

Always re-run `git status --short` because the user may add more work between sessions.

## Verified root causes and seams

- ID-based public manager lookup is documented; a global username-search contract is not present in the repository and must not be invented.
- App state already persists squads by `element` ID and can be extended for imported manager metadata.
- `compute_transfers` already calculates the post-transfer lineup internally but does not serialize bench/armbands/formation.
- `predict_gameweek.py --horizon N` and `load_horizon` already exist.
- The current `predictions_next_gw.csv` has only GW5, and `/api/chips` does not pass a future matrix, so future chip advice is a fixture-adjusted reuse of the GW5 baseline.

## Completed

- [x] Repository discovery and architecture trace
- [x] Root-cause analysis for misleading future Triple Captain output
- [x] Implementation plan written
- [x] Luna starting prompt written
- [x] Plan artifacts committed and pushed as `66648e25` (`Add manager planner and chip advisor plan`)

## 2026-09-22 — Planning handoff

- Starting SHA: `106f6ad9`
- Files changed: this ledger, `FPL_MANAGER_PLANNER_CHIPS_PLAN.md`, and `FPL_MANAGER_PLANNER_CHIPS_PROMPT.md`
- Behavior completed: repository-grounded implementation plan, explicit API/data contracts, phased acceptance criteria, commit/push protocol, and Luna launch prompt
- Verification: `git diff --check` passed before commit; staged diff contained only the three planning artifacts
- Commit: `66648e25 Add manager planner and chip advisor plan`
- Push: `origin/main` advanced from `106f6ad9` to `66648e25`
- Known blocker: the repository has no text manager-search provider contract; Phase 1 must locate the user's API contract or return `search_not_configured` without guessing
- Next exact action: begin Phase 1 at the step recorded below

## Implementation phases

- [x] Phase 1: public-manager adapter and API
- [x] Phase 2: manager search, preview, and local import
- [x] Phase 3: combined transfer/lineup plan on My Team
- [x] Phase 4: real horizon matrix in Chip Advisor
- [x] Phase 5: auditable chip decision evidence
- [ ] Phase 6: full automated and browser verification

## Next exact action

Continue Phase 6: run the full requested backend/frontend gates, start Flask and the Next production build, exercise the requested public manager/team/planner/chip flows in a real browser at 375/768/1280 px, and record any provider-limited scenario accurately.

## 2026-09-22 — Phase 1: public-manager adapter and API

Starting SHA: `80be3f97`
Files changed: `webapp/fpl_client.py`, `webapp/manager_routes.py`, `webapp/app.py`, `tests/test_fpl_client.py`, `tests/test_webapp.py`, this ledger
Behavior completed: Numeric public entry lookup, typed read-only lineup fetch, backward fallback to the latest public picks event, FPL tenths-to-millions price normalization, bounded successful-response TTL cache, stable route error codes, local element safety reporting, and explicit `search_not_configured` for undocumented text search.
Automated evidence: `python -m pytest tests/test_fpl_client.py tests/test_webapp.py -q` — 15 passed; `git diff --check` passed. Repository-owned CSV changes and generated/untracked handoff files remain unstaged.
Manual browser evidence: Not run in this backend-only phase.
Commit SHA and message: `d2260e72 Add public FPL manager lookup and lineup API`
Push result: `origin/main` advanced from `80be3f97` to `d2260e72` successfully.
Known issues/blockers: The repository contains no text manager-search provider contract or configured provider schema. Text search is intentionally not guessed and returns `503 search_not_configured`.
Next exact action: Begin Phase 2 with manager search, preview, and deliberate local import.

The original Phase 1 start instructions above are historical; Phase 1 is complete and its pushed implementation SHA is `d2260e72`.

## 2026-09-22 — Phase 2: manager search, preview, and local import

Branch: `main`
Starting SHA: `29e2e6fd`
Files changed: `webapp/frontend/lib/types.ts`, `webapp/frontend/lib/api.ts`, `webapp/frontend/components/providers/app-provider.tsx`, `webapp/frontend/components/team/manager-search.tsx`, `webapp/frontend/components/team/manager-lineup-preview.tsx`, `webapp/frontend/app/team/page.tsx`, `webapp/frontend/app/broadcast.css`
Behavior completed: Typed manager API client; debounced text and immediate numeric submit; stale-response protection; manager result selection and exact public lineup preview; unresolved local player warning and disabled import; atomic element-ID import preserving observed XI, bench order, armbands, bank, source entry/team/manager/GW, and season; local edits and optimizer updates clear imported metadata.
Automated evidence: `python -m pytest tests/test_fpl_client.py tests/test_webapp.py -q` — 16 passed; `npm run lint` — passed with three existing `<img>` warnings; `npm run build` — passed; `git diff --check --cached` — passed before commit.
Manual browser evidence: Deferred to Phase 6 real-browser verification at 375, 768, and 1280 px.
Commit SHA and message: `35710f37 Add manager lineup search and local import`
Push result: `origin/main` advanced from `29e2e6fd` to `35710f37` successfully.
Known issues/blockers: No documented/configured text manager-search provider contract exists; typed `503 search_not_configured` behavior from Phase 1 remains deliberate. Numeric ID lookup works. Phase 3 implementation was already partially present in the worktree and remains unstaged.
Next exact action: Continue Phase 3 as described above.

## 2026-09-22 — Phase 3: combined transfer and lineup planner

Branch: `main`
Starting SHA: `8f474c25`
Files changed: `scripts/optimise.py`, `webapp/app.py`, `tests/test_optimise.py`, `tests/test_webapp.py`, `webapp/frontend/lib/types.ts`, `webapp/frontend/lib/api.ts`, `webapp/frontend/components/providers/app-provider.tsx`, `webapp/frontend/components/team/team-plan.tsx`, `webapp/frontend/app/team/page.tsx`, `webapp/frontend/app/transfers/page.tsx`, `webapp/frontend/app/broadcast.css`
Behavior completed: Shared lineup serializer used by `/api/lineup` and transfer plans; strict element-ID transfer requests; transfer rows include solver XI, bench, armbands, formation and budget; My Team plans only 0..selected free transfers, exposes editable bank, and applies the selected squad/lineup in one persisted optimizer action; Transfer Studio uses element IDs and still allows deliberate hit comparisons.
Automated evidence: `python -m pytest tests/test_optimise.py tests/test_webapp.py -q` — 30 passed; `npm run lint` — passed with three existing `<img>` warnings; `npm run build` — passed; `git diff --check` — passed.
Manual browser evidence: Deferred to Phase 6 real-browser verification.
Commit SHA and message: `88db5d2d Add combined transfer and lineup planner`
Push result: `origin/main` advanced from `8f474c25` to `88db5d2d` successfully.
Known issues/blockers: Existing PuLP deprecation warnings are emitted during optimizer tests. Text manager search remains unavailable until its provider contract is supplied.
Next exact action: Continue Phase 4 as described above.

## Session entry format

Append one section per completed phase:

```text
## YYYY-MM-DD HH:MM — Phase N: title
Starting SHA:
Files changed:
Behavior completed:
Automated evidence:
Manual browser evidence:
Commit SHA and message:
Push result:
Known issues/blockers:
Next exact action:
```

## 2026-09-22 — Phase 4: real horizon matrix in Chip Advisor

Branch: `main`
Starting SHA: `6226ffe6`
Files changed: `README.md`, `scripts/optimise.py`, `webapp/app.py`, `tests/test_optimise.py`, `tests/test_webapp.py`, `tests/test_chip_advisor.py`
Behavior completed: Prediction reload retains the earliest current gameweek for the current roster while preserving the horizon matrix; current double-fixture rows sum; the web route aligns matrix rows by stable element ID and passes all columns to Chip Advisor. Complete requested coverage uses model projections; missing coverage uses fixture-signal context with null gain and no captain evidence. Wildcard optimization no longer receives NaN fixture-signal values.
Automated evidence: `python -m pytest tests/test_optimise.py tests/test_webapp.py tests/test_chip_advisor.py -q` — 45 passed; `git diff --check` passed.
Manual browser evidence: Deferred to Phase 6 real-browser verification at 375, 768, and 1280 px.
Commit SHA and message: `dc3aa48464d96677b4f0b84bc46c2fbb23e05625 Use horizon projections in chip advisor`
Push result: `origin/main` advanced from `6226ffe6` to `dc3aa484` successfully.
Known issues/blockers: PuLP emits existing deprecation warnings. A single-gameweek prediction export cannot produce future player point gains and intentionally yields fixture-signal context. Text manager search still needs a real provider contract.
Next exact action: Begin Phase 5: replace anonymous chip score bags and opaque thresholds with typed, auditable chip-specific evidence and a named decision policy.

## 2026-09-22 — Phase 5: auditable chip decision evidence

Branch: `main`
Starting SHA: `b81160ad`
Files changed: `README.md`, `scripts/optimise.py`, new `scripts/chip_policy.py`, `tests/test_chip_advisor.py`, `tests/test_optimise.py`, `tests/test_webapp.py`, `webapp/app.py`, `webapp/frontend/app/broadcast.css`, `webapp/frontend/app/chips/page.tsx`, `webapp/frontend/components/chips/chip-opportunity-matrix.tsx`, `webapp/frontend/lib/types.ts`
Behavior completed: Replaced the generic score bag with chip-specific discriminated evidence and the named policy derived from `DECISION_MARGIN`; ranked up to three candidate gameweeks per chip with raw evidence; future candidates remain watch; fixture indices are carried separately from projected points; Free Hit compares optimized and current XI-plus-captain totals with no avoided-hit bonus; API and CLI both load stable-ID horizon projections; cards explain formulas, player totals, runner-up gap, source, coverage, inventory, and uncertainty.
Automated evidence: `python -m pytest tests/test_chip_advisor.py tests/test_optimise.py tests/test_webapp.py -q` — 49 passed; `python -m py_compile scripts/optimise.py scripts/chip_policy.py` passed; `npm run lint` passed with three existing image warnings; `npm run build` passed; `git diff --check` passed.
Manual browser evidence: Deferred to Phase 6 real-browser verification at 375, 768, and 1280 px.
Commit SHA and message: `aa05ea0f8fd8ab7df5151c4a07c5c522baedc02b Make chip recommendations explainable and conservative`
Push result: `origin/main` advanced from `b81160ad` to `aa05ea0f` successfully.
Known issues/blockers: The text manager-search provider contract is still absent, so text searches return typed `search_not_configured`; numeric manager lookup is implemented. Existing PuLP deprecation and three frontend image lint warnings remain.
Next exact action: Begin Phase 6: run the full requested backend/frontend gates, start Flask and the Next production build, exercise the requested public manager/team/planner/chip flows in a real browser at 375/768/1280 px, and record any provider-limited scenario accurately.
