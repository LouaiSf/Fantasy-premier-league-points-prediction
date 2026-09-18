from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fetch_data import news_first_seen  # noqa: E402


def history(rows: list) -> pd.DataFrame:
    """One playerstats row per player per gameweek, as olbauday writes it."""
    return pd.DataFrame(rows, columns=['id', 'gw', 'news'])


def test_news_first_seen_walks_back_to_when_the_note_appeared() -> None:
    stats = history([
        (1, 1, None),
        (1, 2, 'Knock - 75% chance of playing'),
        (1, 3, 'Knock - 75% chance of playing'),
        (1, 4, 'Knock - 75% chance of playing'),
    ])

    assert news_first_seen(stats) == {1: 2}


def test_news_first_seen_restarts_when_the_note_changes() -> None:
    # A worsening injury is a new note, not a continuation of the old one.
    stats = history([
        (1, 1, 'Groin injury - Unknown return date'),
        (1, 2, 'Groin injury - 25% chance of playing'),
        (1, 3, 'Groin injury - 25% chance of playing'),
    ])

    assert news_first_seen(stats) == {1: 2}


def test_news_first_seen_ignores_a_note_that_has_since_been_cleared() -> None:
    # FPL blanks the note when a player recovers. Carrying the old text on is
    # worse than carrying none, so a cleared note has no date at all.
    stats = history([
        (1, 1, 'Groin injury - Unknown return date'),
        (1, 2, 'Groin injury - 25% chance of playing'),
        (1, 3, None),
    ])

    assert news_first_seen(stats) == {}


def test_news_first_seen_handles_players_independently() -> None:
    stats = history([
        (1, 1, 'Knock - 75% chance of playing'),
        (2, 1, None),
        (1, 2, 'Knock - 75% chance of playing'),
        (2, 2, 'Has joined Al Hilal permanently'),
    ])

    assert news_first_seen(stats) == {1: 1, 2: 2}
