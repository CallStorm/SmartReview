/** 顶栏与页面标题：与侧栏文案对齐 */
export function resolvePageTitle(pathname: string): string {
  if (pathname === '/schemes') return '方案类型管理'
  if (pathname === '/review') return '方案审核'
  if (/^\/review\/[^/]+\/manual$/.test(pathname)) return '人工审阅'
  if (/^\/review\/[^/]+\/edit$/.test(pathname)) return '文档编辑'
  if (pathname === '/basis') return '编制依据管理'
  if (pathname === '/templates') return '模板管理'
  if (pathname === '/settings') return '设置'
  if (pathname === '/users') return '用户管理'
  return '施工方案审核系统'
}
