import React, { useEffect, useState } from 'react';
import { Bell, CheckCheck, ClipboardList } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import {
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '../../api/endpoints/notifications';
import { Button, EmptyState, Loading } from '../../components/ui';
import type {
  NotificationItem,
  NotificationStatusFilter,
} from '../../types/notifications';

const PAGE_SIZE = 10;

const statusOptions: { value: NotificationStatusFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'unread', label: '未读' },
  { value: 'read', label: '已读' },
];

const getErrorMessage = (err: unknown, fallback: string): string => {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  return fallback;
};

export const NotificationCenter: React.FC = () => {
  const navigate = useNavigate();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [status, setStatus] = useState<NotificationStatusFilter>('all');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const fetchNotifications = async (page = currentPage, filter = status) => {
    setLoading(true);
    setErrorMsg('');
    try {
      const response = await getNotifications({
        status: filter,
        page,
        page_size: PAGE_SIZE,
      });
      setItems(response.results);
      setTotalCount(response.count);
    } catch (err) {
      setErrorMsg(getErrorMessage(err, '获取通知失败，请稍后重试'));
    } finally {
      setLoading(false);
    }
  };

  /* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
  useEffect(() => {
    fetchNotifications(currentPage, status);
  }, [currentPage, status]);
  /* eslint-enable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */

  const handleStatusChange = (nextStatus: NotificationStatusFilter) => {
    setCurrentPage(1);
    setStatus(nextStatus);
  };

  const handleReadAll = async () => {
    setActionLoading(true);
    setErrorMsg('');
    try {
      await markAllNotificationsRead();
      await fetchNotifications(1, status);
      setCurrentPage(1);
    } catch (err) {
      setErrorMsg(getErrorMessage(err, '全部标记已读失败，请稍后重试'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleOpenNotification = async (item: NotificationItem) => {
    try {
      if (!item.is_read) {
        await markNotificationRead(item.id);
      }
      if (item.target_url) {
        navigate(item.target_url);
      } else {
        await fetchNotifications(currentPage, status);
      }
    } catch (err) {
      setErrorMsg(getErrorMessage(err, '处理通知失败，请稍后重试'));
    }
  };

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);
  const pageNumbers = Array.from({ length: totalPages }, (_, index) => index + 1);

  if (loading) {
    return <Loading text="正在加载通知..." />;
  }

  return (
    <div className="notifications-page fade-in">
      <div className="page-header notifications-header">
        <div>
          <h1>通知中心</h1>
          <p>查看评论、订单和交易流程中的最新动态</p>
        </div>
        <Button variant="outline" loading={actionLoading} onClick={handleReadAll}>
          <CheckCheck size={16} />
          全部已读
        </Button>
      </div>

      <div className="notification-toolbar" aria-label="通知筛选">
        {statusOptions.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`notification-filter ${status === option.value ? 'active' : ''}`}
            onClick={() => handleStatusChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {errorMsg && (
        <div className="alert alert-error notifications-alert" role="alert">
          <span>{errorMsg}</span>
          <Button variant="outline" size="sm" onClick={() => fetchNotifications(currentPage, status)}>
            重试
          </Button>
        </div>
      )}

      {items.length === 0 ? (
        <EmptyState
          icon={<Bell size={48} />}
          title="暂无通知"
          description="评论、订单和交易进度通知会显示在这里。"
          action={{
            label: '浏览商品',
            onClick: () => navigate('/'),
            variant: 'primary',
          }}
        />
      ) : (
        <>
          <div className="notification-list">
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`notification-row ${item.is_read ? 'read' : 'unread'}`}
                onClick={() => handleOpenNotification(item)}
              >
                <span className="notification-row-icon" aria-hidden="true">
                  <ClipboardList size={20} />
                </span>
                <span className="notification-row-main">
                  <span className="notification-row-title">
                    {!item.is_read && <span className="notification-unread-dot" />}
                    {item.title}
                  </span>
                  <span className="notification-row-content">{item.content}</span>
                </span>
                <span className="notification-row-time">
                  {new Date(item.created_at).toLocaleString('zh-CN')}
                </span>
              </button>
            ))}
          </div>

          {totalPages > 1 && (
            <nav className="pagination" aria-label="通知分页">
              <button
                disabled={currentPage === 1}
                onClick={() => setCurrentPage((prev) => Math.max(prev - 1, 1))}
                className="page-btn"
                aria-label="上一页"
              >
                上页
              </button>
              {pageNumbers.map((pageNumber) => (
                <button
                  key={pageNumber}
                  onClick={() => setCurrentPage(pageNumber)}
                  className={`page-btn ${currentPage === pageNumber ? 'active' : ''}`}
                  aria-label={`第 ${pageNumber} 页`}
                  aria-current={currentPage === pageNumber ? 'page' : undefined}
                >
                  {pageNumber}
                </button>
              ))}
              <button
                disabled={currentPage === totalPages}
                onClick={() => setCurrentPage((prev) => Math.min(prev + 1, totalPages))}
                className="page-btn"
                aria-label="下一页"
              >
                下页
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
};
