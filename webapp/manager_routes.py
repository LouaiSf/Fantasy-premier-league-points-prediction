from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from webapp.fpl_client import (
    FplClient,
    FplClientError,
    InvalidUpstreamResponse,
    LeagueNotFound,
    LineupNotFound,
    ManagerNotFound,
    SearchNotConfigured,
    UpstreamUnavailable,
)


def _summary_json(summary) -> dict[str, object]:
    return {
        "entry_id": summary.entry_id,
        "manager_name": summary.manager_name,
        "team_name": summary.team_name,
        "overall_rank": summary.overall_rank,
        "total_points": summary.total_points,
    }


def _error(exc: FplClientError):
    if isinstance(exc, SearchNotConfigured):
        code, status = "search_not_configured", 503
    elif isinstance(exc, ManagerNotFound):
        code, status = "manager_not_found", 404
    elif isinstance(exc, LeagueNotFound):
        code, status = "league_not_found", 404
    elif isinstance(exc, LineupNotFound):
        code, status = "lineup_not_found", 404
    elif isinstance(exc, (InvalidUpstreamResponse, UpstreamUnavailable)):
        code, status = "upstream_unavailable", 502
    else:
        code, status = "upstream_unavailable", 502
    return jsonify({"ok": False, "code": code, "error": str(exc)}), status


def create_manager_blueprint(
    client: FplClient,
    local_element_ids: Callable[[], set[int]],
) -> Blueprint:
    blueprint = Blueprint("managers", __name__, url_prefix="/api/managers")

    @blueprint.get("/search")
    def search_managers():
        query = request.args.get("q", "").strip()
        if not query or len(query) > 80:
            return jsonify({
                "ok": False,
                "code": "invalid_query",
                "error": "query must be between 1 and 80 characters",
            }), 400
        try:
            if query.isdigit():
                results = [_summary_json(client.get_entry(int(query)))]
            else:
                results = [_summary_json(summary) for summary in client.search_text(query)]
            return jsonify({"ok": True, "query": query, "results": results})
        except FplClientError as exc:
            return _error(exc)

    @blueprint.get("/leagues/<int:league_id>/standings")
    def league_standings(league_id: int):
        raw_page = request.args.get("page", "1")
        try:
            page = int(raw_page)
        except ValueError:
            return jsonify({
                "ok": False,
                "code": "invalid_page",
                "error": "page must be a positive integer",
            }), 400
        if page < 1:
            return jsonify({
                "ok": False,
                "code": "invalid_page",
                "error": "page must be a positive integer",
            }), 400
        try:
            standings = client.get_league_standings(league_id, page)
        except FplClientError as exc:
            return _error(exc)
        return jsonify({
            "ok": True,
            "league_id": standings.league_id,
            "league_name": standings.league_name,
            "page": standings.page,
            "has_next": standings.has_next,
            "entries": [
                {
                    "entry_id": entry.entry_id,
                    "manager_name": entry.manager_name,
                    "team_name": entry.team_name,
                    "rank": entry.rank,
                    "total_points": entry.total_points,
                }
                for entry in standings.entries
            ],
        })

    @blueprint.get("/<int:entry_id>/lineup")
    def manager_lineup(entry_id: int):
        raw_gameweek = request.args.get("gameweek")
        try:
            gameweek = None if raw_gameweek is None else int(raw_gameweek)
        except ValueError:
            return jsonify({
                "ok": False,
                "code": "invalid_gameweek",
                "error": "gameweek must be a positive integer",
            }), 400
        if gameweek is not None and gameweek < 1:
            return jsonify({
                "ok": False,
                "code": "invalid_gameweek",
                "error": "gameweek must be a positive integer",
            }), 400
        try:
            lineup = client.get_lineup(entry_id, requested_gameweek=gameweek)
        except FplClientError as exc:
            return _error(exc)
        missing = sorted({
            pick.element for pick in lineup.picks if pick.element not in local_element_ids()
        })
        return jsonify({
            "ok": True,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "fpl_public_api",
            "manager": _summary_json(lineup.summary),
            "requested_gameweek": lineup.requested_gameweek,
            "lineup_gameweek": lineup.lineup_gameweek,
            "bank": lineup.summary.bank,
            "team_value": lineup.summary.team_value,
            "event_points": getattr(lineup, "event_points", None),
            "event_rank": getattr(lineup, "event_rank", None),
            "overall_rank": lineup.summary.overall_rank,
            "total_points": lineup.summary.total_points,
            "active_chip": getattr(lineup, "active_chip", None),
            "missing_elements": missing,
            "picks": [
                {
                    "element": pick.element,
                    "position": pick.position,
                    "multiplier": pick.multiplier,
                    "is_captain": pick.is_captain,
                    "is_vice_captain": pick.is_vice_captain,
                    "purchase_price": pick.purchase_price,
                    "selling_price": pick.selling_price,
                }
                for pick in lineup.picks
            ],
        })

    return blueprint
