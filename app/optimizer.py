"""LP scheduler for GridWise smart campus energy optimization.

Uses scipy.optimize.linprog with the HiGHS solver to minimize grid electricity costs
subject to 24-hour campus demand, rooftop solar, battery state transitions,
end-of-day battery neutrality, and operator directives.
"""
import numpy as np
from scipy.optimize import linprog

from app.schemas import Directive, DirectiveType, HourPlan, Plan, Scenario


class Infeasible(Exception):
    """No schedule satisfies the scenario plus the given directives."""


def optimize(scenario: Scenario, directives: list[Directive]) -> Plan:
    """Solve the 24-hour campus energy scheduling problem as a Linear Program."""
    battery = scenario.battery
    hours = scenario.hours

    # 1. Deterministic directive effects
    effective_solar = [h.solar_kwh for h in hours]
    min_battery_reserve = [battery.minimum_energy_kwh for _ in range(24)]
    max_charge = [battery.max_charge_kwh_per_hour for _ in range(24)]
    max_discharge = [battery.max_discharge_kwh_per_hour for _ in range(24)]
    max_grid = [float("inf") for _ in range(24)]

    for d in directives:
        if not d.applies or not d.structured_adjustment:
            continue
        dtype = d.directive_type
        adj = d.structured_adjustment
        h_list = adj.get("hours", [])

        if dtype == DirectiveType.solar_reduction:
            factor = float(adj["factor"])
            for h in h_list:
                if 0 <= h < 24:
                    effective_solar[h] = effective_solar[h] * factor
        elif dtype == DirectiveType.minimum_battery_reserve:
            reserve = float(adj["minimum_energy_kwh"])
            for h in h_list:
                if 0 <= h < 24:
                    min_battery_reserve[h] = max(min_battery_reserve[h], reserve)
        elif dtype == DirectiveType.no_charge_window:
            for h in h_list:
                if 0 <= h < 24:
                    max_charge[h] = 0.0
        elif dtype == DirectiveType.no_discharge_window:
            for h in h_list:
                if 0 <= h < 24:
                    max_discharge[h] = 0.0
        elif dtype == DirectiveType.max_grid_window:
            cap = float(adj["max_grid_kwh"])
            for h in h_list:
                if 0 <= h < 24:
                    max_grid[h] = min(max_grid[h], cap)

    # 2. Setup Linear Program
    # Decision variables per hour h (5 * 24 = 120 variables):
    # index 5*h + 0: grid_kwh [g_h]
    # index 5*h + 1: solar_used_kwh [s_h]
    # index 5*h + 2: battery_charge_kwh [c_h]
    # index 5*h + 3: battery_discharge_kwh [d_h]
    # index 5*h + 4: battery_energy_after_kwh [e_h]
    num_vars = 24 * 5
    c_obj = np.zeros(num_vars)
    bounds = []

    for h in range(24):
        tariff = hours[h].tariff_bdt_per_kwh
        # g_h: purchase grid electricity
        c_obj[5 * h + 0] = tariff
        bounds.append((0.0, max_grid[h] if max_grid[h] != float("inf") else None))

        # s_h: solar used (free)
        c_obj[5 * h + 1] = 0.0
        bounds.append((0.0, effective_solar[h]))

        # c_h: charge (tiny penalty to prevent simultaneous charge & discharge)
        c_obj[5 * h + 2] = 1e-6
        bounds.append((0.0, max_charge[h]))

        # d_h: discharge (tiny penalty to prevent simultaneous charge & discharge)
        c_obj[5 * h + 3] = 1e-6
        bounds.append((0.0, max_discharge[h]))

        # e_h: energy level in battery
        c_obj[5 * h + 4] = 0.0
        bounds.append((min_battery_reserve[h], battery.capacity_kwh))

    # Equalities:
    # 1) Hourly energy balance (24 eqs): g_h + s_h - c_h + d_h = demand_kwh[h]
    # 2) Battery transitions (24 eqs):
    #    h=0: e_0 - c_0 + d_0 = initial_energy_kwh
    #    h>0: e_h - e_{h-1} - c_h + d_h = 0
    # 3) End of day battery neutrality (1 eq): e_{23} = initial_energy_kwh
    num_eq = 24 + 24 + 1
    A_eq = np.zeros((num_eq, num_vars))
    b_eq = np.zeros(num_eq)

    # 1) Energy balance: g_h + s_h + d_h = demand_kwh[h] + c_h
    for h in range(24):
        row = h
        demand = hours[h].demand_kwh
        A_eq[row, 5 * h + 0] = 1.0   # +g_h
        A_eq[row, 5 * h + 1] = 1.0   # +s_h
        A_eq[row, 5 * h + 2] = -1.0  # -c_h
        A_eq[row, 5 * h + 3] = 1.0   # +d_h
        b_eq[row] = demand

    # 2) Battery dynamics
    # Hour 0
    A_eq[24, 5 * 0 + 4] = 1.0   # +e_0
    A_eq[24, 5 * 0 + 2] = -1.0  # -c_0
    A_eq[24, 5 * 0 + 3] = 1.0   # +d_0
    b_eq[24] = battery.initial_energy_kwh

    # Hours 1..23
    for h in range(1, 24):
        row = 24 + h
        A_eq[row, 5 * h + 4] = 1.0        # +e_h
        A_eq[row, 5 * (h - 1) + 4] = -1.0  # -e_{h-1}
        A_eq[row, 5 * h + 2] = -1.0       # -c_h
        A_eq[row, 5 * h + 3] = 1.0        # +d_h
        b_eq[row] = 0.0

    # 3) Battery neutrality: e_{23} = initial_energy_kwh
    A_eq[48, 5 * 23 + 4] = 1.0
    b_eq[48] = battery.initial_energy_kwh

    # Solve using HiGHS
    result = linprog(c_obj, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not result.success:
        raise Infeasible(f"LP optimization failed: {result.message}")

    # Reconstruct hourly plan
    hourly_plan: list[HourPlan] = []
    for h in range(24):
        g = max(0.0, float(result.x[5 * h + 0]))
        s = max(0.0, float(result.x[5 * h + 1]))
        c = max(0.0, float(result.x[5 * h + 2]))
        d = max(0.0, float(result.x[5 * h + 3]))
        e = max(0.0, float(result.x[5 * h + 4]))

        # Determine battery action
        if c > 1e-4:
            action = "charge"
            bat_kwh = c
        elif d > 1e-4:
            action = "discharge"
            bat_kwh = d
        else:
            action = "idle"
            bat_kwh = 0.0

        hourly_plan.append(
            HourPlan(
                hour=h,
                grid_kwh=round(g, 4),
                solar_used_kwh=round(s, 4),
                battery_action=action,
                battery_kwh=round(bat_kwh, 4),
                battery_energy_after_kwh=round(e, 4),
            )
        )

    # Recalculate totals directly from the generated hourly_plan
    total_grid_kwh = round(sum(p.grid_kwh for p in hourly_plan), 4)
    total_cost_bdt = round(sum(p.grid_kwh * hours[h].tariff_bdt_per_kwh for h, p in enumerate(hourly_plan)), 4)
    peak_grid_kwh = round(max(p.grid_kwh for p in hourly_plan), 4)

    return Plan(
        hourly_plan=hourly_plan,
        total_grid_kwh=total_grid_kwh,
        total_cost_bdt=total_cost_bdt,
        peak_grid_kwh=peak_grid_kwh,
    )
