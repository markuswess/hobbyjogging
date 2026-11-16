"""Read-only Runalyze API access and the field inventory.

Phase 1 of the Runalyze milestone: prove what the API exposes before any
import lands. The client sends the personal token in the ``token`` header (not
``Authorization: Bearer``), paces itself to the documented 240 requests/minute,
and never writes to the database. ``runalyze_import.inventory`` tallies the
activity fields per year and probes the known endpoints, including the four
that currently answer 403.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Protocol

import requests

from .config import runalyze_api_key, runalyze_base_url

REQUESTS_PER_MINUTE = 240
MIN_REQUEST_INTERVAL_S = 60.0 / REQUESTS_PER_MINUTE

# Endpoint label -> path. The collection is singular (`activity`), matching
# the API root at /api. The four 403 endpoints stay listed so the inventory
# reports them explicitly instead of silently omitting them.
INVENTORY_ENDPOINTS = (
    ("ping", "ping"),
    ("activities", "activity"),
    ("equipment", "equipment"),
    ("sport", "sport"),
    ("recurring-route", "recurring-route"),
    ("planned-race", "planned-race"),
    ("device-profile", "device-profile"),
)

ACTIVITY_COLLECTION = "activity"
YEAR_KEYS = ("date_time", "date", "start_date", "start_time", "time")


@dataclass(frozen=True)
class RunalyzeResponse:
    """One HTTP response, including error statuses the caller wants to see."""

    status: int
    headers: dict[str, str]
    payload: object | None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class RunalyzeApi(Protocol):

    def get(
        self,
        path: str,
        params: dict | None = None,
    ) -> RunalyzeResponse:
        ...

    def activities(
        self,
        start: date | None,
        end: date | None,
        *,
        per_page: int = 100,
    ) -> list[dict]:
        ...


class RunalyzeRateLimitError(RuntimeError):
    """Raised when the API answers 429; carries the reset information."""

    def __init__(
        self,
        *,
        retry_after_s: int | None = None,
        reset_at: int | None = None,
        limit: int | None = None,
    ):
        self.retry_after_s = retry_after_s
        self.reset_at = reset_at
        self.limit = limit

        parts = ["Runalyze rate limit exhausted"]
        if limit is not None:
            parts.append(f"limit {limit}")
        if retry_after_s is not None:
            parts.append(f"retry after {retry_after_s} s")
        if reset_at is not None:
            parts.append(
                "resets at "
                + datetime.fromtimestamp(
                    reset_at,
                    tz=timezone.utc,
                ).strftime("%Y-%m-%d %H:%MZ")
            )
        super().__init__("; ".join(parts))


class RunalyzeClient:
    """Read-only Runalyze client with client-side rate limiting."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        timeout: int = 20,
        session: object | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        key = api_key or runalyze_api_key()
        if not key:
            raise RuntimeError("RUNALYZE_API_KEY must be set")

        self.api_key = key
        self.base_url = (base_url or runalyze_base_url()).rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self._clock = clock
        self._sleep = sleep
        self._last_request: float | None = None

    def get(
        self,
        path: str,
        params: dict | None = None,
    ) -> RunalyzeResponse:
        """Return a response without raising on HTTP errors.

        The inventory must report 403s, so the client leaves status handling to
        the caller.
        """
        self._throttle()
        response = self.session.get(
            f"{self.base_url}/{path.lstrip('/')}",
            headers={
                "token": self.api_key,
                "Accept": "application/json",
            },
            params=params,
            timeout=self.timeout,
        )
        self._last_request = self._clock()

        if response.status_code == 429:
            raise RunalyzeRateLimitError(
                retry_after_s=_header_int(
                    response.headers,
                    "Retry-After",
                ),
                reset_at=_header_int(
                    response.headers,
                    "X-RateLimit-Reset",
                ),
                limit=_header_int(
                    response.headers,
                    "X-RateLimit-Limit",
                ),
            )

        try:
            payload = response.json()
        except ValueError:
            payload = response.text or None

        return RunalyzeResponse(
            status=response.status_code,
            headers=dict(response.headers or {}),
            payload=payload,
        )

    def activities(
        self,
        start: date | None,
        end: date | None,
        *,
        per_page: int = 100,
    ) -> list[dict]:
        """Read all activities, following numbered pages.

        The collection ignores its date filters, so every page is read and the
        range is applied locally from ``date_time``.
        """
        items: list[dict] = []
        seen: set[object] = set()
        page = 1

        while True:
            response = self.get(
                ACTIVITY_COLLECTION,
                {"page": page, "itemsPerPage": per_page},
            )
            if not response.ok:
                raise RuntimeError(
                    "Runalyze activity collection failed "
                    f"(HTTP {response.status})"
                )

            batch = _items(response.payload)
            if not batch:
                break

            added = 0
            for item in batch:
                if not isinstance(item, dict):
                    continue
                identifier = item.get("id")
                if identifier is not None:
                    if identifier in seen:
                        continue
                    seen.add(identifier)
                items.append(item)
                added += 1

            # Stop on a short page or a server that ignores pagination.
            if added == 0 or len(batch) < per_page:
                break
            page += 1

        return [
            item
            for item in items
            if _in_range(item, start, end)
        ]

    def _throttle(self) -> None:
        if self._last_request is None:
            return
        elapsed = self._clock() - self._last_request
        wait = MIN_REQUEST_INTERVAL_S - elapsed
        if wait > 0:
            self._sleep(wait)


