import React from 'react';
import { User } from 'lucide-react';
import { resolveAvatarUrl } from '../../utils/media';

interface AvatarProps {
  src?: string | null;
  username?: string;
  alt?: string;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
}

const sizeMap: Record<string, number> = {
  xs: 24,
  sm: 32,
  md: 40,
  lg: 56,
  xl: 80,
};

const fontSizeMap: Record<string, string> = {
  xs: '0.6rem',
  sm: '0.75rem',
  md: '0.9rem',
  lg: '1.1rem',
  xl: '1.5rem',
};

export const Avatar: React.FC<AvatarProps> = ({
  src,
  username = '',
  alt,
  size = 'md',
  className = '',
}) => {
  const dimension = sizeMap[size];
  const resolvedSrc = resolveAvatarUrl(src ?? null, username);
  const letter = username?.charAt(0).toUpperCase() || '';

  const containerStyle: React.CSSProperties = {
    width: dimension,
    height: dimension,
    borderRadius: '50%',
    overflow: 'hidden',
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'var(--bg-elevated)',
    border: '1px solid var(--border-light)',
    color: 'var(--text-muted)',
    fontWeight: 700,
    fontSize: fontSizeMap[size],
  };

  if (resolvedSrc) {
    return (
      <img
        src={resolvedSrc}
        alt={alt || username || '头像'}
        className={`avatar-img ${className}`}
        width={dimension}
        height={dimension}
        style={{ objectFit: 'cover', borderRadius: '50%' }}
      />
    );
  }

  return (
    <div className={`avatar ${className}`} style={containerStyle} aria-label={alt || username || '默认头像'}>
      {letter ? <span>{letter}</span> : <User size={dimension * 0.45} />}
    </div>
  );
};
