from dataclasses import dataclass, field
from typing import Any, Protocol
@dataclass(frozen=True)
class GenerationResult:
    content:str=''; structuredData:dict[str,Any]=field(default_factory=dict); inputTokens:int=0; outputTokens:int=0; model:str=''; provider:str=''
class AIProviderPort(Protocol):
    def generate(self, *, prompt:str, systemInstruction:str='', model:str, temperature:float=0.0, **kwargs:Any)->GenerationResult: ...
    def embed(self, *, text:str, model:str, **kwargs:Any)->list[float]: ...
class DeterministicAIProvider:
    def generate(self, *, prompt:str, systemInstruction:str='', model:str='test', **kwargs:Any)->GenerationResult:
        return GenerationResult(content=f'[deterministic:{model}] {prompt}',inputTokens=len(prompt.split()),outputTokens=1,model=model,provider='deterministic')
    def embed(self, *, text:str, model:str='test', **kwargs:Any)->list[float]:
        return [float((sum(map(ord,text))+i)%997)/997 for i in range(8)]
