import React from 'react';
import { NavLink, Link, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from './providers';

export const Layout: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const getDisplayName = () => {
    if (!user) return '';
    return user.profile?.nickname || user.username;
  };

  return (
    <div className="app-container">
      <header className="navbar">
        <div className="navbar-container">
          <Link to="/" className="navbar-brand">
            <span className="brand-icon">♻️</span>
            <span className="brand-text">二货交易平台</span>
          </Link>
          
          <nav className="navbar-links">
            <NavLink to="/" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
              商品浏览
            </NavLink>
            {user && (
              <>
                <NavLink to="/messages" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
                  私信消息
                </NavLink>
                <NavLink to="/orders/buyer" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
                  我的订单
                </NavLink>
                <NavLink to="/me/listings" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
                  我的商品
                </NavLink>
                <NavLink to="/me" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
                  个人中心
                </NavLink>
              </>
            )}
          </nav>

          <div className="navbar-actions">
            {user ? (
              <div className="user-profile-menu">
                <span className="user-welcome">
                  你好，<strong>{getDisplayName()}</strong>
                </span>
                <button onClick={handleLogout} className="btn btn-outline btn-sm">
                  退出登录
                </button>
              </div>
            ) : (
              <div className="auth-buttons">
                <Link to="/login" className="btn btn-ghost btn-sm">登录</Link>
                <Link to="/register" className="btn btn-primary btn-sm">注册</Link>
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
