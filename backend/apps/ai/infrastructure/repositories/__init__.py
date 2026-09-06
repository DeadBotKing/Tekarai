"""Phase 13-N/O/P/Q/R/T/U/V/W/X Django persistence for metering, audit, queue,
embedding, knowledge, memory, evaluation, feedback, observability, and tool
ports."""

from apps.ai.infrastructure.repositories.agentRepositories import (  # noqa: F401
    DjangoAgentApprovalStore,
    DjangoAgentDefinitionStore,
    DjangoAgentExecutionStore,
    stepToEntity,
)
from apps.ai.infrastructure.repositories.agentRepositories import (
    approvalToEntity as agentApprovalToEntity,
)
from apps.ai.infrastructure.repositories.agentRepositories import (
    definitionToEntity as agentDefinitionToEntity,
)
from apps.ai.infrastructure.repositories.agentRepositories import (
    runToEntity as agentRunToEntity,
)
from apps.ai.infrastructure.repositories.auditRepositories import (  # noqa: F401
    DjangoAuditRecordStore,
    DjangoGovernancePolicyStore,
    DjangoRetentionPurger,
    auditToEntity,
    governancePolicyToEntity,
)
from apps.ai.infrastructure.repositories.embeddingRepositories import (  # noqa: F401
    DjangoEmbeddingStore,
    DjangoVectorSpaceStore,
    embeddingToEntity,
    spaceToEntity,
)
from apps.ai.infrastructure.repositories.evaluationRepositories import (  # noqa: F401
    DjangoEvaluationCaseStore,
    DjangoEvaluationRunStore,
    caseToEntity,
    resultToEntity,
    runToEntity,
)
from apps.ai.infrastructure.repositories.feedbackRepositories import (  # noqa: F401
    DjangoFeedbackStore,
    feedbackToEntity,
)
from apps.ai.infrastructure.repositories.knowledgeRepositories import (  # noqa: F401
    DjangoKnowledgeChunkStore,
    DjangoKnowledgeSourceStore,
    chunkToEntity,
    sourceToEntity,
)
from apps.ai.infrastructure.repositories.memoryRepositories import (  # noqa: F401
    DjangoMemoryEntryStore,
    memoryToEntity,
)
from apps.ai.infrastructure.repositories.observabilityRepositories import (  # noqa: F401
    DjangoAlertEventStore,
    DjangoMetricSnapshotStore,
    alertToEntity,
    snapshotToEntity,
)
from apps.ai.infrastructure.repositories.queueRepositories import (  # noqa: F401
    DjangoJobStore,
    jobToEntity,
)
from apps.ai.infrastructure.repositories.toolRepositories import (  # noqa: F401
    DjangoToolApprovalStore,
    DjangoToolDefinitionStore,
    DjangoToolInvocationStore,
    approvalToEntity,
    definitionToEntity,
    invocationToEntity,
)
from apps.ai.infrastructure.repositories.usageRepositories import (  # noqa: F401
    DjangoCostRateResolver,
    DjangoQuotaCounterStore,
    DjangoQuotaPolicyStore,
    DjangoUsageAttemptStore,
    attemptToEntity,
    counterToEntity,
    policyToEntity,
)

__all__ = [
    "DjangoAgentApprovalStore",
    "DjangoAgentDefinitionStore",
    "DjangoAgentExecutionStore",
    "DjangoAlertEventStore",
    "DjangoAuditRecordStore",
    "DjangoCostRateResolver",
    "DjangoEmbeddingStore",
    "DjangoEvaluationCaseStore",
    "DjangoEvaluationRunStore",
    "DjangoFeedbackStore",
    "DjangoGovernancePolicyStore",
    "DjangoJobStore",
    "DjangoKnowledgeChunkStore",
    "DjangoKnowledgeSourceStore",
    "DjangoMemoryEntryStore",
    "DjangoMetricSnapshotStore",
    "DjangoQuotaCounterStore",
    "DjangoQuotaPolicyStore",
    "DjangoRetentionPurger",
    "DjangoToolApprovalStore",
    "DjangoToolDefinitionStore",
    "DjangoToolInvocationStore",
    "DjangoUsageAttemptStore",
    "DjangoVectorSpaceStore",
    "agentApprovalToEntity",
    "agentDefinitionToEntity",
    "agentRunToEntity",
    "agentStepToEntity",
    "alertToEntity",
    "approvalToEntity",
    "attemptToEntity",
    "auditToEntity",
    "caseToEntity",
    "chunkToEntity",
    "counterToEntity",
    "definitionToEntity",
    "embeddingToEntity",
    "feedbackToEntity",
    "governancePolicyToEntity",
    "invocationToEntity",
    "jobToEntity",
    "memoryToEntity",
    "policyToEntity",
    "resultToEntity",
    "runToEntity",
    "snapshotToEntity",
    "sourceToEntity",
    "spaceToEntity",
]
