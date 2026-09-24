from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Final
from urllib import error, parse, request


FPL_API_BASE: Final[str] = "https://fantasy.premierleague.com/api"
FPL_USER_AGENT: Final[str] = "FPL-Assistant/1.0 (public read-only lookup)"
REQUEST_TIMEOUT_SECONDS: Final[float] = 10.0
MAX_RESPONSE_BYTES: Final[int] = 2_000_000
CACHE_TTL_SECONDS: Final[float] = 20.0
CACHE_LIMIT: Final[int] = 64


class FplClientError(Exception):
    pass

class ManagerNotFound(FplClientError):
    pass

class LeagueNotFound(FplClientError):
    pass

class LineupNotFound(FplClientError):
    pass

class UpstreamUnavailable(FplClientError):
    pass

class UpstreamRateLimited(FplClientError):
    pass

class InvalidUpstreamResponse(FplClientError):
    pass

class SearchNotConfigured(FplClientError):
    pass

@dataclass(frozen=True, slots=True)
class ManagerSummary:
    entry_id: int
    manager_name: str
    team_name: str
    overall_rank: int | None
    total_points: int | None
    current_event: int | None
    bank: float | None = None
    team_value: float | None = None


@dataclass(frozen=True, slots=True)
class ManagerPick:
    element: int
    position: int
    multiplier: int
    is_captain: bool
    is_vice_captain: bool
    purchase_price: float | None
    selling_price: float | None


@dataclass(frozen=True, slots=True)
class ManagerLineup:
    summary: ManagerSummary
    requested_gameweek: int | None
    lineup_gameweek: int
    event_points: int | None
    event_rank: int | None
    active_chip: str | None
    picks: tuple[ManagerPick, ...]


@dataclass(frozen=True, slots=True)
class LeagueStandingsEntry:
    entry_id: int
    manager_name: str
    team_name: str
    rank: int | None
    total_points: int | None


@dataclass(frozen=True, slots=True)
class LeagueStandingsPage:
    league_id: int
    league_name: str
    page: int
    has_next: bool
    entries: tuple[LeagueStandingsEntry, ...]


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    expires_at: float
    payload: dict[str, object]


_CACHE: dict[str, _CacheEntry] = {}


