"""Deterministic, plugin-like Phase 17 analyzer suite."""

from __future__ import annotations

import ast
import json
import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from typing import Any

from apps.projectIntelligence.domain.valueObjects.intelligenceTypes import LANGUAGES, integrityHash


class BaseAnalyzer:
    name = "base"
    version = "1.0.0"

    def result(
        self, snapshot: dict, findings: list[dict], metrics: dict, metadata: dict | None = None
    ) -> dict:
        return {
            "analyzerName": self.name,
            "analyzerVersion": self.version,
            "status": "COMPLETED",
            "timestamp": snapshot["createdAt"],
            "findings": findings,
            "metrics": metrics,
            "errors": [],
            "metadata": metadata or {},
            "resultHash": integrityHash(
                {
                    "name": self.name,
                    "version": self.version,
                    "findings": findings,
                    "metrics": metrics,
                    "metadata": metadata or {},
                }
            ),
        }


class FilesystemAnalyzer(BaseAnalyzer):
    name = "filesystem"

    def analyze(self, snapshot: dict) -> dict:
        files = snapshot["files"]
        debt = []
        for file in files:
            for lineNumber, line in enumerate(file.get("content", "").splitlines(), 1):
                marker = next((x for x in ("TODO", "FIXME") if x in line.upper()), None)
                if marker:
                    debt.append(
                        {
                            "type": "TECHNICAL_DEBT",
                            "marker": marker,
                            "evidence": [{"file": file["path"], "line": lineNumber}],
                        }
                    )
        directories = sorted(
            {
                str(PurePosixPath(f["path"]).parent)
                for f in files
                if str(PurePosixPath(f["path"]).parent) != "."
            }
        )
        return self.result(
            snapshot,
            [
                {
                    "type": "FILE_TREE",
                    "paths": [f["path"] for f in files],
                    "directories": directories,
                },
                *debt,
            ],
            {
                "fileCount": len(files),
                "binaryCount": sum(f["binary"] for f in files),
                "generatedCount": sum(f["generated"] for f in files),
                "totalBytes": sum(f["size"] for f in files),
                "technicalDebtMarkers": len(debt),
            },
        )


class LanguageAnalyzer(BaseAnalyzer):
    name = "language"

    def analyze(self, snapshot: dict) -> dict:
        stats: dict[str, dict] = {}
        for f in snapshot["files"]:
            language = LANGUAGES.get(f["extension"])
            if not language:
                continue
            item = stats.setdefault(
                language, {"language": language, "fileCount": 0, "loc": 0, "extensions": set()}
            )
            item["fileCount"] += 1
            item["loc"] += f["loc"]
            item["extensions"].add(f["extension"])
        total = sum(v["loc"] for v in stats.values()) or 1
        findings = []
        for key in sorted(stats):
            item = stats[key]
            item["extensions"] = sorted(item["extensions"])
            item["percentage"] = round(100 * item["loc"] / total, 2)
            findings.append(item)
        return self.result(
            snapshot,
            findings,
            {"languages": len(findings), "sourceLoc": sum(x["loc"] for x in findings)},
        )


class FrameworkAnalyzer(BaseAnalyzer):
    name = "framework"
    signatures = {
        "Django": ("django", "manage.py"),
        "FastAPI": ("fastapi",),
        "Flask": ("flask",),
        "React": ("react",),
        "Next.js": ("next", "next.config"),
        "Vue": ("vue",),
        "Angular": ("@angular/", "angular.json"),
        ".NET": (".csproj",),
        "Spring": ("org.springframework",),
    }

    def analyze(self, snapshot: dict) -> dict:
        haystack = "\n".join(
            f["path"] + "\n" + f["content"][:20000] for f in snapshot["files"] if not f["binary"]
        ).lower()
        findings = []
        for framework, sigs in self.signatures.items():
            evidence = [s for s in sigs if s.lower() in haystack]
            if evidence:
                findings.append(
                    {
                        "framework": framework,
                        "confidence": min(0.99, 0.6 + 0.15 * len(evidence)),
                        "evidence": evidence,
                    }
                )
        return self.result(snapshot, findings, {"frameworkCount": len(findings)})


