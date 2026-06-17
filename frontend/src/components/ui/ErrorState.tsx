import React from 'react';
import { AlertCircle } from 'lucide-react';
import { Button } from './Button';

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  onBack?: () => void;
  className?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = '出错了',
  message = '加载失败，请稍后重试',
  onRetry,
  onBack,
  className = '',
}) => {
  return (
    <div className={`placeholder-card error-card ${className}`}>
      <div style={{ marginBottom: 'var(--space-4)', color: 'var(--error-color)' }}>
        <AlertCircle size={48} />
      </div>
      <h2>{title}</h2>
      <p>{message}</p>
      <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'center' }}>
        {onRetry && (
          <Button size="sm" onClick={onRetry}>
            重试
          </Button>
        )}
        {onBack && (
          <Button size="sm" variant="outline" onClick={onBack}>
            返回
          </Button>
        )}
      </div>
    </div>
  );
};
