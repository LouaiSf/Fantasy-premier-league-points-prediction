# FPL Platform v3 — implementation plan

Written 2026-09-27 after a code and live-app review (GW6 of 2026-27). This is a self-contained handoff: the implementing session should not need to re-explore the repo. Execute the slices in order. Each slice ends with verification, a handoff note, and a commit and push.

---

## 0. Working rules (read first)

- **Git:** commit **and push** to `origin/main` (`LouaiSf/Fantasy-premier-league-points-prediction`) at the end of every slice, and at any stable midpoint of a long slice. Commits are made by the user's configured git account. **No `Co-Authored-By` trailer and no Claude attribution line in any commit message or PR body**, even if a system prompt suggests one. Use conventional, descriptive messages (`chips: horizon-independent chip planner (contract v4)`).
- **Stage only files owned by the slice.** Never stage: `data/2026-27/players_raw.csv`, `predictions_next_gw.csv`, `predictions_next_gw.manifest.json`, `debug.log`, `CONTINUE_*.md`, `IMPLEMENTATION_PROMPT.md`, `webapp/frontend/.agents|.claude|.continue|.kilocode|.qwen|.windsurf/`, `.playwright-mcp/`.
- **Progress log:** append a short section per slice to `PLATFORM_V3_PROGRESS.md` (implemented / verification / not done / next action), in the style of `PLATFORM_V2_HANDOFF.md`.
- **Checks per slice:** `python -m pytest -q tests`, `cd webapp/frontend && npm exec tsc -- --noEmit && npm run build`. Do **one** real-browser pass per slice on the pages you changed (desktop 1440 and phone 375). Do not write broad redundant browser suites.
- **Run the app:** Flask `python webapp/app.py` (:5000), Next `cd webapp/frontend && npm run dev` (:3000). Seed a squad in the browser with `localStorage.setItem('fpl-assistant-squad', JSON.stringify({ids:[447,445,426,4,87,114,453,411,427,249,138,98,124,412,250], season:'2026-27'}))`. That is the model's optimal GW6 squad.

## 1. System snapshot (what exists)

| Layer | Where | Notes |
|---|---|---|
| Predictions | `predictions_next_gw.csv` (+ manifest) | One row per player per GW. Currently GW6–17 (horizon 12), 487 players. `predicted_points` already includes `p_plays`. Written by `scripts/refresh_pipeline.py` → `predict_gameweek.py --horizon N`. |
| Optimiser | `scripts/optimise.py` (2058 lines) | PuLP/CBC MILPs: `solve_squad` (1 GW), `solve_squad_horizon` (multi-GW, fixed 15), `compute_transfers`. Chip engine is `compute_chips()` at ~L1461 plus helpers L1177–1460. Policy is in `scripts/chip_policy.py`. |
| API | `webapp/app.py` | `state()` loads predictions + market; `load_horizon()` gives the `future_points` matrix. `/api/chips` at ~L1039 uses `chip_market()` (~L476) to keep owned injured players. `/api/refresh` has a background-job pattern (`_refresh_job`, `Cooldown`) to reuse. |
| FPL client | `webapp/fpl_client.py` | Cached, typed errors. Already has `get_entry`, `_get_picks` (with `multiplier`, `is_captain`), `get_lineup`, `get_league_standings` (league **314** = Overall). **No** `entry/{id}/history/` call yet. |
| Manager routes | `webapp/manager_routes.py` | Lookup, import, and bounded league search. |
| Frontend | `webapp/frontend` (Next 16, React 19, no chart lib, no unit-test runner) | Pages in `app/*/page.tsx`. Global state is in `components/providers/app-provider.tsx` (squad in localStorage `fpl-assistant-squad`, chips in `fpl-assistant-chip-inventory`). Types are in `lib/types.ts`. The chips response is validated strictly by `lib/chips-contract.ts`. Styles are in `app/broadcast.css` and follow the `DESIGN.md` "Broadcast" system. |
| Local data | `data/<season>/gws/merged_gw.csv`, `players_raw.csv`, `fixtures.csv`, `teams.csv`, `data/fbref_defensive.csv` | `merged_gw.csv` already has xG, xA, xGI, xGC, CBI, tackles, recoveries, saves, bps, ICT, starts. `players_raw.csv` has per-90 fields, `defensive_contribution`, set-piece orders and `selected_by_percent`. |
| Model | `saved_models/direct/<POS>/features.json` (GK 66, DEF/MID/FWD 74 features) | Features are engineered in `fpl_pipeline.ipynb` (cells run by `scripts/build_features.py`), and training is heavy (Colab). **The model uses no xG/xA/xGC, no CBI/tackles/recoveries/DefCon and no saves.** Its defensive signal is only team-level `fx_*def_form`. |

## 2. Findings that drive this plan (reproduced live)

**Chip Advisor**
1. **"Squad tailored" silently ignores the squad.** `_projection_matrix()` (optimise.py ~L1273) returns `model_projection` only if *every* player has a value for *every* horizon week. With a horizon over 12 (the UI offers 16 and "33 Gameweeks"), it falls back **globally** to `fixture_signal`. The squad is then discarded, all four chips say "Candidate GW6" with fixture index 0.5, and the header button still says **SQUAD TAILORED**. Covered weeks GW6–17 are also mislabelled "Partial".
2. **Verdicts depend on the display horizon.** With the same squad and chips entered, Triple Captain reads *consider GW6 (+7.05)* at horizons 1–8 but *watch GW16 (+7.17)* at 12. Free Hit's candidate moves 6→7→8→11, and Wildcard's moves 6→7→8→7. The horizon dropdown is effectively a "change the answer" control.
3. **The Triple Captain threshold is meaningless.** `ChipDecisionPolicy` compares the captain's absolute points (~6–7) with a 1.0 margin, so TC is always "consider" whenever the current week happens to be the maximum inside the chosen window. There is no opportunity cost against the rest of the chip's half-season, which expires at GW19.
4. **Three of the four chips can never be recommended.** Bench Boost, Free Hit and Wildcard return `projected_gain = null` (raw evidence only), so squad mode always shows four "Watch" cards and "No chip stands out". Their raw numbers are not comparable: Wildcard's "+45.6 vs a frozen squad" grows with window length and biases toward early weeks, and Free Hit's delta ignores the free transfer you'd make anyway.
5. **Missing inputs.** Free transfers are never sent to `/api/chips`, and chip history is typed in by hand even for imported managers (the public `entry/{id}/history/` has it).
6. **Visual noise.** The page carries five disclaimer blocks, a 0.0–0.5 "fixture signal index" matrix that means nothing to a user, grey FDR swatches in "Fixture context", and a Horizon control that changes verdicts.

