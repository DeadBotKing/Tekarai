"""Phase 13-N/O/P/Q/R/T Django persistence for metering, audit, queue,
embedding, knowledge, and memory ports."""

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
    "chunkToEntity",
    "counterToEntity",
    "embeddingToEntity",
    "governancePolicyToEntity",
    "jobToEntity",
    "memoryToEntity",
    "policyToEntity",
    "sourceToEntity",
    "spaceToEntity",
]
