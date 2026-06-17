import React from 'react';

export type BadgeVariant =
  | 'primary'
  | 'secondary'
  | 'success'
  | 'warning'
  | 'error'
  | 'info'
  | 'draft'
  | 'active'
  | 'inactive'
  | 'sold'
  | 'public'
  | 'protected';
export type BadgeSize = 'sm' | 'md';

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  size?: BadgeSize;
  className?: string;
}

const variantMap: Record<BadgeVariant, string> = {
  primary: 'badge-primary',
  secondary: 'badge-secondary',
  success: 'badge-success',
  warning: 'badge-warning',
  error: 'badge-error',
  info: 'badge-info',
  draft: 'badge-draft',
  active: 'badge-active',
  inactive: 'badge-inactive',
  sold: 'badge-sold',
  public: 'badge-public',
  protected: 'badge-protected',
};

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'secondary',
  size = 'md',
  className = '',
}) => {
  const classes = [
    'badge',
    variantMap[variant],
    size === 'sm' ? 'badge-sm' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return <span className={classes}>{children}</span>;
};
