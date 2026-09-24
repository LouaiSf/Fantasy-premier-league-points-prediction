# FPL Platform v2: implementation plan

**Planning baseline:** 24 September 2026, local 2026/27 snapshot at GW6. This document is the implementation specification for the next coding agent. It is not a claim that the changes below have been implemented. Preserve the existing angular broadcast look in `DESIGN.md`; improve layout and language within that system. Work on the current application, not a parallel mockup. The production stylesheet is `webapp/frontend/app/broadcast.css`.

## Outcome and delivery order

The user should be able to find and import their public FPL team quickly, stage and compare up to five transfers, and understand chip advice that has a defensible meaning. Ship in this order:

1. **P0 correctness and honesty:** remove double-discounted chip projections and ungrounded `PLAY` claims; fix chip rules and invalid squad handling; make manager lookup discoverable and direct entry/profile URL import easy.
2. **P1 core workflow:** multi-transfer draft and constrained analysis with explicit finance/hit math; bounded league name search with progress; mobile layouts.
3. **P2 trust and polish:** meaningful hold/save behavior, clearer labels and risk language, stale data handling, one integrated deadline board.
4. **P3 differentiated features:** saved scenarios, change explanations, calibrated confidence and alerts, only after their source data and semantics are reliable.

Each slice below has a concrete completion condition. A slice is complete when its related automated checks pass and its listed browser scenario works once at desktop and once at 375px. Do not repeatedly replay the same QA scenario without a new defect or changed behavior.

## Evidence and constraints from the current code

| Surface | Observed issue | Cause / location | Status |
| --- | --- | --- | --- |
| My Team lookup | A name search requires a league, then paging; lookup is below the first phone screen. | `components/team/manager-search.tsx` filters only loaded pages; `app/team/page.tsx` places it after a tall hero. `FplClient.search_text()` in `webapp/fpl_client.py` always raises `SearchNotConfigured`. | Confirmed by code and live 375px view. |
| Transfer Studio | Choosing max 3 produces 0/1/2/3 optimizer rows, but A/B holds only one pair; that pair does not influence analysis. | Scalar `outId`/`inId` and `runAnalysis()` in `app/transfers/page.tsx`; `/api/transfers` receives no selected pair. | Confirmed by code and live GW6 flow. |
| Transfer action | “Hold this week” says it recorded a hold, but has no durable effect. | Button handler in `app/transfers/page.tsx` only calls a toast. | Confirmed by code. |
| Chip scores | Expected points are multiplied by appearance probability twice. | Exported future points in `scripts/predict_gameweek.py` already contain `p_plays`; `_projection_matrix()` in `scripts/optimise.py` multiplies by `_availability_factor()` again. | Confirmed by code. |
| Chip decisions | Both Triple Captain and Bench Boost can be `PLAY` for one GW; lead card selects the first chip in static order. GW7 Wildcard showed +45.2. | Independent 1-point policy in `scripts/chip_policy.py`, noncomparable chip baselines in `compute_chips()`, and `CHIP_IDS.find()` in `app/chips/page.tsx`. | Confirmed by code and live GW6 flow. |
| Chip error risk | A current injured/suspended player may be absent from `s['players']` and fail squad alignment; `/api/chips` does not catch that `ValueError`. | `squad_from_elements()` selects `s['everyone']`; `_align_squad_to_players()` aligns to available market only. | Likely; reproduce with a fixture before marking fixed. |
| Chip calendar | A horizon that crosses GW19/20 only considers the first half's chip set; Wildcard is not excluded in GW1; planned chips can collide in one GW. | `_candidate_window()` in `scripts/optimise.py`; `addPlannedChip()` in `app/chips/page.tsx`. | Confirmed by code. |
| Risk language | Healthy status is presented as “Nailed on”; “Promoted / New” derives from missing model history; News badge counts all player news. | `app/captain/page.tsx`, `app/watchlist/page.tsx`, `components/player-drawer.tsx`, `components/chrome/main-nav.tsx`. | Confirmed by code; wording is unsupported by its input. |

The existing backend solver already returns a full legal 15, XI, captain, hit and bank for each 0..N transfer count. Preserve it. Its `out` and `in` arrays are **sets of different players, not paired transactions**. `components/team/team-plan.tsx` already computes complete element-set differences and is a useful pattern. Keep stable FPL `element` IDs end to end; names are display text only.

