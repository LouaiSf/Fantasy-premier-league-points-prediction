# FPL Assistant Broadcast Design System

Version 1.3 — the definitive design vision for the 2026/27 match centre.
Scope: `fpl-assistant-prototype.html`, plus the production Next.js components listed in
§5 "Production components" (`webapp/frontend/`), which consume the same tokens from
`webapp/frontend/app/broadcast.css`. The rest of the production Flask interface is untouched
until a component is added to that list.

## 1. Atmosphere & Identity

FPL Assistant feels like a live Premier League broadcast control room crossed with a sharp Sunday-paper
football supplement: fast, graphic, confident, legible under pressure.

The signature is the **Radiant Mane** — cropped jagged arcs that move between cyan/lime analysis,
magenta/aubergine matchday drama and orange/yellow editorial spotlight — while player cutouts and giant
outlined numerals break their frames.

Two rules separate this from a themed dashboard:

1. **Information is carried by composition, not by chrome.** Hierarchy comes from scale, flat colour
   fields, crests, photography and typography — not from borders, shadows and rounded cards.
2. **Colour is rationed.** See §2. A screen that needs five accents to be understood has failed.

## 2. Colour

### Palette

| Role | Token | Value | Usage |
|---|---|---:|---|
| PL canvas | `--pl-purple` | `#37003C` | Persistent navigation and identity |
| Stadium void | `--night-900` | `#1A0022` | Deepest page background |
| Stadium layer | `--night-850` / `--night-800` | `#1F0027` / `#25002C` | Elevated dark regions |
| Stadium mid | `--night-700` | `#430048` | Dividers and secondary purple |
| Pitch white | `--white` | `#FFFFFF` | Primary text and white broadcast panels |
| Paper | `--paper` | `#F5F2F3` | Editorial data fields |
| Ink | `--ink` | `#210025` | Text on luminous/white surfaces |
| Muted light / mid / ink | `--muted-light` / `--muted-mid` / `--muted-ink` | `#CBBCCF` / `#9D88A3` / `#6C5B6D` | Supporting text |
| Electric cyan | `--cyan` | `#04F5FF` | Focus ring and stats-mode identity |
| Volt lime | `--lime` | `#00FF87` | Primary action, positive value, selected state |
| Neon pink | `--pink` | `#E90052` | Alert, negative value, outgoing transfer |
| Sunset orange | `--orange` | `#FF5E00` | Captain spotlight gradient only |
| Hot yellow | `--yellow` | `#EBFF00` | Spotlight contrast and hazard blade |
| Captain gold | `--gold` | `#FFD45A` | Armband badge |
| FDR 1–5 | `--fdr-1` … `--fdr-5` | `#257D5A` `#00CC6A` `#B0B0B0` `#E90052` `#7B0033` | Fixture difficulty field |

Club identity is a two-stop pair per club (`--c1`, `--c2`) set inline from `CLUBS`, never a neutral grey.

### Gradient recipes

- `--gradient-stats`: cyan → lime. Stats Centre / My Team hero.
- `--gradient-matchday`: pink → PL purple. Transfer impact.
- `--gradient-spotlight`: orange → pink → purple. Captain lead recommendation.
- Club panels always use the relevant two-stop club pair.

### Colour discipline (the rule that keeps it off-template)

- **Purple and white are the system. One accent carries a context, and the context header carries it** —
  as a *flat block of colour*, not as a thin neon rail on every panel. The Transfer Studio proves the
  rule: a solid pink `PLAYER OUT` band, a solid lime `PLAYER IN` band, and nothing else competing.
- **Lime means state, never data.** Primary action, selected row, positive delta. A projection column
  rendered lime on all 36 rows is decoration, and was removed.
- **Pink means alert or negative.** Nothing else.
- **Selected filters and tabs are a white block with ink text**, not a coloured one. Quiet, and closer to
  the real Premier League UI than a lime chip.
- Cyan is reserved for the focus ring and the Stats Centre gradient. It is not a UI accent.
- FDR is the one place a full-chroma field is correct — it is the data.
- FDR, injury state, captaincy and comparison leadership always carry a text or numeric cue as well as
  colour.

## 3. Typography

Four roles, and they must stay distinguishable. The licensed faces are not redistributable, so each has a
metric-sympathetic open fallback.

| Role | Stack | Carries |
|---|---|---|
| Display | `"Premier Sans", "Archivo Black", Arial Black` | Enormous headlines, gameweek numerals, squad numbers |
| Product UI | `"Radikal", "Inter", Helvetica Neue` | Navigation, controls, player names, body |
| Editorial | `"Toshi", "Newsreader", Georgia` serif | Analyst reads, quotes, verdicts, tactical insight |
| Data | `"Johnston100", "Barlow Semi Condensed", Archivo` | Prices, clocks, stats, FDR, all tabular values |

