"""The historical sheet's ``Trainigstyp`` vocabulary.

The code table is one source's shorthand, not part of the canonical workout
vocabulary: it lives here so the core stays independent of the ODS layout.
"""

from __future__ import annotations

from hobbyjogging_core.workouts import normalize_token

# (methods, targets, extra tags) per code.
SHEET_TYPE_CODES = {
    "r": ({"continuous"}, {"recovery"}, set()),
    "i": ({"intervals"}, {"vo2max"}, set()),
    "bi": ({"intervals"}, {"vo2max"}, {"hills"}),
    "b": ({"continuous"}, {"base"}, set()),
    "fs": ({"fartlek"}, {"vo2max"}, set()),
    "k": (set(), set(), {"strength"}),
    "ll": ({"long_run"}, {"base"}, set()),
    "lt": ({"race"}, {"other"}, set()),
    "tdl": ({"continuous"}, {"threshold"}, set()),
    "u": (set(), set(), {"bad data"}),
    "idl": ({"continuous"}, set(), set()),
}


def classification_for_sheet_code(
    code: object,
) -> tuple[set[str], set[str], set[str]]:
    """Map a sheet ``Trainigstyp`` code to methods, targets, and tags."""
    token = normalize_token(code)
    methods, targets, tags = SHEET_TYPE_CODES.get(token, (set(), set(), set()))
    return set(methods), set(targets), set(tags)
