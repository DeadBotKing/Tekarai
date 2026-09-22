import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";
import { runtimeConfig } from "../../app/configuration/runtimeConfig";
import { demoNotifications } from "../demo/demoData";
import type { AppNotification, Priority } from "../../shared/types/domain";

interface BroadcastNotificationDto {
  id: string;
  type: string;
  title: string;
  body: string;
  priority: string;
  state: string;
  createdAt: string | null;
}

const normalizePriority = (priority: string): Priority => {
  const value = priority.toLowerCase();
  if (value === "critical" || value === "high" || value === "low") return value;
  return "normal";
};

const normalizeType = (type: string): AppNotification["type"] => {
  const value = type.toLowerCase();
  if (value.includes("task")) return "task";
  if (value.includes("project")) return "project";
  if (value.includes("security") || value.includes("auth")) return "security";
  if (value.includes("insight") || value.includes("ai")) return "insight";
  return "system";
};

const mapBroadcast = (notification: BroadcastNotificationDto): AppNotification => ({
  id: notification.id,
  title: notification.title,
  body: notification.body,
  type: normalizeType(notification.type),
  priority: normalizePriority(notification.priority),
  createdAt: notification.createdAt ?? "",
  read: notification.state.toUpperCase() !== "UNREAD",
});

export interface NotificationService {
  list: (signal?: AbortSignal) => Promise<AppNotification[]>;
  markRead: (notificationId: string, signal?: AbortSignal) => Promise<void>;
  markAllRead: (notifications: AppNotification[], signal?: AbortSignal) => Promise<void>;
}

export const createNotificationService = (api: ApiClient): NotificationService => ({
  list: async (signal) => {
    if (runtimeConfig.demoMode) return [...demoNotifications];
    const broadcasts = await api.get<BroadcastNotificationDto[]>(apiEndpoints.notifications.broadcasts, { signal });
    return broadcasts.map(mapBroadcast);
  },
  markRead: async (notificationId, signal) => {
    if (!runtimeConfig.demoMode) {
      await api.post(apiEndpoints.notifications.broadcastRead(notificationId), undefined, { signal, retry: 0 });
    }
  },
  markAllRead: async (notifications, signal) => {
    if (!runtimeConfig.demoMode) {
      await Promise.all(
        notifications.filter((notification) => !notification.read).map((notification) =>
          api.post(apiEndpoints.notifications.broadcastRead(notification.id), undefined, { signal, retry: 0 }),
        ),
      );
    }
  },
});
