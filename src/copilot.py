"""The copilot facade: question -> retrieval -> compose -> validate -> execute
-> answer. Every stage is independently testable and none of them phone home.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from . import composer, validator
from .registry import load as load_registry
from .retriever import Retriever

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WAREHOUSE = PROJECT_ROOT / "data" / "warehouse.duckdb"
# the full 9.5M-trip warehouse lives in the sibling taxi project
TAXI_WAREHOUSE = (PROJECT_ROOT.parent / "nyc-taxi-semantic-layer"
                  / "data" / "warehouse.duckdb")


def resolve_warehouse(warehouse: Path | None = None) -> Path:
    """Resolution order: explicit arg > COPILOT_WAREHOUSE env > the full
    taxi warehouse when present > the local fixture warehouse."""
    if warehouse is not None:
        return Path(warehouse)
    if os.environ.get("COPILOT_WAREHOUSE"):
        return Path(os.environ["COPILOT_WAREHOUSE"])
    if TAXI_WAREHOUSE.exists():
        return TAXI_WAREHOUSE
    return DEFAULT_WAREHOUSE


@dataclass
class Answer:
    question: str
    sql: str | None
    result: pd.DataFrame | None
    refusal: str | None
    elapsed_ms: float


class Copilot:
    def __init__(self, warehouse: Path | None = None):
        self.registry = load_registry()
        self.retriever = Retriever(self.registry)
        self.warehouse = str(resolve_warehouse(warehouse))
        self.allowed = set(self.registry.raw["tables"].values())

    def ask(self, question: str, execute: bool = True) -> Answer:
        started = time.perf_counter()
        composed = composer.compose(question, self.registry, self.retriever)
        if composed.refusal:
            return Answer(question, None, None, composed.refusal,
                          self._elapsed(started))

        try:
            sql = validator.validate(
                composed.sql,
                allowed_tables=self.allowed,
                default_limit=self.registry.policy["default_limit"],
                max_limit=self.registry.policy["max_limit"],
            )
            validator.dry_run(sql, self.warehouse)
        except validator.ValidationError as exc:
            return Answer(question, composed.sql, None, f"refused: {exc}",
                          self._elapsed(started))

        result = None
        if execute:
            with duckdb.connect(self.warehouse, read_only=True) as con:
                result = con.execute(sql).df()
        return Answer(question, sql, result, None, self._elapsed(started))

    @staticmethod
    def _elapsed(started: float) -> float:
        return (time.perf_counter() - started) * 1000


def build_fixture_warehouse(fixtures_dir: Path, warehouse: Path) -> None:
    """Build a local warehouse from fixture CSVs (offline dev/tests).

    DuckDB's CSV sniffer infers timestamps/booleans, so the fixture warehouse
    keeps the same column types as the real one -- pandas would string-ify
    them and quietly break date functions downstream.
    """
    with duckdb.connect(str(warehouse)) as con:
        con.execute("create schema if not exists marts")
        for csv_path in sorted(fixtures_dir.glob("*.csv")):
            con.execute(
                f"create or replace table marts.{csv_path.stem} as "
                f"select * from read_csv_auto('{csv_path.as_posix()}', header=true)"
            )


if __name__ == "__main__":
    import sys
    bot = Copilot()
    q = " ".join(sys.argv[1:]) or "What was total revenue by month?"
    answer = bot.ask(q)
    print("SQL:\n", answer.sql or "(none)")
    if answer.refusal:
        print("REFUSAL:", answer.refusal)
    elif answer.result is not None:
        print(answer.result.head(12).to_string())
    print(f"({answer.elapsed_ms:.0f} ms)")
