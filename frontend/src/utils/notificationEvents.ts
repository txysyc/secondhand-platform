export const NOTIFICATION_UNREAD_COUNT_EVENT = 'notification:unread-count-changed';

export interface NotificationUnreadCountUpdate {
  unreadCount?: number;
}

/**
 * 在当前浏览器页面内同步通知未读数，避免列表状态与导航徽标脱节。
 */
export const dispatchNotificationUnreadCountUpdate = (
  update: NotificationUnreadCountUpdate
) => {
  window.dispatchEvent(
    new CustomEvent<NotificationUnreadCountUpdate>(NOTIFICATION_UNREAD_COUNT_EVENT, {
      detail: update,
    })
  );
};