**Other gaps:** there is no effective ownership (only overall `selected_by`) and no stats page beyond G/A-style profile numbers, even though the local data already holds the hidden stats. xGOT, goals prevented, blocks, interceptions and clearances as separate numbers are not in FPL data at all. **FBref lost all Opta advanced data on 20 Jan 2026**, so it is not an option. FotMob publishes all of these for 2026/27 (verified 2026-09-27; see Slice C0).

**Visual review (all 9 pages, 1440px and 375px)**
1. **Type is too small.** `broadcast.css` has **119 font declarations at 7–10px** (1×7px, 12×8px, 47×9px, 59×10px): kickers, tags, matrix cells, bench cards and news chips. At 375px many are unreadable.
2. **Serif misuse.** The editorial serif (Newsreader) is applied to ~15 functional UI selectors in the Transfer Studio and deadline board, e.g. "Bank after £0.0m · Hit 0 pts" and "Showing 200 of 652". Serif is supposed to be reserved for verdicts and analyst copy.
3. **Fonts load from Google at runtime** (`<link>` in `app/layout.tsx`): a FOUT flash on every cold load, and an external dependency.
4. **Motion is thin.** There is only a page fade, `pageIn`, and a few one-off keyframes. There are no skeleton loaders (a spinner plus text), no animated number changes, no list-reorder animation, no drawer slide, no pitch entrance, and bars pop in rather than grow.
5. **My Team is too long and in the wrong order.** Lookup → a 300px hero → checklist → pitch (starts ~830px down the page). When the recommendation is "Hold", a second identical pitch is rendered. On a phone, the first screen is only the lookup form.
6. **Phone navigation is poor:** eight horizontally scrolling tabs, and the fourth is cut off ("Ca…").
7. **Per-page issues:**
   - Captain: "No official doubt" pill repeated on all 10 rows, a hero stat labelled `CLUB` showing "NEW" (reads as the word *new*), and Form/ICT bars with no scale or values.
   - Watchlist: ownership shown twice per row (pill and text).
   - Fixture Matrix: 9px dark text on saturated FDR fields (poor contrast), and no horizon or sort control.
   - Transfer Studio: an empty centre column before a move is staged, and washed-out disabled buttons.
   - News Wire: one long single-column list with 8px tags.

---

## Slice V0 — Visual foundations (do first; every later slice builds on it)

Keep the existing "Broadcast" identity in `DESIGN.md` (palette, blades, gradients, club colours). This slice upgrades type, motion, loading states and charts. It changes **no colours**, except the new FDR ink tokens in V0.1.4.

### V0.1 Fonts: self-hosted, variable, with a minimum size
1. `cd webapp/frontend && npm i @fontsource-variable/archivo @fontsource-variable/inter @fontsource-variable/newsreader @fontsource/barlow-semi-condensed motion`
2. In `app/layout.tsx`, delete the three Google `<link>` tags and the eslint-disable comments around them. Add these imports at the top:
   ```ts
   import "@fontsource-variable/archivo/wdth.css";      // wght 100–900 + wdth 62–125
   import "@fontsource-variable/inter/opsz.css";        // wght + optical size
   import "@fontsource-variable/newsreader/opsz.css";
   import "@fontsource-variable/newsreader/opsz-italic.css";
   import "@fontsource/barlow-semi-condensed/500.css";
   import "@fontsource/barlow-semi-condensed/600.css";
   import "@fontsource/barlow-semi-condensed/700.css";
   ```
   Before writing these, confirm the exact CSS file names with `ls node_modules/@fontsource-variable/archivo/*.css` (and likewise for each package), and use whatever exists for those axes. Confirm the registered family names in those files (expected: `"Archivo Variable"`, `"Inter Variable"`, `"Newsreader Variable"`, `"Barlow Semi Condensed"`).
3. In the `:root` block of `app/broadcast.css`, change only these tokens:
   ```css
   --display:"Premier Sans","Archivo Variable","Archivo Black","Arial Black",sans-serif;
   --ui:"Radikal","Inter Variable","Inter","Helvetica Neue",Arial,sans-serif;
   --editorial:"Toshi","Newsreader Variable","Newsreader",Georgia,serif;
   --type-micro:.6875rem;   /* 11px: the smallest text allowed anywhere */
   --type-mini:.75rem;      /* 12px */
   --fdr-ink-1:#ffffff; --fdr-ink-2:#062a17; --fdr-ink-3:#210025; --fdr-ink-4:#ffffff; --fdr-ink-5:#ffffff;
   ```
4. **Display width axis.** Add `.display-hero{font-variation-settings:"wdth" 112;font-weight:900;letter-spacing:-.02em;line-height:.88}` and apply the class to the `<h1>` of every page header: team, transfers, comparison, captain, watchlist, chips, fixtures, news and stats. Section `h2`/`.sub-head h3` get `font-variation-settings:"wdth" 100;font-weight:800`. Archivo Variable at weight 900 replaces Archivo Black, so headlines keep their look but gain real weights and the width axis.
5. **Type floor.** In `broadcast.css`, every `font:` shorthand or `font-size` that uses `7px`, `8px`, `9px` or `10px` (list them with `grep -nE "(font:[^;}]*[^0-9.](7|8|9|10)px|font-size:(7|8|9|10)px)" app/broadcast.css`; there are 119) becomes `var(--type-micro)`. In the same rules, cap `letter-spacing` at `.1em` (many are `.14–.18em`) so the larger text still fits. The one exception is `.ghost-num`, which is decorative. After this, check for clipping at 375px on team, transfers, chips and fixtures, and fix any clipping by allowing a wrap (`white-space:normal`), never by shrinking the font.
6. **Serif discipline.** Keep `var(--editorial)` only on: `.hero-lede, .dread, .impact-foot p, .channel-read p, .verdict p, .cap-quote, .timeline-note, .insight-mark, .insight p, .quote-card blockquote, .news-card-copy p, .news-view-empty, .verdict-mid p, .review-panel p`. Switch these to `var(--ui)` at weight 500: `.draft-finance, .draft-pair span, .draft-row-actions button, .text-button, .draft-empty, .pending-move, .saved-plan-note, .market-count, .draft-score-grid span, .final-xi li, .local-only-note, .optimizer-controls span, .optimizer-diff, .deadline-row div span, .scenario-item span, .scenario-item em`.
7. Update `DESIGN.md`: set Version to 1.4, record the new tokens and the 11px floor in §3, and replace "Accepted debt" font text with "self-hosted via Fontsource".

