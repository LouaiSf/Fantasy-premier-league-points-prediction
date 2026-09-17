from __future__ import annotations

from pathlib import Path

from webapp.platform_data import build_local_snapshot


def test_build_local_snapshot_groups_home_and_away_fixtures(tmp_path: Path) -> None:
    # Given a local FPL season with two clubs and one unfinished fixture.
    season = tmp_path / "data" / "2026-27"
    season.mkdir(parents=True)
    (season / "teams.csv").write_text(
        "id,name,short_name,code\n1,Arsenal,ARS,3\n2,Chelsea,CHE,8\n",
        encoding="utf-8",
    )
    (season / "fixtures.csv").write_text(
        "event,finished,kickoff_time,team_a,team_h,team_h_difficulty,team_a_difficulty\n"
        "4,False,2026-09-19T14:00:00Z,2,1,3,4\n",
        encoding="utf-8",
    )
    (season / "players_raw.csv").write_text(
        "id,first_name,second_name,web_name,team,element_type,now_cost,status,form,total_points,minutes,news,code,selected_by_percent\n"
        "10,Bukayo,Saka,Saka,1,3,101,a,6.4,30,450,,223340,18.2\n",
        encoding="utf-8",
    )

    # When the platform snapshot is built from those checked-in-style CSVs.
    snapshot = build_local_snapshot(tmp_path, "2026-27", horizon=3)

    # Then the same fixture is represented from each club's point of view.
    assert snapshot["gameweek"] == 4
    assert snapshot["teams"][0]["fixtures"][0]["opponent"] == "CHE"
    assert snapshot["teams"][0]["fixtures"][0]["venue"] == "H"
    assert snapshot["teams"][1]["fixtures"][0]["opponent"] == "ARS"
    assert snapshot["teams"][1]["fixtures"][0]["difficulty"] == 4
    assert snapshot["players"][0]["name"] == "Bukayo Saka"


def test_build_local_snapshot_reports_missing_local_files(tmp_path: Path) -> None:
    # Given a season directory without FPL snapshot CSVs.
    (tmp_path / "data" / "2026-27").mkdir(parents=True)

    # When the adapter attempts to build the local snapshot.
    snapshot = build_local_snapshot(tmp_path, "2026-27")

    # Then the boundary reports an honest unavailable state instead of data.
    assert snapshot["available"] is False
    assert snapshot["players"] == []
    assert "fixtures.csv" in snapshot["message"]
