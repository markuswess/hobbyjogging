"""Render the import rules, source policy and payload mapping."""

from __future__ import annotations

from hobbyjogging_core.capabilities import (
    DASHBOARD_CAPABILITIES,
    capability_availability,
    source_rows,
    uncovered_entities,
    uncovered_fields,
)
from hobbyjogging_core.import_rules import (
    FIELD_RULES,
    MANUAL_FIELDS,
    FieldRule,
)
from hobbyjogging_core.sources_config import (
    CAPABILITY_TOGGLES,
    POLICY_SOURCES,
    SourcesConfig,
)
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
        toggles = CAPABILITY_TOGGLES.get(name, {})
        if toggles:
            enabled = ",".join(
                key for key in toggles
                if policy.capability_enabled(key)
            ) or "-"
            disabled = ",".join(
                key for key in toggles
                if not policy.capability_enabled(key)
            ) or "-"
            lines[-1] += (
                f"  capabilities={enabled} disabled={disabled}"
            )
        if not profile.yields_activities:
            lines[-1] += "  (files only)"
    return "\n".join(lines)


def _reason_text(reasons: tuple[tuple[str, str], ...]) -> str:
    if not reasons:
        return "not available in any profile"
    return "; ".join(
        f"{source} ({reason})" for source, reason in reasons
    )


def _capability_sections(config: SourcesConfig) -> list[str]:
    lines = [
        "## Capability matrix",
        "",
        "| source | enabled | yields activities | match | budget | detail | "
        "record types | creation fields |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in source_rows(config):
        lines.append(
            f"| {row.name} | {'yes' if row.enabled else 'no'} | "
            f"{'yes' if row.yields_activities else 'no'} | "
            f"{row.match} | {row.request_budget or '-'} | "
            f"{'yes' if row.detail_required else 'no'} | "
            f"{', '.join(row.entities) or '-'} | "
            f"{', '.join(row.creation_fields) or '-'} |"
        )

    lines.extend(
        [
            "",
            "## Capability selection",
            "",
            "| source | capability | enabled |",
            "|---|---|---|",
        ]
    )
    selection_rows = 0
    for name in sorted(config.policies):
        policy = config.policy(name)
        for key in CAPABILITY_TOGGLES.get(name, {}):
            selection_rows += 1
            enabled = policy.capability_enabled(key)
            state = "yes" if enabled else "no"
            if not policy.enabled:
                state += " (source disabled)"
            lines.append(f"| {name} | {key} | {state} |")
    if selection_rows == 0:
        lines.append("| - | - | no selectable capabilities |")

    lines.extend(["", "## Uncovered record types", ""])
    entities = uncovered_entities(config)
    if not entities:
        lines.append("Every record type is supplied by an enabled source.")
    else:
        for row in entities:
            lines.append(
                f"- `{row.name}` — {_reason_text(row.reasons)}"
            )

    lines.extend(["", "## Uncovered activity fields", ""])
    fields = uncovered_fields(config)
    if not fields:
        lines.append("Every activity field is supplied by an enabled source.")
    else:
        for row in fields:
            lines.append(
                f"- `{row.name}` — {_reason_text(row.reasons)}"
            )

    lines.extend(["", "## Dashboard capabilities", ""])
    for capability in DASHBOARD_CAPABILITIES:
        providers, hints = capability_availability(config, capability)
        detail = (
            f"covered by {', '.join(providers)}"
            if providers
            else ("; ".join(hints) or "not available")
        )
        lines.append(f"- {capability.label}: {detail}")

    lines.append("")
    return lines


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

    lines.extend([""] + _capability_sections(config))

    lines.extend(["## Field rules", ""])
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
