import { Clock, Heart, MapPin, Package, UserRound } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';

// 个人中心各业务入口统一维护，避免页面之间只能依赖顶部下拉菜单跳转。
const accountNavigationItems = [
  { to: '/me', label: '个人资料', icon: UserRound, end: true },
  { to: '/me/listings', label: '我的商品', icon: Package, end: false },
  { to: '/me/favorites', label: '我的收藏', icon: Heart, end: false },
  { to: '/me/history', label: '浏览历史', icon: Clock, end: false },
  { to: '/me/addresses', label: '收货地址', icon: MapPin, end: false },
];

/**
 * 个人中心共享外壳：桌面使用侧栏，移动端自动转换为横向标签导航。
 */
export const AccountLayout = () => (
  <div className="account-layout fade-in">
    <aside className="account-sidebar" aria-label="个人中心导航">
      <div className="account-sidebar-heading">
        <span>账户管理</span>
        <strong>个人中心</strong>
      </div>
      <nav className="account-navigation">
        {accountNavigationItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `account-navigation-item ${isActive ? 'active' : ''}`
            }
          >
            <Icon size={17} aria-hidden="true" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
    <section className="account-content">
      <Outlet />
    </section>
  </div>
);
