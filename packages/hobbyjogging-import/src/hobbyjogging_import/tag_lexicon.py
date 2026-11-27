"""The tag lexicon: what a stored activity tag means and which rule it feeds.

A tag is an input, not a classification. This module is the one place that
turns a normalized tag into a meaning: a workout set, illness/recovery
evidence, a race or trail marker, a rep length, a sheet area code, context, or
an ignored note. Rules read the meaning; an unmapped tag stays unmapped and no
rule invents one for it.

Keep this a code-level module while there is one athlete. A
``tag_semantics`` table is only justified when a second athlete's tags must be
mapped without a release.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

# Kinds a consumer can branch on. ``workout`` carries a method/target set;
# ``rep_time``/``rep_distance`` carry a value; the rest are evidence or
# context. ``ignore`` is a deliberate no-op (e.g. the fatigue note).
@dataclass(frozen=True)
class TagMeaning:
    label: str
    kind: str
    methods: frozenset[str] = frozenset()
    targets: frozenset[str] = frozenset()
    value: float | None = None
    unit: str = ""


def _workout(label, methods=(), targets=()):
    return TagMeaning(
        label,
        "workout",
        frozenset(methods),
        frozenset(targets),
    )


def _context(label):
    return TagMeaning(label, "context")


TAG_MEANINGS: dict[str, TagMeaning] = {
    # Sheet training-area codes, not workout types.
    "w": TagMeaning("sheet area code", "area"),
    "m": TagMeaning("sheet area code", "area"),
    "wb": TagMeaning("sheet area code", "area"),
    "a": TagMeaning("sheet area code", "area"),
    "t": TagMeaning("sheet area code", "area"),
    "i": TagMeaning("sheet area code", "area"),
    # Illness and recovery.
    "krank": TagMeaning("illness", "illness"),
    "verkühlt": TagMeaning("illness", "illness"),
    "infekt": TagMeaning("illness", "illness"),
    "magen-darm": TagMeaning("illness", "illness"),
    "fieber": TagMeaning("illness", "illness"),
    "grippe": TagMeaning("illness", "illness"),
    "erkältet": TagMeaning("illness", "illness"),
    "wieder gesund": TagMeaning("recovered", "recovered"),
    "schlapp": TagMeaning("ignored (fatigue)", "ignore"),
    # Race and trail evidence. "Raceday" often marks the warm-up or cool-down
    # around a race, so it is context, not a race method.
    "raceday": _context("race-day context"),
    "race day": _context("race-day context"),
    "race": TagMeaning("race", "race"),
    "wettkampf": TagMeaning("race", "race"),
    "virtual race": TagMeaning("race", "race"),
    "marathontag": TagMeaning("race", "race"),
    "trail": TagMeaning("trail", "trail"),
    "trailrun": TagMeaning("trail", "trail"),
    "trail run": TagMeaning("trail", "trail"),
    # Workout sets. Threshold/quality tags are the highest-confidence kind.
    "sub threshold": _workout(
        "subT / LT1", ("intervals",), ("subthreshold",)
    ),
    "subthreshold": _workout(
        "subT / LT1", ("intervals",), ("subthreshold",)
    ),
    "sub-threshold": _workout(
        "subT / LT1", ("intervals",), ("subthreshold",)
    ),
    "subt": _workout("subT / LT1", ("intervals",), ("subthreshold",)),
    "lt1": _workout("subT / LT1", ("intervals",), ("lt1",)),
    "lt 1": _workout("subT / LT1", ("intervals",), ("lt1",)),
    "ltt": _workout("running drills", ("drills",)),
    "drill": _workout("running drills", ("drills",)),
    "drills": _workout("running drills", ("drills",)),
    "lauf-abc": _workout("running drills", ("drills",)),
    "lauf abc": _workout("running drills", ("drills",)),
    "lactate threshhold": _workout(
        "threshold", ("continuous",), ("threshold",)
    ),
    "lactate threshold": _workout(
        "threshold", ("continuous",), ("threshold",)
    ),
    "jd threshhold": _workout(
        "threshold", ("continuous",), ("threshold",)
    ),
    "jd threshold": _workout(
        "threshold", ("continuous",), ("threshold",)
    ),
    "aerobic threshhold": _workout(
        "threshold", ("continuous",), ("threshold",)
    ),
    "aerobic threshold": _workout(
        "threshold", ("continuous",), ("threshold",)
    ),
    "garmin threshhold test": _workout(
        "threshold", ("continuous",), ("threshold",)
    ),
    "laktat toleranz": _workout(
        "threshold", ("continuous",), ("threshold",)
    ),
    "tempolauf": _workout("tempo / threshold", ("continuous",), ("threshold",)),
    "tempo": _workout("tempo / threshold", ("continuous",), ("threshold",)),
    "threshold": _workout("tempo / threshold", ("continuous",), ("threshold",)),
    "schwelle": _workout("tempo / threshold", ("continuous",), ("threshold",)),
    "cruise intervals": _workout(
        "intervals", ("intervals",), ("threshold",)
    ),
    "marathontempo": _workout(
        "marathon pace", ("continuous",), ("marathon",)
    ),
    "hm tempo": _workout("marathon pace", ("continuous",), ("marathon",)),
    "tempowechsel": _workout("fartlek", ("fartlek",), ("other",)),
    "wechseltempo": _workout("fartlek", ("fartlek",), ("other",)),
    "temponadelstiche": _workout(
        "tempo with strides", ("continuous", "strides"), ("threshold",)
    ),
    "endbeschleunigung": _workout(
        "progression", ("progression",), ("base",)
    ),
    "progressiv": _workout("progression", ("progression",), ("base",)),
    "progression": _workout("progression", ("progression",), ("base",)),
    "fahrtspiel": _workout("fartlek", ("fartlek",), ("other",)),
    "fartlek": _workout("fartlek", ("fartlek",), ("other",)),
    "longjog": _workout("long run", ("long_run",), ("base",)),
    "longrun": _workout("long run", ("long_run",), ("base",)),
    "long run": _workout("long run", ("long_run",), ("base",)),
    "regeneration": _workout("recovery", ("continuous",), ("recovery",)),
    "regenerativ": _workout("recovery", ("continuous",), ("recovery",)),
    "recovery": _workout("recovery", ("continuous",), ("recovery",)),
    "strides": _workout("strides", ("strides",), ("base",)),
    "stride": _workout("strides", ("strides",), ("base",)),
    "sprints": _workout("sprints", ("strides",), ("speed",)),
    "hillsprints": _workout("sprints", ("strides",), ("speed",)),
    "intervalle": _workout("intervals", ("intervals",), ("other",)),
    "intervals": _workout("intervals", ("intervals",), ("other",)),
    "interval": _workout("intervals", ("intervals",), ("other",)),
    "segmente": _workout("intervals", ("intervals",), ("other",)),
    "hiit": _workout("intervals", ("intervals",), ("vo2max",)),
    "cross intervals": _workout("intervals", ("intervals",), ("other",)),
    "bergaufintervalle": _workout(
        "hill intervals", ("intervals",), ("vo2max",)
    ),
    "rucksackintervalle": _workout(
        "intervals", ("intervals",), ("other",)
    ),
    "speedwork": _workout("speed", ("intervals",), ("speed",)),
    "pyramide": _workout("intervals", ("intervals",), ("other",)),
    "30-20-10": _workout("speed", ("intervals",), ("speed",)),
    "lit": _workout("low intensity", ("continuous",), ("base",)),
    "lit+": _workout("low intensity", ("continuous",), ("base",)),
    "superlit": _workout("low intensity", ("continuous",), ("base",)),
    "gat1": _workout("low intensity", ("continuous",), ("base",)),
    "jd intervals": _workout("intervals", ("intervals",), ("other",)),
    "jd repetition": _workout("intervals", ("intervals",), ("other",)),
    "jd fast reps": _workout("intervals", ("intervals",), ("vo2max",)),
    "jd marathontempo": _workout(
        "marathon pace", ("continuous",), ("marathon",)
    ),
    "jd q1": _context("plan quality session"),
    "jd q2": _context("plan quality session"),
    "jd q3": _context("plan quality session"),
    "jd all paces": _context("plan paces"),
    # Warm-up and cool-down tags are context, not a session type.
    "aufwärmen": _context("warm-up"),
    "einlaufen": _context("warm-up"),
    "aufwachen": _context("warm-up"),
    "warm up": _context("warm-up"),
    "warm-up": _context("warm-up"),
    "warmup": _context("warm-up"),
    "auslaufen": _context("cool-down"),
    "auslaufen+": _context("cool-down"),
    "cool down": _context("cool-down"),
    "cool-down": _context("cool-down"),
    "cooldown": _context("cool-down"),
    "laufbahn": _context("track"),
    "weinberge": _context("vineyards"),
    # Context: gear, weather, fueling, fatigue, plan notes, places of use.
    "kein pulsgurt": _context("no HR strap"),
    "puls hoch": _context("high HR"),
    "puls ungenau": _context("imprecise HR"),
    "ungenau": _context("imprecise measurement"),
    "nach puls": _context("by HR"),
    "bad gps": _context("bad GPS"),
    "late night": _context("late night"),
    "afterwork": _context("after work"),
    "early bird": _context("early morning"),
    "nüchtern": _context("fasted"),
    "rucksack": _context("backpack"),
    "kinderwagen": _context("stroller"),
    "thule": _context("trailer"),
    "thule half half": _context("trailer (half half)"),
    "supertrainers": _context("training shoes"),
    "supershoes": _context("racing shoes"),
    "barfußschuhe": _context("barefoot shoes"),
    "neue schuhe": _context("new shoes"),
    "rennrad": _context("road bike"),
    "lastenrad": _context("cargo bike"),
    "windig": _context("windy"),
    "heiß": _context("hot"),
    "sauheiß": _context("very hot"),
    "schnee": _context("snow"),
    "sauwetter": _context("bad weather"),
    "saukalt": _context("very cold"),
    "rutschig": _context("slippery"),
    "glatteis": _context("ice"),
    "urlaub": _context("holiday"),
    "sightseeing": _context("sightseeing"),
    "shopping": _context("shopping"),
    "bier": _context("beer"),
    "gönnung": _context("treat"),
    "all out": _context("all out"),
    "stehende intervallpausen": _context("standing rest"),
    "taper": _context("taper"),
    "tapering": _context("taper"),
    "abschlusstraining": _context("final workout"),
    "key session": _context("key session"),
    "q reduced": _context("reduced quality"),
    "failed quality": _context("failed quality"),
    "skipped quality": _context("skipped quality"),
    "failed intervals": _context("failed intervals"),
    "workout light": _context("light workout"),
    "double day": _context("double day"),
    "double easy": _context("double easy"),
    "back2back": _context("back-to-back"),
    "pb": _context("personal best"),
    "sieg": _context("win"),
    "verkatert": _context("hungover"),
    "muskelkater": _context("sore muscles"),
    "kopfweh": _context("headache"),
    "schwere beine": _context("heavy legs"),
    "noch nicht ganz fit": _context("not fully fit"),
    "jetlagged": _context("jet lag"),
    "marathon": _context("marathon distance"),
    "halbmarathon": _context("half-marathon distance"),
    "nölm": _context("race event"),
    "vcm": _context("race event"),
    "everesting": _context("everesting"),
    "packrafting": _context("packrafting"),
    "ultracycling": _context("ultracycling"),
    "koppeltraining": _context("brick session"),
    "badminton": _context("badminton"),
    "videoanalyse": _context("video analysis"),
    "lauftechnik": _workout("running drills", ("drills",)),
    "hüftstreckung": _context("hip extension"),
    "kraultechnik": _context("front-crawl technique"),
    "plyometrics": _context("plyometrics"),
    "kraft": _context("strength"),
    "stiegen": _context("stairs"),
    "gravel": _context("gravel"),
}


# Geographic tags. The value is the canonical place label and route name;
# aliases share one route. Keep this beside the lexicon while there is one
# athlete.
PLACE_ALIASES: dict[str, str] = {
    "wienerberg": "Wienerberg",
    "wienerbergteich": "Wienerberg",
    "kanal": "Donaukanal",
    "donaukanal": "Donaukanal",
    "hauptallee": "Hauptallee",
    "guntramsdorf-wien": "Guntramsdorf–Wien",
    "arsenal": "Arsenal",
    "wien-guntramsdorf": "Wien–Guntramsdorf",
    "prater": "Prater",
    "liesingbach": "Liesingbach",
    "helmut zilk park": "Helmut Zilk Park",
    "wien-mödling": "Wien–Mödling",
    "anninger": "Anninger",
    "bezirk": "Bezirk",
    "graz": "Graz",
    "paris": "Paris",
    "rundumadum": "Rundumadum",
    "weinberge": "Weinberge",
    "berlin": "Berlin",
    "donauinsel": "Donauinsel",
    "bassin saulx": "Bassin Saulx",
    "mödling - wien": "Mödling–Wien",
    "biedermannsdorf": "Biedermannsdorf",
    "lac du mail": "Lac du Mail",
    "mödlingbach": "Mödlingbach",
    "schweizergarten": "Schweizergarten",
    "schönbrunn": "Schönbrunn",
    "wiental": "Wiental",
    "laufbahn": "Laufbahn",
    "lcc lauf": "LCC Lauf",
}

TAG_MEANINGS.update(
    {
        tag: TagMeaning(label, "place")
        for tag, label in PLACE_ALIASES.items()
    }
)


# ``6'``, ``3'30''``, ``30''``, ``400m``, ``1km``, ``1 mile``. Rep lengths
# are evidence about structure, not a workout type by themselves.
_REP_MINUTES = re.compile(r"^(\d+)\s*'$")
_REP_MIN_SECONDS = re.compile(r"^(\d+)\s*'\s*(\d+)\s*''$")
_REP_SECONDS = re.compile(r"^(\d+)\s*''$")
_REP_METRES = re.compile(r"^(\d+(?:\.\d+)?)\s*m$")
_REP_KILOMETRES = re.compile(r"^(\d+(?:\.\d+)?)\s*km$")
_REP_MILE = re.compile(r"^(?:1\s*)?(?:mile|meile)$")


def normalize_tag(tag: object) -> str:
    """Casefold, collapse whitespace and trim a stored tag."""
    return " ".join(str(tag or "").strip().lower().split())


def lookup_tag(tag: object) -> TagMeaning | None:
    """Return the meaning of a tag, or ``None`` when it is unmapped."""
    token = normalize_tag(tag)
    if not token:
        return None

    exact = TAG_MEANINGS.get(token)
    if exact is not None:
        return exact

    match = _REP_MIN_SECONDS.match(token)
    if match:
        minutes, seconds = int(match.group(1)), int(match.group(2))
        return TagMeaning(
            f"rep {minutes}:{seconds:02d}",
            "rep_time",
            value=minutes * 60 + seconds,
            unit="s",
        )

    match = _REP_MINUTES.match(token)
    if match:
        minutes = int(match.group(1))
        return TagMeaning(
            f"rep {minutes} min",
            "rep_time",
            value=minutes * 60,
            unit="s",
        )

    match = _REP_SECONDS.match(token)
    if match:
        seconds = int(match.group(1))
        return TagMeaning(
            f"rep {seconds} s",
            "rep_time",
            value=seconds,
            unit="s",
        )

    match = _REP_METRES.match(token)
    if match:
        metres = float(match.group(1))
        return TagMeaning(
            f"rep {metres:g} m",
            "rep_distance",
            value=metres,
            unit="m",
        )

    match = _REP_KILOMETRES.match(token)
    if match:
        metres = float(match.group(1)) * 1000.0
        return TagMeaning(
            f"rep {metres:g} m",
            "rep_distance",
            value=metres,
            unit="m",
        )

    if _REP_MILE.match(token):
        return TagMeaning(
            "rep 1609 m",
            "rep_distance",
            value=1609.34,
            unit="m",
        )

    return None


def meaning_label(tag: object) -> str:
    """Human label for the audit: the meaning or ``unmapped``."""
    meaning = lookup_tag(tag)
    return meaning.label if meaning is not None else "unmapped"


# Tag -> equipment name, matched by normalized equipment name. Keep this
# code-level while there is one athlete; a table is justified only when a
# second athlete's tags must be mapped without a release.
EQUIPMENT_TAGS: dict[str, str] = {
    "thule": "Thule",
    "thule half half": "Thule",
}

_GEAR_TAG_HINTS = ("thule", "anhänger", "anhanger", "trailer")


def equipment_names_for(tags: Iterable[object]) -> list[str]:
    """Return the mapped equipment names for a tag collection, sorted."""
    names = {
        EQUIPMENT_TAGS[token]
        for tag in tags
        if (token := normalize_tag(tag)) in EQUIPMENT_TAGS
    }
    return sorted(names)


def place_names_for(tags: Iterable[object]) -> list[str]:
    """Return the canonical place names for a tag collection, sorted."""
    names = {
        PLACE_ALIASES[token]
        for tag in tags
        if (token := normalize_tag(tag)) in PLACE_ALIASES
    }
    return sorted(names)


def unmapped_equipment_tags(tags: Iterable[object]) -> list[str]:
    """Return gear-like tags that do not map to equipment yet."""
    candidates = {
        token
        for tag in tags
        if (token := normalize_tag(tag))
        and token not in EQUIPMENT_TAGS
        and any(hint in token for hint in _GEAR_TAG_HINTS)
    }
    return sorted(candidates)


def meanings_for(tags: Iterable[object]) -> list[TagMeaning]:
    """Return the mapped meanings for a tag collection, stable by label."""
    meanings = [
        meaning
        for tag in tags
        if (meaning := lookup_tag(tag)) is not None
    ]
    return sorted(meanings, key=lambda item: (item.kind, item.label))


def workout_meanings(tags: Iterable[object]) -> list[TagMeaning]:
    """Return only the workout meanings from a tag collection."""
    return [
        meaning
        for meaning in meanings_for(tags)
        if meaning.kind == "workout"
    ]


def tags_with_kind(tags: Iterable[object], kind: str) -> list[TagMeaning]:
    """Return the mapped tags of one kind, e.g. ``illness`` or ``trail``."""
    return [
        meaning
        for meaning in meanings_for(tags)
        if meaning.kind == kind
    ]
