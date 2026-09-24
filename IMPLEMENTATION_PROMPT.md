# FPL Assistant Platform — Implementation Prompt

You are implementing improvements to an FPL (Fantasy Premier League) web platform. This is a full-stack app with a Flask/Python backend and a Next.js/React/TypeScript frontend. It predicts player points using ML models and helps users build teams, plan transfers, pick captains, time chips, and track news.

## Your Mission

Read `GRAND_PLAN.md` at the project root — it is your blueprint. It contains 18 tasks across 5 phases. Execute them **in the order specified** (Phase 1 → Phase 5). Each task has a "Problem" section explaining what's wrong and a "What to do" section with exact instructions, file paths, CSS classes to create, and code patterns to follow.

## Before You Start

1. Read `GRAND_PLAN.md` in full. Do not skim it.
2. Read `DESIGN.md` for the broadcast design system specification.
3. Start the backend: `python webapp/app.py` (runs on port 5000).
4. Start the frontend: `cd webapp/frontend && npm run dev` (runs on port 3000).
5. Open `http://localhost:3000` in a browser and explore every page to understand the current state.

## Key Context

**Architecture:**
- Backend: Flask API at `webapp/app.py`, data adapter at `webapp/platform_data.py`, optimizer at `scripts/optimise.py`
- Frontend: Next.js 16 App Router at `webapp/frontend/`, 8 page routes under `app/`
- Design system: `webapp/frontend/app/broadcast.css` — a ~1400-line hand-authored CSS file defining the "broadcast control room" dark theme with PL purple, neon accents, angular blade shapes, and four font families
- State: `webapp/frontend/components/providers/app-provider.tsx` fetches `/api/platform` on mount and provides all data via React context
- Data: 2026-27 season data in `data/2026-27/`, ML predictions in `predictions_next_gw.csv`

**The problems you're fixing (in priority order):**
1. The predictions CSV may not align with the 2026-27 roster — player photos show wrong/old portraits, departed players still appear
2. The Chips and Watchlist pages are entirely inline-styled with emoji icons and JS hover handlers — they look like a different app from the broadcast-styled pages
3. The captain badge looks rough/vibecoded
4. All loading states are plain text with no spinners
5. The error boundary references non-existent CSS classes
6. Navigation hides functionality on tablets
7. Various polish gaps across all pages
8. Dead code (unused shadcn components, dead CSS theme variables)

## Rules — Follow These Strictly

**Data:**
- DO NOT retrain models or rebuild features. Training takes hours on GPU. Use existing trained models in `saved_models/` as-is. Only run the lightweight `scripts/predict_gameweek.py` if predictions need regenerating.
- All displayed data must come from `predictions_next_gw.csv` and `data/2026-27/`. Never hardcode player names, teams, or stats.

**Styling:**
- ALWAYS use the broadcast design system in `broadcast.css`. Add new classes there when needed.
- NEVER use inline `style={{ }}` props for layout, colors, backgrounds, borders, or hover effects. The only acceptable inline styles are truly dynamic values like club-color gradients from `clubStyle()`.
- NEVER use `borderRadius` — the broadcast system uses `clip-path: var(--blade)` for its angular aesthetic.
- NEVER use emoji as icons — use typography-based icons (letters in styled circles) or SVG.
- NEVER use `onMouseEnter`/`onMouseLeave` for hover effects — use CSS `:hover`.
- All new CSS classes go in `broadcast.css`, organized under a section comment matching the component name.

**Code quality:**
- TypeScript strict — no `any`, no `@ts-ignore`, no `// @ts-expect-error`.
- No new npm dependencies unless the plan explicitly calls for one.
- No placeholder comments or TODOs — every change must be complete.
- No deleting functionality that works — improve it.
- Prefer editing existing files over creating new ones (except for the Loading and EmptyState components the plan calls for).

**Commits:**
- Commit after every completed task (or meaningful sub-task). 
- Use clear commit messages describing what was done (e.g., "Rewrite Chips page with broadcast design system").
- Do NOT add co-authored-by lines or attribution. Commit as the repo owner.
- After each commit, append to `PROGRESS.md` at the project root:
  ```
  ## 2026-09-17 — Task X.Y: Short title
  One-line summary of what was done.
  ```

**Testing:**
- After each visual change, verify in the browser at `http://localhost:3000`.
- Check both the changed page AND adjacent pages for regressions.
- Don't write automated browser tests yet — visual verification is sufficient for now.
- Do run `npm run build` in `webapp/frontend/` periodically to catch TypeScript errors.

## Phase-by-Phase Execution

### Phase 1: Data Foundation (Tasks 1, 2)

Start here. The goal is correct data flowing through the system.

**CRITICAL — Data source migration comes first:**

