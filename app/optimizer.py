"""LP scheduler. Owner: Anadi.

TODO(Anadi, P0): scipy.optimize.linprog(method="highs"), 96 variables, per the optimizer spec in the plan.
"""
from app.schemas import Directive, Plan, Scenario


class Infeasible(Exception):
    """No schedule satisfies the scenario plus the given directives."""


def optimize(scenario: Scenario, directives: list[Directive]) -> Plan:
    raise NotImplementedError
