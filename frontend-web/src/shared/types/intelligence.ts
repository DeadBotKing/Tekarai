export interface HealthBreakdown {
  label: string;
  score: number;
  detail: string;
}

export interface IntelligenceInsight {
  id: string;
  severity: "info" | "low" | "medium" | "high" | "critical";
  title: string;
  what: string;
  why: string;
  evidence: string;
  confidence: number;
  source: string;
}

export interface IntelligenceRecommendation {
  id: string;
  priority: "low" | "medium" | "high";
  title: string;
  problem: string;
  benefit: string;
  risk: string;
  status: "new" | "review" | "accepted" | "deferred";
}

export interface IntelligenceData {
  projectId: string;
  projectName: string;
  state: "ready" | "scanning" | "analyzing" | "changed" | "stale" | "error";
  lastAnalysis: string;
  analysisVersion: string;
  healthScore: number;
  healthBreakdown: HealthBreakdown[];
  filesAnalyzed: number;
  languages: { name: string; percentage: number; loc: number }[];
  architecture: { layer: string; modules: number; score: number }[];
  dependencies: { name: string; type: "internal" | "external"; version: string; risk: "low" | "medium" | "high" }[];
  changes: { path: string; kind: "added" | "modified" | "deleted"; author: string; timestamp: string }[];
  insights: IntelligenceInsight[];
  recommendations: IntelligenceRecommendation[];
  contextFiles: string[];
}
