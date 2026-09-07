"""Django adapter implementing all Project Intelligence repository ports."""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db import transaction
from django.forms.models import model_to_dict

from apps.projectIntelligence.domain.entities.intelligenceRecords import (
    ProjectState,
)
from apps.projectIntelligence.domain.valueObjects.intelligenceTypes import integrityHash
from apps.projectIntelligence.infrastructure.persistence import models as m


def dto(obj) -> dict:
    data = model_to_dict(obj)
    for key, value in list(data.items()):
        if isinstance(value, uuid.UUID):
            data[key] = str(value)
        elif isinstance(value, datetime):
            data[key] = value.isoformat()
    data["id"] = str(obj.id)
    data["createdAt"] = obj.createdAt.isoformat() if obj.createdAt else None
    return data


class DjangoIntelligenceStore:
    def nextSnapshotVersion(self, tenantId, projectId):
        latest = (
            m.ProjectSnapshotModel.objects.filter(tenantId=tenantId, projectId=projectId)
            .order_by("-version")
            .first()
        )
        return 1 + (latest.version if latest else 0)

    def saveSnapshot(self, s):
        m.ProjectSnapshotModel.objects.create(
            id=s.id,
            tenantId=s.tenantId,
            projectId=s.projectId,
            version=s.version,
            workspace=s.workspace,
            analysisVersion=s.analysisVersion,
            snapshotHash=s.snapshotHash,
            artifactUri=s.artifactUri,
            artifactChecksum=s.snapshotHash,
            environment=s.environment,
            gitState=s.gitState,
            fileCount=len(s.files),
        )

    @transaction.atomic
    def saveSnapshotBundle(self, snapshot):
        self.saveSnapshot(snapshot)
        self.saveFiles(snapshot)

    def saveFiles(self, s):
        m.ProjectFileModel.objects.bulk_create(
            [
                m.ProjectFileModel(
                    tenantId=s.tenantId,
                    snapshotId=s.id,
                    projectId=s.projectId,
                    path=f["path"],
                    fileType=f["extension"] or "unknown",
                    size=f["size"],
                    modifiedNs=f["modifiedNs"],
                    binary=f["binary"],
                    generated=f["generated"],
                    ignored=f["ignored"],
                    temporary=f["temporary"],
                    metadata={"mime": f["mime"], "loc": f["loc"], "secretNamed": f["secretNamed"]},
                )
                for f in s.files
            ]
        )
        m.ProjectFileHashModel.objects.bulk_create(
            [
                m.ProjectFileHashModel(
                    tenantId=s.tenantId,
                    snapshotId=s.id,
                    projectId=s.projectId,
                    path=f["path"],
                    fileHash=f["hash"],
                )
                for f in s.files
            ]
        )

    def latestSnapshot(self, tenantId, projectId):
        obj = (
            m.ProjectSnapshotModel.objects.filter(tenantId=tenantId, projectId=projectId)
            .order_by("-version")
            .first()
        )
        if not obj:
            return None
        data = dto(obj)
        files = []
        hashes = {
            x.path: x.fileHash
            for x in m.ProjectFileHashModel.objects.filter(tenantId=tenantId, snapshotId=obj.id)
        }
        for f in m.ProjectFileModel.objects.filter(tenantId=tenantId, snapshotId=obj.id).order_by(
            "path"
        ):
            files.append(
                {
                    "path": f.path,
                    "extension": f.fileType if f.fileType != "unknown" else "",
                    "size": f.size,
                    "modifiedNs": f.modifiedNs,
                    "hash": hashes.get(f.path, ""),
                    "binary": f.binary,
                    "generated": f.generated,
                    "ignored": f.ignored,
                    "temporary": f.temporary,
                    **f.metadata,
                    "content": "",
                }
            )
        data["files"] = files
        return data

    def snapshotById(self, tenantId, projectId, snapshotId):
        obj = m.ProjectSnapshotModel.objects.filter(
            tenantId=tenantId, projectId=projectId, id=snapshotId
        ).first()
        if not obj:
            return None
        data = dto(obj)
        hashes = {
            x.path: x.fileHash
            for x in m.ProjectFileHashModel.objects.filter(tenantId=tenantId, snapshotId=obj.id)
        }
        data["files"] = [
            {"path": x.path, "hash": hashes.get(x.path, "")}
            for x in m.ProjectFileModel.objects.filter(
                tenantId=tenantId, snapshotId=obj.id
            ).order_by("path")
        ]
        return data

    @transaction.atomic
    def saveAnalysis(self, tenantId, projectId, snapshotId, data):
        version = (
            1
            + m.ProjectAnalysisModel.objects.filter(tenantId=tenantId, projectId=projectId).count()
        )
        obj = m.ProjectAnalysisModel.objects.create(
            tenantId=tenantId,
            projectId=projectId,
            snapshotId=snapshotId,
            version=version,
            status=data["status"],
            analysisHash=data["analysisHash"],
            startedAt=data["startedAt"],
            completedAt=data.get("completedAt"),
            incremental=data.get("incremental", False),
            affectedFiles=data.get("affectedFiles", []),
            metrics=data.get("metrics", {}),
        )
        for result in data["results"]:
            m.ProjectAnalysisResultModel.objects.create(
                tenantId=tenantId,
                analysisId=obj.id,
                projectId=projectId,
                analyzerName=result["analyzerName"],
                analyzerVersion=result["analyzerVersion"],
                status=result["status"],
                findings=result["findings"],
                metrics=result["metrics"],
                errors=result["errors"],
                metadata=result["metadata"],
                resultHash=result["resultHash"],
            )
            if result["analyzerName"] == "dependency":
                deps = [x["edge"] for x in result["findings"] if x.get("type") == "DEPENDENCY"]
                m.ProjectDependencyModel.objects.bulk_create(
                    [
                        m.ProjectDependencyModel(
                            tenantId=tenantId,
                            analysisId=obj.id,
                            projectId=projectId,
                            source=x["source"],
                            target=x["target"],
                            dependencyType=x["kind"],
                            metadata={},
                        )
                        for x in deps
                    ]
                )
            if result["analyzerName"] == "architecture":
                m.ProjectArchitectureModel.objects.create(
                    tenantId=tenantId,
                    analysisId=obj.id,
                    projectId=projectId,
                    version=version,
                    model={"findings": result["findings"], "metrics": result["metrics"]},
                    violationCount=result["metrics"].get("architectureViolations", 0),
                    architectureHash=result["resultHash"],
                )
        return dto(obj)

    @transaction.atomic
    def saveKnowledge(self, tenantId, projectId, analysisId, data):
        version = (
            1
            + m.ProjectKnowledgeModel.objects.filter(tenantId=tenantId, projectId=projectId).count()
        )
        obj = m.ProjectKnowledgeModel.objects.create(
            tenantId=tenantId,
            projectId=projectId,
            analysisId=analysisId,
            snapshotId=data["snapshotId"],
            version=version,
            knowledge=data["knowledge"],
            knowledgeHash=data["knowledgeHash"],
        )
        m.ProjectKnowledgeNodeModel.objects.bulk_create(
            [
                m.ProjectKnowledgeNodeModel(
                    tenantId=tenantId,
                    knowledgeId=obj.id,
                    projectId=projectId,
                    nodeKey=n["key"],
                    nodeType=n["type"],
                    properties=n.get("properties", {}),
                )
                for n in data["nodes"]
            ]
        )
        m.ProjectKnowledgeEdgeModel.objects.bulk_create(
            [
                m.ProjectKnowledgeEdgeModel(
                    tenantId=tenantId,
                    knowledgeId=obj.id,
                    projectId=projectId,
                    sourceKey=e["source"],
                    targetKey=e["target"],
                    edgeType=e["type"],
                    properties=e.get("properties", {}),
                )
                for e in data["edges"]
            ]
        )
        return dto(obj)

    def saveInsights(self, tenantId, projectId, knowledgeId, items):
        out = []
        for x in items:
            obj = m.ProjectInsightModel.objects.create(
                tenantId=tenantId,
                projectId=projectId,
                knowledgeId=knowledgeId,
                kind=x["kind"],
                title=x["title"],
                severity=x["severity"],
                confidence=x["confidence"],
                evidence=x["evidence"],
                source=x["source"],
                impact=x["impact"],
            )
            out.append(dto(obj))
        return out

    def saveRecommendations(self, tenantId, projectId, items):
        out = []
        for x in items:
            version = (
                1
                + m.ProjectRecommendationModel.objects.filter(
                    tenantId=tenantId, insightId=x["insightId"]
                ).count()
            )
            obj = m.ProjectRecommendationModel.objects.create(
                tenantId=tenantId, projectId=projectId, version=version, **x
            )
            out.append(dto(obj))
        return out

    def saveDecisions(self, tenantId, projectId, items):
        out = []
        for x in items:
            version = (
                1
                + m.ProjectDecisionModel.objects.filter(
                    tenantId=tenantId, recommendationId=x["recommendationId"]
                ).count()
            )
            obj = m.ProjectDecisionModel.objects.create(
                tenantId=tenantId, projectId=projectId, version=version, **x
            )
            out.append(dto(obj))
        return out

    def saveContext(self, tenantId, projectId, data):
        version = (
            1
            + m.ProjectContextPackageModel.objects.filter(
                tenantId=tenantId, projectId=projectId
            ).count()
        )
        obj = m.ProjectContextPackageModel.objects.create(
            tenantId=tenantId, projectId=projectId, version=version, **data
        )
        return dto(obj)

    def getOrCreateState(self, tenantId, projectId, now):
        obj, _ = m.ProjectStateModel.objects.get_or_create(
            tenantId=tenantId,
            projectId=projectId,
            defaults={"status": "INITIALIZING", "updatedAt": now},
        )
        return ProjectState(
            obj.id,
            obj.tenantId,
            obj.projectId,
            obj.status,
            obj.updatedAt,
            obj.snapshotId,
            obj.error,
        )

    def saveState(self, state):
        m.ProjectStateModel.objects.filter(id=state.id, tenantId=state.tenantId).update(
            status=state.status,
            updatedAt=state.updatedAt,
            snapshotId=state.snapshotId,
            error=state.error,
        )

    def saveChanges(self, tenantId, projectId, fromId, toId, data):
        obj = m.ProjectChangeModel.objects.create(
            tenantId=tenantId, projectId=projectId, fromSnapshotId=fromId, toSnapshotId=toId, **data
        )
        return dto(obj)

    def saveResume(self, tenantId, projectId, data):
        version = (
            1 + m.ProjectResumeModel.objects.filter(tenantId=tenantId, projectId=projectId).count()
        )
        obj = m.ProjectResumeModel.objects.create(
            tenantId=tenantId, projectId=projectId, version=version, **data
        )
        return dto(obj)

    def createJob(self, tenantId, projectId, actorId, data):
        obj, created = m.IntelligenceJobModel.objects.get_or_create(
            tenantId=tenantId,
            projectId=projectId,
            idempotencyKey=data["idempotencyKey"],
            defaults={
                "actorId": actorId,
                "jobType": data["jobType"],
                "status": "QUEUED",
                "priority": data.get("priority", 5),
                "metadata": data.get("metadata", {}),
            },
        )
        result = dto(obj)
        result["created"] = created
        return result

    @transaction.atomic
    def claimJob(self, jobId, now):
        obj = (
            m.IntelligenceJobModel.objects.select_for_update()
            .filter(id=jobId, status="QUEUED")
            .first()
        )
        if not obj:
            return None
        obj.status = "RUNNING"
        obj.startedAt = now
        obj.save(update_fields=["status", "startedAt"])
        return dto(obj)

    def finishJob(self, jobId, now, *, result=None, error=""):
        obj = m.IntelligenceJobModel.objects.get(id=jobId)
        obj.status = "FAILED" if error else "COMPLETED"
        obj.completedAt = now
        obj.error = error[:2000]
        obj.result = result or {}
        obj.save(update_fields=["status", "completedAt", "error", "result"])
        return dto(obj)

    def retryJob(self, jobId, errorType):
        obj = m.IntelligenceJobModel.objects.get(id=jobId)
        obj.status = "QUEUED"
        obj.retryCount += 1
        obj.error = f"Transient {errorType}; retry scheduled."
        obj.save(update_fields=["status", "retryCount", "error"])
        return dto(obj)

    def getJob(self, tenantId, jobId):
        obj = m.IntelligenceJobModel.objects.filter(tenantId=tenantId, id=jobId).first()
        return dto(obj) if obj else None

    def projectData(self, tenantId, projectId, kind):
        mapping = {
            "state": m.ProjectStateModel,
            "snapshots": m.ProjectSnapshotModel,
            "analyses": m.ProjectAnalysisModel,
            "architecture": m.ProjectArchitectureModel,
            "dependencies": m.ProjectDependencyModel,
            "knowledge": m.ProjectKnowledgeModel,
            "insights": m.ProjectInsightModel,
            "recommendations": m.ProjectRecommendationModel,
            "decisions": m.ProjectDecisionModel,
            "context": m.ProjectContextPackageModel,
            "changes": m.ProjectChangeModel,
            "resume": m.ProjectResumeModel,
        }
        model = mapping[kind]
        qs = model.objects.filter(tenantId=tenantId, projectId=projectId).order_by("-createdAt")
        if kind in ("state", "architecture", "knowledge", "context", "resume"):
            obj = qs.first()
            return dto(obj) if obj else None
        return [dto(x) for x in qs[:500]]

    def audit(self, tenantId, actorId, projectId, action, metadata):
        m.IntelligenceAuditModel.objects.create(
            tenantId=tenantId,
            actorId=actorId,
            projectId=projectId,
            action=action,
            metadata=metadata,
        )

    def event(self, tenantId, projectId, eventType, payload):
        m.IntelligenceEventModel.objects.create(
            tenantId=tenantId,
            projectId=projectId,
            eventType=eventType,
            payload=payload,
            eventHash=integrityHash({"eventType": eventType, "payload": payload}),
        )
