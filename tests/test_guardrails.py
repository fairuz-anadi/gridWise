"""Deterministic guardrail layer (app/directives.py) against every shape the model could return.

The interpreter is faked, so these run offline. They encode Problem Statement §08: allowed types,
note mapping, hours normalization, numeric bounds, applies semantics and safe failure.
"""
import math

import pytest

import app.directives as directives
from app.directives import UNAVAILABLE_EXPLANATION, interpret_and_validate, validate_raw
from app.schemas import Battery, DirectiveType

BATTERY = Battery(capacity_kwh=200, initial_energy_kwh=100, minimum_energy_kwh=40,
                  max_charge_kwh_per_hour=50, max_discharge_kwh_per_hour=50)
NOTES = ["note zero", "note one", "note two"]


def entry(i, dtype, windows=None, kind="none", value=0, **extra):
    d = {"note_index": i, "directive_type": dtype, "windows": windows or [], "value_kind": kind, "value": value,
         "explanation": "x"}
    d.update(extra)
    return d


def fake_llm(raw):
    async def _call(notes, battery):
        return raw
    return _call


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    monkeypatch.setenv("LLM_CACHE", "0")
    directives.clear_cache()


# ---------- window expansion ----------

@pytest.mark.parametrize("windows, hours", [
    ([{"start_hour": 13, "end_hour_exclusive": 15}], [13, 14]),
    ([{"start_hour": 18, "end_hour_exclusive": 21}], [18, 19, 20]),
    ([{"start_hour": 0, "end_hour_exclusive": 24}], list(range(24))),
    ([{"start_hour": 22, "end_hour_exclusive": 2}], [0, 1, 22, 23]),          # crosses midnight
    ([{"start_hour": 14, "end_hour_exclusive": 14}], [14]),                    # single hour
    ([{"start_hour": 18, "end_hour_exclusive": 19}, {"start_hour": 21, "end_hour_exclusive": 22}], [18, 21]),
    ([{"start_hour": 10, "end_hour_exclusive": 12}, {"start_hour": 11, "end_hour_exclusive": 13}], [10, 11, 12]),  # overlap dedup
])
def test_windows_expand_to_ascending_unique_hours(windows, hours):
    out = validate_raw([entry(0, "no_charge_window", windows)], ["n"], BATTERY)
    assert out[0].structured_adjustment == {"hours": hours}


@pytest.mark.parametrize("windows", [
    [{"start_hour": 24, "end_hour_exclusive": 25}],
    [{"start_hour": -1, "end_hour_exclusive": 3}],
    [{"start_hour": "noon", "end_hour_exclusive": 14}],
    [],
    "13-15",
])
def test_invalid_windows_degrade_to_no_op(windows):
    out = validate_raw([entry(0, "no_charge_window", windows)], ["n"], BATTERY)
    assert out[0].directive_type == DirectiveType.no_op and out[0].applies is False and out[0].structured_adjustment is None


# ---------- values ----------

def test_solar_fraction_and_percent_forms():
    w = [{"start_hour": 12, "end_hour_exclusive": 14}]
    a = validate_raw([entry(0, "solar_reduction", w, "usable_solar_fraction", 0.25)], ["n"], BATTERY)[0]
    b = validate_raw([entry(0, "solar_reduction", w, "usable_solar_fraction", 25)], ["n"], BATTERY)[0]  # model slipped a percent
    assert a.structured_adjustment == {"hours": [12, 13], "factor": 0.25} == b.structured_adjustment


def test_reserve_percent_of_capacity_uses_request_capacity():
    w = [{"start_hour": 18, "end_hour_exclusive": 21}]
    d = validate_raw([entry(0, "minimum_battery_reserve", w, "reserve_percent_of_capacity", 50)], ["n"], BATTERY)[0]
    assert d.structured_adjustment == {"hours": [18, 19, 20], "minimum_energy_kwh": 100.0}


