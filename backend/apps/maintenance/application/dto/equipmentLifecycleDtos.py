"""DTOs for advisory equipment-lifecycle analysis."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeviceLifecycleAnalysisDto:
    deviceId: str
    generatedAt: str
    advisoryOnly: bool
    analysisMethod: str
    condition: str
    confidence: str
    confidenceReason: str
    summary: str
    events: dict[str, object] = field(default_factory=dict)
    reliability: dict[str, object] = field(default_factory=dict)
    performance: dict[str, object] = field(default_factory=dict)
    lifeEstimate: dict[str, object] = field(default_factory=dict)
    partLifeEstimates: list[dict[str, object]] = field(default_factory=list)
    indicators: list[dict[str, str]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    aiAdvisory: dict[str, object] | None = None


@dataclass(frozen=True)
class RepairScopeSuggestionDto:
    suggestedScope: str
    confidence: str
    reasons: list[str] = field(default_factory=list)
    requiresHumanConfirmation: bool = True
    analysisMethod: str = "explainable-rule-fallback"
