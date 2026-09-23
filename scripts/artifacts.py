"""Versioned, verifiable prediction artifacts.

The deployed site never trains or predicts. It consumes one immutable artifact,
predictions_next_gw.csv, and its manifest:

    predictions_next_gw.csv
    predictions_next_gw.manifest.json    sha256 of the CSV, when and from what

The models that produce the CSV (`saved_models/**/*.joblib`, ~13 MB) are
gitignored, so a fresh clone cannot regenerate it. That is deliberate: training
and prediction are a separate job -- a Colab/GPU run, or scripts/refresh_pipeline.py
on a machine that has the models -- and their output is published as this
artifact. The manifest records a fingerprint of the model bundle that produced
it, so a served prediction can always be traced to (and compared with) the exact
models behind it.

    python scripts/artifacts.py write     # (re)write the manifest for the current CSV
    python scripts/artifacts.py verify    # exit 1 unless the manifest matches the CSV

Status values from describe():

    verified    manifest present and its sha256 matches the CSV
    mismatch    manifest present but the CSV has different bytes (edited by hand,
                or caught between the two atomic replaces of a refresh)
    missing     no manifest: an unversioned artifact
    unreadable  manifest exists but is not valid JSON
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

MANIFEST_SCHEMA = 1
DEFAULT_ARTIFACT = 'predictions_next_gw.csv'
MODEL_DIRS = ('saved_models', os.path.join('fpl_results', 'saved_models'))


def manifest_path(csv_path: str) -> str:
    stem, _ = os.path.splitext(csv_path)
    return stem + '.manifest.json'


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def model_bundle_info(root: str = ROOT) -> dict | None:
    """A fingerprint of the trained models: one hash over every file in the bundle.

    Hashes each .joblib and meta.json by content, then hashes the sorted
    (relative path, file hash) list, so the bundle hash changes if any model,
    scaler, encoder or its metadata does -- and not because of file timestamps.
    """
    for directory in MODEL_DIRS:
        base = os.path.join(root, directory)
        if not os.path.isdir(base):
            continue
        entries = []
        for folder, _dirs, files in os.walk(base):
            for name in files:
                if name.endswith('.joblib') or name == 'meta.json':
                    full = os.path.join(folder, name)
                    entries.append((os.path.relpath(full, base).replace(os.sep, '/'),
                                    sha256_file(full)))
        if not entries:
            continue
        entries.sort()
        bundle = hashlib.sha256(
            '\n'.join(f'{rel}:{digest}' for rel, digest in entries).encode()).hexdigest()
        return {'sha256': bundle, 'files': len(entries), 'directory': directory.replace(os.sep, '/')}
    return None


def _git_commit(root: str) -> str | None:
    try:
        out = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True,
                             text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def build_manifest(csv_path: str, *, season: str, horizon: int, first_gw: int, last_gw: int,
                   players: int, rows: int, root: str = ROOT,
                   generated_at: str | None = None) -> dict:
    return {
        'schema': MANIFEST_SCHEMA,
        'artifact': os.path.basename(csv_path),
        'sha256': sha256_file(csv_path),
        'bytes': os.path.getsize(csv_path),
        'generated_at': generated_at or datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'season': season,
        'horizon': horizon,
        'first_gw': first_gw,
        'last_gw': last_gw,
        'players': players,
        'rows': rows,
        'model_bundle': model_bundle_info(root),
        'code_commit': _git_commit(root),
    }


def write_manifest(csv_path: str, manifest: dict) -> str:
    """Atomically write the manifest next to the CSV."""
    target = manifest_path(csv_path)
    temp = f'{target}.{os.getpid()}.tmp'
    with open(temp, 'w', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write('\n')
    os.replace(temp, target)
    return target


def describe(csv_path: str) -> dict:
    """What the served artifact is: its hash, and whether its manifest vouches for it."""
    info = {
        'artifact': os.path.basename(csv_path),
        'sha256': sha256_file(csv_path),
        'bytes': os.path.getsize(csv_path),
        'manifest_status': 'missing',
        'generated_at': None, 'season': None, 'horizon': None,
        'first_gw': None, 'last_gw': None, 'model_bundle': None, 'code_commit': None,
    }
    path = manifest_path(csv_path)
    if not os.path.exists(path):
        return info
    try:
        with open(path, encoding='utf-8') as handle:
            manifest = json.load(handle)
        if not isinstance(manifest, dict):
            raise ValueError('manifest is not an object')
    except (OSError, ValueError):
        info['manifest_status'] = 'unreadable'
        return info
    info['manifest_status'] = 'verified' if manifest.get('sha256') == info['sha256'] else 'mismatch'
    for key in ('generated_at', 'season', 'horizon', 'first_gw', 'last_gw',
                'model_bundle', 'code_commit'):
        info[key] = manifest.get(key)
    return info


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['write', 'verify'])
    ap.add_argument('--csv', default=os.path.join(ROOT, DEFAULT_ARTIFACT))
    args = ap.parse_args()

    if args.command == 'verify':
        status = describe(args.csv)['manifest_status'] if os.path.exists(args.csv) else 'absent'
        print(f'{args.csv}: {status}')
        return 0 if status == 'verified' else 1

    import pandas as pd
    frame = pd.read_csv(args.csv)
    gameweeks = sorted(int(g) for g in frame['GW'].dropna().unique())
    season = sorted(d for d in os.listdir(os.path.join(ROOT, 'data')) if d[:4].isdigit())[-1]
    manifest = build_manifest(
        args.csv, season=season, horizon=len(gameweeks), first_gw=gameweeks[0],
        last_gw=gameweeks[-1], players=int(frame['element'].nunique()), rows=len(frame))
    print(f'wrote {write_manifest(args.csv, manifest)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
