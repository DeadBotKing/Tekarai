from types import SimpleNamespace
import unittest

from apps.maintenance.infrastructure.services.repairScopeAiAdvisor import (
    ConfiguredRepairScopeAIAdvisor,
)


class FakeModelCaller:
    def __init__(self, structured):
        self.structured = structured
        self.request = None

    def call(self, tenantId, request):
        self.request = request
        return SimpleNamespace(answer="", structured=self.structured)


class RepairScopeAiAdvisorTests(unittest.TestCase):
    def test_provider_result_is_validated_and_always_requires_human_confirmation(self) -> None:
        caller = FakeModelCaller(
            {
                "suggestedScope": "major",
                "confidence": "high",
                "reasons": ["Evidence indicates replacement of a main assembly."],
            }
        )
        advisor = ConfiguredRepairScopeAIAdvisor(
            caller=caller,
            providerCode="openai",
            modelCode="maintenance-model",
        )

        suggestion = advisor.suggest(
            tenantId="tenant-1",
            evidence={
                "title": "Pump",
                "parts": [
                    {"name": "bearing", "lifecycleImpact": "minor", "quantity": "999"}
                ],
            },
        )

        self.assertEqual(suggestion.suggestedScope, "major")
        self.assertTrue(suggestion.requiresHumanConfirmation)
        self.assertEqual(caller.request.modelPolicy["provider"], "OPENAI")
        self.assertNotIn("quantity", caller.request.input["evidence"]["parts"][0])
        self.assertIn("quantity", caller.request.instructions.lower())

    def test_invalid_provider_output_falls_back_to_domain_rules(self) -> None:
        caller = FakeModelCaller(
            {"suggestedScope": "retire", "confidence": "high", "reasons": ["unsafe"]}
        )
        advisor = ConfiguredRepairScopeAIAdvisor(
            caller=caller,
            providerCode="LOCAL",
            modelCode="test-model",
        )

        self.assertIsNone(advisor.suggest(tenantId="tenant-2", evidence={"title": "test"}))

    def test_unconfigured_provider_is_a_clean_noop(self) -> None:
        advisor = ConfiguredRepairScopeAIAdvisor(providerCode="", modelCode="")

        self.assertIsNone(advisor.suggest(tenantId="tenant-3", evidence={"title": "test"}))


if __name__ == "__main__":
    unittest.main()
