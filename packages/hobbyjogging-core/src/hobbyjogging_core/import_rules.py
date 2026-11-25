"""Declarative import rules shared by the writer, importers and reports.

The canonical writer is owner-based: the first source to fill a field keeps
it, a later source only fills an empty value, and a meaningful disagreement
opens a review item. There is deliberately no global source priority; a
source order would let a weaker source overwrite a stronger one on the
fields where it happens to be better.

Two exceptions are worth declaring rather than hard-coding in the writer:

* a field may have a ranked authority, where a named source is a better
  measurement than the current owner (``moving_s`` and ``elapsed_s`` from
  Intervals, ``device_id`` and ``vo2max_garmin`` from FIT);
* a field may treat a placeholder value as unfilled (``sport``: ``other``
  yields to a specific sport).

This module owns those rules, the conflict tolerances and the source
profiles. Importers, the settings report and the writer read the same data,
so a rule cannot drift between the code that applies it and the view that
describes it.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_NUMERIC_TOLERANCE = (0.01, 0.5)
START_TOLERANCE_S = 15.0


@dataclass(frozen=True)
class FieldRule:
    """How one canonical activity field accepts values from sources."""

    conflict: bool = False
    tolerance: tuple[float, float] | None = None
    authority: tuple[str, ...] = ()
    manual: bool = False
    placeholder: bool = False
    pause_accounting: bool = False
    datetime: bool = False


# The table is the single source of truth for field behaviour. A field that
# is absent is owner-tracked without a conflict item, which is the default
# for source-specific extras. Subjective text and ratings are present only so
# the edit surface may write them manually, not to open conflicts.
FIELD_RULES: dict[str, FieldRule] = {
    # Recording time is owner-tracked, but a difference that fits inside
    # either source's pause gap is accounting noise rather than a conflict.
    "duration_s": FieldRule(
        conflict=True,
        tolerance=(0.05, 2.0),
        manual=True,
        pause_accounting=True,
    ),
    # Intervals measures moving and elapsed time for this athlete; FIT is the
    # fallback when Intervals is absent (the second-athlete case).
    "elapsed_s": FieldRule(
        conflict=True,
        tolerance=(0.01, 2.0),
        authority=("intervals", "fit"),
        manual=True,
    ),
    "moving_s": FieldRule(
        conflict=True,
        tolerance=(0.01, 2.0),
        authority=("intervals", "fit"),
        manual=True,
    ),
    "distance_m": FieldRule(
        conflict=True,
        tolerance=(0.01, 10.0),
        manual=True,
    ),
    "elevation_gain_m": FieldRule(
        conflict=True,
        tolerance=(0.10, 20.0),
        manual=True,
    ),
    "elevation_loss_m": FieldRule(
        conflict=True,
        tolerance=(0.10, 20.0),
        manual=True,
    ),
    "max_hr": FieldRule(
        conflict=True,
        tolerance=(0.01, 2.0),
        manual=True,
    ),
    "avg_hr": FieldRule(
        conflict=True,
        tolerance=(0.01, 5.0),
        manual=True,
    ),
    "started_at_utc": FieldRule(
        conflict=True,
        manual=True,
        datetime=True,
    ),
    "local_date": FieldRule(conflict=True, manual=True),
    "tz_offset_min": FieldRule(conflict=True, manual=True),
    "sport": FieldRule(conflict=True, manual=True, placeholder=True),
    "training_load": FieldRule(
        conflict=True,
        manual=True,
        # Intervals' load is the reference; a Runalyze TRIMP is a fallback and
        # never outranks it in a mixed database.
        authority=("intervals", "runalyze"),
    ),
    # FIT carries the device serial and the Garmin VO2max estimate, so each
    # wins over another source's value. A manual assignment still wins.
    "device_id": FieldRule(authority=("fit",), manual=True),
    "vo2max_garmin": FieldRule(authority=("fit",), manual=True),
    "vo2max_runalyze": FieldRule(manual=True),
    # Subjective fields: never a cross-source conflict, but editable by hand.
    "name": FieldRule(manual=True),
    "description": FieldRule(manual=True),
    "sub_sport": FieldRule(manual=True),
    "rpe": FieldRule(manual=True),
    "feel": FieldRule(manual=True),
}

CONFLICT_FIELDS = frozenset(
    field for field, rule in FIELD_RULES.items() if rule.conflict
)
MANUAL_FIELDS = tuple(
    field for field, rule in FIELD_RULES.items() if rule.manual
)
NUMERIC_TOLERANCES = {
    field: rule.tolerance
    for field, rule in FIELD_RULES.items()
    if rule.tolerance is not None
}
DATETIME_FIELDS = frozenset(
    field for field, rule in FIELD_RULES.items() if rule.datetime
)


def authority_rank(rule: FieldRule, source: str) -> int | None:
    """Return a source's rank for a field, or None when it is not ranked."""
    try:
        return rule.authority.index(source)
    except ValueError:
        return None


