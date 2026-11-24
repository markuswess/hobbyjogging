"""Source capability matrix and the visible-dashboard coverage.

Capability is declared by :class:`~hobbyjogging_core.import_rules.SourceProfile`;
selection is the athlete's ``sources.toml``. This module joins the two for the
settings renderer and the doctor, so the matrix, the uncovered list and the
missing-capability warning cannot drift.

Nothing here decides field ownership: that stays in ``FIELD_RULES``. A
capability only says whether a step can supply a record type or field at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from .import_rules import SOURCES
from .sources_config import (
    CAPABILITY_FIELDS,
    CAPABILITY_TOGGLES,
    SourcesConfig,
)


@dataclass(frozen=True)
class SourceCapabilityRow:
    """One source's declared capabilities."""

    name: str
    enabled: bool
    yields_activities: bool
    match: str
    request_budget: str | None
    detail_required: bool
    entities: tuple[str, ...]
    creation_fields: tuple[str, ...]


@dataclass(frozen=True)
class Uncovered:
    """A capability no enabled source supplies, with the reason per source."""

    name: str
    reasons: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class DashboardCapability:
    """One visible dashboard area and what can supply it."""

    key: str
    label: str
    entities: frozenset[str] = frozenset()
    fields: frozenset[str] = frozenset()
    manual_hint: str = ""


# The fixed list the doctor warns about. Add a capability here only if the
# dashboard visibly depends on it; the settings inverse is broader.
DASHBOARD_CAPABILITIES: tuple[DashboardCapability, ...] = (
    DashboardCapability(
        "wellness",
        "wellness (resting HR/HRV/sleep)",
        entities=frozenset({"wellness"}),
    ),
    DashboardCapability(
        "load",
        "training load",
        entities=frozenset({"trimp"}),
        fields=frozenset({"training_load"}),
    ),
    DashboardCapability(
        "zones",
        "HR/pace zones",
        entities=frozenset({"zones"}),
        manual_hint="enter manual thresholds with `threshold add`",
    ),
    DashboardCapability(
        "social",
        "social text",
        entities=frozenset({"social"}),
    ),
    DashboardCapability(
        "reps",
        "typed reps/intervals",
        entities=frozenset({"workout_type", "intervals"}),
    ),
    DashboardCapability(
        "races",
        "race results",
        entities=frozenset({"race_result"}),
    ),
)


def source_rows(config: SourcesConfig) -> list[SourceCapabilityRow]:
    """Return the matrix rows, one per configurable source."""
    rows = []
    for name in sorted(config.policies):
        policy = config.policy(name)
        profile = policy.profile
        rows.append(
            SourceCapabilityRow(
                name=name,
                enabled=policy.enabled,
                yields_activities=profile.yields_activities,
                match=profile.match,
                request_budget=profile.request_budget,
                detail_required=profile.detail_required,
                entities=tuple(sorted(profile.entities)),
                creation_fields=tuple(sorted(profile.creation_fields)),
            )
        )
    return rows


def supplied_entities(
    config: SourcesConfig,
    name: str,
) -> frozenset[str]:
    """The profile's record types once disabled toggles are removed."""
    policy = config.policy(name)
    disabled = {
        CAPABILITY_TOGGLES[name][key]
        for key in CAPABILITY_TOGGLES.get(name, {})
        if not policy.capability_enabled(key)
    }
    return policy.profile.entities - disabled


def supplied_fields(
    config: SourcesConfig,
    name: str,
) -> frozenset[str]:
    """The profile's creation fields once disabled toggles are removed."""
    policy = config.policy(name)
    fields = set(policy.profile.creation_fields)
    for key, gated in CAPABILITY_FIELDS.get(name, {}).items():
        if not policy.capability_enabled(key):
            fields -= gated
    return frozenset(fields)


def all_entities() -> tuple[str, ...]:
    """Every record type any profile declares."""
    return tuple(sorted({
        entity
        for profile in SOURCES.values()
        for entity in profile.entities
    }))


def all_fields() -> tuple[str, ...]:
    """Every canonical activity field any profile can create."""
    return tuple(sorted({
        field
        for profile in SOURCES.values()
        for field in profile.creation_fields
    }))


def uncovered_entities(config: SourcesConfig) -> list[Uncovered]:
    """Record types no enabled source supplies, with the reason."""
    supplied = {
        name: supplied_entities(config, name)
        for name in config.policies
        if config.enabled(name)
    }
    covered = set().union(*supplied.values()) if supplied else set()

    rows = []
    for entity in all_entities():
        if entity in covered:
            continue
        rows.append(
            Uncovered(
                entity,
                tuple(_reasons(config, entity)),
            )
        )
    return rows


def uncovered_fields(config: SourcesConfig) -> list[Uncovered]:
    """Activity fields no enabled source can create, with the reason."""
    supplied = {
        name: supplied_fields(config, name)
        for name in config.policies
        if config.enabled(name)
    }
    covered = set().union(*supplied.values()) if supplied else set()

    rows = []
    for field in all_fields():
        if field in covered:
            continue
        rows.append(
            Uncovered(
                field,
                tuple(_field_reasons(config, field)),
            )
        )
    return rows


def capability_availability(
    config: SourcesConfig,
    capability: DashboardCapability,
) -> tuple[list[str], list[str]]:
    """Return the enabled providers and a reason per unavailable source."""
    providers = _providers(config, capability)
    if providers:
        return providers, []

    hints: list[str] = []
    for name in sorted(config.policies):
        policy = config.policy(name)
        profile = policy.profile
        has_entity = bool(capability.entities & profile.entities)
        has_field = bool(capability.fields & profile.creation_fields)
        if not has_entity and not has_field:
            continue
        if not policy.enabled:
            hints.append(f"available in {name} (source disabled)")
            continue
        hints.append(f"available in {name} (capability disabled)")
    if capability.manual_hint:
        hints.append(capability.manual_hint)
    return [], _unique(hints)


def _providers(
    config: SourcesConfig,
    capability: DashboardCapability,
) -> list[str]:
    providers = []
    for name in sorted(config.policies):
        if not config.enabled(name):
            continue
        if capability.entities & supplied_entities(config, name):
            providers.append(name)
            continue
        if capability.fields & supplied_fields(config, name):
            providers.append(name)
    return providers


def _reasons(config, entity) -> list[tuple[str, str]]:
    reasons = []
    for name in sorted(SOURCES):
        if name == "manual" or name not in config.policies:
            continue
        profile = SOURCES[name]
        if entity not in profile.entities:
            continue
        if config.enabled(name):
            reasons.append((name, "capability disabled"))
        else:
            reasons.append((name, "source disabled"))
    return reasons


def _field_reasons(config, field) -> list[tuple[str, str]]:
    reasons = []
    for name in sorted(SOURCES):
        if name == "manual" or name not in config.policies:
            continue
        profile = SOURCES[name]
        if field not in profile.creation_fields:
            continue
        if config.enabled(name):
            reasons.append((name, "capability disabled"))
        else:
            reasons.append((name, "source disabled"))
    return reasons


def _unique(values: list[str]) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
