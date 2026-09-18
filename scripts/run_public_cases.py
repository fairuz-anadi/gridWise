"""Run the 10 public sample cases through POST /optimize-energy and check every result.

  python scripts/run_public_cases.py --directives=reference   # in-process, reference interpretations injected (no LLM)
  python scripts/run_public_cases.py --directives=live        # in-process, real interpreter
  python scripts/run_public_cases.py --url https://our-app    # a running server (always live interpreter)

Checks per case: HTTP 200, interpretation matches the reference, our replay check against the
reference directives passes (what the judge does), and cost matches the reference optimum.
"""
import argparse
import logging
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.schemas import Directive, Plan, Scenario  # noqa: E402
from app.validator import replay_check  # noqa: E402

TOL = 0.01
for name in ("httpx", "httpx2", "gridwise"):
    logging.getLogger(name).setLevel(logging.WARNING)


def interpretation_diffs(got: list[dict], want: list[dict]) -> list[str]:
    if len(got) != len(want):
        return [f"{len(got)} interpretation entries, expected {len(want)}"]
    diffs = []
    for g, w in zip(got, want):
        i = w["note_index"]
        for key in ("note_index", "applies", "directive_type"):
            if g.get(key) != w[key]:
                diffs.append(f"note {i}: {key} = {g.get(key)!r}, expected {w[key]!r}")
        ga, wa = g.get("structured_adjustment"), w["structured_adjustment"]
        if (ga is None) != (wa is None) or (wa and set(ga) != set(wa)):
            diffs.append(f"note {i}: structured_adjustment = {ga}, expected {wa}")
            continue
        for key, val in (wa or {}).items():
            ok = ga[key] == val if key == "hours" else abs(ga[key] - val) <= TOL
            if not ok:
                diffs.append(f"note {i}: {key} = {ga[key]}, expected {val}")
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directives", choices=["reference", "live"], default="live")
    parser.add_argument("--url", help="base URL of a running server (implies --directives=live)")
    args = parser.parse_args()

    cases = json.loads((ROOT / "tests/fixtures/public_cases.json").read_text(encoding="utf-8"))["cases"]
    reference = {c["input"]["scenario_id"]: c["expected_output"]["directive_interpretation"] for c in cases}

    if args.url:
        import httpx
        client = httpx.Client(base_url=args.url.rstrip("/"), timeout=35)
    else:
        from fastapi.testclient import TestClient
        import app.main
        if args.directives == "reference":
            async def inject(notes, battery):
                sid = current["id"]
                return [Directive.model_validate(d) for d in reference[sid]]
            app.main.interpret_and_validate = inject
        client = TestClient(app.main.app)

    current, passed, latencies = {}, 0, []
    for case in cases:
        cid, body, expected = case["id"], case["input"], case["expected_output"]
        current["id"] = body["scenario_id"]
        start = time.perf_counter()
        r = client.post("/optimize-energy", json=body)
        latencies.append(time.perf_counter() - start)
        problems = []
        if r.status_code != 200:
            problems.append(f"HTTP {r.status_code}: {r.text[:200]}")
        else:
            out = r.json()
            if out.get("scenario_id") != body["scenario_id"]:
                problems.append("scenario_id not echoed")
            problems += interpretation_diffs(out.get("directive_interpretation", []),
                                             expected["directive_interpretation"])
            truth = [Directive.model_validate(d) for d in expected["directive_interpretation"]]
            problems += replay_check(Scenario.model_validate(body), truth, Plan.model_validate(out))
            if abs(out["total_cost_bdt"] - expected["total_cost_bdt"]) > TOL:
                problems.append(f"cost {out['total_cost_bdt']} vs optimum {expected['total_cost_bdt']}")
        status = "PASS" if not problems else "FAIL"
        passed += not problems
        print(f"{status} {cid} ({latencies[-1] * 1000:.0f} ms)")
        for p in problems:
            print(f"     - {p}")

    latencies.sort()
    p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
    print(f"\n{passed}/{len(cases)} passed, p95 {p95 * 1000:.0f} ms")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
