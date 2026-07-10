export interface TabItem<T extends string> {
  value: T;
  label: string;
  count?: number;
}

interface TabsProps<T extends string> {
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  className?: string;
}

/**
 * 通用标签切换控件，通过标准 tab 语义支持键盘和辅助技术识别。
 */
export const Tabs = <T extends string>({
  items,
  value,
  onChange,
  ariaLabel,
  className = '',
}: TabsProps<T>) => (
  <div className={`ui-tabs ${className}`.trim()} role="tablist" aria-label={ariaLabel}>
    {items.map((item) => {
      const isActive = item.value === value;

      return (
        <button
          key={item.value}
          type="button"
          role="tab"
          aria-selected={isActive}
          className={`ui-tab ${isActive ? 'active' : ''}`}
          onClick={() => onChange(item.value)}
        >
          <span>{item.label}</span>
          {typeof item.count === 'number' && <span className="ui-tab-count">{item.count}</span>}
        </button>
      );
    })}
  </div>
);
