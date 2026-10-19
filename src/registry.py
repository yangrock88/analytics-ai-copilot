"""Load the governed registry and expose lookup helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = PROJECT_ROOT / "copilot" / "registry.yaml"


@dataclass
class Registry:
    raw: dict

    @property
    def metrics(self) -> dict:
        return self.raw["metrics"]

    @property
    def dimensions(self) -> dict:
        return self.raw["dimensions"]

    @property
    def filters(self) -> dict:
        return self.raw["filters"]

    @property
    def policy(self) -> dict:
        return self.raw["policy"]

    def corpus(self) -> list[tuple[str, str, str]]:
        """(kind, name, text) rows for retrieval indexing."""
        rows = []
        for name, m in self.metrics.items():
            text = f"{m['description']} | {' '.join(m['synonyms'])}"
            rows.append(("metric", name, text))
        for name, d in self.dimensions.items():
            text = f"{d['description']} | {' '.join(d['synonyms'])}"
            rows.append(("dimension", name, text))
        return rows


def load(path: Path = REGISTRY_PATH) -> Registry:
    return Registry(yaml.safe_load(path.read_text()))


if __name__ == "__main__":
    reg = load()
    print(f"{len(reg.metrics)} metrics, {len(reg.dimensions)} dimensions indexed")
