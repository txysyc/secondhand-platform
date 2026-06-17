import React, { useState, useEffect } from 'react';
import { useAuth } from '../../app/providers';
import { updateProfile } from '../../api/endpoints/users';
import { resolveAvatarUrl, resolveMediaUrl } from '../../utils/media';

export const ProfileEdit: React.FC = () => {
  const { user, refreshUser } = useAuth();

  const [nickname, setNickname] = useState('');
  const [bio, setBio] = useState('');
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);

  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (user) {
      setNickname(user.profile?.nickname || '');
      setBio(user.profile?.bio || '');
      setAvatarPreview(resolveMediaUrl(user.profile?.avatar_url));
    }
  }, [user]);

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setAvatarFile(file);
      const url = URL.createObjectURL(file);
      setAvatarPreview(url);
    }
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
    } catch (err: any) {
      setErrorMsg(err.message || '保存失败，请重试');
    } finally {
      setSaving(false);
    }
  };

  if (!user) {
    return (
      <div className="placeholder-card error-card">
        <h2>⚠️ 您尚未登录</h2>
        <p>访问此页面需要先登录您的账号。</p>
      </div>
    );
  }

  return (
    <div className="profile-edit-container fade-in">
      <div className="profile-card">
        <h2 className="auth-title" style={{ marginBottom: '8px' }}>编辑个人资料</h2>
        <p className="auth-subtitle" style={{ marginBottom: '32px' }}>设置您的公开昵称、个人简介及头像</p>

        {successMsg && (
          <div className="alert alert-success">
            <span>🎉 {successMsg}</span>
          </div>
        )}

        {errorMsg && (
          <div className="alert alert-error">
            <span>⚠️ {errorMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {/* 头像上传与预览 */}
          <div className="avatar-upload-section">
            <div className="avatar-preview-wrapper">
              <img
                src={avatarPreview || resolveAvatarUrl(null, user.username)}
                alt="头像预览"
                className="avatar-preview-img"
              />
            </div>
            <div className="avatar-upload-btn-wrapper">
              <button type="button" className="btn btn-outline">
                {avatarFile ? '更换头像' : '上传头像图片'}
              </button>
              <input
                type="file"
                accept="image/*"
                className="avatar-file-input"
                onChange={handleAvatarChange}
                disabled={saving}
              />
            </div>
          </div>

          {/* 账号系统用户名及邮箱 (只读展示) */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '20px' }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label>系统用户名</label>
              <input
                type="text"
                className="form-control"
                style={{ backgroundColor: 'var(--bg-main)', cursor: 'not-allowed', color: 'var(--text-muted)' }}
                value={user.username}
                disabled
              />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label>注册邮箱</label>
              <input
                type="text"
                className="form-control"
                style={{ backgroundColor: 'var(--bg-main)', cursor: 'not-allowed', color: 'var(--text-muted)' }}
                value={user.email || '未绑定邮箱'}
                disabled
              />
            </div>
          </div>

          {/* 昵称 */}
          <div className="form-group">
            <label htmlFor="nickname">个性昵称</label>
            <input
              id="nickname"
              type="text"
              className="form-control"
              placeholder="请输入您的公开昵称，未设置时将显示用户名"
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              disabled={saving}
              required
            />
          </div>

          {/* 简介 */}
          <div className="form-group">
            <label htmlFor="bio">个人简介</label>
            <textarea
              id="bio"
              className="form-control"
              style={{ minHeight: '120px', resize: 'vertical' }}
              placeholder="向大家介绍一下你自己吧..."
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              disabled={saving}
            />
          </div>

          <button type="submit" className="btn btn-primary btn-block btn-lg" style={{ marginTop: '12px' }} disabled={saving}>
            {saving ? '正在保存...' : '保存修改'}
          </button>
        </form>
      </div>
    </div>
  );
};
