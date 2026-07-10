interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  ariaLabel: string;
}

type PaginationItem = number | 'ellipsis-start' | 'ellipsis-end';

/**
 * 计算紧凑分页窗口，只保留首尾页和当前页附近页码。
 */
const getPaginationItems = (currentPage: number, totalPages: number): PaginationItem[] => {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  const items: PaginationItem[] = [1];
  const start = Math.max(2, Math.min(currentPage - 1, totalPages - 4));
  const end = Math.min(totalPages - 1, Math.max(currentPage + 1, 5));

  if (start > 2) items.push('ellipsis-start');
  for (let page = start; page <= end; page += 1) items.push(page);
  if (end < totalPages - 1) items.push('ellipsis-end');
  items.push(totalPages);

  return items;
};

/**
 * 全站通用分页器，避免大数据量时一次渲染成千上万个页码按钮。
 */
export const Pagination = ({
  currentPage,
  totalPages,
  onPageChange,
  ariaLabel,
}: PaginationProps) => {
  if (totalPages <= 1) return null;

  return (
    <nav className="pagination" aria-label={ariaLabel}>
      <button
        type="button"
        disabled={currentPage === 1}
        onClick={() => onPageChange(currentPage - 1)}
        className="page-btn page-btn-direction"
        aria-label="上一页"
      >
        上页
      </button>

      {getPaginationItems(currentPage, totalPages).map((item) =>
        typeof item === 'number' ? (
          <button
            key={item}
            type="button"
            onClick={() => onPageChange(item)}
            className={`page-btn ${currentPage === item ? 'active' : ''}`}
            aria-label={`第 ${item} 页`}
            aria-current={currentPage === item ? 'page' : undefined}
          >
            {item}
          </button>
        ) : (
          <span key={item} className="pagination-ellipsis" aria-hidden="true">
            …
          </span>
        )
      )}

      <button
        type="button"
        disabled={currentPage === totalPages}
        onClick={() => onPageChange(currentPage + 1)}
        className="page-btn page-btn-direction"
        aria-label="下一页"
      >
        下页
      </button>
    </nav>
  );
};
