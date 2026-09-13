# FPL Assistant Platform Progress

Last updated: 2026-09-13
Branch: `web-platform`

## Completed work

- Audited the production Flask app, optimiser integration, prototype, design system, local season data, and Git state.
- Created the requested `web-platform` branch from `origin/main` at `4dee8080`.
- Confirmed the production app already delegates squad and transfer decisions to `scripts/optimise.py`; that seam will be preserved.
- Identified the legitimate local platform inputs: `predictions_next_gw.csv` when generated, `data/<season>/players_raw.csv`, `data/<season>/fixtures.csv`, `data/<season>/teams.csv`, and saved model metadata.

## Current work in progress

- Replacing the monolithic minimal template with a routed, responsive broadcast-style application shell and reusable static assets.
- Connecting My Team, player profiles, transfers, comparison, captaincy, news, and fixtures to the existing Flask APIs and local data.

## Remaining work

- Implement and verify all seven product surfaces.
- Add targeted tests for the new read-only fixture adapter and web routes.
- Run browser QA at 375px, 768px, and 1280px, including keyboard and interaction states.
- Inspect, commit, and push each tested milestone.

## Known blockers or decisions needed

- `predictions_next_gw.csv` is not present. A local-only regeneration attempt failed because the gitignored LightGBM/scaler binaries are absent from `saved_models/`. Exact pipeline message: `GK: missing LightGBM.joblib, scaler.joblib`. The platform must therefore render an honest unavailable-data state until a legitimate prediction export is restored or regenerated; no synthetic production predictions will be added.
- Premier League player photos and crests are external prototype assets. Production publication still requires rights confirmation and locally hosted optimised derivatives, as recorded in `DESIGN.md`.

## Test and verification evidence

- `python scripts/predict_gameweek.py --help` passed.
- `python scripts/predict_gameweek.py --season 2025-26 --no-api --out predictions_next_gw.csv` reached model loading and failed as expected on the missing gitignored model binaries; no output file was created.
- Git working state inspected before implementation; unrelated untracked `jj.html`, `.playwright-cli/`, and existing `output/` artifacts remain untouched.

## Next recommended milestone

Ship the application shell, API client, honest empty/error state, and local fixture adapter as the first tested commit; then layer the seven connected surfaces onto that foundation.
