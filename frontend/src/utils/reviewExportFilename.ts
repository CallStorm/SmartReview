function sanitizeExportBasename(originalFilename: string): string {
  const raw = (originalFilename || '').trim() || 'document'
  const base = raw.replace(/\.docx$/i, '')
  return base.replace(/[\\/:*?"<>|]/g, '_').trim() || 'document'
}

/** 导出带批注方案：上传文件名去扩展名 + `_审核.docx` */
export function buildReviewExportFilename(originalFilename: string): string {
  return `${sanitizeExportBasename(originalFilename)}_审核.docx`
}

/** 导出审核报告：上传文件名去扩展名 + `_审核报告.docx` */
export function buildAuditReportFilename(originalFilename: string): string {
  return `${sanitizeExportBasename(originalFilename)}_审核报告.docx`
}
