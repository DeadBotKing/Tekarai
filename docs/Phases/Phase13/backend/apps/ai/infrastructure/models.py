from __future__ import annotations
import uuid
from django.db import models

class BaseAiModel(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    tenantId=models.UUIDField(db_index=True)
    createdAt=models.DateTimeField(auto_now_add=True); updatedAt=models.DateTimeField(auto_now=True)
    class Meta: abstract=True

class AIProviderModel(BaseAiModel):
    code=models.CharField(max_length=80); name=models.CharField(max_length=160); providerType=models.CharField(max_length=40)
    configurationReference=models.CharField(max_length=255,blank=True); isActive=models.BooleanField(default=True); metadata=models.JSONField(default=dict,blank=True)
    class Meta: db_table='aiProviders'; unique_together=[('tenantId','code')]
class AIModelModel(BaseAiModel):
    provider=models.ForeignKey(AIProviderModel,on_delete=models.PROTECT,related_name='models'); code=models.CharField(max_length=120); name=models.CharField(max_length=160); modelType=models.CharField(max_length=40,default='LLM'); version=models.CharField(max_length=80,blank=True); contextWindow=models.PositiveIntegerField(default=8192); inputCapability=models.JSONField(default=list); outputCapability=models.JSONField(default=list); supportsStreaming=models.BooleanField(default=False); supportsTools=models.BooleanField(default=False); supportsEmbeddings=models.BooleanField(default=False); supportsVision=models.BooleanField(default=False); isActive=models.BooleanField(default=True); metadata=models.JSONField(default=dict,blank=True)
    class Meta: db_table='aiModels'; unique_together=[('tenantId','code','version')]
class AICapabilityModel(BaseAiModel):
    code=models.CharField(max_length=100); name=models.CharField(max_length=160); description=models.TextField(blank=True); isActive=models.BooleanField(default=True); policy=models.JSONField(default=dict,blank=True)
    class Meta: db_table='aiCapabilities'; unique_together=[('tenantId','code')]
class AIPromptModel(BaseAiModel):
    code=models.CharField(max_length=160); name=models.CharField(max_length=160); description=models.TextField(blank=True); isActive=models.BooleanField(default=True)
    class Meta: db_table='aiPrompts'; unique_together=[('tenantId','code')]
class AIPromptVersionModel(BaseAiModel):
    prompt=models.ForeignKey(AIPromptModel,on_delete=models.PROTECT,related_name='versions'); version=models.PositiveIntegerField(); template=models.TextField(); systemInstruction=models.TextField(blank=True); variables=models.JSONField(default=list); outputSchema=models.JSONField(default=dict,blank=True); modelConstraints=models.JSONField(default=dict,blank=True); createdBy=models.UUIDField(null=True); isActive=models.BooleanField(default=False)
    class Meta: db_table='aiPromptVersions'; unique_together=[('prompt','version')]
class AIRequestModel(BaseAiModel):
    capability=models.ForeignKey(AICapabilityModel,on_delete=models.PROTECT); requestedBy=models.UUIDField(null=True); requestType=models.CharField(max_length=40); sourceDomain=models.CharField(max_length=100,blank=True); sourceEntityType=models.CharField(max_length=100,blank=True); sourceEntityId=models.CharField(max_length=100,blank=True); priority=models.CharField(max_length=20,default='NORMAL'); status=models.CharField(max_length=30,default='PENDING'); correlationId=models.CharField(max_length=128,db_index=True); traceId=models.CharField(max_length=128,blank=True); parentRequestId=models.UUIDField(null=True); inputData=models.JSONField(default=dict); startedAt=models.DateTimeField(null=True); completedAt=models.DateTimeField(null=True); errorCode=models.CharField(max_length=80,blank=True); idempotencyKey=models.CharField(max_length=160,blank=True)
    class Meta: db_table='aiRequests'; indexes=[models.Index(fields=['tenantId','status','createdAt'])]
class AIResponseModel(BaseAiModel):
    request=models.OneToOneField(AIRequestModel,on_delete=models.PROTECT,related_name='response'); model=models.ForeignKey(AIModelModel,on_delete=models.PROTECT); status=models.CharField(max_length=30); content=models.TextField(blank=True); structuredData=models.JSONField(default=dict,blank=True); inputTokens=models.PositiveIntegerField(default=0); outputTokens=models.PositiveIntegerField(default=0); totalTokens=models.PositiveIntegerField(default=0); latencyMs=models.PositiveIntegerField(default=0); outputClassification=models.CharField(max_length=30,default='ADVISORY'); promptVersion=models.ForeignKey(AIPromptVersionModel,null=True,on_delete=models.PROTECT); createdAt=models.DateTimeField(auto_now_add=True)
    class Meta: db_table='aiResponses'
class AIUsageModel(BaseAiModel):
    request=models.OneToOneField(AIRequestModel,on_delete=models.PROTECT); provider=models.ForeignKey(AIProviderModel,on_delete=models.PROTECT); model=models.ForeignKey(AIModelModel,on_delete=models.PROTECT); inputTokens=models.PositiveIntegerField(default=0); outputTokens=models.PositiveIntegerField(default=0); totalTokens=models.PositiveIntegerField(default=0); estimatedCost=models.DecimalField(max_digits=18,decimal_places=8,default=0); currency=models.CharField(max_length=3,default='USD'); queueTimeMs=models.PositiveIntegerField(default=0); contextBuildTimeMs=models.PositiveIntegerField(default=0); providerTimeMs=models.PositiveIntegerField(default=0); validationTimeMs=models.PositiveIntegerField(default=0); totalTimeMs=models.PositiveIntegerField(default=0)
    class Meta: db_table='aiUsage'
class AIFeedbackModel(BaseAiModel):
    request=models.ForeignKey(AIRequestModel,on_delete=models.PROTECT); response=models.ForeignKey(AIResponseModel,on_delete=models.PROTECT); userId=models.UUIDField(null=True); rating=models.PositiveSmallIntegerField(null=True); sentiment=models.CharField(max_length=20,blank=True); correction=models.TextField(blank=True); comment=models.TextField(blank=True)
    class Meta: db_table='aiFeedback'
class AIMemoryModel(BaseAiModel):
    userId=models.UUIDField(null=True); scope=models.CharField(max_length=40); key=models.CharField(max_length=160); value=models.JSONField(); version=models.PositiveIntegerField(default=1); isActive=models.BooleanField(default=True); expiresAt=models.DateTimeField(null=True)
    class Meta: db_table='aiMemory'; unique_together=[('tenantId','scope','key','version')]
class AIKnowledgeItemModel(BaseAiModel):
    sourceDomain=models.CharField(max_length=100); sourceEntityType=models.CharField(max_length=100); sourceEntityId=models.CharField(max_length=160); title=models.CharField(max_length=300); content=models.TextField(); classification=models.CharField(max_length=30,default='INTERNAL'); checksum=models.CharField(max_length=128); status=models.CharField(max_length=30,default='PENDING'); metadata=models.JSONField(default=dict)
    class Meta: db_table='aiKnowledgeItems'; unique_together=[('tenantId','sourceDomain','sourceEntityId','checksum')]
class AIKnowledgeChunkModel(BaseAiModel):
    item=models.ForeignKey(AIKnowledgeItemModel,on_delete=models.CASCADE,related_name='chunks'); ordinal=models.PositiveIntegerField(); content=models.TextField(); embedding=models.JSONField(null=True); tokenCount=models.PositiveIntegerField(default=0); metadata=models.JSONField(default=dict)
    class Meta: db_table='aiKnowledgeChunks'; unique_together=[('item','ordinal')]
class AIAuditRecordModel(BaseAiModel):
    request=models.ForeignKey(AIRequestModel,on_delete=models.PROTECT); action=models.CharField(max_length=60); actorId=models.UUIDField(null=True); providerCode=models.CharField(max_length=100,blank=True); modelCode=models.CharField(max_length=160,blank=True); promptVersion=models.CharField(max_length=80,blank=True); contextSources=models.JSONField(default=list); resultClassification=models.CharField(max_length=30,blank=True); metadata=models.JSONField(default=dict); redacted=models.BooleanField(default=True)
    class Meta: db_table='aiAuditRecords'
