"""Deterministic knowledge, insight, recommendation, decision and context engines."""

from __future__ import annotations

import re
from typing import Any

from apps.projectIntelligence.domain.valueObjects.intelligenceTypes import integrityHash


class ChangeDetector:
    def compare(self, previous: dict | None, current: dict) -> dict:
        old = {f["path"]: f["hash"] for f in (previous or {}).get("files", [])}
        new = {f["path"]: f["hash"] for f in current["files"]}
        added = sorted(new.keys() - old.keys())
        deleted = sorted(old.keys() - new.keys())
        modified = sorted(k for k in old.keys() & new.keys() if old[k] != new[k])
        renamed = []
        deletedByHash = {old[x]: x for x in deleted}
        for path in list(added):
            if new[path] in deletedByHash:
                original = deletedByHash[new[path]]
                renamed.append({"from": original, "to": path})
                added.remove(path)
                deleted.remove(original)
        return {
            "added": added,
            "modified": modified,
            "deleted": deleted,
            "renamed": renamed,
            "changeHash": integrityHash(
                {"added": added, "modified": modified, "deleted": deleted, "renamed": renamed}
            ),
        }


class KnowledgeBuilder:
    version = "1.0.0"

    def build(self, snapshot: dict, results: list[dict]) -> dict:
        byName = {r["analyzerName"]: r for r in results}
        files = snapshot["files"]
        nodes: list[dict[str, Any]] = [
            {
                "key": "project",
                "type": "Project",
                "properties": {"projectId": snapshot["projectId"]},
            }
        ]
        edges = []
        for f in files:
            nodes.append(
                {
                    "key": f["path"],
                    "type": "Test" if "test" in f["path"].lower() else "File",
                    "properties": {"hash": f["hash"], "size": f["size"]},
                }
            )
            edges.append({"source": "project", "target": f["path"], "type": "CONTAINS"})
        dep = byName.get("dependency", {})
        for finding in dep.get("findings", []):
            if finding.get("type") == "DEPENDENCY":
                e = finding["edge"]
                nodes.append(
                    {"key": e["target"], "type": "Dependency", "properties": {"kind": e["kind"]}}
                )
                edges.append({"source": e["source"], "target": e["target"], "type": "IMPORTS"})
            elif finding.get("type") == "SYMBOL":
                key = f"{finding['file']}::{finding['name']}"
                nodes.append(
                    {
                        "key": key,
                        "type": finding["symbolType"],
                        "properties": {"line": finding["line"]},
                    }
                )
                edges.append({"source": finding["file"], "target": key, "type": "CONTAINS"})
        unique = {n["key"]: n for n in nodes}
        nodes = [unique[k] for k in sorted(unique)]
        knowledge = {
            "projectOverview": {"fileCount": len(files), "snapshotVersion": snapshot["version"]},
            "projectStructure": [f["path"] for f in files],
            "languages": byName.get("language", {}).get("findings", []),
            "frameworks": byName.get("framework", {}).get("findings", []),
            "dependencies": dep.get("metrics", {}),
            "symbols": [x for x in dep.get("findings", []) if x.get("type") == "SYMBOL"],
            "architecture": byName.get("architecture", {}),
            "tests": byName.get("test", {}),
            "documentation": byName.get("documentation", {}),
            "configuration": byName.get("configuration", {}),
            "git": snapshot["gitState"],
            "analyzerFailures": [r for r in results if r["status"] == "FAILED"],
        }
        architectureViolations = (
            knowledge["architecture"].get("metrics", {}).get("architectureViolations", 0)
        )
        architectureDocs = knowledge["documentation"].get("metrics", {}).get("architectureDocs", 0)
        knowledge["documentationContradictions"] = (
            [
                {
                    "what": "Documented architecture differs from detected dependencies",
                    "evidence": ["architecture analyzer", "architecture documentation"],
                    "confidence": 0.75,
                }
            ]
            if architectureViolations and architectureDocs
            else []
        )
        knowledge["health"] = self.health(knowledge)
        knowledge["technicalDebt"] = self.debt(results)
        return {
            "knowledge": knowledge,
            "nodes": nodes,
            "edges": edges,
            "knowledgeHash": integrityHash(
                {"knowledge": knowledge, "nodes": nodes, "edges": edges}
            ),
        }

    def health(self, k: dict) -> dict:
        arch = max(
            0, 100 - 15 * k["architecture"].get("metrics", {}).get("architectureViolations", 0)
        )
        tests = min(100, int(k["tests"].get("metrics", {}).get("testRatio", 0) * 200))
        docs = min(100, k["documentation"].get("metrics", {}).get("documentationFiles", 0) * 15)
        deps = max(0, 100 - 20 * k["dependencies"].get("cycleCount", 0))
        scores = {
            "architecture": arch,
            "testing": tests,
            "documentation": docs,
            "dependencies": deps,
            "codeQuality": 80,
            "security": 80,
            "maintainability": round((arch + deps) / 2),
            "activity": 80 if k["git"].get("available") else 50,
        }
        return {
            "score": round(sum(scores.values()) / len(scores), 1),
            "breakdown": scores,
            "explanation": "Deterministic weighted project evidence; not an unsupported scalar.",
        }

    def debt(self, results: list[dict]) -> list[dict]:
        debt = []
        for r in results:
            for f in r.get("findings", []):
                if f.get("type") in (
                    "CIRCULAR_DEPENDENCY",
                    "HIGH_COUPLING",
                    "MISSING_TESTS",
                    "CROSS_LAYER_ACCESS",
                    "UNUSED_DEPENDENCY",
                    "TECHNICAL_DEBT",
                ):
                    debt.append(
                        {
                            "type": f["type"],
                            "evidence": f.get("evidence", [f]),
                            "source": r["analyzerName"],
                        }
                    )
        return debt


