"""Per-athlete source configuration (``sources.toml``).

Capability lives in :class:`SourceProfile`; this module owns the athlete's
choices: which sources are enabled, what an unmatched row does, where social
text goes, and which optional capabilities of a source run. Credentials stay
in ``.env``.

Capability selection is not precedence: turning a capability off skips that
step, but field ownership still follows the owner-based rules in
:mod:`hobbyjogging_core.import_rules`.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .import_rules import SOURCES, SourceProfile

CONFIG_ENV = "HOBBYJOGGING_SOURCES"
DEFAULT_CONFIG_PATH = Path("sources.toml")

CREATE_CHOICES = ("create", "review", "ignore")
TITLE_CHOICES = ("social", "name")
DESCRIPTION_CHOICES = ("social", "description")

BASE_KEYS = frozenset({"enabled", "create", "title", "description"})

# The create/review/ignore policy is wired for the enrichment sources in this
# pass; the recording sources always create and are governed by enabled.
POLICY_SOURCES = frozenset({"strava", "runalyze"})

# A TOML capability key selects one profile entity. The profile stays the
# single capability declaration; this map only names the athlete-facing switch.
CAPABILITY_TOGGLES: dict[str, dict[str, str]] = {
    "runalyze": {
        "tags": "tags",
        "gear": "gear",
        "races": "race_result",
        "vo2max": "vo2max",
        "workout_type": "workout_type",
        "trimp": "trimp",
    },
    "garmin": {
        "wellness": "wellness",
    },
}

# A capability can also gate a canonical field that is not an entity of its
# own (the TRIMP fallback fills ``training_load``).
CAPABILITY_FIELDS: dict[str, dict[str, frozenset[str]]] = {
    "runalyze": {
        "trimp": frozenset({"training_load"}),
    },
}


def _validate_capability_map() -> None:
    for source, toggles in CAPABILITY_TOGGLES.items():
        profile = SOURCES.get(source)
        if profile is None:
            raise RuntimeError(
                f"capability toggle names an unknown source: {source}"
            )
        for key, entity in toggles.items():
            if entity not in profile.entities:
                raise RuntimeError(
                    f"{source}.{key} selects {entity!r}, which its profile "
                    "does not declare"
                )
    for source, fields_by_key in CAPABILITY_FIELDS.items():
        for key, fields in fields_by_key.items():
            if key not in CAPABILITY_TOGGLES.get(source, {}):
                raise RuntimeError(
                    f"{source}.{key} gates fields but is not a toggle"
                )
            missing = fields - SOURCES[source].creation_fields
            if missing:
                raise RuntimeError(
                    f"{source}.{key} gates undeclared field(s): "
                    f"{sorted(missing)}"
                )


_validate_capability_map()


@dataclass(frozen=True)
class SourcePolicy:
    """The athlete's choice for one source."""

    name: str
    enabled: bool = True
    create: str = "create"
    title: str = "social"
    description: str = "social"
    # The enabled capability keys (``CAPABILITY_TOGGLES`` for this source).
    capabilities: frozenset[str] = frozenset()

    @property
    def profile(self) -> SourceProfile:
        return SOURCES[self.name]

    def capability_enabled(self, key: str) -> bool:
        return key in self.capabilities


@dataclass(frozen=True)
class SourcesConfig:
    """The effective policy for every configurable source."""

    policies: dict[str, SourcePolicy]
    path: Path | None = None

    def policy(self, name: str) -> SourcePolicy:
        try:
            return self.policies[name]
        except KeyError:
            known = ", ".join(sorted(self.policies))
            raise KeyError(
                f"unknown source {name!r}; known sources: {known}"
            ) from None

    def enabled(self, name: str) -> bool:
        return self.policy(name).enabled

    def capability(self, name: str, key: str) -> bool:
        """Whether one selected capability of an enabled source runs."""
        policy = self.policy(name)
        if key not in CAPABILITY_TOGGLES.get(name, {}):
            known = ", ".join(sorted(CAPABILITY_TOGGLES.get(name, {})))
            raise KeyError(
                f"{name} has no {key!r} capability; known: {known or 'none'}"
            )
        return policy.capability_enabled(key)

    def create(self, name: str, override: str | None = None) -> str:
        """The effective unmatched-row policy, with a one-off override."""
        value = override or self.policy(name).create
        if value not in CREATE_CHOICES:
            raise ValueError(
                f"create must be one of {CREATE_CHOICES}, got {value!r}"
            )
        return value


