"""Safe deterministic baseline engine used offline and for platform tests."""

from __future__ import annotations

import random

from apps.learning.domain.valueObjects.learningTypes import canonicalJson, integrityHash


class DeterministicLearningEngine:
    """Builds a reproducible statistical artifact, never executing user code."""

    def train(self, *, samples, algorithm, configuration, seed):
        random.seed(seed)
        if not samples:
            raise ValueError("Training requires at least one sample.")
        artifact = {
            "format": "tekarai-learning-artifact-v1",
            "algorithm": algorithm,
            "configuration": configuration,
            "sampleHashes": [sample["sampleHash"] for sample in samples],
            "seed": seed,
            "fingerprint": integrityHash([sample["target"] for sample in samples]),
        }
        content = canonicalJson(artifact).encode("utf-8")
        count = len(samples)
        metrics = {
            "sampleCount": float(count),
            "trainingScore": min(0.99, 0.5 + count / 2000),
            "trainingLatencyMs": float(count),
        }
        return content, metrics
