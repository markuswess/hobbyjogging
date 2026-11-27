"""Historical audit: raw payload keys and tags."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter

from hobbyjogging_import.derive import FIELD_MAPS, SHEET_MAPS
from hobbyjogging_import.tag_lexicon import meaning_label

from .audit_common import cell

KNOWN_KEYS = {
    "intervals": {
        "icu_intervals",
        "icu_hr_zones",
        "icu_hr_zone_times",
        "pace_zones",
        "pace_zone_times",
        "tags",
        "average_temp",
        "average_weather_temp",
        "has_weather",
    },
    "runalyze": {
        "type",
        "tags",
        "equipment",
        "laps",
        "note",
        "vo2max",
        "fit_trimp",
        "trimp",
        "sport",
        "sport_id",
        "id",
    },
    "fit": {"file", "session"},
    "strava": {"brand", "model", "type", "external_id", "name", "gear"},
    "sheet": {
        "row",
        "sheet",
        "values",
        # Handled by a child importer, not a canonical scalar.
        "Trainigstyp",
        "Trainingsgebiet",
        "Streckennummer",
        "Strecke",
        "Schuhe",
        "Gmap Pedometer Link",
    },
}

MAX_UNMAPPED_KEYS = 15

# -- raw keys ------------------------------------------------------------


def raw_key_audit(connection: sqlite3.Connection) -> dict:
    result = {}
    for source in ("intervals", "runalyze", "fit", "strava", "sheet"):
        where = "source = ? AND payload_json IS NOT NULL"
        params = [source]
        if source in {"intervals", "runalyze", "fit", "sheet"}:
            where += " AND record_type = 'activity'"
        rows = connection.execute(
            f"""
            SELECT payload_json
            FROM source_records
            WHERE {where}
            """,
            params,
        ).fetchall()
        if not rows:
            continue
        counts: Counter[str] = Counter()
        sheet_counts: Counter[str] = Counter()
        sheets = set()
        session_counts: Counter[str] = Counter()
        for row in rows:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            if source == "sheet":
                sheet = str(payload.get("sheet") or "")
                sheets.add(sheet)
                values = payload.get("values")
                if isinstance(values, dict):
                    sheet_counts.update(str(key) for key in values)
                continue
            counts.update(str(key) for key in payload)
            if source == "fit":
                session = payload.get("session")
                if isinstance(session, dict):
                    session_counts.update(str(key) for key in session)

        if source == "sheet":
            mapped = set()
            for sheet, fields in SHEET_MAPS.items():
                for spec in fields.values():
                    mapped.update(spec.keys)
            known = KNOWN_KEYS["sheet"]
            mapped.update(known)
            unmapped = {
                key: count for key, count in sheet_counts.items()
                if key not in mapped
            }
            result[source] = {
                "records": len(rows),
                "unmapped": unmapped,
                "sheets": sorted(sheets),
                "kind": "sheet",
            }
            continue

        mapped = {
            spec.keys[0].split(".")[0]
            for spec in FIELD_MAPS.get(source, {}).values()
            if spec.keys
        }
        mapped.update(KNOWN_KEYS.get(source, set()))
        unmapped = {
            key: count for key, count in counts.items()
            if key not in mapped
        }
        result[source] = {
            "records": len(rows),
            "unmapped": unmapped,
            "session_unmapped": {
                key: count
                for key, count in session_counts.items()
                if key not in {
                    spec.keys[0].split(".")[1]
                    for spec in FIELD_MAPS.get("fit", {}).values()
                    if spec.keys and len(spec.keys[0].split(".")) > 1
                }
                and key not in {"laps", "index", "sport"}
            } if source == "fit" else {},
            "kind": source,
        }
    return result


def raw_key_section(raw: dict) -> list[str]:
    lines = ["## Raw payload keys without a canonical home", ""]
    if not raw:
        lines.append("No stored payloads.")
        lines.append("")
        return lines
    for source in ("intervals", "runalyze", "fit", "strava", "sheet"):
        data = raw.get(source)
        if data is None:
            continue
        lines.append(f"### {source} ({data['records']} records)")
        lines.append("")
        if source == "fit":
            lines.append(
                "FIT payloads are normalized summaries; the archive is the "
                "raw source, so unstored FIT fields are not visible here."
            )
            lines.append("")
        unmapped = data["unmapped"]
        if data.get("kind") == "sheet":
            lines.append("Sheets: " + ", ".join(
                f"`{sheet}`" for sheet in data["sheets"]
            ))
            lines.append("")
        if not unmapped:
            lines.append("No unmapped keys.")
            lines.append("")
            continue
        items = sorted(unmapped.items(), key=lambda item: (-item[1], item[0]))
        lines.extend(["| key | records |", "|---|---:|"])
        for key, count in items[:MAX_UNMAPPED_KEYS]:
            lines.append(f"| `{cell(key)}` | {count} |")
        if len(items) > MAX_UNMAPPED_KEYS:
            lines.append(
                f"| … {len(items) - MAX_UNMAPPED_KEYS} more | |"
            )
        lines.append("")
        if data.get("session_unmapped"):
            lines.append("FIT session keys without a scalar mapping: ")
            lines.append(
                ", ".join(
                    f"`{cell(key)}` ({count})"
                    for key, count in sorted(
                        data["session_unmapped"].items()
                    )
                )
            )
            lines.append("")
    return lines


# -- tags ----------------------------------------------------------------


def tag_audit(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute(
        """
        SELECT t.tag AS tag,
               COUNT(*) AS count,
               GROUP_CONCAT(DISTINCT t.source) AS sources,
               MIN(a.local_date) AS first,
               MAX(a.local_date) AS last
        FROM activity_tags t
        JOIN activities a ON a.id = t.activity_id
        WHERE a.excluded_at IS NULL
        GROUP BY t.tag
        ORDER BY count DESC, tag
        """
    ).fetchall()
    return [
        {
            "tag": row["tag"],
            "count": row["count"],
            "sources": row["sources"] or "",
            "first": row["first"] or "",
            "last": row["last"] or "",
            "meaning": _tag_meaning(row["tag"]),
        }
        for row in rows
    ]


def _tag_meaning(tag: str) -> str:
    return meaning_label(tag)


def tag_section(tags: list[dict]) -> list[str]:
    if not tags:
        return ["## Tags", "", "No tags stored.", ""]
    unmapped = [tag for tag in tags if tag["meaning"] == "unmapped"]
    mapped = [tag for tag in tags if tag["meaning"] != "unmapped"]
    lines = [
        "## Tags",
        "",
        f"{len(tags)} distinct tags; {len(unmapped)} unmapped, "
        f"{len(mapped)} with a known meaning.",
        "",
        "### Unmapped tags",
        "",
        "| tag | count | sources | first | last |",
        "|---|---:|---|---|---|",
    ]
    if not unmapped:
        lines.append("| - | 0 | - | - | - |")
    for tag in unmapped:
        lines.append(
            f"| `{cell(tag['tag'])}` | {tag['count']} | "
            f"{cell(tag['sources'])} | {tag['first']} | {tag['last']} |"
        )
    lines.extend(
        [
            "",
            "### Known tags",
            "",
            "| tag | meaning | count |",
            "|---|---|---:|",
        ]
    )
    if not mapped:
        lines.append("| - | - | 0 |")
    for tag in mapped:
        lines.append(
            f"| `{cell(tag['tag'])}` | {tag['meaning']} | "
            f"{tag['count']} |"
        )
    lines.append("")
    return lines


