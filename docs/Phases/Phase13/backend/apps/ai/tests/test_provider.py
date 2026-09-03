from apps.ai.domain.ports import DeterministicAIProvider
def test_deterministic_provider_is_offline_and_repeatable():
    p=DeterministicAIProvider(); a=p.generate(prompt='hello',model='test'); b=p.generate(prompt='hello',model='test')
    assert a==b and a.provider=='deterministic'
