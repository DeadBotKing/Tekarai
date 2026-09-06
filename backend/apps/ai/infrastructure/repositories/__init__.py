"""Phase 13-N/O/P/Q/R/T/U/V Django persistence for metering, audit, queue,
embedding, knowledge, memory, evaluation, and feedback ports."""

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
from apps.ai.infrastructure.repositories.queueRepositories import (  # noqa: F401
    DjangoJobStore,
    jobToEntity,
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
    "DjangoQuotaCounterStore",
    "DjangoQuotaPolicyStore",
    "DjangoRetentionPurger",
    "DjangoUsageAttemptStore",
    "DjangoVectorSpaceStore",
    "attemptToEntity",
    "auditToEntity",
    "caseToEntity",
    "chunkToEntity",
    "counterToEntity",
    "embeddingToEntity",
    "feedbackToEntity",
    "governancePolicyToEntity",
    "jobToEntity",
    "memoryToEntity",
    "policyToEntity",
    "resultToEntity",
    "runToEntity",
    "sourceToEntity",
    "spaceToEntity",
]
