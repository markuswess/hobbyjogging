"""Historical audit: descriptions, trail, race, classification, periods."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter

from hobbyjogging_core.model import TEST_SPLIT_SOURCE
from hobbyjogging_core.sports import RUN_SPORTS
from hobbyjogging_import.runalyze_types import audit_types
from hobbyjogging_import.tag_lexicon import lookup_tag, normalize_tag

from .audit_common import cell, shorten

TRAIL_M_PER_KM = 40.0
TRAIL_SAMPLE = 40
INTERVAL_SAMPLE = 8
INTERVAL_PATTERNS = {
    "reps NxM": re.compile(r"\b\d+\s*[x×]\s*\d+\b", re.IGNORECASE),
    "ladder": re.compile(
        r"\b\d+(?:\s*-\s*\d+){2,}\s*(?:min|minuten|km|m)\b",
        re.IGNORECASE,
    ),
    "repeat word": re.compile(
        r"\b\d+\s*(?:wiederholungen?|wdh)\b", re.IGNORECASE
    ),
    "interval word": re.compile(
        r"\b(?:intervalle?|intervals?|serien?|reps?)\b", re.IGNORECASE
    ),
    "short rep": re.compile(
        r"\b\d+\s*['′]\s*(?:min|minuten)?\b", re.IGNORECASE
    ),
}


# -- interval-like descriptions -----------------------------------------


def description_audit(connection: sqlite3.Connection) -> dict:
    rows = connection.execute(
        """
        SELECT a.id, a.local_date, a.description,
               EXISTS(
                   SELECT 1 FROM activity_workout_methods m
                   WHERE m.activity_id = a.id
               ) OR EXISTS(
                   SELECT 1 FROM activity_workout_targets t
                   WHERE t.activity_id = a.id
               ) AS classified
        FROM activities a
        WHERE a.excluded_at IS NULL AND TRIM(a.description) != ''
        ORDER BY a.local_date
        """
    ).fetchall()
    pattern_counts = Counter()
    per_year = {}
    matches = []
    for row in rows:
        text = row["description"] or ""
        hit = []
        for name, pattern in INTERVAL_PATTERNS.items():
            if pattern.search(text):
                pattern_counts[name] += 1
                hit.append(name)
        year = (row["local_date"] or "")[:4]
        bucket = per_year.setdefault(
            year, {"descriptions": 0, "interval": 0, "unclassified": 0}
        )
        bucket["descriptions"] += 1
        if hit:
            bucket["interval"] += 1
            if not row["classified"]:
                bucket["unclassified"] += 1
            if len(matches) < INTERVAL_SAMPLE:
                matches.append(
                    {
                        "date": row["local_date"],
                        "patterns": ", ".join(hit),
                        "text": shorten(text),
                    }
                )
    return {
        "descriptions": len(rows),
        "patterns": pattern_counts,
        "per_year": per_year,
        "matches": matches,
    }


def description_section(data: dict, activities: int) -> list[str]:
    lines = [
        "## Interval-like descriptions",
        "",
        f"{data['descriptions']} activities carry a description "
        f"({data['descriptions'] / activities * 100 if activities else 0:.0f}% "
        "of all).",
        "",
        "| pattern | activities |",
        "|---|---:|",
    ]
    for name in INTERVAL_PATTERNS:
        lines.append(f"| {name} | {data['patterns'].get(name, 0)} |")
    lines.extend(
        [
            "",
            "| year | descriptions | interval-like | unclassified |",
            "|---|---:|---:|---:|",
        ]
    )
    for year in sorted(data["per_year"]):
        row = data["per_year"][year]
        lines.append(
            f"| {year} | {row['descriptions']} | {row['interval']} | "
            f"{row['unclassified']} |"
        )
    if data["matches"]:
        lines.extend(
            [
                "",
                "Sample interval-like descriptions:",
                "",
                "| date | pattern | text |",
                "|---|---|---|",
            ]
        )
        for item in data["matches"]:
            lines.append(
                f"| {item['date']} | {item['patterns']} | "
                f"{cell(item['text'])} |"
            )
    lines.extend(
        [
            "",
            "Rep rows are not reconstructed from text; this section only "
            "measures whether the descriptions are structured enough to try.",
            "",
        ]
    )
    return lines


# -- trail evidence ------------------------------------------------------


def trail_audit(connection: sqlite3.Connection) -> dict:
    placeholders = ", ".join("?" for _ in RUN_SPORTS)
    rows = connection.execute(
        f"""
        SELECT a.id, a.local_date, a.sport, a.sub_sport, a.distance_m,
               a.elevation_gain_m,
               (SELECT SUM(l.elevation_gain_m) FROM activity_laps l
                WHERE l.activity_id = a.id AND l.source != ?) AS lap_gain
        FROM activities a
        WHERE a.excluded_at IS NULL
          AND a.sport IN ({placeholders})
          AND a.distance_m > 0
        ORDER BY a.local_date
        """,
        (TEST_SPLIT_SOURCE, *tuple(sorted(RUN_SPORTS))),
    ).fetchall()
    ids = {row["id"] for row in rows}
    tags = {}
    for row in connection.execute(
        """
        SELECT t.activity_id, t.tag FROM activity_tags t
        JOIN activities a ON a.id = t.activity_id
        WHERE a.excluded_at IS NULL
        """
    ):
        if row["activity_id"] in ids:
            tags.setdefault(row["activity_id"], set()).add(
                str(row["tag"]).lower()
            )
    route_names = {}
    for row in connection.execute(
        """
        SELECT ar.activity_id, r.name FROM activity_routes ar
        JOIN routes r ON r.id = ar.route_id
        """
    ):
        if row["activity_id"] in ids:
            route_names.setdefault(row["activity_id"], set()).add(
                str(row["name"]).lower()
            )

    candidates = []
    evidence_counts = Counter()
    route_hints = 0
    already_trail = 0
    for row in rows:
        if row["sport"] == "trail_run":
            already_trail += 1
            continue
        gain = row["elevation_gain_m"]
        if gain is None:
            gain = row["lap_gain"]
        gain = float(gain or 0.0)
        m_per_km = gain / (float(row["distance_m"]) / 1000.0)
        evidence = []
        if m_per_km >= TRAIL_M_PER_KM:
            evidence.append(("elevation", f"{m_per_km:.0f} m/km"))
        sub = str(row["sub_sport"] or "").lower()
        if sub in {"trail", "mountain"} or "trail" in sub:
            evidence.append(("sub_sport", sub))
        if any("trail" in tag for tag in tags.get(row["id"], set())):
            evidence.append(("tag", "trail"))
        names = route_names.get(row["id"], set())
        route_hint = any(
            "trail" in name or "berg" in name for name in names
        )
        if not evidence:
            if route_hint:
                route_hints += 1
            continue
        for key, _value in evidence:
            evidence_counts[key] += 1
        if route_hint:
            evidence_counts["route"] += 1
            evidence.append(("route", ", ".join(sorted(names))))
        candidates.append(
            {
                "date": row["local_date"],
                "sport": row["sport"],
                "distance": float(row["distance_m"]) / 1000.0,
                "m_per_km": m_per_km,
                "evidence": ", ".join(value for _key, value in evidence),
            }
        )
    return {
        "runs": len(rows),
        "already_trail": already_trail,
        "candidates": candidates,
        "evidence": evidence_counts,
        "route_hints": route_hints,
    }


def trail_section(data: dict) -> list[str]:
    lines = [
        "## Elevation and trail evidence",
        "",
        f"{data['runs']} runs; {data['already_trail']} already `trail_run`; "
        f"{len(data['candidates'])} run candidates with trail evidence.",
        "",
        "| evidence | candidates |",
        "|---|---:|",
    ]
    for key, count in sorted(data["evidence"].items()):
        lines.append(f"| {key} | {count} |")
    if data["candidates"]:
        lines.extend(
            [
                "",
                "| date | sport | km | m/km | evidence |",
                "|---|---|---:|---:|---|",
            ]
        )
        for item in data["candidates"][:TRAIL_SAMPLE]:
            lines.append(
                f"| {item['date']} | {item['sport']} | "
                f"{item['distance']:.1f} | {item['m_per_km']:.0f} | "
                f"{cell(item['evidence'])} |"
            )
        if len(data["candidates"]) > TRAIL_SAMPLE:
            lines.append(
                f"| … {len(data['candidates']) - TRAIL_SAMPLE} more | | | | |"
            )
    if data.get("route_hints"):
        lines.append(
            f"\n{data['route_hints']} further runs mention a trail-like route "
            "name but carry no elevation, sub-sport or trail-tag evidence."
        )
    lines.extend(
        [
            "",
            f"The elevation threshold is {TRAIL_M_PER_KM:.0f} m/km; "
            "sub-sport, trail tags and route names are supporting evidence. "
            "No sport is changed by this audit.",
            "",
        ]
    )
    return lines


# -- races ---------------------------------------------------------------


def race_audit(connection: sqlite3.Connection) -> dict:
    race_ids = {
        row["activity_id"]
        for row in connection.execute(
            """
            SELECT activity_id FROM activity_workout_methods
            WHERE method = 'race'
            """
        )
    }
    results = connection.execute(
        """
        SELECT r.activity_id, a.local_date, r.event_id
        FROM race_results r
        JOIN activities a ON a.id = r.activity_id
        WHERE r.excluded_at IS NULL AND a.excluded_at IS NULL
        """
    ).fetchall()
    race_tags = connection.execute(
        """
        SELECT a.id, a.local_date FROM activity_tags t
        JOIN activities a ON a.id = t.activity_id
        WHERE a.excluded_at IS NULL
          AND lower(t.tag) IN ('race', 'raceday', 'race day', 'wettkampf')
        """
    ).fetchall()
    by_year = {}
    for activity_id in race_ids:
        row = connection.execute(
            "SELECT local_date FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()
        if row is None:
            continue
        year = row["local_date"][:4]
        bucket = by_year.setdefault(
            year, {"race_method": 0, "results": 0, "race_tags": 0}
        )
        bucket["race_method"] += 1
    for row in results:
        year = row["local_date"][:4]
        by_year.setdefault(
            year, {"race_method": 0, "results": 0, "race_tags": 0}
        )["results"] += 1
    for row in race_tags:
        year = row["local_date"][:4]
        by_year.setdefault(
            year, {"race_method": 0, "results": 0, "race_tags": 0}
        )["race_tags"] += 1

    result_ids = {row["activity_id"] for row in results}
    no_result = race_ids - result_ids
    no_event = [row for row in results if not row["event_id"]]
    return {
        "race_method": len(race_ids),
        "results": len(results),
        "race_tags": len(race_tags),
        "no_result": len(no_result),
        "no_event": len(no_event),
        "by_year": by_year,
        "events": connection.execute(
            "SELECT COUNT(*) FROM events WHERE excluded_at IS NULL"
        ).fetchone()[0],
    }


def race_section(data: dict) -> list[str]:
    lines = [
        "## Race evidence",
        "",
        "| evidence | count |",
        "|---|---:|",
        f"| activities with the `race` method | {data['race_method']} |",
        f"| official race results | {data['results']} |",
        f"| race tags | {data['race_tags']} |",
        f"| race method without a result | {data['no_result']} |",
        f"| results without an event link | {data['no_event']} |",
        f"| planned events | {data['events']} |",
        "",
        "| year | race method | results | race tags |",
        "|---|---:|---:|---:|",
    ]
    for year in sorted(data["by_year"]):
        row = data["by_year"][year]
        lines.append(
            f"| {year} | {row['race_method']} | {row['results']} | "
            f"{row['race_tags']} |"
        )
    lines.append("")
    return lines


# -- classification ------------------------------------------------------


def classification_audit(connection: sqlite3.Connection) -> dict:
    total = connection.execute(
        "SELECT COUNT(*) FROM activities WHERE excluded_at IS NULL"
    ).fetchone()[0]
    with_sets = connection.execute(
        """
        SELECT COUNT(*) FROM activities a
        WHERE a.excluded_at IS NULL
          AND (EXISTS(SELECT 1 FROM activity_workout_methods m
                      WHERE m.activity_id = a.id)
               OR EXISTS(SELECT 1 FROM activity_workout_targets t
                         WHERE t.activity_id = a.id))
        """
    ).fetchone()[0]
    methods = Counter(
        row["method"]
        for row in connection.execute(
            "SELECT method FROM activity_workout_methods"
        )
    )
    targets = Counter(
        row["target"]
        for row in connection.execute(
            "SELECT target FROM activity_workout_targets"
        )
    )
    by_year = {}
    rows = connection.execute(
        """
        SELECT substr(a.local_date, 1, 4) AS year, COUNT(*) AS activities,
               SUM(CASE WHEN EXISTS(
                       SELECT 1 FROM activity_workout_methods m
                       WHERE m.activity_id = a.id
                   ) OR EXISTS(
                       SELECT 1 FROM activity_workout_targets t
                       WHERE t.activity_id = a.id
                   ) THEN 0 ELSE 1 END) AS unclassified
        FROM activities a
        WHERE a.excluded_at IS NULL
        GROUP BY year ORDER BY year
        """
    ).fetchall()
    for row in rows:
        by_year[row["year"]] = {
            "activities": row["activities"],
            "unclassified": row["unclassified"],
        }
    types = audit_types(connection)
    open_items = connection.execute(
        "SELECT COUNT(*) FROM review_items "
        "WHERE status = 'open' AND category = 'workout_classification'"
    ).fetchone()[0]
    return {
        "total": total,
        "classified": with_sets,
        "unclassified": total - with_sets,
        "methods": methods,
        "targets": targets,
        "by_year": by_year,
        "types": types,
        "open_items": open_items,
    }


def classification_section(data: dict) -> list[str]:
    lines = [
        "## Classification coverage",
        "",
        f"{data['classified']} of {data['total']} activities have a method "
        f"or target; {data['unclassified']} are unclassified. "
        f"{data['open_items']} `workout_classification` items are open.",
        "",
        "| year | activities | unclassified |",
        "|---|---:|---:|",
    ]
    for year in sorted(data["by_year"]):
        row = data["by_year"][year]
        lines.append(
            f"| {year} | {row['activities']} | {row['unclassified']} |"
        )
    lines.extend(
        [
            "",
            "Methods: "
            + ", ".join(
                f"`{name}` {count}"
                for name, count in data["methods"].most_common()
            ),
            "",
            "Targets: "
            + ", ".join(
                f"`{name}` {count}"
                for name, count in data["targets"].most_common()
            ),
            "",
            "### Runalyze types",
            "",
        ]
    )
    types = data["types"]
    if not types:
        lines.append("No stored Runalyze types.")
    else:
        unmapped = [row for row in types if not row.mapped]
        lines.append(
            f"{len(types)} distinct types; {len(unmapped)} unmapped."
        )
        if unmapped:
            lines.extend(
                [
                    "",
                    "| type | abbr | count |",
                    "|---|---|---:|",
                ]
            )
            for row in unmapped:
                lines.append(
                    f"| {cell(row.name)} | {cell(row.abbreviation)} | "
                    f"{row.count} |"
                )
    lines.append("")
    return lines


# -- periods and illness -------------------------------------------------


def period_audit(connection: sqlite3.Connection) -> dict:
    periods = [
        dict(row)
        for row in connection.execute(
            """
            SELECT kind, start_date, end_date, label
            FROM training_periods
            WHERE excluded_at IS NULL
            ORDER BY start_date, kind
            """
        )
    ]
    counts = Counter(row["kind"] for row in periods)
    illness = [row for row in periods if row["kind"] == "illness"]
    tag_rows = connection.execute(
        """
        SELECT a.local_date, t.tag FROM activity_tags t
        JOIN activities a ON a.id = t.activity_id
        WHERE a.excluded_at IS NULL
        """
    ).fetchall()
    tagged_days: dict[str, set[str]] = {}
    recovered_days: set[str] = set()
    for row in tag_rows:
        meaning = lookup_tag(row["tag"])
        if meaning is None:
            continue
        if meaning.kind == "illness":
            tagged_days.setdefault(
                normalize_tag(row["tag"]), set()
            ).add(row["local_date"])
        elif meaning.kind == "recovered":
            recovered_days.add(row["local_date"])

    def inside_illness(day: str) -> bool:
        for period in illness:
            start = period["start_date"]
            end = period["end_date"] or start
            if start <= day <= end:
                return True
        return False

    illness_days = [
        day for days in tagged_days.values() for day in days
    ]
    outside = sorted({day for day in illness_days if not inside_illness(day)})
    return {
        "periods": periods,
        "counts": counts,
        "illness": illness,
        "tagged_days": tagged_days,
        "recovered_days": recovered_days,
        "outside": outside,
    }


def period_section(data: dict) -> list[str]:
    lines = [
        "## Periods and illness evidence",
        "",
        "| kind | periods |",
        "|---|---:|",
    ]
    if not data["counts"]:
        lines.append("| - | 0 |")
    for kind in sorted(data["counts"]):
        lines.append(f"| {kind} | {data['counts'][kind]} |")
    lines.extend(
        [
            "",
            "### Stored periods",
            "",
            "| kind | start | end | label |",
            "|---|---|---|---|",
        ]
    )
    if not data["periods"]:
        lines.append("| - | - | - | - |")
    for period in data["periods"]:
        lines.append(
            f"| {period['kind']} | {period['start_date']} | "
            f"{period['end_date'] or ''} | {cell(period['label'] or '')} |"
        )
    lines.extend(
        [
            "",
            "### Illness tags",
            "",
        ]
    )
    if not data["tagged_days"]:
        lines.append("No illness tags.")
    else:
        for tag in sorted(data["tagged_days"]):
            days = sorted(data["tagged_days"][tag])
            lines.append(
                f"- `{tag}`: {len(days)} days, "
                f"{days[0]} .. {days[-1]}"
            )
        if data["outside"]:
            sample = ", ".join(data["outside"][:12])
            lines.append(
                f"- {len(data['outside'])} tagged days fall outside an "
                f"illness period: {sample}"
            )
        else:
            lines.append("- Every illness-tagged day falls inside a period.")
        if data["recovered_days"]:
            days = sorted(data["recovered_days"])
            lines.append(
                f"- `wieder gesund`: {len(days)} days, "
                f"{days[0]} .. {days[-1]} (closes a range, not an incident)"
            )
    lines.append("")
    return lines


# -- review queue --------------------------------------------------------


def review_audit(connection: sqlite3.Connection) -> dict:
    open_by_category = {
        row["category"]: row["count"]
        for row in connection.execute(
            """
            SELECT category, COUNT(*) AS count FROM review_items
            WHERE status = 'open' GROUP BY category ORDER BY category
            """
        )
    }
    totals = {
        row["status"]: row["count"]
        for row in connection.execute(
            "SELECT status, COUNT(*) AS count FROM review_items "
            "GROUP BY status"
        )
    }
    return {"open": open_by_category, "totals": totals}


def review_section(data: dict) -> list[str]:
    lines = [
        "## Review queue",
        "",
        "| status | items |",
        "|---|---:|",
    ]
    for status in ("open", "ignored", "resolved"):
        lines.append(f"| {status} | {data['totals'].get(status, 0)} |")
    lines.extend(["", "| open category | items |", "|---|---:|"])
    if not data["open"]:
        lines.append("| - | 0 |")
    for category in sorted(data["open"]):
        lines.append(f"| `{category}` | {data['open'][category]} |")
    lines.append("")
    return lines


