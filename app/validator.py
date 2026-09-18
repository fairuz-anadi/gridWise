"""Replay checker: verifies all Problem Statement §09 and §11 rules against a finished plan.

Runs on every response before it leaves the server, and doubles as the test oracle.
"""
import math

from app.optimizer import _apply_directives
from app.schemas import Directive, Plan, Scenario

TOL = 0.01  # spec §11.5: 0.01 kWh / 0.01 BDT


def replay_check(scenario: Scenario, directives: list[Directive], plan: Plan) -> list[str]:
    """Return a list of violation messages; [] means the plan is valid."""
    errors: list[str] = []
    b = scenario.battery
    lim = _apply_directives(scenario, directives)
    rows = plan.hourly_plan

    if [p.hour for p in rows] != list(range(24)):
        return ["hourly_plan must contain hours 0-23 exactly once, in order"]

    energy = b.initial_energy_kwh
    for p, inp in zip(rows, scenario.hours):
        h = p.hour
        values = (p.grid_kwh, p.solar_used_kwh, p.battery_kwh, p.battery_energy_after_kwh)
        if any(not math.isfinite(v) or v < 0 for v in values):
            errors.append(f"h{h}: values must be finite and non-negative")
            continue

        charge = p.battery_kwh if p.battery_action == "charge" else 0.0
        discharge = p.battery_kwh if p.battery_action == "discharge" else 0.0
        if p.battery_action == "idle" and p.battery_kwh > TOL:
            errors.append(f"h{h}: idle but battery_kwh = {p.battery_kwh}")

        # battery transition, bounds, rate limits (incl. reserve / no-charge / no-discharge directives)
        if abs(energy + charge - discharge - p.battery_energy_after_kwh) > TOL:
            errors.append(f"h{h}: battery transition {energy} -> {p.battery_energy_after_kwh} "
                          f"does not match {p.battery_action} {p.battery_kwh}")
        energy = p.battery_energy_after_kwh
        if energy < lim["min_energy"][h] - TOL:
            errors.append(f"h{h}: battery {energy} below minimum {lim['min_energy'][h]}")
        if energy > b.capacity_kwh + TOL:
            errors.append(f"h{h}: battery {energy} above capacity {b.capacity_kwh}")
        if charge > lim["max_charge"][h] + TOL:
            errors.append(f"h{h}: charge {charge} exceeds limit {lim['max_charge'][h]}")
        if discharge > lim["max_discharge"][h] + TOL:
            errors.append(f"h{h}: discharge {discharge} exceeds limit {lim['max_discharge'][h]}")

        # effective solar, grid cap, energy balance
        if p.solar_used_kwh > lim["solar"][h] + TOL:
            errors.append(f"h{h}: solar_used {p.solar_used_kwh} exceeds effective solar {lim['solar'][h]}")
        if p.grid_kwh > lim["max_grid"][h] + TOL:
            errors.append(f"h{h}: grid {p.grid_kwh} exceeds cap {lim['max_grid'][h]}")
        supply = p.grid_kwh + p.solar_used_kwh + discharge
        if abs(supply - (inp.demand_kwh + charge)) > TOL:
            errors.append(f"h{h}: energy balance off by {supply - inp.demand_kwh - charge:.4f}")

    if abs(rows[-1].battery_energy_after_kwh - b.initial_energy_kwh) > TOL:
        errors.append(f"end-of-day battery {rows[-1].battery_energy_after_kwh} != initial {b.initial_energy_kwh}")

    # reported totals must match the plan
    grids = [p.grid_kwh for p in rows]
    cost = sum(g * i.tariff_bdt_per_kwh for g, i in zip(grids, scenario.hours))
    if abs(sum(grids) - plan.total_grid_kwh) > TOL:
        errors.append(f"total_grid_kwh {plan.total_grid_kwh} != recalculated {sum(grids):.4f}")
    if abs(cost - plan.total_cost_bdt) > TOL:
        errors.append(f"total_cost_bdt {plan.total_cost_bdt} != recalculated {cost:.4f}")
    if abs(max(grids) - plan.peak_grid_kwh) > TOL:
        errors.append(f"peak_grid_kwh {plan.peak_grid_kwh} != recalculated {max(grids):.4f}")

    return errors
