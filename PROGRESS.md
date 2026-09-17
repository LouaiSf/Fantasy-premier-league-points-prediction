# Implementation Progress

## 2026-09-17 — Task 1.3: Model path fallback
Added fallback from `saved_models/direct/meta.json` to `fpl_results/saved_models/direct/meta.json` in `model_summary()`.

## 2026-09-17 — Task 1.4: Prediction merge on element ID
Changed `/api/platform` enrichment join from player name to `element` (FPL integer ID) to prevent mis-matches and ghost entries.

## 2026-09-17 — Task 3: Chips page broadcast rewrite
Rewrote `app/chips/page.tsx` using broadcast design system — replaced all inline styles and emoji icons with CSS classes, added `chip-advisor-*` and `chip-conf` classes to broadcast.css, replaced emoji with styled letter-circle icons (TC/BB/FH/WC).

## 2026-09-17 — Task 4: Watchlist page broadcast rewrite
Rewrote `app/watchlist/page.tsx` using broadcast design system — removed all inline styles and `onMouseEnter`/`onMouseLeave` handlers, added `watch-*` CSS classes to broadcast.css with CSS `:hover` effects, responsive breakpoints at 860px/560px.

## 2026-09-17 — Task 5: Captain badge (pm-badge verified)
Confirmed `.pm-badge` class in broadcast.css and usage in `player-marker.tsx` are correctly aligned with the gold circle spec.

## 2026-09-17 — Task 6: Loading and empty state components
Created `components/loading.tsx` and `components/empty-state.tsx` with broadcast spinner and styling. Added `.loading-state`, `.loading-spinner`, `.loading-label`, `.empty-state`, `.empty-title`, `.empty-message` to broadcast.css. Updated all 8 page routes and player-drawer to use `<Loading />` component.

## 2026-09-17 — Task 7: Error boundary fix
Fixed `error-boundary.tsx` — removed non-existent `panel card-tint` and `btn-primary` CSS classes, changed `--muted-foreground` to `--muted-mid`, using `.btn` directly.

## 2026-09-17 — CSS additions: blade vars + badge
Added `--blade` and `--blade-sm` CSS variables to `:root` in broadcast.css. Added `.badge` utility class for page header eyebrow labels.