## Slice 1 — fast, truthful manager lookup

### 1A. Direct entry or profile URL (first landing interaction)

**Issue and cause.** The current default says “FPL entry ID”; typing a name calls `/api/managers/search?q=...`, which reports name search unconfigured. The usable league path is a second tab below a very tall My Team hero. For a user trying to find their own account, this feels like an endless page search.

**Exact behavior.** Replace the two-tab entry point with a compact “Find your FPL team” card at the top of `app/team/page.tsx`, before squad statistics and the large hero. One input accepts (a) a positive numeric entry ID, or (b) an official `https://fantasy.premierleague.com/entry/<id>` URL with optional trailing path/query. Submit performs existing `api.searchManagers(String(id))`, shows manager name, team name, ID and rank, then fetches existing lineup preview. Import remains an explicit button, never automatic. A text name opens the league-name section described in 1B rather than calling the dead global text route. Helper copy: “Paste the link to your FPL team, or enter its entry ID. For a name, search a mini-league.” Add one help link to the official FPL site with a short instruction to open your team and copy its URL.

**Parsing and state.** Implement one pure parser in a new `webapp/frontend/lib/manager-entry.ts`: trim; accept `^[1-9][0-9]*$` within a practical safe integer range; for URLs use `new URL`, require `https:` and exact host `fantasy.premierleague.com`, require path segments `entry`, positive ID; reject arbitrary domains, unrelated FPL paths and malformed URLs with a field-level error. Do not store or send whole pasted URLs. In `ManagerSearch`, clear selected candidate/lineup whenever the normalized query changes or the mode changes. Give each async search/lineup request an `AbortController` or monotonically increasing request ID so an older response cannot replace a new selection. Use actual buttons in a labelled result list; do not use `role=listbox`/`role=option` unless keyboard arrow behavior is implemented.

**Recent accounts.** On successful import, save `{season, entry_id, manager_name, team_name, imported_at}` in season-scoped local storage, at most five unique IDs, newest first. Render those as one-tap “Recent teams” buttons in the lookup card. Add a clear control and a note “Saved on this device”; no server account or credential claim. Never persist lineup or purchase prices in this new list. Verify an imported ID still exists when reopened and show a recoverable stale-entry error. The existing squad persistence remains the source of truth for the active team.

**Files.** `webapp/frontend/app/team/page.tsx`, `components/team/manager-search.tsx`, `lib/api.ts`, `lib/types.ts`, new `lib/manager-entry.ts`, relevant broadcast/team CSS. Keep `webapp/manager_routes.py` numeric search as the authoritative lookup. Remove the visible dependency on `FplClient.search_text()`; do not pretend a global name index exists.

**Acceptance.** At 375px the lookup heading and input are visible without scrolling past a full hero. ID and official URL resolve the same manager. A non-FPL URL is rejected locally. A rapid search A→B never shows A's lineup under B. Import updates My Team; reopening uses Recent teams; clear removes them. An unknown ID shows a specific, recoverable error.

### 1B. Search a known league by manager or team name

**Issue and cause.** The existing filter covers only pages already fetched; a no-result message is easily mistaken for “not in league.” Each classic standings page has 50 entries. There is no verified public global manager-name search endpoint in this application. Do not promise “find any manager by name.”

**Endpoint contract.** Add `GET /api/managers/leagues/<league_id>/search?q=<name>&cursor=<page>&limit=5` in `webapp/manager_routes.py`. `cursor` is the **next page to scan**, default 1; `limit` is integer 1..5, default 5. Validate 2..80 trimmed search characters, league ID positive, page positive. For each page call existing `FplClient.get_league_standings`, stop after `limit` pages, upstream `has_next=false`, or an upstream error. Normalize manager/team names with Unicode NFKD, strip combining marks, casefold and collapse whitespace; all query terms must occur in combined manager/team text. Deduplicate by entry ID. Return:

```json
{
  "ok": true,
  "league_id": 123,
  "league_name": "My league",
  "query": "example",
  "results": [{"entry_id": 1, "manager_name": "...", "team_name": "...", "rank": 1, "total_points": 0}],
  "scanned_from_page": 1,
  "scanned_through_page": 5,
  "scanned_entries": 250,
  "next_cursor": 6,
  "has_more": true,
  "scope": "league_pages"
}
```

