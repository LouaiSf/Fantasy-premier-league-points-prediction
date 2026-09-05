"""Package just the files the Colab pipeline needs into a zip.

Uploading the whole project to Drive means 17,368 files, and 13,228 of those
are per-player CSVs under data/*/players/ that nothing in the pipeline reads.
Drive is slow with file counts like that, so this builds a bundle instead.

Two sizes:

  --minimal   notebook + scripts + all_seasons_data_final.csv   (~51 MB, 10 files)
              Enough to run Colab stages 5-7 (features -> train). Use this if
              the dataset has already been rebuilt locally, which it has if
              scripts/build_dataset.py --write has been run.

  (default)   the above, plus every raw file the dataset rebuild reads
              (~97 MB, 76 files). Lets you run the Colab notebook end to end,
              including the merged_gw repair and the dataset rebuild.

Usage
-----
    python scripts/make_colab_bundle.py
    python scripts/make_colab_bundle.py --minimal
    python scripts/make_colab_bundle.py --out-dir C:/Users/pc/Desktop
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import zipfile

# Everything the notebook and the pipeline scripts are made of.
CODE = [
    'final.ipynb',
    'FPL_Colab.ipynb',
    'requirements.txt',
    'README.md',
]

# Produced by scripts/build_dataset.py. The feature stage reads it, and the
# dataset rebuild lifts the FBref defensive columns out of it.
DATASET = ['all_seasons_data_final.csv']


def raw_inputs() -> list[str]:
    """Files the dataset rebuild (final.ipynb cells 3-34 + 40) reads."""
    paths = ['data/master_team_list.csv']
    seasons = sorted(d for d in os.listdir('data')
                     if os.path.isdir(os.path.join('data', d)) and d[0].isdigit())
    for season in seasons:
        paths.append(f'data/{season}/gws/merged_gw.csv')
        # teams.csv covers the seasons master_team_list.csv is missing;
        # players_raw.csv supplies positions for 2016-17..2019-20.
        for extra in ('teams.csv', 'players_raw.csv'):
            candidate = f'data/{season}/{extra}'
            if os.path.exists(candidate):
                paths.append(candidate)

    # The per-gameweek files, so scripts/rebuild_merged_gw.py can audit each
    # merged_gw.csv against its parts rather than trusting it. 2024-25 is the
    # season the repair actually fixes; 2025-26 and later are included so the
    # audit stays meaningful as new gameweeks arrive.
    for season in ('2024-25', '2025-26', '2026-27'):
        paths.extend(sorted(glob.glob(f'data/{season}/gws/gw*.csv')))
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--minimal', action='store_true',
                    help='skip the raw data/ inputs; start Colab at the feature stage')
    ap.add_argument('--out-dir', default='.', help='where to write the zip')
    args = ap.parse_args()

    paths = list(CODE) + sorted(glob.glob('scripts/*.py')) + list(DATASET)
    if not args.minimal:
        paths += raw_inputs()

    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        print("missing (skipped):")
        for p in missing:
            print(f"  {p}")
        paths = [p for p in paths if os.path.exists(p)]

    name = 'fpl_colab_minimal.zip' if args.minimal else 'fpl_colab.zip'
    out = os.path.join(args.out_dir, name)

    total = sum(os.path.getsize(p) for p in paths)
    print(f"bundling {len(paths)} files, {total / 1e6:.1f} MB uncompressed")

    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in paths:
            zf.write(p, p.replace(os.sep, '/'))

    print(f"\nwrote {out} ({os.path.getsize(out) / 1e6:.1f} MB)")
    print("\nNext:")
    print(f"  1. upload {name} to the top level of your Google Drive (My Drive)")
    print("  2. colab.research.google.com -> File -> Upload notebook -> FPL_Colab.ipynb")
    print("  3. Runtime -> Change runtime type -> CPU, High-RAM")
    if args.minimal:
        print("  4. run sections 0-2, then skip to section 5 (feature engineering)")
    else:
        print("  4. Runtime -> Run all")
    print("\nDo not unzip it yourself -- section 1 of the notebook does that.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
