/** Versioned application-interface paths. Feature code never assembles API versions or auth headers. */
export const apiEndpoints = {
  auth: { login: "auth/login", refresh: "auth/refresh", logout: "auth/logout", me: "me" },
  tenants: "tenants",
  users: "users",
  roles: "roles",
  audit: "platform/audit-events",
  notifications: { list: "notifications", unreadCount: "notifications/unread-count", read: (id: string) => `notifications/${id}/read`, readBulk: "notifications/read-bulk", search: "notifications/search" },
  intelligence: {
    overview: (projectId: string) => `projects/${projectId}/intelligence/`,
    state: (projectId: string) => `projects/${projectId}/intelligence/state/`,
    architecture: (projectId: string) => `projects/${projectId}/intelligence/architecture/`,
    dependencies: (projectId: string) => `projects/${projectId}/intelligence/dependencies/`,
    insights: (projectId: string) => `projects/${projectId}/intelligence/insights/`,
    recommendations: (projectId: string) => `projects/${projectId}/intelligence/recommendations/`,
    context: (projectId: string) => `projects/${projectId}/intelligence/context/`,
    buildContext: (projectId: string) => `projects/${projectId}/intelligence/context/build/`,
    analyze: (projectId: string) => `projects/${projectId}/intelligence/analyze/`,
    reanalyze: (projectId: string) => `projects/${projectId}/intelligence/reanalyze/`,
    changes: (projectId: string) => `projects/${projectId}/intelligence/changes/`,
    resume: (projectId: string) => `projects/${projectId}/intelligence/resume/`,
    compare: (projectId: string) => `projects/${projectId}/intelligence/compare/`,
  },
} as const;