**The data face is not a monospace, and this is deliberate.** Johnston100 is a humanist sans with tabular
figures. Substituting a typewriter mono (Roboto Mono, Consolas) reads as a terminal, not a stadium, and
was the single biggest type error in v0.5. A condensed grotesque gives the scoreboard/score-bug feel the
product wants and buys horizontal density in the fixture matrix and stat tables.

Tabular figures are enforced with `font-feature-settings: "tnum" 1, "lnum" 1` on `:root` rather than
`font-variant-numeric`, because the `font:` shorthand used throughout the stylesheet silently resets
`font-variant-numeric` and would leave figures proportional.

### Scale

| Level | Token | Size | Weight | Usage |
|---|---|---:|---|---|
| Stadium display | `--type-display-xl` | `clamp(3.5rem, 11vw, 10rem)` | 900 | Giant GW and silhouette numerals |
| Display | `--type-display` | `clamp(2.5rem, 5.8vw, 6rem)` | 900 | Page hero titles |
| H1 | `--type-h1` | `clamp(2rem, 4vw, 4.25rem)` | 900 | Major screen heading |
| H2 | `--type-h2` | `clamp(1.4rem, 2.4vw, 2.4rem)` | 800 | Section heading |
| H3 | `--type-h3` | `1.125rem` | 700 | Card/player title |
| Body | `--type-body` | `0.9375rem` | 450 | Product copy |
| Small | `--type-small` | `0.8125rem` | 550 | Supporting copy |
| Caption | `--type-caption` | `0.6875rem` | 700 uppercase | Broadcast labels |

## 4. Spacing & Layout

Base unit 4px; `--space-1` … `--space-20` (4 → 80px).

- Content maximum `1440px` (`.shell`), `1720px` for the three-column Transfer Studio (`.shell-wide`).
- Crest ticker and main navigation are sticky; the document owns vertical scrolling.
- Screens are document sections toggled by the tablist. The active tab indicator (`.nav-ink`) travels.
- **Named scroll regions** are permitted where the surface is a working list rather than a reading
  surface: the fixture matrix reel (horizontal), the two Transfer Studio desk lists, and the comparison
  team sheet. Each is keyboard reachable and labelled. Everything else scrolls with the document.
- Asymmetric 7/5 and 8/4 compositions are preferred over uniform mosaics.
- Border radii are intentionally mixed and mostly absent: compact controls 4px, broadcast panels 12px,
  hero arenas 20px. Endless 16px rounded rectangles are prohibited.

## 5. Components

### Chrome
- **CrestTicker** — 20 club crests, hover/focus highlights every element of that club across the screen.
- **BroadcastNav** — tablist with a travelling lime blade, unread count on News Wire.
- **DeadlineClock** — live countdown plus a deadline tension bar that fills as the lock approaches.

### Primitives
- **ScoreBug** (`.bug`) — label/value pair, neutral white rail. Not colour-coded per instance.
- **Meter**, **Dial** — `--d` is unitless and multiplied to px inside the component, so every call site
  passes a number.
- **FdrCell / FixChip / FixtureRibbon** — difficulty 1–5 plus blank and double, always with opponent,
  venue and the numeric value.
- **PointsSequence / FormLadder** — the ladder adds the opponent, venue and a dotted season-average line;
  a bar chart alone is not a form graphic.
- **PhotoFallback** — a failed portrait becomes a club-gradient roundel of initials at small sizes and a
  ghosted outline mark inside large cutout slots, sized in JS from the container. The layout never
  collapses because a CDN image 404s.

### Screen components
- **PlayerMarker** — cutout, club ring, projected-points bug, availability flag, armband, fixture tag.
- **PlayerDossier** (drawer) — club-spined, six numbered slates: the read (editorial), matchday, form
  ladder, fixture ribbon, output table with positional percentile ranks, market. One action bar. Drawer
  actions are an isolated event boundary: close completes before Compare or Transfer changes screen, so
  an action can never bubble back into the player-open trigger.
- **TransferDesk / TransferChannel** — the outgoing and incoming desks are deliberately quiet: a single
  price line and one projected-points read per row. The desk is capped to the relevant shortlist until
  a search or filter asks for more. The full move is staged in one wide horizontal channel above them;
  its compact decision read appears only when a move exists, while the deeper impact breakdown remains
  a progressive disclosure below. Scout reasoning appears only on the selected incoming player.
- **TeamSheet** — the comparison picker: a printed squad list grouped by position with sticky position
  slates. Explicitly *not* a grid of identical tiles.
- **CandidateRunway** — ranked captaincy board; the lead candidate becomes a club-gradient row.
- **LeadStory** — the News Wire interruption: hazard blade, oversized crop breaking the frame, severity
  badges, serif quote, squad-impact panel, source reliability dial.
- **NewsViewSwitch** — one filtered wire can be read three ways without creating parallel data: **Desk**
  is the full editorial control room; **Cards** is the calm scan-friendly briefing grid; **Reel** is a
  horizontal, image-led picture line. It is a native tablist: the active view is announced, inactive
  panels are hidden, and the same filters drive every view. The Reel is deliberately user-driven
  (scroll snap plus previous/next controls), never an auto-moving carousel.