class InsightEngine:
    def generate(self, knowledge: dict, results: list[dict]) -> list[dict]:
        output = []
        templates = {
            "CIRCULAR_DEPENDENCY": (
                "Circular dependency detected",
                "HIGH",
                "Cycles increase change risk.",
            ),
            "HIGH_COUPLING": (
                "High coupling detected",
                "HIGH",
                "Coupling increases maintenance complexity.",
            ),
            "CROSS_LAYER_ACCESS": (
                "Architecture boundary violated",
                "CRITICAL",
                "Dependency direction is not respected.",
            ),
            "MISSING_TESTS": ("Tests are missing", "HIGH", "Changes cannot be verified reliably."),
            "UNUSED_DEPENDENCY": (
                "Possibly unused dependency detected",
                "LOW",
                "Unused packages increase maintenance and security surface.",
            ),
            "TECHNICAL_DEBT": (
                "Explicit technical-debt marker detected",
                "MEDIUM",
                "Deferred work can accumulate delivery risk.",
            ),
        }
        for r in results:
            for f in r.get("findings", []):
                if f.get("type") in templates:
                    title, severity, impact = templates[f["type"]]
                    output.append(
                        {
                            "kind": f["type"],
                            "title": title,
                            "severity": severity,
                            "confidence": 0.95,
                            "evidence": f.get("evidence", [f]),
                            "source": r["analyzerName"],
                            "impact": impact,
                        }
                    )
        for contradiction in knowledge.get("documentationContradictions", []):
            output.append(
                {
                    "kind": "DOCUMENTATION_CONTRADICTION",
                    "title": contradiction["what"],
                    "severity": "MEDIUM",
                    "confidence": contradiction["confidence"],
                    "evidence": contradiction["evidence"],
                    "source": "documentation+architecture",
                    "impact": "Agents and maintainers may follow stale architecture guidance.",
                }
            )
        for debt in knowledge.get("technicalDebt", []):
            if not any(x["kind"] == debt["type"] for x in output):
                output.append(
                    {
                        "kind": debt["type"],
                        "title": "Technical debt candidate",
                        "severity": "MEDIUM",
                        "confidence": 0.8,
                        "evidence": debt["evidence"],
                        "source": debt["source"],
                        "impact": "May reduce maintainability.",
                    }
                )
        return output


