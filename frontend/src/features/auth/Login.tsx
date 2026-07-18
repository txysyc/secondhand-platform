import React, { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';
import { useAuth } from '../../app/auth';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';

interface LocationState {
  from?: { pathname: string };
}

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
  const from = (location.state as LocationState | undefined)?.from?.pathname || '/';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setFieldErrors({});
    setGlobalError('');

    try {
      await login(identifier, password);
      // 登录成功后重定向到之前的路由
      navigate(from, { replace: true });
    } catch (err: unknown) {
      const error = err as { errors?: Record<string, string[]>; message?: string };
      if (error.errors && Object.keys(error.errors).length > 0) {
        const formattedErrors: Record<string, string> = {};
        Object.entries(error.errors).forEach(([key, value]) => {
          formattedErrors[key] = Array.isArray(value) ? value[0] : String(value);
        });
        setFieldErrors(formattedErrors);
      } else {
        setGlobalError(error.message || '登录失败，请稍后重试');
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
          <div className="alert alert-error" role="alert">
            <AlertCircle size={20} aria-hidden="true" />
            <span>{globalError}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="auth-form">
          <Input
            id="identifier"
            type="text"
            label="用户名或邮箱"
            placeholder="请输入用户名或电子邮箱"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            disabled={loading}
            required
            error={fieldErrors.identifier || fieldErrors.non_field_errors}
          />

          <Input
            id="password"
            type="password"
            label="密码"
            placeholder="请输入您的密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            required
            error={fieldErrors.password}
          />

          <Button type="submit" variant="primary" size="lg" fullWidth loading={loading}>
            {loading ? '正在登录...' : '立即登录'}
          </Button>
        </form>

        <div className="auth-footer">
          <span>还没有账号？</span>
          <Link to="/register" className="auth-link">
            免费注册
          </Link>
        </div>
      </div>
    </div>
  );
};
