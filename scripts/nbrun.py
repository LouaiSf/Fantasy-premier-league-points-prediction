"""Execute a contiguous range of cells from a notebook, headless.

The pipeline scripts deliberately do not reimplement the notebook's logic.
They locate a range of cells by an anchor string and exec them in a shared
namespace, so whatever fpl_pipeline.ipynb does is exactly what runs -- including the
temporal splits and the coverage guard. Fixing a cell in the notebook fixes
the pipeline with it, and the two cannot drift apart.
"""

from __future__ import annotations

import json
import sys
import time


class _Display:
    """Stand-in for IPython's display(), which some cells call."""

    def __call__(self, *args, **kwargs):
        for a in args:
            print(a)


def load_cells(path: str) -> list[dict]:
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)['cells']


def find_cell(cells: list[dict], needle: str, kind: str = 'code') -> int:
    """Index of the one cell containing `needle`. Raises unless exactly one."""
    hits = [i for i, c in enumerate(cells)
            if c['cell_type'] == kind and needle in ''.join(c['source'])]
    if len(hits) != 1:
        raise LookupError(
            f"expected exactly one cell containing {needle!r}, found {len(hits)}"
            + (f" at {hits}" if hits else "")
        )
    return hits[0]


def run_range(
    notebook: str,
    first: str,
    last: str,
    namespace: dict | None = None,
    extra_cells: list[str] | None = None,
    verbose: bool = True,
) -> dict:
    """Exec every code cell from the cell containing `first` to the one
    containing `last`, inclusive, then any `extra_cells` anchors after that.

    Returns the namespace the cells ran in, so callers can pull results out.
    """
    cells = load_cells(notebook)
    start, end = find_cell(cells, first), find_cell(cells, last)
    if start > end:
        raise ValueError(f"anchor order reversed: cell {start} comes after {end}")

    ns = namespace if namespace is not None else {}
    ns.setdefault('__name__', '__main__')
    ns.setdefault('display', _Display())
    ns.setdefault('get_ipython', lambda: None)

    indices = list(range(start, end + 1))
    for anchor in (extra_cells or []):
        indices.append(find_cell(cells, anchor))

    if verbose:
        print(f"[nbrun] {notebook}: executing {len(indices)} cells "
              f"({start}..{end}" + (f" plus {indices[end - start + 1:]}" if extra_cells else "") + ")")

    for n, i in enumerate(indices, 1):
        cell = cells[i]
        if cell['cell_type'] != 'code':
            continue
        source = ''.join(cell['source'])
        if not source.strip():
            continue
        # Jupyter magics and shell escapes are not valid Python.
        if any(ln.lstrip().startswith(('!', '%')) for ln in source.splitlines() if ln.strip()):
            source = '\n'.join(
                ln for ln in source.splitlines()
                if not ln.lstrip().startswith(('!', '%'))
            )
            if not source.strip():
                if verbose:
                    print(f"[nbrun] cell {i}: skipped (magics only)")
                continue

        head = next((ln for ln in source.splitlines() if ln.strip()), '')[:64]
        if verbose:
            print(f"[nbrun] ({n}/{len(indices)}) cell {i}: {head}")
        started = time.time()
        try:
            exec(compile(source, f"{notebook}#cell{i}", 'exec'), ns)
        except Exception:
            print(f"\n[nbrun] FAILED in cell {i} of {notebook}:\n", file=sys.stderr)
            print(source, file=sys.stderr)
            raise
        elapsed = time.time() - started
        if verbose and elapsed > 5:
            print(f"[nbrun]      ({elapsed:.0f}s)")

    return ns


def stub_boosters_if_absent() -> None:
    """Let the preprocessing cells import xgboost/lightgbm when they are absent.

    The cell range this script runs stops before any model is trained, but it
    passes through the notebook's import cell. This script only ever fits Ridge
    and ElasticNet, so a placeholder that satisfies the import is enough -- and
    it means the ablation runs on a laptop without a booster toolchain.

    Nothing here is ever fitted. If that changes, this must go.
    """
    for name in ('xgboost', 'lightgbm'):
        try:
            __import__(name)
            continue
        except ImportError:
            pass

        import types

        class _Unusable:
            def __init__(self, *_args, **_kwargs):
                raise RuntimeError(
                    f"{name} is not installed. scripts/ablate.py only fits "
                    f"linear models; use scripts/train.py on Colab for boosters."
                )

        module = types.ModuleType(name)
        if name == 'xgboost':
            module.XGBRegressor = _Unusable
        else:
            module.LGBMRegressor = _Unusable
        sys.modules[name] = module
        print(f"note: {name} not installed -- import placeholder in use "
              f"(this script fits linear models only)")