def test_reserve_kwh_clamped_to_capacity_and_zero():
    w = [{"start_hour": 1, "end_hour_exclusive": 2}]
    hi = validate_raw([entry(0, "minimum_battery_reserve", w, "reserve_kwh", 999)], ["n"], BATTERY)[0]
    lo = validate_raw([entry(0, "minimum_battery_reserve", w, "reserve_kwh", -5)], ["n"], BATTERY)[0]
    assert hi.structured_adjustment["minimum_energy_kwh"] == 200 and lo.structured_adjustment["minimum_energy_kwh"] == 0


def test_factor_clamped_into_unit_interval():
    w = [{"start_hour": 1, "end_hour_exclusive": 2}]
    d = validate_raw([entry(0, "solar_reduction", w, "usable_solar_fraction", 170)], ["n"], BATTERY)[0]
    assert d.structured_adjustment["factor"] == 1.0
    d = validate_raw([entry(0, "solar_reduction", w, "usable_solar_fraction", -0.3)], ["n"], BATTERY)[0]
    assert d.structured_adjustment["factor"] == 0.0


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, "lots", None])
def test_non_finite_values_become_no_op(bad):
    w = [{"start_hour": 1, "end_hour_exclusive": 2}]
    for dtype, kind in (("solar_reduction", "usable_solar_fraction"), ("minimum_battery_reserve", "reserve_kwh"), ("max_grid_window", "max_grid_kwh")):
        d = validate_raw([entry(0, dtype, w, kind, bad)], ["n"], BATTERY)[0]
        assert d.directive_type == DirectiveType.no_op and d.structured_adjustment is None


def test_max_grid_shape_and_non_negative():
    w = [{"start_hour": 18, "end_hour_exclusive": 21}]
    d = validate_raw([entry(0, "max_grid_window", w, "max_grid_kwh", 155)], ["n"], BATTERY)[0]
    assert d.applies is True and d.structured_adjustment == {"hours": [18, 19, 20], "max_grid_kwh": 155.0}
    neg = validate_raw([entry(0, "max_grid_window", w, "max_grid_kwh", -10)], ["n"], BATTERY)[0]
    assert neg.structured_adjustment["max_grid_kwh"] == 0.0


# ---------- types / applies semantics ----------

def test_unknown_type_is_no_op_never_invented():
    d = validate_raw([entry(0, "grid_export_window", [{"start_hour": 1, "end_hour_exclusive": 2}])], ["n"], BATTERY)[0]
    assert d.directive_type == DirectiveType.no_op and d.applies is False


def test_no_op_always_has_applies_false_and_null_adjustment():
    d = validate_raw([entry(0, "no_op", [{"start_hour": 1, "end_hour_exclusive": 5}], "reserve_kwh", 50)], ["n"], BATTERY)[0]
    assert d.applies is False and d.structured_adjustment is None


def test_every_non_no_op_has_applies_true():
    w = [{"start_hour": 1, "end_hour_exclusive": 2}]
    raws = [entry(0, "solar_reduction", w, "usable_solar_fraction", 0.5), entry(1, "no_charge_window", w),
            entry(2, "max_grid_window", w, "max_grid_kwh", 100)]
    assert all(d.applies for d in validate_raw(raws, NOTES, BATTERY))


# ---------- note mapping ----------

def test_one_entry_per_note_in_order_even_when_model_returns_fewer():
    out = validate_raw([entry(2, "no_charge_window", [{"start_hour": 1, "end_hour_exclusive": 2}])], NOTES, BATTERY)
    assert [d.note_index for d in out] == [0, 1, 2]
    assert out[0].directive_type == DirectiveType.no_op and out[2].directive_type == DirectiveType.no_charge_window


