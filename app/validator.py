"""Replay checker: re-applies every Problem Statement §11 rule to a finished plan. Owner: Anadi.

TODO(Anadi, P0): implement all §11 checks.
"""
from app.schemas import Directive, Plan, Scenario


def replay_check(scenario: Scenario, directives: list[Directive], plan: Plan) -> list[str]:
    """Return a list of violation messages; [] means the plan is valid."""
    raise NotImplementedError