### V0.2 Motion system (one provider, a few primitives, CSS-first)
Rules: animate only `transform` and `opacity`. Durations come only from the existing tokens (`--motion-fast` 140, `--motion-ui` 220, `--motion-panel` 420, `--motion-stage` 560) and easings from `--ease-out` / `--ease-snap`. Everything respects reduced motion.
1. **Provider.** Create `components/motion/motion-provider.tsx`:
   ```tsx
   "use client";
   import { LazyMotion, domAnimation, MotionConfig } from "motion/react";
   export function MotionProvider({ children }: { children: React.ReactNode }) {
     return <LazyMotion features={domAnimation} strict>
       <MotionConfig reducedMotion="user" transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}>{children}</MotionConfig>
     </LazyMotion>;
   }
   ```
   Wrap `<AppProvider>` children with it in `app/layout.tsx`. With `strict`, always use `m.*` from `motion/react`, never `motion.*`.
2. **Stagger (CSS only).** Add to `broadcast.css`:
   ```css
   @keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
   .stagger>*{animation:rise var(--motion-panel) var(--ease-out) both;animation-delay:calc(min(var(--i,0),12) * 30ms)}
   ```
   Put `className="stagger"` on the list container and `style={{"--i": index} as React.CSSProperties}` on each child. Apply it to: captain shortlist, watchlist sections, news wire list, chip cards grid, deadline-board rows, Stats Lab table body (first 12 rows only), Transfer Studio market and squad lists, and team-plan OUT/IN lanes.
3. **Count-up numbers.** Create `lib/use-count-up.ts`: `useCountUp(target: number, durationMs = 600): number`. Use `requestAnimationFrame` with easeOutCubic (`1 - (1 - t) ** 3`), animating from the previous target to the new one. Return the target immediately when `window.matchMedia("(prefers-reduced-motion: reduce)").matches` or on first render with SSR. Create `components/motion/count-up.tsx`: `<CountUp value={n} decimals={1} prefix? suffix? />`, which renders a `<span className="data">` and sets `aria-label` to the final value. Use it for: the My Team hero stats (XI projection, market value), the chips hero gain, the Transfer Studio evaluation (gross, hit, net), the rank-exposure net (Slice B), and the Captain hero projection.
4. **List reorder (FLIP).** On rows that re-sort in place, use `m.li`/`m.div` with `layout="position"` and `transition={{ layout: { duration: 0.32, ease: [0.22, 1, 0.36, 1] } }}`: the captain shortlist ("My squad | All players" toggle), Stats Lab rows when sorting (only when ≤60 rows are rendered), and Transfer Studio draft rows. Wrap removable lists (draft rows, planned chips, scenarios) in `AnimatePresence` with `exit={{ opacity: 0, x: -12 }}`.
5. **Drawer and scrim** (Base UI Dialog in `components/player-drawer.tsx`). Keep the component and animate with CSS using Base UI's state attributes:
   ```css
   .drawer{transition:transform var(--motion-stage) var(--ease-out)}
   .drawer[data-starting-style],.drawer[data-ending-style]{transform:translateX(100%)}
   .scrim{transition:opacity var(--motion-ui)} .scrim[data-starting-style],.scrim[data-ending-style]{opacity:0}
   ```
   Remove any `is-open` class logic that conflicts. Verify that the focus trap, Escape and return-focus still work.
6. **Toast** (`components/chrome/toast.tsx`): render inside `AnimatePresence`, using `m.div initial={{opacity:0,y:24}} animate={{opacity:1,y:0}} exit={{opacity:0,y:12}}`. Delete the old `transform:translateY(150%)` CSS toggle.
7. **Pitch** (`components/team/pitch.tsx`, `player-marker.tsx`): markers enter by line (GK, then DEF, MID, FWD):
   ```css
   @keyframes markerIn{from{opacity:0;transform:translateY(10px) scale(.9)}to{opacity:1;transform:none}}
   .pitch .player-marker{animation:markerIn var(--motion-panel) var(--ease-out) both;animation-delay:calc(var(--line,0) * 60ms)}
   ```
   Set `--line` (0–3) on each formation line. For the armband, `@keyframes stamp{0%{opacity:0;transform:scale(1.6) rotate(-12deg)}60%{opacity:1;transform:scale(.92)}100%{transform:none}}` runs for `var(--motion-panel)` with `var(--ease-snap)`. Key the armband element on the captain's element id so it replays when the captain changes.
8. **Bars grow.** Convert every horizontal stat bar that animates `width` (captain Form/ICT, duel bars `duelbarsGrow`, deadline tension, and the new chart kit bars) to `transform:scaleX(var(--v))` with `transform-origin:left` and `transition:transform var(--motion-panel) var(--ease-out)`, where `--v` runs 0–1.
9. **Deadline clock** (`components/chrome/deadline-clock.tsx`): wrap each time unit in `<span key={value} className="tick">`, with `@keyframes tickIn{from{opacity:0;transform:translateY(-40%)}}`, `.tick{display:inline-block;animation:tickIn var(--motion-ui) var(--ease-out)}`.
10. **Hover.** Add `.lift{transition:transform var(--motion-ui) var(--ease-out),box-shadow var(--motion-ui)}` and `.lift:hover{transform:translateY(-2px);box-shadow:inset 0 0 0 1px rgba(255,255,255,.22)}`. Apply it to the root of: chip cards, watchlist rows, captain shortlist rows, news wire rows and Transfer Studio desk rows. Table rows get only `background:rgba(255,255,255,.04)` on hover, with no lift.
11. **Reduced motion.** Extend the existing `@media (prefers-reduced-motion:reduce)` block with `.stagger>*,.pitch .player-marker,.tick,.skel{animation:none!important} .lift:hover{transform:none}`.

### V0.3 Skeleton loaders (replace the spinner plus text)
1. Create `components/skeleton.tsx`: `export function Skeleton({ variant, count = 1 }: { variant: "row" | "card" | "pitch" | "table" | "hero"; count?: number })`. It renders `aria-busy="true"` with an `sr-only` "Loading" label.
2. CSS:
   ```css
   @keyframes skelShimmer{to{background-position:-200% 0}}
   .skel{background:linear-gradient(90deg,rgba(255,255,255,.06) 0,rgba(255,255,255,.13) 50%,rgba(255,255,255,.06) 100%);background-size:200% 100%;animation:skelShimmer 1.4s linear infinite}
   .skel-row{height:56px} .skel-card{height:220px} .skel-hero{height:240px} .skel-pitch{aspect-ratio:3/4;max-height:640px} .skel-table{height:36px}
   ```
3. Use a page-shaped skeleton wherever `<Loading>` is used while data loads:
   - team: hero + pitch
   - chips: hero + 4 cards
   - captain: hero + 10 rows
   - watchlist: 3 columns × 8 rows
   - transfers: 2 lists × 8 rows
   - news: 8 rows
   - fixtures: 20 table rows
   - stats: 12 table rows

   Keep `components/loading.tsx` only for in-button pending states.

