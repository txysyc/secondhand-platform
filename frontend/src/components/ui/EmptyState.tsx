import React from 'react';
import { Button } from './Button';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
    variant?: 'primary' | 'outline';
  };
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  className = '',
}) => {
  return (
    <div className={`placeholder-card ${className}`}>
      {icon && (
        <div
          style={{
            fontSize: '3rem',
            marginBottom: 'var(--space-4)',
            color: 'var(--primary-color)',
          }}
        >
          {icon}
        </div>
      )}
      <h2>{title}</h2>
      {description && <p>{description}</p>}
      {action && (
        <Button variant={action.variant || 'primary'} size="sm" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
};
