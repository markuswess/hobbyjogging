"""Read-only audit of historical evidence already stored.

The audit answers one question: what facts are in the raw payloads, tags,
descriptions, laps, races and periods that the canonical record does not use
yet? It writes nothing and opens no review items. It is the gate for the
historical refurbishment (root item 37) and is re-runnable as imports land.

The output is Markdown: coverage per field and year, raw payload keys that
have no canonical home, tag meanings, interval-like descriptions, trail and
race evidence, classification gaps and the illness/season periods.
"""

from __future__ import annotations

import sqlite3

from hobbyjogging_core.db.writer import ACTIVITY_COLUMNS

from .audit_facts import (
    classification_audit,
    classification_section,
    description_audit,
    description_section,
    period_audit,
    period_section,
    race_audit,
    race_section,
    review_audit,
    review_section,
    trail_audit,
    trail_section,
)
from .audit_sources import (
    raw_key_audit,
    raw_key_section,
    tag_audit,
    tag_section,
)

KEY_FIELDS = (
    "avg_hr",
    "max_hr",
    "distance_m",
    "elevation_gain_m",
    "training_load",
    "rpe",
    "description",
    "device_id",
    "vo2max",
)

def build_audit(
    connection: sqlite3.Connection,
    *,
    database: str | None = None,
) -> str:
    """Return the Markdown audit for one database."""
    years = _years(connection)
    activities = _activity_count(connection)
    lines = ["# Historical data audit", ""]
    if database:
        lines.append(f"Database: `{database}`")
    lines.append(f"Activities (non-excluded): {activities}")
    if years:
        lines.append(
            f"Range: {years[0]['year']} .. {years[-1]['year']}"
        )
    lines.append("")

    lines.extend(_scope_section(connection, activities))
    coverage = _coverage(connection)
    year_counts = _year_field_counts(connection)
    lines.extend(_coverage_section(coverage, years, year_counts))
    raw = raw_key_audit(connection)
    lines.extend(raw_key_section(raw))
    tags = tag_audit(connection)
    lines.extend(tag_section(tags))
    descriptions = description_audit(connection)
    lines.extend(description_section(descriptions, activities))
    trail = trail_audit(connection)
    lines.extend(trail_section(trail))
    races = race_audit(connection)
    lines.extend(race_section(races))
    classification = classification_audit(connection)
    lines.extend(classification_section(classification))
    periods = period_audit(connection)
    lines.extend(period_section(periods))
    review = review_audit(connection)
    lines.extend(review_section(review))
    lines.extend(_summary_section(
        activities,
        coverage,
        raw,
        tags,
        descriptions,
        trail,
        races,
        classification,
        review,
    ))
    return "\n".join(lines).rstrip() + "\n"


# -- scope ---------------------------------------------------------------


def _activity_count(connection: sqlite3.Connection) -> int:
    return connection.execute(
        "SELECT COUNT(*) FROM activities WHERE excluded_at IS NULL"
    ).fetchone()[0]


