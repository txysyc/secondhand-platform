import { CircleX } from 'lucide-react';

/**
 * 全站统一的路由未找到页面。
 */
export const NotFoundPage = () => (
  <div className="placeholder-card error-card fade-in">
    <CircleX size={34} aria-hidden="true" />
    <h2>页面未找到</h2>
    <p>您访问的路由地址不存在。</p>
  </div>
);
