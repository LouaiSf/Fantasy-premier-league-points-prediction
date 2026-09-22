# FPL Manager Import, Lineup Planner, and Chip Advisor Plan

Status: implementation-ready
Prepared against: `main` at `106f6ad9`
Progress ledger: `FPL_MANAGER_PLANNER_CHIPS_PROGRESS.md`
Execution prompt: `FPL_MANAGER_PLANNER_CHIPS_PROMPT.md`

## 1. Goal

Deliver three connected user outcomes without creating a second source of football logic:

1. Search for an FPL manager by entry ID or manager/team name, inspect that manager's latest public lineup, and explicitly save it as the local user's team.
2. On My Team, choose the number of available free transfers and receive one combined plan containing transfers, the resulting XI, ordered bench, captain, and vice-captain. The user can apply the proposed squad locally.
3. Make Chip Advisor trustworthy and explainable. It must use the existing multi-gameweek prediction pipeline when that data exists, must never present a one-gameweek fixture heuristic as a player-level model projection, and must explain every chip score using visible inputs.

The current broadcast design system in `DESIGN.md` remains the visual contract. The existing Flask API, Next.js app, PuLP optimizer, and local-storage team model remain the architecture.

## 2. Verified repository facts

- `webapp/app.py` is the Flask boundary. `/api/lineup` already optimizes XI, bench order, captain, and vice-captain for an owned 15. `/api/transfers` already calls `scripts/optimise.py::compute_transfers`.
- `scripts/optimise.py::compute_transfers` jointly optimizes every transfer count and correctly charges hits, but each returned row currently omits bench order, captain, vice-captain, and formation even though `solve_squad` already calculated them.
- `components/providers/app-provider.tsx` stores a squad by FPL `element` IDs and persists XI, bench, captain, and vice-captain IDs. This is the correct seam for “Set as my team.”
- `scripts/predict_gameweek.py --horizon N` and `scripts/optimise.py::load_horizon` already produce and load a real player-by-gameweek projection matrix.
- The current `predictions_next_gw.csv` contains only GW5. `webapp/app.py::api_chips` does not pass `future_points` to `compute_chips`, so future chip weeks reuse one next-gameweek player score and scale it with fixture count/FDR.
- The current chip thresholds (`2/4/5/8`) are opaque product policy, not measured model metrics. Future candidate weeks can also receive a `play` status even though the user cannot play a chip until that week.
- The repository documents official public entry lookup by numeric ID (`/api/entry/{id}/` and `/api/entry/{id}/event/{gw}/picks/`) but contains no global username-search endpoint or response contract. Do not invent one.
- The worktree already contains user-owned CSV changes and untracked handoff/generated files. Every implementation commit must stage explicit paths only.

## 3. Non-negotiable product decisions

### 3.1 Manager lookup

- Numeric queries use the public FPL entry endpoint directly.
- Text queries use a server-side manager-search provider configured by `FPL_MANAGER_SEARCH_URL`. The browser never calls that provider directly and never receives its key, if it has one.
- Before implementing text search, locate the real provider contract in project configuration or user-supplied API documentation. If it is absent, implement numeric lookup fully and make text search return a typed `503 search_not_configured` response. Record the missing contract in the progress ledger. Never guess an endpoint, fields, or authentication scheme.
- Manager names and team names are not unique. Text search returns a candidate list containing entry ID, manager name, team name, overall rank, and total points. Only a user selection opens a lineup.
- Public picks can lag the current deadline. Resolve the requested event as follows: use the explicit `gameweek` query when supplied; otherwise start at the entry's/current public event and walk backward until a picks response exists. Return the actual event used and label it “Latest public lineup for GWX.” Do not call it the live pre-deadline team.
- The feature remains read-only. It never asks for FPL credentials and never submits transfers to FPL.

### 3.2 Local team ownership

- Viewing another manager never mutates My Team.
- “Set as my team” is an explicit button and saves the 15 element IDs, observed XI order, bench order, captain, vice-captain, bank, source entry ID, source manager/team name, source gameweek, and season.
- Editing the squad manually or applying an optimizer proposal changes the source to `manual` or `optimizer` and clears stale observed-manager metadata.
- A saved imported team must be rejected on reload when its season no longer matches `/api/platform`, using the current new-season behavior.

### 3.3 Combined lineup plan

