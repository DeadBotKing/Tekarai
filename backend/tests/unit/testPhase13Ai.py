from django.test import SimpleTestCase
from apps.ai.domain.ports import DeterministicAIProvider

class Phase13AiProviderTests(SimpleTestCase):
    def testDeterministicProviderIsOfflineAndRepeatable(self):
        provider = DeterministicAIProvider()
        first = provider.generate(prompt="hello", model="test")
        second = provider.generate(prompt="hello", model="test")
        self.assertEqual(first, second)
        self.assertEqual(first.provider, "deterministic")

    def testEmbeddingIsDeterministic(self):
        provider = DeterministicAIProvider()
        self.assertEqual(provider.embed(text="hello"), provider.embed(text="hello"))
        self.assertEqual(len(provider.embed(text="hello")), 8)
