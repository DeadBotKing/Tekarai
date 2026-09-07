"""Composition root for Phase 17."""

from pathlib import Path

from django.conf import settings

from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider


def kernel():
    return {
        "unitOfWork": sharedKernelProvider("unitOfWork")(),
        "auditRecorder": sharedKernelProvider("auditRecorder")(),
        "eventDispatcher": sharedKernelProvider("eventDispatcher")(),
        "permissionGate": sharedKernelProvider("permissionGate")(),
        "clock": sharedKernelProvider("clock")(),
    }


def store():
    from apps.projectIntelligence.infrastructure.persistence.intelligenceStore import (
        DjangoIntelligenceStore,
    )

    return DjangoIntelligenceStore()


def workspace():
    from apps.projectIntelligence.infrastructure.filesystem.secureWorkspace import (
        SecureWorkspaceReader,
    )

    return SecureWorkspaceReader(
        Path(settings.PROJECT_INTELLIGENCE_WORKSPACE_ROOT),
        settings.PROJECT_INTELLIGENCE_MAX_FILES,
        settings.PROJECT_INTELLIGENCE_MAX_FILE_BYTES,
    )


def gitReader():
    from apps.projectIntelligence.infrastructure.git.gitReader import ReadOnlyGitReader

    return ReadOnlyGitReader()


def storage():
    from apps.projectIntelligence.infrastructure.storage.snapshotStorage import (
        ImmutableSnapshotStorage,
    )

    return ImmutableSnapshotStorage()


def analyzers():
    from apps.projectIntelligence.infrastructure.analyzers.builtinAnalyzers import BUILTIN_ANALYZERS

    return tuple(x() for x in BUILTIN_ANALYZERS)


def cacheFactory(tenantId):
    from apps.projectIntelligence.infrastructure.cache.analysisCache import DjangoAnalysisCache

    return DjangoAnalysisCache(tenantId, settings.PROJECT_INTELLIGENCE_CACHE_TTL_SECONDS)


def queue():
    from apps.projectIntelligence.infrastructure.queue.intelligenceQueue import (
        CeleryIntelligenceJobQueue,
    )

    return CeleryIntelligenceJobQueue()


def pipeline():
    from apps.projectIntelligence.application.services.intelligenceServices import (
        IntelligencePipeline,
    )

    return IntelligencePipeline(
        store(), workspace(), gitReader(), storage(), analyzers(), cacheFactory, kernel()["clock"]
    )


def snapshotService():
    from apps.projectIntelligence.application.services.intelligenceServices import SnapshotService

    return SnapshotService(pipeline(), **kernel())


def queueService():
    from apps.projectIntelligence.application.services.intelligenceServices import (
        QueueAnalysisService,
    )

    return QueueAnalysisService(store(), queue(), **kernel())


def processJobService():
    from apps.projectIntelligence.application.services.intelligenceServices import ProcessJobService

    return ProcessJobService(store(), pipeline(), kernel()["clock"])


def contextService():
    from apps.projectIntelligence.application.services.intelligenceServices import (
        BuildContextService,
    )

    return BuildContextService(pipeline(), **kernel())


def queryService():
    from apps.projectIntelligence.application.services.intelligenceServices import QueryService

    return QueryService(store(), **kernel())


def compareService():
    from apps.projectIntelligence.application.services.intelligenceServices import (
        CompareSnapshotsService,
    )

    return CompareSnapshotsService(store(), **kernel())


def jobQueryService():
    from apps.projectIntelligence.application.services.intelligenceServices import JobQueryService

    return JobQueryService(store(), **kernel())