When the league ends, `next_cursor=null`, `has_more=false`. Use the same upstream error mapping as standings; if a later page fails, return a recoverable partial result plus `interrupted=true` and the failed page as `next_cursor`, rather than losing already found entries. Cache standings pages by `(league_id,page)` for 60 seconds in the client/service, reuse the existing upstream timeout, and cap one browser-triggered scan to five upstream pages. Do not start a whole-league background crawl. If the FPL upstream rate-limits, surface “Search paused by FPL; try again” and keep the cursor. This route should have no personally identifying logging beyond normal request logs.

**UI flow.** Show a numeric league ID input, name/team query, and optional approximate rank. A rank hint computes start page `max(1, ceil(rank/50)-1)` and clearly labels the search as starting near that rank; never imply earlier pages were checked. “Search league” runs one five-page scan with inline progress, shows all matches with manager/team/entry/rank, and lists the exact checked page range. “Search next 250 members” uses `next_cursor`; deduplicate accumulated results. A zero result state says “No match in pages X–Y. Continue searching this league or paste your team link.” Switching league or query resets cursor/results and cancels older requests. Preserve manual page jump only as an advanced control. On selection, use the same lineup preview and import path as 1A.

**Files/tests.** `webapp/manager_routes.py`, `webapp/fpl_client.py` (cache only if that is the existing upstream owner), `components/team/manager-search.tsx`, `lib/api.ts`, `lib/types.ts`; add focused tests near existing manager route/client tests for normalization, cursor, deduplication, partial failure, and no false global “not found.”

**Acceptance.** A manager on page 4 appears after one search from page 1; a manager on page 7 appears after one Continue. Changing league mid-request never mixes results. UI always names its searched range. A 404 league, upstream outage and no match have distinct messages. No browser action fetches unbounded pages.

## Slice 2 — multi-transfer Studio with real A/B semantics

### 2A. State, identity and transaction math

**Issue and cause.** `app/transfers/page.tsx` holds one `outId` and one `inId`; max transfer count only changes optimizer range. The pair is excluded from the API call. The impact cards flatten multiple outgoing/incoming names, so users cannot inspect or save a coherent multi-move draft.

**State model.** Replace scalar selection with `draft: Array<{out_element:number; in_element:number}>`, maximum `maxTransfers` (0..5). Keep a separate temporary `pendingOutElement` while choosing the next incoming player. Clicking a currently owned, unused outgoing player filters incoming choices to the same FPL position; selecting incoming adds one pair. A row shows ordinal, both player names/club/position, sell price, buy price and price difference, with Edit and Remove. Edit returns that row to picker without losing the other rows. If the user tries to lower max below draft length, reject the change and show “Remove moves to lower the transfer limit”; never silently discard moves. `Clear draft` is explicit.

**Validation.** An outgoing ID must be in the original 15, each outgoing and incoming ID unique, incoming ID not in the original 15, equal positions, 0..5 pairs and `draft.length <= max`. A transfer may temporarily exceed a club limit or bank during building, but mark draft incomplete/invalid and disable “Evaluate this draft” until the **final** 15 obey exact 2 GK / 5 DEF / 5 MID / 3 FWD, max three from a club, and `bank_after >= 0` in integer tenths. No double purchases, circular replacement or null IDs. Use `sellingPricesTenthsForSquad()` for each sale and current market `value_m` tenths for each buy; never use displayed decimal arithmetic as the source of truth. `bank_after_tenths = bank_tenths + sum(sell_tenths) - sum(buy_tenths)`. `hit = 4 * max(0, draft.length - free)`. A draft remains clearly marked **unsaved plan**, not completed FPL transfers.

**Lineup score.** For a valid draft, send the final 15 element IDs to existing `/api/lineup` only when the user clicks `Evaluate this draft`, then show `gross = XI predicted sum + captain predicted points`, `net = gross - hit`, and `gain = net - baseline_gross` from an existing current-lineup result. This is the exact manual draft score; do **not** use the rough sum of individual player deltas as a final claim. The local draft card may show a provisional price delta before full validation, labelled provisional. If prediction data are unavailable, still show legal squad and finance, but no predicted gain. Do not call the solver on every picker click.

