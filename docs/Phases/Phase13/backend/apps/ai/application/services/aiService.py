from __future__ import annotations
import time, uuid
from django.utils import timezone
from apps.ai.domain.ports import AIProviderPort
from apps.ai.infrastructure.models import AIRequestModel,AIResponseModel,AIUsageModel,AIAuditRecordModel
class AIService:
    def __init__(self, provider:AIProviderPort): self.provider=provider
    def generate(self, *, tenantId, capability, requestedBy, prompt, model, providerModel, correlationId=None, systemInstruction='', outputClassification='ADVISORY', sourceDomain='', sourceEntityId=''):
        started=time.monotonic(); correlationId=correlationId or str(uuid.uuid4())
        req=AIRequestModel.objects.create(tenantId=tenantId,capability=capability,requestedBy=requestedBy,requestType='GENERATE',status='RUNNING',correlationId=correlationId,inputData={'prompt':prompt},sourceDomain=sourceDomain,sourceEntityId=sourceEntityId,startedAt=timezone.now())
        try:
            result=self.provider.generate(prompt=prompt,systemInstruction=systemInstruction,model=model.code)
            elapsed=int((time.monotonic()-started)*1000); req.status='COMPLETED'; req.completedAt=timezone.now(); req.save(update_fields=['status','completedAt'])
            response=AIResponseModel.objects.create(tenantId=tenantId,request=req,model=model, status='COMPLETED',content=result.content,structuredData=result.structuredData,inputTokens=result.inputTokens,outputTokens=result.outputTokens,totalTokens=result.inputTokens+result.outputTokens,latencyMs=elapsed,outputClassification=outputClassification)
            AIUsageModel.objects.create(tenantId=tenantId,request=req,provider=providerModel,model=model,inputTokens=result.inputTokens,outputTokens=result.outputTokens,totalTokens=result.inputTokens+result.outputTokens,totalTimeMs=elapsed)
            AIAuditRecordModel.objects.create(tenantId=tenantId,request=req,action='GENERATE',actorId=requestedBy,providerCode=providerModel.code,modelCode=model.code,resultClassification=outputClassification)
            return response
        except Exception as exc:
            req.status='FAILED'; req.errorCode=type(exc).__name__; req.completedAt=timezone.now(); req.save(update_fields=['status','errorCode','completedAt']); AIAuditRecordModel.objects.create(tenantId=tenantId,request=req,action='GENERATE_FAILED',actorId=requestedBy,metadata={'error':type(exc).__name__}); raise
