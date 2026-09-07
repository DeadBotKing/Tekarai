import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { runtimeConfig } from "../../app/configuration/runtimeConfig";
import { useApiClient } from "../api/apiContext";
import { useAuth } from "../auth/authContext";
import { createNotificationService } from "../../features/notifications/notificationService";
import { demoNotifications } from "../../features/demo/demoData";
import type { AppNotification } from "../../shared/types/domain";

interface NotificationContextValue {
  notifications: AppNotification[];
  unreadCount: number;
  markRead: (notificationId: string) => void;
  markAllRead: () => void;
  refresh: () => Promise<void>;
}

const NotificationContext = createContext<NotificationContextValue | null>(null);

export function NotificationProvider({ children }: { children: ReactNode }): JSX.Element {
  const api = useApiClient();
  const { isAuthenticated } = useAuth();
  const service = useMemo(() => createNotificationService(api), [api]);
  const [notifications, setNotifications] = useState<AppNotification[]>(demoNotifications);
  const refresh = useCallback(async (): Promise<void> => {
    if (!isAuthenticated) return;
    const next = await service.list();
    setNotifications(next);
  }, [isAuthenticated, service]);
  useEffect(() => { if (!runtimeConfig.demoMode) void refresh(); }, [refresh]);
  const markRead = useCallback((notificationId: string): void => {
    setNotifications((current) => current.map((item) => item.id === notificationId ? { ...item, read: true } : item));
    void service.markRead(notificationId).catch(() => undefined);
  }, [service]);
  const markAllRead = useCallback((): void => {
    setNotifications((current) => current.map((item) => ({ ...item, read: true })));
    void service.markAllRead().catch(() => undefined);
  }, [service]);
  const value = useMemo(() => ({ notifications, unreadCount: notifications.filter((item) => !item.read).length, markRead, markAllRead, refresh }), [markAllRead, markRead, notifications, refresh]);
  return <NotificationContext.Provider value={value}>{children}</NotificationContext.Provider>;
}

export const useNotifications = (): NotificationContextValue => {
  const context = useContext(NotificationContext);
  if (!context) throw new Error("useNotifications must be used inside NotificationProvider");
  return context;
};