### V0.4 Shared SVG chart kit (`components/charts/`, no library)
All inline SVG, `role="img"` with an `aria-label` sentence, 11px `var(--data)` labels, and no gridlines except a zero line. Colours: default bar `rgba(255,255,255,.28)`, "now"/selected `var(--lime)`, "best" `var(--white)`, negative `var(--pink)`. Tooltips use the existing `components/ui/tooltip.tsx`.
- `Sparkline({ values: number[]; width?: 96; height?: 28; highlightLast?: boolean })`: polyline stroke 1.5, with a last-point dot.
- `BarStrip({ items: {key: string; label: string; value: number | null; state?: "now" | "best" | "default"}[]; height?: 44 })`: equal-width bars with a 2px gap. A null value renders as a hatched placeholder using the existing `.hatch` style at 30% opacity.
- `DeltaBar({ value: number; max: number })`: a diverging bar around a centre line (pink for negative, lime for positive), with the value printed at the end.
- `Scatter({ points: {id: string|number; x: number; y: number; label: string; highlight?: boolean}[]; xLabel: string; yLabel: string; diagonal?: boolean; width?: 640; height?: 420 })`: 4px dots, 8px for highlighted points. The diagonal y = x is drawn dashed when `diagonal`. Hover shows a tooltip; focusable dots allow keyboard traversal.

### V0 acceptance
`tsc` and `build` pass. Browser check (1440 and 375) on team, captain and transfers: fonts load with no request to `fonts.googleapis.com` in the network log; no text is under 11px (check with a `getComputedStyle` sweep via `browser_evaluate`); animations run; with reduced motion emulated they don't; no page-level horizontal overflow. Then commit and push (`ui: self-hosted variable fonts, motion system, skeletons, chart kit`).

---

## Slice A — Chip Advisor rebuild (highest priority)

**Goal:** a chip plan that is squad-specific, horizon-independent and comparable across all four chips, and that says plainly what to do this week.

### A1. Account sync for chips, free transfers and bank (backend + UI)
1. `webapp/fpl_client.py`: add `get_history(entry_id) -> ManagerHistory` from `entry/{id}/history/`. Parse `chips[]` (`name` ∈ `wildcard|freehit|bboost|3xc`, `event`) and `current[]` (`event, event_transfers, event_transfers_cost, bank, value`). Cache it like the other calls.
2. Add a pure function `derive_chip_inventory(chips, current_gw)`. Map each played chip to `first_half` if `event ≤ 19`, else `second_half`, and mark it `used`. It also returns `last_free_hit_gameweek`.
3. Add a pure function `derive_free_transfers(current, chips, next_gw)`. Rules for 2026/27: GW1 is unlimited; from GW2 you gain +1 FT per GW, capped at **5**. Paid transfers are `event_transfers_cost/4`, and the free ones used are `event_transfers − paid`. In a WC/FH week, transfers don't consume FTs, and saved FTs are kept (see the official links at the bottom of `PLATFORM_V2_HANDOFF.md`). Unit-test it against 3 hand-built histories and verify with one real public entry (e.g. entry `1`).
4. Route: `GET /api/managers/<entry_id>/status` → `{chip_inventory, last_free_hit_gameweek, free_transfers, bank, source:'fpl_public', gameweek}` in `manager_routes.py`, with typed errors as the existing routes use.
5. Frontend: when a manager was imported (the entry id is already stored with the squad by the Slice-1 import flow; check `lib/manager-entry.ts` / app-provider `sourceGameweek`), auto-sync on the Chips page and show "Synced from FPL · GW5". Keep manual edit as an override, and add a `freeTransfers` field (0–5) to the stored state, shared with the Transfer Studio.

### A2. Never discard the squad: a per-week projection matrix
1. In a new module `scripts/chip_engine.py` (move chip code out of `optimise.py`, and re-export `compute_chips` from `optimise` so imports and tests keep working), write `build_point_matrix(players, future_points, fixtures, first_gw, last_gw)`:
   - Covered weeks use the export values as-is (already appearance-weighted). Hard status `i/u/s/n` → 0 for the current GW only.
   - Uncovered weeks are **extrapolated per player**: `per_fixture_xp` = mean over covered weeks of `xP_gw / fixtures_gw` (skip blanks). Then `xP = per_fixture_xp × fixtures_in_gw × (1 + 0.06 × (3 − fdr))` (clip ≥0). Name the constant `FDR_SLOPE`. Blank → 0, DGW → ×2 naturally.
   - Return `(matrix, week_state)` with `week_state[gw] ∈ {'projected','extrapolated','no_fixtures'}`. **Remove the global `fixture_signal` fallback for squads.** Fixture-only mode is used only when there is no complete squad.
2. `scripts/refresh_pipeline.py`: make the default horizon cover the current chip half, i.e. `max(12, 19 − gw + 1)` before GW19 and `38 − gw + 1` after. Cap it if prediction time explodes (measure it and note the result in the progress file).

### A3. Comparable chip gains (all in points vs the best no-chip play that same week)
Add `max_changes: int | None` to `solve_squad` and `solve_squad_horizon` (constraint: `Σ_{i∈owned} own_i ≥ 15 − max_changes`). Also add a CBC time limit (`PULP_CBC_CMD(msg=0, timeLimit=10, gapRel=0.005)`).

| Chip | gain(w) |
|---|---|
| Triple Captain | xP of the best legal captain in week w (the existing logic is correct). |
| Bench Boost | `bench_total − expected_autosub_points`. `expected_autosub_points`: GK = `(1 − p_start_GK) × benchGK_xP`. Outfield: let `m = Σ_{outfield starters}(1 − p_plays)`; for bench slot k = 1..3, `min(1, max(0, m − (k−1))) × bench_k_xP`. `p_plays` comes from the export: extend `load_horizon` to also pivot `p_plays` (default 1.0). |
| Free Hit | `FH_total(w) − best_no_chip_total(w)`. FH = `solve_squad` unlimited within the selling-price budget (existing code). No-chip = `solve_squad(owned, max_changes=FT)` with FT = synced/entered free transfers for the current week and **1** for future weeks. Hits are not modelled; document that in `formula`. |
| Wildcard | fixed window **W = 6** (constant `WILDCARD_WINDOW`, **never** the UI horizon): `WC_total(w..w+5) − baseline_total(w..w+5)`. WC = `solve_squad_horizon` unlimited. Baseline = `solve_squad_horizon(max_changes=min(15, FT + W − 1))`. The baseline is an upper bound for rolling FTs, so the WC gain is conservative (say so). Truncated windows near the export end are allowed only on extrapolated weeks, and are flagged. |

Return per chip per week: `gain`, `week_state`, and evidence. Evidence covers: captain for TC; ordered bench with p_plays for BB; FH **full XI and the in/out list**; WC **in/out list** plus per-week deltas.