@dataclass(frozen=True)
class EndpointReport:
    label: str
    status: int
    note: str = ""


@dataclass
class InventorySummary:
    base_url: str = ""
    dry_run: bool = True
    endpoints: list[EndpointReport] = field(default_factory=list)
    activity_count: int = 0
    years: list[int] = field(default_factory=list)
    activities_by_year: dict[int, int] = field(default_factory=dict)
    fields: dict[str, dict[int, int]] = field(default_factory=dict)


def run_inventory(
    api: RunalyzeApi,
    *,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
    per_page: int = 100,
    dry_run: bool = True,
    base_url: str = "",
) -> InventorySummary:
    """Report endpoint availability and activity-field coverage per year."""
    summary = InventorySummary(base_url=base_url, dry_run=dry_run)

    for label, path in INVENTORY_ENDPOINTS:
        params = (
            {"page": 1, "itemsPerPage": 1}
            if path == ACTIVITY_COLLECTION
            else None
        )
        response = api.get(path, params)
        summary.endpoints.append(
            EndpointReport(
                label,
                response.status,
                _endpoint_note(path, response),
            )
        )

    try:
        activities = api.activities(start, end, per_page=per_page)
    except RuntimeError as exc:
        activities = []
        summary.endpoints.append(
            EndpointReport("activities list", 0, str(exc))
        )

    if limit is not None:
        activities = activities[:limit]

    summary.activity_count = len(activities)

    first = activities[0] if activities else None
    identifier = first.get("id") if isinstance(first, dict) else None
    if identifier is not None:
        response = api.get(f"activity/{identifier}")
        summary.endpoints.append(
            EndpointReport(
                "activity detail",
                response.status,
                _endpoint_note("activity", response),
            )
        )

    years: set[int] = set()
    activities_by_year: dict[int, int] = {}
    fields: dict[str, dict[int, int]] = {}
    for activity in activities:
        if not isinstance(activity, dict):
            continue
        year = _activity_year(activity)
        if year is None:
            continue
        years.add(year)
        activities_by_year[year] = activities_by_year.get(year, 0) + 1
        for name, value in activity.items():
            if value is None:
                continue
            counts = fields.setdefault(name, {})
            counts[year] = counts.get(year, 0) + 1

    summary.years = sorted(years)
    summary.activities_by_year = activities_by_year
    summary.fields = fields
    return summary


