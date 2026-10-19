"""Analytics copilot demo runner.

Usage:
    python run.py setup      # build local warehouse from fixtures (offline)
    python run.py ask "What was total revenue by month?"
    python run.py eval       # run the golden set -> eval/eval_report.md
    python run.py chat       # streamlit chat UI

To point at the full taxi warehouse (project 1):
    set COPILOT_WAREHOUSE=..\\nyc-taxi-semantic-layer\\data\\warehouse.duckdb
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.copilot import Copilot, build_fixture_warehouse  # noqa: E402
from src.copilot import resolve_warehouse  # noqa: E402

WAREHOUSE = PROJECT_ROOT / "data" / "warehouse.duckdb"
FIXTURES = PROJECT_ROOT / "data" / "fixtures"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "ask", "eval", "chat"])
    parser.add_argument("question", nargs="*", default=[])
    args = parser.parse_args()

    if args.command == "setup":
        build_fixture_warehouse(FIXTURES, WAREHOUSE)
        print(f"fixture warehouse ready at {WAREHOUSE}")
        return

    if args.command in ("ask", "eval", "chat"):
        resolved = resolve_warehouse()
        if not resolved.exists():
            print("no warehouse found; run `python run.py setup` first "
                  "(or set COPILOT_WAREHOUSE)")
            sys.exit(1)
        print(f"warehouse: {resolved}")

    if args.command == "ask":
        bot = Copilot()
        question = " ".join(args.question)
        answer = bot.ask(question)
        print(f"Q: {question}\n")
        if answer.refusal:
            print(f"REFUSAL: {answer.refusal}")
        else:
            print(f"SQL:\n{answer.sql}\n")
            print(answer.result.to_string(max_rows=25))
        print(f"\n({answer.elapsed_ms:.0f} ms)")

    if args.command == "eval":
        from eval.eval_harness import main as eval_main
        sys.exit(eval_main())

    if args.command == "chat":
        app = PROJECT_ROOT / "dashboards" / "app.py"
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(app)], check=True)


if __name__ == "__main__":
    main()