**Optimizer contract.** Keep existing `/api/transfers` without locks as the “Best available options” view, and add optional `locked_out_elements` and `locked_in_elements` arrays to the same route for a **draft-constrained** view. Both lists must be equally long, unique, 0..5, and correspond to a valid same-position multiset of outgoing/incoming IDs. `locked_out` must belong to the current 15; `locked_in` must be purchasable market elements not already owned. `max >= locked_out.length`; rows with fewer transfers are returned as failures with a clear “needs at least N staged moves” reason. In `compute_transfers()`, map IDs to `players.index`; add locked incoming indices to `solve_squad(locked=...)`, add outgoing indices to `banned=...`, preserve `must_transfer_out` and selling-price `cost_overrides`. Include ID arrays `out_elements` and `in_elements` in every result row and expose `draft_constraints` in the response. A row must have exactly `transfers` outgoing and incoming IDs. Reject invalid locks at the API boundary with 400 `invalid_transfer_draft`, never solver 500. Keep the current exact baseline and hit accounting.

**Important distinction.** The optimizer returns unordered outgoing/incoming sets. Render its result as two separate lists headed `OUT` and `IN`, grouped by position for scanability; do not zip names into synthetic pairs. The user draft does contain intentional pairs and may display paired rows. The constrained optimizer can complete a draft with extra transfers but still returns sets; label “Includes your N staged moves.”

### 2B. Page composition and persistence

**Desktop:** keep the existing broadcast Studio header and colors. Left rail is `Your squad / OUT`; right rail is `Market / IN`. A central `Draft N of max` panel lists all staged pairs and total bank/hits. Place a two-tab result below: `My draft` (exact score and final XI) and `Best available` (0..max cards). Each optimized card shows count, net gain, hit, bank after, full separate Out/In lists, and a View XI button. Selecting a count must update the full A/B difference, not only the first player. Show the 0-transfer baseline beside any selected result so net points have a reference.

**Mobile at 375px:** first viewport contains title, N/max indicator and primary Add move/Evaluate controls. Stack OUT picker then IN picker, then draft rows and results; the current `.studio-grid` ordering in `webapp/frontend/app/broadcast.css` puts an empty channel first, so change its narrow breakpoint ordering. Market list must announce `Showing 200 of X` if the existing `slice(0,200)` remains, with search over the full eligible set and an obvious More control. No selected draft should disappear below a giant channel panel. Ensure hit, bank and player names wrap without horizontal scroll.

**Actions:** Add `Save draft` to season-scoped local storage keyed by active squad fingerprint (sorted 15 IDs plus finance snapshot), with one active draft and last edited timestamp. Reopen it only when the squad fingerprint matches; otherwise show “Saved plan is for another squad” with clear/discard options. `Apply to My Team` replaces the local squad only after a review panel listing all outs, ins, bank, hit and new XI; use the existing team store/provider and current finance format. It must say this updates **this app**, not the official FPL account. `Hold this week` saves `{season,gw,squad_fingerprint,created_at}` in local storage and displays “Holding GWx” on Studio and the Deadline board until cleared or that GW passes. Save and hold are reversible/clearable.

**Files.** `webapp/frontend/app/transfers/page.tsx`, `lib/api.ts`, `lib/types.ts`, the existing team storage/provider files used by My Team, `components/team/team-plan.tsx` if extracting a shared element diff renderer, `webapp/app.py`, `scripts/optimise.py`, and `webapp/frontend/app/broadcast.css`.

**Focused verification.** One backend test of two locks plus an extra optimized transfer, one of wrong-position/duplicate/over-budget validation, one of unavailable owned player and real selling prices. One client-level test for adding/editing/removing 3 moves and no loss on max change. Manual browser scenario: stage 3 legal same-position moves, verify all three rows and cumulative bank/hit, evaluate, compare 0/1/2/3 cards, inspect all outgoing/incoming IDs and final XI, save/reopen, apply to local My Team, test 375px. A second scenario verifies a selected draft actually constrains optimized results.

## Slice 3 — Chip Advisor as a defensible decision tool

### 3A. Repair data and rules before scoring

