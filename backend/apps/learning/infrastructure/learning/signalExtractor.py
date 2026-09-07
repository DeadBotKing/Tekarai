"""Deterministic, schema-preserving feature/signal extraction baseline."""

from __future__ import annotations


class DeterministicSignalExtractor:
    def extract(self, samples: tuple[dict, ...]) -> tuple[dict, ...]:
        extracted = []
        for sample in samples:
            signals = {}
            for key, value in sample.get("input", {}).items():
                if isinstance(value, (int, float, bool, str)):
                    signals[str(key)] = value
            extracted.append({**sample, "features": signals})
        return tuple(extracted)
