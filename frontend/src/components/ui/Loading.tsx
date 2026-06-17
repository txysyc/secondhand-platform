import React from 'react';

interface LoadingProps {
  text?: string;
  size?: 'sm' | 'md';
  className?: string;
}

export const Loading: React.FC<LoadingProps> = ({
  text = '加载中...',
  size = 'md',
  className = '',
}) => {
  return (
    <div className={`loading-container ${className}`}>
      <div className={`spinner ${size === 'sm' ? 'spinner-sm' : ''}`} />
      {text && <p>{text}</p>}
    </div>
  );
};