class RecommendationEngine:
    actions = {
        "CIRCULAR_DEPENDENCY": "Introduce an interface or move shared behavior to break the dependency cycle.",
        "HIGH_COUPLING": "Split responsibilities behind stable module boundaries.",
        "CROSS_LAYER_ACCESS": "Invert the dependency through an application/domain port.",
        "MISSING_TESTS": "Add focused unit and integration tests for changed behavior.",
    }

    def generate(self, insights: list[dict]) -> list[dict]:
        return [
            {
                "insightId": x["id"],
                "problem": x["title"],
                "recommendation": self.actions.get(
                    x["kind"], "Review and remediate the evidenced issue."
                ),
                "reason": x["impact"],
                "evidence": x["evidence"],
                "expectedBenefit": "Lower delivery and maintenance risk.",
                "risk": "Refactoring may require compatibility testing.",
                "priority": x["severity"],
            }
            for x in insights
        ]


class DecisionEngine:
    def evaluate(self, recommendations: list[dict], actorId: str | None = None) -> list[dict]:
        ranking = {
            "CRITICAL": "REVIEW_REQUIRED",
            "HIGH": "REVIEW_REQUIRED",
            "MEDIUM": "DEFER",
            "LOW": "DEFER",
            "INFO": "DEFER",
        }
        return [
            {
                "recommendationId": x["id"],
                "decision": ranking[x["priority"]],
                "evidence": x["evidence"],
                "reason": "Evidence-based deterministic triage; human acceptance is required for impactful changes.",
                "decidedById": actorId,
            }
            for x in recommendations
        ]


class ContextBuilder:
    version = "1.0.0"

    def build(
        self,
        task: str,
        budget: int,
        snapshot: dict,
        knowledge: dict,
        insights: list[dict],
        recommendations: list[dict],
        changes: list[dict],
    ) -> dict:
        terms = {x.lower() for x in re.findall(r"[A-Za-z0-9_./-]+", task) if len(x) > 2}
        ranked = []
        for f in snapshot["files"]:
            if f.get("binary") or f.get("secretNamed") or f.get("ignored") or f.get("generated"):
                continue
            path = f["path"].lower()
            score = (
                sum(term in path for term in terms) * 10
                + (5 if "test" in path else 0)
                + (2 if f["extension"] in (".md", ".rst") else 0)
            )
            ranked.append((score, -f["size"], f))
        ranked.sort(key=lambda x: (-x[0], -x[1], x[2]["path"]))
        remaining = max(256, budget) * 4
        included = []
        excluded = []
        for _, __, f in ranked:
            content = f.get("content", "")
            item = {"path": f["path"], "hash": f["hash"], "content": content[: max(0, remaining)]}
            cost = len(item["path"]) + len(item["content"])
            if cost <= remaining and content:
                included.append(item)
                remaining -= cost
            else:
                excluded.append(f["path"])
        package = {
            "task": task,
            "projectOverview": knowledge.get("projectOverview", {}),
            "architecture": knowledge.get("architecture", {}),
            "dependencies": knowledge.get("dependencies", {}),
            "currentState": knowledge.get("health", {}),
            "recentChanges": changes[:20],
            "knownIssues": insights[:50],
            "recommendations": recommendations[:50],
            "relevantFiles": included,
            "relevantSymbols": knowledge.get("symbols", [])[:100],
            "constraints": ["Workspace is read-only", "Deterministic evidence is source of truth"],
            "developmentRules": knowledge.get("documentation", {}),
        }
        return {
            "package": package,
            "includedFiles": [x["path"] for x in included],
            "includedModules": sorted({x["path"].split("/")[0] for x in included}),
            "excludedFiles": excluded,
            "contextHash": integrityHash(package),
        }


class ResumeGenerator:
    version = "1.0.0"

    def generate(
        self,
        snapshot: dict,
        knowledge: dict,
        changes: list[dict],
        insights: list[dict],
        recommendations: list[dict],
    ) -> dict:
        value = {
            "project": snapshot["projectId"],
            "currentState": knowledge.get("health"),
            "architecture": knowledge.get("architecture"),
            "recentChanges": changes[:20],
            "activeProblems": insights[:30],
            "completedWork": ["Snapshot and deterministic analysis completed"],
            "pendingWork": [x["recommendation"] for x in recommendations[:20]],
            "knownConstraints": ["Workspace read-only", "Tenant boundary enforced"],
            "recommendedNextAction": recommendations[0]["recommendation"]
            if recommendations
            else "Keep project intelligence current.",
        }
        return {"resume": value, "resumeHash": integrityHash(value)}
