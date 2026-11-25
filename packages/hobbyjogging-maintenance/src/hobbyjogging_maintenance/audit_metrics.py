"""Session-average metrics: coverage, units and cross-source conflicts."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from hobbyjogging_core.import_rules import METRIC_FIELDS
from hobbyjogging_import.fit import parse_fit_file
from hobbyjogging_import.metrics import derive_metrics

UNIT_LABELS = {
    "cadence": "spm (run) / rpm (ride)",
    "stride_m": "m",
    "vertical_oscillation_mm": "mm",
    "stance_time_ms": "ms",
    "stance_time_pct": "%",
    "stance_balance_pct": "%",
    "vertical_ratio_pct": "%",
    "respiration_bpm": "breaths/min",
    "power_w": "W",
    "calories_kcal": "kcal",
    "training_effect": "0-5",
    "gap_mps": "m/s",
    "altitude_avg_m": "m",
    "altitude_min_m": "m",
    "altitude_max_m": "m",
}

SOURCES = ("fit", "intervals", "runalyze", "sheet")


def build_metrics_audit(
    connection: sqlite3.Connection,
    *,
    fit_sample: int = 100,
) -> list[str]:
    stored = _stored(connection)
    fit = _fit(connection, fit_sample)
    by_activity = {
        activity_id: dict(sources)
        for activity_id, sources in stored["by_activity"].items()
    }
    for activity_id, sources in fit["by_activity"].items():
        by_activity.setdefault(activity_id, {}).update(sources)
    conflicts = _conflicts(by_activity)

    lines = [
        "## Session-average metrics",
        "",
        "Canonical units: run cadence is steps/min (a one-leg value at or "
        "below 120 is doubled), ride cadence is rpm, stride is metres and "
        "the dynamics are millimetres, milliseconds and percent.",
        "",
        f"Coverage is non-null values per source record scanned. "
        f"FIT is a sample of {fit['files']} raw files because older stored "
        "payloads predate these fields.",
        "",
        "| field | unit | fit sample | intervals | runalyze | sheet |",
        "|---|---|---:|---:|---:|---:|",
    ]

    for field in METRIC_FIELDS:
        cells = [
            _share(fit["counts"].get(field, 0), fit["files"]),
            _share(
                stored["counts"]["intervals"].get(field, 0),
                stored["records"].get("intervals", 0),
            ),
            _share(
                stored["counts"]["runalyze"].get(field, 0),
                stored["records"].get("runalyze", 0),
            ),
            _share(
                stored["counts"]["sheet"].get(field, 0),
                stored["records"].get("sheet", 0),
            ),
        ]
        lines.append(
            f"| `{field}` | {UNIT_LABELS[field]} | "
            + " | ".join(cells)
            + " |"
        )

    lines.extend(
        [
            "",
            "### Metric conflicts",
            "",
            "Fields where two sources disagree by more than 2 % "
            "(or 0.5 in the field's unit), on the same activity "
            "(the FIT sample is included).",
            "",
            "| field | compared | disagree |",
            "|---|---:|---:|",
        ]
    )
    if not conflicts:
        lines.append("| - | 0 | 0 |")
    for field in METRIC_FIELDS:
        compared, disagree = conflicts.get(field, (0, 0))
        if compared:
            lines.append(f"| `{field}` | {compared} | {disagree} |")

    lines.extend(
        [
            "",
            "The row stores session averages only; per-second streams stay in "
            "the FIT archive and are not part of the canonical database.",
            "",
        ]
    )
    return lines


def _stored(connection: sqlite3.Connection) -> dict:
    counts = {source: Counter() for source in SOURCES}
    records = Counter()
    by_activity: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)

    rows = connection.execute(
        """
        SELECT a.id, a.sport, sr.source, sr.payload_json
        FROM source_records sr
        JOIN activity_sources als ON als.source_record_id = sr.id
        JOIN activities a ON a.id = als.activity_id
        WHERE a.excluded_at IS NULL
          AND sr.record_type = 'activity'
          AND sr.source IN ('intervals', 'runalyze', 'sheet')
        ORDER BY a.local_date, a.id, sr.source
        """
    ).fetchall()

    for row in rows:
        payload = _payload(row["payload_json"])
        if payload is None:
            continue
        source = row["source"]
        records[source] += 1
        values = derive_metrics(source, payload, row["sport"] or "")
        counts[source].update(values.keys())
        if values:
            by_activity[row["id"]][source] = values

    return {
        "counts": counts,
        "records": records,
        "by_activity": by_activity,
    }


def _fit(connection: sqlite3.Connection, sample: int) -> dict:
    counts: Counter[str] = Counter()
    by_activity: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    if sample <= 0:
        return {
            "counts": counts,
            "files": 0,
            "by_activity": by_activity,
        }

    rows = connection.execute(
        """
        SELECT DISTINCT sr.raw_path, a.id, a.sport, sr.external_id
        FROM source_records sr
        JOIN activity_sources als ON als.source_record_id = sr.id
        JOIN activities a ON a.id = als.activity_id
        WHERE a.excluded_at IS NULL
          AND sr.source = 'fit'
          AND sr.raw_path IS NOT NULL
        ORDER BY a.local_date, a.id
        LIMIT ?
        """,
        (sample,),
    ).fetchall()

    files = 0
    for row in rows:
        path = Path(row["raw_path"]).expanduser()
        if not path.is_file():
            continue
        try:
            summary = parse_fit_file(path)
        except Exception:
            continue
        index = _session_index(row["external_id"])
        if index is None or not 1 <= index <= len(summary.sessions):
            continue
        files += 1
        values = derive_metrics(
            "fit",
            {"session": summary.sessions[index - 1].__dict__},
            row["sport"] or "",
        )
        counts.update(values.keys())
        if values:
            by_activity[row["id"]]["fit"] = values

    return {
        "counts": counts,
        "files": files,
        "by_activity": by_activity,
    }


def _conflicts(
    by_activity: dict[str, dict[str, dict[str, float]]],
) -> dict:
    compared: Counter[str] = Counter()
    disagree: Counter[str] = Counter()

    for sources in by_activity.values():
        if len(sources) < 2:
            continue
        names = list(sources)
        for field in METRIC_FIELDS:
            values = [
                sources[source].get(field)
                for source in names
                if sources[source].get(field) is not None
            ]
            if len(values) < 2:
                continue
            compared[field] += 1
            if max(values) - min(values) > _tolerance(field, values):
                disagree[field] += 1

    return {
        field: (compared[field], disagree[field])
        for field in METRIC_FIELDS
        if compared[field]
    }


def _tolerance(field: str, values: list[float]) -> float:
    if field == "cadence":
        return 2.0
    if field in ("altitude_avg_m", "altitude_min_m", "altitude_max_m"):
        return 2.0
    return max(0.5, 0.02 * max(abs(value) for value in values))


def _session_index(external_id: str | None) -> int | None:
    if not external_id:
        return None
    suffix = str(external_id).rsplit(":", 1)[-1]
    try:
        return int(suffix)
    except ValueError:
        return None


def _share(value: int, total: int) -> str:
    if not total:
        return "-"
    return f"{value} ({value / total * 100:.0f} %)"


def _payload(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None
