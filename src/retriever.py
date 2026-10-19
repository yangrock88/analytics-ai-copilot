"""Local TF-IDF retrieval over the registry corpus.

No embeddings service, no API keys: sklearn's TfidfVectorizer is plenty for a
40-entity governed corpus, and it runs the same in CI as on a laptop. That is
a feature -- the copilot's retrieval layer is reproducible offline.
"""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .registry import Registry


@dataclass
class Match:
    kind: str       # "metric" | "dimension"
    name: str
    score: float


class Retriever:
    def __init__(self, registry: Registry):
        self.registry = registry
        corpus = registry.corpus()
        self._keys = [(kind, name) for kind, name, _ in corpus]
        self._vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
        self._matrix = self._vectorizer.fit_transform([text for _, _, text in corpus])

    def search(self, question: str, top_k: int = 8) -> list[Match]:
        q = self._vectorizer.transform([question.lower()])
        scores = cosine_similarity(q, self._matrix)[0]
        ranked = scores.argsort()[::-1][:top_k]
        return [
            Match(kind=self._keys[i][0], name=self._keys[i][1], score=float(scores[i]))
            for i in ranked if scores[i] > 0
        ]


if __name__ == "__main__":
    from .registry import load
    reg = load()
    r = Retriever(reg)
    for m in r.search("what was revenue by state in 2017"):
        print(f"{m.kind:<10} {m.name:<20} {m.score:.3f}")
