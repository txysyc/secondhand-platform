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

/**
 * 根据用户名生成稳定的本地首字母头像，避免外部头像服务不可用时出现破图。
 */
export const avatarFallbackUrl = (seed: string) => {
  const avatarColors = ['#087f72', '#39736b', '#b85b24', '#596f62', '#8a6534'];
  const colorIndex = Array.from(seed).reduce((total, character) => total + character.charCodeAt(0), 0);
  const backgroundColor = avatarColors[colorIndex % avatarColors.length];
  const initial = Array.from(seed.trim())[0]?.toUpperCase() || '闲';
  const safeInitial = initial.replace(
    /[&<>"']/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' })[character] ||
      character
  );
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96"><rect width="96" height="96" rx="48" fill="${backgroundColor}"/><text x="48" y="51" fill="#fff" font-family="sans-serif" font-size="36" font-weight="700" text-anchor="middle" dominant-baseline="middle">${safeInitial}</text></svg>`;

  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
};

export const resolveAvatarUrl = (url: string | null | undefined, seed: string) => {
  return resolveMediaUrl(url) || avatarFallbackUrl(seed);
};
