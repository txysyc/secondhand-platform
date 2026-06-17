import React, { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../../app/providers';

export const Login: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [globalError, setGlobalError] = useState('');

  // 记录跳转来源
  const from = (location.state as any)?.from?.pathname || '/';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setFieldErrors({});
    setGlobalError('');

    try {
      await login(identifier, password);
      // 登录成功后重定向到之前的路由
      navigate(from, { replace: true });
    } catch (err: any) {
      if (err && err.errors && Object.keys(err.errors).length > 0) {
        const formattedErrors: Record<string, string> = {};
        Object.entries(err.errors).forEach(([key, value]) => {
          formattedErrors[key] = Array.isArray(value) ? value[0] : String(value);
        });
        setFieldErrors(formattedErrors);
      } else {
        setGlobalError(err?.message || '登录失败，请稍后重试');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-wrapper fade-in">
      <div className="auth-card">
        <h2 className="auth-title">欢迎回来</h2>
        <p className="auth-subtitle">请登录您的二货交易平台账号</p>
        
        {globalError && (
          <div className="alert alert-error">
            <span>⚠️ {globalError}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label htmlFor="identifier">用户名或邮箱</label>
            <input
              id="identifier"
              type="text"
              className={`form-control ${fieldErrors.identifier || fieldErrors.non_field_errors ? 'is-invalid' : ''}`}
              placeholder="请输入用户名或电子邮箱"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              disabled={loading}
              required
            />
            {fieldErrors.identifier && (
              <span className="invalid-feedback">{fieldErrors.identifier}</span>
            )}
            {fieldErrors.non_field_errors && (
              <span className="invalid-feedback">{fieldErrors.non_field_errors}</span>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="password">密码</label>
            <input
              id="password"
              type="password"
              className={`form-control ${fieldErrors.password ? 'is-invalid' : ''}`}
              placeholder="请输入您的密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              required
            />
            {fieldErrors.password && (
              <span className="invalid-feedback">{fieldErrors.password}</span>
            )}
          </div>

          <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={loading}>
            {loading ? '正在登录...' : '立即登录'}
          </button>
        </form>

        <div className="auth-footer">
          <span>还没有账号？</span>
          <Link to="/register" className="auth-link">免费注册</Link>
        </div>
      </div>
    </div>
  );
};
