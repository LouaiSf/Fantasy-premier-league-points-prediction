# FPL Manager Planner and Chip Advisor Progress

Last updated: 2026-09-22
Plan status: ready; implementation not started

## Repository baseline

- Branch: `main`
- Upstream: `origin/main`
- Starting implementation baseline before the plan commit: `106f6ad9`
- Existing optimizer/API/frontend behavior was inspected and recorded in `FPL_MANAGER_PLANNER_CHIPS_PLAN.md`.

## User-owned worktree state to preserve

The following existed before this plan and must not be staged by feature commits unless the user separately requests it:

- Modified: `all_seasons_data_final.csv`
- Modified: `data/2026-27/fixtures.csv`
- Modified: `data/2026-27/gws/merged_gw.csv`
- Modified: `data/2026-27/players_raw.csv`
- Untracked: existing continuation/prompt notes, `debug.log`, and generated directories under `webapp/frontend/`

Always re-run `git status --short` because the user may add more work between sessions.

## Verified root causes and seams

- ID-based public manager lookup is documented; a global username-search contract is not present in the repository and must not be invented.
- App state already persists squads by `element` ID and can be extended for imported manager metadata.
- `compute_transfers` already calculates the post-transfer lineup internally but does not serialize bench/armbands/formation.
- `predict_gameweek.py --horizon N` and `load_horizon` already exist.
- The current `predictions_next_gw.csv` has only GW5, and `/api/chips` does not pass a future matrix, so future chip advice is a fixture-adjusted reuse of the GW5 baseline.

## Completed

- [x] Repository discovery and architecture trace
- [x] Root-cause analysis for misleading future Triple Captain output
- [x] Implementation plan written
- [x] Luna starting prompt written
- [ ] Plan artifacts committed and pushed

## Implementation phases

- [ ] Phase 1: public-manager adapter and API
- [ ] Phase 2: manager search, preview, and local import
- [ ] Phase 3: combined transfer/lineup plan on My Team
- [ ] Phase 4: real horizon matrix in Chip Advisor
- [ ] Phase 5: auditable chip decision evidence
- [ ] Phase 6: full automated and browser verification

## Next exact action

After confirming the plan commit exists locally and on `origin/main`, begin Phase 1 by locating the real text manager-search API contract in repository configuration/documentation. Then create failing HTTP-boundary tests for numeric entry lookup, lineup event fallback, and the `search_not_configured` text-query behavior before implementing `webapp/fpl_client.py` and `webapp/manager_routes.py`.

## Session entry format

Append one section per completed phase:

```text
## YYYY-MM-DD HH:MM — Phase N: title
Starting SHA:
Files changed:
Behavior completed:
Automated evidence:
Manual browser evidence:
Commit SHA and message:
Push result:
Known issues/blockers:
Next exact action:
```
