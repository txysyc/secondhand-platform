/** 我的商品筛选状态选项。 */
export const MY_LISTING_STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'draft', label: '草稿' },
  { value: 'active', label: '在售' },
  { value: 'reserved', label: '交易占用' },
  { value: 'withdrawn', label: '已下架' },
];

/** 我的商品筛选类型选项。 */
export const MY_LISTING_ITEM_TYPE_OPTIONS = [
  { value: 'all', label: '全部类型' },
  { value: 'physical', label: '实体商品' },
  { value: 'virtual', label: '虚拟商品' },
];

/** 我的商品列表支持的排序选项。 */
export const MY_LISTING_SORT_OPTIONS = [
  { value: 'updated_desc', label: '最近更新' },
  { value: 'updated_asc', label: '最早更新' },
  { value: 'published_desc', label: '最近发布' },
  { value: 'published_asc', label: '最早发布' },
  { value: 'price_asc', label: '价格从低到高' },
  { value: 'price_desc', label: '价格从高到低' },
];
