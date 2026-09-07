"""Governed Phase 17 pipeline and use cases."""

from __future__ import annotations

import platform
import uuid
from datetime import datetime

from apps.projectIntelligence.domain.entities.intelligenceRecords import ProjectSnapshot
from apps.projectIntelligence.domain.services.intelligenceEngines import (
    ChangeDetector,
    ContextBuilder,
    DecisionEngine,
    InsightEngine,
    KnowledgeBuilder,
    RecommendationEngine,
    ResumeGenerator,
)
from apps.projectIntelligence.domain.valueObjects import intelligenceTypes as t
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import UseCase
from apps.sharedKernel.domain.errors import (
    ConflictError,
    EntityNotFoundError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid


def contextIds() -> tuple[uuid.UUID, uuid.UUID]:
    c = currentContext()
    return asUuid(c.actorId), asUuid(c.actorTenantId)


def serial(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [serial(x) for x in value]
    if isinstance(value, list):
        return [serial(x) for x in value]
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    return value


def snapshotDto(s: ProjectSnapshot) -> dict:
    return serial({k: v for k, v in vars(s).items() if not k.startswith("_")})


class IntelligencePipeline:
    version = "1.0.0"

    def __init__(self, store, workspace, git, storage, analyzers, cacheFactory, clock):
        self.store = store
        self.workspace = workspace
        self.git = git
        self.storage = storage
        self.analyzers = analyzers
        self.cacheFactory = cacheFactory
        self.clock = clock
        self.changes = ChangeDetector()
        self.knowledge = KnowledgeBuilder()
        self.insights = InsightEngine()
        self.recommendations = RecommendationEngine()
        self.decisions = DecisionEngine()
        self.context = ContextBuilder()
        self.resume = ResumeGenerator()

    def createSnapshot(self, tenantId, actorId, projectId, relativeWorkspace):
        relativeWorkspace = t.safeRelativePath(relativeWorkspace)
        previous = self.store.latestSnapshot(tenantId, projectId)
        if previous and previous["workspace"] != relativeWorkspace:
            raise ConflictError("A project is permanently bound to its original workspace.")
        now = self.clock.nowUtc()
        state = self.store.getOrCreateState(tenantId, projectId, now)
        if state.status in ("READY", "CHANGED", "STALE", "ERROR"):
            state.moveTo("SCANNING", now)
        elif state.status == "INITIALIZING":
            state.moveTo("SCANNING", now)
        self.store.saveState(state)
        try:
            base = self.workspace.resolve(relativeWorkspace)
            previousFiles = ()
            if previous:
                if not self.storage.verify(previous["artifactUri"], previous["snapshotHash"]):
                    raise ConflictError("Previous snapshot artifact failed integrity verification.")
                previousFiles = tuple(self.storage.load(previous["artifactUri"])["files"])
            files = self.workspace.scan(relativeWorkspace, previousFiles)
            gitState = self.git.inspect(base)
        except Exception as exc:
            state.moveTo("ERROR", now, error=f"{type(exc).__name__}: {exc}")
            self.store.saveState(state)
            self.store.audit(
                tenantId, actorId, projectId, "SNAPSHOT_FAILED", {"errorType": type(exc).__name__}
            )
            self.store.event(
                tenantId,
                projectId,
                "ProjectAnalysisFailed",
                {"stage": "SNAPSHOT", "errorType": type(exc).__name__},
            )
            raise
        version = self.store.nextSnapshotVersion(tenantId, projectId)
        environment = {"python": platform.python_version(), "platform": platform.system()}
        snapshot = ProjectSnapshot.create(
            tenantId,
            projectId,
            version,
            relativeWorkspace,
            files,
            gitState,
            environment,
            self.version,
            now,
        )
        if previous and previous["snapshotHash"] == snapshot.snapshotHash:
            if state.status != "ANALYZING":
                state.moveTo("ANALYZING", now)
            state.moveTo("READY", now, snapshotId=asUuid(previous["id"]))
            self.store.saveState(state)
            previous["unchanged"] = True
            return previous, previous
        payload = {
            "projectId": str(projectId),
            "workspace": relativeWorkspace,
            "files": files,
            "gitState": gitState,
            "environment": environment,
            "analysisVersion": self.version,
        }
        uri, checksum = self.storage.put(tenantId, projectId, snapshot.id, payload)
        if checksum != snapshot.snapshotHash:
            raise ConflictError("Snapshot artifact integrity mismatch.")
        snapshot.artifactUri = uri
        self.store.saveSnapshotBundle(snapshot)
        data = snapshotDto(snapshot)
        change = self.changes.compare(previous, data)
        self.store.saveChanges(
            tenantId, projectId, asUuid(previous["id"]) if previous else None, snapshot.id, change
        )
        if previous and any(change[key] for key in ("added", "modified", "deleted", "renamed")):
            state.moveTo("CHANGED", now, snapshotId=snapshot.id)
            self.store.saveState(state)
            self.store.event(
                tenantId,
                projectId,
                "ProjectChanged",
                {"snapshotId": str(snapshot.id), "changeHash": change["changeHash"]},
            )
        state.moveTo("ANALYZING", now, snapshotId=snapshot.id)
        state.moveTo("READY", now, snapshotId=snapshot.id)
        self.store.saveState(state)
        self.store.audit(
            tenantId,
            actorId,
            projectId,
            "SNAPSHOT",
            {"snapshotId": str(snapshot.id), "hash": snapshot.snapshotHash},
        )
        self.store.event(
            tenantId,
            projectId,
            "ProjectSnapshotCreated",
            {"snapshotId": str(snapshot.id), "version": version},
        )
        return data, previous

    def analyzerFingerprint(self, analyzerName: str, snapshot: dict) -> str:
        files = snapshot["files"]
        if analyzerName == "git":
            evidence = snapshot["gitState"]
        else:
            predicates = {
                "documentation": lambda f: (
                    f["extension"] in (".md", ".rst", ".txt")
                    or f["name"].lower().startswith("readme")
                ),
                "configuration": lambda f: (
                    f["extension"] in (".toml", ".yaml", ".yml", ".json")
                    or f["name"].lower().startswith(("requirements", "dockerfile"))
                ),
                "test": lambda f: "test" in f["path"].lower(),
                "language": lambda f: bool(f["extension"]),
                "dependency": lambda f: (
                    f["extension"] in (".py", ".js", ".jsx", ".ts", ".tsx")
                    or f["name"].lower() in ("package.json", "requirements.txt", "pyproject.toml")
                ),
                "architecture": lambda f: f["extension"] in (".py", ".js", ".jsx", ".ts", ".tsx"),
                "framework": lambda f: not f["binary"],
                "filesystem": lambda f: True,
            }
            predicate = predicates.get(analyzerName, lambda f: True)
            evidence = [(f["path"], f["hash"]) for f in files if predicate(f)]
        return t.integrityHash(evidence)

    def run(self, tenantId, actorId, projectId, relativeWorkspace, incremental=False):
        started = self.clock.nowUtc()
        snapshot, previous = self.createSnapshot(tenantId, actorId, projectId, relativeWorkspace)
        if snapshot.get("unchanged"):
            latest = self.store.projectData(tenantId, projectId, "knowledge")
            if latest:
                return {
                    "snapshot": snapshot,
                    "analysis": None,
                    "knowledge": latest,
                    "unchanged": True,
                }
            artifact = self.storage.load(snapshot["artifactUri"])
            artifact.update(
                {
                    key: snapshot[key]
                    for key in ("id", "version", "snapshotHash", "createdAt", "artifactUri")
                }
            )
            snapshot = artifact
        analysisState = self.store.getOrCreateState(tenantId, projectId, started)
        if analysisState.status != "ANALYZING":
            if analysisState.status != "SCANNING":
                analysisState.moveTo("SCANNING", started)
            analysisState.moveTo("ANALYZING", started)
            self.store.saveState(analysisState)
        changed = self.changes.compare(previous, snapshot)
        affected = changed["added"] + changed["modified"] + changed["deleted"]
        cache = self.cacheFactory(tenantId)
        self.store.event(
            tenantId,
            projectId,
            "ProjectAnalysisStarted",
            {"snapshotId": snapshot["id"], "incremental": incremental},
        )
        results = []
        failures = 0
        for analyzer in self.analyzers:
            key = t.integrityHash(
                {
                    "inputFingerprint": self.analyzerFingerprint(analyzer.name, snapshot),
                    "analyzer": analyzer.name,
                    "version": analyzer.version,
                }
            )
            cached = cache.get(key)
            if cached:
                result = {**cached, "metadata": {**cached.get("metadata", {}), "cacheHit": True}}
            else:
                try:
                    result = analyzer.analyze(snapshot)
                    cache.put(key, result)
                except Exception as exc:
                    failures += 1
                    result = {
                        "analyzerName": analyzer.name,
                        "analyzerVersion": analyzer.version,
                        "status": "FAILED",
                        "timestamp": started.isoformat(),
                        "findings": [],
                        "metrics": {},
                        "errors": [
                            {"type": type(exc).__name__, "message": "Analyzer failed in isolation."}
                        ],
                        "metadata": {},
                        "resultHash": t.integrityHash(
                            {"analyzer": analyzer.name, "error": type(exc).__name__}
                        ),
                    }
            results.append(result)
        finished = self.clock.nowUtc()
        status = (
            "PARTIAL"
            if failures and failures < len(results)
            else "FAILED"
            if failures == len(results)
            else "COMPLETED"
        )
        metrics = {
            "durationMs": max(0, int((finished - started).total_seconds() * 1000)),
            "filesScanned": len(snapshot["files"]),
            "filesChanged": len(affected),
            "analyzerFailures": failures,
            "dependencyCount": next(
                (
                    r["metrics"].get("dependencyCount", 0)
                    for r in results
                    if r["analyzerName"] == "dependency"
                ),
                0,
            ),
            "architectureViolations": next(
                (
                    r["metrics"].get("architectureViolations", 0)
                    for r in results
                    if r["analyzerName"] == "architecture"
                ),
                0,
            ),
        }
        analysisData = {
            "status": status,
            "startedAt": started,
            "completedAt": finished,
            "incremental": incremental,
            "affectedFiles": affected,
            "results": results,
            "metrics": metrics,
            "analysisHash": t.integrityHash(
                {
                    "snapshot": snapshot["snapshotHash"],
                    "results": [r["resultHash"] for r in results],
                }
            ),
        }
        analysis = self.store.saveAnalysis(
            tenantId, projectId, asUuid(snapshot["id"]), analysisData
        )
        built = self.knowledge.build(snapshot, results)
        built["snapshotId"] = snapshot["id"]
        knowledge = self.store.saveKnowledge(tenantId, projectId, asUuid(analysis["id"]), built)
        insightRows = self.store.saveInsights(
            tenantId,
            projectId,
            asUuid(knowledge["id"]),
            self.insights.generate(built["knowledge"], results),
        )
        recommendationRows = self.store.saveRecommendations(
            tenantId, projectId, self.recommendations.generate(insightRows)
        )
        decisionRows = self.store.saveDecisions(
            tenantId, projectId, self.decisions.evaluate(recommendationRows)
        )
        for item in insightRows:
            self.store.event(
                tenantId, projectId, "ProjectInsightCreated", {"insightId": item["id"]}
            )
        for item in recommendationRows:
            self.store.event(
                tenantId,
                projectId,
                "ProjectRecommendationCreated",
                {"recommendationId": item["id"]},
            )
        for item in decisionRows:
            self.store.event(
                tenantId, projectId, "ProjectDecisionCreated", {"decisionId": item["id"]}
            )
        if metrics["architectureViolations"]:
            self.store.event(
                tenantId,
                projectId,
                "ArchitectureViolationDetected",
                {"count": metrics["architectureViolations"]},
            )
        cycleCount = next(
            (
                r["metrics"].get("cycleCount", 0)
                for r in results
                if r["analyzerName"] == "dependency"
            ),
            0,
        )
        if cycleCount:
            self.store.event(tenantId, projectId, "DependencyCycleDetected", {"count": cycleCount})
        changes = self.store.projectData(tenantId, projectId, "changes")
        resumeData = self.resume.generate(
            snapshot, built["knowledge"], changes, insightRows, recommendationRows
        )
        resumeData.update({"snapshotId": snapshot["id"], "knowledgeId": knowledge["id"]})
        resume = self.store.saveResume(tenantId, projectId, resumeData)
        state = self.store.getOrCreateState(tenantId, projectId, finished)
        state.moveTo(
            "READY" if status != "FAILED" else "ERROR",
            finished,
            snapshotId=asUuid(snapshot["id"]),
            error="" if status != "FAILED" else "All analyzers failed",
        )
        self.store.saveState(state)
        self.store.audit(
            tenantId,
            actorId,
            projectId,
            "ANALYZE",
            {"analysisId": analysis["id"], "status": status, "incremental": incremental},
        )
        for event, payload in (
            ("ProjectAnalysisCompleted", {"analysisId": analysis["id"], "status": status}),
            ("ProjectKnowledgeUpdated", {"knowledgeId": knowledge["id"]}),
            ("ProjectResumeGenerated", {"resumeId": resume["id"]}),
        ):
            self.store.event(tenantId, projectId, event, payload)
        return {
            "snapshot": snapshot,
            "analysis": analysis,
            "knowledge": knowledge,
            "insights": insightRows,
            "recommendations": recommendationRows,
            "decisions": decisionRows,
            "resume": resume,
        }

    def buildContext(self, tenantId, actorId, projectId, task, budget):
        task = t.safeTask(task)
        if budget < 256 or budget > 100000:
            raise ValidationFailedError("tokenBudget must be between 256 and 100000.")
        snap = self.store.latestSnapshot(tenantId, projectId)
        knowledge = self.store.projectData(tenantId, projectId, "knowledge")
        if not snap or not knowledge:
            raise ConflictError("Analyze the project before building context.")
        payload = self.storage.load(snap["artifactUri"])
        payload.update(
            {
                "id": snap["id"],
                "version": snap["version"],
                "snapshotHash": snap["snapshotHash"],
                "createdAt": snap["createdAt"],
            }
        )
        insights = self.store.projectData(tenantId, projectId, "insights")
        recommendations = self.store.projectData(tenantId, projectId, "recommendations")
        changes = self.store.projectData(tenantId, projectId, "changes")
        data = self.context.build(
            task, budget, payload, knowledge["knowledge"], insights, recommendations, changes
        )
        data.update(
            {
                "snapshotId": snap["id"],
                "knowledgeId": knowledge["id"],
                "generatorVersion": self.context.version,
                "task": task,
                "tokenBudget": budget,
            }
        )
        result = self.store.saveContext(tenantId, projectId, data)
        self.store.audit(
            tenantId,
            actorId,
            projectId,
            "CONTEXT_BUILD",
            {"contextId": result["id"], "taskHash": t.integrityHash(task)},
        )
        self.store.event(tenantId, projectId, "ProjectContextBuilt", {"contextId": result["id"]})
        return result


class SnapshotService(UseCase):
    requiredAction = "projectIntelligence.manage"

    def __init__(self, pipeline, **kernel):
        super().__init__(**kernel)
        self.pipeline = pipeline

    def perform(self, command):
        actor, tenant = contextIds()
        snapshot, _ = self.pipeline.createSnapshot(
            tenant, actor, asUuid(command.projectId), command.workspace
        )
        return snapshot


class QueueAnalysisService(UseCase):
    requiredAction = "projectIntelligence.analyze"

    def __init__(self, store, queue, **kernel):
        super().__init__(**kernel)
        self.store = store
        self.queue = queue

    def perform(self, command):
        actor, tenant = contextIds()
        project = asUuid(command.projectId)
        key = command.idempotencyKey.strip() or str(uuid.uuid4())
        if not 0 <= command.priority <= 9:
            raise ValidationFailedError("priority must be between 0 and 9.")
        job = self.store.createJob(
            tenant,
            project,
            actor,
            {
                "jobType": "REANALYZE" if command.incremental else "ANALYZE",
                "idempotencyKey": key,
                "priority": command.priority,
                "metadata": {"workspace": command.workspace, "incremental": command.incremental},
            },
        )
        if job["created"]:
            self.queue.publish(asUuid(job["id"]))
        return job


class ProcessJobService:
    def __init__(self, store, pipeline, clock):
        self.store = store
        self.pipeline = pipeline
        self.clock = clock

    def execute(self, command):
        job = self.store.claimJob(command.jobId, self.clock.nowUtc())
        if not job:
            return {"status": "SKIPPED"}
        try:
            result = self.pipeline.run(
                asUuid(job["tenantId"]),
                asUuid(job["actorId"]),
                asUuid(job["projectId"]),
                job["metadata"].get("workspace", "."),
                bool(job["metadata"].get("incremental")),
            )
            return self.store.finishJob(
                command.jobId,
                self.clock.nowUtc(),
                result={
                    "snapshotId": result["snapshot"]["id"],
                    "analysisId": result["analysis"]["id"] if result.get("analysis") else None,
                },
            )
        except OSError as exc:
            self.store.retryJob(command.jobId, type(exc).__name__)
            raise
        except Exception as exc:
            failedAt = self.clock.nowUtc()
            self.store.finishJob(
                command.jobId, failedAt, error=f"{type(exc).__name__}: processing failed"
            )
            state = self.store.getOrCreateState(
                asUuid(job["tenantId"]), asUuid(job["projectId"]), failedAt
            )
            if state.status != "ERROR":
                state.moveTo("ERROR", failedAt, error=f"{type(exc).__name__}: processing failed")
                self.store.saveState(state)
            self.store.event(
                asUuid(job["tenantId"]),
                asUuid(job["projectId"]),
                "ProjectAnalysisFailed",
                {"errorType": type(exc).__name__},
            )
            raise


class BuildContextService(UseCase):
    requiredAction = "projectIntelligence.context"

    def __init__(self, pipeline, **kernel):
        super().__init__(**kernel)
        self.pipeline = pipeline

    def perform(self, command):
        actor, tenant = contextIds()
        return self.pipeline.buildContext(
            tenant, actor, asUuid(command.projectId), command.task, command.tokenBudget
        )


class QueryService(UseCase):
    requiredAction = "projectIntelligence.view"
    allowed = frozenset(
        {
            "state",
            "snapshots",
            "analyses",
            "architecture",
            "dependencies",
            "knowledge",
            "insights",
            "recommendations",
            "decisions",
            "context",
            "changes",
            "resume",
        }
    )

    def __init__(self, store, **kernel):
        super().__init__(**kernel)
        self.store = store

    def perform(self, query):
        if query.kind not in self.allowed:
            raise ValidationFailedError("Unsupported intelligence query.")
        _, tenant = contextIds()
        return self.store.projectData(tenant, asUuid(query.projectId), query.kind)


class CompareSnapshotsService(UseCase):
    requiredAction = "projectIntelligence.view"

    def __init__(self, store, **kernel):
        super().__init__(**kernel)
        self.store = store
        self.detector = ChangeDetector()

    def perform(self, command):
        _, tenant = contextIds()
        project = asUuid(command.projectId)
        first = self.store.snapshotById(tenant, project, asUuid(command.fromSnapshotId))
        second = (
            self.store.snapshotById(tenant, project, asUuid(command.toSnapshotId))
            if command.toSnapshotId
            else self.store.latestSnapshot(tenant, project)
        )
        if not first or not second:
            raise EntityNotFoundError("Snapshot not found.")
        return self.detector.compare(first, second)


class JobQueryService(UseCase):
    requiredAction = "projectIntelligence.view"

    def __init__(self, store, **kernel):
        super().__init__(**kernel)
        self.store = store

    def perform(self, jobId):
        _, tenant = contextIds()
        value = self.store.getJob(tenant, asUuid(jobId))
        if not value:
            raise EntityNotFoundError("Intelligence job not found.")
        return value