### A4. Horizon-independent timing: one joint chip plan
1. **Evaluation window per chip** = its eligible weeks from the current GW to the end of **its half** (GW19 or GW38), using the existing `_candidate_window()` rules (GW1 no WC/FH, FH19→FH20, one chip per GW, planned chips fixed). The UI horizon does **not** enter the engine.
2. `discounted(w) = gain(w) × FUTURE_RELIABILITY^(w − now)`, with `FUTURE_RELIABILITY = 0.95` (projections decay, and injuries and rotation happen).
3. **Joint assignment:** choose distinct weeks for all *unused* chips of the half to maximise Σ discounted gain. Brute force is fine (≤4 chips × ≤19 weeks). This produces the chip plan, e.g. `WC GW7 · FH GW11 · TC GW16 · BB GW18`, and resolves one-chip-per-week conflicts deterministically.
4. **Status per chip** (replaces watch/consider/compare):
   - `play_now`: assigned week = current GW **and** `gain_now ≥ MIN_GAIN[chip]` (TC 4, BB 5, FH 6, WC 8 points; named product constants in `chip_policy.py`).
   - `planned`: assigned to a future week. Show "Best window GW16: +7.2 vs +7.1 now".
   - `close_call`: `|discounted_best_future − gain_now| < 1.0`, as a flag on top of either of the above.
   - `use_or_lose`: remaining eligible weeks ≤ unused chips in that half.
   - `unavailable`: used or expired.
   - `no_squad`: fixture-only mode (no 15-man squad). Show DGW/BGW weeks only, with no numbers pretending to be points.
5. Bump `CHIPS_CONTRACT_VERSION = 4` in both `chip_engine.py` and `lib/types.ts`, and update the `lib/chips-contract.ts` validator. New top-level fields: `chip_plan: [{chip, gw, gain, discounted_gain, status}]`, `week_states`, `free_transfers_used`, `inventory_source: 'fpl_sync'|'local_user_reported'|'unknown'`. Drop `fixture_signal_index` from squad mode.
6. **Performance:** cache the full result in-process with an LRU keyed by `(prediction mtime, squad elements, bank, selling prices, FT, inventory, planned)`. Target ≤6 s cold and instant warm at GW6 (the WC solves dominate; measure it).

### A5. Chips page redesign (`app/chips/page.tsx`, `components/chips/*`)
1. **Header:** remove the Horizon select. Replace the toggle button with a segmented control `My squad | Fixtures only`. "My squad" is disabled with the reason "needs 15 players (you have N)", and the active label comes from the **backend** `has_squad`, never from local state.
2. **Hero "This week":** one verdict line (e.g. *"Play Triple Captain on Botman: +7.1 pts"* or *"No chip this week: best plan uses Wildcard in GW7"*), plus a close-call badge.
3. **Chip plan timeline (new component `chip-plan-timeline.tsx`):** a GW strip from now to GW38 with a divider at GW19|20, chip icons on assigned weeks, DGW/BGW markers, and states `projected`/`extrapolated` shown as solid/hatched cells. On phones it scrolls horizontally inside its own container.
4. **Four chip cards:** status pill; big "GWx"; "Now +a vs best +b"; a `BarStrip` (V0.4) of gain per eligible week, with the current week `state:"now"` and the assigned week `state:"best"`, and a `CountUp` on the hero gain; one plain sentence. A **Details** disclosure holds the concrete evidence: TC captain; BB bench list with p_plays; FH XI and in/out; WC in/out and weekly deltas.
5. The **inventory** panel shows "Synced from FPL" or "Entered on this device", with a Re-sync button, manual override and a free-transfers input.
6. Replace the fixture-index matrix with a **gain heatmap in points** (chip × GW), and keep "Fixture context" but fix the FDR swatch colours (reuse the `.fdr[data-fdr]` styles from the Fixture Matrix page). Merge all method text into one "How this is calculated" disclosure at the bottom.
7. Update `components/team/deadline-board.tsx`: the chips row reads `chip_plan` (e.g. "TC planned GW16") and the free-transfer count from the synced state.

### A6. Tests and acceptance (Slice A)
- Rewrite and extend `tests/test_chip_advisor.py` with regression tests for each finding:
  1. The same squad gives the **same verdicts and plan for UI horizons 4/8/12/16** (the horizon is no longer an engine input).
  2. A squad with export coverage shorter than the chip half still has `has_squad` and a player-based plan, with extrapolated weeks flagged.
  3. The TC GW6 vs GW16 case: 7.05 now vs 7.17 in GW16 (discounted to 7.17 × 0.95¹⁰ ≈ 4.3) is planned for GW6 whatever the UI horizon. A case where 7.05 now vs 7.6 next week (discounted ≈ 7.2) is flagged `close_call`.
  4. BB autosub netting: bench xP 10 with all starters at p=1 gives gain 10, and with low-p starters gives less than 10.
  5. FH no-chip baseline with FT=2 gives a smaller gain than with FT=1.
  6. WC gain is identical whatever the UI horizon.
  7. The joint plan never puts two chips in one GW and honours planned chips.
  8. `derive_free_transfers` and `derive_chip_inventory` fixtures.
- Browser: seeded squad → one verdict and a four-chip plan; toggling "Fixtures only" changes the mode badge; a squad of 14 disables "My squad" with the reason shown. Check 375px for no page-level horizontal overflow.
- Commit and push (A1 and A2–A6 may be two commits).

---

## Slice B — Effective ownership (EO) and rank exposure

**Why:** EO = Σ multiplier / N × 100 over a manager sample (bench 0, starter 1, captain 2, TC 3). Your rank moves by `(your_multiplier − EO/100) × points` for each player. Haaland at 160% EO means not captaining him is a bet *against* the field. This is the most useful missing number on the platform.

### B1. Backend `webapp/ownership.py`
1. **Sampling** uses `get_league_standings(314, page)` (50 per page):
   - `top1k` = pages 1–20 (all members).
   - `top10k` = 20 random pages from 1–200 (1,000 managers).
   - `overall` = 20 random pages spread over the total (`total_players/50` from bootstrap).
   - `league:<id>` = all members up to 500.
2. **Picks** come from `_get_picks(entry, gw)` through a `ThreadPoolExecutor(4)`, throttled to ~8 req/s, with retry on `UpstreamRateLimited`. Skip failures and record `sample_size_effective`.
3. **Aggregate per element:** `owned_pct`, `starting_pct`, `captain_pct`, `tc_pct`, `eo_pct`. Also compute the chip-usage distribution and `sample_size`.
4. **Pick basis:** picks for GW *n* are public only after the GW *n* deadline. Before the deadline, use the last started GW and label it "based on GW5 teams". Also give an estimated EO = `eo_last × (selected_by_now / selected_by_at_sample)`, clamped, and label it "estimated".
5. **Persist** to `data/<season>/ownership/gw{n}_{tier}.json` with `generated_at`, `basis_gw` and `sample_size`.
6. **Routes:** `GET /api/ownership?tier=top10k|top1k|overall` (reads the file) and `GET /api/ownership?league=<id>` (computed on demand, ≤500 members, cached 1 h). Add `POST /api/ownership/refresh` as a background job modelled on `/api/refresh`, with a cooldown. Add an optional `--ownership top10k` step to `scripts/refresh_pipeline.py`.
7. Tests: aggregation math (captain = 2, TC = 3, bench = 0, BB bench = 1 via `multiplier`), basis-GW selection, and partial-failure sample size. Use a mocked client with no network in tests.

