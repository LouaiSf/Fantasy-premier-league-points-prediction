from __future__ import annotations

import csv
from pathlib import Path
from typing import Final, TypedDict


class FixtureRecord(TypedDict):
    gameweek: int
    opponent: str
    opponent_name: str
    venue: str
    difficulty: int
    kickoff_time: str


class TeamRecord(TypedDict):
    id: int
    name: str
    short_name: str
    code: int
    fixtures: list[FixtureRecord]


class PlayerRecord(TypedDict):
    element: int
    name: str
    web_name: str
    first_name: str
    team: str
    team_short: str
    position: str
    value_m: float
    status: str
    news: str
    form: float
    total_points: int
    minutes: int
    goals_scored: int
    assists: int
    clean_sheets: int
    bonus: int
    bps: int
    ict_index: float
    expected_goals: float
    expected_assists: float
    selected_by: float
    transfers_in_event: int
    transfers_out_event: int
    chance_of_playing_next_round: int | None
    photo: str | None
    predicted_points: float | None
    points_per_million: float | None


class PlatformSnapshot(TypedDict):
    available: bool
    message: str
    season: str
    gameweek: int | None
    players: list[PlayerRecord]
    teams: list[TeamRecord]


POSITION_NAMES: Final[dict[int, str]] = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _integer(value: str | None, default: int = 0) -> int:
    try:
        return int(float(value or default))
    except ValueError:
        return default


def _decimal(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except ValueError:
        return default


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def latest_local_season(root: Path) -> str | None:
    data_root = root / "data"
    if not data_root.exists():
        return None
    seasons = sorted(
        path.name
        for path in data_root.iterdir()
        if path.is_dir() and path.name[:4].isdigit()
    )
    return seasons[-1] if seasons else None


def build_local_snapshot(
    root: Path,
    season: str,
    horizon: int = 8,
) -> PlatformSnapshot:
    season_root = root / "data" / season
    required = [season_root / name for name in ("teams.csv", "fixtures.csv", "players_raw.csv")]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        return {
            "available": False,
            "message": f"Local platform data is unavailable: {', '.join(missing)} missing.",
            "season": season,
            "gameweek": None,
            "players": [],
            "teams": [],
        }

    team_rows = _read_rows(season_root / "teams.csv")
    teams_by_id = {
        _integer(row.get("id")): TeamRecord(
            id=_integer(row.get("id")),
            name=row.get("name", ""),
            short_name=row.get("short_name", ""),
            code=_integer(row.get("code")),
            fixtures=[],
        )
        for row in team_rows
    }
    fixture_rows = _read_rows(season_root / "fixtures.csv")
    unfinished = [
        _integer(row.get("event"))
        for row in fixture_rows
        if row.get("event") and row.get("finished", "").lower() != "true"
    ]
    gameweek = min(unfinished) if unfinished else None
    if gameweek is not None:
        last_gameweek = gameweek + horizon - 1
        for row in fixture_rows:
            event = _integer(row.get("event"))
            if event < gameweek or event > last_gameweek:
                continue
            home = teams_by_id.get(_integer(row.get("team_h")))
            away = teams_by_id.get(_integer(row.get("team_a")))
            if home is None or away is None:
                continue
            home["fixtures"].append(
                FixtureRecord(
                    gameweek=event,
                    opponent=away["short_name"],
                    opponent_name=away["name"],
                    venue="H",
                    difficulty=_integer(row.get("team_h_difficulty"), 3),
                    kickoff_time=row.get("kickoff_time", ""),
                )
            )
            away["fixtures"].append(
                FixtureRecord(
                    gameweek=event,
                    opponent=home["short_name"],
                    opponent_name=home["name"],
                    venue="A",
                    difficulty=_integer(row.get("team_a_difficulty"), 3),
                    kickoff_time=row.get("kickoff_time", ""),
                )
            )

    players: list[PlayerRecord] = []
    for row in _read_rows(season_root / "players_raw.csv"):
        team = teams_by_id.get(_integer(row.get("team")))
        if team is None:
            continue
        code = _integer(row.get("code"))
        first_name = row.get("first_name", "").strip()
        second_name = row.get("second_name", "").strip()
        chance_text = row.get("chance_of_playing_next_round", "")
        chance = _integer(chance_text) if chance_text not in {"", "None"} else None
        players.append(
            PlayerRecord(
                element=_integer(row.get("id")),
                name=f"{first_name} {second_name}".strip(),
                web_name=row.get("web_name", second_name),
                first_name=first_name,
                team=team["name"],
                team_short=team["short_name"],
                position=POSITION_NAMES.get(_integer(row.get("element_type")), "MID"),
                value_m=_decimal(row.get("now_cost")) / 10,
                status=row.get("status", "a"),
                news=row.get("news", "").strip(),
                form=_decimal(row.get("form")),
                total_points=_integer(row.get("total_points")),
                minutes=_integer(row.get("minutes")),
                goals_scored=_integer(row.get("goals_scored")),
                assists=_integer(row.get("assists")),
                clean_sheets=_integer(row.get("clean_sheets")),
                bonus=_integer(row.get("bonus")),
                bps=_integer(row.get("bps")),
                ict_index=_decimal(row.get("ict_index")),
                expected_goals=_decimal(row.get("expected_goals")),
                expected_assists=_decimal(row.get("expected_assists")),
                selected_by=_decimal(row.get("selected_by_percent")),
                transfers_in_event=_integer(row.get("transfers_in_event")),
                transfers_out_event=_integer(row.get("transfers_out_event")),
                chance_of_playing_next_round=chance,
                photo=(
                    f"https://resources.premierleague.com/premierleague/photos/players/110x140/p{code}.png"
                    if code
                    else None
                ),
                predicted_points=None,
                points_per_million=None,
            )
        )

    return {
        "available": True,
        "message": "Loaded from the repository's local FPL season snapshot.",
        "season": season,
        "gameweek": gameweek,
        "players": players,
        "teams": sorted(teams_by_id.values(), key=lambda team: team["name"]),
    }
