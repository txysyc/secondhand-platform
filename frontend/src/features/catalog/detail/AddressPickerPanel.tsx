import type React from 'react';
import { Link } from 'react-router-dom';
import { MapPin, Star } from 'lucide-react';

import { Button } from '../../../components/ui';
import type { UserAddress } from '../../../types/address';

interface AddressPickerPanelProps {
  addresses: UserAddress[];
  selectedAddressId: number | null;
  loadingAddresses: boolean;
  buySubmitting: boolean;
  onSelectedAddressIdChange: (addressId: number) => void;
  onCancel: () => void;
  onConfirm: () => void;
}

export const AddressPickerPanel: React.FC<AddressPickerPanelProps> = ({
  addresses,
  selectedAddressId,
  loadingAddresses,
  buySubmitting,
  onSelectedAddressIdChange,
  onCancel,
  onConfirm,
}) => (
  <div className="address-picker">
    <h4 className="address-picker-title">
      <MapPin size={16} />
      选择收货地址
    </h4>
    {loadingAddresses ? (
      <div className="address-picker-loading">正在加载地址…</div>
    ) : addresses.length === 0 ? (
      <div className="address-picker-empty">
        <p>您还没有收货地址</p>
        <Link to="/me/addresses" className="btn-link">
          前往添加
        </Link>
      </div>
    ) : (
      <div className="address-picker-list">
        {addresses.map((addr) => (
          <label
            key={addr.id}
            className={`address-picker-item ${selectedAddressId === addr.id ? 'selected' : ''}`}
          >
            <input
              type="radio"
              name="address"
              value={addr.id}
              checked={selectedAddressId === addr.id}
              onChange={() => onSelectedAddressIdChange(addr.id)}
            />
            <div className="address-picker-info">
              <span className="address-picker-recipient">
                {addr.recipient_name}
                <span className="address-picker-phone">{addr.phone}</span>
                {addr.is_default && (
                  <span className="address-default-badge">
                    <Star size={11} />
                    默认
                  </span>
                )}
              </span>
              <span className="address-picker-text">
                {addr.province} {addr.city} {addr.district} {addr.detail_address}
              </span>
            </div>
          </label>
        ))}
        <Link to="/me/addresses" className="btn-link address-picker-manage">
          管理地址
        </Link>
      </div>
    )}
    <div className="address-picker-actions">
      <Button variant="outline" size="sm" onClick={onCancel}>
        取消
      </Button>
      <Button
        size="sm"
        onClick={onConfirm}
        loading={buySubmitting}
        disabled={!selectedAddressId || loadingAddresses}
      >
        确认下单
      </Button>
    </div>
  </div>
);
