type RequestConfig = RequestInit & {
  params?: Record<string, string | number | boolean>;
};

class ApiClient {
  private baseUrl: string = import.meta.env.VITE_API_BASE_URL || '/api/v1';
  private isRefreshing: boolean = false;
  private refreshSubscribers: ((token: string) => void)[] = [];
  private authFailureCallback: (() => void) | null = null;

  /**
   * 注册认证失败（Token 刷新失败）的全局回调
   */
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
    if (this.authFailureCallback) {
      this.authFailureCallback();
    }
  }

  private subscribeTokenRefresh(cb: (token: string) => void) {
    this.refreshSubscribers.push(cb);
  }

  private onRefreshed(token: string) {
    this.refreshSubscribers.forEach((cb) => cb(token));
    this.refreshSubscribers = [];
  }

  private handleRefreshFailure() {
    this.refreshSubscribers = [];
    this.clearTokens();
  }

  private async request(url: string, config: RequestConfig = {}): Promise<any> {
    const { params, ...init } = config;
    
    // 拼接 URL 查询参数
    let fullUrl = url.startsWith('http') ? url : `${this.baseUrl}${url}`;
    if (params) {
      const searchParams = new URLSearchParams();
      Object.entries(params).forEach(([key, val]) => {
        if (val !== undefined && val !== null) {
          searchParams.append(key, String(val));
        }
      });
      const qs = searchParams.toString();
      if (qs) {
        fullUrl += (fullUrl.includes('?') ? '&' : '?') + qs;
      }
    }

    // 设置 Header
    const headers = new Headers(init.headers);
    const { access } = this.getTokens();
    if (access) {
      headers.set('Authorization', `Bearer ${access}`);
    }

    // FormData 情况下由浏览器自动配置边界，不设 Content-Type
    if (init.body instanceof FormData) {
      headers.delete('Content-Type');
    } else if (init.body && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }

    init.headers = headers;

    try {
      const response = await fetch(fullUrl, init);

      if (response.status === 401) {
        const { refresh } = this.getTokens();
        
        // 如果没有 refresh token，或者请求本身就是刷新 token，则直接判定登录失效
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

        // 返回 Promise 在刷新成功后重新请求并 resolve 结果
        return new Promise((resolve) => {
          this.subscribeTokenRefresh((newToken) => {
            const newHeaders = new Headers(init.headers);
            newHeaders.set('Authorization', `Bearer ${newToken}`);
            init.headers = newHeaders;
            resolve(
              fetch(fullUrl, init).then((res) => {
                if (!res.ok) {
                  return this.parseError(res).then((err) => Promise.reject(err));
                }
                return res.status === 204 ? null : res.json();
              })
            );
          });
        });
      }

      return await this.handleResponse(response);
    } catch (error) {
      throw error;
    }
  }

  private async refreshToken(refresh: string): Promise<string> {
    const res = await fetch(`${this.baseUrl}/auth/token/refresh/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh }),
    });

    if (!res.ok) {
      throw new Error('Refresh token failed');
    }

    const data = await res.json();
    this.setTokens(data.access);
    return data.access;
  }

  private async handleResponse(response: Response): Promise<any> {
    if (!response.ok) {
      throw await this.parseError(response);
    }
    
    if (response.status === 204) {
      return null;
    }

    return await response.json();
  }

  private async parseError(response: Response): Promise<any> {
    try {
      const errorData = await response.json();
      return {
        status: response.status,
        message: errorData.message || '网络请求错误',
        errors: errorData.errors || {},
      };
    } catch {
      return {
        status: response.status,
        message: `服务器响应异常 (${response.status})`,
        errors: {},
      };
    }
  }

  public get(url: string, config?: RequestConfig) {
    return this.request(url, { ...config, method: 'GET' });
  }

  public post(url: string, body?: any, config?: RequestConfig) {
    return this.request(url, {
      ...config,
      method: 'POST',
      body: body instanceof FormData ? body : JSON.stringify(body),
    });
  }

  public patch(url: string, body?: any, config?: RequestConfig) {
    return this.request(url, {
      ...config,
      method: 'PATCH',
      body: body instanceof FormData ? body : JSON.stringify(body),
    });
  }

  public put(url: string, body?: any, config?: RequestConfig) {
    return this.request(url, {
      ...config,
      method: 'PUT',
      body: body instanceof FormData ? body : JSON.stringify(body),
    });
  }

  public delete(url: string, config?: RequestConfig) {
    return this.request(url, { ...config, method: 'DELETE' });
  }
}

export const apiClient = new ApiClient();
export type { RequestConfig };
