"""Documents context composition root (Phase 31)."""

from __future__ import annotations

from apps.documents.application.useCases import (
    DeleteDocumentUseCase,
    GetDocumentStreamUseCase,
    ListDocumentsUseCase,
    UploadDocumentUseCase,
)
from apps.documents.infrastructure.repositories.documentRepositoryImpl import (
    DocumentRepositoryImpl,
)
from apps.documents.infrastructure.storage import DocumentStorage
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider


def _kernelPorts() -> dict:
    return {
        "unitOfWork": sharedKernelProvider("unitOfWork")(),
        "auditRecorder": sharedKernelProvider("auditRecorder")(),
        "eventDispatcher": sharedKernelProvider("eventDispatcher")(),
        "permissionGate": sharedKernelProvider("permissionGate")(),
        "clock": sharedKernelProvider("clock")(),
    }


def documentRepository() -> DocumentRepositoryImpl:
    return DocumentRepositoryImpl()


def documentStorage() -> DocumentStorage:
    return DocumentStorage()


def listDocumentsUseCase() -> ListDocumentsUseCase:
    useCase = ListDocumentsUseCase(**_kernelPorts())
    useCase.repository = documentRepository()
    return useCase


def uploadDocumentUseCase() -> UploadDocumentUseCase:
    useCase = UploadDocumentUseCase(**_kernelPorts())
    useCase.repository = documentRepository()
    useCase.storage = documentStorage()
    return useCase


def downloadDocumentUseCase() -> GetDocumentStreamUseCase:
    useCase = GetDocumentStreamUseCase(**_kernelPorts())
    useCase.repository = documentRepository()
    useCase.storage = documentStorage()
    return useCase


def deleteDocumentUseCase() -> DeleteDocumentUseCase:
    useCase = DeleteDocumentUseCase(**_kernelPorts())
    useCase.repository = documentRepository()
    useCase.storage = documentStorage()
    return useCase