1. **Single appearance weighting.** In `scripts/optimise.py::_projection_matrix()`, use the exported `future_points` numeric values directly when complete; `scripts/predict_gameweek.py` has already computed `p_plays * conditional_points`. Retain a separate availability field for risk explanation, but never multiply expected points again. Add a regression fixture with `p_plays=0.5` and exported expected points 4.0, assert chip matrix is 4.0 rather than 2.0. Document a `projection_semantics = expected_points_including_appearance` contract in the prediction manifest/API.
2. **Owned unavailable players.** Reproduce a current 15 containing one `status=i/u/s/n` player through `/api/chips`. Build chip projection rows for the current squad from `s['everyone']` (stable IDs), merge projection/zero-availability state by element, and use `s['players']` only for potential buys. An unavailable owned player can stay in a legal current squad; do not silently substitute a different element or crash. If an ID truly is absent from all snapshot data, return typed 400 `unknown_player`. Catch expected validation errors at `/api/chips`, keeping 500 for real defects. Preserve the known injury/return caveat in the UI.
3. **Per-GW chip eligibility.** Replace `_candidate_window(first_gw,...)` with an eligibility function evaluated separately for every GW and chip set. GW1: no Wildcard or Free Hit. GW1–19 use first set; GW20–38 use second set. A horizon crossing GW19/20 must produce candidates from both sets with separate inventory/expiry metadata. Only one chip is legal in a GW. Free Hit GW19 blocks Free Hit GW20. Saved free transfers remain saved after chip use. Validate planned chip rows as a map keyed by GW; on adding a second chip to the same GW, ask to replace the existing plan, and reject duplicates server-side. Keep first-half inventory editable after GW19 for retrospective correction, while expired chips are no longer suggested for future weeks.
4. **Coverage and freshness.** `predict_gameweek.py` freezes form, price, minutes history and availability across its future horizon. Attach per-GW `projection_state` (`complete`, `partial`, `fixture_only`, `unknown`) and generated timestamp, based on presence of player projections **and** confirmed fixture coverage. Distinguish no confirmed fixture from a confirmed blank. A partial/unknown week must not carry a numerical chip recommendation. Label later weeks “scenario estimate using current player state”; do not describe them as precise future certainty. At the top, show `GW range / generated time / model or fixture signal / missing data` and a Refresh action using the existing refresh flow.

### 3B. Score each chip against the right alternative

Define one unit everywhere: **expected incremental FPL points relative to the best legal no-chip action under the same information**. The `projected_gain` property must be `null` when that comparison is not implemented or data quality is insufficient; expose raw supporting values in `evidence` instead. Never compare a multiweek Wildcard sum directly with a one-week Triple Captain gain as if the numbers have the same meaning.

| Chip | Existing calculation | Required implementation |
| --- | --- | --- |
| Triple Captain | One extra copy of current captain's points. | Re-evaluate best legal captain for the week and return the additional expected captain points, including appearance uncertainty once. Show captain name, fixtures, availability and one-week gain. Compare playing now against remaining eligible weeks of the same chip set as an opportunity-cost estimate; if no trustworthy future projection, show `watch`/`consider`, never `PLAY`. |
| Bench Boost | Sum of four bench players' expected points, labelled gain. | First expose this as `gross_bench_points`, **not net chip gain**. For the current GW, compute both expected totals over all `2^15` play/no-play masks, using each player's `p_plays` as an independent Bernoulli probability. In a play mask, a playing player's conditional points are `expected_points / p_plays` when `p_plays > 0`, otherwise zero; apply the legal no-chip bench order (GK-for-GK; outfield substitutions preserve formation; captain/vice fallback). In the BB branch, count all playing bench players without substitutions. Then `net_bb_gain = expected_BB_total - expected_no_chip_total`. Expose `appearance_assumption: independent` and verify calibration on historical lineups; no simulation seed or sampling error is needed with exact enumeration. Until this is implemented and checked, keep `projected_gain=null` and `status=watch`. |
| Free Hit | Best one-week XI minus unchanged current XI. | Compute the best no-chip lineup after the user's currently available free transfers, bank and exact selling prices, charging any selected hit. Compare that no-chip net week with a legal one-week Free Hit squad, then account for the value/cost of preserving normal transfers and the post-FH squad reverting. At minimum, show one-week `raw_lineup_delta` separately from `chip_specific_gain`; do not label raw delta as chip benefit. Pass `free_transfers` into `/api/chips` and reuse the transfer solver baseline. Return `null` decision gain if finance state is missing. |
| Wildcard | Optimized persistent squad over horizon minus frozen original squad, often huge. | Keep this output only as `rebuild_potential_vs_static_squad` in evidence. Build a rolling no-chip baseline from the current GW forward that can make legal free transfers each GW, tracks bank, sale values, saved free transfers (max 5), hits and changing future fixtures. Compare a Wildcard-now branch to that baseline over the **same** horizon and with the same projection quality/discount policy. State horizon, per-week deltas, assumptions and terminal squad. If rolling baseline is not implemented and backtested, `projected_gain=null` and no action verdict. |

