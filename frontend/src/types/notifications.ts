import type { User } from './auth';

export type NotificationType =
  | 'listing_commented'
  | 'comment_replied'
  | 'order_created'
  | 'order_paid'
  | 'order_delivered'
  | 'order_completed';

export type NotificationStatusFilter = 'all' | 'unread' | 'read';

export interface NotificationActor extends Pick<User, 'id' | 'username' | 'profile'> {}

export interface NotificationItem {
  id: number;
  type: NotificationType;
  title: string;
  content: string;
  actor: NotificationActor | null;
  target_type: 'listing' | 'order' | 'comment';
  target_id: number;
  target_url: string;
  payload: Record<string, unknown>;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface NotificationUnreadCount {
  unread_count: number;
}

export interface NotificationReadAllResult {
  updated_count: number;
}

export interface NotificationSocketEvent {
  type: 'notification.created' | 'notification.unread_count' | 'notification.system';
  notification?: NotificationItem;
  unread_count?: number;
}
