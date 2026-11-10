"""Browser links for canonical activities.

The source adapter resolves the external ids; this module only owns the URL
shape and the model handed to the session report.
"""

from __future__ import annotations

from dataclasses import dataclass

from hobbyjogging_core.datasource import DataSource

INTERVALS_URL = "https://intervals.icu/activities/{}"
GARMIN_URL = "https://connect.garmin.com/app/activity/{}"

# Garmin's activity list and the canonical start can differ by a second or
# two after matching. Keep the fallback tight enough that two nearby starts
# cannot both match.
GARMIN_MATCH_TOLERANCE_S = 15.0


@dataclass(frozen=True)
class ActivityLinks:
    """External activity pages for one canonical activity."""

    intervals: str | None = None
    garmin: str | None = None

    @property
    def any(self) -> bool:
        return bool(self.intervals or self.garmin)


def resolve_activity_links(
    source: DataSource,
    activity_id: str,
) -> ActivityLinks:
    """Return the source links an adapter can provide, if any."""
    resolver = getattr(source, "activity_links", None)

    if resolver is None:
        return ActivityLinks()

    return resolver(activity_id) or ActivityLinks()
