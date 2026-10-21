# FPL Assistant — Stadium Wayfinding

Version 2.0. Replaces the 1.x "Broadcast" system. Applies to every screen in `webapp/frontend`.
Stylesheets: `app/styles/system.css` (tokens, shell, primitives), `team.css` (gate 1), `screens.css`
(gates 2–8), `drawer.css` (overlays), imported from `app/layout.tsx` after Tailwind so they win.
Shared signage components live in `components/signage.tsx`; icons in `components/icons.tsx`.

## 1. Idea

The app is signed like a Premier League stadium concourse: you always know which gate you are at,
what the call is, and where to go next. Premier League colours and a Premier-Sans-like face are a
brand commitment (see PRODUCT.md). Copy is human: no model scores, R², model names, IDs or
methodology strings anywhere on the surface.

Three moves carry the world:

1. **Numbered gates.** Eight destinations, numbered 1–8 in the rail, on each page's gate sign and in
   the phone gate bar. The number is also the keyboard shortcut (1–8 outside text fields).
2. **One verdict plate per screen.** The decision in plain words, on a PL gradient, with the player it
   is about as a real cutout breaking the plate's top edge.
3. **Signage atoms.** Position blocks, a projection ramp, FDR blocks and limit tracks read the same
   on every screen.

## 2. Colour

| Token | Value | Job |
|---|---|---|
| `--pl-purple` | `#37003C` | Rail, gate signs, primary buttons, ink on luminous fields |
| `--ground` | `#F4F1F6` | Page (light concourse) |
| `--surface` / `--surface-2` | `#FFFFFF` / `#FAF8FB` | Panels, rows |
| `--ink` / `--ink-2` / `--muted` | `#1E0021` / `#4A3A4E` / `#6F5F72` | Text |
| `--line` / `--line-strong` | `#E7E1EA` / `#D3C9D7` | Dividers, input borders |
| `--green` | `#00FF87` | The way forward: go buttons, the active gate edge, strong projections |
| `--pink` | `#E90052` | Out, alerts, sell desk |
| `--cyan` | `#04F5FF` | Focus ring on purple, DEF block |
| `--yellow` | `#EBFF00` | Doubt, GK block |
| `--green-ink` / `--pink-ink` | `#007A3D` / `#C70046` | Positive/negative text on light grounds |
| `--on-purple` / `-2` / `-3` | `#FFF` / `#E6D6E9` / `#BFA4C5` | Text on purple, tinted from the hue |

Gradients (verdict plates only): `--grad-matchday` pink→purple, `--grad-spotlight`
orange→pink→purple (a strong call), `--grad-stats` cyan→green (value/verdict, purple ink),
`--grad-night` (neutral/empty states).

Position blocks: GK yellow, DEF cyan, MID green, FWD pink (white text). FDR uses the official FPL
scale: 1 `#375523`, 2 `#01FC7A`, 3 `#E7E7E7`, 4 `#FF1751`, 5 `#80072D`, each with its own ink and
always with opponent and venue text. Club colours (`lib/club-colors.ts`) only ever back player
cutouts and run cards.

Light ground was chosen from the use scene: dense tables read under any light, and purple plates
carry the identity.

## 3. Type

One family, Archivo Variable (self-hosted via `@fontsource-variable/archivo/wdth.css`), as the open
stand-in for Premier Sans.

| Role | Setting |
|---|---|
| Gate sign title | 900, `font-stretch: 118%`, `--t-sign` clamp(1.9rem → 3rem), -0.02em |
| Verdict plate | 900, 112%, `--t-plate` clamp(2rem → 4.25rem), line-height .95 |
| Section / panel heads | 900, 108–112%, 1.0625–1.375rem |
| Figures | 800–900, `font-stretch: 75–85%`, tabular (`tnum` set on `html`) |
| UI / body | 450–800, 100%, 15px body, 13px small, 12px floor |

No eyebrow or kicker labels above headings, no all-caps label rows, no serif.

## 4. Layout

- Shell: `.app` grid of the 248px purple rail and the stage (content max 1360px, gutter
  clamp(16px, 2.6vw, 40px)). Below 1024px the rail becomes a sticky top bar (brand, compact
  deadline, refresh) and a fixed bottom gate bar (gates 1–4 plus a More sheet for 5–8).
- Page rhythm: `.page` is a 32px-gap grid: gate sign, verdict plate, then work sections.
- `.cols` 1.55fr / 1fr for work + side stack; stacks at 1100px.
- Corners are square. Depth is a light shadow on panels only (`--shadow-1/2`); plates have none.

## 5. Components

- **GateSign** — number tile (purple, green numeral), title, one-sentence lede, actions right.
- **VerdictPlate** — props `tone`, `title`, `body`, `player`, `facts` (`PlateFact`), `actions`,
  `busy`. The cutout uses the player's 500×500 transparent PL photo on a club-colour wedge, clipped
  at the plate's sides and free to break the top edge. On phones the cutout becomes a 150×190 corner
  piece beside the title.
- **Pos**, **Proj** (≥6 solid green, ≥4 green tint, else plain), **Fdr**, **Track** (fills to an end
  stop, turns pink when full), **Face** (cutout on a club-colour square), **Segmented**.
- **Panels/rows**: `.panel`, `.panel-head`, `.prow` (face, name + one human "why" line from
  `lib/why.ts`, position, projection), `.table`, `.callout`, `.disclosure`.
- **Buttons**: `.btn` purple, `.btn--go` green with a moving arrow, `.btn--line`, `.btn--ghost`,
  `.btn--sm`.
- **Pitch**: purple turf with chalk lines; markers are a club tile + white name plate with the
  projection; armbands and availability flags sit on the tile corners.
- **Dossier drawer**: club-colour header with crest watermark and big cutout, status strip, four
  figures, then This week / Next games / Recent points / Season / Transfers sections.

## 6. Motion

Ease `cubic-bezier(.16,1,.3,1)`; 140 / 240 / 520ms. One authored moment per gate change: the gate
number wipes in, the verdict plate wipes in from the left and the cutout rises, and the rail's white
active plate travels between gates. Pitch lines rise in order; deadline figures flip when they change.
`prefers-reduced-motion` collapses all of it while keeping every state.

## 7. Accessibility

AA contrast throughout (secondary text on purple is tinted, never grey). Every control is native.
Focus ring: purple on light, cyan on purple. Meaning never rides on colour alone: FDR carries the
opponent and number, positions carry their letters, doubts carry text. The phone More sheet,
drawer and dialogs are keyboard reachable; the 1–8 shortcuts are ignored while typing or when a
dialog is open.
