"""Replay checker: verifies all Problem Statement §09 and §11 rules against a finished plan.

Owner: Anadi.
"""
from app.schemas import Directive, DirectiveType, Plan, Scenario

TOLERANCE = 0.01


def replay_check(scenario: Scenario, directives: list[Directive], plan: Plan) -> list[str]:
    """Return a list of violation messages; an empty list [] means the plan is valid."""
    violations: list[str] = []
    battery = scenario.battery
    hours = scenario.hours
    hourly_plan = plan.hourly_plan

    # 1. Horizon & shape checks
    if len(hourly_plan) != 24:
        violations.append(f"hourly_plan must contain exactly 24 entries, found {len(hourly_plan)}")
        return violations

    for h, p in enumerate(hourly_plan):
        if p.hour != h:
            violations.append(f"Hour mismatch: expected hour {h}, found {p.hour}")

    # 2. Extract effective solar and directive constraints
    effective_solar = [h.solar_kwh for h in hours]
    min_reserves = [battery.minimum_energy_kwh for _ in range(24)]
    no_charge_hours: set[int] = set()
    no_discharge_hours: set[int] = set()
    grid_caps: dict[int, float] = {}

    for d in directives:
        if not d.applies or not d.structured_adjustment:
            continue
        dtype = d.directive_type
        adj = d.structured_adjustment
        h_list = adj.get("hours", [])

        if dtype == DirectiveType.solar_reduction:
            factor = float(adj.get("factor", 1.0))
            for h in h_list:
                if 0 <= h < 24:
                    effective_solar[h] = effective_solar[h] * factor
        elif dtype == DirectiveType.minimum_battery_reserve:
            reserve = float(adj.get("minimum_energy_kwh", battery.minimum_energy_kwh))
            for h in h_list:
                if 0 <= h < 24:
                    min_reserves[h] = max(min_reserves[h], reserve)
        elif dtype == DirectiveType.no_charge_window:
            no_charge_hours.update(h for h in h_list if 0 <= h < 24)
        elif dtype == DirectiveType.no_discharge_window:
            no_discharge_hours.update(h for h in h_list if 0 <= h < 24)
        elif dtype == DirectiveType.max_grid_window:
            cap = float(adj.get("max_grid_kwh", float("inf")))
            for h in h_list:
                if 0 <= h < 24:
                    grid_caps[h] = min(grid_caps.get(h, float("inf")), cap)

    # 3. Hour-by-hour simulation & validation
    prev_energy = battery.initial_energy_kwh

    for h in range(24):
        p = hourly_plan[h]
        inp_hour = hours[h]

        # Non-negative checks
        if p.grid_kwh < -TOLERANCE:
            violations.append(f"Hour {h}: grid_kwh is negative ({p.grid_kwh})")
        if p.solar_used_kwh < -TOLERANCE:
            violations.append(f"Hour {h}: solar_used_kwh is negative ({p.solar_used_kwh})")
        if p.battery_kwh < -TOLERANCE:
            violations.append(f"Hour {h}: battery_kwh is negative ({p.battery_kwh})")

        # Solar bound
        if p.solar_used_kwh > effective_solar[h] + TOLERANCE:
            violations.append(
                f"Hour {h}: solar_used_kwh ({p.solar_used_kwh}) exceeds effective solar ({effective_solar[h]:.2f})"
            )

        # Directives checks
        if h in no_charge_hours and p.battery_action == "charge" and p.battery_kwh > TOLERANCE:
            violations.append(f"Hour {h}: charging violates no_charge_window directive")

        if h in no_discharge_hours and p.battery_action == "discharge" and p.battery_kwh > TOLERANCE:
            violations.append(f"Hour {h}: discharging violates no_discharge_window directive")

        if h in grid_caps and p.grid_kwh > grid_caps[h] + TOLERANCE:
            violations.append(
                f"Hour {h}: grid_kwh ({p.grid_kwh}) exceeds max_grid_window limit ({grid_caps[h]})"
            )

        # Battery reserve and capacity bounds
        active_min = min_reserves[h]
        if p.battery_energy_after_kwh < active_min - TOLERANCE:
            violations.append(
                f"Hour {h}: battery energy after ({p.battery_energy_after_kwh}) below reserve minimum ({active_min})"
            )
        if p.battery_energy_after_kwh > battery.capacity_kwh + TOLERANCE:
            violations.append(
                f"Hour {h}: battery energy after ({p.battery_energy_after_kwh}) exceeds capacity ({battery.capacity_kwh})"
            )

        # Battery rate limits
        if p.battery_action == "charge":
            if p.battery_kwh > battery.max_charge_kwh_per_hour + TOLERANCE:
                violations.append(
                    f"Hour {h}: charge amount ({p.battery_kwh}) exceeds max_charge_kwh_per_hour ({battery.max_charge_kwh_per_hour})"
                )
            expected_energy = prev_energy + p.battery_kwh
            charge_in = p.battery_kwh
            discharge_out = 0.0
        elif p.battery_action == "discharge":
            if p.battery_kwh > battery.max_discharge_kwh_per_hour + TOLERANCE:
                violations.append(
                    f"Hour {h}: discharge amount ({p.battery_kwh}) exceeds max_discharge_kwh_per_hour ({battery.max_discharge_kwh_per_hour})"
                )
            expected_energy = prev_energy - p.battery_kwh
            charge_in = 0.0
            discharge_out = p.battery_kwh
        elif p.battery_action == "idle":
            if abs(p.battery_kwh) > TOLERANCE:
                violations.append(f"Hour {h}: idle battery action must have battery_kwh=0, got {p.battery_kwh}")
            expected_energy = prev_energy
            charge_in = 0.0
            discharge_out = 0.0
        else:
            violations.append(f"Hour {h}: invalid battery_action '{p.battery_action}'")
            expected_energy = prev_energy
            charge_in = 0.0
            discharge_out = 0.0

        # Battery state transition check
        if abs(p.battery_energy_after_kwh - expected_energy) > TOLERANCE:
            violations.append(
                f"Hour {h}: battery transition mismatch (expected {expected_energy:.2f}, got {p.battery_energy_after_kwh:.2f})"
            )

        # Energy balance check:
        # grid_kwh + solar_used_kwh + battery_discharge_kwh = demand_kwh + battery_charge_kwh
        lhs = p.grid_kwh + p.solar_used_kwh + discharge_out
        rhs = inp_hour.demand_kwh + charge_in
        if abs(lhs - rhs) > TOLERANCE:
            violations.append(
                f"Hour {h}: energy balance violated (lhs={lhs:.2f} != rhs={rhs:.2f})"
            )

        prev_energy = p.battery_energy_after_kwh

    # 4. End-of-day battery neutrality
    if abs(hourly_plan[23].battery_energy_after_kwh - battery.initial_energy_kwh) > TOLERANCE:
        violations.append(
            f"End-of-day battery neutrality violated: started at {battery.initial_energy_kwh}, ended at {hourly_plan[23].battery_energy_after_kwh}"
        )

    # 5. Consistency of totals
    recalc_grid = sum(p.grid_kwh for p in hourly_plan)
    recalc_cost = sum(p.grid_kwh * hours[h].tariff_bdt_per_kwh for h, p in enumerate(hourly_plan))
    recalc_peak = max(p.grid_kwh for p in hourly_plan)

    if abs(plan.total_grid_kwh - recalc_grid) > TOLERANCE:
        violations.append(
            f"total_grid_kwh mismatch: reported {plan.total_grid_kwh}, recalculated {recalc_grid:.2f}"
        )
    if abs(plan.total_cost_bdt - recalc_cost) > TOLERANCE:
        violations.append(
            f"total_cost_bdt mismatch: reported {plan.total_cost_bdt}, recalculated {recalc_cost:.2f}"
        )
    if abs(plan.peak_grid_kwh - recalc_peak) > TOLERANCE:
        violations.append(
            f"peak_grid_kwh mismatch: reported {plan.peak_grid_kwh}, recalculated {recalc_peak:.2f}"
        )

    return violations
