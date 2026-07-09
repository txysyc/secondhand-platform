import type React from 'react';
import { Search } from 'lucide-react';

import { Button, Input, Select } from '../../../components/ui';
import type { Category } from '../../../types/listings';

export const MY_LISTING_STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'draft', label: '草稿' },
  { value: 'active', label: '在售' },
  { value: 'reserved', label: '交易占用' },
  { value: 'withdrawn', label: '已下架' },
];

export const MY_LISTING_ITEM_TYPE_OPTIONS = [
  { value: 'all', label: '全部类型' },
  { value: 'physical', label: '实体商品' },
  { value: 'virtual', label: '虚拟商品' },
];

export const MY_LISTING_SORT_OPTIONS = [
  { value: 'updated_desc', label: '最近更新' },
  { value: 'updated_asc', label: '最早更新' },
  { value: 'published_desc', label: '最近发布' },
  { value: 'published_asc', label: '最早发布' },
  { value: 'price_asc', label: '价格从低到高' },
  { value: 'price_desc', label: '价格从高到低' },
];

interface MyListingsFilterPanelProps {
  categories: Category[];
  searchText: string;
  status: string;
  category: string;
  itemType: string;
  sort: string;
  tempMinPrice: string;
  tempMaxPrice: string;
  onSearchTextChange: (value: string) => void;
  onTempMinPriceChange: (value: string) => void;
  onTempMaxPriceChange: (value: string) => void;
  onFilterSubmit: (event: React.FormEvent) => void;
  onClearFilters: () => void;
  onUpdateQueryParam: (params: Record<string, string | number | null>) => void;
}

export const MyListingsFilterPanel: React.FC<MyListingsFilterPanelProps> = ({
  categories,
  searchText,
  status,
  category,
  itemType,
  sort,
  tempMinPrice,
  tempMaxPrice,
  onSearchTextChange,
  onTempMinPriceChange,
  onTempMaxPriceChange,
  onFilterSubmit,
  onClearFilters,
  onUpdateQueryParam,
}) => (
  <form className="my-listing-filter-panel" onSubmit={onFilterSubmit}>
    {/* 我的商品关键词筛选。 */}
    <Input
      id="my_listing_search"
      icon={<Search size={16} />}
      label="搜索商品"
      placeholder="标题或描述"
      value={searchText}
      onChange={(event) => onSearchTextChange(event.target.value)}
    />
    <Select
      id="my_listing_status"
      label="商品状态"
      options={MY_LISTING_STATUS_OPTIONS}
      value={status}
      onChange={(event) => onUpdateQueryParam({ status: event.target.value })}
    />
    <Select
      id="my_listing_category"
      label="分类"
      options={[{ value: 'all', label: '全部分类' }, ...categories.map((item) => ({ value: item.id, label: item.name }))]}
      value={category}
      onChange={(event) => onUpdateQueryParam({ category: event.target.value })}
    />
    <Select
      id="my_listing_item_type"
      label="类型"
      options={MY_LISTING_ITEM_TYPE_OPTIONS}
      value={itemType}
      onChange={(event) => onUpdateQueryParam({ item_type: event.target.value })}
    />
    <Select
      id="my_listing_sort"
      label="排序"
      options={MY_LISTING_SORT_OPTIONS}
      value={sort}
      onChange={(event) => onUpdateQueryParam({ sort: event.target.value })}
    />
    <Input
      id="my_listing_min_price"
      label="最低价格"
      type="number"
      value={tempMinPrice}
      onChange={(event) => onTempMinPriceChange(event.target.value)}
    />
    <Input
      id="my_listing_max_price"
      label="最高价格"
      type="number"
      value={tempMaxPrice}
      onChange={(event) => onTempMaxPriceChange(event.target.value)}
    />
    <div className="filter-actions-row">
      <Button type="submit" size="sm">
        应用筛选
      </Button>
      <Button type="button" variant="outline" size="sm" onClick={onClearFilters}>
        清空
      </Button>
    </div>
  </form>
);
