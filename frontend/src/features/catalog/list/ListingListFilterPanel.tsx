import type React from 'react';
import { Search } from 'lucide-react';

import { Button, Input, Select } from '../../../components/ui';
import type { Category } from '../../../types/listings';
import { LISTING_SORT_OPTIONS } from './options';

interface ListingListFilterPanelProps {
  categories: Category[];
  searchText: string;
  currentCategory: string;
  itemType: string;
  tempMinPrice: string;
  tempMaxPrice: string;
  tempPublishedAfter: string;
  tempPublishedBefore: string;
  currentSort: string;
  onSearchTextChange: (value: string) => void;
  onTempMinPriceChange: (value: string) => void;
  onTempMaxPriceChange: (value: string) => void;
  onTempPublishedAfterChange: (value: string) => void;
  onTempPublishedBeforeChange: (value: string) => void;
  onSearchSubmit: (event: React.FormEvent) => void;
  onPriceSubmit: (event: React.FormEvent) => void;
  onPublishedSubmit: (event: React.FormEvent) => void;
  onUpdateQueryParam: (params: Record<string, string | number | null>) => void;
}

export const ListingListFilterPanel: React.FC<ListingListFilterPanelProps> = ({
  categories,
  searchText,
  currentCategory,
  itemType,
  tempMinPrice,
  tempMaxPrice,
  tempPublishedAfter,
  tempPublishedBefore,
  currentSort,
  onSearchTextChange,
  onTempMinPriceChange,
  onTempMaxPriceChange,
  onTempPublishedAfterChange,
  onTempPublishedBeforeChange,
  onSearchSubmit,
  onPriceSubmit,
  onPublishedSubmit,
  onUpdateQueryParam,
}) => (
  <aside className="filter-panel">
    {/* 搜索关键字筛选。 */}
    <div className="filter-section">
      <h3 className="filter-section-title">搜索</h3>
      <form onSubmit={onSearchSubmit} className="filter-search-form">
        <Input
          id="search"
          icon={<Search size={18} />}
          placeholder="搜索商品..."
          value={searchText}
          onChange={(e) => onSearchTextChange(e.target.value)}
        />
        <Button type="submit" variant="primary" size="sm" aria-label="搜索">
          <Search size={16} />
        </Button>
      </form>
    </div>

    {/* 分类筛选。 */}
    <div className="filter-section">
      <h3 className="filter-section-title">商品分类</h3>
      <ul className="category-list">
        <li>
          <button
            onClick={() => onUpdateQueryParam({ category: 'all' })}
            className={`category-item-btn ${currentCategory === 'all' ? 'active' : ''}`}
          >
            全部商品
          </button>
        </li>
        {categories.map((cat) => (
          <li key={cat.id}>
            <button
              onClick={() => onUpdateQueryParam({ category: cat.id })}
              className={`category-item-btn ${currentCategory === String(cat.id) ? 'active' : ''}`}
            >
              {cat.name}
            </button>
          </li>
        ))}
      </ul>
    </div>

    {/* 商品交付类别筛选。 */}
    <div className="filter-section">
      <h3 className="filter-section-title">交付类别</h3>
      <div className="segmented-control">
        <button
          onClick={() => onUpdateQueryParam({ item_type: 'all' })}
          className={`segment-btn ${itemType === 'all' ? 'active' : ''}`}
        >
          全部
        </button>
        <button
          onClick={() => onUpdateQueryParam({ item_type: 'physical' })}
          className={`segment-btn ${itemType === 'physical' ? 'active' : ''}`}
        >
          实体
        </button>
        <button
          onClick={() => onUpdateQueryParam({ item_type: 'virtual' })}
          className={`segment-btn ${itemType === 'virtual' ? 'active' : ''}`}
        >
          虚拟
        </button>
      </div>
    </div>

    {/* 价格区间筛选。 */}
    <div className="filter-section">
      <h3 className="filter-section-title">价格区间 (元)</h3>
      <form onSubmit={onPriceSubmit}>
        <div className="price-range-inputs">
          <div className="price-input-wrapper">
            <span className="price-currency">¥</span>
            <input
              type="number"
              className="form-control price-control"
              placeholder="最低"
              value={tempMinPrice}
              onChange={(e) => onTempMinPriceChange(e.target.value)}
            />
          </div>
          <span className="price-range-divider">-</span>
          <div className="price-input-wrapper">
            <span className="price-currency">¥</span>
            <input
              type="number"
              className="form-control price-control"
              placeholder="最高"
              value={tempMaxPrice}
              onChange={(e) => onTempMaxPriceChange(e.target.value)}
            />
          </div>
        </div>
        <Button type="submit" variant="outline" size="sm" fullWidth className="price-apply-btn">
          应用区间
        </Button>
      </form>
    </div>

    {/* 发布时间区间筛选。 */}
    <div className="filter-section">
      <h3 className="filter-section-title">发布时间</h3>
      <form onSubmit={onPublishedSubmit}>
        <div className="published-range-inputs">
          <label className="filter-field-label" htmlFor="published_after">
            起始时间
          </label>
          <input
            id="published_after"
            type="datetime-local"
            className="form-control"
            value={tempPublishedAfter}
            onChange={(e) => onTempPublishedAfterChange(e.target.value)}
          />
          <label className="filter-field-label" htmlFor="published_before">
            截止时间
          </label>
          <input
            id="published_before"
            type="datetime-local"
            className="form-control"
            value={tempPublishedBefore}
            onChange={(e) => onTempPublishedBeforeChange(e.target.value)}
          />
        </div>
        <Button type="submit" variant="outline" size="sm" fullWidth className="published-apply-btn">
          应用时间
        </Button>
      </form>
    </div>

    {/* 排序筛选。 */}
    <div className="filter-section">
      <h3 className="filter-section-title">排序方式</h3>
      <div className="filter-sort-select">
        <Select
          id="sort"
          options={LISTING_SORT_OPTIONS}
          value={currentSort}
          onChange={(e) => onUpdateQueryParam({ sort: e.target.value })}
        />
      </div>
    </div>
  </aside>
);
