from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from apps.maintenance.application.useCases.equipmentLifecycleUseCases import (
    GetDeviceLifecycleAnalysisQuery,
    GetDeviceLifecycleAnalysisUseCase,
)
from apps.maintenance.domain.services.equipmentLifecycle import EquipmentLifecycleSnapshot
from apps.maintenance.infrastructure.services.equipmentLifecycleAiAdvisor import (
    ConfiguredEquipmentLifecycleAIAdvisor,
)


class FakeModelCaller:
    def __init__(self, structured):
        self.structured = structured
        self.request = None

    def call(self, tenantId, request):
        self.request = request
        return SimpleNamespace(answer="", structured=self.structured)


class EquipmentLifecycleAiAdvisorTests(unittest.TestCase):
    def test_advisory_uses_aggregate_metrics_and_localized_request(self) -> None:
        caller = FakeModelCaller(
            {
                "summary": "Recent gauge readings are below the configured baseline.",
                "recommendations": ["Verify the meter and inspect the declining subsystem."],
            }
        )
        advisor = ConfiguredEquipmentLifecycleAIAdvisor(
            caller=caller,
            providerCode="openai",
            modelCode="maintenance-model",
        )

        result = advisor.advise(
            tenantId="tenant-1",
            language="en",
            analysis={
                "deviceId": "do-not-send",
                "condition": "watch",
                "confidence": "medium",
                "events": {"correctiveCount": 12, "majorRepairCount": 1},
                "reliability": {"failureFrequencyTrend": "increasing"},
                "performance": {
                    "trend": "declining",
                    "validReadingCount": 5,
                    "signals": [
                        {
                            "name": "Output pressure",
                            "unit": "bar",
                            "trend": "declining",
                            "readingCount": 5,
                            "retentionPercent": 82.0,
                        }
                    ],
                },
                "lifeEstimate": {
                    "status": "insufficientData",
                    "peerCount": 1,
                    "estimatedRemainingMajorRepairs": None,
                },
                "rawWorkOrderNarrative": "private text must not be sent",
                "limitations": ["Insufficient retirement peers."],
            },
        )

        self.assertEqual(result["summary"], "Recent gauge readings are below the configured baseline.")
        self.assertEqual(caller.request.modelPolicy["provider"], "OPENAI")
        self.assertEqual(caller.request.input["language"], "en")
        submitted = caller.request.input["analysis"]
        self.assertNotIn("deviceId", submitted)
        self.assertNotIn("rawWorkOrderNarrative", submitted)
        self.assertEqual(submitted["events"]["correctiveCount"], 12)
        self.assertIn("not invent measurements", caller.request.instructions)
        self.assertEqual(caller.request.outputSchema["properties"]["recommendations"]["maxItems"], 3)

    def test_invalid_provider_reply_returns_no_ai_note(self) -> None:
        caller = FakeModelCaller({"summary": " ", "recommendations": []})
        advisor = ConfiguredEquipmentLifecycleAIAdvisor(
            caller=caller,
            providerCode="LOCAL",
            modelCode="test-model",
        )

        self.assertIsNone(advisor.advise(tenantId="tenant-2", language="fa", analysis={}))

    def test_unconfigured_provider_is_a_clean_noop(self) -> None:
        advisor = ConfiguredEquipmentLifecycleAIAdvisor(providerCode="", modelCode="")

        self.assertIsNone(advisor.advise(tenantId="tenant-3", language="de", analysis={}))

    def test_ai_note_does_not_replace_statistical_result_or_change_asset_state(self) -> None:
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        deviceRepository = SimpleNamespace(getById=lambda tenantId, deviceId: object())
        lifecycleRepository = SimpleNamespace(
            getSnapshot=lambda tenantId, deviceId, at: EquipmentLifecycleSnapshot()
        )
        advisor = SimpleNamespace(
            advise=lambda **kwargs: {
                "summary": "There is not enough evidence for a useful-life estimate.",
                "recommendations": ["Record suitable meter readings."],
            }
        )
        noOp = object()
        useCase = GetDeviceLifecycleAnalysisUseCase(
            deviceRepository=deviceRepository,
            lifecycleRepository=lifecycleRepository,
            aiAdvisor=advisor,
            unitOfWork=noOp,
            auditRecorder=noOp,
            eventDispatcher=noOp,
            permissionGate=noOp,
            clock=SimpleNamespace(nowUtc=lambda: now),
        )

        with patch(
            "apps.maintenance.application.useCases.equipmentLifecycleUseCases.resolveTenantId",
            return_value="tenant-1",
        ):
            dto = useCase.perform(
                GetDeviceLifecycleAnalysisQuery(
                    deviceId="f1587b93-68fb-4525-861d-e5769d1f6f15", language="en"
                )
            )

        self.assertEqual(dto.analysisMethod, "provider-assisted-advisory-v1")
        self.assertEqual(dto.condition, "insufficientData")
        self.assertEqual(dto.lifeEstimate["status"], "insufficientData")
        self.assertIn("There is not enough evidence", dto.aiAdvisory["summary"])
        self.assertTrue(dto.advisoryOnly)


if __name__ == "__main__":
    unittest.main()
