# Platform v2 planning handoff

This file preserves the planning state if context is compacted or the work moves to another session. Read `PLATFORM_V2_IMPLEMENTATION_PLAN.md` first. The current task is **planning**, not implementing the application changes.

## User request

Produce a detailed, implementation-ready plan for manager search by name, multi-transfer Studio, Chip Advisor realism, other visual/logical problems, and new features. Specify issue, cause, exact fix, and verification without repetitive QA. Commit and push useful progress, with no `Co-authored-by` trailer. Continue writing a handoff before later context compaction.

## Workspace and safety

- Root: `C:\Users\HP\Desktop\FPL PROJECT - Copy\Fantasy-premier-league-points-prediction`.
- Branch: `main`, remote: `origin` (`LouaiSf/Fantasy-premier-league-points-prediction`).
- Existing dirty/untracked user files were present before this task: `data/2026-27/players_raw.csv`, `predictions_next_gw.csv`, `predictions_next_gw.manifest.json`, `CONTINUE_PROGRESS.md`, `CONTINUE_PROMPT.md`, `IMPLEMENTATION_PROMPT.md`, `debug.log`, and several untracked `webapp/frontend/.agents/`, `.claude/`, `.continue/`, `.kilocode/`, `.qwen/`, `.windsurf/` directories. Leave them untouched and stage only the two `PLATFORM_V2_*.md` files.
- Prefer OMO `mcp__git_bash__run` for shell commands on Windows; PowerShell is suitable for native process management. Do not spawn subagents; current developer instruction prohibits them without an explicit user or AGENTS/skill request.

## Verified findings

1. **Manager search**: `webapp/frontend/components/team/manager-search.tsx` name filtering only covers fetched league standings pages (50 members per page). It auto-scans at most five pages only if the current filter has zero results. Numeric entry IDs work, but `webapp/fpl_client.py::search_text` always raises `SearchNotConfigured`. `webapp/manager_routes.py` has league paging but no global name index. On a 375px viewport, the My Team hero is about 739px high and the manager search starts around document y=931px, so lookup is below the first screen. Plan a prominent direct entry ID/profile URL flow, recent saved accounts, and honest bounded league scanning with coverage/progress; do not claim true global name search without a real data source.
2. **Transfer Studio**: `webapp/frontend/app/transfers/page.tsx` has only scalar `outId`/`inId`. `maxTransfers` changes optimizer count but cannot stage or display multiple individual pairs. Full analysis ignores selected A/B players. Backend `scripts/optimise.py::compute_transfers` already calculates rows for 0..N transfers. `webapp/frontend/components/team/team-plan.tsx` already derives full outgoing/incoming element sets. In live GW6 data, a max-three run yielded 0, 1, 2, and 3-transfer rows; later rows contained multiple names but the broadcast channel still showed one pair. Stage ordered manual pairs separately from optimizer output; never invent an out-to-in pairing for optimizer rows that only provide two sets. Add stable element IDs and locked selections to the optimizer contract if a staged draft is meant to constrain it. The “Hold this week” action currently only displays a toast and does not persist any decision.
3. **Chip Advisor**: Live GW6 auto-picked squad plus saved inventory showed Triple Captain +6.5 and Bench Boost +14.7 both as `PLAY`, while the “Next chip decision” chose Triple Captain because it is first in the fixed chip order. Wildcard showed +45.2 for GW7. `scripts/predict_gameweek.py` already exports expected points after multiplying by appearance probability, but `scripts/optimise.py::_projection_matrix` multiplies those values by availability again. `compute_chips` compares TC, BB, FH, and WC on noncomparable baselines; FH ignores normal free transfers; WC sums an optimized squad versus a frozen squad across the horizon; BB treats gross bench points as chip gain. A fixed 1-point margin (`scripts/chip_policy.py`) labels PLAY without evidence or wait value. `confidence` is hard-coded. Future weeks freeze player state in `predict_gameweek.py`. `_candidate_window` can mishandle a horizon crossing GW19/20. Current owned unavailable players can be missing from the market table used to align the squad, likely causing a server error; reproduce before calling it confirmed. The frontend permits multiple planned chips in one GW. `app/chips/page.tsx` puts a long inventory form before the decision on mobile. Plan a rules engine, projection correction, credible baselines, explicit data quality, single coherent decision, and calibrated thresholds; until validated, show `WATCH/COMPARE`, not `PLAY`.
4. **Other findings**: `app/captain/page.tsx` labels every healthy status “Nailed on”, unsupported by the status field. `components/chrome/main-nav.tsx` news badge counts all player news/status rows rather than unread or squad-specific items. `app/watchlist/page.tsx` and `components/player-drawer.tsx` infer “Promoted/New” from missing training history, which does not prove newness. `DESIGN.md` contains stale copy claiming all figures are seeded prototype data. Preserve its angular broadcast design tokens while improving hierarchy and mobile layouts. Production CSS is `webapp/frontend/app/broadcast.css`.

## External authoritative rule sources

- [Official 2026/27 chips](https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627): two sets, first through GW19 and second from GW20, one chip per GW, FH unavailable GW1, and FH GW19 cannot be followed by FH GW20.
- [Official 2026/27 rule changes](https://www.premierleague.com/en/news/4679873): free transfers roll to five, no AFCON bonus transfers.
- [Official FPL FAQ](https://www.premierleague.com/en/news/4661030): Wildcard and Free Hit unavailable GW1; saved free transfers remain after a chip.

## Completed in this planning turn

- Created `PLATFORM_V2_IMPLEMENTATION_PLAN.md` with the issue/cause/fix matrix, exact search and transfer contracts, chip rules and scoring requirements, mobile composition, ordered implementation slices, feature roadmap, focused tests and one-pass acceptance matrix.
- Checked key file paths and solver entrypoints against the current tree. The production stylesheet is `webapp/frontend/app/broadcast.css`; the player drawer is `webapp/frontend/components/player-drawer.tsx`.
- Reset the temporary 375px browser viewport and closed the hidden localhost audit tab. Stopped only the audited Flask and Next.js development process trees after checking their command lines.
- Preserved all pre-existing dirty/untracked user files. No product code or data files were changed.

## Remaining work

1. Finish final factual/style review of the plan against code and official rules; correct any unsupported claims. Avoid product code changes: user requested a plan.
2. Review `git diff --check` and the full staged diff. Stage only the plan and this handoff, commit with no co-author, and push. Verify commit message/body and remote state. Do not touch the pre-existing dirty files.
3. Confirm the commit is on `origin/main`, then give the user the plan file link, the main findings, and the commit hash. The browser and audit servers have already been cleaned up.

## Suggested execution prompt for the next session

> Continue the FPL Platform v2 planning task from `PLATFORM_V2_HANDOFF.md`. Read the file and inspect current git status before editing. The detailed plan already exists at `PLATFORM_V2_IMPLEMENTATION_PLAN.md`; perform the final review, stage only the two `PLATFORM_V2_*.md` files, commit without any `Co-authored-by` trailer, and push. Preserve all pre-existing dirty files. The user requested an implementation plan, not application changes.
