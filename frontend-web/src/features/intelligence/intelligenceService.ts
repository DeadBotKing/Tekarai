import { runtimeConfig } from "../../app/configuration/runtimeConfig";
import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";
import { demoIntelligence } from "../demo/demoData";
import type { IntelligenceData } from "../../shared/types/intelligence";

export interface IntelligenceJob { id: string; projectId: string; status: "queued" | "running" | "completed" | "failed"; progress?: number; }
export interface ContextPackage { projectId: string; snapshotId: string; knowledgeVersion: string; generatedAt: string; tokenBudget: number; includedFiles: string[]; excludedFiles: string[]; }

export interface IntelligenceService {
  getOverview: (projectId: string, signal?: AbortSignal) => Promise<IntelligenceData>;
  startAnalysis: (projectId: string, workspace: string, incremental: boolean, signal?: AbortSignal) => Promise<IntelligenceJob>;
  buildContext: (projectId: string, task: string, tokenBudget: number, signal?: AbortSignal) => Promise<ContextPackage>;
}

export const createIntelligenceService = (api: ApiClient): IntelligenceService => ({
  getOverview: async (projectId, signal) => {
    const response = await api.get<Partial<IntelligenceData>>(apiEndpoints.intelligence.overview(projectId), { signal });
    return normalizeOverview(response, projectId);
  },
  startAnalysis: (projectId, workspace, incremental, signal) => api.post<IntelligenceJob>(incremental ? apiEndpoints.intelligence.reanalyze(projectId) : apiEndpoints.intelligence.analyze(projectId), { workspace, priority: 5 }, { signal, retry: 0 }),
  buildContext: (projectId, task, tokenBudget, signal) => api.post<ContextPackage>(apiEndpoints.intelligence.buildContext(projectId), { task, tokenBudget }, { signal, retry: 0 }),
});

export const loadIntelligence = async (api: ApiClient, projectId: string, signal?: AbortSignal): Promise<IntelligenceData> => {
  if (runtimeConfig.demoMode) {
    await new Promise((resolve) => window.setTimeout(resolve, 120));
    return { ...demoIntelligence, projectId };
  }
  return createIntelligenceService(api).getOverview(projectId, signal);
};

export const normalizeOverview = (response: Partial<IntelligenceData>, projectId: string): IntelligenceData => ({
  projectId,
  projectName: response.projectName ?? 'تحلیل معتبر موجود نیست',
  state: response.state ?? 'error',
  lastAnalysis: response.lastAnalysis ?? '',
  analysisVersion: response.analysisVersion ?? '',
  healthScore: response.healthScore ?? 0,
  filesAnalyzed: response.filesAnalyzed ?? 0,
  healthBreakdown: response.healthBreakdown ?? [],
  languages: response.languages ?? [],
  architecture: response.architecture ?? [],
  dependencies: response.dependencies ?? [],
  changes: response.changes ?? [],
  insights: response.insights ?? [],
  recommendations: response.recommendations ?? [],
  contextFiles: response.contextFiles ?? [],
});
