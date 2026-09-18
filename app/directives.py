"""LLM output -> validated directives (the deterministic guardrail layer). Owner: Turjo.

Guarantees (Problem Statement §08):
- Exactly one Directive per operator note, in note_index order 0..N-1.
- directive_type is one of the six supported values; anything else becomes no_op.
- no_op: applies = False, structured_adjustment = None. Every other type: applies = True with the
  exact structured_adjustment shape for that type.
- hours: unique integers 0..23 in ascending order, expanded from the model's [start, end) windows.
- factor in [0, 1]; reserve finite, >= 0, <= capacity; max_grid finite, >= 0. Non-finite -> no_op.
- Never raises. A provider outage degrades every note to no_op with an explanation that names the
  interpreter, so callers (and the console) can tell an outage from a genuine distractor.

Accepts two raw shapes from the model: the window/value form produced by app/llm/interpreter.py and
the older literal `structured_adjustment` form, so a prompt change never breaks the pipeline.
"""
import json
import logging
import math
import os
from collections import OrderedDict
from typing import Any

from app.llm import call_llm_interpreter
from app.schemas import Battery, Directive, DirectiveType

logger = logging.getLogger("gridwise.directives")

UNAVAILABLE_EXPLANATION = "Interpreter unavailable; this note was treated as having no effect on today's schedule."
NO_EFFECT_EXPLANATION = "This note does not affect today's energy schedule."

_CACHE_MAX = 512
_cache: "OrderedDict[str, list[Directive]]" = OrderedDict()


def _cache_key(notes: list[str], battery: Battery) -> str:
    return json.dumps([[n.strip() for n in notes], battery.capacity_kwh], ensure_ascii=False)


def _cache_get(key: str) -> list[Directive] | None:
    if os.getenv("LLM_CACHE", "1") == "0":
        return None
    hit = _cache.get(key)
    if hit is not None:
        _cache.move_to_end(key)
        return [d.model_copy() for d in hit]
    return None


def _cache_put(key: str, value: list[Directive]) -> None:
    if os.getenv("LLM_CACHE", "1") == "0":
        return
    _cache[key] = [d.model_copy() for d in value]
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


def clear_cache() -> None:
    _cache.clear()


# ---------- primitives ----------

def _finite(x: Any) -> float | None:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _as_int(x: Any) -> int | None:
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, str) and x.strip().lstrip("-").isdigit():
        return int(x.strip())
    return None


def _hours_from_windows(windows: Any) -> list[int] | None:
    """Expand [start, end) windows into unique ascending hours. Handles windows that cross midnight."""
    if not isinstance(windows, list) or not windows:
        return None
    hours: set[int] = set()
    for w in windows:
        if not isinstance(w, dict):
            return None
        start, end = _as_int(w.get("start_hour")), _as_int(w.get("end_hour_exclusive"))
        if start is None or end is None or not (0 <= start <= 23) or not (0 <= end <= 24):
            return None
        if end == start:  # a single hour phrased as "at 3 PM"
            hours.add(start)
            continue
        if end > start:
            hours.update(range(start, end))
        else:  # crosses midnight, e.g. 22 -> 2 means 22, 23, 0, 1
            hours.update(range(start, 24))
            hours.update(range(0, end))
    return sorted(hours) if hours else None


def _hours_from_list(raw: Any) -> list[int] | None:
    if not isinstance(raw, list) or not raw:
        return None
    out: set[int] = set()
    for h in raw:
        v = _as_int(h)
        if v is None or not (0 <= v <= 23):
            return None
        out.add(v)
    return sorted(out) if out else None


def _no_op(idx: int, explanation: str) -> Directive:
    return Directive(note_index=idx, applies=False, directive_type=DirectiveType.no_op, structured_adjustment=None, explanation=explanation)


# ---------- one note ----------

