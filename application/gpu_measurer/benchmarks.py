from __future__ import annotations

import csv
import re
from difflib import SequenceMatcher
from pathlib import Path

from .models import BenchmarkMatch


def normalize_gpu_name(name: str) -> str:
    normalized = name.lower()
    normalized = re.sub(r"\b(nvidia|amd|intel)\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


class BenchmarkRepository:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.passmark_rows = self._load("passmark_gpu_benchmarks.csv")
        self.compute_rows = self._load("gpu_compute_api_benchmarks.csv")
        self._passmark = {
            normalize_gpu_name(row.get("gpuName", "")): row for row in self.passmark_rows
        }
        self._compute = {
            normalize_gpu_name(row.get("Device", "")): row for row in self.compute_rows
        }

    def _load(self, filename: str) -> list[dict[str, str]]:
        path = self.data_dir / filename
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def match(self, gpu_name: str) -> BenchmarkMatch:
        key = normalize_gpu_name(gpu_name)
        match = BenchmarkMatch(
            requested_name=gpu_name,
            passmark=self._passmark.get(key),
            compute=self._compute.get(key),
        )
        if match.exact:
            return match

        scored: list[tuple[str, float]] = []
        seen = set()
        for row in self.passmark_rows:
            name = row.get("gpuName", "")
            if not name or name in seen:
                continue
            seen.add(name)
            score = SequenceMatcher(None, key, normalize_gpu_name(name)).ratio()
            scored.append((name, score))
        match.suggestions = sorted(scored, key=lambda item: item[1], reverse=True)[:3]
        return match
