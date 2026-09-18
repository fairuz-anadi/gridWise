"""LLM output -> validated directives (the deterministic guardrail layer).

Owner: Turjo.
Guarantees:
- Returns exactly one Directive per operator note, in note_index order (0..N-1).
- Every non-no_op directive has applies = True and a valid structured_adjustment.
- no_op directives have applies = False and structured_adjustment = None.
- Hours are unique integers in [0..23] sorted in ascending order.
- Numeric bounds (factor in [0, 1], reserve in [0, capacity], max_grid >= 0) are strictly checked.
- Never raises: any malformed or unexpected note interpretation safely defaults to no_op.
"""
import logging
from typing import Any

from app.llm import call_llm_interpreter
from app.schemas import Battery, Directive, DirectiveType

logger = logging.getLogger("gridwise.directives")

VALID_DIRECTIVE_TYPES = {
    DirectiveType.solar_reduction,
    DirectiveType.minimum_battery_reserve,
    DirectiveType.no_charge_window,
    DirectiveType.no_discharge_window,
    DirectiveType.max_grid_window,
    DirectiveType.no_op,
}


def _validate_hours(raw_hours: Any) -> list[int] | None:
    """Validate and normalize hours: unique integers 0..23 in ascending order."""
    if not isinstance(raw_hours, list) or not raw_hours:
        return None
    cleaned = set()
    for h in raw_hours:
        try:
            h_int = int(h)
            if 0 <= h_int <= 23:
                cleaned.add(h_int)
            else:
                return None
        except (ValueError, TypeError):
            return None
    if not cleaned:
        return None
    return sorted(list(cleaned))


def _validate_and_sanitize_directive(
    idx: int,
    raw: dict[str, Any] | None,
    battery: Battery
) -> Directive:
    """Validate and sanitize a single directive interpretation entry."""
    default_no_op = Directive(
        note_index=idx,
        applies=False,
        directive_type=DirectiveType.no_op,
        structured_adjustment=None,
        explanation="Note does not affect today's energy schedule.",
    )

    if not isinstance(raw, dict):
        return default_no_op

    raw_type = raw.get("directive_type")
    try:
        dtype = DirectiveType(raw_type)
    except (ValueError, TypeError):
        logger.warning("Unknown directive_type '%s' at note %d; defaulting to no_op", raw_type, idx)
        return default_no_op

    explanation = raw.get("explanation") or "Interpreted directive"
    if not isinstance(explanation, str):
        explanation = str(explanation)

    if dtype == DirectiveType.no_op:
        return Directive(
            note_index=idx,
            applies=False,
            directive_type=DirectiveType.no_op,
            structured_adjustment=None,
            explanation=explanation,
        )

    adj = raw.get("structured_adjustment")
    if not isinstance(adj, dict):
        logger.warning("Directive %s missing structured_adjustment dict at note %d", dtype, idx)
        return default_no_op

    hours = _validate_hours(adj.get("hours"))
    if not hours:
        logger.warning("Invalid or empty hours for %s at note %d", dtype, idx)
        return default_no_op

    if dtype == DirectiveType.solar_reduction:
        factor_raw = adj.get("factor")
        try:
            factor = float(factor_raw)
            if factor < 0.0 or factor > 1.0:
                factor = max(0.0, min(1.0, factor))
            return Directive(
                note_index=idx,
                applies=True,
                directive_type=dtype,
                structured_adjustment={"hours": hours, "factor": factor},
                explanation=explanation,
            )
        except (ValueError, TypeError):
            logger.warning("Invalid solar factor %s at note %d", factor_raw, idx)
            return default_no_op

    elif dtype == DirectiveType.minimum_battery_reserve:
        reserve_raw = adj.get("minimum_energy_kwh")
        try:
            reserve = float(reserve_raw)
            if reserve < 0.0:
                reserve = 0.0
            if reserve > battery.capacity_kwh:
                reserve = battery.capacity_kwh
            return Directive(
                note_index=idx,
                applies=True,
                directive_type=dtype,
                structured_adjustment={"hours": hours, "minimum_energy_kwh": reserve},
                explanation=explanation,
            )
        except (ValueError, TypeError):
            logger.warning("Invalid minimum_energy_kwh %s at note %d", reserve_raw, idx)
            return default_no_op

    elif dtype in (DirectiveType.no_charge_window, DirectiveType.no_discharge_window):
        return Directive(
            note_index=idx,
            applies=True,
            directive_type=dtype,
            structured_adjustment={"hours": hours},
            explanation=explanation,
        )

    elif dtype == DirectiveType.max_grid_window:
        max_grid_raw = adj.get("max_grid_kwh")
        try:
            max_grid = float(max_grid_raw)
            if max_grid < 0.0:
                max_grid = 0.0
            return Directive(
                note_index=idx,
                applies=True,
                directive_type=dtype,
                structured_adjustment={"hours": hours, "max_grid_kwh": max_grid},
                explanation=explanation,
            )
        except (ValueError, TypeError):
            logger.warning("Invalid max_grid_kwh %s at note %d", max_grid_raw, idx)
            return default_no_op

    return default_no_op


async def interpret_and_validate(notes: list[str], battery: Battery) -> list[Directive]:
    """One Directive per note, in note_index order. Never raises; a note that fails becomes no_op."""
    try:
        raw_interpretations = await call_llm_interpreter(notes, battery)
    except Exception as e:
        logger.error("Unexpected error invoking LLM interpreter: %s", e)
        raw_interpretations = []

    # Map raw interpretations by note_index if present
    raw_by_index: dict[int, dict[str, Any]] = {}
    for item in raw_interpretations:
        if isinstance(item, dict):
            idx = item.get("note_index")
            if isinstance(idx, int) and 0 <= idx < len(notes):
                raw_by_index[idx] = item

    # Fallback to positional mapping if indices were missing
    if len(raw_by_index) == 0 and len(raw_interpretations) == len(notes):
        for i, item in enumerate(raw_interpretations):
            if isinstance(item, dict):
                raw_by_index[i] = item

    # Build validated directives in strict note_index order 0..N-1
    validated: list[Directive] = []
    for i in range(len(notes)):
        raw_item = raw_by_index.get(i)
        directive = _validate_and_sanitize_directive(i, raw_item, battery)
        validated.append(directive)

    return validated