def default_capabilities(name: str) -> frozenset[str]:
    """Every declared capability is on unless the athlete turns it off."""
    return frozenset(CAPABILITY_TOGGLES.get(name, {}))


def default_policies() -> dict[str, SourcePolicy]:
    return {
        name: SourcePolicy(
            name=name,
            create="create" if profile.yields_activities else "ignore",
            capabilities=default_capabilities(name),
        )
        for name, profile in SOURCES.items()
        if name != "manual"
    }


def load_sources(path: str | Path | None = None) -> SourcesConfig:
    """Load ``sources.toml``, falling back to the code defaults.

    A path passed explicitly, or ``HOBBYJOGGING_SOURCES``, must exist; the
    default ``./sources.toml`` is optional.
    """
    explicit = path is not None
    if path is None:
        path = os.environ.get(CONFIG_ENV) or DEFAULT_CONFIG_PATH
    path = Path(path).expanduser()

    policies = default_policies()
    if not path.is_file():
        if explicit or os.environ.get(CONFIG_ENV):
            raise FileNotFoundError(f"sources config not found: {path}")
        return SourcesConfig(policies=policies)

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    unknown = set(data) - {"sources"}
    if unknown:
        raise ValueError(
            f"unknown top-level key(s) in {path}: {sorted(unknown)}"
        )

    sources = data.get("sources", {})
    if not isinstance(sources, dict):
        raise ValueError(f"[sources] must be a table in {path}")

    for name, values in sources.items():
        if name == "manual":
            raise ValueError("manual is not a configurable source")
        if name not in SOURCES:
            known = ", ".join(sorted(policies))
            raise ValueError(
                f"unknown source {name!r} in {path}; known: {known}"
            )
        if not isinstance(values, dict):
            raise ValueError(f"[sources.{name}] must be a table")

        toggles = CAPABILITY_TOGGLES.get(name, {})
        allowed = BASE_KEYS | set(toggles)
        extra = set(values) - allowed
        if extra:
            raise ValueError(
                f"unknown key(s) for {name}: {sorted(extra)}; "
                f"allowed: {', '.join(sorted(allowed))}"
            )

        profile = SOURCES[name]
        current = policies[name]

        enabled = values.get("enabled", current.enabled)
        if not isinstance(enabled, bool):
            raise ValueError(f"{name}.enabled must be true or false")

        create = values.get("create", current.create)
        if create not in CREATE_CHOICES:
            raise ValueError(
                f"{name}.create must be one of {CREATE_CHOICES}"
            )
        if not profile.yields_activities and "create" in values:
            raise ValueError(
                f"{name} does not yield activity rows; create is not "
                "configurable"
            )
        if "create" in values and name not in POLICY_SOURCES:
            raise ValueError(
                f"{name}.create is not wired yet; use enabled"
            )

        title = values.get("title", current.title)
        if title not in TITLE_CHOICES:
            raise ValueError(f"{name}.title must be one of {TITLE_CHOICES}")

        description = values.get("description", current.description)
        if description not in DESCRIPTION_CHOICES:
            raise ValueError(
                f"{name}.description must be one of {DESCRIPTION_CHOICES}"
            )

        selected = set(current.capabilities)
        for key in toggles:
            value = values.get(key, key in current.capabilities)
            if not isinstance(value, bool):
                raise ValueError(f"{name}.{key} must be true or false")
            if value:
                selected.add(key)
            else:
                selected.discard(key)

        policies[name] = SourcePolicy(
            name=name,
            enabled=enabled,
            create=create,
            title=title,
            description=description,
            capabilities=frozenset(selected),
        )

    return SourcesConfig(policies=policies, path=path)
