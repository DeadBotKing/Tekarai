from apps.ai.domain.ports import DeterministicAIProvider
def testDeterministicProviderIsOfflineAndRepeatable():
    p=DeterministicAIProvider(); a=p.generate(prompt='hello',model='test'); b=p.generate(prompt='hello',model='test')
    assert a==b and a.provider=='deterministic'
