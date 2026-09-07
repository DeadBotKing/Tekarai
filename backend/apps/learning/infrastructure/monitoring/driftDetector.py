"""Base distribution/performance drift detector."""

from __future__ import annotations


class ThresholdDriftDetector:
    def detect(self, *, baseline, current, thresholds):
        changes = {}
        detected = False
        for name, threshold in thresholds.items():
            if name not in baseline or name not in current:
                continue
            denominator = max(abs(float(baseline[name])), 1e-9)
            relative = abs(float(current[name]) - float(baseline[name])) / denominator
            changes[name] = round(relative, 8)
            detected = detected or relative > float(threshold)
        return detected, changes
