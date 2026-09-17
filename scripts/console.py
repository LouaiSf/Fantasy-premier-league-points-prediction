"""Make stdout survive the names in this dataset.

Premier League squads are full of characters cp1252 cannot encode -- Horniček,
Lindelof, Odegaard, Gross, Munoz all carry one. On Windows stdout defaults to
the console codepage, and redirecting it to a file or a pipe keeps that
default, so printing a squad raises UnicodeEncodeError partway through the
starting XI. The optimiser had already solved the integer program by then; the
answer was lost to a print.

errors='replace' rather than strict, because a character that will not encode
should cost a question mark in the output, not the run.
"""

from __future__ import annotations

import sys


def force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is not None:
            try:
                reconfigure(encoding='utf-8', errors='replace')
            except (ValueError, OSError):
                # A stream that cannot be reconfigured is one we did not open;
                # printing is still better than refusing to start.
                pass
