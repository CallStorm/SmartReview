import type { TablePaginationConfig } from 'antd/es/table/interface'

/** 各页表格统一分页：默认每页 5 条，切换项与中文汇总文案 */
export const DEFAULT_TABLE_PAGINATION: TablePaginationConfig = {
  defaultPageSize: 5,
  showSizeChanger: true,
  pageSizeOptions: ['5', '10', '20', '50', '100'],
  showTotal: (total, range) =>
    `${range[0]}-${range[1]} 条，共 ${total} 条`,
}
