# Analytics Copilot — Governed Text-to-SQL Without the LLM Tax

A natural-language analytics copilot over the NYC taxi semantic layer
(project 1: 9.5M real trips, $252M in fares). The design thesis: **for a
governed metric catalog, deterministic text-to-SQL beats an LLM on every
axis that matters in production** — accuracy, latency, cost, testability —
and it runs fully offline in CI.

```
question
   -> retrieval (local TF-IDF over the governed registry, no embeddings API)
   -> compose   (deterministic parser: metric + dimensions + filters + window)
   -> validate  (read-only, table allowlist, LIMIT injection, EXPLAIN dry-run)
   -> execute   (DuckDB)
   -> answer    (data + the SQL that produced it)
```

Anything that doesn't parse cleanly is a **refusal**, not a hallucination.

## The governed registry

`copilot/registry.yaml` is the single source of truth: 9 metrics, 6
dimensions, synonyms, and policy. It mirrors the dbt semantic layer in
`nyc-taxi-semantic-layer/dbt/models/marts/metrics.yml` — the copilot
literally cannot reference a table or metric the analytics team hasn't
governed. It also inherits the semantic layer's honesty: tip rate is
computed on card trips only, because cash tips are never recorded.

## The eval story

`eval/golden.yaml` pins 12 cases: structure (metric/dimension/filters),
behavior (refusals for weather, competitor questions, and a prompt-injection
attempt), and **pinned values** verified against the full warehouse
(e.g. January 2024 revenue = $78,181,096.34, Manhattan card tip rate =
23.67%).

`python run.py eval` regenerates `eval/eval_report.md`. Change the composer,
rerun the eval, diff the report — that's the ship/no-ship gate, the same
discipline as an LLM eval pipeline minus the nondeterminism.

## Run it

```bat
python run.py setup                                  :: fixture warehouse (offline)
python run.py ask "Top 5 pickup zones by total revenue"
python run.py eval                                   :: golden set report
python run.py chat                                   :: streamlit UI
pytest tests -q

:: point at the full 9.5M-trip warehouse (project 1):
set COPILOT_WAREHOUSE=..\nyc-taxi-semantic-layer\data\warehouse.duckdb
```

## What I'd add an LLM for (and what I wouldn't)

- **Worth it**: paraphrase-heavy intent classification beyond the synonym
  table, free-form filter extraction, answer narration.
- **Not worth it**: SQL generation over a governed catalog (the composer is
  exact and inspectable), safety validation (deterministic rules beat
  probabilistic refusals), value computation (the warehouse computes; the
  model should never do arithmetic).

Known scope limits, stated out loud: 9 metrics / 6 dimensions, one dataset,
English questions, no multi-turn context. Widening the registry widens the
copilot; nothing else changes.
