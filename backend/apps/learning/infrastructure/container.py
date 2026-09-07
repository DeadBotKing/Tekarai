"""Composition root for the Phase 16 Self-Learning Platform."""

from __future__ import annotations

from django.conf import settings

from apps.sharedKernel.infrastructure.wiring import importFromDottedPath, sharedKernelProvider


def kernelPorts():
    return {
        "unitOfWork": sharedKernelProvider("unitOfWork")(),
        "auditRecorder": sharedKernelProvider("auditRecorder")(),
        "eventDispatcher": sharedKernelProvider("eventDispatcher")(),
        "permissionGate": sharedKernelProvider("permissionGate")(),
        "clock": sharedKernelProvider("clock")(),
    }


def store():
    from apps.learning.infrastructure.persistence.learningStore import DjangoLearningStore

    return DjangoLearningStore()


def storage():
    from apps.learning.infrastructure.storage.artifactStorage import ImmutableArtifactStorage

    return ImmutableArtifactStorage()


def featureExtractor():
    from apps.learning.infrastructure.learning.signalExtractor import (
        DeterministicSignalExtractor,
    )

    return DeterministicSignalExtractor()


def learningEngine():
    dotted = getattr(
        settings,
        "LEARNING_ENGINE_IMPL",
        "apps.learning.infrastructure.learning.deterministicEngine.DeterministicLearningEngine",
    )
    return importFromDottedPath(dotted)()


def evaluationEngine():
    dotted = getattr(
        settings,
        "LEARNING_EVALUATION_IMPL",
        "apps.learning.infrastructure.evaluation.deterministicEvaluation.DeterministicEvaluationEngine",
    )
    return importFromDottedPath(dotted)()


def validationEngine():
    from apps.learning.infrastructure.evaluation.policyValidation import PolicyValidationEngine

    return PolicyValidationEngine()


def deploymentEngine():
    from apps.learning.infrastructure.deployment.safeDeployment import SafeDeploymentEngine

    return SafeDeploymentEngine()


def driftDetector():
    from apps.learning.infrastructure.monitoring.driftDetector import ThresholdDriftDetector

    return ThresholdDriftDetector()


def jobQueue():
    dotted = getattr(
        settings,
        "LEARNING_QUEUE_IMPL",
        "apps.learning.infrastructure.queue.learningQueue.CeleryLearningJobQueue",
    )
    return importFromDottedPath(dotted)()


def createExperienceService():
    from apps.learning.application.services.learningServices import CreateExperienceService

    return CreateExperienceService(store(), **kernelPorts())


def createDatasetService():
    from apps.learning.application.services.learningServices import CreateDatasetService

    return CreateDatasetService(store(), **kernelPorts())


def buildDatasetService():
    from apps.learning.application.services.learningServices import BuildDatasetService

    return BuildDatasetService(store(), **kernelPorts())


def validateDatasetService():
    from apps.learning.application.services.learningServices import ValidateDatasetService

    return ValidateDatasetService(store(), **kernelPorts())


def createExperimentService():
    from apps.learning.application.services.learningServices import CreateExperimentService

    return CreateExperimentService(store(), **kernelPorts())


def queueExperimentService():
    from apps.learning.application.services.learningServices import QueueExperimentService

    return QueueExperimentService(store(), jobQueue(), **kernelPorts())


def processJobService():
    from apps.learning.application.services.learningServices import ProcessLearningJobService

    return ProcessLearningJobService(
        store(),
        storage(),
        featureExtractor(),
        learningEngine(),
        kernelPorts()["clock"],
        codeVersion="0.16.0",
    )


def artifactLifecycleService():
    from apps.learning.application.services.learningServices import ArtifactLifecycleService

    return ArtifactLifecycleService(
        store(),
        storage(),
        evaluationEngine(),
        validationEngine(),
        deploymentEngine(),
        **kernelPorts(),
    )


def feedbackService():
    from apps.learning.application.services.learningServices import RecordFeedbackService

    return RecordFeedbackService(store(), **kernelPorts())


def monitoringService():
    from apps.learning.application.services.learningServices import MonitoringService

    return MonitoringService(store(), driftDetector(), **kernelPorts())


def queryService():
    from apps.learning.application.services.learningServices import LearningQueryService

    return LearningQueryService(store(), **kernelPorts())