- My Team is the combined surface. Do not create a ninth top-level navigation page.
- “Free transfers” means transfers available without a hit. The compact planner evaluates `0..free_transfers` and may recommend holding. Existing Transfer Studio remains the advanced surface for deliberately allowing hit-costing moves.
- The result is one atomic `TeamPlan`: current lineup, transfer recommendation, resulting 15, XI, ordered bench, captain, vice-captain, formation, bank after, projected gross/net gain, and an uncertainty note.
- “Apply suggestion” persists the resulting team locally only. It does not make an FPL transfer.
- Element IDs are the request identity. Names remain display data only.

### 3.4 Chip advice semantics

- `model_projection` is legal only when every requested gameweek has a complete player projection column for the current roster. Partial matrices must not be silently filled with the fixture heuristic.
- `fixture_signal` is a non-point opportunity index. In this mode, return `expected_gain: null`, omit player-specific captain evidence, and use `watch`/`hold`, never `play`.
- A future best week is always `watch`, not `play`. `play` is reserved for the current gameweek when the model matrix, complete squad, chip inventory, and decision policy all support it.
- Use “projected gain,” not “expected certainty.” Every response includes projection source, generated timestamp, coverage gameweeks, and an uncertainty/quality label.
- Do not silently inflate Free Hit value with speculative avoided hits. Base gain is `optimized XI + captain - current XI - captain`. If avoided hits are shown, return them as a separate contextual field only when calculated from an explicit transfer plan.
- Keep the raw chip formulas auditable:
  - Triple Captain incremental gain: one additional copy of the chosen captain's projected points.
  - Bench Boost incremental gain: projected points of the four ordered bench players.
  - Free Hit gain: best legal one-week squad total minus current legal lineup total.
  - Wildcard gain: optimized persistent squad total over the remaining horizon minus current squad total over the same weeks.
- Replace the anonymous threshold dictionary with a named `ChipDecisionPolicy`. Values must be documented as product policy and derived from existing `HIT_COST`/`DECISION_MARGIN` or from a checked-in calibration artifact; do not describe them as learned metrics unless a calibration script and result file prove that.

## 4. Target contracts

### 4.1 Manager search

`GET /api/managers/search?q=<query>`

Success:

```json
{
  "ok": true,
  "query": "123456",
  "results": [
    {
      "entry_id": 123456,
      "manager_name": "First Last",
      "team_name": "Example XI",
      "overall_rank": 12034,
      "total_points": 241
    }
  ]
}
```

Rules:

- Trim input; reject empty queries and text longer than 80 characters with `400 invalid_query`.
- Numeric query returns zero or one normalized candidate from the entry endpoint.
- Text query returns all normalized provider candidates in deterministic rank/name/ID order.
- Use `404 manager_not_found` for a missing numeric entry, `503 search_not_configured` for unavailable text search, and `502 upstream_unavailable` for timeout/invalid upstream responses.

### 4.2 Manager lineup

`GET /api/managers/<entry_id>/lineup?gameweek=<optional>`

Return:

```text
ok, fetched_at, source, manager, requested_gameweek, lineup_gameweek,
bank, team_value, event_points, event_rank, overall_rank, total_points,
active_chip, picks[]
```

Each pick contains:

```text
element, position, multiplier, is_captain, is_vice_captain,
purchase_price, selling_price
```

Prices are normalized from FPL tenths to millions at the HTTP boundary. The picks remain in FPL `position` order so positions 1–11 and 12–15 reconstruct the observed pitch and bench. Return `missing_elements` when the live lineup contains an element absent from the local snapshot; disable “Set as my team” until all 15 resolve.

### 4.3 Team plan

Prefer extending the existing transfer boundary rather than duplicating optimization:

`POST /api/transfers`

New primary request:

```json
{
  "elements": [1, 2, 3],
  "free": 2,
  "bank": 0.7,
  "max": 2
}
```

Keep the current `squad` name array temporarily for the existing UI call site, but migrate both Team and Transfer Studio to `elements` in the same phase and then remove name matching from this endpoint if no caller remains.

Extend each `TransferRow` with:

```text
bench[], captain, vice_captain, formation, spend, bank_after, xi_points,
captained_total
```

Extend the top level with `current_lineup`, serialized with the same lineup shape. This guarantees that a `0`-transfer plan still returns bench and armband advice.

### 4.4 Chip result

Replace the untyped `score_breakdown` bag in TypeScript with a discriminated evidence union keyed by chip. Common recommendation fields:

```text
chip, status, candidate_gw, candidate_gameweeks, projected_gain,
projection_mode, confidence, reasons[], warnings[], decision_policy,
alternatives[]
```

Evidence by chip:

- Triple Captain: player element/name/team/position, projected points, fixtures, availability, normal captain total, triple captain total, incremental gain, runner-up week, gap to runner-up.
- Bench Boost: ordered bench players and points, availability for each, bench total, runner-up week, gap.
- Free Hit: current XI/captain total, optimized XI/captain total, raw delta, changed-player count; avoided hits only when backed by an explicit plan.
- Wildcard: current and optimized cumulative totals, weekly deltas, horizon length, changed-player count.

Top-level metadata:

```text
projection_mode, projection_generated_at, projection_gameweeks,
requested_horizon, evaluated_horizon, data_quality, methodology_version
```

## 5. Implementation phases

### Phase 0: Protect the worktree and initialize continuity

Files: `FPL_MANAGER_PLANNER_CHIPS_PROGRESS.md`, Git only.

1. Read this plan, the prompt, progress ledger, `DESIGN.md`, `webapp/frontend/AGENTS.md`, and current `git status`.
2. Record the starting SHA, branch, upstream, dirty files, and exact next action in the progress ledger.
3. Never stage the pre-existing CSV changes, `debug.log`, existing continuation files, or generated frontend agent directories.
4. After every meaningful vertical slice: update the ledger, run the slice's checks, stage explicit paths, inspect the staged diff, commit without trailers/co-authors, and push to the configured upstream.

Checkpoint commit: not required if only the already-committed plan exists.

### Phase 1: Add a typed public-manager adapter and API

Files:

- New `webapp/fpl_client.py`
- New `webapp/manager_routes.py`
- `webapp/app.py` only to register the blueprint and provide the current local element set if required
- `webapp/requirements.txt` only if the chosen client dependency is not already deployed
- `tests/test_fpl_client.py`
- `tests/test_webapp.py`

Implementation:

1. Implement one HTTP boundary with an explicit connect/read timeout, FPL user agent, response-size guard, JSON shape parsing, and typed exceptions. Follow the project's existing standard-library `urllib` pattern unless a deployed dependency is deliberately added.
2. Normalize upstream data into typed manager summary, pick, and lineup structures before route code sees it.
3. Add a bounded in-process TTL cache for entry and picks responses. Cache only successful public responses; key by normalized URL; expire quickly enough to cross a deadline safely. Do not cache errors.
4. Implement numeric search, configured text search, duplicate candidate results, backward event fallback, and normalized error responses.
5. Register a Flask blueprint under `/api/managers` so `webapp/app.py` does not accumulate the HTTP client logic.
6. Tests use wire-shaped fixtures and monkeypatched HTTP at the boundary. Cover success, duplicate names, invalid JSON, timeout, 404, text provider absent, current-event picks unavailable with previous-event fallback, and price normalization.

Acceptance:

- Numeric entry lookup and lineup fetch work without authentication.
- Text lookup never guesses a provider.
- Every error has a stable code and useful message.
- No manager lookup mutates local state.

Commit and push: `Add public FPL manager lookup and lineup API`

### Phase 2: Add manager search, preview, and “Set as my team”

Files:

- `webapp/frontend/lib/types.ts`
- `webapp/frontend/lib/api.ts`
- `webapp/frontend/components/providers/app-provider.tsx`
- New focused components under `webapp/frontend/components/team/` such as `manager-search.tsx` and `manager-lineup-preview.tsx`
- `webapp/frontend/app/team/page.tsx`
- `webapp/frontend/app/broadcast.css`
- `DESIGN.md` only if a new reusable component/state is introduced

Implementation:

1. Add exact client types matching the normalized manager API. Do not expose upstream provider JSON shapes to UI code.
2. Add `api.searchManagers` and `api.managerLineup` with URL-encoded query values.
3. Extend stored squad data with source metadata, bank, source gameweek, observed XI/bench order, and source manager. Add one atomic context action `setImportedTeam(lineup)`; do not compose several setters that can persist an intermediate broken state.
4. Search behavior: 300 ms debounce for text, immediate submit for numeric IDs, request cancellation or stale-response guard, keyboard-selectable result list, explicit empty/error/offline states.
5. Preview the selected manager's exact public XI, bench order, captain, vice-captain, chip, bank, rank, and source GW. Map elements through the existing platform snapshot. Display unresolved elements and disable import.
6. “Set as my team” writes the imported state, switches the main pitch to it, shows a toast, and survives reload. Viewing and closing a preview does nothing.
7. Follow existing broadcast primitives: a compact search rail above the pitch, result rows rather than generic cards, native inputs/buttons, visible focus, and no new raw colors/spacing.

Acceptance:

- Multiple same-name results are distinguishable by team name and entry ID.
- A preview preserves the other manager's bench order and armbands.
- Import is deliberate, season-safe, persistent, and reversible through the existing editor.
- Failure of the external manager API leaves the saved local team usable.