def _validate_and_sanitize_directive(idx: int, raw: dict[str, Any] | None, battery: Battery) -> Directive:
    """Turn one raw model entry into a spec-exact Directive, or a no_op if anything is off."""
    if not isinstance(raw, dict):
        return _no_op(idx, UNAVAILABLE_EXPLANATION)

    try:
        dtype = DirectiveType(raw.get("directive_type"))
    except (ValueError, TypeError):
        logger.warning("note %d: unsupported directive_type %r -> no_op", idx, raw.get("directive_type"))
        return _no_op(idx, NO_EFFECT_EXPLANATION)

    explanation = raw.get("explanation")
    explanation = explanation.strip() if isinstance(explanation, str) and explanation.strip() else ""

    if dtype == DirectiveType.no_op:
        return _no_op(idx, explanation or NO_EFFECT_EXPLANATION)

    # hours: literal list (old shape) or windows (new shape)
    adj = raw.get("structured_adjustment")
    legacy = isinstance(adj, dict)
    hours = _hours_from_list(adj.get("hours")) if legacy else _hours_from_windows(raw.get("windows"))
    if not hours:
        logger.warning("note %d: %s without valid hours -> no_op", idx, dtype.value)
        return _no_op(idx, NO_EFFECT_EXPLANATION)

    kind = raw.get("value_kind") if not legacy else None
    value = _finite((adj or {}).get(_LEGACY_FIELD.get(dtype)) if legacy else raw.get("value"))
    explanation = explanation or f"{dtype.value.replace('_', ' ').capitalize()} for the stated hours."

    if dtype == DirectiveType.solar_reduction:
        if value is None:
            return _no_op(idx, NO_EFFECT_EXPLANATION)
        factor = value / 100.0 if (kind == "usable_solar_fraction" or legacy) and value > 1.0 and value <= 100.0 else value
        factor = min(1.0, max(0.0, factor))
        return Directive(note_index=idx, applies=True, directive_type=dtype, structured_adjustment={"hours": hours, "factor": round(factor, 6)}, explanation=explanation)

    if dtype == DirectiveType.minimum_battery_reserve:
        if value is None:
            return _no_op(idx, NO_EFFECT_EXPLANATION)
        kwh = value * battery.capacity_kwh / 100.0 if kind == "reserve_percent_of_capacity" else value
        kwh = min(battery.capacity_kwh, max(0.0, kwh))
        return Directive(note_index=idx, applies=True, directive_type=dtype, structured_adjustment={"hours": hours, "minimum_energy_kwh": round(kwh, 4)}, explanation=explanation)

    if dtype in (DirectiveType.no_charge_window, DirectiveType.no_discharge_window):
        return Directive(note_index=idx, applies=True, directive_type=dtype, structured_adjustment={"hours": hours}, explanation=explanation)

    if dtype == DirectiveType.max_grid_window:
        if value is None:
            return _no_op(idx, NO_EFFECT_EXPLANATION)
        return Directive(note_index=idx, applies=True, directive_type=dtype, structured_adjustment={"hours": hours, "max_grid_kwh": round(max(0.0, value), 4)}, explanation=explanation)

    return _no_op(idx, NO_EFFECT_EXPLANATION)


_LEGACY_FIELD = {
    DirectiveType.solar_reduction: "factor",
    DirectiveType.minimum_battery_reserve: "minimum_energy_kwh",
    DirectiveType.max_grid_window: "max_grid_kwh",
}


# ---------- all notes ----------

def validate_raw(raw_interpretations: list[Any], notes: list[str], battery: Battery) -> list[Directive]:
    """Map raw model entries onto notes (by note_index, else positionally) and validate each one."""
    by_index: dict[int, dict[str, Any]] = {}
    for item in raw_interpretations:
        if isinstance(item, dict):
            idx = _as_int(item.get("note_index"))
            if idx is not None and 0 <= idx < len(notes) and idx not in by_index:
                by_index[idx] = item
    if not by_index and len(raw_interpretations) == len(notes):
        by_index = {i: item for i, item in enumerate(raw_interpretations) if isinstance(item, dict)}
    return [_validate_and_sanitize_directive(i, by_index.get(i), battery) for i in range(len(notes))]


async def interpret_and_validate(notes: list[str], battery: Battery) -> list[Directive]:
    """One Directive per note, in note_index order. Never raises; a note that fails becomes no_op."""
    key = _cache_key(notes, battery)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    try:
        raw = await call_llm_interpreter(notes, battery)
    except Exception as e:  # the interpreter already catches provider errors; this is belt and braces
        logger.error("interpreter raised %s; degrading to no_op", type(e).__name__)
        raw = []

    if not raw:
        return [_no_op(i, UNAVAILABLE_EXPLANATION) for i in range(len(notes))]

    validated = validate_raw(raw, notes, battery)
    if len(raw) == len(notes):  # never cache a partially-degraded answer
        _cache_put(key, validated)
    return validated
