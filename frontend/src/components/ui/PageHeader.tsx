import type React from 'react';

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  eyebrow?: string;
  className?: string;
}

/**
 * 统一页面标题区，保证标题、说明和操作按钮在不同页面保持一致密度。
 */
export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  description,
  actions,
  eyebrow,
  className = '',
}) => (
  <header className={`page-header page-header-component ${className}`.trim()}>
    <div className="page-header-copy">
      {eyebrow && <span className="page-header-eyebrow">{eyebrow}</span>}
      <h1>{title}</h1>
      {description && <p>{description}</p>}
    </div>
    {actions && <div className="page-header-actions">{actions}</div>}
  </header>
);
