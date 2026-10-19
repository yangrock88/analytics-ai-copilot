"""Deterministic question -> SQL composer over the governed registry.

Parse order matters: an entity mention can mean a group-by, a filter, or part
of a metric synonym, and the wrong read changes the answer. The rules below
are deliberately simple and documented; anything that doesn't parse cleanly
is a refusal, not a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .registry import Registry
from .retriever import Retriever

METRIC_THRESHOLD = 0.20
YEAR_RE = re.compile(r"\b(2024)\b")
TOP_N_RE = re.compile(r"\btop\s+(\d+)\b", re.IGNORECASE)

# governed-domain guard: named external entities we have no data about.
# a real copilot needs this tripwire as much as it needs retrieval.
OUT_OF_DOMAIN = [
    "amazon", "walmart", "uber", "lyft", "competitor", "competitors",
    "weather", "stock price", "netflix", "subway", "citi bike",
]

BOROUGHS = ["manhattan", "queens", "brooklyn", "bronx",
            "staten island", "ewr"]

MONTHS = {"january": 1, "february": 2, "march": 3}


@dataclass
class QuerySpec:
    metric: str
    dimensions: list[str] = field(default_factory=list)
    borough_filter: str | None = None
    payment_filter: str | None = None
    month: int | None = None
    year: int | None = None
    top_n: int | None = None


@dataclass
class ComposeResult:
    sql: str | None
    spec: QuerySpec | None
    refusal: str | None


def _find_metric(question: str, retriever: Retriever) -> tuple[str | None, float]:
    metric_matches = [m for m in retriever.search(question, top_k=6)
                      if m.kind == "metric"]
    if not metric_matches or metric_matches[0].score < METRIC_THRESHOLD:
        return None, metric_matches[0].score if metric_matches else 0.0
    return metric_matches[0].name, metric_matches[0].score


def _find_dimensions(question: str, registry: Registry) -> list[str]:
    dims = []
    q = question.lower()
    for name, dim in registry.dimensions.items():
        for syn in dim["synonyms"]:
            syn_re = re.escape(syn) if syn.endswith("s") else re.escape(syn) + "s?"
            patterns = [
                # "revenue by borough", "trips per zone"
                rf"\b(?:by|per|each|across)\s+(?:\w+\s+)??{syn_re}\b",
                # "top 5 zones by revenue", "top boroughs"
                rf"\btop\s+(?:\d+\s+)?(?:\w+\s+)??{syn_re}\b",
            ]
            if any(re.search(p, q) for p in patterns):
                dims.append(name)
                break
    if any(w in q for w in ["monthly", "over time", "trend", "by month", "per month"]):
        if "pickup_month" not in dims:
            dims.append("pickup_month")
    return dims


def parse(question: str, registry: Registry, retriever: Retriever) -> ComposeResult:
    lowered = question.lower()
    for entity in OUT_OF_DOMAIN:
        if entity in lowered:
            return ComposeResult(
                sql=None, spec=None,
                refusal=(
                    f"'{entity}' is outside this dataset (NYC yellow taxis, "
                    "Q1 2024). I only answer from the governed marts."
                ),
            )

    metric, score = _find_metric(question, retriever)
    if metric is None:
        available = ", ".join(sorted(registry.metrics))
        return ComposeResult(
            sql=None, spec=None,
            refusal=(
                "I couldn't map that to a governed metric "
                f"(best retrieval score {score:.2f}, threshold {METRIC_THRESHOLD}). "
                f"I can answer about: {available}."
            ),
        )

    spec = QuerySpec(metric=metric)
    spec.dimensions = _find_dimensions(question, registry)

    # a named borough is a filter, not a group-by, unless "by borough" was asked
    for borough in BOROUGHS:
        if re.search(rf"\b{re.escape(borough)}\b", lowered):
            spec.borough_filter = borough.title()
            spec.dimensions = [d for d in spec.dimensions
                               if d != "pickup_borough"]
            break

    # explicit cash/card payment filters ("paid in cash", "cash trips").
    # note: "card tip rate" is a metric synonym, not a payment filter, so we
    # only trip on cash or on card + paid/trips phrasing.
    if re.search(r"\bcash\b", lowered):
        spec.payment_filter = "cash"
    elif re.search(r"\bcredit card\b", lowered) or (
        re.search(r"\bcard\b", lowered)
        and re.search(r"\bpaid|\btrips\b", lowered)
    ):
        spec.payment_filter = "credit_card"

    for name, num in MONTHS.items():
        if re.search(rf"\b{name}\b", lowered):
            spec.month = num
            break

    year_match = YEAR_RE.search(question)
    if year_match:
        spec.year = int(year_match.group(1))

    top_n = TOP_N_RE.search(question)
    if top_n:
        spec.top_n = int(top_n.group(1))

    return ComposeResult(sql=None, spec=spec, refusal=None)


def build_sql(spec: QuerySpec, registry: Registry) -> str:
    metric_def = registry.metrics[spec.metric]

    select_parts, where_parts, group_parts = [], [], []

    for dim_name in spec.dimensions:
        dim = registry.dimensions[dim_name]
        select_parts.append(f"{dim['expr']} as {dim_name}")
        group_parts.append(dim["expr"])

    select_parts.append(f"{metric_def['expr']} as {spec.metric}")

    if spec.borough_filter:
        where_parts.append(f"t.pickup_borough = '{spec.borough_filter}'")
    if spec.payment_filter:
        where_parts.append(f"t.payment_desc = '{spec.payment_filter}'")
    if spec.month:
        where_parts.append(f"month(t.picked_up_at) = {spec.month}")
    if spec.year:
        where_parts.append(f"year(t.picked_up_at) = {spec.year}")

    sql = "select " + ", ".join(select_parts)
    sql += "\nfrom marts.fct_trips t"
    if where_parts:
        sql += "\nwhere " + " and ".join(where_parts)
    if group_parts:
        sql += "\ngroup by " + ", ".join(group_parts)
        if spec.dimensions == ["pickup_month"]:
            sql += "\norder by pickup_month"
        else:
            sql += f"\norder by {spec.metric} desc"
    if spec.top_n:
        sql += f"\nlimit {spec.top_n}"
    return sql


def compose(question: str, registry: Registry, retriever: Retriever) -> ComposeResult:
    parsed = parse(question, registry, retriever)
    if parsed.refusal:
        return parsed
    parsed.sql = build_sql(parsed.spec, registry)
    return parsed