def test_out_of_range_and_duplicate_indices_ignored():
    w = [{"start_hour": 1, "end_hour_exclusive": 2}]
    out = validate_raw([entry(7, "no_charge_window", w), entry(1, "no_charge_window", w), entry(1, "no_discharge_window", w)], NOTES, BATTERY)
    assert out[1].directive_type == DirectiveType.no_charge_window  # first wins
    assert out[0].directive_type == DirectiveType.no_op


def test_positional_fallback_when_indices_missing():
    w = [{"start_hour": 1, "end_hour_exclusive": 2}]
    raws = [entry(0, "no_charge_window", w), entry(0, "no_discharge_window", w), entry(0, "no_op")]
    for r in raws:
        r.pop("note_index")
    out = validate_raw(raws, NOTES, BATTERY)
    assert [d.directive_type for d in out] == [DirectiveType.no_charge_window, DirectiveType.no_discharge_window, DirectiveType.no_op]


def test_string_note_index_accepted():
    out = validate_raw([entry("1", "no_charge_window", [{"start_hour": 1, "end_hour_exclusive": 2}])], NOTES, BATTERY)
    assert out[1].directive_type == DirectiveType.no_charge_window


def test_legacy_structured_adjustment_shape_still_accepted():
    raw = [{"note_index": 0, "applies": True, "directive_type": "solar_reduction",
            "structured_adjustment": {"hours": [14, 13, 13], "factor": 0.2}, "explanation": "legacy"}]
    d = validate_raw(raw, ["n"], BATTERY)[0]
    assert d.structured_adjustment == {"hours": [13, 14], "factor": 0.2}


# ---------- safe failure & cache (async path) ----------

@pytest.mark.asyncio
async def test_provider_outage_degrades_every_note_with_interpreter_marker(monkeypatch):
    monkeypatch.setattr(directives, "call_llm_interpreter", fake_llm([]))
    out = await interpret_and_validate(NOTES, BATTERY)
    assert [d.note_index for d in out] == [0, 1, 2]
    assert all(d.directive_type == DirectiveType.no_op and not d.applies for d in out)
    assert all("interpreter" in d.explanation.lower() for d in out)


@pytest.mark.asyncio
async def test_interpreter_exception_never_propagates(monkeypatch):
    async def boom(notes, battery):
        raise RuntimeError("provider exploded")
    monkeypatch.setattr(directives, "call_llm_interpreter", boom)
    out = await interpret_and_validate(NOTES, BATTERY)
    assert len(out) == 3 and all(d.explanation == UNAVAILABLE_EXPLANATION for d in out)


@pytest.mark.asyncio
async def test_cache_serves_repeats_without_calling_the_model(monkeypatch):
    monkeypatch.setenv("LLM_CACHE", "1")
    calls = {"n": 0}

    async def counting(notes, battery):
        calls["n"] += 1
        return [entry(0, "no_charge_window", [{"start_hour": 1, "end_hour_exclusive": 2}])]
    monkeypatch.setattr(directives, "call_llm_interpreter", counting)
    a = await interpret_and_validate(["Do not charge 1-2 AM"], BATTERY)
    b = await interpret_and_validate(["Do not charge 1-2 AM"], BATTERY)
    assert calls["n"] == 1 and a == b
    # a different capacity is a different scenario (percent-of-capacity reserves depend on it)
    await interpret_and_validate(["Do not charge 1-2 AM"], BATTERY.model_copy(update={"capacity_kwh": 300}))
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_outage_is_not_cached(monkeypatch):
    monkeypatch.setenv("LLM_CACHE", "1")
    seq = [[], [entry(0, "no_charge_window", [{"start_hour": 1, "end_hour_exclusive": 2}])]]

    async def flaky(notes, battery):
        return seq.pop(0)
    monkeypatch.setattr(directives, "call_llm_interpreter", flaky)
    first = await interpret_and_validate(["x"], BATTERY)
    second = await interpret_and_validate(["x"], BATTERY)
    assert first[0].directive_type == DirectiveType.no_op and second[0].directive_type == DirectiveType.no_charge_window