Commit and push: `Add manager lineup search and local import`

### Phase 3: Return and render one combined team plan

Files:

- `scripts/optimise.py` (small serialization change around `compute_transfers`; do not refactor unrelated optimizer code)
- `webapp/app.py`
- `tests/test_optimise.py`
- `tests/test_webapp.py`
- `webapp/frontend/lib/types.ts`
- `webapp/frontend/lib/api.ts`
- New `webapp/frontend/components/team/team-plan.tsx`
- `webapp/frontend/app/team/page.tsx`
- `webapp/frontend/app/transfers/page.tsx`
- `webapp/frontend/app/broadcast.css`

Implementation:

1. Add a shared element-ID squad resolver at the Flask boundary and migrate transfer requests away from names.
2. Extend `compute_transfers` rows with the lineup data already present in each `solve_squad` result. Do not run an independent captain or bench heuristic.
3. Return `current_lineup` even when zero transfers is the recommendation. Serialize through one lineup serializer so `/api/lineup` and `/api/transfers` cannot disagree.
4. Add a My Team “Next move” control with free transfers `0..5` and bank. Imported bank initializes the field; manual teams default to `0.0` and remain editable.
5. For this compact surface set `max = free`. Render hold or the outgoing/incoming pairs, projected net gain, uncertainty note, resulting formation, XI, bench order, captain, and vice-captain on the same page.
6. Add “Apply suggestion” only when a legal recommendation exists. It persists the recommended element IDs and lineup in one context action and clears imported-source metadata.
7. Keep Transfer Studio intact for manual comparisons and hit-costing scenarios, but migrate its API call to element IDs and reuse the extended response types.

Acceptance:

- Selecting 0 FTs still returns optimized bench/captain advice with no transfer.
- Selecting 1 or 2 FTs never charges a hit on My Team and can recommend fewer moves or holding.
- Joint two-transfer combinations remain possible; do not turn the solver into a greedy swap sequence.
- Applying a plan updates My Team, Transfers, Captain, and Chips because all consume the same provider state.

Commit and push: `Add combined transfer and lineup planner`

### Phase 4: Feed the real horizon matrix into Chip Advisor

Files:

- `scripts/optimise.py`
- Optional new `scripts/chip_policy.py` for policy/evidence structures; prefer this over growing the already-large optimizer module
- `webapp/app.py`
- `tests/test_chip_advisor.py`
- `tests/test_webapp.py`
- `README.md`

Implementation:

1. Make a horizon export safe for all existing callers:
   - Update `load_predictions` so a file containing multiple `GW` values returns only the earliest/current gameweek player table, never the highest row from any future week.
   - Continue using `load_horizon` for the complete player-by-GW matrix.
2. In `reload_predictions`, load both views from the same artifact when it contains multiple GWs. Store `future_points`, `future_gameweeks`, and horizon metadata in `_state`. A single-GW file remains valid but is explicitly fixture-signal-only for future weeks.
3. Pass the matrix into `compute_chips`. Reindex by stable element identity and assert coverage before setting `model_projection`.
4. If the requested horizon exceeds matrix coverage, return the evaluated range and a warning, or reject it with a stable validation error. Never synthesize the missing tail while retaining a model label.
5. Update the documented generation command to produce sufficient coverage, for example:

   `python scripts/predict_gameweek.py --season 2026-27 --horizon 12 --out predictions_next_gw.csv`

6. Preserve deployment behavior: the committed artifact can contain the horizon while `/api/platform` still exposes only the current GW row per player.

Acceptance:

- The current GW player list remains one row per element.
- Chip candidate values equal the correct per-GW matrix cells, including summed DGWs and zero BGWs.
- A single-GW export cannot generate player-specific future “expected gain.”

Commit and push: `Use multi-gameweek projections for chip advice`

### Phase 5: Replace opaque chip scoring with auditable evidence

Files:

- `scripts/optimise.py` and/or `scripts/chip_policy.py`
- `tests/test_chip_advisor.py`
- `webapp/frontend/lib/types.ts`
- `webapp/frontend/app/chips/page.tsx`
- `webapp/frontend/components/chips/chip-opportunity-matrix.tsx`
- `webapp/frontend/app/broadcast.css`

Implementation:

1. Separate calculation from decision policy. Calculation produces raw per-GW gains and evidence; policy converts them to `play/watch/hold/unavailable` using data quality, inventory, current-vs-future week, and a documented margin.
2. Return the top three eligible weeks per chip with their raw evidence, not only the winner.
3. Enforce status semantics: future candidate = `watch`; incomplete squad or fixture-only data = `watch/hold`; current complete model-backed candidate may be `play` if it clears policy.
4. Remove fixture-only numbers from point-labelled fields. Opportunity indices and projected points use different fields and units.
5. Render a concise “Why this choice” block per chip:
   - formula in plain language;
   - exact contributing players/totals;
   - runner-up week and gap;
   - projection source and coverage;
   - inventory/eligibility constraint;
   - uncertainty note.
6. Update “How this was calculated” from static caveat copy to values returned by the API. Do not duplicate formula logic in React.
7. Keep the page hierarchy and broadcast styling. Evidence is progressive disclosure; the primary card still answers chip, week, status, and gain at a glance.

Regression scenarios:

- With only the current single-GW export, Bruno Fernandes in GW7 is never presented as a model-backed Triple Captain pick and has no point-labelled future gain.
- With a synthetic horizon matrix, the GW7 captain is whichever owned player has the highest GW7 cell, proving the code no longer reuses the GW5 baseline.
- A strong GW7 candidate while the current week is GW5 is `watch`, not `play`.
- Triple Captain gain equals one extra captain projection; Bench Boost equals exactly four bench projections; Free Hit has no speculative hit bonus.

Commit and push: `Make chip recommendations explainable and conservative`

### Phase 6: End-to-end verification and documentation

Files:

- Tests and docs only as required by failures
- `FPL_MANAGER_PLANNER_CHIPS_PROGRESS.md`

Automated gates:

1. `python -m pytest tests/test_fpl_client.py tests/test_webapp.py tests/test_optimise.py tests/test_chip_advisor.py`
2. `npm run lint` in `webapp/frontend`
3. `npm run build` in `webapp/frontend`
4. `git diff --check`

Manual browser scenarios against running Flask and Next production builds:

1. Search a valid numeric ID; inspect manager identity, ranks, bank, source GW, XI, bench, captain, and vice-captain.
2. Search a duplicated text name using the configured provider; select the intended candidate.
3. Exercise invalid ID, no result, provider timeout, search-not-configured, and missing local element states.
4. Preview without importing; verify My Team is unchanged. Import; reload; verify the exact team and metadata persist.
5. Run the planner with 0, 1, and 2 free transfers; verify hold, single move, and joint-move presentations; apply a proposal and confirm every dependent page sees it.
6. Inspect Chip Advisor with single-GW data and horizon data. Verify source labels, units, evidence totals, candidate status, inventory rules, and no Bruno-style baseline leakage.
7. Test keyboard flow, visible focus, loading, empty, error, and success states at 375, 768, and 1280 px. The page must not scroll horizontally.
8. Run the repository visual-QA workflow on `/team`, `/transfers`, and `/chips`; run real-browser Lighthouse on the production build if that workflow is available. Do not weaken the UX to improve scores.

Final acceptance:

- No duplicate optimizer logic exists in Flask or React.
- No user-visible point value comes from a fixture-only index.
- No external API failure erases the saved team.
- No unresolved type errors, lint errors, test failures, or visual blockers remain.
- The progress ledger names every commit, command result, manual scenario, residual risk, and next action.

Commit and push: `Complete manager planner and chip advisor verification`

## 6. Commit and continuation protocol

After each phase:

1. Update `FPL_MANAGER_PLANNER_CHIPS_PROGRESS.md` with date/time, branch, HEAD before commit, completed acceptance items, files changed, tests/QA evidence, known issues, and the next exact action.
2. Run `git status --short` and ensure unrelated user files remain unstaged.
3. Stage only the phase's explicit paths with `git add -- <paths>`.
4. Inspect `git diff --staged --stat` and `git diff --staged`.
5. Commit in the repository's imperative sentence style. Do not use `--author`, `Co-authored-by`, or any attribution trailer.
6. Push immediately to the configured upstream. Record the resulting commit SHA and push result in the ledger. If push fails, keep the commit, record the exact failure, and make resolving the push the next action before more feature work.
7. A new session starts by reading this plan and the progress ledger, checking whether local HEAD and upstream contain the recorded SHA, and continuing from “Next exact action.” It must not repeat completed phases.

## 7. Scope exclusions

- No FPL authentication, credentials, or writing changes to the official game.
- No global username search fabricated from undocumented official endpoints.
- No mini-league feature, account system, or server-side user database.
- No model retraining. Generating the existing horizon prediction artifact is allowed and required.
- No broad optimizer, Flask, or CSS cleanup unrelated to these outcomes.
- No committing pre-existing data refreshes or generated agent configuration unless separately requested.
