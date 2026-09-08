"""Build all_seasons_data_featured.csv from all_seasons_data_final.csv.

Runs fpl_pipeline.ipynb's own feature-engineering cells (lagged previous-game stats,
opponent strength, rolling player form, context features) rather than
reimplementing them, so this stays in step with the notebook.

This is the memory-hungry stage: ~230k rows expand to ~230 columns. Expect
several GB of peak RAM, which is why it belongs on Colab rather than an 8 GB
laptop.

Usage
-----
    python scripts/build_features.py
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nbrun import run_range  # noqa: E402

NOTEBOOK = 'fpl_pipeline.ipynb'
IN_FILE = 'all_seasons_data_final.csv'
OUT_FILE = 'all_seasons_data_featured.csv'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--notebook', default=NOTEBOOK)
    args = ap.parse_args()

    if not os.path.exists(IN_FILE):
        raise SystemExit(
            f"{IN_FILE} not found. Run scripts/build_dataset.py --write first."
        )

    print("=" * 78)
    print("FEATURE ENGINEERING  (fpl_pipeline.ipynb cells 83..101)")
    print("=" * 78)
    print(f"input:  {IN_FILE} ({os.path.getsize(IN_FILE) / 1e6:.0f} MB)")

    ns = run_range(
        args.notebook,
        first=f"all_seasons_data = pd.read_csv('{IN_FILE}')",
        last=f"all_seasons_data_featured.to_csv('{OUT_FILE}'",
        namespace={'pd': pd, 'np': np},
    )

    featured = ns['all_seasons_data_featured']
    print("\n" + "=" * 78)
    print("RESULT")
    print("=" * 78)
    print(f"{OUT_FILE}: {featured.shape[0]:,} rows x {featured.shape[1]} columns")

    kinds = {
        'lagged (_prev_)': [c for c in featured.columns if '_prev_' in c],
        'rolling (_rolling_)': [c for c in featured.columns if '_rolling_' in c],
        'opponent': [c for c in featured.columns if c.startswith('opponent_')],
        'strength/advantage': [c for c in featured.columns
                               if 'strength' in c or 'advantage' in c],
    }
    for name, cols in kinds.items():
        print(f"  {name:<22} {len(cols):>4}")

    print(f"\nrows per season:")
    print(featured.groupby('season').size().to_string())
    print(f"\nwrote {OUT_FILE} "
          f"({os.path.getsize(OUT_FILE) / 1e6:.0f} MB)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
