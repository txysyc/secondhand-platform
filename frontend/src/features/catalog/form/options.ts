// 商品表单下拉选项集中维护，避免页面组件重复承担静态配置。

export const CONDITION_OPTIONS = [
  { value: 'new', label: '全新 (未拆封/未使用)' },
  { value: 'like_new', label: '九五新 (几乎无使用痕迹)' },
  { value: 'good', label: '九成新 (轻微使用痕迹)' },
  { value: 'fair', label: '八成新及以下 (有明显瑕疵/使用痕迹)' },
];

export const DELIVERY_METHOD_OPTIONS = [
  { value: 'meetup', label: '同城当面面交' },
  { value: 'shipping', label: '邮寄顺丰包邮' },
  { value: 'both', label: '均可' },
];

export const ITEM_TYPE_OPTIONS = [
  { value: 'physical', label: '实体商品' },
  { value: 'virtual', label: '虚拟商品 (卡券/兑换码等)' },
];
