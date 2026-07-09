import type React from 'react';

import { Input, Select, TextArea } from '../../../components/ui';
import type { ItemCondition, ItemType, PhysicalDeliveryMethod } from '../../../types/listings';
import { CONDITION_OPTIONS, DELIVERY_METHOD_OPTIONS, ITEM_TYPE_OPTIONS } from './options';

interface ListingFormFieldsProps {
  categoryOptions: Array<{ value: string | number; label: string }>;
  title: string;
  category: string;
  itemType: ItemType;
  price: string;
  description: string;
  deliveryNotes: string;
  condition: ItemCondition;
  physicalDeliveryMethod: PhysicalDeliveryMethod;
  virtualValidUntil: string;
  fieldErrors: Record<string, string>;
  saving: boolean;
  isEditMode: boolean;
  onTitleChange: (value: string) => void;
  onCategoryChange: (value: string) => void;
  onItemTypeChange: (value: ItemType) => void;
  onPriceChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onDeliveryNotesChange: (value: string) => void;
  onConditionChange: (value: ItemCondition) => void;
  onPhysicalDeliveryMethodChange: (value: PhysicalDeliveryMethod) => void;
  onVirtualValidUntilChange: (value: string) => void;
}

export const ListingFormFields: React.FC<ListingFormFieldsProps> = ({
  categoryOptions,
  title,
  category,
  itemType,
  price,
  description,
  deliveryNotes,
  condition,
  physicalDeliveryMethod,
  virtualValidUntil,
  fieldErrors,
  saving,
  isEditMode,
  onTitleChange,
  onCategoryChange,
  onItemTypeChange,
  onPriceChange,
  onDescriptionChange,
  onDeliveryNotesChange,
  onConditionChange,
  onPhysicalDeliveryMethodChange,
  onVirtualValidUntilChange,
}) => (
  <>
    {/* 商品标题输入。 */}
    <Input
      id="title"
      label="商品标题"
      required
      type="text"
      placeholder="请输入商品标题 (例如：品牌、型号、关键规格)"
      value={title}
      onChange={(e) => onTitleChange(e.target.value)}
      disabled={saving}
    />

    {/* 分类与交付类别选择。 */}
    <div className="form-row">
      <Select
        id="category"
        label="商品分类"
        required
        options={categoryOptions}
        value={category}
        onChange={(e) => onCategoryChange(e.target.value)}
        disabled={saving}
      />

      <Select
        id="itemType"
        label="交付类别"
        required
        options={ITEM_TYPE_OPTIONS}
        value={itemType}
        onChange={(e) => onItemTypeChange(e.target.value as ItemType)}
        disabled={saving || isEditMode}
      />
    </div>

    {/* 价格输入保留原有货币前缀样式。 */}
    <div className="form-group">
      <label htmlFor="price" className="form-label-required">
        转让价格 (元)
      </label>
      <div className="price-input-wrapper">
        <span className="price-currency">¥</span>
        <input
          id="price"
          type="number"
          step="0.01"
          min="0"
          className="form-control price-control"
          placeholder="请输入转让价格"
          value={price}
          onChange={(e) => onPriceChange(e.target.value)}
          disabled={saving}
          required
        />
      </div>
    </div>

    {/* 根据商品类型展示实体或虚拟商品专属字段。 */}
    <div className="form-specs-section">
      {itemType === 'physical' ? (
        <div className="form-row">
          <Select
            id="condition"
            label="商品成色"
            required
            options={CONDITION_OPTIONS}
            value={condition}
            onChange={(e) => onConditionChange(e.target.value as ItemCondition)}
            disabled={saving}
          />

          <Select
            id="deliveryMethod"
            label="建议交付方式"
            required
            options={DELIVERY_METHOD_OPTIONS}
            value={physicalDeliveryMethod}
            onChange={(e) => onPhysicalDeliveryMethodChange(e.target.value as PhysicalDeliveryMethod)}
            disabled={saving}
          />
        </div>
      ) : (
        <Input
          id="validUntil"
          label="虚拟兑换码有效期"
          required={itemType === 'virtual'}
          type="datetime-local"
          error={fieldErrors.virtual_valid_until}
          value={virtualValidUntil}
          onChange={(e) => onVirtualValidUntilChange(e.target.value)}
          disabled={saving}
        />
      )}
    </div>

    {/* 商品详细描述。 */}
    <TextArea
      id="description"
      label="商品描述"
      required
      rows={5}
      placeholder="请详细说明商品的规格参数、购买途径、使用痕迹、功能瑕疵等，有利于更快卖出"
      value={description}
      onChange={(e) => onDescriptionChange(e.target.value)}
      disabled={saving}
    />

    {/* 交易补充说明。 */}
    <Input
      id="deliveryNotes"
      label="补充交易说明 (可选)"
      type="text"
      placeholder="例：同城可约地铁站面交；谢绝砍价；不退换"
      value={deliveryNotes}
      onChange={(e) => onDeliveryNotesChange(e.target.value)}
      disabled={saving}
    />
  </>
);
