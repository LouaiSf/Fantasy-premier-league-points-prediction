# FPL Platform v3 implementation progress

This tracks execution of `PLATFORM_V3_PLAN.md`. Read the plan and `git status` before every resumed session.

## Slice V0: visual foundations

### Implemented

- **V0.1 Fonts.** Self-hosted variable Fontsource packages (`@fontsource-variable/archivo`, `-inter`, `-newsreader`, `@fontsource/barlow-semi-condensed`) replace the runtime Google Fonts `<link>` tags in `app/layout.tsx`. Confirmed registered family names (`Archivo Variable`, `Inter Variable`, `Newsreader Variable`, `Barlow Semi Condensed`) match the `--display`/`--ui`/`--editorial` token stacks in `broadcast.css`. Added `.display-hero` (`"wdth" 112`, weight 900) to every page's `<h1>` (team, transfers, comparison, captain, watchlist, chips, fixtures, news; stats does not exist yet) and gave `.sub-head h3` the `"wdth" 100`/weight 800 pairing. Added `--type-micro`/`--type-mini` tokens and raised all 119 sub-11px `font`/`font-size` declarations in `broadcast.css` to `var(--type-micro)`, capping `letter-spacing` at `.1em` in those same rules (script-driven, verified 0 remaining matches). Restricted `var(--editorial)` to the 13 analyst-copy selectors the plan named and switched the 16 functional-UI selectors it named to `var(--ui)` at weight 500; four other editorial usages the plan's list didn't cover (`.prow-why`, `.lead-quote`, `.quote-card::before`, `.reel-copy p`) were left as editorial since they read as analyst/quote copy, not UI chrome. `DESIGN.md` bumped to v1.4 with the new tokens, the 11px floor, and "self-hosted via Fontsource" in §3 and Accepted Debt.
- **V0.2 Motion.** Added `components/motion/motion-provider.tsx` (`LazyMotion`+`MotionConfig`, `strict`) wrapping `AppProvider`'s children in `app/layout.tsx`. Added CSS primitives `.stagger` (entrance rise, capped delay) and `.lift` (hover), applied to the captain shortlist, watchlist grids, news wire list/cards, the chip advisor grid, the deadline board list, the Transfer Studio OUT/IN/market lists, and the team-plan OUT/IN lanes. Added `lib/use-count-up.ts` + `components/motion/count-up.tsx` and wired it into My Team's XI projection and market value, the chips hero gain, the Transfer Studio gross/hit/net, and the captain hero projection. Converted the captain shortlist to `m.div` with `layout="position"` FLIP reordering, and wrapped the Transfer Studio draft rows, saved scenarios and planned-chip list in `AnimatePresence` with an exit transition. Rewired the player drawer and toast off a manual `is-open` class onto Base UI's `data-starting-style`/`data-ending-style` attributes (verified drawer open/Escape-close/focus still work). Pitch markers now enter staggered by formation line via a `.marker-slot` wrapper (kept the animation off the interactive `.pm` button itself — confirmed empirically that a `both`-fill entrance animation on the same element permanently blocks its own `:hover` transform, which is why `.cand`'s existing hover lift is already silently dead; the wrapper avoids repeating that bug for the new marker entrance). The captain armband gets a `stamp` entrance keyed to remount per captain change. Converted width-animated bars (captain Form/ICT `.meter`, `.duel-track` duel bars, the deadline tension bar) to `transform:scaleX`/`transform-origin:left`. Split the deadline countdown into per-unit `.tick` spans that only replay when their own value changes. Extended the reduced-motion media query to zero out `.stagger`, `.marker-slot`, `.tick`, `.skel` and neutralize `.lift:hover`.
- **V0.3 Skeletons.** Added `components/skeleton.tsx` (`row`/`card`/`pitch`/`table`/`hero` variants, shimmer keyframe, `aria-busy`) and replaced the top-level spinner-plus-text loading state with page-shaped skeletons: team (hero+pitch), chips (hero+4 cards), captain (hero+10 rows), watchlist (3×8 rows), transfers (2×8 rows), news (8 rows), fixtures (20 table rows). `components/loading.tsx` now covers only in-button/in-flight states (watchlist "Updating market metrics…", chips "Calculating…", comparison's `Suspense` fallback).
- **V0.4 Chart kit.** Added `components/charts/{sparkline,bar-strip,delta-bar,scatter}.tsx`: inline SVG/HTML, no charting library, 11px `var(--data)` labels, a zero line instead of gridlines, `.hatch` at 30% opacity for null `BarStrip` values, and the existing `components/ui/tooltip.tsx` (via Base UI's `render` prop) for hover/keyboard-focus detail on `BarStrip` bars and `Scatter` points. Nothing in the app renders these yet — Slice A5, B2 and C2 are their intended first consumers — so they were verified by temporarily mounting sample data on `/fixtures`, confirming render, tooltip and keyboard focus in a real browser, then reverting that page to its committed state (`git diff` clean before commit).

### Verification evidence

- `npm exec tsc -- --noEmit` and `npm run build` passed after each of the four sub-slices.
- Playwright at 1440×900 and 375×800 on `/team`, `/captain`, `/transfers` (plus spot checks on `/chips`, `/watchlist`, `/fixtures`, `/news`): 0 console errors on every page, no `getComputedStyle` font-size under 11px, no document-level horizontal overflow.
- Network log: no request to `fonts.googleapis.com`/`fonts.gstatic.com` for the app's own type; `document.fonts` shows `Archivo Variable`, `Inter Variable`, `Newsreader Variable` and `Barlow Semi Condensed` loaded. The one remaining `fonts.googleapis.com` hit is Next.js's own dev-mode error-overlay font (`__nextjs-Geist`), unrelated to the app and dev-only.
- `prefers-reduced-motion: reduce` emulated: `.marker-slot`/`.stagger > *`/`.pm-badge` all report `animationDuration: 0s`.
- Player drawer: opened via a profile button, `data-starting-style` transform confirmed sliding in, Escape closes it and it fully unmounts (`.drawer` count 0 afterward).
- Chart kit: `Sparkline`/`BarStrip`/`DeltaBar`/`Scatter` all rendered with sample data; `BarStrip` and `Scatter` tooltips appeared on hover (`[data-slot="tooltip-content"]` text matched); `Scatter` dots report the correct radius (4 / 8 for `highlight`) and are keyboard-focusable.

### Not done / caveats

- Table-row hover styling (`background:rgba(255,255,255,.04)` on hover, no lift) has no current target — no data table in the app has a hover state yet; relevant once Slice C's Stats Lab table exists.
- The four chart-kit components have zero real consumers until Slice A5 (BarStrip in chip cards), B2 (DeltaBar in rank exposure) and C2 (Scatter/Sparkline in Stats Lab and the player drawer).
- `.cand:hover`'s own `transform:translateX(5px)` background-slide effect was already permanently overridden by its pre-existing `candIn` `both`-fill entrance animation before this slice; that's a pre-existing bug, left as-is since fixing it wasn't in scope for V0 (the new `.lift` class was added additively there and only contributes its box-shadow, which isn't blocked).

### Commits

- `d22b74ca` — ui: self-hosted variable fonts, 11px type floor, serif discipline (V0.1)
- `728a8d7f` — ui: motion system - stagger, count-up, FLIP reorder, drawer/toast, pitch and meter animation (V0.2)
- `3d6d643b` — ui: page-shaped skeleton loaders replace the spinner-plus-text state (V0.3)
- `dc3ed076` — ui: shared inline-SVG chart kit (Sparkline, BarStrip, DeltaBar, Scatter) (V0.4)

All four pushed to `origin/main`.

### Exact next action

Slice A — Chip Advisor rebuild (A1 account sync, A2 per-week projection matrix, A3 comparable chip gains, A4 horizon-independent joint chip plan, A5 page redesign consuming the new `BarStrip`, A6 tests). See `PLATFORM_V3_PLAN.md` for the full spec.