def format_inventory(summary: InventorySummary) -> str:
    """Render the inventory as a compact terminal report."""
    title = "Runalyze inventory"
    if summary.dry_run:
        title += " (dry run)"
    lines = [title]
    if summary.base_url:
        lines.append(f"Base: {summary.base_url}")
    lines.extend(["", "Endpoints:"])

    for endpoint in summary.endpoints:
        note = f"  ({endpoint.note})" if endpoint.note else ""
        lines.append(
            f"  {endpoint.label:<16} {endpoint.status}{note}"
        )

    blocked = [
        endpoint.label
        for endpoint in summary.endpoints
        if endpoint.status == 403
    ]
    if blocked:
        lines.append(
            "  blocked: "
            + ", ".join(blocked)
            + " (expected; the nested activity payload covers them)"
        )

    years = summary.years
    lines.append("")
    if not summary.activity_count:
        lines.append("Activities: none in the requested range")
        return "\n".join(lines)

    span = (
        f"{years[0]}-{years[-1]}" if len(years) >= 2 else str(years[0])
    )
    lines.append(f"Activities: {summary.activity_count} ({span})")

    if not years:
        return "\n".join(lines)

    header = "  " + f"{'':<30}" + "".join(
        f"{year:>7}" for year in years
    ) + f"{'total':>8}"
    lines.extend(["", header])

    lines.append(
        "  "
        + f"{'activities':<30}"
        + "".join(
            f"{summary.activities_by_year.get(year, 0):>7}"
            for year in years
        )
        + f"{summary.activity_count:>8}"
    )

    for name in sorted(summary.fields):
        counts = summary.fields[name]
        total = sum(counts.values())
        lines.append(
            "  "
            + f"{name[:30]:<30}"
            + "".join(f"{counts.get(year, 0):>7}" for year in years)
            + f"{total:>8}"
        )

    lines.extend([
        "",
        "Counts are activities with a non-null value for the field.",
    ])
    return "\n".join(lines)


def _endpoint_note(path: str, response: RunalyzeResponse) -> str:
    if response.status == 403:
        return "blocked"
    if not response.ok:
        return _short(response.payload)
    if path == "ping":
        payload = response.payload
        if isinstance(payload, list) and payload:
            return _short(payload[0])
        return _short(payload)
    if path == "activity":
        payload = response.payload
        if isinstance(payload, dict):
            return f"{len(payload)} fields"
    return "ok"


def _short(value: object, limit: int = 48) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _header_int(headers: object, name: str) -> int | None:
    """Read an integer header, tolerating plain dicts and case differences."""
    try:
        items = headers.items()
    except AttributeError:
        return None

    wanted = name.lower()
    for key, value in items:
        if str(key).lower() != wanted:
            continue
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return None
    return None


def _items(payload: object) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "data", "results", "hydra:member"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _activity_date(activity: dict) -> date | None:
    for key in YEAR_KEYS:
        value = activity.get(key)
        if value is None:
            continue
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            continue
    return None


def _in_range(
    activity: dict,
    start: date | None,
    end: date | None,
) -> bool:
    if start is None and end is None:
        return True

    day = _activity_date(activity)
    if day is None:
        return False
    if start is not None and day < start:
        return False
    if end is not None and day > end:
        return False
    return True


def _activity_year(activity: dict) -> int | None:
    for key in YEAR_KEYS:
        if key not in activity:
            continue
        year = _year_from_value(activity[key])
        if year is not None:
            return year
    return None


def _year_from_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        number = float(value)
        if number >= 10_000_000_000:  # milliseconds
            number /= 1000
        if number >= 1_000_000_000:  # unix seconds
            return datetime.fromtimestamp(number, tz=timezone.utc).year
        if number >= 10_000_000:  # YYYYMMDD
            return int(number) // 10_000
        return None

    text = str(value or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        year = int(text[:4])
        if 1900 <= year <= 2200:
            return year
    return None
