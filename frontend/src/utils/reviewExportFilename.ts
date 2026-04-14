/** 导出带批注报告：上传文件名去扩展名 + `_审核.docx` */
export function buildReviewExportFilename(originalFilename: string): string {
  const raw = (originalFilename || '').trim() || 'document'
  const base = raw.replace(/\.docx$/i, '')
  const safe = base.replace(/[\\/:*?"<>|]/g, '_').trim() || 'document'
  return `${safe}_审核.docx`
}
