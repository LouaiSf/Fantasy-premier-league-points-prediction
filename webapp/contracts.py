"""Request contract for the JSON API: parsing, validation and error codes.

Every route reads its input through this module so that a malformed request is
always a 4xx with a machine-readable `code`, never a generic 500 from an
unexpected type three calls deep.

    {"ok": false, "error": "<sentence for a person>", "code": "<slug>", "field": "<name>"}

`field` is present when one input is at fault. Codes in use:

    invalid_json          body is not JSON (or contains NaN / Infinity)
    invalid_body          body is JSON but not an object
    invalid_field         a field has the wrong type, is non-finite or out of range
    unknown_player        an element ID or name is not in the prediction set
    invalid_squad         the players supplied do not form a legal squad
    predictions_unavailable / market_prices_unavailable
                          the server has no data to answer with (503)
    refresh_auth_required / refresh_disabled / refresh_cooldown / rate_limited /
    refresh_in_progress   see the refresh endpoints
    not_found / method_not_allowed / payload_too_large / http_error
    internal_error        anything unexpected (500); details go to the server log

Numbers are JSON numbers only -- "12" is not 12 -- and never NaN or infinite.
Booleans are not numbers. `null` means "not supplied" for optional fields.

Every /api response carries `api_contract_version` and an X-API-Contract-Version
header. Bump API_CONTRACT_VERSION on any change a client could observe: a field
renamed or removed, a code changed, a stricter validation rule. /api/chips
additionally keeps its own `contract_version`, owned by the chip advisor.
"""

from __future__ import annotations

import json
import math

API_CONTRACT_VERSION = 2

# Nothing in this API legitimately takes more than a few kilobytes.
MAX_BODY_BYTES = 256 * 1024
MAX_LIST_ITEMS = 100
MAX_NAME_LENGTH = 100


class RequestError(Exception):
    """A request the server will not process; carries everything the reply needs."""

    def __init__(self, message: str, code: str = 'invalid_field',
                 field: str | None = None, status: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field
        self.status = status

    def body(self) -> dict:
        payload = {'ok': False, 'error': self.message, 'code': self.code}
        if self.field:
            payload['field'] = self.field
        return payload


def _reject_constant(name: str):
    # json.loads accepts NaN / Infinity / -Infinity by default. They are not JSON.
    raise ValueError(f'{name} is not allowed')


def read_json_object(req) -> dict:
    """The request body as a dict. An empty body is an empty object."""
    raw = req.get_data(cache=True)
    if not raw or not raw.strip():
        return {}
    try:
        body = json.loads(raw.decode('utf-8'), parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError) as exc:
        detail = str(exc) if 'not allowed' in str(exc) else 'could not be parsed'
        raise RequestError(f'request body is not valid JSON ({detail})', 'invalid_json') from None
    if not isinstance(body, dict):
        raise RequestError('request body must be a JSON object', 'invalid_body')
    return body


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def number(source: dict, field: str, default=None, *, lo=None, hi=None,
           integer: bool = False, range_message: str | None = None):
    """An optional finite number (or whole number) within [lo, hi]."""
    value = source.get(field)
    if value is None:
        return default
    if not _is_number(value):
        raise RequestError(f'{field} must be a number', 'invalid_field', field)
    if not math.isfinite(value):
        raise RequestError(f'{field} must be a finite number', 'invalid_field', field)
    if integer:
        if isinstance(value, float):
            if not value.is_integer():
                raise RequestError(f'{field} must be a whole number', 'invalid_field', field)
            value = int(value)
    elif isinstance(value, int):
        value = float(value)
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise RequestError(range_message or f'{field} must be between {lo} and {hi}',
                           'invalid_field', field)
    return value


def query_number(args, field: str, default, *, lo=None, hi=None, integer: bool = False):
    """number(), for query-string values, which arrive as text."""
    raw = args.get(field)
    if raw is None or raw == '':
        return default
    try:
        parsed = float(raw)
    except ValueError:
        raise RequestError(f'{field} must be a number', 'invalid_field', field) from None
    return number({field: parsed}, field, default, lo=lo, hi=hi, integer=integer)


def boolean(source: dict, field: str, default: bool) -> bool:
    value = source.get(field, default)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise RequestError(f'{field} must be true or false', 'invalid_field', field)
    return value


def int_list(source: dict, field: str, *, message: str | None = None,
             minimum: int = 1, maximum: int | None = None,
             required: bool = False) -> list[int] | None:
    """A list of whole numbers, e.g. FPL element IDs. None when not supplied."""
    value = source.get(field)
    if value is None:
        if required:
            raise RequestError(message or f'{field} is required', 'invalid_field', field)
        return None
    bad = (not isinstance(value, list) or len(value) > MAX_LIST_ITEMS
           or any(isinstance(item, bool) or not isinstance(item, int) or item < minimum
                  or (maximum is not None and item > maximum) for item in value))
    if bad:
        raise RequestError(message or f'{field} must be a list of whole numbers',
                           'invalid_field', field)
    return value


def name_list(source: dict, field: str) -> list[str]:
    """A list of player names. Blank entries are ignored; anything else must be text."""
    value = source.get(field)
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS or any(
            not isinstance(item, str) or len(item) > MAX_NAME_LENGTH for item in value):
        raise RequestError(f'{field} must be a list of player names', 'invalid_field', field)
    return [item.strip() for item in value if item.strip()]


def selling_prices(source: dict, owned_elements: set[int] | None,
                   field: str = 'selling_prices_tenths') -> dict[int, float] | None:
    """{element: price in £m} from {"element": tenths}, covering exactly the owned squad."""
    raw = source.get(field)
    if raw is None:
        return None
    if not isinstance(raw, dict) or len(raw) > MAX_LIST_ITEMS:
        raise RequestError(f'{field} must be an object of element ID to tenths of a million',
                           'invalid_field', field)
    try:
        parsed = {int(key): value for key, value in raw.items()}
    except (TypeError, ValueError):
        raise RequestError(f'{field} keys must be numeric FPL element IDs',
                           'invalid_field', field) from None
    if any(not _is_number(value) or not math.isfinite(value) or value < 0
           for value in parsed.values()):
        raise RequestError(f'{field} values must be finite nonnegative numbers',
                           'invalid_field', field)
    if any(not float(value).is_integer() for value in parsed.values()):
        raise RequestError(f'{field} values must be whole-number tenths',
                           'invalid_field', field)
    if owned_elements is None:
        raise RequestError(f'{field} requires a 15-player squad in this request',
                           'invalid_field', field)
    if set(parsed) != owned_elements:
        raise RequestError(f'{field} must have exactly one entry per owned element',
                           'invalid_field', field)
    return {element: tenths / 10.0 for element, tenths in parsed.items()}


def chip_inventory(source: dict, field: str = 'chip_inventory') -> dict | None:
    """The chip inventory must be an object; the advisor normalises what is inside it."""
    value = source.get(field)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise RequestError(f'{field} must be an object', 'invalid_field', field)
    return value