Bench Boost's independent-appearance assumption is a model limitation, so disclose it even with exact enumeration and validate its calibration on historical lineups. For Free Hit and Wildcard, use identity-based finance, never market value for a kept owned player. Once all net gains exist, a per-half scheduling pass must consider conflicts (one chip per GW), used/planned chips and the value of waiting; it returns **at most one** current-week chip candidate, with other current chips marked `compare` and a stated tradeoff. Avoid comparing chip types by raw gain alone when their horizon differs.

### 3C. Status, confidence and visual language

`ChipDecisionPolicy.status()` currently turns any current-week gain ≥1 into `PLAY` when inventory is locally saved; this is an arbitrary product margin, not calibration. In the first P0 release, replace the action vocabulary with `watch`, `consider`, `hold`, `unavailable`, and `compare`. No `PLAY` is emitted until historical holdout evaluation has selected and documented a threshold for each chip and opportunity-cost rule. If a later release restores `PLAY`, the result must include `reason`, `baseline`, `candidate`, `wait_cost`, `data_state`, `calibration_version`, and never conflict with another PLAY in the same GW. Replace hard-coded high/medium/low `confidence` with a calibrated range or omit it; a warning paragraph is not a confidence metric.

Make chip inventory explicitly **manager-entered on this device**. Rename API/UI `inventory_status: synced` to `inventory_source: local_user_reported | unknown` in a versioned contract; do not imply verified FPL synchronization. On mobile, show the current decision/data-quality summary first and place inventory in a collapsed “Manage my chips” disclosure. The opportunity matrix needs distinct units/legend for point gains versus fixture signal indexes; do not color an arbitrary fixture index as if it were expected points. Explain “what would need to change” in a short, chip-specific note for each card. `app/chips/page.tsx` should use a backend `primary_decision` field, not `CHIP_IDS.find()`.

**Files.** `scripts/predict_gameweek.py`, `scripts/optimise.py`, `scripts/chip_policy.py`, `webapp/app.py`, `webapp/frontend/app/chips/page.tsx`, `components/chips/chip-opportunity-matrix.tsx`, `lib/api.ts`, `lib/types.ts`, chip CSS, and `tests/test_chip_advisor.py` plus route tests. Increment `CHIPS_CONTRACT_VERSION` only when the API/parser/schema change together; update the runtime parser, not just TypeScript interfaces.

**Acceptance.** An exported 4.0 expected-point value remains 4.0 in the matrix. An owned unavailable player yields a valid response or typed 400 for a truly unknown ID. GW1 excludes WC/FH; a GW18–21 horizon covers both chip sets; FH19 excludes FH20. A user cannot plan two chips in one GW. Current GW6 data no longer shows two `PLAY` calls or Wildcard +45.2 as comparable to one-week chip gain. Fixture-only/partial data show watch signals with no numerical gain. Phone view shows decision and data quality before the inventory form.

## Slice 4 — nearby logical and visual repairs

