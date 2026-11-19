"""Render the import rules, source policy and payload mapping."""

from __future__ import annotations

from hobbyjogging_core.import_rules import (
    FIELD_RULES,
    MANUAL_FIELDS,
    SOURCES,
    FieldRule,
)
from hobbyjogging_core.sources_config import POLICY_SOURCES, SourcesConfig
from hobbyjogging_core.workouts import (
    QUALITY_METHODS,
    QUALITY_TARGETS,
    WORKOUT_METHODS,
    WORKOUT_TARGETS,
)

from .causes import CAUSES
from .derive import FIELD_MAPS, SHEET_MAPS
from .matching import MatchPolicy
from .quality import REVIEW_CATEGORIES


def format_sources(config: SourcesConfig) -> str:
    lines = ["Sources:"]
    for name in sorted(config.policies):
        policy = config.policy(name)
        profile = policy.profile
        if not profile.yields_activities:
            create = "-"
        elif name in POLICY_SOURCES:
            create = policy.create
        else:
            create = "always"
        lines.append(
            f"  {name:10} enabled={str(policy.enabled):5} "
            f"create={create:6} "
            f"title={policy.title:6} description={policy.description}"
        )
        if not profile.yields_activities:
            lines[-1] += "  (files only)"
    return "\n".join(lines)


def settings_report(config: SourcesConfig) -> str:
    lines = [
        "# Import settings",
        "",
        "## Sources",
        "",
        "| source | enabled | unmatched | title | description | match | detail |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in sorted(config.policies):
        policy = config.policy(name)
        profile = policy.profile
        if not profile.yields_activities:
            create = "-"
        elif name in POLICY_SOURCES:
            create = policy.create
        else:
            create = "always"
        lines.append(
            f"| {name} | {'yes' if policy.enabled else 'no'} | "
            f"{create} | {policy.title} | {policy.description} | "
            f"{profile.match} | {'yes' if profile.detail_required else 'no'} |"
        )

    lines.extend(["", "## Field rules", ""])
    lines.append(
        "| field | conflict | tolerance | authority | manual | placeholder |"
    )
    lines.append("|---|---|---|---|---|---|")
    for field in sorted(FIELD_RULES):
        rule: FieldRule = FIELD_RULES[field]
        tolerance = (
            f"{rule.tolerance[0]:g} / {rule.tolerance[1]:g}"
            if rule.tolerance
            else "-"
        )
        lines.append(
            f"| {field} | {'yes' if rule.conflict else 'no'} | {tolerance} | "
            f"{', '.join(rule.authority) or '-'} | "
            f"{'yes' if rule.manual else 'no'} | "
            f"{'yes' if rule.placeholder else 'no'} |"
        )

    policy = MatchPolicy()
    lines.extend(
        [
            "",
            "## Matching",
            "",
            "existing link → temporal overlap (a FIT segment may be contained) "
            "→ distance agreement → same-day exact twin → `ambiguous_match` "
            "review → create only when nothing is left to review.",
            "",
            f"- distance tolerance: {policy.distance_ratio:.0%} or "
            f"{policy.distance_m:g} m",
            f"- exact twin: {policy.exact_duration_s:g} s and "
            f"{policy.exact_distance_m:g} m",
            "",
            "## Review categories",
            "",
            ", ".join(f"`{category}`" for category in REVIEW_CATEGORIES),
            "",
            "## Conflict causes",
            "",
        ]
    )
    for cause in CAUSES.values():
        lines.append(
            f"- `{cause.name}` — {cause.label} ({cause.severity}"
            f"{', resolvable' if cause.resolvable else ''}): "
            f"{cause.explanation}"
        )

    lines.extend(
        [
            "",
            "## Classification",
            "",
            f"- methods: {', '.join(sorted(set(WORKOUT_METHODS.values())))}",
            f"- targets: {', '.join(sorted(set(WORKOUT_TARGETS.values())))}",
            f"- quality methods: {', '.join(sorted(QUALITY_METHODS))}",
            f"- quality targets: {', '.join(sorted(QUALITY_TARGETS))}",
            "",
            "## Payload mapping",
            "",
        ]
    )
    for source, fields in FIELD_MAPS.items():
        lines.append(f"### {source}")
        if not fields:
            lines.append("")
            lines.append("(no canonical activity fields)")
            lines.append("")
            continue
        for field in sorted(fields):
            keys = ", ".join(fields[field].keys) or "(derived)"
            lines.append(f"- `{field}` ← {keys}")
        lines.append("")

    for sheet, fields in SHEET_MAPS.items():
        lines.append(f"### sheet / {sheet}")
        for field in sorted(fields):
            keys = ", ".join(fields[field].keys) or "(derived)"
            lines.append(f"- `{field}` ← {keys}")
        lines.append("")

    lines.extend(
        [
            "## Manual edits",
            "",
            f"- editable fields: {', '.join(MANUAL_FIELDS)}",
            "- manual values and owner patches live in "
            "`activity_manual_fields` and are never overwritten by an import.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
