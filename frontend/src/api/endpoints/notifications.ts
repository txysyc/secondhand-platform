import { apiClient } from '../client';
import type { PaginatedResponse } from '../../types/listings';
import type {
  NotificationItem,
  NotificationReadAllResult,
  NotificationStatusFilter,
  NotificationUnreadCount,
} from '../../types/notifications';

interface NotificationQueryParams {
  status?: NotificationStatusFilter;
  page?: string | number;
  page_size?: string | number;
}

/**
 * 获取当前用户通知列表。
 */
export const getNotifications = async (
  params?: NotificationQueryParams
): Promise<PaginatedResponse<NotificationItem>> => {
  return apiClient.get('/notifications/', { params: params as Record<string, string | number> });
};

/**
 * 获取当前用户未读通知数量。
 */
export const getNotificationUnreadCount = async (): Promise<NotificationUnreadCount> => {
  return apiClient.get('/notifications/unread-count/');
};

/**
 * 标记单条通知已读。
 */
export const markNotificationRead = async (
  id: string | number
): Promise<NotificationItem> => {
  return apiClient.post(`/notifications/${id}/read/`);
};

/**
 * 标记当前用户全部通知已读。
 */
export const markAllNotificationsRead = async (): Promise<NotificationReadAllResult> => {
  return apiClient.post('/notifications/read-all/');
};
