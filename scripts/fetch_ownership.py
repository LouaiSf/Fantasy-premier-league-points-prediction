"""Sample real FPL teams and save effective ownership for one tier.

Writes data/<season>/ownership/gw<basis>_<tier>.json, which /api/ownership
serves. The basis is the latest gameweek whose deadline has passed: picks are
not public before it. A top-10k or overall sample is about 1,020 requests at
8 a second, so roughly two and a half minutes.

Usage
-----
    python scripts/fetch_ownership.py --tier top10k
    python scripts/fetch_ownership.py --tier top1k --season 2026-27
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from webapp import ownership  # noqa: E402
from webapp.fpl_client import FplClient, FplClientError  # noqa: E402


def latest_season() -> str:
    data = os.path.join(ROOT, 'data')
    return sorted(d for d in os.listdir(data) if d[:4].isdigit() and os.path.isdir(os.path.join(data, d)))[-1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--tier', choices=ownership.TIERS, default='top10k')
    ap.add_argument('--season', default=None)
    args = ap.parse_args(argv)
    season = args.season or latest_season()

    client = FplClient()
    try:
        bootstrap = client.get_bootstrap()
        basis = ownership.basis_gameweek(bootstrap.get('events') or [])
        if basis is None:
            print('No gameweek has started yet, so no teams are public.', file=sys.stderr)
            return 1
        selected = {int(p['id']): float(p.get('selected_by_percent') or 0)
                    for p in bootstrap.get('elements') or []}
        print(f'{args.tier}: sampling GW{basis} teams ...', flush=True)
        report = ownership.build(client, tier=args.tier, gameweek=basis,
                                 total_players=bootstrap.get('total_players'), selected_by=selected)
    except FplClientError as exc:
        print(f'FPL could not be reached: {exc}', file=sys.stderr)
        return 1
    path = ownership.save(ROOT, season, report)
    top = sorted(report['players'].items(), key=lambda kv: -kv[1]['eo_pct'])[:5]
    print(f'{report["sample_size"]} teams ({report["sample_failed"]} failed) -> {os.path.relpath(path, ROOT)}')
    names = {int(p['id']): p['web_name'] for p in bootstrap.get('elements') or []}
    for element, row in top:
        print(f'  {names.get(int(element), element):<16} EO {row["eo_pct"]:6.1f}%  '
              f'owned {row["owned_pct"]:5.1f}%  captain {row["captain_pct"]:5.1f}%')
    return 0


if __name__ == '__main__':
    sys.exit(main())
