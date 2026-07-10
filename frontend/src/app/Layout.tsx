import React, { useState, useRef, useEffect } from 'react';
import { NavLink, Link, Outlet, useNavigate } from 'react-router-dom';
import {
  Recycle,
  Menu,
  X,
  Bell,
  MessageSquare,
  ShoppingBag,
  Package,
  User,
  LogOut,
  ChevronDown,
  Clock,
  Heart,
  MapPin,
} from 'lucide-react';
import { useAuth } from './providers';
import { getNotificationUnreadCount } from '../api/endpoints/notifications';
import { Avatar } from '../components/ui/Avatar';
import { Button } from '../components/ui/Button';
import type { NotificationSocketEvent } from '../types/notifications';

interface NavigationItem {
  to: string;
  label: string;
  icon: React.ReactNode;
  unreadCount?: number;
}

export const Layout: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [menuOpen, setMenuOpen] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [notificationUnreadCount, setNotificationUnreadCount] = useState(0);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const notificationSocketRef = useRef<WebSocket | null>(null);
  const notificationReconnectTimerRef = useRef<number | null>(null);

  const handleLogout = () => {
    logout();
    setDropdownOpen(false);
    setMenuOpen(false);
    setNotificationUnreadCount(0);
    notificationSocketRef.current?.close();
    notificationSocketRef.current = null;
    navigate('/login');
  };

  const displayName = user ? user.profile?.nickname || user.username : '';

  // 点击页面其他区域关闭用户下拉菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    };

    if (dropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [dropdownOpen]);

  useEffect(() => {
    let cancelled = false;

    const clearReconnectTimer = () => {
      // 组件卸载或用户退出时清理重连定时器，避免旧用户状态继续重连。
      if (notificationReconnectTimerRef.current) {
        window.clearTimeout(notificationReconnectTimerRef.current);
        notificationReconnectTimerRef.current = null;
      }
    };

    const refreshUnreadCount = async () => {
      try {
        const data = await getNotificationUnreadCount();
        if (!cancelled) {
          setNotificationUnreadCount(data.unread_count);
        }
      } catch {
        if (!cancelled) {
          setNotificationUnreadCount(0);
        }
      }
    };

    const connectNotificationSocket = () => {
      const token = localStorage.getItem('access_token');
      if (!token || cancelled) return;

      try {
        const fallbackWsBaseUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
        const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL || fallbackWsBaseUrl;
        const socket = new WebSocket(
          `${wsBaseUrl}/ws/notifications/?token=${encodeURIComponent(token)}`
        );
        notificationSocketRef.current = socket;

        socket.onmessage = (event) => {
          if (notificationSocketRef.current !== socket) return;
          const data = JSON.parse(event.data) as NotificationSocketEvent;
          if (
            data.type === 'notification.created' ||
            data.type === 'notification.unread_count'
          ) {
            setNotificationUnreadCount(data.unread_count ?? 0);
          }
        };

        socket.onclose = () => {
          if (cancelled || notificationSocketRef.current !== socket) return;
          notificationSocketRef.current = null;
          clearReconnectTimer();
          notificationReconnectTimerRef.current = window.setTimeout(() => {
            refreshUnreadCount();
            connectNotificationSocket();
          }, 5000);
        };

        socket.onerror = () => {
          socket.close();
        };
      } catch {
        clearReconnectTimer();
        notificationReconnectTimerRef.current = window.setTimeout(() => {
          refreshUnreadCount();
          connectNotificationSocket();
        }, 5000);
      }
    };

    if (user) {
      refreshUnreadCount();
      connectNotificationSocket();
    } else {
      setNotificationUnreadCount(0);
    }

    return () => {
      cancelled = true;
      clearReconnectTimer();
      notificationSocketRef.current?.close();
      notificationSocketRef.current = null;
    };
  }, [user]);

  const publicNav: NavigationItem[] = [{ to: '/', label: '商品浏览', icon: <Package size={18} /> }];

  const authenticatedNav: NavigationItem[] = [
    {
      to: '/notifications',
      label: '通知',
      icon: <Bell size={18} />,
      unreadCount: notificationUnreadCount,
    },
    { to: '/messages', label: '消息', icon: <MessageSquare size={18} /> },
    { to: '/orders/buyer', label: '订单', icon: <ShoppingBag size={18} /> },
    { to: '/me/listings', label: '我的商品', icon: <Package size={18} /> },
    { to: '/me', label: '个人中心', icon: <User size={18} /> },
  ];

  return (
    <div className="app-container">
      <header className="navbar">
        <div className="navbar-container">
          <Link to="/" className="navbar-brand" aria-label="二货交易平台首页">
            <span className="brand-icon" aria-hidden="true">
              <Recycle size={20} />
            </span>
            <span className="brand-text">二货交易平台</span>
          </Link>

          <button
            type="button"
            className="mobile-menu-btn"
            aria-label={menuOpen ? '关闭导航菜单' : '打开导航菜单'}
            aria-expanded={menuOpen}
            aria-controls="primary-navigation"
            onClick={() => setMenuOpen((prev) => !prev)}
          >
            {menuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>

          <nav
            id="primary-navigation"
            className={`navbar-links ${menuOpen ? 'open' : ''}`}
            aria-label="主导航"
          >
            {publicNav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => (isActive ? 'nav-item active' : 'nav-item')}
                onClick={() => setMenuOpen(false)}
              >
                <span className="nav-item-icon" aria-hidden="true">
                  {item.icon}
                </span>
                {item.label}
              </NavLink>
            ))}
            {user &&
              authenticatedNav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `${isActive ? 'nav-item active' : 'nav-item'}${
                      item.to === '/notifications' ? ' notification-nav-link' : ''
                    }`
                  }
                  onClick={() => setMenuOpen(false)}
                >
                  <span className="nav-item-icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  {item.label}
                  {typeof item.unreadCount === 'number' && item.unreadCount > 0 && (
                    <span className="notification-badge" aria-label={`未读通知 ${item.unreadCount} 条`}>
                      {item.unreadCount > 99 ? '99+' : item.unreadCount}
                    </span>
                  )}
                </NavLink>
              ))}
          </nav>

          <div className="navbar-actions">
            {user ? (
              <div className="user-profile-menu" ref={dropdownRef}>
                <button
                  type="button"
                  className="user-menu-trigger"
                  aria-haspopup="true"
                  aria-expanded={dropdownOpen}
                  onClick={() => setDropdownOpen((prev) => !prev)}
                >
                  <Avatar
                    src={user.profile?.avatar_url}
                    username={user.username}
                    alt={displayName}
                    size="sm"
                  />
                  <span className="user-welcome">
                    <strong>{displayName}</strong>
                  </span>
                  <ChevronDown
                    size={16}
                    className={`user-menu-chevron ${dropdownOpen ? 'open' : ''}`}
                    aria-hidden="true"
                  />
                </button>

                {dropdownOpen && (
                  <div className="user-dropdown" role="menu">
                    <Link
                      to="/me"
                      className="user-dropdown-item"
                      onClick={() => setDropdownOpen(false)}
                      role="menuitem"
                    >
                      <User size={16} />
                      个人中心
                    </Link>
                    <Link
                      to="/me/favorites"
                      className="user-dropdown-item"
                      onClick={() => setDropdownOpen(false)}
                      role="menuitem"
                    >
                      <Heart size={16} />
                      我的收藏
                    </Link>
                    <Link
                      to="/me/history"
                      className="user-dropdown-item"
                      onClick={() => setDropdownOpen(false)}
                      role="menuitem"
                    >
                      <Clock size={16} />
                      浏览历史
                    </Link>
                    <Link
                      to="/me/addresses"
                      className="user-dropdown-item"
                      onClick={() => setDropdownOpen(false)}
                      role="menuitem"
                    >
                      <MapPin size={16} />
                      我的地址
                    </Link>
                    <button
                      type="button"
                      className="user-dropdown-item user-dropdown-danger"
                      onClick={handleLogout}
                      role="menuitem"
                    >
                      <LogOut size={16} />
                      退出登录
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="auth-buttons">
                <Button variant="ghost" size="sm" onClick={() => navigate('/login')}>
                  登录
                </Button>
                <Button variant="primary" size="sm" onClick={() => navigate('/register')}>
                  注册
                </Button>
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="main-content">
        <div className="content-container">
          <Outlet />
        </div>
      </main>

      <footer className="footer">
        <div className="footer-container">
          <p>© 2026 二货交易平台. 基于 React + Vite + TypeScript 前后端分离重构版</p>
        </div>
      </footer>
    </div>
  );
};