| Priority | Issue → cause | Exact change | Done when |
| --- | --- | --- | --- |
| P1 | `app/captain/page.tsx::riskFor()` calls any `status=a` player “Nailed on”; status does not prove a start. | Use “No official availability doubt” for status-a, a separate `minutes_risk: unknown` unless a validated starts model exists, and explicit doubtful/injured messages. Do not imply the model can guarantee minutes. | Healthy players no longer receive “Nailed on” solely from official status. |
| P1 | `components/chrome/main-nav.tsx` badge is all players with news/status, currently a large number; it looks like unread alerts. | Count only alerts relevant to the active 15 and label “Squad alerts”; if active squad absent, omit badge. Do not call it unread without a seen-state implementation. | Badge count matches active squad alerts and is explained in accessible text. |
| P1 | `app/watchlist/page.tsx` and `components/player-drawer.tsx` call missing training history “Promoted / New”; prior-history flag does not establish that. | Replace with “Limited model history”/“No prior model history” and describe lower projection reliability. Never label a player promoted unless a real promoted-club field supports it. | No player is declared new/promoted from `has_prior_history=false` alone. |
| P1 | My Team and Chip Advisor put long setup areas above the user's next action on phone. | Place import/next-decision cards first; collapse advanced controls; use existing broadcast spacing/type tokens, 44px minimum touch targets, legible status/empty states and no clipped horizontal card content at 375px. | One meaningful action and its data state are visible in first mobile screen on both pages. |
| P2 | `DESIGN.md` says all figures are seeded prototype data although the app reads model/API data. | Update the stale paragraph after the UI changes; describe live snapshot, local manager data, fallback fixture signals and what is estimated. | Design doc matches actual production data flow. |
| P2 | Solver forbids GK captain (`scripts/optimise.py`); that is a heuristic, not an FPL rule. | Remove the GK captain constraint and GK exclusion from vice candidates; allow every starting XI player to be captain/vice, then verify a fixture where a GK has the highest projection. | No UI or API treats GK captain as illegal. |

After these targeted fixes, perform one exploratory pass through Team → Captain → Transfers → Chips → Watchlist at desktop and 375px. Log any additional reproducible issue with route, input, observed output, expected output and code cause before expanding scope. Do not redesign a page because it merely differs from personal taste; use `DESIGN.md` and its existing typography/colors as the specification. Fix real clipping, hierarchy, stale state and misleading labels discovered during that pass.

**Visual implementation constants:** use the existing `--pl-purple #37003C`, `--night-900 #1A0022`, `--paper #F5F2F3`, `--ink #210025`, `--lime #00FF87` for primary/selected state, and `--pink #E90052` for outgoing/negative/alert. Keep cyan for focus and stats identity. Use existing `--type-h1`/`--type-h2`/data type tokens and 4px spacing scale; do not add a new typeface, palette or generic rounded-card grid. Keep `.shell` at its current 1440px maximum and `.shell-wide` at 1720px for Studio. On a phone, one column with 16px side padding, 12px between compact controls, and minimum 44px touch targets; data values and status must include text, not color alone. These constraints come from `DESIGN.md` and the current stylesheet.

## Slice 5 — new features that add real value

1. **Deadline decision board (P2, next after correctness).** A compact `/deadline` or My Team dashboard card merges active 15, captain choice, transfer draft, chip plan, bank/free transfers, owned-player alerts and snapshot timestamp for the next GW. Each row links to its existing tool and says `ready`, `needs review`, or `missing input` based on explicit facts, not an opaque score. This prevents five disconnected pages from leaving users unsure what to do. Implement only after the underlying decisions have trustworthy statuses. Store no new server account.
2. **Saved scenario A/B (P2).** Let users duplicate a legal transfer draft into at most three local scenarios. Compare final 15, XI, captain, GW net points, hit, bank and 3-GW projected total with the same snapshot version. Do not compare different prediction snapshots without a visible stale label. JSON export/import can follow later; no public sharing or backend storage is needed for first release.
3. **Projection change explainer (P3).** Capture prior local prediction snapshot metadata, then show a player's old/new expected points, appearance probability, fixtures and generated time. Attribute changes only when those input fields really changed; otherwise say “model refresh” without invented causality. This is more useful than a bare ranking jump.
4. **Personal watchlist alerts (P3).** Optional local alerts for owned/watchlisted players' official status, new confirmed fixture or price changes, with a timestamp and seen state. Trigger only from actual snapshot changes and make alerts dismissible. Do not label all news as unread or predict price moves from unsupported data.
5. **Model reliability card (P3).** Publish rolling holdout metrics by position and projection horizon (MAE/calibration, sample size, last backtest date), then display an interval or reliability band next to decisions. This is a prerequisite for strong chip `PLAY` advice, not a decorative confidence badge.

Avoid adding a league-wide global name index, automatic official FPL account updates, real-time price alerts or push notifications until their data source, authorization and ongoing operation are defined. The requested upgrade is primarily trust and usable decision flow.

## Implementation sequence and contracts for GPT Luna

