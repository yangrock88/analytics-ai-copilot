"""Offline eval harness: runs the golden set through the copilot and scores
structure, behavior, and (where pinned) values. This is how a copilot change
earns the right to ship -- the same discipline as an LLM eval pipeline, minus
the nondeterminism.

Usage: python -m eval.eval_harness [--warehouse PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.copilot import Copilot, resolve_warehouse  # noqa: E402

# value pins in golden.yaml are measured against the full taxi warehouse;
# on any other warehouse (e.g. the 3k-row fixtures) they are skipped.
FULL_WAREHOUSE = (PROJECT_ROOT.parent / "nyc-taxi-semantic-layer"
                  / "data" / "warehouse.duckdb")


def score_case(bot: Copilot, case: dict, check_values: bool) -> dict:
    q = case["question"]
    expect = case["expect"]
    answer = bot.ask(q, execute=True)
    failures = []

    if expect.get("refused"):
        if answer.refusal is None:
            failures.append(f"expected refusal, got SQL: {answer.sql}")
    else:
        if answer.refusal is not None:
            failures.append(f"unexpected refusal: {answer.refusal}")
        else:
            spec_sql = (answer.sql or "").lower()
            if expect.get("metric") and f"as {expect['metric']}" not in spec_sql:
                failures.append(f"metric {expect['metric']} not in SQL")
            for dim in expect.get("dimensions", []):
                if dim not in spec_sql:
                    failures.append(f"dimension {dim} not in SQL")
            if expect.get("borough_filter") and expect["borough_filter"] not in (answer.sql or ""):
                failures.append("borough filter missing")
            if expect.get("payment_filter") and expect["payment_filter"] not in spec_sql:
                failures.append("payment filter missing")
            if expect.get("month") and f"month(t.picked_up_at) = {expect['month']}" not in (answer.sql or ""):
                failures.append("month filter missing")
            if expect.get("year") and str(expect["year"]) not in (answer.sql or ""):
                failures.append("year filter missing")
            if expect.get("top_n") and f"limit {expect['top_n']}" not in spec_sql:
                failures.append("top_n limit missing")

            if "expected_value" in expect and not check_values:
                pass  # structural checks still apply; value pin skipped
            elif "expected_value" in expect and answer.result is not None:
                got = float(answer.result.iloc[0, -1])
                want = float(expect["expected_value"])
                tol = float(expect.get("rel_tolerance", 0.02))
                if want == 0:
                    ok = abs(got) < 1e-9
                else:
                    ok = abs(got - want) / abs(want) <= tol
                if not ok:
                    failures.append(f"value {got:,.2f} != pinned {want:,.2f} (±{tol:.0%})")

    return {
        "id": case["id"],
        "question": q,
        "passed": not failures,
        "failures": failures,
        "elapsed_ms": answer.elapsed_ms,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse", default=None)
    # parse_known_args: this main() is also called from run.py, whose own
    # argv ('run.py eval') is none of this parser's business
    args, _ = parser.parse_known_args()

    warehouse = resolve_warehouse(Path(args.warehouse) if args.warehouse else None)
    check_values = warehouse.resolve() == FULL_WAREHOUSE.resolve()
    print(f"eval warehouse: {warehouse} "
          f"({'value pins enforced' if check_values else 'value pins skipped'})")

    bot = Copilot(warehouse=warehouse)
    cases = yaml.safe_load((PROJECT_ROOT / "eval" / "golden.yaml").read_text())

    results = [score_case(bot, case, check_values) for case in cases]
    passed = sum(r["passed"] for r in results)

    lines = ["# Copilot eval report", ""]
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        lines.append(f"- [{mark}] {r['id']}: {r['question']} ({r['elapsed_ms']:.0f} ms)")
        for f in r["failures"]:
            lines.append(f"    - {f}")
    lines.append("")
    lines.append(f"**{passed}/{len(results)} cases passed**")

    report = PROJECT_ROOT / "eval" / "eval_report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
