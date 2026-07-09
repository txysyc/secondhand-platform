import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Pencil, Trash2, Star, ArrowLeft, MapPin } from 'lucide-react';
import {
  getAddresses,
  createAddress,
  updateAddress,
  deleteAddress,
  setDefaultAddress,
} from '../../api/endpoints/addresses';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Card } from '../../components/ui/Card';
import { Loading } from '../../components/ui/Loading';
import type { UserAddress } from '../../types/address';

// 空白表单数据
const EMPTY_FORM = {
  recipient_name: '',
  phone: '',
  province: '',
  city: '',
  district: '',
  detail_address: '',
  is_default: false,
};

type AddressForm = typeof EMPTY_FORM;

interface AddressFormPanelProps {
  initial: AddressForm;
  submitting: boolean;
  onSubmit: (data: AddressForm) => Promise<void>;
  onCancel: () => void;
  title: string;
}

const AddressFormPanel: React.FC<AddressFormPanelProps> = ({
  initial,
  submitting,
  onSubmit,
  onCancel,
  title,
}) => {
  const [form, setForm] = useState<AddressForm>(initial);
  const [errors, setErrors] = useState<Partial<Record<keyof AddressForm, string>>>({});

  const set = (field: keyof AddressForm, value: string | boolean) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const newErrors: Partial<Record<keyof AddressForm, string>> = {};
    const required: (keyof AddressForm)[] = [
      'recipient_name',
      'phone',
      'province',
      'city',
      'district',
      'detail_address',
    ];
    required.forEach((f) => {
      if (!String(form[f]).trim()) {
        newErrors[f] = '该字段不能为空';
      }
    });
    if (Object.keys(newErrors).length) {
      setErrors(newErrors);
      return;
    }
    setErrors({});
    await onSubmit(form);
  };

  return (
    <form onSubmit={handleSubmit} className="address-form">
      <h4 className="address-form-title">{title}</h4>
      <div className="address-form-grid">
        <div className="form-field">
          <label htmlFor="af-name" className="form-label">收货人</label>
          <Input
            id="af-name"
            value={form.recipient_name}
            onChange={(e) => set('recipient_name', e.target.value)}
            placeholder="请填写收货人姓名"
          />
          {errors.recipient_name && <span className="form-error">{errors.recipient_name}</span>}
        </div>

        <div className="form-field">
          <label htmlFor="af-phone" className="form-label">手机号</label>
          <Input
            id="af-phone"
            value={form.phone}
            onChange={(e) => set('phone', e.target.value)}
            placeholder="请填写手机号"
          />
          {errors.phone && <span className="form-error">{errors.phone}</span>}
        </div>

        <div className="form-field">
          <label htmlFor="af-province" className="form-label">省</label>
          <Input
            id="af-province"
            value={form.province}
            onChange={(e) => set('province', e.target.value)}
            placeholder="如：北京市"
          />
          {errors.province && <span className="form-error">{errors.province}</span>}
        </div>

        <div className="form-field">
          <label htmlFor="af-city" className="form-label">市</label>
          <Input
            id="af-city"
            value={form.city}
            onChange={(e) => set('city', e.target.value)}
            placeholder="如：朝阳区"
          />
          {errors.city && <span className="form-error">{errors.city}</span>}
        </div>

        <div className="form-field">
          <label htmlFor="af-district" className="form-label">区</label>
          <Input
            id="af-district"
            value={form.district}
            onChange={(e) => set('district', e.target.value)}
            placeholder="如：望京街道"
          />
          {errors.district && <span className="form-error">{errors.district}</span>}
        </div>

        <div className="form-field form-field-wide">
          <label htmlFor="af-detail" className="form-label">详细地址</label>
          <Input
            id="af-detail"
            value={form.detail_address}
            onChange={(e) => set('detail_address', e.target.value)}
            placeholder="楼栋、门牌号等"
          />
          {errors.detail_address && <span className="form-error">{errors.detail_address}</span>}
        </div>

        <div className="form-field form-field-checkbox">
          <label className="form-checkbox-label">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => set('is_default', e.target.checked)}
            />
            设为默认地址
          </label>
        </div>
      </div>

      <div className="address-form-actions">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          取消
        </Button>
        <Button type="submit" size="sm" loading={submitting}>
          保存地址
        </Button>
      </div>
    </form>
  );
};

