"""Paraphrase-robustness eval for the operator-note interpreter (rubric: LLM Directive Interpretation).

Runs every note in tests/eval/paraphrases.json through the live interpret_and_validate() path — the
same code the API uses — and scores the four fields the judge checks: applies, directive_type,
hours, numeric value. Also reports latency percentiles.

  python scripts/run_eval.py                 # all cases, one note per request
  python scripts/run_eval.py --batch 3       # pack 3 notes per request, like a real scenario
  python scripts/run_eval.py --only sr,res   # subset by id prefix
  python scripts/run_eval.py --url https://host --batch 3   # through a running server's POST /optimize-energy

Requires an LLM key in the environment or .env (see README). The interpretation cache is bypassed.
"""
import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["LLM_CACHE"] = "0"

import app.main  # noqa: E402,F401  (loads .env)
from app.directives import interpret_and_validate  # noqa: E402
from app.schemas import Battery  # noqa: E402

TOL = 0.01


def expected_value(case: dict) -> float | None:
    for k in ("factor", "minimum_energy_kwh", "max_grid_kwh"):
        if k in case:
            return float(case[k])
    return None


def actual_value(d) -> float | None:
    adj = d.structured_adjustment or {}
    for k in ("factor", "minimum_energy_kwh", "max_grid_kwh"):
        if k in adj:
            return float(adj[k])
    return None


def score(case: dict, d) -> dict[str, bool]:
    want_type = case["directive_type"]
    want_applies = want_type != "no_op"
    ok_applies = d.applies == want_applies
    ok_type = d.directive_type.value == want_type
    if want_type == "no_op":
        return {"applies": ok_applies, "type": ok_type, "hours": ok_type, "value": ok_type}
    got_hours = (d.structured_adjustment or {}).get("hours")
    ok_hours = got_hours == case.get("hours")
    ev, av = expected_value(case), actual_value(d)
    ok_value = (ev is None and av is None) or (ev is not None and av is not None and abs(ev - av) <= TOL)
    return {"applies": ok_applies, "type": ok_type, "hours": ok_hours, "value": ok_value}


def _http_interpreter(url: str):
    """Send each group as a full scenario to a running server and read back its directive_interpretation."""
    import httpx
    from app.schemas import Directive
    template = json.loads((ROOT / "examples/sample-06.request.json").read_text(encoding="utf-8"))
    client = httpx.Client(base_url=url.rstrip("/"), timeout=35)
    counter = {"n": 0}

    async def call(notes: list[str], battery: Battery) -> list:
        counter["n"] += 1
        body = dict(template, scenario_id=f"EVAL-{counter['n']}", operator_notes=notes, battery=battery.model_dump())
        r = client.post("/optimize-energy", json=body)
        r.raise_for_status()
        return [Directive.model_validate(d) for d in r.json()["directive_interpretation"]]
    return call


async def run(cases: list[dict], capacity: float, batch: int, seed: int, url: str | None = None) -> None:
    battery = Battery(capacity_kwh=capacity, initial_energy_kwh=capacity / 2, minimum_energy_kwh=capacity * 0.1,
                      max_charge_kwh_per_hour=capacity / 4, max_discharge_kwh_per_hour=capacity / 4)
    interpret = _http_interpreter(url) if url else interpret_and_validate
    order = list(cases)
    if batch > 1:
        random.Random(seed).shuffle(order)
    groups = [order[i:i + batch] for i in range(0, len(order), batch)]

    totals = {"applies": 0, "type": 0, "hours": 0, "value": 0}
    exact = 0
    latencies: list[float] = []
    failures: list[str] = []
    for group in groups:
        notes = [c["note"] for c in group]
        t0 = time.perf_counter()
        directives = await interpret(notes, battery)
        latencies.append(time.perf_counter() - t0)
        for c, d in zip(group, directives):
            s = score(c, d)
            for k, v in s.items():
                totals[k] += v
            if all(s.values()):
                exact += 1
            else:
                bad = ",".join(k for k, v in s.items() if not v)
                failures.append(f"{c['id']:7s} [{bad}] got {d.directive_type.value} {d.structured_adjustment} | want {c['directive_type']} "
                                f"hours={c.get('hours')} value={expected_value(c)}\n         note: {c['note']}")

    n = len(cases)
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
    print(f"\n{n} notes in {len(groups)} requests ({batch} per request)")
    for k, v in totals.items():
        print(f"  {k:8s} {v}/{n}  ({100 * v / n:.0f}%)")
    print(f"  exact    {exact}/{n}  ({100 * exact / n:.0f}%)")
    print(f"  latency  p50 {p50 * 1000:.0f} ms · p95 {p95 * 1000:.0f} ms · max {latencies[-1] * 1000:.0f} ms")
    if failures:
        print("\nFailures:")
        for f in failures:
            print("  " + f)
    sys.exit(0 if exact == n else 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=1, help="notes per request (1-3)")
    ap.add_argument("--only", help="comma-separated id prefixes, e.g. sr,no")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--url", help="base URL of a running server; scores its live responses instead of the in-process path")
    args = ap.parse_args()
    pack = json.loads((ROOT / "tests/eval/paraphrases.json").read_text(encoding="utf-8"))
    cases = pack["cases"]
    if args.only:
        prefixes = tuple(p.strip() for p in args.only.split(","))
        cases = [c for c in cases if c["id"].startswith(prefixes)]
    asyncio.run(run(cases, float(pack["_meta"]["battery_capacity_kwh"]), max(1, min(3, args.batch)), args.seed, args.url))


if __name__ == "__main__":
    main()
