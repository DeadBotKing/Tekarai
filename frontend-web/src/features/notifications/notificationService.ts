import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";
import { runtimeConfig } from "../../app/configuration/runtimeConfig";
import { demoNotifications } from "../demo/demoData";
import type { AppNotification } from "../../shared/types/domain";

export interface NotificationService {
  list: (signal?: AbortSignal) => Promise<AppNotification[]>;
  markRead: (notificationId: string, signal?: AbortSignal) => Promise<void>;
  markAllRead: (signal?: AbortSignal) => Promise<void>;
}

export const createNotificationService = (api: ApiClient): NotificationService => ({
  list: async (signal) => {
    if (runtimeConfig.demoMode) return [...demoNotifications];
    return api.get<AppNotification[]>(apiEndpoints.notifications.list, { signal });
  },
  markRead: async (notificationId, signal) => {
    if (!runtimeConfig.demoMode) await api.post(apiEndpoints.notifications.read(notificationId), undefined, { signal, retry: 0 });
  },
  markAllRead: async (signal) => {
    if (!runtimeConfig.demoMode) await api.post(apiEndpoints.notifications.readBulk, { all: true }, { signal, retry: 0 });
  },
});
