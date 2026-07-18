import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { AlertCircle, PartyPopper } from 'lucide-react';
import { useAuth } from '../../app/auth';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';

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
    } catch (err: unknown) {
      const error = err as { errors?: Record<string, string[]>; message?: string };
      if (error.errors && Object.keys(error.errors).length > 0) {
        const formattedErrors: Record<string, string> = {};
        Object.entries(error.errors).forEach(([key, value]) => {
          formattedErrors[key] = Array.isArray(value) ? value[0] : String(value);
        });
        setFieldErrors(formattedErrors);
      } else {
        setGlobalError(error.message || '注册失败，请稍后重试');
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
          <div className="alert alert-error" role="alert">
            <AlertCircle size={20} aria-hidden="true" />
            <span>{globalError}</span>
          </div>
        )}

        {successMsg && (
          <div className="alert alert-success" role="status">
            <PartyPopper size={20} aria-hidden="true" />
            <span>{successMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="auth-form">
          <Input
            id="username"
            type="text"
            label="用户名"
            placeholder="请设置用户名，至少 3 个字符"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={loading}
            required
            error={fieldErrors.username}
          />

          <Input
            id="email"
            type="email"
            label="电子邮箱"
            placeholder="请输入电子邮箱"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
            required
            error={fieldErrors.email}
          />

          <Input
            id="password"
            type="password"
            label="密码"
            placeholder="请输入登录密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            required
            error={fieldErrors.password}
          />

          <Input
            id="passwordConfirm"
            type="password"
            label="确认密码"
            placeholder="请再次输入密码以确认"
            value={passwordConfirm}
            onChange={(e) => setPasswordConfirm(e.target.value)}
            disabled={loading}
            required
            error={fieldErrors.password_confirm}
          />

          <Button type="submit" variant="primary" size="lg" fullWidth loading={loading}>
            {loading ? '正在处理...' : '立即注册'}
          </Button>
        </form>

        <div className="auth-footer">
          <span>已有账号？</span>
          <Link to="/login" className="auth-link">
            返回登录
          </Link>
        </div>
      </div>
    </div>
  );
};
