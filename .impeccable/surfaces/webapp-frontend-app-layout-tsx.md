---
version: 1
slug: "webapp-frontend-app-layout-tsx"
primary_target: "webapp/frontend/app/layout.tsx"
related_targets: ["webapp/frontend/app/team/page.tsx","webapp/frontend/app/broadcast.css"]
---

# FPL Assistant app shell and all tool pages

Scope: the whole Next.js app (`webapp/frontend`): shell, My Team, Transfers, Captain, Chips, Fixtures, Compare, Watchlist, News, player dossier. Mode: Operate.

Audience/job: FPL managers (serious and casual) making the weekly decision before the deadline; also judged as a showcase on first look. Pinned by the user: Premier League colours and a Premier-Sans-like face; human copy, no model metrics or dev numbers; player images and profiles stay prominent; every page keeps its function.

## Direction contract

THESIS: The app is signed like a Premier League stadium concourse. You always know which gate you are at, what the call is, and where to go next. It refuses the category default of a dark neon dashboard with a giant hero banner on every page and labels shouting over every number.

OWN-WORLD: PL purple #37003C sign plates and gate rail on a light concourse ground (#F4F1F6), white work surfaces, ink #1E0021. PL green #00FF87 marks the way forward (primary action, the call, positive). Pink #E90052 for out, alerts and negatives. Cyan #04F5FF is the focus ring and data highlight. Position blocks: GK yellow #EBFF00, DEF cyan, MID green, FWD pink, each a solid square block with its letters. Archivo in one family: wide heavy for signs, normal for UI, condensed for figures. Square corners, arrows drawn as SVG chevrons, PL gradients only on sign plates.

STORY: The manager lands on their gate, reads the verdict plate first, sees their players with photos and a one-line why, checks hard limits as tracks, and follows an arrow to the next gate (transfer, captain, chip).

FIRST VIEWPORT: Left: a fixed purple gate rail (brand, eight numbered gates, a live deadline sign at the foot; keys 1-8 jump between gates). Top of the work area: a sign strip with the gameweek, deadline countdown and squad status. Then one dominant verdict plate in a PL gradient with the key player's cutout breaking its top edge and the primary action as a green arrow plate. Below: the working grid (pitch/XI with position blocks and photos, the limits tracks, flagged players). On phones the rail becomes a bottom gate bar plus a menu sheet.

FORM: Stadium Wayfinding & stand signage, position 4 of my ordered list (1 matchday programme, 2 floodlit pitch, 3 sticker album, 4 stadium wayfinding, 5 teletext/vidiprinter, 6 kit craft, 7 bar scarves). seed:396905f6d20ce448. Raises: hard limits are tracks that fill and cannot overflow (from the cassette j-card); every player row carries one plain-language why (from the character catalogue); projections read through one fixed size ramp (from the star atlas); one dominant plate per screen (from the zoo map). Signature interaction: the gate change. The verdict plate slides in like a sign being swapped, and the rail's active gate plate travels between destinations.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
