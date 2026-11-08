import type { WorkspaceModule } from "./organizationWorkspace";
/** Static offline fixture only; production always uses the server registry. */
export const previewWorkspaceCatalog: WorkspaceModule[] = [
  {
    "code": "maintenance",
    "label": "تجهیزات و تعمیرات",
    "route": "/app/maintenance/equipment",
    "actionPrefixes": [
      "maintenance.",
      "analytics.",
      "asset."
    ],
    "apiPrefixes": [
      "maintenance",
      "analytics"
    ],
    "permissions": [
      "maintenance.device.list",
      "maintenance.workorder.list"
    ],
    "requires": []
  },
  {
    "code": "projects",
    "label": "پروژه‌ها",
    "route": "/app/projects",
    "actionPrefixes": [
      "project."
    ],
    "apiPrefixes": [
      "projects"
    ],
    "permissions": [
      "project.view",
      "project.list"
    ],
    "requires": []
  },
  {
    "code": "tasks",
    "label": "کارها",
    "route": "/app/tasks",
    "actionPrefixes": [
      "task."
    ],
    "apiPrefixes": [
      "tasks"
    ],
    "permissions": [
      "task.view",
      "task.list"
    ],
    "requires": [
      "projects"
    ]
  },
  {
    "code": "documents",
    "label": "اسناد",
    "route": "/app/documents",
    "actionPrefixes": [
      "document.",
      "maintenance.document."
    ],
    "apiPrefixes": [
      "documents",
      "maintenance/documents"
    ],
    "permissions": [
      "maintenance.document.view",
      "document.view"
    ],
    "requires": []
  },
  {
    "code": "procurement",
    "label": "تدارکات",
    "route": "/app/maintenance/procurement",
    "actionPrefixes": [
      "procurement."
    ],
    "apiPrefixes": [
      "procurement"
    ],
    "permissions": [
      "procurement.supplier.view"
    ],
    "requires": [
      "maintenance"
    ]
  },
  {
    "code": "safety",
    "label": "ایمنی",
    "route": "/app/maintenance/permits",
    "actionPrefixes": [
      "safety."
    ],
    "apiPrefixes": [
      "safety"
    ],
    "permissions": [
      "safety.permit.view"
    ],
    "requires": [
      "maintenance"
    ]
  },
  {
    "code": "communication",
    "label": "گفتگو",
    "route": "/app/chat",
    "actionPrefixes": [
      "communication."
    ],
    "apiPrefixes": [
      "communication"
    ],
    "permissions": [
      "communication.chat.use"
    ],
    "requires": []
  },
  {
    "code": "intelligence",
    "label": "هوشمندی",
    "route": "/app/intelligence",
    "actionPrefixes": [
      "projectIntelligence.",
      "ai.",
      "learning."
    ],
    "apiPrefixes": [
      "ai",
      "learning",
      "project-intelligence",
      "intelligence"
    ],
    "permissions": [
      "projectIntelligence.view",
      "intelligence.view"
    ],
    "requires": [
      "projects"
    ]
  }
];
