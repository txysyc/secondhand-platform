const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
const MEDIA_BASE_URL = import.meta.env.VITE_MEDIA_BASE_URL || '';

const trimTrailingSlash = (value: string) => value.replace(/\/+$/, '');

const resolveBackendOrigin = () => {
  if (MEDIA_BASE_URL) {
    return trimTrailingSlash(MEDIA_BASE_URL);
  }

  if (/^https?:\/\//i.test(API_BASE_URL)) {
    return trimTrailingSlash(API_BASE_URL.replace(/\/api\/v\d+\/?$/i, ''));
  }

  return import.meta.env.DEV ? 'http://localhost:8000' : '';
};

/**
 * 将后端返回的媒体路径统一转换为浏览器可访问地址。
 * Django ImageField 默认返回 /media/...，在 Vite 开发端口下需要补齐后端 origin。
 */
export const resolveMediaUrl = (url?: string | null) => {
  if (!url) return null;
  if (/^(https?:|data:|blob:)/i.test(url)) return url;

  const normalizedPath = url.startsWith('/') ? url : `/${url}`;
  const origin = resolveBackendOrigin();
  return origin ? `${origin}${normalizedPath}` : normalizedPath;
};

export const avatarFallbackUrl = (seed: string) => {
  return `https://api.dicebear.com/7.x/identicon/svg?seed=${encodeURIComponent(seed)}`;
};

export const resolveAvatarUrl = (url: string | null | undefined, seed: string) => {
  return resolveMediaUrl(url) || avatarFallbackUrl(seed);
};