class DependencyAnalyzer(BaseAnalyzer):
    name = "dependency"

    def analyze(self, snapshot: dict) -> dict:
        edges: list[dict[str, Any]] = []
        symbols: list[dict[str, Any]] = []
        external: Counter[str] = Counter()
        projectModules = {
            f["path"].removesuffix(".py").replace("/", ".")
            for f in snapshot["files"]
            if f["extension"] == ".py"
        }
        for f in snapshot["files"]:
            if f["extension"] == ".py" and f["content"]:
                try:
                    tree = ast.parse(f["content"])
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.append(
                            {
                                "type": "SYMBOL",
                                "file": f["path"],
                                "name": node.name,
                                "symbolType": "Class"
                                if isinstance(node, ast.ClassDef)
                                else "Function",
                                "line": node.lineno,
                            }
                        )
                    names = []
                    if isinstance(node, ast.Import):
                        names = [x.name for x in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        names = [node.module]
                    for name in names:
                        internal = any(
                            name == m or m.startswith(name + ".") or name.startswith(m + ".")
                            for m in projectModules
                        )
                        edges.append(
                            {
                                "source": f["path"],
                                "target": name,
                                "kind": "INTERNAL" if internal else "EXTERNAL",
                            }
                        )
                        if not internal:
                            external[name.split(".")[0]] += 1
            elif f["extension"] in (".js", ".jsx", ".ts", ".tsx"):
                for target in re.findall(r"(?:from\s+|require\()[\"']([^\"']+)", f["content"]):
                    edges.append(
                        {
                            "source": f["path"],
                            "target": target,
                            "kind": "INTERNAL" if target.startswith(".") else "EXTERNAL",
                        }
                    )
        graph: dict[str, set[str]] = defaultdict(set)
        for e in edges:
            if e["kind"] == "INTERNAL":
                graph[e["source"]].add(e["target"])
        cycles = self._cycles(graph)
        coupling = Counter(e["source"] for e in edges)
        declared: set[str] = set()
        for file in snapshot["files"]:
            if file["name"].startswith("requirements"):
                declared.update(
                    re.split(r"[<=>~!\[]", line.strip())[0].lower()
                    for line in file["content"].splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                )
            elif file["name"] == "package.json":
                try:
                    package = json.loads(file["content"])
                    declared.update(package.get("dependencies", {}))
                    declared.update(package.get("devDependencies", {}))
                except (TypeError, json.JSONDecodeError):
                    pass
        imported = {name.lower().replace("_", "-") for name in external}
        unused = sorted(name for name in declared if name.replace("_", "-") not in imported)
        findings: list[dict[str, Any]] = [
            *({"type": "DEPENDENCY", "edge": e} for e in edges),
            *symbols,
        ]
        findings += [
            {
                "type": "UNUSED_DEPENDENCY",
                "dependency": name,
                "evidence": ["declared dependency without detected import"],
            }
            for name in unused
        ]
        findings += [{"type": "CIRCULAR_DEPENDENCY", "cycle": c, "evidence": c} for c in cycles]
        findings += [
            {"type": "HIGH_COUPLING", "file": k, "count": v, "evidence": [k]}
            for k, v in coupling.items()
            if v >= 10
        ]
        return self.result(
            snapshot,
            findings,
            {
                "dependencyCount": len(edges),
                "internalCount": sum(e["kind"] == "INTERNAL" for e in edges),
                "externalCount": sum(e["kind"] == "EXTERNAL" for e in edges),
                "cycleCount": len(cycles),
                "unusedDependencyCount": len(unused),
                "symbolCount": len(symbols),
            },
            {"externalPackages": dict(sorted(external.items()))},
        )

    def _cycles(self, graph: dict[str, set[str]]) -> list[list[str]]:
        cycles = []

        def visit(node, path):
            if node in path:
                cycle = path[path.index(node) :] + [node]
                if cycle not in cycles:
                    cycles.append(cycle)
                return
            if len(path) > 20:
                return
            for nxt in sorted(graph.get(node, ())):
                visit(nxt, path + [node])

        for n in sorted(graph):
            visit(n, [])
        return cycles[:100]


class ArchitectureAnalyzer(BaseAnalyzer):
    name = "architecture"
    layers = ("presentation", "application", "domain", "infrastructure")
    forbidden = {
        "domain": {"presentation", "application", "infrastructure"},
        "application": {"presentation"},
    }

    def analyze(self, snapshot: dict) -> dict:
        modules = defaultdict(list)
        violations = []
        for f in snapshot["files"]:
            parts = PurePosixPath(f["path"]).parts
            layer = next((x for x in self.layers if x in parts), "unknown")
            modules[layer].append(f["path"])
            if f["extension"] == ".py":
                for source, targets in self.forbidden.items():
                    if source in parts:
                        for target in targets:
                            if re.search(
                                rf"(?:from|import)\s+[^\n]*\.{target}(?:\.|\s)", f["content"]
                            ):
                                violations.append(
                                    {
                                        "type": "CROSS_LAYER_ACCESS",
                                        "file": f["path"],
                                        "from": source,
                                        "to": target,
                                        "evidence": [f["path"]],
                                    }
                                )
        findings = [
            {"type": "LAYERS", "layers": {k: sorted(v) for k, v in sorted(modules.items())}}
        ] + violations
        return self.result(
            snapshot,
            findings,
            {
                "moduleCount": sum(len(v) for v in modules.values()),
                "architectureViolations": len(violations),
                "layerCount": len(modules),
            },
        )


class GitAnalyzer(BaseAnalyzer):
    name = "git"

    def analyze(self, snapshot: dict) -> dict:
        git = snapshot["gitState"]
        return self.result(
            snapshot,
            [{"type": "GIT_STATE", "value": git}],
            {
                "commitCount": git.get("commitCount", 0),
                "modifiedFiles": len(git.get("changes", [])),
                "contributors": len(git.get("contributors", [])),
            },
        )


class TestAnalyzer(BaseAnalyzer):
    name = "test"

    def analyze(self, snapshot: dict) -> dict:
        tests = [
            f
            for f in snapshot["files"]
            if "test" in f["name"].lower() or "tests" in PurePosixPath(f["path"]).parts
        ]
        source = [f for f in snapshot["files"] if f["extension"] in LANGUAGES and f not in tests]
        ratio = round(len(tests) / max(1, len(source)), 3)
        findings = [
            {
                "type": "TEST_COVERAGE_PROXY",
                "testFiles": [f["path"] for f in tests],
                "sourceToTestRatio": ratio,
            }
        ]
        if not tests:
            findings.append({"type": "MISSING_TESTS", "evidence": ["No test file detected"]})
        return self.result(
            snapshot,
            findings,
            {"testFiles": len(tests), "sourceFiles": len(source), "testRatio": ratio},
        )


class DocumentationAnalyzer(BaseAnalyzer):
    name = "documentation"

    def analyze(self, snapshot: dict) -> dict:
        docs = [
            f
            for f in snapshot["files"]
            if f["extension"] in (".md", ".rst", ".txt") or f["name"].lower().startswith("readme")
        ]
        architecture = [
            f["path"] for f in docs if "architect" in (f["path"] + f["content"][:1000]).lower()
        ]
        return self.result(
            snapshot,
            [
                {
                    "type": "DOCUMENTATION",
                    "files": [f["path"] for f in docs],
                    "architectureDocs": architecture,
                }
            ],
            {"documentationFiles": len(docs), "architectureDocs": len(architecture)},
        )


class ConfigurationAnalyzer(BaseAnalyzer):
    name = "configuration"
    names = {
        "pyproject.toml",
        "package.json",
        "requirements.txt",
        "dockerfile",
        "docker-compose.yml",
        "pom.xml",
        "go.mod",
        ".env.example",
    }

    def analyze(self, snapshot: dict) -> dict:
        files = [
            f["path"]
            for f in snapshot["files"]
            if f["name"].lower() in self.names or f["extension"] in (".toml", ".yaml", ".yml")
        ]
        return self.result(
            snapshot,
            [{"type": "CONFIGURATION", "files": files}],
            {"configurationFiles": len(files)},
        )


BUILTIN_ANALYZERS = (
    FilesystemAnalyzer,
    LanguageAnalyzer,
    FrameworkAnalyzer,
    DependencyAnalyzer,
    ArchitectureAnalyzer,
    GitAnalyzer,
    TestAnalyzer,
    DocumentationAnalyzer,
    ConfigurationAnalyzer,
)