def _required_int(data: dict[str, object], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise InvalidUpstreamResponse(f"FPL response field '{key}' is missing")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidUpstreamResponse(f"FPL response field '{key}' is invalid") from exc


def _optional_int(data: dict[str, object], key: str) -> int | None:
    value = data.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(data: dict[str, object], key: str, divisor: float = 1.0) -> float | None:
    value = data.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return round(float(value) / divisor, 1)
    except (TypeError, ValueError):
        return None


def _mapping(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InvalidUpstreamResponse(f"FPL {context} response is not an object")
    return {str(key): item for key, item in value.items()}


def _bool(value: object) -> bool:
    return value is True or value == 1


class FplClient:
    def __init__(self, base_url: str = FPL_API_BASE) -> None:
        self.base_url = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _get_json(
        self, url: str, *, not_found_exc: type[FplClientError] = ManagerNotFound,
        cache_ttl_seconds: float = CACHE_TTL_SECONDS,
    ) -> dict[str, object]:
        now = time.monotonic()
        cached = _CACHE.get(url)
        if cached is not None and cached.expires_at > now:
            return cached.payload
        if cached is not None:
            _CACHE.pop(url, None)

        http_request = request.Request(
            url,
            headers={"User-Agent": FPL_USER_AGENT, "Accept": "application/json"},
            method="GET",
        )
        try:
            with request.urlopen(http_request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                status = getattr(response, "status", None)
                if status is None:
                    status = response.getcode()
                if status == 404:
                    raise not_found_exc("public FPL resource was not found")
                if status == 429:
                    raise UpstreamRateLimited("public FPL API rate limit reached")
                if status < 200 or status >= 300:
                    raise UpstreamUnavailable(f"public FPL API returned HTTP {status}")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except FplClientError:
            raise
        except error.HTTPError as exc:
            if exc.code == 404:
                raise not_found_exc("public FPL resource was not found") from exc
            if exc.code == 429:
                raise UpstreamRateLimited("public FPL API rate limit reached") from exc
            raise UpstreamUnavailable(f"public FPL API returned HTTP {exc.code}") from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise UpstreamUnavailable("public FPL API could not be reached") from exc

        if len(raw) > MAX_RESPONSE_BYTES:
            raise InvalidUpstreamResponse("public FPL API response exceeded the size limit")
        try:
            payload = _mapping(json.loads(raw.decode("utf-8")), "API")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidUpstreamResponse("public FPL API returned invalid JSON") from exc
        _CACHE[url] = _CacheEntry(now + cache_ttl_seconds, payload)
        if len(_CACHE) > CACHE_LIMIT:
            oldest = min(_CACHE, key=lambda key: _CACHE[key].expires_at)
            _CACHE.pop(oldest, None)
        return payload

    def get_entry(self, entry_id: int) -> ManagerSummary:
        if entry_id <= 0:
            raise ManagerNotFound("public FPL entry IDs are positive")
        url = self._url(f"entry/{entry_id}/")
        data = self._get_json(url)
        try:
            resolved_id = _required_int(data, "id")
        except InvalidUpstreamResponse:
            _CACHE.pop(url, None)
            raise
        first = data.get("player_first_name")
        last = data.get("player_last_name")
        manager_name = " ".join(str(part).strip() for part in (first, last) if part).strip()
        if not manager_name:
            manager_name = str(data.get("player_name") or "")
        return ManagerSummary(
            entry_id=resolved_id,
            manager_name=manager_name,
            team_name=str(data.get("name") or ""),
            overall_rank=_optional_int(data, "summary_overall_rank"),
            total_points=_optional_int(data, "summary_overall_points"),
            current_event=_optional_int(data, "current_event"),
            bank=_optional_float(data, "bank", 10.0),
            team_value=_optional_float(data, "value", 10.0),
        )

    def _get_picks(self, entry_id: int, gameweek: int) -> tuple[dict[str, object], list[ManagerPick]]:
        url = self._url(f"entry/{entry_id}/event/{gameweek}/picks/")
        try:
            data = self._get_json(url)
        except ManagerNotFound as exc:
            raise LineupNotFound(f"no public picks for GW{gameweek}") from exc
        raw_picks = data.get("picks")
        if not isinstance(raw_picks, list):
            raise InvalidUpstreamResponse("FPL picks response has no picks list")
        picks: list[ManagerPick] = []
        for raw in raw_picks:
            pick = _mapping(raw, "picks")
            picks.append(ManagerPick(
                element=_required_int(pick, "element"),
                position=_required_int(pick, "position"),
                multiplier=_optional_int(pick, "multiplier") or 0,
                is_captain=_bool(pick.get("is_captain")),
                is_vice_captain=_bool(pick.get("is_vice_captain")),
                purchase_price=_optional_float(pick, "purchase_price", 10.0),
                selling_price=_optional_float(pick, "selling_price", 10.0),
            ))
        picks.sort(key=lambda pick: pick.position)
        return data, picks

    def get_lineup(self, entry_id: int, requested_gameweek: int | None = None) -> ManagerLineup:
        summary = self.get_entry(entry_id)
        start = requested_gameweek or summary.current_event or 1
        if start < 1:
            raise LineupNotFound("no valid public gameweek is available")
        gameweeks = [start] if requested_gameweek is not None else list(range(start, 0, -1))
        for gameweek in gameweeks:
            try:
                payload, picks = self._get_picks(entry_id, gameweek)
            except LineupNotFound:
                continue
            history = _mapping(payload.get("entry_history", {}), "entry history")
            merged = ManagerSummary(
                entry_id=summary.entry_id,
                manager_name=summary.manager_name,
                team_name=summary.team_name,
                overall_rank=_optional_int(history, "overall_rank") or summary.overall_rank,
                total_points=_optional_int(history, "total_points") or summary.total_points,
                current_event=summary.current_event,
                bank=_optional_float(history, "bank", 10.0) if history else summary.bank,
                team_value=_optional_float(history, "value", 10.0) if history else summary.team_value,
            )
            return ManagerLineup(
                summary=merged,
                requested_gameweek=requested_gameweek,
                lineup_gameweek=gameweek,
                event_points=_optional_int(history, "event_points"),
                event_rank=_optional_int(history, "event_rank"),
                active_chip=(str(history["active_chip"]) if history.get("active_chip") else None),
                picks=tuple(picks),
            )
        raise LineupNotFound(f"no public picks found for entry {entry_id}")

    def search_text(self, query: str) -> tuple[ManagerSummary, ...]:
        configured_url = os.environ.get("FPL_MANAGER_SEARCH_URL", "").strip()
        if not configured_url:
            raise SearchNotConfigured("text manager search is not configured")
        parsed = parse.urlparse(configured_url)
        if parsed.scheme not in {"http", "https"}:
            raise SearchNotConfigured("text manager search provider URL is invalid")
        raise SearchNotConfigured(
            "text manager search provider contract is not documented; refusing to guess its fields"
        )

    def get_league_standings(self, league_id: int, page: int = 1) -> LeagueStandingsPage:
        """One page of a classic league's standings: manager name, team name,
        entry ID, rank and points for every member on that page.

        There is no FPL endpoint to search all ~11M managers by name -- that
        would mean crawling every entry ID, which this client deliberately
        does not do. A classic league's standings are the smallest public
        surface that actually supports name search: enumerate a league a
        manager already knows the ID of (their own mini-league, or a public
        one) and filter it client-side.
        """
        if league_id <= 0:
            raise LeagueNotFound("public FPL league IDs are positive")
        if page <= 0:
            raise InvalidUpstreamResponse("page must be a positive number")
        url = self._url(f"leagues-classic/{league_id}/standings/?page_standings={page}")
        data = self._get_json(
            url, not_found_exc=LeagueNotFound, cache_ttl_seconds=60.0)
        league = _mapping(data.get("league", {}), "league")
        standings = _mapping(data.get("standings", {}), "standings")
        raw_results = standings.get("results")
        if not isinstance(raw_results, list):
            raise InvalidUpstreamResponse("FPL league standings response has no results list")
        entries = []
        for raw in raw_results:
            row = _mapping(raw, "standings result")
            entries.append(LeagueStandingsEntry(
                entry_id=_required_int(row, "entry"),
                manager_name=str(row.get("player_name") or ""),
                team_name=str(row.get("entry_name") or ""),
                rank=_optional_int(row, "rank"),
                total_points=_optional_int(row, "total"),
            ))
        return LeagueStandingsPage(
            league_id=league_id,
            league_name=str(league.get("name") or ""),
            page=page,
            has_next=_bool(standings.get("has_next")),
            entries=tuple(entries),
        )