- **Disclosure** — single-open accordion, ten comparison categories.
- **VerdictStamp** — rotated circular stamp closing the comparison.

### Production components
Live in `webapp/frontend/`, styled from the same `--pl-purple`/`--pink`/`--lime`/`--cyan` tokens and
`PlayerPhoto` fallback as the prototype — no parallel accent palette.
- **ChipsPage** (`app/chips/page.tsx`) — chip planning desk: inventory tracker, next-decision banner,
  per-chip advisor cards, fixture heatmap. `.chip-error` is a solid `--pink`-bordered inline banner with
  a Retry action; it must never be replaced by a silent empty state or an uncaught crash.
- **My Team** (`app/team/page.tsx`, `components/team/squad-editor.tsx`,
  `components/team/manager-lineup-preview.tsx`, `components/team/team-plan.tsx`, `components/team/pitch.tsx`)
  — owned-squad finance and lineup editor. Distinguishes current market value from selling value; never
  uses `is-over`/red budget styling for a legally appreciated squad.

## 6. Motion

| Token | Value | Use |
|---|---|---|
| `--motion-fast` | `140ms` | Press, icon, colour feedback |
| `--motion-ui` | `220ms` | Tabs, hover lift, filters |
| `--motion-panel` | `420ms` | Screen/accordion reveal |
| `--motion-stage` | `560ms` | Drawer and staged reveals |
| `--ease-out` | `cubic-bezier(.22,1,.36,1)` | Entrances |
| `--ease-snap` | `cubic-bezier(.34,1.56,.64,1)` | Short directional swap |

Motion serves state: the drawer enters like a broadcast panel, the horizontal transfer lane animates only
when both ends are filled, the comparison arena reveals on the second selection, and the news-view tab
indicator moves between reading modes. The Reel itself never auto-advances. The nav blade travels between
destinations. `prefers-reduced-motion: reduce` removes transforms, the ticker crawl, the lane flow and
reveal staggering while preserving every state change.

## 7. Depth & Surfaces

Layered broadcast planes, not a card grid. Purple shell depth is a three-layer recipe: tonal shift, a 1px
low-alpha white rim, and a directional ambient glow. Blur is used only on the drawer scrim, the sticky
nav and the lead-story panel. White editorial regions use crisp dividers and no floating shadow. Club
panels use hard gradient light and clipped graphic shapes rather than grey elevation.

## 8. Accessibility & Accepted Debt

- WCAG 2.2 AA contrast for functional text; luminous lime/yellow surfaces always take dark ink.
- Every control is a native button, switch, select or input, and is keyboard reachable.
- The player drawer is a labelled `role="dialog"`, traps Tab, closes on Escape, and returns focus to the
  marker that opened it.
- At 560px and below, the Captain Spotlight score bugs become a 2 × 2 broadcast grid and section
  annotations wrap; decorative player crops may bleed inside their clipped hero but never widen the page.
- At the same narrow breakpoint, five-player formation lines use compact 60px markers with zero explicit
  gap so every profile target remains fully inside the turf. Squad alerts recompose into a label/action
  rail above a full-width message instead of squeezing all three into one row.
- The mobile navigation scrolls the active destination into view, the fifth My Team summary stat spans
  the full row, and the Transfer Channel becomes a vertical out → in sequence so labels never clip.
- Fixture-run summaries resolve deliberately as four columns on desktop, a complete 2 × 2 field on
  tablet, and one continuous briefing rail on phone; an orphaned fourth card is never allowed to create
  false empty-panel space. Its overflow fade and scroll cue appear only when later gameweeks are actually
  off-screen; the sticky club column narrows on phone to keep two fixtures visible at once.
- Visible `:focus-visible` ring — cyan on dark, purple on paper.
- Meaning is never colour-only: FDR carries its number, leadership carries a screen-reader "leads",
  availability carries text.
- Images have fixed dimensions and a graceful non-breaking fallback; decorative mane and numeral layers
  are `aria-hidden`.

### Personas
- **Deadline sprinter** — 90 seconds before lock; must reach squad warnings and the armband without
  precision tapping.
- **Data comparer** — keyboard-heavy; must fill two seats, open categories and reach the verdict in
  logical order.
- **Low-vision strategist** — 200% zoom; must read status and FDR without relying on hue.

### Accepted debt
- Proprietary Premier League faces are referenced but not redistributed; open fallbacks are loaded.
  Owner action: drop licensed WOFF2 files into `webapp/static/fonts/` and the named families take over.
- Crest and player photography come from the Premier League CDN for prototype purposes. Production
  publication requires the owner to confirm rights and host local optimised derivatives.
- All figures are seeded prototype data. Nothing is wired to the model, the FPL API or the Flask app.
