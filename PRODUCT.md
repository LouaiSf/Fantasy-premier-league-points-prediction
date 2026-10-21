# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Three audiences at once, confirmed by the owner:

- **Serious FPL managers** chasing rank, who come back every gameweek and need fast decisions before the deadline (squad, transfers, captain, chips).
- **The broad FPL public**: keen-but-casual managers who need the platform to guide them, not just hand them numbers.
- **People seeing it as a showcase** (peers, recruiters), who judge it on first look and on how it feels to move around.

## Product Purpose

FPL Assistant is a gameweek decision companion for Fantasy Premier League. It projects every player's points from a locally trained model, then turns those projections into the decisions a manager actually makes: who to field, who to captain, which transfers are worth a hit, when to play a chip, which fixtures to target, and what the news means for their squad. Success is a manager making a better weekly decision faster, and enjoying the place they make it in.

## Positioning

The advice is computed for *this* manager's squad, from projections this project produces itself, through the same optimiser the CLI uses. It is not a generic tips page or a reskinned FPL site.

## Operating Context

- Weekly ritual around the FPL deadline: check the team, read the news, plan transfers, choose a captain, consider chips.
- Used on desktop for planning and on phones close to the deadline.
- A manager can import their real FPL squad by manager ID; squad, drafts and chip inventory otherwise live in the browser.
- Data: Flask API (`webapp/app.py`) serving model projections, prices and fixtures; public FPL API for manager, league and history data.

## Capabilities and Constraints

- Pages that must all keep their function: My Team (squad, lineup, deadline board, transfer-and-lineup plan, manager/league lookup), Transfer Studio, Comparison, Captain & Form, Watchlist, Chip Advisor, Fixture Matrix, News Wire, plus the player dossier drawer.
- Frontend: Next.js 16 / React 19 in `webapp/frontend`, deployed on Vercel; API on Render.
- Projections are estimates; the product never presents them as certainties.

## Brand Commitments

- **Premier League feel stays.** The platform should be recognisably football and of the Premier League world.
- **Human, not vibecoded.** No model scores, R², MAE, accuracy percentages, backtest numbers, "powered by" blurbs, or other developer-facing metrics on the product surface. No redundant numbers repeated for decoration. Numbers appear only when they help a decision (points, price, fixture difficulty, minutes), and copy speaks like a knowledgeable friend, not a dashboard.
- Name: FPL Assistant.

## Evidence on Hand

- Live projections, prices, fixtures, news and player photos/crests from the PL CDN (rights for publication still to be confirmed by the owner).
- No testimonials, user counts or press exist; none may be invented.

## Product Principles

1. Decision first: every screen leads with the call to make this gameweek, then the reasons.
2. Say it like a person: plain verdicts, short reasons, no jargon or metric dumps.
3. Honest about uncertainty without drowning the user in disclaimers.
4. Fast under deadline pressure, on a phone, with one thumb.
5. A place worth returning to every week: alive, crafted, never generic.

## Accessibility & Inclusion

WCAG 2.2 AA for functional text; colour never carries meaning alone (fixture difficulty, availability, captaincy always have a text or numeric cue); full keyboard reach; reduced-motion respected.