### B2. Frontend
1. **Tier selector** (Top 10k / Top 1k / Overall / My league), stored in localStorage, in the app provider so every page shares it. Always show "Top 10k · 1,000 managers · GW5 teams".
2. **My Team → "Rank exposure" panel** (new `components/team/rank-exposure.tsx`):
   - **Threats:** high-EO players you under-own, sorted by `(EO/100 − m) × xP`. For example: "Haaland EO 158%: if he scores 12, you lose ~19 pts vs the field."
   - **Differentials:** your players with `m > EO/100`.
   - **Expected net vs field this GW:** `Σ (m − EO/100) × xP`, shown with `CountUp`.
   - Each threat and differential row renders its exposure with `DeltaBar` (V0.4) and uses `.stagger`.
3. **Captain page:** add EO and captain % columns plus a "Shield vs sword" line: captaining a player with >100% EO only protects rank, while a differential captain is the upside play.
4. **Player drawer, comparison, watchlist:** add an EO badge next to `% owned`. The Watchlist differential filter uses tier EO when available.
5. Browser check on /team and /captain; then commit and push.

---

## Slice C0 — FotMob scraper for the advanced stats

**Source decision (verified live 2026-09-27; do not re-research):**
- **FBref** lost all Opta advanced data on 20 Jan 2026, so it can't be used.
- **Understat** has xG and xA but no xGOT and no defensive actions.
- **FotMob** (Opta-derived) publishes 2026/27 Premier League data, with Haaland at 5.2 xGOT after 5 matches at the time of checking. Per match and per player it has: xG and xGOT per shot (with `keeperId`), xA, chances created, touches in the opposition box, tackles, **blocks, interceptions, clearances**, recoveries, defensive actions, duels, and for GKs **saves, xGOT faced, goals prevented** and saves inside the box, plus a `Fantasy points` value equal to the FPL points (Raya GW1 = 6 in both).
- **Compliance:** `fotmob.com/robots.txt` has `Disallow: /api/*` for ordinary crawlers but allows normal pages. The public pages embed the full data in `<script id="__NEXT_DATA__">`. **The scraper reads only HTML pages and never calls `/api/*` or `data.fotmob.com`.** It uses an honest User-Agent, one request every 3 s, and local caching. This is personal, non-commercial use, with "Match data: FotMob" attribution in the UI. Raw and processed FotMob files are **not committed** (add `data/*/fotmob/` to `.gitignore`); the pipeline regenerates them.

### C0.1 `scripts/fetch_fotmob.py` (stdlib `urllib` + pandas, like `scripts/fetch_data.py`)
**Constants:**
```python
LEAGUE_ID = 47
BASE = "https://www.fotmob.com"
USER_AGENT = "FPL-Assistant-research/1.0 (personal non-commercial project; github.com/LouaiSf/Fantasy-premier-league-points-prediction)"
MIN_INTERVAL_S = 3.0; TIMEOUT_S = 30; RETRY_BACKOFF_S = (10, 30, 90)   # on 429/5xx; abort run after 3 consecutive failures
```

**Robots check.** At start, run `urllib.robotparser` on `/robots.txt`. Assert `can_fetch(USER_AGENT, url)` for the league URL and one match URL, and abort with a clear message if not allowed.

**League page.** `GET {BASE}/leagues/47/fixtures/premier-league?season=2026-2027` (season format `YYYY-YYYY`). Parse `__NEXT_DATA__` into `props.pageProps.fixtures.allMatches[]`. The fields used are `id`, `round`, `pageUrl` (strip `#…`), `home{id,name}`, `away{id,name}` and `status{utcTime,finished,cancelled}`. Keep only `finished and not cancelled` matches.

**Match page.** `GET {BASE}{pageUrl}` gives `props.pageProps.content.shotmap.shots[]` and `props.pageProps.content.playerStats{}`. Cache pageProps only to `data/<season>/fotmob/raw/match_<id>.json.gz`. An already-cached match is never refetched.

**Team map.** 2026-27 FotMob team id → FPL `teams.csv` name:
```python
FOTMOB_TEAM_TO_FPL = {8678: "Bournemouth", 9825: "Arsenal", 10252: "Aston Villa", 9937: "Brentford",
    10204: "Brighton", 8455: "Chelsea", 8669: "Coventry City", 9826: "Crystal Palace", 8668: "Everton",
    9879: "Fulham", 8667: "Hull City", 9902: "Ipswich Town", 8463: "Leeds", 8650: "Liverpool",
    8456: "Man City", 10260: "Man Utd", 10261: "Newcastle", 10203: "Nott'm Forest",
    8472: "Sunderland", 8586: "Spurs"}
```
For backfill seasons, add missing clubs to the same dict. An unmapped team id raises a hard error that lists the id and name.

**Fixture → GW.** Join each match to `data/<season>/fixtures.csv` on `(team_h, team_a)` FPL ids, which are unique per season. Take `event` as the GW and `id` as the FPL fixture id, and assert that every finished match maps.

**Player stats parsing.** Each `playerStats[pid]` has `{name, id, optaId, teamId, isGoalkeeper, stats:[{title, stats:{<label>:{stat:{value}}}}]}`. Flatten all sections and read these exact English labels into snake_case columns:
`Minutes played, Expected assists (xA), Chances created, Touches in opposition box, Tackles, Blocks, Clearances, Interceptions, Recoveries, Defensive actions, Duels won, Aerial duels won, Dribbled past, Saves, Goals conceded, xGOT faced, Goals prevented, Saves inside box, Fantasy points`.
A missing label is **NaN**, never 0. Players with empty `stats` (unused subs) are skipped.

**Shot parsing.** From `shots[]`, per player per match: `xg = Σ expectedGoals`, `xgot = Σ expectedGoalsOnTarget`, `shots`, `shots_on_target = Σ isOnTarget`, `shots_in_box = Σ isFromInsideBox`, and `goals = count(eventType == "Goal" and not isOwnGoal)`. Exclude own goals throughout. As a cross-check, compare the GK's `Σ expectedGoalsOnTarget` over shots with `keeperId == gk` against the parsed `xGOT faced`. Log a warning when they differ by more than 0.05.

