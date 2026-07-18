type RequestConfig = RequestInit & {
  params?: Record<string, string | number | boolean>;
};

/** API 统一错误载荷，保持与后端 message/errors 契约一致。 */
export interface ApiErrorPayload {
  status: number;
  message: string;
  errors: unknown;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

class ApiClient {
  private baseUrl: string = import.meta.env.VITE_API_BASE_URL || '/api/v1';
  private isRefreshing = false;
  private refreshSubscribers: ((token: string) => void)[] = [];
  private authFailureCallback: (() => void) | null = null;

  /** 注册认证失败（Token 刷新失败）的全局回调。 */
  public setAuthFailureCallback(callback: () => void) {
    this.authFailureCallback = callback;
  }

  private getTokens() {
    return {
      access: localStorage.getItem('access_token'),
      refresh: localStorage.getItem('refresh_token'),
    };
  }

  private setTokens(access: string, refresh?: string) {
    localStorage.setItem('access_token', access);
    if (refresh) {
      localStorage.setItem('refresh_token', refresh);
    }
  }

  private clearTokens() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    this.authFailureCallback?.();
  }

  private subscribeTokenRefresh(callback: (token: string) => void) {
    this.refreshSubscribers.push(callback);
  }

  private onRefreshed(token: string) {
    this.refreshSubscribers.forEach((callback) => callback(token));
    this.refreshSubscribers = [];
  }

  private handleRefreshFailure() {
    this.refreshSubscribers = [];
    this.clearTokens();
  }

  private async request<T = unknown>(url: string, config: RequestConfig = {}): Promise<T> {
    const { params, ...init } = config;

    // 拼接 URL 查询参数。
    let fullUrl = url.startsWith('http') ? url : `${this.baseUrl}${url}`;
    if (params) {
      const searchParams = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        // 页面筛选对象会保留未填写字段；空值不能序列化成字符串 undefined/null。
        if (value === undefined || value === null) {
          return;
        }
        searchParams.append(key, String(value));
      });
      const queryString = searchParams.toString();
      if (queryString) {
        fullUrl += (fullUrl.includes('?') ? '&' : '?') + queryString;
      }
    }

    const headers = new Headers(init.headers);
    const { access } = this.getTokens();
    if (access) {
      headers.set('Authorization', `Bearer ${access}`);
    }

    // FormData 由浏览器自动设置 boundary，JSON 请求才补充 Content-Type。
    if (init.body instanceof FormData) {
      headers.delete('Content-Type');
    } else if (init.body && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    init.headers = headers;

    const response = await fetch(fullUrl, init);
    if (response.status !== 401) {
      return this.handleResponse<T>(response);
    }

    const { refresh } = this.getTokens();
    if (!refresh || url === '/auth/token/refresh/') {
      this.clearTokens();
      throw await this.parseError(response);
    }

    if (!this.isRefreshing) {
      this.isRefreshing = true;
      this.refreshToken(refresh)
        .then((newAccess) => {
          this.isRefreshing = false;
          this.onRefreshed(newAccess);
        })
        .catch(() => {
          this.isRefreshing = false;
          this.handleRefreshFailure();
        });
    }

    // 刷新期间的请求排队，共用同一个新 access token。
    return new Promise<T>((resolve, reject) => {
      this.subscribeTokenRefresh((newToken) => {
        const retryHeaders = new Headers(init.headers);
        retryHeaders.set('Authorization', `Bearer ${newToken}`);
        fetch(fullUrl, { ...init, headers: retryHeaders })
          .then((retryResponse) => this.handleResponse<T>(retryResponse))
          .then(resolve)
          .catch(reject);
      });
    });
  }

  private async refreshToken(refresh: string): Promise<string> {
    const response = await fetch(`${this.baseUrl}/auth/token/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    });

    if (!response.ok) {
      throw new Error('Refresh token failed');
    }

    const data: unknown = await response.json();
    if (!isRecord(data) || typeof data.access !== 'string') {
      throw new Error('Refresh token response is invalid');
    }
    this.setTokens(data.access);
    return data.access;
  }

  private async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      throw await this.parseError(response);
    }
    if (response.status === 204) {
      return null as T;
    }
    return (await response.json()) as T;
  }

  private async parseError(response: Response): Promise<ApiErrorPayload> {
    try {
      const data: unknown = await response.json();
      const payload = isRecord(data) ? data : {};
      return {
        status: response.status,
        message: typeof payload.message === 'string' ? payload.message : '网络请求错误',
        errors: payload.errors ?? {},
      };
    } catch {
      return {
        status: response.status,
        message: `服务器响应异常 (${response.status})`,
        errors: {},
      };
    }
  }

  public get<T = unknown>(url: string, config?: RequestConfig) {
    return this.request<T>(url, { ...config, method: 'GET' });
  }

  public post<T = unknown>(url: string, body?: unknown, config?: RequestConfig) {
    return this.request<T>(url, {
      ...config,
      method: 'POST',
      body: body instanceof FormData ? body : JSON.stringify(body),
    });
  }

  public patch<T = unknown>(url: string, body?: unknown, config?: RequestConfig) {
    return this.request<T>(url, {
      ...config,
      method: 'PATCH',
      body: body instanceof FormData ? body : JSON.stringify(body),
    });
  }

  public put<T = unknown>(url: string, body?: unknown, config?: RequestConfig) {
    return this.request<T>(url, {
      ...config,
      method: 'PUT',
      body: body instanceof FormData ? body : JSON.stringify(body),
    });
  }

  public delete<T = unknown>(url: string, config?: RequestConfig) {
    return this.request<T>(url, { ...config, method: 'DELETE' });
  }
}

export const apiClient = new ApiClient();
export type { RequestConfig };
