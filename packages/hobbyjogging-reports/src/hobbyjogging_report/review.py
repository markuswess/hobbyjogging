"""Import-review filtering for reports.

Activities with open review items carry `needs_review` in the canonical
model. Reports exclude them by default so questionable data never silently
changes training numbers; the excluded count is surfaced as a report note.
"""

from hobbyjogging_core.model import Activity


def exclude_review(
    activities: list[Activity],
    *,
    include_review: bool = False,
) -> tuple[list[Activity], int]:
    """Return (kept activities, excluded count) for a report."""
    if include_review:
        return activities, 0

    kept = [a for a in activities if not a.needs_review]
    return kept, len(activities) - len(kept)


def review_note(excluded: int) -> str:
    if excluded == 0:
        return ""

    unit = "activity" if excluded == 1 else "activities"
    return f"{excluded} {unit} excluded (import review)"