**Player → FPL element mapping**, per match and team:
- Candidates are the `merged_gw.csv` rows for that FPL fixture and team; `name` there is the FPL web_name. Add `first_name second_name` from `players_raw.csv`.
- Normalise names with NFKD, strip accents, lowercase and drop punctuation.
- **Name score** = 1.0 if the full name equals `first second`; 0.95 if FotMob's last token equals the web_name or `second_name`; otherwise `difflib.SequenceMatcher` ratio, accepted if ≥ 0.85.
- **Verification:** `|minutes − fpl_minutes| ≤ 1` and `fantasy_points == total_points`.
- **Method codes and confidence:** `name+minutes+points` = 1.0, `name+minutes` = 0.9, and `minutes+points` = 0.8 when that pair is unique within the team-fixture. Otherwise the player is unmapped.
- Per season, a FotMob player maps to the element chosen most often, and conflicts are reported.
- `data/fotmob_overrides.csv` (`fotmob_player_id,element`, committed) is applied first.
- **Coverage gate:** at least 98% of FotMob minutes must be mapped, otherwise exit code 2 and print the unmapped list.

**Outputs** (`data/<season>/fotmob/`):
- `player_match.csv`: `season, gw, fpl_fixture, fotmob_match_id, fpl_team_id, fotmob_player_id, opta_id, element, map_method, is_gk`, then the label columns, then the shot columns.
- `shots.csv`: one row per shot, with `minute, situation, shot_type, x, y, is_on_target, is_blocked, is_goal, is_own_goal, xg, xgot, keeper_id`.
- `player_map.csv`.

**CLI:** `python scripts/fetch_fotmob.py --season 2026-27 [--backfill 2023-24,2024-25,2025-26] [--max-matches N] [--dry-run]`. A first full season is about 380 × 3 s ≈ 19 min; a weekly incremental run is about 10 matches ≈ 30 s.

**Pipeline.** Add an optional `--with-fotmob` step to `scripts/refresh_pipeline.py` after fetch. It is **non-fatal**: on failure the pipeline continues and reports `fotmob: stale since <date>`. Expose the last FotMob sync time in `/api/platform` as `fotmob_updated_at`.

### C0.2 Tests (no network)
- Commit one trimmed real match pageProps and one trimmed league pageProps as `tests/fixtures/fotmob/*.json`.
- Test: label parsing (missing → NaN), shot aggregation excluding own goals, the GK xGOT cross-check, fixture → GW join, name normalisation (accents such as "Hornícek" and "Groß"), each mapping method, the override precedence, the coverage-gate exit code, and a robots-disallow abort (mock `RobotFileParser`).
- Then commit and push (`data: robots-compliant FotMob match scraper`).

---

## Slice C — Stats Lab page (`/stats`)

**Goal:** surface the underlying numbers FPL managers use to spot regression and hidden value, combining FPL `merged_gw.csv` with FotMob `player_match.csv` (joined on `element, gw`).

### C1. Backend `GET /api/stats/players` (new module `webapp/stats.py`, cached by the mtimes of both files)
Parameters: `gw_from, gw_to, position, min_minutes, sort, preset`. Per player, compute for the window and for the last 4 GWs:
- **Attack:** xG, xGOT, xA, xGI per 90; **G − xG** (finishing vs chance quality); **xGOT − xG** (shot placement; positive = hits the target well); **G − xGOT** (luck vs the keeper); shots, shots in box and touches in the opposition box per 90; chances created per 90; A − xA.
- **Defence:** tackles, interceptions, blocks, clearances and recoveries per 90 (FotMob, separately) and FPL `defensive_contribution` per 90. **DefCon hit rate** is the % of 60+ min appearances reaching the threshold; put the thresholds in one constant and verify them against the official 2026/27 scoring rules (2025/26 used DEF CBIT ≥ 10 and MID/FWD CBIRT ≥ 12 for 2 pts). **DefCon probability next match** = P(Poisson(rate per 90 × expected minutes / 90) ≥ threshold).
- **GK:** saves per 90, save %, **xGOT faced per 90**, **goals prevented** total and per 90, saves inside the box, CS%.
- **Team table:** rolling team xG for/against and xGOT against over 4/6 GWs.
- **Response:** each row carries `sources: ["fpl","fotmob"]`. FotMob fields are `null` (not 0) when a player is unmapped or FotMob is stale. The response also carries `fotmob_updated_at`.
- **Tests:** per-90 math, windowing, min minutes, null-when-unmapped, presets and the Poisson DefCon.

### C2. Frontend `app/stats/page.tsx` plus a "Stats Lab" entry in the nav (and in the phone "More" sheet, V1.1)
1. **Header:** `.display-hero` "STATS LAB"; a caption "Match data: FotMob · FPL official · updated <time>".
2. **Controls:** position tabs (All/GK/DEF/MID/FWD, a white-block selected state), a GW window (`Last 4 | Last 6 | Season | Custom`), min minutes (`90 | 270 | 450`), and a search box.
3. **Presets** as chips above the table, one click each. Each sets `sort` plus its visible columns:

| Preset | Sort / filter |
|---|---|
| Unlucky finishers | xG − G desc, min 3 shots |
| Clinical finishers | xGOT − xG desc |
| DefCon machines | DefCon hit rate desc, DEF/MID |
| Shot-stoppers | goals prevented / 90 desc, GK |
| Busy keepers | xGOT faced / 90 desc, GK (save-point upside) |
| Rising threat | xGI/90 last 4 − season desc |
| Creators without returns | xA − A desc |

4. **Table:** a sticky header and a sticky first column (photo 28px + name + club crest 16px); numbers in `var(--data)` 13px right-aligned; the active sort column header is a white block. Each metric cell gets an inline percentile bar under the number (`transform:scaleX(pct)`, colour `rgba(255,255,255,.28)`, top-10% `var(--lime)`). Show 50 rows with "Show 50 more". It lives in its own horizontal scroll region labelled "Stats table".
5. **Scatter** (V0.4 `Scatter`) above the table, with an axis preset per view: finishers use xG (x) vs G (y) with the diagonal; GKs use xGOT faced/90 (x) vs goals prevented/90 (y); DefCon uses defensive actions/90 (x) vs hit rate (y). Your owned players are `highlight: true`. Clicking a dot opens the player drawer.
6. **Player drawer:** add an "Underlying" slate with `Sparkline`s of per-GW xGI, xGOT and defensive actions (GKs: goals prevented) from a new `GET /api/player/<id>/underlying`.
7. Browser check at 1440 and 375, then commit and push.

---

## Slice V1 — Page-level polish (after C; uses V0 primitives)

Each item lists the exact change. Do them in this order, then run one browser pass over all pages and commit.