Use small reviewable commits, ordered by dependency:

1. **Search foundation:** parser + top-of-page UI + recent IDs; then bounded league endpoint/UI. Check existing `webapp/frontend/AGENTS.md` and Next 16 local docs before touching frontend code. Update related types and request wrappers in the same commit as API changes.
2. **Transfer foundation:** draft state and final-squad validator in tenths; backend identity locks and ID arrays; exact draft evaluation; responsive layout and persistence. Keep unconstrained and constrained outputs visibly separate. Never pair optimizer sets by array order.
3. **Chip safety:** immediate projection weighting fix, unavailable-player handling and 2026/27 rules; versioned response with honest status/data quality; then implement/calibrate chip-specific counterfactuals. If a complete Wildcard/Bench Boost counterfactual is not ready, ship evidence with null decision gain and WATCH rather than a fabricated number.
4. **Adjacent fixes and integrated board:** wording/badges/mobile hierarchy, then deadline board, scenarios and later intelligence features.

For each code commit: run the smallest related tests, TypeScript/typecheck and build where affected, then one browser scenario on the changed surface. Record the command/result and observed UI state in the commit or handoff. Do not add repetitive tests that mirror JSX. Do add regression tests for projection semantics, cross-half chip eligibility, identity/finance transfer constraints and request races because these protect subtle behavior. Do not change historical data CSVs or prediction artifacts to make tests pass.

### One-pass acceptance matrix

| Scenario | Exact check |
| --- | --- |
| Search direct | Paste numeric ID and official profile URL; both preview same entry; rapid switch cancels stale result; import/reopen/clear recent. |
| Search league | Find page-4 name, continue to page 7, inspect range/progress, switch league mid-request and confirm no mixing. |
| Transfers | Stage 3 legal moves, edit middle, verify bank in tenths and hit with free=1; constrain optimizer; inspect every Out/In; save/reopen/apply. |
| Transfer edge | Duplicate player, wrong position, club >3, negative bank, max lowered and unavailable owned player receive clear errors/state. |
| Chips | Known expected point stays unchanged; owned injured player; GW1; GW18–21 boundary; FH19→20; duplicate planned chip; fixture-only; no conflicting PLAY. |
| Mobile | At 375px lookup/next decision visible early, Studio shows draft before deep results, no horizontal overflow or clipped controls. |
| Adjacent | Captain status wording, squad alert count, watchlist history wording correspond to actual data. |

### Definition of done

The platform, in the browser, lets a manager import their public team without page hunting, assemble and inspect several real transfer moves, and understand chip output as evidence with correct rules and comparable decision semantics. API and UI agree on element identity, money in tenths, fixture/model data state and the source of inventory. Focused tests pass; the acceptance matrix has one recorded pass per changed surface; there are no unsupported `PLAY`, “Nailed on,” “unread,” or “global name match” claims. Any remaining unsupported chip counterfactual is explicitly unavailable, not reported as projected gain.

## Sources and planning limits

- [Premier League: 2026/27 FPL chips](https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627) supports two chip sets, the GW19/20 boundary, one chip per GW and FH adjacency rule.
- [Premier League: 2026/27 changes](https://www.premierleague.com/en/news/4679873) supports the free-transfer cap of five and removal of AFCON bonus transfers.
- [Premier League FPL FAQ](https://www.premierleague.com/en/news/4661030) supports GW1 Wildcard/Free Hit restrictions and retained saved free transfers after chip use.
- [Premier League FPL basics: managing your team](https://www.premierleague.com/en/news/2174899) says the captain and vice-captain are selected from the starting lineup; it gives no goalkeeper exclusion.
- Local evidence comes from the cited files, current tests, and a GW6 browser walkthrough. The unavailable-owned-player crash is a code-derived risk pending reproduction, and no public global manager-name API has been validated; neither should be stated as a reproduced runtime failure or guaranteed external fact.

## Continuation and git discipline

When approaching context compaction, update `PLATFORM_V2_HANDOFF.md` **before** compaction with completed files/commits, exact outstanding work, commands/results, active server/browser state and any blockers. A new session reads that file plus `git status` first. Commit and push at coherent progress points; stage only task-owned files, inspect the full staged diff, and use a normal single-author commit message with **no `Co-authored-by` trailer**. Never reset or stage unrelated dirty files.
