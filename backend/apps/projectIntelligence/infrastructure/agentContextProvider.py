"""Authorized bridge from Project Intelligence packages to the AI/Agent context engine."""

from __future__ import annotations

import json
import uuid

from apps.projectIntelligence.application.dto.agentContext import ProjectContextSource
from apps.projectIntelligence.infrastructure.persistence.models import ProjectContextPackageModel
from apps.sharedKernel.domain.errors import EntityNotFoundError


class ProjectIntelligenceAgentContextProvider:
    def latest(self, tenantId: uuid.UUID, projectId: uuid.UUID) -> ProjectContextSource:
        package = (
            ProjectContextPackageModel.objects.filter(tenantId=tenantId, projectId=projectId)
            .order_by("-version")
            .first()
        )
        if not package:
            raise EntityNotFoundError("Project context package not found.")
        return ProjectContextSource(
            tenantId=tenantId,
            sourceDomain="projectIntelligence",
            sourceEntityType="ProjectContextPackage",
            sourceEntityId=str(package.id),
            content=json.dumps(package.package, sort_keys=True, ensure_ascii=False),
            classification="INTERNAL",
            authorized=True,
            metadata={
                "projectId": str(projectId),
                "snapshotId": str(package.snapshotId),
                "knowledgeId": str(package.knowledgeId),
                "contextHash": package.contextHash,
                "version": package.version,
            },
        )