0. **The original data source (`vaastav/Fantasy-Premier-League`) is stuck at GW2.** GW5 deadline is imminent. Switch to `olbauday/FPL-Core-Insights` (https://github.com/olbauday/FPL-Core-Insights) which updates twice daily through GW4+. BUT it has a completely different file structure — see Task 1.0 in `GRAND_PLAN.md` for the full mapping. You must modify `scripts/fetch_data.py` to add an `--source olbauday` mode that downloads from olbauday and converts to vaastav format (the format the rest of the pipeline expects). Download sample CSVs first to inspect actual column names before writing mappings. Then run: `python scripts/fetch_data.py --season 2026-27 --source olbauday --force`

   **CRITICAL `now_cost` unit fix:** The olbauday data stores `now_cost` already in millions (Haaland=15.5) while vaastav stored it in tenths (Haaland=155). The current `data/2026-27/players_raw.csv` has this wrong. During the olbauday→vaastav translation, you MUST multiply `now_cost` by 10: `df['now_cost'] = (df['now_cost'] * 10).round().astype(int)`. Without this fix:
   - `platform_data.py` divides by 10 again, showing all players at 1/10th their real price
   - The ML model receives `value` features ~10x smaller than training range, **corrupting all predictions** (not just display — the model was trained on tenths). This is why Kinsky (a £4.5m GK) appears as the best captain pick — the value-related features are out of distribution.

1. **After fresh data is fetched**, the current `predictions_next_gw.csv` is KNOWN to be stale — it contains relegated teams (Burnley, West Ham, Wolves) while missing promoted teams (Coventry City, Hull City, Ipswich Town). Regenerate: `python scripts/predict_gameweek.py --season 2026-27`. Do NOT retrain or rebuild features.

2. Verify `/api/platform` returns 2026-27 data by hitting `http://127.0.0.1:5000/api/meta` and checking the season field.

3. Fix the prediction merge join in `webapp/app.py` if it joins on `name` instead of `element` (Task 1.4).

4. Fix the model path fallback in `model_summary()` to check both `saved_models/` and `fpl_results/saved_models/` (Task 1.3).

5. Verify player photos load correctly by spot-checking 5-10 player URLs from the 2026-27 data in a browser (Task 2.2).

6. Improve `PlayerPhoto` fallback with error state caching (Task 2.3).

7. Add "NEW" badges for players with `has_prior_history: false` (Task 2.5).

**Commit after Phase 1.**

### Phase 2: Visual Overhaul (Tasks 3, 4, 5, 6, 7)

This is the biggest phase. Take it one task at a time.

**Task 3 — Chips page rewrite:**
- Add all chip CSS classes to `broadcast.css` (the plan gives you exact CSS)
- Rewrite `app/chips/page.tsx` replacing every inline style with broadcast classes
- Replace emoji icons with styled letter circles (TC/BB/FH/WC)
- Style the heatmap table with FDR color classes
- **Commit.**

**Task 4 — Watchlist page rewrite:**
- Add watchlist CSS classes to `broadcast.css` (the plan gives you exact CSS)
- Rewrite `app/watchlist/page.tsx` removing all inline styles and JS hover handlers
- Style player cards with broadcast classes, hover via CSS
- Add responsive breakpoints
- **Commit.**

**Task 5 — Captain badge refinement:**
- Fix the captain badge in `player-marker.tsx` and `broadcast.css`
- Make it a clean gold circle with "C" in display font
- Verify hero section and battle section on the captain page
- **Commit.**

**Task 6 — Loading and empty states:**
- Create `components/loading.tsx` with broadcast spinner
- Create `components/empty-state.tsx` with broadcast styling
- Add CSS classes to `broadcast.css`
- Replace plain-text loading states in ALL 8 pages + player drawer
- Replace inconsistent empty states in Chips, Watchlist, and anywhere else
- **Commit.**

**Task 7 — Error boundary fix:**
- Fix CSS class references in `error-boundary.tsx`
- Use broadcast variables and classes
- **Commit.**

### Phase 3: Polish (Tasks 8–14)

Work through each task. These are smaller, targeted improvements.

- Task 8: Fix nav responsive behavior and crest ticker accessibility. **Commit.**
- Task 9: Enrich player drawer with predicted points, key factors, sparkline. **Commit.**
- Task 10: Team page — formation display, budget validation, bench ordering. **Commit.**
- Task 11: Transfer studio — market list cap, loading feedback, price indicators. **Commit.**
- Task 12: Comparison page — predicted points metric, bar animations, URL encoding. **Commit.**
- Task 13: News page — status badge colors, chance-of-playing indicator, item limit. **Commit.**
- Task 14: Fixtures page — verify 2026-27 data, DGW/BGW indicators. **Commit.**

### Phase 4: Cleanup (Tasks 15, 16, 17)

- Task 15: Remove unused shadcn components (grep to confirm unused first!), clean globals.css, remove unused npm deps, delete default Next.js SVGs. **Commit.**
- Task 16: Backend hardening — error response consistency, graceful degradation, add `prediction_available` and `prediction_timestamp` to platform response. **Commit.**
- Task 17: Performance — lazy loading images, contrast audit, focus-visible styles, reduced-motion support, semantic HTML. **Commit.**

### Phase 5: Verification (Task 18)

Run through the manual smoke test script in the plan. Fix anything that breaks. **Final commit.**

## How to Handle Issues Not in the Plan

If you discover a bug or issue not covered by the plan:
- If it's small (< 10 minutes to fix) and clearly wrong, fix it as part of the nearest related task.
- If it's large, note it in `PROGRESS.md` under a "Discovered Issues" section but do not derail the plan to fix it.
- If it blocks a task (e.g., the backend won't start), fix the blocker first, commit it separately with a clear message, and continue.

## What Success Looks Like

When you're done:
- Every page uses the broadcast design system consistently — dark theme, angular blade shapes, neon accents, no emoji, no inline styles
- Player photos are current 2026-27 portraits from the PL CDN
- Only current PL players appear (no departed players)
- Predicted points from the ML model are visible on Team, Captain, Transfers, Watchlist, Chips, and Player Drawer
- All loading states show a broadcast-styled spinner
- All empty states show a broadcast-styled message
- The platform works at desktop, tablet, and mobile widths
- `PROGRESS.md` documents every completed task
- The git history has clean, descriptive commits for each task