# Session-average metrics are a separate row, not activity columns. The unit
# is part of the field name or documented in ActivityMetrics; ``cadence`` is
# steps/min for run sports and rpm for rides. The tuple is the field order,
# the map the per-field ranked authority (FIT is the device measurement,
# Intervals owns altitude, Runalyze fills the gaps).
METRIC_FIELDS = (
    "cadence",
    "stride_m",
    "vertical_oscillation_mm",
    "stance_time_ms",
    "stance_time_pct",
    "stance_balance_pct",
    "vertical_ratio_pct",
    "respiration_bpm",
    "power_w",
    "calories_kcal",
    "training_effect",
    "gap_mps",
    "altitude_avg_m",
    "altitude_min_m",
    "altitude_max_m",
)
METRIC_AUTHORITY: dict[str, tuple[str, ...]] = {
    "cadence": ("fit", "intervals", "runalyze", "sheet"),
    "stride_m": ("fit", "intervals", "runalyze"),
    "vertical_oscillation_mm": ("fit", "intervals", "runalyze", "sheet"),
    "stance_time_ms": ("fit", "intervals", "runalyze", "sheet"),
    "stance_time_pct": ("fit", "intervals"),
    "stance_balance_pct": ("fit", "intervals", "runalyze"),
    "vertical_ratio_pct": ("fit", "intervals", "runalyze", "sheet"),
    "respiration_bpm": ("fit", "runalyze"),
    "power_w": ("fit", "runalyze"),
    "calories_kcal": ("fit", "intervals", "runalyze"),
    "training_effect": ("fit", "intervals", "runalyze"),
    "gap_mps": ("intervals", "runalyze"),
    "altitude_avg_m": ("intervals",),
    "altitude_min_m": ("intervals",),
    "altitude_max_m": ("intervals",),
}


def metric_authority_rank(field: str, source: str) -> int | None:
    """Return a source's rank for one metric field, or None if unranked."""
    try:
        return METRIC_AUTHORITY[field].index(source)
    except (KeyError, ValueError):
        return None


@dataclass(frozen=True)
class SourceProfile:
    """What one import source can supply, and how it joins the canonical DB.

    This is capability data, not a priority list. Field ownership stays with
    ``FieldRule``; the profile answers the questions an importer or a
    settings view asks before a run: does this source yield activity rows, how
    does it match, does it need detail requests, and what can a create fill.
    """

    name: str
    label: str
    entities: frozenset[str]
    yields_activities: bool
    match: str
    creation_fields: frozenset[str] = frozenset()
    absence: str = "ignore"
    detail_required: bool = False
    request_budget: str | None = None
    notes: str = ""


