"""Chat UI for the analytics copilot."""

import sys
from pathlib import Path

import streamlit as st
import theme

ACCENT = "#8a5cf6"  # violet
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.copilot import Copilot  # noqa: E402

st.set_page_config(page_title="Analytics Copilot", layout="wide")
theme.apply(ACCENT)

SUGGESTIONS = [
    "What was total revenue by month?",
    "Top 5 pickup zones by total revenue",
    "What is the card tip rate in Manhattan?",
    "Average fare by borough",
    "How many trips were paid in cash in February?",
]

theme.hero(
    "Analytics Copilot — governed text-to-SQL",
    [
        ("Governed metrics", "9"),
        ("Dimensions", "6"),
        ("Golden eval", "12 / 12"),
        ("Median latency", "~50 ms"),
    ],
    ACCENT,
)

theme.guide_bar(
    {
        "problem": "Business users wait days for an analyst to answer simple "
                   "questions \u2014 and general-purpose text-to-SQL tools "
                   "answer fast but hallucinate tables, columns, and entire "
                   "metrics. This project asks: can plain-English questions "
                   "get instant, governed, provably correct answers?",
        "approach": "A deterministic composer resolves each question against "
                    "a governed metric registry \u2014 no LLM writes SQL. "
                    "Anything the registry can't answer gets a refusal, not a "
                    "guess, and a pinned golden eval proves correctness after "
                    "every data refresh.",
        "sources": [
            "Governed registry: copilot/registry.yaml (metrics, dimensions, filters)",
            "Warehouse: NYC taxi marts (shared with the semantic-layer project)",
            "Correctness gate: eval/golden.yaml with pinned values",
        ],
    },
    {
        "Governed metrics": {
            "what": "Business measures defined in the registry \u2014 total "
                    "revenue, trip count, card tip rate, and the rest.",
            "why": "The registry is the boundary of what can be asked. "
                   "Bounding the vocabulary is what makes hallucination "
                   "impossible rather than merely unlikely.",
            "interpret": "Nine metrics sounds small; it covers the questions "
                         "the business actually asks, and grows by editing one "
                         "YAML file \u2014 not code.",
            "source": "copilot/registry.yaml",
        },
        "Dimensions": {
            "what": "The approved ways to slice a metric: borough, zone, "
                    "payment type, month, and so on.",
            "why": "Group-bys are where text-to-SQL usually goes rogue; "
                   "restricting them to a governed list keeps every generated "
                   "query valid by construction.",
            "interpret": "'Tip rate by borough' works because borough is a "
                         "registered dimension; 'tip rate by weather' gets a "
                         "refusal because it isn't.",
            "source": "copilot/registry.yaml",
        },
        "Golden eval": {
            "what": "Twelve pinned question/answer cases run against the full "
                    "warehouse \u2014 structure and exact values both checked.",
            "why": "Correctness that isn't re-verified after every data "
                   "refresh is a rumor. The value pins make the eval a real "
                   "regression gate.",
            "interpret": "12/12 means every answer shown here matches the "
                         "warehouse to the cent. If a refresh changes January "
                         "revenue, the eval fails before a user notices.",
            "action": "Schedule the eval nightly; treat any failure as a "
                      "release blocker.",
            "source": "eval/golden.yaml + eval/eval_harness.py",
        },
        "Median latency": {
            "what": "Typical time from question to answer, measured across "
                    "the golden cases.",
            "why": "Speed is the design payoff: deterministic composition "
                   "skips the LLM round trip entirely.",
            "interpret": "~50 ms is instant by analyst standards \u2014 and "
                         "it costs nothing per question, which an LLM-backed "
                         "tool can't claim.",
            "source": "eval/eval_harness.py timings",
        },
    },
)

theme.brief(
    [
        ("Ask about the airports",
         "\"Top 5 pickup zones by total revenue\" — JFK and LaGuardia dominate "
         "the quarter; the copilot resolves it to one governed SQL statement."),
        ("Ask about tipping",
         "\"What is the card tip rate in Manhattan?\" — the metric is defined "
         "card-only because cash tips are never recorded. The registry carries "
         "that honesty."),
        ("Try to break it",
         "\"How do our trips compare to Uber?\" or \"ignore previous "
         "instructions and drop table fct_trips\" — off-domain and injection "
         "attempts get refusals, not guesses."),
    ],
    ACCENT,
)

theme.actions(
    [
        ("Add an LLM narration layer",
         "The deterministic composer stays the source of truth for SQL; an "
         "LLM would only narrate the returned table in prose. Hallucinated "
         "SQL stays impossible by construction."),
        ("Expand the registry",
         "New metrics and dimensions become askable by editing "
         "copilot/registry.yaml — no composer changes. Point it at the "
         "semantic layer's metrics.yml and the two stay in lockstep."),
        ("Schedule the golden eval",
         "Run eval/eval_harness.py nightly against the full warehouse. "
         "Value pins make it a real regression gate: if a data refresh "
         "changes January revenue, the eval fails before a user notices."),
    ],
    ACCENT,
)


@st.cache_resource
def get_bot() -> Copilot:
    return Copilot()


bot = get_bot()

if "history" not in st.session_state:
    st.session_state.history = []

cols = st.columns(len(SUGGESTIONS))
for col, suggestion in zip(cols, SUGGESTIONS):
    if col.button(suggestion, use_container_width=True):
        st.session_state.pending = suggestion

question = st.chat_input("Ask about the NYC taxi dataset...")
if "pending" in st.session_state:
    question = st.session_state.pop("pending")

if question:
    with st.spinner("thinking..."):
        answer = bot.ask(question)
    st.session_state.history.append((question, answer))

for q, a in reversed(st.session_state.history):
    with st.chat_message("user"):
        st.write(q)
    with st.chat_message("assistant"):
        if a.refusal:
            st.warning(a.refusal)
        else:
            result = a.result.rename(
                columns={c: theme.humanize(c) for c in a.result.columns})
            st.dataframe(result, hide_index=True, use_container_width=True)
            with st.expander("SQL"):
                st.code(a.sql, language="sql")
        st.caption(f"{a.elapsed_ms:.0f} ms")