def _years(connection: sqlite3.Connection) -> list[dict]:
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT substr(local_date, 1, 4) AS year, COUNT(*) AS activities
            FROM activities
            WHERE excluded_at IS NULL
            GROUP BY year
            ORDER BY year
            """
        )
    ]


def _scope_section(
    connection: sqlite3.Connection,
    activities: int,
) -> list[str]:
    lines = [
        "## Scope",
        "",
        "| table | rows |",
        "|---|---:|",
        f"| activities (non-excluded) | {activities} |",
    ]
    for table in (
        "source_records",
        "activity_field_sources",
        "activity_tags",
        "activity_workout_methods",
        "activity_workout_targets",
        "training_periods",
        "events",
        "race_results",
        "wellness_days",
        "review_items",
    ):
        count = connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        lines.append(f"| {table} | {count} |")
    lines.extend(
        [
            "",
            "### Source records",
            "",
            "| source | record type | records |",
            "|---|---|---:|",
        ]
    )
    rows = connection.execute(
        """
        SELECT source, record_type, COUNT(*) AS records
        FROM source_records
        GROUP BY source, record_type
        ORDER BY source, record_type
        """
    ).fetchall()
    if not rows:
        lines.append("| - | - | 0 |")
    for row in rows:
        lines.append(
            f"| {row['source']} | {row['record_type']} | "
            f"{row['records']} |"
        )
    lines.append("")
    return lines


# -- canonical coverage --------------------------------------------------


def _coverage(connection: sqlite3.Connection) -> dict[str, int]:
    """Non-empty values per canonical activity column, all-time."""
    expressions = []
    for field in sorted(ACTIVITY_COLUMNS):
        expressions.append(
            "SUM(CASE WHEN "
            f"{field} IS NOT NULL AND TRIM(CAST({field} AS TEXT)) != '' "
            "THEN 1 ELSE 0 END)"
        )
    row = connection.execute(
        "SELECT " + ", ".join(expressions) + " "
        "FROM activities WHERE excluded_at IS NULL"
    ).fetchone()
    return {
        field: int(value or 0)
        for field, value in zip(sorted(ACTIVITY_COLUMNS), row)
    }


def _year_field_counts(connection: sqlite3.Connection) -> dict[str, dict]:
    fields = sorted(ACTIVITY_COLUMNS)
    expressions = []
    for field in fields:
        expressions.append(
            "SUM(CASE WHEN "
            f"{field} IS NOT NULL AND TRIM(CAST({field} AS TEXT)) != '' "
            f"THEN 1 ELSE 0 END) AS {field}"
        )
    expressions.append(
        "SUM(CASE WHEN vo2max_garmin IS NOT NULL "
        "OR vo2max_runalyze IS NOT NULL THEN 1 ELSE 0 END) AS vo2max"
    )
    rows = connection.execute(
        "SELECT substr(local_date, 1, 4) AS year, COUNT(*) AS activities, "
        + ", ".join(expressions)
        + " FROM activities WHERE excluded_at IS NULL GROUP BY year "
        "ORDER BY year"
    ).fetchall()
    result = {}
    for row in rows:
        result[row["year"]] = {
            "activities": row["activities"],
            **{
                field: int(row[field] or 0)
                for field in fields
            },
            "vo2max": int(row["vo2max"] or 0),
        }
    return result


def _coverage_section(
    coverage: dict[str, int],
    years: list[dict],
    year_counts: dict[str, dict],
) -> list[str]:
    activities = _sum_years(years)
    lines = [
        "## Field coverage",
        "",
        f"Across {activities} activities:",
        "",
        "| field | values | coverage |",
        "|---|---:|---:|",
    ]
    for field in sorted(coverage):
        value = coverage[field]
        share = (value / activities * 100) if activities else 0
        lines.append(f"| `{field}` | {value} | {share:.1f}% |")

    if year_counts:
        lines.extend(
            [
                "",
                "### Key fields by year",
                "",
                "| year | activities | "
                + " | ".join(KEY_FIELDS)
                + " |",
                "|---:|---:|" + "---:|" * len(KEY_FIELDS),
            ]
        )
        for year in sorted(year_counts):
            row = year_counts[year]
            cells = []
            for field in KEY_FIELDS:
                value = row.get(field, 0)
                share = (
                    value / row["activities"] * 100
                    if row["activities"]
                    else 0
                )
                cells.append(f"{share:.0f}%")
            lines.append(
                f"| {year} | {row['activities']} | "
                + " | ".join(cells)
                + " |"
            )

    gaps = []
    for field in sorted(coverage):
        if not year_counts:
            break
        poor = []
        for year in sorted(year_counts):
            row = year_counts[year]
            total = row["activities"]
            value = row.get(field, 0)
            share = value / total if total else 0
            if total and share < 0.5:
                poor.append(f"{year} ({share:.0%})")
        if poor:
            gaps.append(f"| `{field}` | " + ", ".join(poor) + " |")
    if gaps:
        lines.extend(
            [
                "",
                "### Coverage gaps (fields under 50 % in a year)",
                "",
                "| field | years |",
                "|---|---|",
            ]
        )
        lines.extend(gaps)

    if year_counts:
        years_sorted = sorted(year_counts)
        lines.extend(
            [
                "",
                "### All fields by year",
                "",
                "| field | " + " | ".join(years_sorted) + " |",
                "|---|" + "---:|" * len(years_sorted),
            ]
        )
        for field in sorted(coverage):
            cells = []
            for year in years_sorted:
                row = year_counts[year]
                if not row["activities"]:
                    cells.append("-")
                    continue
                share = row.get(field, 0) / row["activities"] * 100
                cells.append(f"{share:.0f}%")
            lines.append(
                f"| `{field}` | " + " | ".join(cells) + " |"
            )

    lines.append("")
    return lines


def _sum_years(years: list[dict]) -> int:
    return sum(row["activities"] for row in years)


# -- summary -------------------------------------------------------------


def _summary_section(
    activities: int,
    coverage: dict[str, int],
    raw: dict,
    tags: list[dict],
    descriptions: dict,
    trail: dict,
    races: dict,
    classification: dict,
    review: dict,
) -> list[str]:
    unmapped_keys = sum(
        len(data["unmapped"]) for data in raw.values()
    )
    unmapped_tags = sum(
        1 for tag in tags if tag["meaning"] == "unmapped"
    )
    return [
        "## Summary",
        "",
        f"- {activities} activities; {coverage.get('avg_hr', 0)} with avg HR, "
        f"{coverage.get('training_load', 0)} with load, "
        f"{coverage.get('description', 0)} with a description.",
        f"- {unmapped_keys} unmapped raw keys across the stored sources; "
        f"{unmapped_tags} unmapped tags.",
        f"- {descriptions['descriptions']} descriptions; "
        f"{descriptions['patterns'].get('reps NxM', 0)} contain an NxM "
        "rep pattern.",
        f"- {len(trail['candidates'])} run candidates with trail evidence; "
        f"{races['race_method']} activities carry the `race` method and "
        f"{races['results']} official results are stored.",
        f"- {classification['unclassified']} activities are unclassified; "
        f"{classification['open_items']} classification items are open; "
        f"{review['totals'].get('open', 0)} review items are open in total.",
        "",
    ]


