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
    cost_change_event: int
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
                cost_change_event=_integer(row.get("cost_change_event")),
                photo=(
                    f"https://resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png"
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


class PlayerHistoryRecord(TypedDict):
    season: str
    gameweek: int
    opponent: str
    opponent_name: str
    was_home: bool
    total_points: int
    minutes: int
    goals_scored: int
    assists: int
    clean_sheets: int
    bonus: int
    bps: int
    ict_index: float


def player_history(
    root: Path,
    season: str,
    element_id: int,
    limit: int = 8,
) -> list[PlayerHistoryRecord]:
    history: list[PlayerHistoryRecord] = []
    season_dir = root / "data" / season
    merged_path = season_dir / "gws" / "merged_gw.csv"
    teams_path = season_dir / "teams.csv"

    team_names: dict[int, tuple[str, str]] = {}
    teams_by_name: dict[str, tuple[str, str]] = {}
    if teams_path.exists():
        for row in _read_rows(teams_path):
            tid = _integer(row.get("id"))
            short_name = row.get("short_name", "")
            full_name = row.get("name", "")
            team_names[tid] = (short_name, full_name)
            if full_name:
                teams_by_name[full_name.casefold()] = (short_name, full_name)

    def _opponent(raw: object) -> tuple[str, str]:
        """Resolve opponent_team, which is an id in some seasons and a name in others.

        vaastav's merged_gw.csv stores the opponent as a team id. The olbauday
        translation resolves it to a club name at fetch time, and
        build_dataset.py maps ids to names for any season it appends
        generically -- so by the time a season reaches this function the column
        may hold either. Reading it as an id unconditionally turned every
        2026-27 fixture in the drawer into "Team 0 (A)".
        """
        text = str(raw or "").strip()
        if not text:
            return ("", "Unknown")
        named = teams_by_name.get(text.casefold())
        if named:
            return named
        opp_id = _integer(raw)
        return team_names.get(opp_id, ("", text if not text.isdigit() else f"Team {opp_id}"))

    player_name: str | None = None
    if merged_path.exists():
        rows = _read_rows(merged_path)
        player_rows = [r for r in rows if _integer(r.get("element")) == element_id]
        if player_rows:
            player_name = player_rows[0].get("name")
            for r in player_rows:
                short_opp, full_opp = _opponent(r.get("opponent_team"))
                history.append({
                    "season": season,
                    "gameweek": _integer(r.get("GW") or r.get("round")),
                    "opponent": short_opp,
                    "opponent_name": full_opp,
                    "was_home": str(r.get("was_home", "")).lower() == "true",
                    "total_points": _integer(r.get("total_points")),
                    "minutes": _integer(r.get("minutes")),
                    "goals_scored": _integer(r.get("goals_scored")),
                    "assists": _integer(r.get("assists")),
                    "clean_sheets": _integer(r.get("clean_sheets")),
                    "bonus": _integer(r.get("bonus")),
                    "bps": _integer(r.get("bps")),
                    "ict_index": _decimal(r.get("ict_index")),
                })

    if len(history) < limit:
        prev_season = "2025-26" if season == "2026-27" else None
        if prev_season:
            prev_dir = root / "data" / prev_season
            prev_merged = prev_dir / "gws" / "merged_gw.csv"
            prev_teams_path = prev_dir / "teams.csv"
            prev_teams: dict[int, tuple[str, str]] = {}
            prev_by_name: dict[str, tuple[str, str]] = {}
            if prev_teams_path.exists():
                for row in _read_rows(prev_teams_path):
                    tid = _integer(row.get("id"))
                    short_name = row.get("short_name", "")
                    full_name = row.get("name", "")
                    prev_teams[tid] = (short_name, full_name)
                    if full_name:
                        prev_by_name[full_name.casefold()] = (short_name, full_name)
            if prev_merged.exists():
                prev_rows = _read_rows(prev_merged)
                matched_prev = [r for r in prev_rows if (player_name and r.get("name") == player_name)]
                for r in reversed(matched_prev):
                    if len(history) >= limit:
                        break
                    raw_opp = str(r.get("opponent_team") or "").strip()
                    short_opp, full_opp = prev_by_name.get(
                        raw_opp.casefold(),
                        prev_teams.get(_integer(raw_opp),
                                       ("", raw_opp or "Unknown")),
                    )
                    history.insert(0, {
                        "season": prev_season,
                        "gameweek": _integer(r.get("GW") or r.get("round")),
                        "opponent": short_opp,
                        "opponent_name": full_opp,
                        "was_home": str(r.get("was_home", "")).lower() == "true",
                        "total_points": _integer(r.get("total_points")),
                        "minutes": _integer(r.get("minutes")),
                        "goals_scored": _integer(r.get("goals_scored")),
                        "assists": _integer(r.get("assists")),
                        "clean_sheets": _integer(r.get("clean_sheets")),
                        "bonus": _integer(r.get("bonus")),
                        "bps": _integer(r.get("bps")),
                        "ict_index": _decimal(r.get("ict_index")),
                    })

    return history[-limit:]
