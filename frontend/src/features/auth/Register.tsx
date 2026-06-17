import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../app/providers';

export const Register: React.FC = () => {
  const { register, login } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  
  const [loading, setLoading] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [globalError, setGlobalError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setFieldErrors({});
    setGlobalError('');
    setSuccessMsg('');

    if (password !== passwordConfirm) {
      setFieldErrors({ password_confirm: '两次输入的密码不一致' });
      setLoading(false);
      return;
    }

    try {
      await register({
        username,
        email,
        password,
        password_confirm: passwordConfirm,
      });

      setSuccessMsg('注册成功！正在为您自动登录并跳转...');

      // 注册成功后延迟自动登录并跳转
      setTimeout(async () => {
        try {
          await login(username, password);
          navigate('/', { replace: true });
        } catch {
          navigate('/login', { replace: true });
        }
      }, 1500);

    } catch (err: any) {
      if (err && err.errors && Object.keys(err.errors).length > 0) {
        const formattedErrors: Record<string, string> = {};
        Object.entries(err.errors).forEach(([key, value]) => {
          formattedErrors[key] = Array.isArray(value) ? value[0] : String(value);
        });
        setFieldErrors(formattedErrors);
      } else {
        setGlobalError(err?.message || '注册失败，请稍后重试');
      }
      setLoading(false);
    }
  };

  return (
    <div className="auth-wrapper fade-in">
      <div className="auth-card">
        <h2 className="auth-title">创建新账号</h2>
        <p className="auth-subtitle">加入二货交易平台，开始买卖闲置商品</p>
        
        {globalError && (
          <div className="alert alert-error">
            <span>⚠️ {globalError}</span>
          </div>
        )}

        {successMsg && (
          <div className="alert alert-success">
            <span>🎉 {successMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label htmlFor="username">用户名</label>
            <input
              id="username"
              type="text"
              className={`form-control ${fieldErrors.username ? 'is-invalid' : ''}`}
              placeholder="请设置用户名，至少 3 个字符"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              required
            />
            {fieldErrors.username && (
              <span className="invalid-feedback">{fieldErrors.username}</span>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="email">电子邮箱</label>
            <input
              id="email"
              type="email"
              className={`form-control ${fieldErrors.email ? 'is-invalid' : ''}`}
              placeholder="请输入电子邮箱"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
              required
            />
            {fieldErrors.email && (
              <span className="invalid-feedback">{fieldErrors.email}</span>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="password">密码</label>
            <input
              id="password"
              type="password"
              className={`form-control ${fieldErrors.password ? 'is-invalid' : ''}`}
              placeholder="请输入登录密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              required
            />
            {fieldErrors.password && (
              <span className="invalid-feedback">{fieldErrors.password}</span>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="passwordConfirm">确认密码</label>
            <input
              id="passwordConfirm"
              type="password"
              className={`form-control ${fieldErrors.password_confirm ? 'is-invalid' : ''}`}
              placeholder="请再次输入密码以确认"
              value={passwordConfirm}
              onChange={(e) => setPasswordConfirm(e.target.value)}
              disabled={loading}
              required
            />
            {fieldErrors.password_confirm && (
              <span className="invalid-feedback">{fieldErrors.password_confirm}</span>
            )}
          </div>

          <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={loading}>
            {loading ? '正在注册...' : '立即注册'}
          </button>
        </form>

        <div className="auth-footer">
          <span>已有账号？</span>
          <Link to="/login" className="auth-link">返回登录</Link>
        </div>
      </div>
    </div>
  );
};