SOURCES: dict[str, SourceProfile] = {
    "fit": SourceProfile(
        name="fit",
        label="FIT archive",
        entities=frozenset({"activity", "fit_file", "device"}),
        yields_activities=True,
        match="contained_fit",
        creation_fields=frozenset(
            {
                "local_date",
                "started_at_utc",
                "tz_offset_min",
                "sport",
                "sub_sport",
                "name",
                "duration_s",
                "elapsed_s",
                "moving_s",
                "distance_m",
                "avg_hr",
                "max_hr",
                "elevation_gain_m",
                "elevation_loss_m",
                "vo2max_garmin",
                "device_id",
            }
        ),
        notes="A device file may be a contained segment of a larger activity.",
    ),
    "intervals": SourceProfile(
        name="intervals",
        label="Intervals.icu",
        entities=frozenset(
            {
                "activity",
                "intervals",
                "wellness",
                "event",
                "thresholds",
                "zones",
                "weather",
                "device",
            }
        ),
        yields_activities=True,
        match="temporal",
        creation_fields=frozenset(
            {
                "local_date",
                "started_at_utc",
                "tz_offset_min",
                "sport",
                "sub_sport",
                "name",
                "description",
                "duration_s",
                "elapsed_s",
                "moving_s",
                "distance_m",
                "avg_hr",
                "max_hr",
                "elevation_gain_m",
                "elevation_loss_m",
                "training_load",
                "rpe",
                "feel",
                "intensity",
                "device_id",
            }
        ),
        absence="events",
        notes="Authoritative for planned events and moving/elapsed time.",
    ),
    "garmin": SourceProfile(
        name="garmin",
        label="Garmin Personal API",
        entities=frozenset({"fit_file", "wellness"}),
        yields_activities=False,
        match="none",
        request_budget="garmin",
        notes="Downloads FIT files and the daily wellness feed.",
    ),
    "sheet": SourceProfile(
        name="sheet",
        label="Training sheet",
        entities=frozenset({"activity", "gear"}),
        yields_activities=True,
        match="temporal",
        creation_fields=frozenset(
            {
                "local_date",
                "started_at_utc",
                "tz_offset_min",
                "sport",
                "name",
                "description",
                "duration_s",
                "elapsed_s",
                "distance_m",
                "avg_hr",
                "max_hr",
                "elevation_gain_m",
            }
        ),
        notes="Historical ODS import; the source of the early gear rows.",
    ),
    "runalyze": SourceProfile(
        name="runalyze",
        label="Runalyze",
        entities=frozenset(
            {
                "activity",
                "gear",
                "race_result",
                "tags",
                "vo2max",
                "workout_type",
                "trimp",
            }
        ),
        yields_activities=True,
        match="exact_twin",
        creation_fields=frozenset(
            {
                "local_date",
                "started_at_utc",
                "tz_offset_min",
                "sport",
                "duration_s",
                "elapsed_s",
                "distance_m",
                "avg_hr",
                "max_hr",
                "description",
                "training_load",
                "vo2max_runalyze",
            }
        ),
        detail_required=True,
        request_budget="runalyze_window",
        notes="Enrichment first; creation is a per-athlete policy.",
    ),
    "strava": SourceProfile(
        name="strava",
        label="Strava",
        entities=frozenset({"activity", "gear", "social"}),
        yields_activities=True,
        match="temporal",
        creation_fields=frozenset(
            {
                "local_date",
                "started_at_utc",
                "tz_offset_min",
                "sport",
                "duration_s",
                "elapsed_s",
                "moving_s",
                "distance_m",
                "avg_hr",
                "max_hr",
                "elevation_gain_m",
            }
        ),
        notes="CSV bulk export first: social text and gear metadata.",
    ),
    "manual": SourceProfile(
        name="manual",
        label="Manual edit",
        entities=frozenset({"activity", "event", "gear", "race_result"}),
        yields_activities=True,
        match="none",
        absence="manual",
        notes="A human edit always outranks import sources.",
    ),
}


def source_profile(name: str) -> SourceProfile:
    """Return one source profile, failing loudly on a typo."""
    try:
        return SOURCES[name]
    except KeyError:
        known = ", ".join(sorted(SOURCES))
        raise KeyError(f"unknown source {name!r}; known sources: {known}")