export const AddressManager: React.FC = () => {
  const [addresses, setAddresses] = useState<UserAddress[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  // 展示新增表单
  const [showAddForm, setShowAddForm] = useState(false);
  const [addSubmitting, setAddSubmitting] = useState(false);

  // 编辑中的地址 id
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editSubmitting, setEditSubmitting] = useState(false);

  // 操作反馈
  const [actionError, setActionError] = useState<string | null>(null);

  const loadAddresses = async () => {
    setLoading(true);
    setErrorMsg('');
    try {
      const data = await getAddresses();
      setAddresses(data);
    } catch {
      setErrorMsg('获取地址列表失败，请检查网络。');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAddresses();
  }, []);

  const handleAdd = async (form: AddressForm) => {
    setAddSubmitting(true);
    setActionError(null);
    try {
      await createAddress(form);
      setShowAddForm(false);
      await loadAddresses();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : '新增地址失败，请重试');
    } finally {
      setAddSubmitting(false);
    }
  };

  const handleEdit = async (id: number, form: AddressForm) => {
    setEditSubmitting(true);
    setActionError(null);
    try {
      await updateAddress(id, form);
      setEditingId(null);
      await loadAddresses();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : '修改地址失败，请重试');
    } finally {
      setEditSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('确定要删除这条收货地址吗？')) return;
    setActionError(null);
    try {
      await deleteAddress(id);
      await loadAddresses();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : '删除地址失败，请重试');
    }
  };

  const handleSetDefault = async (id: number) => {
    setActionError(null);
    try {
      await setDefaultAddress(id);
      await loadAddresses();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : '设置默认地址失败，请重试');
    }
  };

  if (loading) {
    return <Loading text="正在加载收货地址..." />;
  }

  return (
    <div className="address-manager fade-in">
      <div className="address-manager-header">
        <Link to="/me" className="back-link">
          <ArrowLeft size={16} />
          返回个人中心
        </Link>
        <h2 className="address-manager-title">
          <MapPin size={20} />
          我的收货地址
        </h2>
      </div>

      {errorMsg && <div className="alert alert-error">{errorMsg}</div>}
      {actionError && <div className="alert alert-error">{actionError}</div>}

      {/* 新增地址入口 */}
      {!showAddForm && (
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setShowAddForm(true);
            setEditingId(null);
          }}
          className="address-add-btn"
        >
          <Plus size={16} />
          新增收货地址
        </Button>
      )}

      {showAddForm && (
        <Card shadow="sm" className="address-form-card">
          <AddressFormPanel
            title="新增收货地址"
            initial={EMPTY_FORM}
            submitting={addSubmitting}
            onSubmit={handleAdd}
            onCancel={() => setShowAddForm(false)}
          />
        </Card>
      )}

      {/* 地址列表 */}
      {addresses.length === 0 && !showAddForm ? (
        <div className="address-empty">
          <MapPin size={40} strokeWidth={1.5} />
          <p>您还没有收货地址，点击上方按钮添加一个吧</p>
        </div>
      ) : (
        <div className="address-list">
          {addresses.map((addr) => (
            <Card key={addr.id} shadow="sm" className={`address-card ${addr.is_default ? 'is-default' : ''}`}>
              {editingId === addr.id ? (
                <AddressFormPanel
                  title="修改收货地址"
                  initial={{
                    recipient_name: addr.recipient_name,
                    phone: addr.phone,
                    province: addr.province,
                    city: addr.city,
                    district: addr.district,
                    detail_address: addr.detail_address,
                    is_default: addr.is_default,
                  }}
                  submitting={editSubmitting}
                  onSubmit={(form) => handleEdit(addr.id, form)}
                  onCancel={() => setEditingId(null)}
                />
              ) : (
                <div className="address-card-body">
                  <div className="address-card-info">
                    <div className="address-card-recipient">
                      <span className="address-recipient-name">{addr.recipient_name}</span>
                      <span className="address-recipient-phone">{addr.phone}</span>
                      {addr.is_default && (
                        <span className="address-default-badge">
                          <Star size={12} />
                          默认
                        </span>
                      )}
                    </div>
                    <p className="address-card-text">
                      {addr.province} {addr.city} {addr.district} {addr.detail_address}
                    </p>
                  </div>
                  <div className="address-card-actions">
                    {!addr.is_default && (
                      <button
                        type="button"
                        className="btn-link"
                        onClick={() => handleSetDefault(addr.id)}
                      >
                        设为默认
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn-link"
                      onClick={() => {
                        setEditingId(addr.id);
                        setShowAddForm(false);
                      }}
                    >
                      <Pencil size={14} />
                      编辑
                    </button>
                    <button
                      type="button"
                      className="btn-link btn-link-danger"
                      onClick={() => handleDelete(addr.id)}
                    >
                      <Trash2 size={14} />
                      删除
                    </button>
                  </div>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
