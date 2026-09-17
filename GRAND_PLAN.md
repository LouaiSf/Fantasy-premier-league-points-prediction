# FPL Assistant Platform — Grand Implementation Plan

**Version:** 1.0  
**Date:** 2026-09-17  
**Purpose:** This document is the single source of truth for bringing the FPL Assistant web platform from its current prototype state to production readiness. It is written to be self-contained — any agent reading this can pick up a section and implement it without needing additional context.

**Commit discipline:** After completing each numbered task (or a meaningful sub-task within one), create a git commit with a clear message describing what was done. Do NOT use `--co-authored-by` or attribution lines. Commit as the repo owner (Yahia Kerroum). After committing, append a short entry to `PROGRESS.md` at the project root (create it if it doesn't exist) with the date, task number, and a one-line summary of what was done.

**General rules for all work:**
- Never delete functionality that exists and works. Improve it.
- Never add placeholder/TODO comments. Every change should be complete.
- Use the existing broadcast design system in `webapp/frontend/app/broadcast.css` — do NOT create a parallel design system or use inline styles.
- All data displayed must come from the model predictions in `predictions_next_gw.csv` and the 2026-27 season data in `data/2026-27/`. Never hardcode player names, team names, or stats.
- Test changes by running the Flask backend (`python webapp/app.py`) and the Next.js frontend (`cd webapp/frontend && npm run dev`) and visually verifying.
- Do not introduce new npm dependencies unless absolutely necessary and explicitly called for.
- Keep TypeScript strict — no `any` types, no `@ts-ignore`.
- **DO NOT retrain models or rebuild features.** Training and feature engineering are extremely time-consuming (hours on GPU). Use the existing trained models in `saved_models/` (or `fpl_results/saved_models/`) as-is. Only run the lightweight prediction step (`scripts/predict_gameweek.py`) which takes seconds. If the predict script fails, debug the script itself — do not fall back to retraining.

---

## TABLE OF CONTENTS

1. [Data Pipeline & Model Integration](#1-data-pipeline--model-integration)
2. [Player Data Accuracy (Photos, Rosters, Transfers)](#2-player-data-accuracy)
3. [Visual Overhaul — Chips Page](#3-visual-overhaul--chips-page)
4. [Visual Overhaul — Watchlist Page](#4-visual-overhaul--watchlist-page)
5. [Visual Overhaul — Captain Page (Badge & Polish)](#5-visual-overhaul--captain-page)
6. [Loading States & Empty States](#6-loading-states--empty-states)
7. [Error Boundary Fix](#7-error-boundary-fix)
8. [Navigation & Responsive Fixes](#8-navigation--responsive-fixes)
9. [Player Drawer Enrichment](#9-player-drawer-enrichment)
10. [Team Page Polish](#10-team-page-polish)
11. [Transfer Studio Polish](#11-transfer-studio-polish)
12. [Comparison Page Polish](#12-comparison-page-polish)
13. [News Page Polish](#13-news-page-polish)
14. [Fixtures Page Polish](#14-fixtures-page-polish)
15. [Dead Code Cleanup](#15-dead-code-cleanup)
16. [Backend Hardening](#16-backend-hardening)
17. [Performance & Accessibility](#17-performance--accessibility)
18. [End-to-End Smoke Tests](#18-end-to-end-smoke-tests)

---

## 1. Data Pipeline & Model Integration

### Problem
The platform does not properly use the ML model's output from `fpl_results/`. The `predictions_next_gw.csv` at the project root may be stale or generated against an older season's roster. The `fpl_results/saved_models/` directory contains trained models but the webapp reads from `saved_models/` (root level). The predictions must match the 2026-27 roster in `data/2026-27/players_raw.csv` (616 players).

**CRITICAL DATA SOURCE ISSUE:** The original data source (`vaastav/Fantasy-Premier-League`) is stuck at GW2 of the 2026-27 season. The GW5 deadline is imminent. We must switch to a new, actively-maintained data source: **`olbauday/FPL-Core-Insights`** (https://github.com/olbauday/FPL-Core-Insights), which updates twice daily and has data through GW4.

However, the olbauday repo has a **completely different structure** from vaastav. The rest of our pipeline (build_dataset, predict_gameweek, platform_data, app.py) all expect the vaastav format. The solution is a **translation layer** — fetch from olbauday, convert to vaastav format, save to our local `data/2026-27/` directory.

### What to do

**1.0 — Switch data source: Modify `scripts/fetch_data.py` to support olbauday**

The current `fetch_data.py` downloads from `vaastav/Fantasy-Premier-League`. Add support for `olbauday/FPL-Core-Insights` as an alternative source with a `--source` flag.

**olbauday repo structure (differs from vaastav):**
```
data/2026-2027/                          ← note: "2026-2027" not "2026-27"
  players.csv                            ← season-level player list
  teams.csv                              ← season-level team list  
  playerstats.csv                        ← cumulative player stats ("equivalent of FPL API Data")
  gameweek_summaries.csv
  By Gameweek/                           ← note: space in dir name
    GW1/
      fixtures.csv
      matches.csv
      player_gameweek_stats.csv          ← per-GW player stats (non-cumulative)
      playerstats.csv                    ← cumulative stats up to this GW
      playermatchstats.csv
      players.csv                        ← player list snapshot at end of GW
      teams.csv
      momentum.csv
      shots.csv
      xg_by_minute.csv
    GW2/
    ...
    GW38/
```

**Raw URL pattern:**
```
https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/main/data/2026-2027/players.csv
https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/main/data/2026-2027/teams.csv
https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/main/data/2026-2027/By%20Gameweek/GW4/player_gameweek_stats.csv
```

**Translation strategy — download from olbauday, produce vaastav-format files:**

The goal is to produce these files in `data/2026-27/` (our local format):
- `players_raw.csv` — from olbauday's season-root `playerstats.csv` (or latest GW's `players.csv`)
- `teams.csv` — from olbauday's season-root `teams.csv` (may need column mapping)
- `fixtures.csv` — from olbauday's latest GW `fixtures.csv` (may need column mapping)
- `gws/merged_gw.csv` — built by concatenating olbauday's `player_gameweek_stats.csv` from each GW folder
- `gws/gw{N}.csv` — from olbauday's per-GW `player_gameweek_stats.csv`

**Column mapping (olbauday → vaastav):**

You MUST investigate the actual column names in olbauday's CSVs before writing the mapping. Download a sample of each file and compare columns to what our pipeline expects. Key fields our pipeline needs:

For `players_raw.csv` (what `platform_data.py` reads):
- `id` (element/player ID), `code` (permanent player code, used for photo URLs), `first_name`, `second_name`, `web_name`, `team` (team ID), `element_type` (1=GK,2=DEF,3=MID,4=FWD), `now_cost` (price in tenths), `status`, `news`, `form`, `total_points`, `minutes`, `goals_scored`, `assists`, `clean_sheets`, `bonus`, `bps`, `ict_index`, `expected_goals`, `expected_assists`, `selected_by_percent`, `transfers_in_event`, `transfers_out_event`, `chance_of_playing_next_round`

For `teams.csv`:
- `id`, `name`, `short_name`, `code`, `strength`

For `fixtures.csv`:
- `event` (GW number), `team_h`, `team_a`, `team_h_difficulty`, `team_a_difficulty`, `finished`, `kickoff_time`

For `gws/merged_gw.csv`:
- `element`, `name`, `opponent_team`, `total_points`, `was_home`, `minutes`, `goals_scored`, `assists`, `clean_sheets`, `bonus`, `bps`, `ict_index`, `GW` (or `round`)

**Important notes:**
- olbauday's `playerstats.csv` is described as "the equivalent of FPL API Data" — it likely has most of the fields `players_raw.csv` needs, possibly with different column names.
- The `code` field is critical — it's used to construct player photo URLs (`p{code}.png`). Make sure it's present or derivable.
- olbauday uses `2026-2027` as the season directory name; our pipeline uses `2026-27`. Always save locally as `2026-27`.
- Spaces in olbauday's paths must be URL-encoded as `%20` when fetching.
- There may be column discrepancies — fields missing, named differently, or formatted differently. When a field is missing, set a sensible default (0, empty string, None) rather than crashing.

**Implementation approach:**

Add a new function to `fetch_data.py` (e.g., `fetch_season_olbauday()`) that:
1. Downloads the season-root files (`playerstats.csv`, `teams.csv`, `players.csv`)
2. Downloads per-GW `player_gameweek_stats.csv` from each available GW
3. Maps columns to vaastav format
4. Saves to `data/2026-27/` in the expected structure
5. Builds `gws/merged_gw.csv` by concatenating all per-GW data

Add a CLI flag: `--source olbauday` (default remains `vaastav` for backward compatibility).

Usage:
```
python scripts/fetch_data.py --season 2026-27 --source olbauday --force
```

**What NOT to do:**
- Do NOT change how `platform_data.py`, `build_dataset.py`, or `predict_gameweek.py` read data. The translation happens at fetch time only.
- Do NOT rename the local `data/2026-27/` directory to match olbauday's `2026-2027`.
- Do NOT assume column names match — download sample files first and inspect them.

**1.1 — Regenerate predictions for 2026-27**

**KNOWN ISSUE:** The current `predictions_next_gw.csv` was generated against an older season. It contains teams that are no longer in the Premier League and is missing newly promoted teams:
- **In predictions but NOT in 2026-27:** Burnley, West Ham, Wolves (relegated)
- **In 2026-27 but NOT in predictions:** Coventry City, Hull City, Ipswich Town (promoted)

This mismatch causes the backend to reject the predictions entirely — the platform shows no predicted points anywhere.

**Fix:** First, fetch fresh data with the new source (Task 1.0). Then run the prediction pipeline:
```
python scripts/predict_gameweek.py --season 2026-27
```
This should write a fresh `predictions_next_gw.csv` at the project root using the 2026-27 roster and fixtures. If this script fails because it can't find models, check both `saved_models/` and `fpl_results/saved_models/` — use whichever has the trained `.joblib` files with a valid `direct/meta.json`.

Players from newly promoted teams (Coventry City, Hull City, Ipswich Town) will likely get `has_prior_history: false` since they have no PL training data. Their predictions will be less reliable — the frontend should flag this (see Task 2.5).

**DO NOT rebuild features or retrain models** — that takes hours of GPU compute and is done separately via Colab. The existing trained models are valid; only the lightweight prediction step (loading models + running inference on the 2026-27 fixture data) is needed here. If `predict_gameweek.py` fails, debug the script's file paths and data loading — do not fall back to retraining.

**1.2 — Validate prediction-roster alignment**

After generating predictions, verify every `element` in `predictions_next_gw.csv` exists in `data/2026-27/players_raw.csv`. The backend already does this check in `_load_predictions()` in `webapp/app.py` (it compares team lists), but you should also verify at the player level:

```python
import pandas as pd
preds = pd.read_csv('predictions_next_gw.csv')
roster = pd.read_csv('data/2026-27/players_raw.csv')
roster_ids = set(roster['id'].astype(int))
pred_ids = set(preds['element'].astype(int))
missing = pred_ids - roster_ids
print(f"Predictions for players NOT in 2026-27 roster: {len(missing)}")
```

If there are mismatches, the predictions were generated against the wrong season. Fix by running the predict script with the correct `--season` flag.

**1.3 — Fix model path in `webapp/app.py`**

In `webapp/app.py`, the function `model_summary()` (around line 122) reads `saved_models/direct/meta.json`. Verify this path exists at the project root. If the actual models live only under `fpl_results/saved_models/`, either:
- Copy/symlink `fpl_results/saved_models/` → `saved_models/` at the root, OR
- Update `model_summary()` to check both paths:

```python
meta_path = os.path.join('saved_models', 'direct', 'meta.json')
if not os.path.exists(meta_path):
    meta_path = os.path.join('fpl_results', 'saved_models', 'direct', 'meta.json')
```

**1.4 — Ensure prediction merge works in `/api/platform`**

In `webapp/app.py`, the `/api/platform` endpoint merges predictions onto the player snapshot. Currently it joins by `name` (string matching). This is fragile — names can differ between the prediction CSV and `players_raw.csv`. Change the merge to join on `element` (integer player ID) instead of `name`. The `element` column exists in both files.

Look at the `_enrich_snapshot()` or similar function in `app.py` that does this merge. The join key must be `element` (the FPL player ID), not name. If the current code already uses element, verify it works with the 2026-27 data.

**1.5 — Surface model confidence in the frontend**

The `/api/meta` endpoint returns model info (per-position model name, feature count, test R²). Currently nothing in the frontend displays this. Add a small "Model Info" footer or tooltip on pages that show predicted points (Team, Captain, Transfers) showing:
- Which model generated the predictions (e.g., "LightGBM")
- When predictions were last generated (the file timestamp)
- A note for players with `has_prior_history: false` — their predictions are less reliable

This info already flows through the API. Just display it.

---

## 2. Player Data Accuracy

### Problem
Player portraits show older/wrong photos. Players who left the Premier League still appear. The photo URL is constructed from the `code` field in `players_raw.csv` using `https://resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png`. If the `players_raw.csv` is from the 2026-27 season, the `code` values should be current. The issue is likely that either (a) the predictions CSV contains players from an older season, or (b) the PL CDN hasn't updated photos for some players.

### What to do

**2.1 — Use 2026-27 `players_raw.csv` as the single source of truth for the roster**

The `/api/platform` endpoint reads from `data/{latest_season}/players_raw.csv`. Since 2026-27 data now exists, it should automatically use it (the `latest_local_season()` function picks the alphabetically last season directory). Verify this returns "2026-27".

Players who left the PL will not appear in the 2026-27 `players_raw.csv` — they are automatically excluded. If they still show up, the platform is reading from an older season directory. Debug by checking what `latest_local_season()` returns.

**2.2 — Fix photo URL construction to use fresh codes**

The photo URL pattern `https://resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png` is correct. The `code` field in `players_raw.csv` is the permanent FPL player code. For the 2026-27 season, these codes point to current portraits.

However, verify the CDN actually serves these images. In the browser console or a script, spot-check 10-15 player photo URLs from the 2026-27 data:

```python
import pandas as pd
df = pd.read_csv('data/2026-27/players_raw.csv')
for _, row in df.head(15).iterrows():
    code = int(row['code'])
    print(f"{row['web_name']}: https://resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png")
```

Open a few in a browser. If they 404, the CDN may use a different URL pattern for 2026-27. Check if there's a `photo` column in `players_raw.csv` that contains the filename directly (like `154561.jpg`). If so, try the pattern: `https://resources.premierleague.com/premierleague/photos/players/250x250/p{photo_column_without_extension}.png`.

**2.3 — Improve the `PlayerPhoto` fallback**

The current fallback in `webapp/frontend/components/player-photo.tsx` shows initials in a colored circle. This is fine as a last resort, but we can do better:

1. Try the 110x140 size variant as a secondary attempt before falling back to initials: `https://resources.premierleague.com/premierleague/photos/players/110x140/p{code}.png`
2. Add a subtle silhouette placeholder SVG (a generic player outline) as an intermediate fallback between the CDN fail and initials.
3. Store the error state so the same broken image isn't re-requested on every render.

Implementation in `player-photo.tsx`:
```tsx
const [imgState, setImgState] = useState<'loading' | 'loaded' | 'error'>('loading');

// In the img tag:
onError={() => setImgState('error')}
onLoad={() => setImgState('loaded')}
```

When `imgState === 'error'`, render a styled SVG silhouette with the player's initials underneath, using their club colors as the background gradient.

**2.4 — Verify departed players are excluded from predictions**

If predictions were generated from an older roster, players who transferred out of the PL will have predictions but won't exist in the 2026-27 `players_raw.csv`. The `/api/platform` merge should simply skip these (they won't match on `element`). But the `/api/players` endpoint does its own merge in `enriched_players()` — verify it also handles this gracefully (no crash, no ghost entries).

**2.5 — Handle new signings with no history**

Players new to the PL in 2026-27 will have `has_prior_history: false` in predictions. In the frontend, these should be visually flagged:
- Add a small "NEW" badge (using broadcast `.badge` class) next to their name in any player list.
- In the Player Drawer, show a note: "New to the Premier League — predicted points are less reliable."
- In Captain recommendations, demote players with no history below those with history at similar predicted points.

---

## 3. Visual Overhaul — Chips Page

### Problem
The Chips page (`webapp/frontend/app/chips/page.tsx`) is entirely inline-styled, uses emoji icons, has `borderRadius` instead of broadcast blade shapes, and looks like a separate app from the rest of the platform. It needs to be fully rebuilt using the broadcast design system.

### What to do

**3.1 — Add broadcast CSS classes for chip components**

In `webapp/frontend/app/broadcast.css`, add a new section (after the existing component sections):

```css
/* ── Chip Advisor ─────────────────────────────────────────── */
.chip-grid        { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: var(--sp-4); }
.chip-card        { background: var(--surface-1); clip-path: var(--blade); padding: var(--sp-5); display: flex; flex-direction: column; gap: var(--sp-3); transition: transform var(--motion-fast) var(--ease-out); }
.chip-card:hover  { transform: translateY(-2px); }
.chip-icon        { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 50%; font-size: var(--text-lg); font-weight: 700; font-family: var(--display); }
.chip-name        { font-family: var(--display); font-size: var(--text-lg); text-transform: uppercase; letter-spacing: 0.05em; }
.chip-rec         { font-family: var(--data); font-size: var(--text-sm); color: var(--muted-light); }
.chip-conf        { display: inline-flex; align-items: center; gap: var(--sp-1); font-family: var(--data); font-size: var(--text-xs); padding: 2px 8px; }
.chip-conf.high   { background: rgba(0,255,135,0.15); color: var(--lime); }
.chip-conf.medium { background: rgba(0,240,255,0.15); color: var(--cyan); }
.chip-conf.low    { background: rgba(255,255,255,0.08); color: var(--muted-light); }

.chip-heatmap     { width: 100%; border-collapse: collapse; font-family: var(--data); font-size: var(--text-xs); }
.chip-heatmap th  { text-align: left; padding: var(--sp-2); color: var(--muted-mid); font-weight: 500; border-bottom: 1px solid var(--rule); position: sticky; top: 0; background: var(--night-900); }
.chip-heatmap td  { padding: var(--sp-2); border-bottom: 1px solid var(--rule); }
```

**3.2 — Rewrite the Chips page JSX**

Replace all inline styles with the broadcast CSS classes above. Specific changes:

1. **Remove all emoji icons.** Replace with styled `<span>` elements using broadcast typography:
   - Triple Captain → "TC" in a gold circle (`background: var(--gold)`)
   - Bench Boost → "BB" in a cyan circle (`background: var(--cyan)`)
   - Free Hit → "FH" in a pink circle (`background: var(--pink)`)
   - Wildcard → "WC" in a lime circle (`background: var(--lime)`)

2. **Replace every `style={{ }}` prop** with the appropriate broadcast CSS class. Go through the file line by line. Every `background: "rgba(...)"` becomes a broadcast surface class. Every `borderRadius` becomes `clip-path: var(--blade)` via a class. Every `color: "var(...)"` moves to a class.

3. **The heatmap table** should use `.chip-heatmap` class. Each FDR cell should use the existing FDR color classes from broadcast.css (`.fdr-1` through `.fdr-5`).

4. **The horizon slider** should use a native `<input type="range">` styled with broadcast CSS (add a `.range-input` class to broadcast.css if needed), or convert to the pattern used elsewhere (e.g., button group like the count selector on other pages).

5. **The "Squad-tailored" toggle** should use the broadcast switch pattern (the same pattern used in the Fixtures page's "My clubs only" toggle).

6. **Confidence badges** should use the `.chip-conf` classes (`.high`, `.medium`, `.low`) instead of inline conditional styles.

7. **The "Why?" reasoning text** should use the `.chip-rec` editorial styling with the `--editorial` font family for readability.

**3.3 — Match the page structure to other pages**

Follow the pattern of the Captain or News pages:
- Hero section at top with a title in `.display-md` and a subtitle in editorial font
- Content below in a consistent grid
- Use the `.wire-filters` or similar bar for the horizon/toggle controls
- Use `.panel` for the heatmap wrapper

**What NOT to do:**
- Do not use `borderRadius` anywhere — the broadcast system uses `clip-path` for its angular aesthetic.
- Do not use inline `style` props for layout/colors — only for truly dynamic values (like club-color gradients from `clubStyle()`).
- Do not add any new npm packages for icons — use typography-based icons (letters in circles) consistent with the broadcast feel.
- Do not put emoji in the UI.

---

## 4. Visual Overhaul — Watchlist Page

### Problem
The Watchlist page (`webapp/frontend/app/watchlist/page.tsx`) is entirely inline-styled with JavaScript hover handlers (`onMouseEnter`/`onMouseLeave`). It looks bolted-on compared to the broadcast-styled pages. The player cards use `borderRadius: "4px"` and none of the broadcast design tokens.

### What to do

**4.1 — Add broadcast CSS classes for watchlist components**

In `broadcast.css`, add:

```css
/* ── Watchlist ────────────────────────────────────────────── */
.watch-grid       { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: var(--sp-3); }
.watch-card       { background: var(--surface-1); clip-path: var(--blade); padding: var(--sp-4); display: flex; align-items: center; gap: var(--sp-3); transition: transform var(--motion-fast) var(--ease-out), background var(--motion-fast); cursor: pointer; }
.watch-card:hover { transform: translateX(4px); background: var(--surface-2); }
.watch-tag        { font-family: var(--data); font-size: var(--text-xs); padding: 2px 8px; clip-path: var(--blade-sm); text-transform: uppercase; letter-spacing: 0.05em; }
.watch-tag.value  { background: rgba(0,255,135,0.15); color: var(--lime); }
.watch-tag.diff   { background: rgba(0,240,255,0.15); color: var(--cyan); }
.watch-tag.trap   { background: rgba(255,60,120,0.15); color: var(--pink); }
.watch-tag.new    { background: rgba(255,200,0,0.15); color: var(--gold); }
.watch-pts        { font-family: var(--data); font-size: var(--text-lg); font-weight: 700; }
.watch-price      { font-family: var(--data); font-size: var(--text-sm); color: var(--muted-light); }
```

**4.2 — Rewrite the Watchlist page JSX**

1. **Remove ALL inline styles.** Every single `style={{ }}` must go.
2. **Remove all `onMouseEnter`/`onMouseLeave` handlers.** Hover effects come from CSS (`:hover` pseudo-class in the `.watch-card` class).
3. **Each player card** becomes:
   ```tsx
   <div className="watch-card" onClick={() => openDrawer(player)}>
     <PlayerPhoto src={player.photo} name={player.web_name} size={48} />
     <div className="watch-info">
       <span className="watch-name">{player.web_name}</span>
       <span className="watch-price">{money(player.value_m)} · {player.team_short}</span>
     </div>
     <div className="watch-pts">{num(player.predicted_points, 1)}</div>
     <span className={`watch-tag ${category}`}>{tagLabel}</span>
   </div>
   ```
4. **The tab switcher** should use the broadcast `.btn` and `.btn.ghost` classes, matching how the News page does its filter buttons.
5. **The threshold/count selects** should be styled select elements or button groups using broadcast styling.
6. **The search input** should use the `.search` class from broadcast.css (same as the Transfer Studio search).

**4.3 — Add responsive breakpoints**

In the `@media` section of broadcast.css:
- At ≤860px: `.watch-grid` goes to `grid-template-columns: 1fr` (single column)
- At ≤560px: Reduce card padding, shrink typography

**What NOT to do:**
- No `borderRadius` — use `clip-path: var(--blade)`.
- No JavaScript hover handlers — CSS `:hover` only.
- No inline `transition` styles — use broadcast motion tokens.

---

## 5. Visual Overhaul — Captain Page

### Problem
The captain armband/badge has been reported as looking "vibecoded." The page itself is one of the better-styled ones (uses broadcast CSS), but the captain badge element needs refinement.

### What to do

**5.1 — Refine the captain armband in `player-marker.tsx`**

Look at `webapp/frontend/components/team/player-marker.tsx`. The captain badge is likely a `C` letter in a circle overlaid on the player marker. Issues reported include positioning and visual quality.

The captain badge should:
- Be a small circle (20×20px) with `background: var(--gold)` and `color: var(--night-900)` (dark text on gold)
- Use `font-family: var(--display)` and `font-weight: 700`
- Be positioned at the top-right of the player photo with `position: absolute; top: -4px; right: -4px`
- Have a 2px solid border in `var(--night-900)` to separate it from the photo
- NOT use clip-path (circles are fine for badges — clip-path is for cards/panels)

Check `broadcast.css` for any existing `.armband` or `.captain` class and either fix it or create one:

```css
.captain-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--gold);
  color: var(--night-900);
  font-family: var(--display);
  font-size: 11px;
  font-weight: 700;
  display: grid;
  place-items: center;
  border: 2px solid var(--night-900);
  z-index: 2;
  line-height: 1;
}
```

**5.2 — Captain page hero refinement**

The captain page hero section uses the top candidate's club colors as a gradient background. This is good. Verify:
- The gradient doesn't make text unreadable (ensure text has a dark overlay or text-shadow)
- The player photo is properly sized and doesn't stretch
- The club crest next to the player info is appropriately sized (24-32px)

**5.3 — Captain "battle" section**

The head-to-head comparison between the top 2 picks uses dual bar charts. Verify these bars:
- Use broadcast color tokens (`--cyan` for player A, `--pink` for player B, or club colors)
- Have minimum width so near-zero values are still visible
- Show values in `--data` font family
- Animate on reveal (use the broadcast `.bar` animation pattern)

---

## 6. Loading States & Empty States

### Problem
Every page shows plain text like `"Loading the local season data..."` with no visual indicator. Empty states are inconsistent — some use broadcast CSS, some use inline styles, some reference non-existent classes.

### What to do

**6.1 — Create a broadcast loading spinner component**

The broadcast.css already defines a `@keyframes spin` animation. Create a reusable component:

File: `webapp/frontend/components/loading.tsx`
```tsx
export function Loading({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="loading-state">
      <div className="loading-spinner" />
      <p className="loading-label">{label}</p>
    </div>
  );
}
```

Add to broadcast.css:
```css
.loading-state   { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--sp-3); padding: var(--sp-8) 0; }
.loading-spinner { width: 32px; height: 32px; border: 3px solid var(--rule); border-top-color: var(--cyan); border-radius: 50%; animation: spin 0.8s linear infinite; }
.loading-label   { font-family: var(--ui); font-size: var(--text-sm); color: var(--muted-mid); }
```

**6.2 — Replace all plain-text loading states**

In every page file, replace the `<p>Loading the local season data...</p>` pattern with `<Loading label="Loading season data…" />`.

Pages to update:
- `app/team/page.tsx`
- `app/captain/page.tsx`
- `app/chips/page.tsx`
- `app/transfers/page.tsx`
- `app/comparison/page.tsx`
- `app/watchlist/page.tsx`
- `app/news/page.tsx`
- `app/fixtures/page.tsx`
- `components/player-drawer.tsx` (for history loading)

**6.3 — Create a broadcast empty-state component**

File: `webapp/frontend/components/empty-state.tsx`
```tsx
export function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="empty-state">
      <h3 className="empty-title">{title}</h3>
      <p className="empty-message">{message}</p>
    </div>
  );
}
```

Add to broadcast.css:
```css
.empty-state   { text-align: center; padding: var(--sp-8) var(--sp-4); }
.empty-title   { font-family: var(--display); font-size: var(--text-lg); color: var(--white); margin-bottom: var(--sp-2); }
.empty-message { font-family: var(--ui); font-size: var(--text-sm); color: var(--muted-mid); max-width: 40ch; margin: 0 auto; }
```

**6.4 — Replace all inconsistent empty states**

Update the "Predictions Unavailable" states in Chips and Watchlist pages to use `<EmptyState title="Predictions Unavailable" message="Run the prediction pipeline to enable this feature." />`.

Update the pitch empty state, news empty state, etc. to all use this component (or keep their custom ones if they're already well-styled in broadcast CSS — just ensure consistency).

---

## 7. Error Boundary Fix

### Problem
`webapp/frontend/components/error-boundary.tsx` references CSS classes that don't exist (`panel`, `card-tint`, `btn`, `btn-primary`) and uses the wrong CSS variable (`--muted-foreground` instead of `--muted-mid`).

### What to do

Open `error-boundary.tsx` and fix the fallback render:

1. Replace `className="panel card-tint"` with a valid broadcast surface class. Use a wrapper `div` with broadcast styling:
   ```tsx
   <div style={{ background: 'var(--surface-1)', padding: 'var(--sp-6)' }}>
   ```
   Or better, add an `.error-panel` class to broadcast.css.

2. Replace `btn btn-primary` with broadcast button classes. Check what button classes exist in broadcast.css (likely `.btn` and a color modifier). If `.btn` exists, use it. The button should call `window.location.reload()`.

3. Replace `color: var(--muted-foreground)` with `color: var(--muted-mid)`.

4. Use the `--display` font for the error heading, `--ui` for the message.

---

## 8. Navigation & Responsive Fixes

### Problem
At ≤1080px, the navigation actions (Refresh button and Deadline Clock) are hidden via `display: none`. This removes functionality on tablets. The crest ticker buttons are non-functional but announced as buttons to screen readers.

### What to do

**8.1 — Fix navigation actions on tablet**

In broadcast.css, find the media query that hides `.nav-actions` (around line 1136). Instead of `display: none`, change to a more compact layout:
- At ≤1080px: Hide the "Refresh" text label but keep the icon/button functional. Shrink the deadline clock to show just the countdown number without the "until GW X" label.
- At ≤860px: Move the refresh button and deadline clock into a collapsible overflow menu (hamburger or "..." button) rather than hiding them entirely.

Alternatively, at minimum: keep the refresh button visible at all breakpoints (it can be just an icon at small sizes) and keep the deadline clock visible (it can show just "2d 14h" without context text).

**8.2 — Fix crest ticker accessibility**

In `webapp/frontend/components/chrome/crest-ticker.tsx`:
- If the crest buttons have no `onClick`, change them from `<button>` to `<div>` or `<span>` with `role="img"` and an `aria-label` like `aria-label="{team name} crest"`.
- OR give them functionality: clicking a crest could filter the current page to show only that team's players (many pages have team filters).

**8.3 — Navigation active state**

Verify the ink underline animation works correctly on all 8 tabs. The `ResizeObserver` in `main-nav.tsx` handles font-swap reflow, but check that:
- The underline appears immediately on page load (not just on hover/click)
- The underline tracks correctly when switching tabs rapidly
- The underline works at all viewport sizes

---

## 9. Player Drawer Enrichment

### Problem
The player drawer (`webapp/frontend/components/player-drawer.tsx`) is one of the most important components — it's the deep-dive view for any player. It needs to show richer data and connect better to the model predictions.

### What to do

**9.1 — Add predicted points prominently**

If the player has `predicted_points`, show it as a large number in the hero section:
```
PROJECTED: 4.8 pts
```
Use the `--data` font at `--text-2xl` size, colored `var(--lime)` for high predictions, `var(--cyan)` for medium, `var(--muted-light)` for low.

**9.2 — Add "Why this prediction?" context**

Below the predicted points, show the key factors:
- Form (last 5 GW average)
- Fixture difficulty of the upcoming match
- Home/away status
- `has_prior_history` flag (if false, show a caveat)

These fields all exist in the API response.

**9.3 — Add season stat sparklines or mini-charts**

If the player has gameweek history (from the `/api/player/{id}/history` endpoint), render a small bar chart or sparkline of their last 5-8 gameweek scores. This can be pure CSS (a row of thin bars with heights proportional to points).

```css
.sparkline       { display: flex; align-items: flex-end; gap: 2px; height: 32px; }
.sparkline-bar   { width: 6px; background: var(--cyan); border-radius: 1px 1px 0 0; transition: height var(--motion-fast) var(--ease-out); }
```

**9.4 — Show transfer popularity**

Display `transfers_in_event` and `transfers_out_event` as a net transfer indicator. A heavily transferred-in player is trending; heavily transferred-out is losing favor. Use green/red arrows or the broadcast color scheme (`--lime` for net positive, `--pink` for net negative).

---

## 10. Team Page Polish

### Problem
The Team page is the landing page (root redirects to `/team`). It's one of the most polished pages but has some areas for improvement.

### What to do

**10.1 — Squad cost validation**

When the user has a squad selected, show the total cost and remaining budget. Currently the hero shows "squad cost" but verify it:
- Sums all 15 player values correctly
- Shows remaining budget (100.0 - total cost) in the rail sidebar
- Highlights in red/pink if over budget

**10.2 — Auto-pick integration with predictions**

The "Run auto-pick" button calls `/api/squad`. Verify:
- It works with the 2026-27 data
- The result populates the pitch correctly
- Player photos in the pitch markers load properly
- The captain badge appears on the auto-picked captain

**10.3 — Bench ordering**

The sidebar shows a bench order list. Verify:
- Bench players are ordered by predicted points (best first off the bench)
- Their predicted points are shown next to their names
- The bench section is clearly separated from XI stats

**10.4 — Formation display**

Show the current formation (e.g., "3-5-2") in the hero or above the pitch. The `previewSquad()` function in `lib/squad.ts` determines the formation — surface this to the UI.

---

## 11. Transfer Studio Polish

### Problem
The Transfer Studio is the most complex page and is already well-built, but needs some polish.

### What to do

**11.1 — Verify optimizer results display**

After clicking "Run full analysis," the impact grid shows results for 0-3 transfers. Verify:
- Net gain/loss is calculated correctly (gross points - hit cost)
- The recommended number of transfers is highlighted
- Player names in the "in/out" lists are correct and current
- Clicking a player in the results opens the player drawer

**11.2 — Market list cap**

The incoming player list is capped at 120 (`inRows.slice(0, 120)`). This may hide good options. Increase to 200 or add a "Show more" button. Alternatively, ensure the search/filter is prominent enough that users can find any player.

**11.3 — Visual feedback during analysis**

When the optimizer is running, show the broadcast loading spinner (from task 6) instead of plain text. The transfer "channel" center column should show a pulsing animation during analysis.

**11.4 — Price change indicators**

If `players_raw.csv` contains `cost_change_event` or `cost_change_start`, show rising/falling price indicators next to player values in the market columns. Use `var(--lime)` for rising, `var(--pink)` for falling.

---

## 12. Comparison Page Polish

### Problem  
The Comparison page is well-built but can be enhanced.

### What to do

**12.1 — Pre-fill from squad**

If the user has a squad, the player picker's "My squad" pool should be the default when filling slots. This saves clicks.

**12.2 — Metric bar animations**

The 12 comparison metric rows have dual bars. Verify:
- Bars animate on appearance (use CSS transitions)
- The winning metric row has the winner's bar highlighted
- Near-zero values still show a visible sliver (minimum 2-3% width)

**12.3 — Add predicted points as first metric**

If predictions are available, "Projected Points (next GW)" should be the first metric in the comparison, above form and total points. This is the most decision-relevant data.

**12.4 — Shareable comparison**

Consider encoding the two player IDs in the URL query string (`?a=123&b=456`) so the comparison can be bookmarked or shared. Use `useSearchParams` from next/navigation.

---

## 13. News Page Polish

### Problem
The News page is well-styled but some refinements would help.

### What to do

**13.1 — Status badge colors**

Verify the status badges match FPL conventions:
- `a` (available) = green/lime
- `d` (doubtful) = yellow/orange  
- `i` (injured) = red/pink
- `s` (suspended) = red
- `u` (unavailable) = gray
- `n` (not known) = gray

Check that the colors in the JSX match broadcast tokens.

**13.2 — Chance of playing indicator**

For players with `chance_of_playing_next_round` set (25%, 50%, 75%), show this as a colored percentage badge. Use a gradient from red (25%) through orange (50%) to yellow (75%).

**13.3 — Item limit**

The news list is capped at 25 items (`rest = filtered.slice(1, 25)`). During busy transfer windows, there may be many more. Add a "Show all" toggle or increase the default.

**13.4 — Link to player drawer**

Verify every news item is clickable and opens the player drawer for that player. The drawer should show the news text and status prominently.

---

## 14. Fixtures Page Polish

### Problem
The Fixtures page is well-implemented. Minor polish items.

### What to do

**14.1 — Verify 2026-27 fixtures load correctly**

The fixture matrix reads from the 2026-27 `fixtures.csv`. Verify:
- All 20 teams appear
- The 8-gameweek horizon is correct (starts from the next unfinished gameweek)
- FDR colors (1-5) display correctly
- Home/Away indicators (H/A) are shown in each cell

**14.2 — DGW/BGW indicators**

If a team has a double gameweek (two fixtures in one GW), the cell should show both opponents. If a team has a blank (no fixture), the cell should show "—" with a distinct gray styling. Check the data supports this.

**14.3 — "Easiest run" calculation**

Verify the "Easiest run" cards at the top calculate correctly over the visible 8-GW window. The average FDR should use the actual difficulty values from `fixtures.csv`.

---

## 15. Dead Code Cleanup

### Problem
Many shadcn UI components are installed but never used. Two design systems coexist. Lucide-react is imported by unused code.

### What to do

**15.1 — Remove unused shadcn UI components**

Check each file in `webapp/frontend/components/ui/`. If a component is not imported by any page or custom component, remove it. Based on the analysis, these are likely unused:
- `command.tsx` (unless `cmdk` is used somewhere)
- `input-group.tsx`
- `input.tsx`
- `scroll-area.tsx`
- `select.tsx`
- `separator.tsx`
- `switch.tsx`
- `tabs.tsx`
- `textarea.tsx`
- `badge.tsx`

Before deleting, grep the codebase to confirm: `grep -r "from.*components/ui/badge" webapp/frontend/`

**15.2 — Clean up globals.css**

Remove the shadcn oklch neutral theme variables from `globals.css` (both `:root` and `.dark` blocks) since they're completely overridden by broadcast.css. Keep only:
- The `@import "tailwindcss"` line
- The `@import "./broadcast.css"` line
- The `@custom-variant dark` line (can be removed if dark mode isn't used)
- Any Tailwind `@theme` blocks that are actually referenced

Do NOT remove broadcast.css content.

**15.3 — Remove unused dependencies**

If `lucide-react` is only used by the unused `components/ui/dialog.tsx`, remove it from `package.json`:
```
npm uninstall lucide-react
```

Check if `cmdk` is actually used. If not, remove it too.

**15.4 — Remove default Next.js assets**

Delete the default SVGs from `webapp/frontend/public/` that aren't used:
- `file.svg`, `globe.svg`, `next.svg`, `vercel.svg`, `window.svg`

These are leftover from `create-next-app` and serve no purpose.

---

## 16. Backend Hardening

### Problem
The backend works but has some fragilities.

### What to do

**16.1 — Prediction-roster join robustness**

In `webapp/app.py`, the `/api/platform` endpoint merges predictions onto the snapshot. Double-check the join is on `element` (integer FPL ID), not `name`. If it's on name, change it to element. Names are not unique and can have encoding issues.

**16.2 — Error response consistency**

All API endpoints should return a consistent error format:
```json
{"ok": false, "error": "Human-readable message"}
```

Check every endpoint returns this on error. The frontend's `requestJson()` function in `lib/api.ts` checks for `{ok: false}` and throws — make sure the backend always sets this.

**16.3 — Graceful degradation when predictions are missing**

If `predictions_next_gw.csv` doesn't exist or is empty:
- `/api/platform` should still return all players and teams, just with `predicted_points: null` and `prediction_available: false`
- `/api/squad`, `/api/transfers`, `/api/chips`, `/api/watchlist` should return `{ok: false, error: "Predictions not available. Run the prediction pipeline first."}` with HTTP 503

Verify this works by temporarily renaming the predictions file and hitting the endpoints.

**16.4 — Add `prediction_available` and `prediction_timestamp` to platform response**

The frontend needs to know if predictions exist and when they were generated. Add these fields to the `/api/platform` response:
```python
"prediction_available": bool(_state.get("players")),
"prediction_timestamp": _state.get("mtime"),  # ISO 8601 string
```

The frontend should display this (e.g., "Predictions from 2h ago" in the navigation or on relevant pages).

---

## 17. Performance & Accessibility

### What to do

**17.1 — Image loading optimization**

All player photos and club crests use raw `<img>` tags. Add `loading="lazy"` to every `<img>` that is not above the fold (i.e., not in the hero/header area):

In `player-photo.tsx`:
```tsx
<img loading="lazy" decoding="async" ... />
```

In `club-crest.tsx`:
```tsx
<img loading="lazy" decoding="async" ... />
```

For above-the-fold images (hero sections), use `loading="eager"` and add `fetchPriority="high"`.

**17.2 — Contrast audit**

Check these color combinations against WCAG AA (4.5:1 for normal text, 3:1 for large text):
- `var(--muted-mid)` (#9d88a3) on `var(--night-900)` (#1a0022) — this is likely below 4.5:1
- `var(--muted-light)` on dark surfaces

If contrast is insufficient, lighten `--muted-mid` slightly (try #b8a5be or similar). Test with a contrast checker.

**17.3 — Focus visible styles**

Add a global focus-visible style in broadcast.css:
```css
:focus-visible {
  outline: 2px solid var(--cyan);
  outline-offset: 2px;
}
```

This ensures all interactive elements have visible focus indicators for keyboard users, including elements that previously used inline styles.

**17.4 — Reduce motion support**

The broadcast.css already has a `@media (prefers-reduced-motion: reduce)` query. Verify it disables:
- The crest ticker scrolling animation
- The page entry animations
- The ink underline transitions
- The spinner animation (replace with a static "Loading..." text)

**17.5 — Semantic HTML**

Verify pages use proper landmarks:
- `<main>` for the primary content area
- `<nav>` for navigation (likely already done)
- `<header>` for the hero sections
- `<section>` with appropriate `aria-label` for major page sections

---

## 18. End-to-End Smoke Tests

### What to do

After all improvements are complete, run through this manual test script:

**18.1 — Data flow test**
1. Start Flask: `python webapp/app.py`
2. Start Next.js: `cd webapp/frontend && npm run dev`
3. Open `http://localhost:3000`
4. Verify it redirects to `/team`
5. Verify 20 teams appear in the crest ticker
6. Verify the season shows "2026-27"

**18.2 — Predictions test**
1. Go to Team page, click "Run auto-pick"
2. Verify 11 players appear on the pitch with photos
3. Verify predicted points appear on each player marker
4. Verify the captain badge appears on one player
5. Click a player — verify the drawer opens with correct stats

**18.3 — Page-by-page test**
- **Transfers:** Stage a transfer, run analysis, verify results
- **Captain:** Verify top candidates list with photos, form, predicted points
- **Watchlist:** Verify all 4 lists populate with photos and stats
- **Chips:** Verify recommendations appear with the heatmap
- **Fixtures:** Verify 20-team × 8-GW matrix with FDR colors
- **News:** Verify injury/status items appear with correct badges
- **Comparison:** Pick two players, verify all 12 metrics compare correctly

**18.4 — Visual consistency check**
- Every page should use the dark broadcast theme (dark purple background, neon accents)
- No page should have `borderRadius` cards (everything uses clip-path blades)
- No page should have emoji icons
- No plain-text "Loading..." states
- All player photos should load (or show proper fallbacks)
- All club crests should load (or show colored circle fallbacks)

**18.5 — Responsive check**
- Test at 1440px (desktop)
- Test at 768px (tablet)
- Test at 375px (mobile)
- Verify navigation is usable at all sizes
- Verify no horizontal scrollbar appears on any page (except the fixtures matrix which has its own scroll container)

---

## IMPLEMENTATION ORDER (Priority)

Execute in this order for maximum impact with minimum risk:

### Phase 1: Data Foundation (Tasks 1, 2)
Get the data pipeline right first. Without correct predictions and player data, nothing else matters.

### Phase 2: Visual Overhaul (Tasks 3, 4, 5, 6, 7)
Fix the most visually broken elements. Chips and Watchlist pages are the worst offenders. Loading/empty states affect every page.

### Phase 3: Polish (Tasks 8, 9, 10, 11, 12, 13, 14)
Refine every page to production quality. These are lower priority because the pages already work.

### Phase 4: Cleanup & Hardening (Tasks 15, 16, 17)
Remove dead code, harden the backend, improve performance and accessibility.

### Phase 5: Verification (Task 18)
Run the full smoke test suite to verify everything works together.

---

## APPENDIX: Key File Locations

| File | Purpose |
|------|---------|
| `webapp/app.py` | Flask API server (544 lines) |
| `webapp/platform_data.py` | Data adapter for local CSV files (316 lines) |
| `scripts/optimise.py` | ILP optimizer for squads/transfers |
| `scripts/predict_gameweek.py` | Generates `predictions_next_gw.csv` |
| `predictions_next_gw.csv` | Current model predictions |
| `data/2026-27/players_raw.csv` | Current season player roster (616 players) |
| `data/2026-27/teams.csv` | Current season team data (20 teams) |
| `data/2026-27/fixtures.csv` | Current season fixture list |
| `webapp/frontend/app/layout.tsx` | Root layout, providers, nav |
| `webapp/frontend/app/broadcast.css` | The broadcast design system (~1400 lines) |
| `webapp/frontend/app/globals.css` | Tailwind base + (mostly dead) shadcn theme |
| `webapp/frontend/components/player-photo.tsx` | Player portrait component |
| `webapp/frontend/components/club-crest.tsx` | Club crest component |
| `webapp/frontend/components/player-drawer.tsx` | Player detail slide-out |
| `webapp/frontend/components/team/player-marker.tsx` | Pitch player marker |
| `webapp/frontend/components/providers/app-provider.tsx` | Global state provider |
| `webapp/frontend/lib/api.ts` | API client |
| `webapp/frontend/lib/types.ts` | TypeScript interfaces |
| `webapp/frontend/lib/format.ts` | Formatting utilities |
| `webapp/frontend/lib/club-colors.ts` | Club color mapping |
| `webapp/frontend/lib/squad.ts` | Client-side squad logic |
| `saved_models/direct/meta.json` | Model metadata |
| `DESIGN.md` | Design system specification |
| `PROGRESS.md` | Work progress log (create/append after each task) |