1. **Phone navigation (≤760px).** Create `components/chrome/bottom-nav.tsx`: `position:fixed;bottom:0;inset-inline:0;height:calc(64px + env(safe-area-inset-bottom));padding-bottom:env(safe-area-inset-bottom);background:rgba(55,0,60,.97);backdrop-filter:blur(14px);border-top:1px solid rgba(255,255,255,.14);z-index:56`.
   - Five equal items with a 24px inline-SVG icon (stroke 1.75, `currentColor`, defined in `components/chrome/nav-icons.tsx`) and an 11px label: **Team, Transfers, Captain, Chips, More**.
   - The active item gets a white label and a 3px lime blade on top (the same `clip-path` as `.nav-ink`); inactive items are `--muted-light`.
   - **More** opens a bottom sheet (`m.div` from `y:"100%"`, spring `{type:"spring",stiffness:420,damping:40}`, scrim fade 220ms, closes on Escape, scrim tap or route change, with focus trapped) listing Comparison, Watchlist, Fixture Matrix, News Wire and Stats Lab.
   - The squad alert badge shows on More and on the News item.
   - At ≤760px, hide `.nav-scroll` in `main-nav.tsx` (brand, deadline and refresh stay) and add `main{padding-bottom:calc(64px + env(safe-area-inset-bottom))}`.
2. **My Team order and density** (`app/team/page.tsx`):
   - (a) When a squad exists, the lookup collapses into one bar: "Imported: <team name> · GW<n>", with a "Change team" button that expands the current lookup form inline. With no squad, the form stays as today.
   - (b) Hero `max-height:240px` on desktop and 170px at ≤760px. The GW numeral uses `--type-display` rather than `--type-display-xl`, and the five stats use `CountUp`.
   - (c) New order: hero → pitch + rail → deadline board → rank exposure (Slice B) → team plan.
   - (d) In `components/team/team-plan.tsx`, when the recommendation is Hold (zero transfers), **don't render the second pitch**. Render one line, "Suggested XI matches your current XI", plus the armband summary. The suggested pitch appears only when the XI differs.
3. **Captain page** (`app/captain/page.tsx`):
   - Show the availability pill only when `status !== "a"` or `chance < 100`.
   - The hero stat `CLUB` shows the club's full name ("Newcastle"), not its short code.
   - The Form/ICT bars print their value at the bar end, with one caption "Bars scaled to the highest in this list".
   - The shortlist rows use `layout` reorder (V0.2.4) when toggling My squad / All players.
4. **Watchlist:** remove the duplicate "x% owned" text line (keep the pill). When Slice B data exists, the pill shows `EO x% (Top 10k)` and differential filtering uses EO.
5. **Fixture Matrix** (`app/fixtures/page.tsx`):
   - Cell text becomes `700 var(--type-mini) var(--data)` with `color:var(--fdr-ink-N)` matching the cell's FDR.
   - Add a horizon select (4/6/8/12, default 6) and a sort select (Club A–Z | Easiest run | Hardest run), where the run is the sum of FDR over the horizon with blanks counted as 6 and doubles split.
   - The header row and club column are sticky, and a hovered row gets `outline:2px solid var(--white)`.
6. **Transfer Studio:**
   - With an empty draft, the centre column shows a three-step guide (big `ghost-num` 1/2/3 with "Pick an OUT player" / "Pick a same-position IN player" / "Evaluate this draft"), and each step turns lime as it is completed.
   - Disabled buttons become `.btn[disabled]{opacity:1;background:rgba(255,255,255,.08);color:var(--muted-mid);box-shadow:inset 0 0 0 1px rgba(255,255,255,.12)}` (global rule).
   - The evaluation numbers use `CountUp`.
7. **News Wire:**
   - At ≥1200px the league wire becomes `grid-template-columns:repeat(2,minmax(0,1fr))`.
   - Items for your squad come first under a sticky sub-header "Your squad (n)".
   - Tags use `--type-micro`.
8. **Chips:** already rebuilt in A5; just verify the V0 primitives are used there.
9. **Empty and error states:** every `EmptyState` gets an icon (24px from `nav-icons.tsx`), a one-line cause and a primary action (e.g. "Import your team", "Refresh data"). No page shows a bare sentence.
10. **Final pass:** 1440 and 375 across all pages. Check 0 console errors, no page-level horizontal overflow and no text under 11px, and check reduced motion. Update `DESIGN.md` §5 with the bottom nav and the Stats Lab. Commit and push (`ui: phone nav, My Team order, page polish`).

---

## Slice D — Feed the hidden stats into the model (after C, gated by evidence)

1. **Backfill FotMob** for 2023-24, 2024-25 and 2025-26 (`fetch_fotmob.py --backfill …`, about 1 hour one-off). Earlier seasons stay NaN.
2. In the `fpl_pipeline.ipynb` feature cells (run by `scripts/build_features.py`), add player rolling 3/5/10 and prev-1 features for:
   - **FPL columns:** `expected_goals`, `expected_assists`, `expected_goal_involvements`, `expected_goals_conceded`, `clearances_blocks_interceptions`, `tackles`, `recoveries`, `defensive_contribution`, `saves`.
   - **FotMob columns** (joined on `element, GW`): `xgot`, `shots_in_box`, `touches_in_opposition_box`, `chances_created`, `blocks`, `interceptions`, `clearances`, and for GKs `xgot_faced` and `goals_prevented`.
   - **Derived:** rolling `goals − xg` and `xgot − xg`.
3. **Missing-data honesty:**
   - xG exists only from 2022-23, `recoveries` is zero for all rows in 2019-20 to 2024-25 (source gap), and FotMob starts 2023-24. Set these to **NaN**, not 0, before rolling.
   - LightGBM handles NaN; for ElasticNet (the GK/FWD best models) add missing-indicator columns plus median impute.
4. Evaluate with the existing `scripts/ablate.py` / `baselines.py` on the same holdout. Keep the features for a position only if test R² and MAE both improve (current R²: GK 0.43, DEF 0.28, MID 0.34, FWD 0.34). Record the results in `ablation_metrics.json` and the progress file.
5. Retraining is memory-heavy, so run it on Colab (`scripts/make_colab_bundle.py`; the bundle must include `data/*/fotmob/player_match.csv`). Commit the code and metrics, and commit model artefacts only if they improved. Commit and push.

---

## Order, and what "done" means

1. **V0**, the visual foundations. It's small, and every later UI builds on it.
2. **A1 → A6**, the chips. This is the user's top complaint.
3. **B**, effective ownership.
4. **C0**, the FotMob scraper, then **C**, the Stats Lab.
5. **V1**, page polish.
6. **D**, the model; evidence-gated.

Done = each slice's tests pass, `tsc` and `build` pass, one browser pass per changed page at 1440/375 with 0 console errors, no page-level horizontal overflow and no text under 11px, the progress file is updated, and the work is **committed and pushed by the user's account without co-author trailers**.
