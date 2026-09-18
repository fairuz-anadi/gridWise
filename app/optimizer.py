"""LP scheduler. Owner: Anadi.

Variables (all >= 0), h = 0..23:  g[h] grid, s[h] solar_used, c[h] charge, d[h] discharge  -> 96 vars
Objective:    minimise sum tariff[h] * g[h]
Balance:      g[h] + s[h] + d[h] - c[h] = demand[h]
Neutrality:   sum c - sum d = 0
State:        min_h - E0 <= sum_{k<=h} (c[k] - d[k]) <= capacity - E0
Bounds:       g <= max_grid[h], s <= solar[h] * factor[h], c <= max_charge, d <= max_discharge
              (directives tighten these; see _apply_directives)
"""
import numpy as np
from scipy.optimize import linprog

from app.schemas import Directive, DirectiveType, HourPlan, Plan, Scenario

H = 24
DP = 4  # decimal places in the returned plan


class Infeasible(Exception):
    """No schedule satisfies the scenario plus the given directives."""


def _apply_directives(scenario: Scenario, directives: list[Directive]) -> dict[str, np.ndarray]:
    """Per-hour limits after applying every directive with applies = True (spec §5.3)."""
    b = scenario.battery
    limits = {
        "solar": np.array([h.solar_kwh for h in scenario.hours], dtype=float),
        "min_energy": np.full(H, b.minimum_energy_kwh),
        "max_charge": np.full(H, b.max_charge_kwh_per_hour),
        "max_discharge": np.full(H, b.max_discharge_kwh_per_hour),
        "max_grid": np.full(H, np.inf),
    }
    for d in directives:
        if not d.applies or d.directive_type == DirectiveType.no_op:
            continue
        adj = d.structured_adjustment
        hours = adj["hours"]
        match d.directive_type:
            case DirectiveType.solar_reduction:
                # Multiply so overlapping reductions stack; never uses more solar than any single note allows.
                limits["solar"][hours] *= adj["factor"]
            case DirectiveType.minimum_battery_reserve:
                limits["min_energy"][hours] = np.maximum(limits["min_energy"][hours], adj["minimum_energy_kwh"])
            case DirectiveType.no_charge_window:
                limits["max_charge"][hours] = 0.0
            case DirectiveType.no_discharge_window:
                limits["max_discharge"][hours] = 0.0
            case DirectiveType.max_grid_window:
                limits["max_grid"][hours] = np.minimum(limits["max_grid"][hours], adj["max_grid_kwh"])
    return limits


def optimize(scenario: Scenario, directives: list[Directive]) -> Plan:
    b = scenario.battery
    demand = np.array([h.demand_kwh for h in scenario.hours], dtype=float)
    tariff = np.array([h.tariff_bdt_per_kwh for h in scenario.hours], dtype=float)
    lim = _apply_directives(scenario, directives)
    e0 = b.initial_energy_kwh

    # Column blocks: g = 0..23, s = 24..47, c = 48..71, d = 72..95
    G, S, C, D = (slice(i * H, (i + 1) * H) for i in range(4))
    eye = np.eye(H)

    cost = np.zeros(4 * H)
    cost[G] = tariff

    a_eq = np.zeros((H + 1, 4 * H))
    a_eq[:H, G], a_eq[:H, S], a_eq[:H, C], a_eq[:H, D] = eye, eye, -eye, eye
    a_eq[H, C], a_eq[H, D] = 1.0, -1.0
    b_eq = np.append(demand, 0.0)

    # cumulative net charge after hour h, bounded above and below
    tri = np.tril(np.ones((H, H)))
    a_ub = np.zeros((2 * H, 4 * H))
    a_ub[:H, C], a_ub[:H, D] = tri, -tri          # sum(c-d) <= capacity - E0
    a_ub[H:, C], a_ub[H:, D] = -tri, tri          # -sum(c-d) <= E0 - min_h
    b_ub = np.concatenate([np.full(H, b.capacity_kwh - e0), e0 - lim["min_energy"]])

    bounds = (
        [(0, None if np.isinf(m) else m) for m in lim["max_grid"]]
        + [(0, s) for s in lim["solar"]]
        + [(0, m) for m in lim["max_charge"]]
        + [(0, m) for m in lim["max_discharge"]]
    )

    res = linprog(cost, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if res.status != 0:
        raise Infeasible(res.message)
    x = res.x

    # Post-process: one net battery action per hour, round, then recompute grid so balance is exact.
    hourly, energy = [], e0
    for h in range(H):
        net = round(float(x[C][h] - x[D][h]), DP)
        solar_used = round(float(x[S][h]), DP)
        energy = round(energy + net, DP)
        grid = round(float(demand[h]) + net - solar_used, DP)
        if grid < 0:  # float noise only; the LP keeps it >= 0
            grid = 0.0
        action = "charge" if net > 0 else "discharge" if net < 0 else "idle"
        hourly.append(HourPlan(
            hour=h,
            grid_kwh=grid,
            solar_used_kwh=solar_used,
            battery_action=action,
            battery_kwh=abs(net),
            battery_energy_after_kwh=energy,
        ))

    grids = [p.grid_kwh for p in hourly]
    return Plan(
        hourly_plan=hourly,
        total_grid_kwh=round(sum(grids), DP),
        total_cost_bdt=round(sum(g * float(t) for g, t in zip(grids, tariff)), DP),
        peak_grid_kwh=max(grids),
    )
