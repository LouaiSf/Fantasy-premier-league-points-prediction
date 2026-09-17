# FPL Platform — Comprehensive Fix & Elevation Plan

**Date:** 2026-09-14  
**Branch:** `web-platform`  
**Goal:** Fix every broken feature, update to 2026-27 season data, and elevate the platform from prototype to a working product.

---

## PART 1: CRITICAL FIXES (Things that are broken right now)

---

### 1.1 — Season Data Is Stale: Upgrade to 2026-27

**Problem:** The platform runs on a partial 2025-26 snapshot (only GW1-6 and GW8-9 fetched, GW7 missing, GW10-38 never fetched). The 2025-26 season ended May 2026. It is now September 2026 — the 2026-27 season has started. The platform shows last season's players, prices, teams and fixtures.

**What to do:**

1. Run `python scripts/fetch_data.py --season 2025-26 --force --season 2026-27` to:
   - Complete the 2025-26 data (all 38 GWs needed for training)
   - Fetch the new 2026-27 season data (teams, players, fixtures, available GWs)
   
2. Run `python scripts/build_dataset.py` to rebuild `all_seasons_data.csv` with the complete 2025-26 season included.

3. Run `python scripts/build_features.py` to rebuild `all_seasons_data_featured.csv` with full feature engineering. (This is RAM-heavy ~11GB — if local machine can't handle it, use `FPL_Colab.ipynb`.)

4. Run `python scripts/train.py` to retrain models on all data through 2025-26, testing on 2026-27.

5. Run `python scripts/predict_gameweek.py --season 2026-27` to generate fresh `predictions_next_gw.csv` for the current 2026-27 gameweek.

6. Copy the new trained models to `saved_models/direct/` (replacing the old 66-74 feature models).

**Files touched:** `data/2025-26/`, `data/2026-27/` (new), `all_seasons_data.csv`, `all_seasons_data_featured.csv`, `saved_models/direct/`, `predictions_next_gw.csv`

**Verification:** After step 5, start the Flask server and hit `GET /api/meta` — it should return `season: "2026-27"`, a valid `gameweek`, and `prediction_available: true`.

---

### 1.2 — Reconcile the Two Model Directories

**Problem:** Two sets of trained models exist:
- `saved_models/direct/` — older training run, 66-74 features per position, all LightGBM best
- `fpl_results/saved_models/direct/` — newer Colab run, 159-220 features per position, FWD best is ElasticNet

The webapp reads from `saved_models/direct/` (the older, weaker set). The `fpl_results/` models were trained on more features but their predictions file has the wrong league roster (contains Coventry City, Hull City, Ipswich Town — not in the 2025-26 PL).

**What to do:**

After retraining in step 1.1, the root `saved_models/direct/` will have the newest models. Delete or archive `fpl_results/saved_models/` to avoid future confusion. If NOT retraining (doing a quick fix instead), copy `fpl_results/saved_models/` to `saved_models/` BUT you must also regenerate predictions using those models against the correct `data/2025-26` (or `2026-27`) roster — you cannot mix the fpl_results models with the fpl_results predictions file because the roster doesn't match.

**Files touched:** `saved_models/direct/`, `fpl_results/saved_models/` (delete/archive)

---

### 1.3 — Auto-Pick Returns Players Without Images

**Problem:** When auto-pick (`POST /api/squad`) returns players, many render as blank circles on the pitch. The `PlayerPhoto` component hides the `<img>` on CDN 404 (`visibility: hidden`), showing just the club-gradient background. The CSS defines a `.photo-fb` class (broadcast.css lines 203-210) with gradient + initials styling, but NO React component ever uses it.

**What to do:**

1. **In `webapp/frontend/components/player-photo.tsx`:** On image error, instead of just hiding the image, render a fallback `<span className="photo-fb">` containing the player's initials (first letter of first name + first letter of last name). Accept a `name` prop for this.

2. **Update every call site** that uses `<PlayerPhoto>` to pass the player's `name` or `web_name`:
   - `components/team/player-marker.tsx` — already has `p.name`
   - `components/player-drawer.tsx` — has player data
   - `app/transfers/page.tsx` — has player data in slot rendering
   - `app/comparison/page.tsx` — has player data in plinth rendering
   - `app/captain/page.tsx` — has player data

3. **The initials extraction:** Split name by space, take first char of first and last segments: `"Bryan Mbeumo" → "BM"`, `"Mohamed Salah" → "MS"`. For single-word names, just use the first character.

**Files touched:** `components/player-photo.tsx`, `components/team/player-marker.tsx`, `components/player-drawer.tsx`, `app/transfers/page.tsx`, `app/comparison/page.tsx`, `app/captain/page.tsx`

---

### 1.4 — Badge / Flag Positioning Broken at Mobile Widths

**Problem:** In `broadcast.css`, the captain badge (`.pm-badge`) and availability flag (`.pm-flag`) positions don't adjust at the 560px breakpoint. When `.pm-bust` shrinks to 40x40px:
- `.pm-badge` at `right:6px; top:-3px` overflows and can overlap adjacent markers
- `.pm-flag` at `right:6px; top:44px` sits BELOW the 40px bust, overlapping the name strip
- `.pm-pred` at `left:4px; top:2px` overlaps the narrower bust

**What to do:**

In `broadcast.css`, inside the `@media(max-width:560px)` block (around line 1197), add responsive adjustments:

```css
.pm-badge { right: 2px; top: -2px; width: 18px; height: 18px; font-size: 10px; }
.pm-flag  { right: 2px; top: 30px; width: 18px; height: 18px; font-size: 10px; }
.pm-pred  { left: 2px; top: 0;    font-size: 10px; min-width: 24px; padding: 1px 4px; }
```

Also check the 860px breakpoint — `.pm-flag` position (`top:44px`) needs adjustment there too since `.pm-bust` is 52x52px at that width: `top:44px` just barely works but should be `top:38px` to sit at the bottom of the bust, not below it.

**Files touched:** `webapp/frontend/app/broadcast.css`

---

### 1.4b — Captain Page Armband Drifts Off Sleeve at Smaller Viewports

**Problem:** The `.armband-ring` on the captain hero portrait is positioned with `left:49%; top:59%; width:20%; height:8%` relative to `.cap-shot`. There are three breakpoint issues:

1. **At `max-width:860px`:** `.cap-shot` changes to `width:52%; height:74%` and the armband adjusts to `left:47%; width:24%; height:9%` — acceptable but the ring sits slightly too far right on shorter portraits.
2. **At `max-width:560px`:** `.cap-shot` shrinks drastically to `width:66%; right:-12%; height:56%; opacity:.85` but there is **NO `.armband-ring` adjustment at all** for this breakpoint. The ring keeps its 860px coordinates, which places it completely off the visible sleeve area — it either floats in empty space or clips outside the container.
3. **Player photo variance:** The percentage positioning assumes a roughly consistent arm position across all player photos, but PL CDN portraits vary in crop and pose. Some players have the armband landing on the chest or shoulder instead of the upper arm.

**What to do:**

1. **Add a 560px breakpoint rule for `.armband-ring`** in `broadcast.css` (after the existing 860px rule around line 1390):

```css
@media (max-width:560px) {
  .armband-ring { left: 44%; top: 54%; width: 28%; height: 11%; }
}
```

These values account for the wider, shorter `.cap-shot` at phone width — the ring should be proportionally larger and shifted left/up to remain on the visible portion of the portrait.

2. **Alternatively (more robust):** Anchor the armband to the bottom-center of `.cap-shot` instead of a mid-body percentage. The bottom of the portrait is always the player's torso, making `bottom: 30%; left: 46%` more reliable across different photo crops than `top: 59%`. This requires changing the default positioning from `top` to `bottom`:

```css
.armband-ring {
  position: absolute;
  left: 46%;
  bottom: 30%;
  z-index: 3;
  width: 20%;
  height: 8%;
  /* ... rest unchanged ... */
}
```

Then adjust `bottom` values at each breakpoint instead of `top`, since the bottom edge of 250x250 portraits is consistently at waist/torso level.

3. **In the captain page JSX** (`app/captain/page.tsx` line 63): The `<span className="armband-ring">` currently sits as a sibling to the `<PlayerPhoto>` inside `.cap-shot`. That's correct — keep it as a positioned child of `.cap-shot` so all percentage coordinates are relative to the portrait container.

**Files touched:** `webapp/frontend/app/broadcast.css` (add 560px rule, optionally refactor to bottom-anchoring)

---

### 1.5 — Teams Don't Get Saved Properly

**Problem:** Squad is stored in `localStorage` as an array of player NAME strings (`"fpl-assistant-squad"` key). Issues:
- Names change between seasons (spelling corrections, accents) → players silently drop
- No cross-device sync
- No season key → switching seasons silently wipes the squad
- No budget validation on restore
- `setTeamResult(null)` on every name change forces re-running the optimizer to get XI/bench split

**What to do:**

1. **Store by element ID, not name.** In `app-provider.tsx`:
   - Change the localStorage format from `string[]` (names) to `{ season: string, ids: number[] }`.
   - On load, validate IDs against the snapshot's player list. If the season doesn't match, clear the stored squad and show a toast: "New season — please rebuild your squad."
   - Keep a migration path: if `localStorage` contains a plain `string[]` (old format), convert it to the new format by looking up each name in the current snapshot.

2. **Add budget validation on restore.** After loading IDs from storage, compute total value. If it exceeds 100.0, show a toast warning: "Squad over budget (£X.Xm) — prices may have changed."

3. **Persist the teamResult alongside squad names.** Store `{ season, ids, formation, captainId }` so the XI/bench split and captain survive a page reload without re-running the optimizer.

**Files touched:** `webapp/frontend/components/providers/app-provider.tsx`, `webapp/frontend/lib/types.ts` (add StoredSquad type)

---

### 1.6 — "Run Full Analysis" Is Broken in Transfer Studio

**Problem:** The "Run full analysis" button in `app/transfers/page.tsx` (line ~133-138) is disabled when predictions are unavailable. Since the predictions file was incompatible with the data snapshot, the API reports `prediction_available: false` and the button stays permanently disabled.

**What to do:**

This is fixed by 1.1 (getting valid predictions). But also add a visible explanation:

1. In `app/transfers/page.tsx`, when `!snapshot.prediction_available`, show a message below the button: "Predictions unavailable — run the prediction pipeline to enable analysis" instead of just a greyed-out button with no explanation.

2. Same treatment for the auto-pick button in `app/team/page.tsx` — when predictions are unavailable, show why it's disabled.

**Files touched:** `webapp/frontend/app/transfers/page.tsx`, `webapp/frontend/app/team/page.tsx`

---

### 1.7 — Crest Images Have No Error Handling

**Problem:** Club crest images use `<img src={crestUrl(code)}>` throughout the app with zero `onError` handling. If a crest URL 404s (new club, CDN issue), a broken image icon appears. This affects:
- `components/chrome/crest-ticker.tsx`
- `app/fixtures/page.tsx`
- `app/news/page.tsx`
- `app/comparison/page.tsx`
- `components/player-drawer.tsx`
- `components/team/player-marker.tsx`

**What to do:**

Create a `<ClubCrest>` component (similar pattern to `PlayerPhoto`) that:
- Renders `<img src={crestUrl(code, size)} ...>`
- On error, hides the image and shows a fallback: the club's `short_name` (3 letters) in a small circle with the club's gradient colors from `club-colors.ts`
- Replace all bare `<img src={crestUrl(...)}` throughout the app with `<ClubCrest>`

**Files touched:** New `components/club-crest.tsx`, then update all 6 files listed above.

---

### 1.8 — Club Colors Missing for New/Changed Clubs

**Problem:** `lib/club-colors.ts` has a hardcoded 20-club map. When clubs get promoted/relegated, new clubs render with grey fallback `["#555", "#111"]`. For 2026-27, the promoted clubs won't have colors.

**What to do:**

1. **Make club colors dynamic.** Add a `club_colors` field to the `/api/platform` response in `webapp/platform_data.py`. Build the color map server-side from `teams.csv` data (team code → known PL colors). Keep the current `club-colors.ts` map as a client-side fallback, but expand it to cover ALL clubs that have ever been in the PL (at least 30+ clubs). The map is small — adding 15 more entries costs nothing.

2. **At minimum (quick fix):** Expand the hardcoded map in `club-colors.ts` to include every club likely to appear in 2026-27. Add at least: Leicester (`#003090`, `#FDBE11`), Ipswich (`#0033A0`, `#ED1A3B`), Southampton (`#D71920`, `#FFFFFF`), Luton (`#F78F1E`, `#002D62`), Burnley (`#6C1D45`, `#99D6EA`), Leeds (`#1D428A`, `#FFCD00`), Sunderland (`#EB172B`, `#000000`), Coventry (`#6CADDF`, `#003DA5`), Sheffield United (`#EE2737`, `#000000`), Middlesbrough (`#E11B22`, `#FFFFFF`), etc. — any club that could plausibly appear in the PL.

**Files touched:** `webapp/frontend/lib/club-colors.ts`

---

### 1.9 — Inconsistent Photo Sizes Between API Endpoints

**Problem:** Two different photo URL sizes:
- `webapp/platform_data.py` line 204: `250x250` (used by `/api/platform`)
- `webapp/app.py` line 335: `110x140` (used by `/api/players`)

If front-end code ever mixes data from both endpoints, photos could be different aspect ratios.

**What to do:**

Standardize on `250x250` everywhere. In `webapp/app.py` line ~334, change:
```python
f"https://resources.premierleague.com/premierleague/photos/players/110x140/p{int(code)}.png"
```
to:
```python
f"https://resources.premierleague.com/premierleague/photos/players/250x250/p{int(code)}.png"
```

**Files touched:** `webapp/app.py`

---

### 1.10 — NameError Bug in `suggest_transfers()`

**Problem:** In `scripts/optimise.py` line ~360, the function `suggest_transfers()` references `rows` which is not defined. It should be `data['rows']`:
```python
best = max(rows, key=lambda r: r['net'])  # BUG: 'rows' undefined
```

The web API is unaffected (it calls `compute_transfers()` directly), but the CLI `suggest_transfers` subcommand crashes every time.

**What to do:**

Change `rows` to `data['rows']` on that line:
```python
best = max(data['rows'], key=lambda r: r['net'])
```

**Files touched:** `scripts/optimise.py`

---

### 1.11 — `SystemExit` Used for Error Handling

**Problem:** In `webapp/app.py` line ~144, `squad_from_names()` raises `SystemExit` for duplicate player errors. `SystemExit` is a base exception that can kill the Flask process. While it's caught in `api_transfers()` and `api_chips()`, any uncaught instance terminates the server.

**What to do:**

Change `raise SystemExit(...)` to `raise ValueError(...)` in `squad_from_names()`. The `except` blocks in `api_transfers()` and `api_chips()` should catch `(ValueError, KeyError)` instead of `(SystemExit, KeyError)`.

**Files touched:** `webapp/app.py`

---

## PART 2: IMPORTANT IMPROVEMENTS (Elevating the Platform)

---

### 2.1 — Add a React Error Boundary

**Problem:** No error boundary exists. Any component render crash = white screen with no recovery.

**What to do:**

Create `webapp/frontend/components/error-boundary.tsx` — a class component (error boundaries must be class components in React) that catches render errors and shows a styled fallback: "Something went wrong" with a "Reload" button. Wrap the app's `{children}` in `app/layout.tsx` with this boundary.

**Files touched:** New `components/error-boundary.tsx`, `app/layout.tsx`

---

### 2.2 — Add a "Refresh Data" Button in the Webapp

**Problem:** To update data, you must manually run CLI scripts. There's no way to trigger a data refresh from the webapp itself. The `/api/reload` endpoint exists but only re-reads the existing `predictions_next_gw.csv` — it doesn't fetch new data.

**What to do:**

1. **Add `POST /api/refresh` endpoint** in `webapp/app.py` that:
   - Calls `scripts/fetch_data.py --season <current_season>` as a subprocess
   - Then calls `scripts/predict_gameweek.py --season <current_season>` to regenerate predictions
   - Then triggers the existing `reload_predictions()` to pick up the new file
   - Returns progress/status (or at minimum, success/failure)

2. **Add a refresh button** in the MainNav or in a settings dropdown. Show a spinner while refreshing. Show a toast on completion.

3. **Auto-staleness detection:** In `/api/meta`, add the `mtime` of `predictions_next_gw.csv` as `predictions_updated_at`. The frontend can show "Predictions last updated: 3 days ago" and suggest a refresh if stale (>24h).

**Files touched:** `webapp/app.py`, `webapp/frontend/components/chrome/main-nav.tsx`

---

### 2.3 — Make the Deadline Clock Accurate for 2026-27

**Problem:** The `DeadlineClock` component counts down to the earliest kickoff in the current gameweek. But if the fixtures data is stale (still showing 2025-26), the clock shows a deadline that already passed.

**What to do:**

This is mostly fixed by 1.1 (fresh data). But also:

1. **In `deadline-clock.tsx`:** If the computed deadline is in the past, show "GW[N] — In Progress" or "GW[N] — Deadline Passed" instead of a negative countdown.

2. **Handle the off-season gracefully:** If there are no future fixtures (off-season), show "Season starts [date]" instead of a broken countdown.

**Files touched:** `webapp/frontend/components/chrome/deadline-clock.tsx`

---

### 2.4 — Player Drawer: Add Per-Gameweek History

**Problem:** The player drawer shows season aggregate stats but no per-gameweek breakdown. The prototype's "last 5 GW" ladder was omitted because the single-snapshot data doesn't carry it. But `data/<season>/gws/merged_gw.csv` HAS per-gameweek data.

**What to do:**

1. **In `webapp/platform_data.py`:** Add a function `player_history(element_id)` that reads `data/<season>/gws/merged_gw.csv` and returns the player's last 5-8 gameweek rows (points, minutes, goals, assists, bonus, opponent, was_home).

2. **Add `GET /api/player/<element_id>/history` endpoint** in `webapp/app.py` that calls this function.

3. **In `player-drawer.tsx`:** Fetch history when the drawer opens. Render a mini-table or sparkline of recent GW points, styled with the broadcast design system's `.stable` table class.

**Files touched:** `webapp/platform_data.py`, `webapp/app.py`, `webapp/frontend/components/player-drawer.tsx`

---

### 2.5 — Transfer Studio: Show Player Images in Desk Lists

**Problem:** The transfer desks (out/in player lists) show player rows but the photo thumbnails can be blank (same CDN 404 issue as auto-pick). Combined with fix 1.3 (initials fallback), this will look much better — but also improve the desk row rendering.

**What to do:**

1. Apply the `PlayerPhoto` fix from 1.3 (initials fallback) — this propagates to desk rows automatically since they already use `PlayerPhoto`.

2. **In the desk row rendering** (`app/transfers/page.tsx`), ensure the club crest mini-badge (`.badge-mini`) positioned at `left:-4px; bottom:2px` on slot photos also gets the error-handling treatment from fix 1.7.

**Files touched:** Already covered by 1.3 and 1.7

---

### 2.6 — Fixture Matrix: Handle Gameweek Overflow

**Problem:** The fixture matrix generates 8 gameweeks starting from the current GW: `Array.from({ length: 8 }, (_, i) => startGw + i)`. If the current GW is 35+, this generates GW39-42 which don't exist — those columns show as empty.

**What to do:**

In `app/fixtures/page.tsx`, cap the gameweek range at 38:
```typescript
const gameweeks = Array.from({ length: 8 }, (_, i) => startGw + i).filter(gw => gw <= 38);
```

If fewer than 3 gameweeks remain, show a "Season ending soon" message instead of a mostly-empty grid.

**Files touched:** `webapp/frontend/app/fixtures/page.tsx`

---

### 2.7 — Production API Base URL

**Problem:** `lib/api.ts` line 9 hardcodes fallback to `http://127.0.0.1:5000`. No production URL is configured. Deployment requires manually setting `NEXT_PUBLIC_API_BASE`.

**What to do:**

1. **Add a `.env.local.example` file** in `webapp/frontend/` documenting the required env var:
   ```
   NEXT_PUBLIC_API_BASE=http://127.0.0.1:5000
   ```

2. **In `lib/api.ts`:** Add a runtime check — if `NEXT_PUBLIC_API_BASE` is not set and `window.location.hostname !== 'localhost'` and `!== '127.0.0.1'`, log a warning to the console.

3. **In `next.config.ts`:** Add `images.remotePatterns` for `resources.premierleague.com` so `next/image` can be used in the future.

**Files touched:** `webapp/frontend/lib/api.ts`, `webapp/frontend/next.config.ts`, new `webapp/frontend/.env.local.example`

---

### 2.8 — Delete v1 Jinja/Vanilla-JS Files

**Problem:** The old v1 frontend (`webapp/templates/`, `webapp/static/`, Jinja page routes) is still in place. All 7 surfaces have been rebuilt in Next.js. The v1 code is dead weight and confusing.

**What to do:**

1. Delete `webapp/templates/` directory entirely.
2. Delete `webapp/static/` directory entirely.
3. In `webapp/app.py`, remove the Jinja page routes:
   - Remove `render_template` import
   - Remove the `index()` route (`@app.route('/')`)
   - Remove the `platform_page()` route (`@app.route('/<page>')`)
   - Remove the `favicon()` route (Next.js serves its own)
   - Keep ALL `/api/*` routes untouched
4. Remove `Flask`'s `template_folder` and `static_folder` config if set.

**Files touched:** `webapp/app.py`, delete `webapp/templates/`, delete `webapp/static/`

---

### 2.9 — Watchlist / Differentials Surface

**Problem:** The backend has a fully working `/api/watchlist` endpoint (best value picks, overpriced players, differentials, no-history flags) but there is NO frontend page for it. This is free value — the optimizer already computes everything.

**What to do:**

Create `webapp/frontend/app/watchlist/page.tsx`:
- Add "Watchlist" as a 7th tab in `main-nav.tsx` (between Fixture Matrix and an appropriate position)
- Four sections matching the API response:
  1. **Best Value** — top points-per-million players, rendered as ranked cards
  2. **Differentials** — low-ownership gems (< 10% ownership), great for mini-league advantage
  3. **Overpriced** — premium players not delivering relative to cost
  4. **No History** — flagged players where predictions are unreliable (new signings, etc.)
- Each card shows: player photo (with fallback), name, team crest, position, price, predicted points, ownership %, points-per-million
- Clicking a player opens the existing player drawer

**Files touched:** New `app/watchlist/page.tsx`, `components/chrome/main-nav.tsx` (add tab)

---

### 2.10 — Chip Advisor Surface

**Problem:** The backend has a fully working `/api/chips` endpoint (Triple Captain, Bench Boost, Free Hit, Wildcard timing advisor based on fixture analysis) but there is NO frontend page for it.

**What to do:**

Create `webapp/frontend/app/chips/page.tsx`:
- Add "Chip Advisor" as an 8th tab in `main-nav.tsx`
- Show the fixture calendar heatmap (reuse FDR color coding from fixtures page)
- Four chip recommendation cards:
  1. **Triple Captain** — best GW and recommended player
  2. **Bench Boost** — best GW based on fixture density
  3. **Free Hit** — blank/double GW analysis
  4. **Wildcard** — current squad vs optimal squad value gap
- Each card shows: recommended GW, reasoning (fixture count, difficulty), confidence level
- The user can input their current squad (auto-populated from saved squad) and horizon (default 8 GWs)
- Requires predictions to be available; show explanation when disabled

**Files touched:** New `app/chips/page.tsx`, `components/chrome/main-nav.tsx` (add tab)

---

## PART 3: DATA PIPELINE FIXES

---

### 3.1 — Complete the Data Pipeline End-to-End

**Problem:** The data pipeline exists in scripts but has gaps and the fpl_results/ directory contains a stale/incompatible output.

**What to do (in order):**

```bash
# 1. Fetch complete 2025-26 + new 2026-27 data
python scripts/fetch_data.py --season 2025-26 --force --season 2026-27

# 2. Rebuild the merged dataset
python scripts/build_dataset.py

# 3. Build features (RAM-heavy, use Colab if needed)
python scripts/build_features.py

# 4. Train models
python scripts/train.py

# 5. Generate predictions for current 2026-27 gameweek
python scripts/predict_gameweek.py --season 2026-27

# 6. Verify
python -c "import pandas as pd; df = pd.read_csv('predictions_next_gw.csv'); print(f'{len(df)} players, teams: {df.team.unique()}')"
```

After this, the webapp should show current 2026-27 data with working predictions.

---

### 3.2 — Archive fpl_results/ Properly

**Problem:** `fpl_results/` contains Colab output with an incompatible predictions file (different league roster) and model artifacts. It creates confusion about which is the "real" model set.

**What to do:**

1. After retraining, the root `saved_models/` is authoritative. 
2. Keep `fpl_results/model_metrics.json` and `fpl_results/baseline_metrics.json` as reference.
3. Delete `fpl_results/predictions_next_gw.csv` (it's stale and incompatible).
4. Delete `fpl_results/saved_models/` (superseded by root).
5. Add `fpl_results/` to `.gitignore` since it's a Colab output directory, not a source-of-truth.

**Files touched:** `fpl_results/`, `.gitignore`

---

## PART 4: QUICK WINS (Small fixes, big impact)

---

### 4.1 — Show "Predictions Unavailable" Explanations

Anywhere the UI disables a feature because predictions aren't loaded, add a visible message explaining why and what to do. Currently: auto-pick button, transfer analysis button, captain rankings, watchlist.

### 4.2 — Toast Improvements

The toast auto-dismisses after 2800ms with no manual dismiss. Add an "×" close button and support queuing (new toast waits for current one to finish instead of replacing it). In `app-provider.tsx` lines 88-99.

### 4.3 — Delete Dead Code

- `components/coming-soon.tsx` — never imported anywhere
- 12 of 13 shadcn/ui components (`button`, `tabs`, `select`, `switch`, `badge`, `scroll-area`, `separator`, `input`, `textarea`, `dialog`, `input-group`, `command`) — only `tooltip` is actually used. Delete unused ones, or keep them if the new surfaces (watchlist, chips) will use them.

### 4.4 — Fix Unclosed File Handles

In `webapp/app.py` lines ~111 and ~281:
```python
# Change this:
meta = json.load(open(meta_path, encoding='utf-8'))
# To this:
with open(meta_path, encoding='utf-8') as f:
    meta = json.load(f)
```

### 4.5 — Auto-Refresh Predictions on File Change

In `webapp/app.py`, `reload_predictions()` stores `mtime` but never checks it. Add an `mtime` check to `state()` — if the file's mtime has changed since last load, automatically reload. This way, running `predict_gameweek.py` while the server is up immediately reflects in the webapp without needing to `POST /api/reload`.

```python
def state():
    s = _state
    if not s or ('mtime' in s and os.path.getmtime(PRED_PATH) != s['mtime']):
        return reload_predictions()
    return s
```

### 4.6 — Improve the `hasattr(opt, 'read_csv_tolerant')` Guard

In `webapp/app.py` line ~299, the `hasattr` check for `read_csv_tolerant` is dead code — this function doesn't exist in `optimise.py`. Remove the guard and just use `pd.read_csv()` directly.

---

## PART 5: IMPLEMENTATION PRIORITY ORDER

For Sonnet to implement in this order:

### Phase 1 — Make It Work (do first)
1. **1.1** — Fetch 2026-27 data (run pipeline scripts)
2. **1.2** — Reconcile model directories  
3. **1.10** — Fix NameError in optimise.py
4. **1.11** — Fix SystemExit error handling
5. **1.9** — Standardize photo sizes
6. **1.6** — Enable full analysis (data fix makes this work)
7. **4.5** — Auto-refresh predictions on file change
8. **4.4** — Fix unclosed file handles
9. **4.6** — Remove dead hasattr guard

### Phase 2 — Make It Look Right
10. **1.3** — Player photo initials fallback
11. **1.7** — Crest error handling
12. **1.4** — Badge/flag mobile positioning
13. **1.4b** — Captain armband 560px drift fix (anchor to bottom of portrait)
13. **1.8** — Expand club colors map
14. **2.1** — React error boundary
15. **2.3** — Deadline clock edge cases

### Phase 3 — Make It Better
16. **1.5** — Squad persistence by ID with season key
17. **2.4** — Player drawer per-GW history
18. **2.2** — Refresh data button from webapp
19. **2.6** — Fixture matrix GW overflow cap

### Phase 4 — Elevate
20. **2.8** — Delete v1 Jinja files
21. **2.9** — Watchlist / Differentials page
22. **2.10** — Chip Advisor page
23. **4.2** — Toast improvements
24. **4.3** — Delete dead code
25. **2.7** — Production API base URL

---

## APPENDIX: File Map

| Area | Key Files |
|------|-----------|
| Flask API | `webapp/app.py` (522 lines) |
| Data adapter | `webapp/platform_data.py` (221 lines) |
| Optimizer | `scripts/optimise.py` (747 lines) |
| Predictions | `scripts/predict_gameweek.py` |
| Data fetch | `scripts/fetch_data.py` |
| Frontend root | `webapp/frontend/app/layout.tsx` |
| App provider | `webapp/frontend/components/providers/app-provider.tsx` |
| Player photo | `webapp/frontend/components/player-photo.tsx` |
| Player marker | `webapp/frontend/components/team/player-marker.tsx` |
| Player drawer | `webapp/frontend/components/player-drawer.tsx` |
| Club colors | `webapp/frontend/lib/club-colors.ts` |
| API client | `webapp/frontend/lib/api.ts` |
| Types | `webapp/frontend/lib/types.ts` |
| Design system | `webapp/frontend/app/broadcast.css` (1392 lines) |
| Main nav | `webapp/frontend/components/chrome/main-nav.tsx` |
| Deadline clock | `webapp/frontend/components/chrome/deadline-clock.tsx` |
| Team page | `webapp/frontend/app/team/page.tsx` |
| Transfers page | `webapp/frontend/app/transfers/page.tsx` |
| Comparison page | `webapp/frontend/app/comparison/page.tsx` |
| Captain page | `webapp/frontend/app/captain/page.tsx` |
| News page | `webapp/frontend/app/news/page.tsx` |
| Fixtures page | `webapp/frontend/app/fixtures/page.tsx` |
| Predictions CSV | `predictions_next_gw.csv` (root) |
| Models | `saved_models/direct/{GK,DEF,MID,FWD}/` |
| Season data | `data/2025-26/`, `data/2026-27/` |
| Colab output | `fpl_results/` (stale, to archive) |
