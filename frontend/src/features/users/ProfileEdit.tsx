import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, PartyPopper, AlertCircle } from 'lucide-react';
import { useAuth } from '../../app/auth';
import { updateProfile } from '../../api/endpoints/users';
import { resolveMediaUrl } from '../../utils/media';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { TextArea } from '../../components/ui/TextArea';
import { Button } from '../../components/ui/Button';
import { Avatar } from '../../components/ui/Avatar';
import { ErrorState } from '../../components/ui/ErrorState';

/**
 * 只读信息字段组件
 */
const ReadOnlyField: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="form-group read-only-field">
    <label>{label}</label>
    <input
      type="text"
      className="form-control read-only-control"
      value={value}
      disabled
      readOnly
      aria-readonly="true"
    />
  </div>
);

export const ProfileEdit: React.FC = () => {
  const { user, refreshUser } = useAuth();
  const navigate = useNavigate();

  const initialNickname = user?.profile?.nickname || '';
  const initialBio = user?.profile?.bio || '';
  const initialAvatarPreview = resolveMediaUrl(user?.profile?.avatar_url);

  const [nickname, setNickname] = useState(initialNickname);
  const [bio, setBio] = useState(initialBio);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(initialAvatarPreview);

  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setAvatarFile(file);
      const url = URL.createObjectURL(file);
      setAvatarPreview(url);
    }
  };

  const handleChooseFile = () => {
    fileInputRef.current?.click();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSuccessMsg('');
    setErrorMsg('');

    const formData = new FormData();
    formData.append('nickname', nickname);
    formData.append('bio', bio);
    if (avatarFile) {
      formData.append('avatar', avatarFile);
    }

    try {
      await updateProfile(formData);
      setSuccessMsg('个人资料已成功保存！');
      await refreshUser();
    } catch (err: unknown) {
      const error = err as { message?: string };
      setErrorMsg(error.message || '保存失败，请重试');
    } finally {
      setSaving(false);
    }
  };

  if (!user) {
    return (
      <ErrorState
        title="您尚未登录"
        message="访问此页面需要先登录您的账号。"
        onBack={() => navigate('/login')}
      />
    );
  }

  return (
    <div className="profile-edit-container fade-in">
      <Card padding="lg" shadow="md" className="profile-card">
        <h2 className="auth-title profile-edit-title">编辑个人资料</h2>
        <p className="auth-subtitle profile-edit-subtitle">
          设置您的公开昵称、个人简介及头像
        </p>

        {successMsg && (
          <div className="alert alert-success" role="status">
            <PartyPopper size={20} aria-hidden="true" />
            <span>{successMsg}</span>
          </div>
        )}

        {errorMsg && (
          <div className="alert alert-error" role="alert">
            <AlertCircle size={20} aria-hidden="true" />
            <span>{errorMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {/* 头像上传与预览 */}
          <div className="avatar-upload-section">
            <div className="avatar-preview-wrapper">
              <Avatar
                src={avatarPreview}
                username={user.username}
                alt={nickname || user.username}
                size="xl"
                className="profile-edit-avatar"
              />
            </div>
            <div className="avatar-upload-btn-wrapper">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleChooseFile}
                aria-controls="avatar-input"
              >
                <Upload size={16} aria-hidden="true" />
                {avatarFile ? '更换头像' : '上传头像图片'}
              </Button>
              <input
                id="avatar-input"
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="visually-hidden-file-input"
                onChange={handleAvatarChange}
                disabled={saving}
                aria-label="选择头像图片"
              />
              <span className="form-helper avatar-upload-hint">
                支持 JPG、PNG 格式
              </span>
            </div>
          </div>

          {/* 账号系统用户名及邮箱 (只读展示) */}
          <div className="form-row account-info-row">
            <ReadOnlyField label="系统用户名" value={user.username} />
            <ReadOnlyField label="注册邮箱" value={user.email || '未绑定邮箱'} />
          </div>

          {/* 昵称 */}
          <Input
            id="nickname"
            type="text"
            label="个性昵称"
            placeholder="请输入您的公开昵称，未设置时将显示用户名"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            disabled={saving}
            required
          />

          {/* 简介 */}
          <TextArea
            id="bio"
            label="个人简介"
            placeholder="向大家介绍一下你自己吧..."
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            disabled={saving}
            rows={5}
          />

          <Button
            type="submit"
            variant="primary"
            size="lg"
            fullWidth
            loading={saving}
            className="profile-save-btn"
          >
            {saving ? '正在保存...' : '保存修改'}
          </Button>
        </form>
      </Card>
    </div>
  );
};
