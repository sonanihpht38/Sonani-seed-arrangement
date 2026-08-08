// Feature API layer for per-user notifications.

import { api } from "../../api/client";

export type NotificationLevel = "info" | "success" | "warning" | "error";

export interface AppNotification {
  id: number;
  title: string;
  message: string;
  level: NotificationLevel;
  link: string;
  is_read: boolean;
  created_at: string;
}

export const notificationsApi = {
  list: () => api.get<AppNotification[]>("/notifications/"),
  unreadCount: () => api.get<{ count: number }>("/notifications/unread_count/"),
  markRead: (id: number) => api.post<{ detail: string }>(`/notifications/${id}/read/`, {}),
  markAllRead: () => api.post<{ updated: number }>("/notifications/mark_all_read/", {}),
};
