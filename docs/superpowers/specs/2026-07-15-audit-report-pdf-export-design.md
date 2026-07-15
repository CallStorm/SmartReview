# 审核报告改导出 PDF

日期：2026-07-15  
状态：已认可

## 背景与目标

当前「审核报告」通过 `GET /review-tasks/{id}/audit-report` 导出为可编辑的 DOCX（`python-docx` 生成）。用户下载后可随意二次修改报告内容。

目标：将该导出改为 **PDF**，打开可读、日常难以编辑；内容与现有 Word 报告同构。

## 范围

- 仅「审核报告」导出路径。
- 「导出方案 / 导出 Word」（带批注方案 DOCX）不变。
- OnlyOffice 预览/编辑不变。

非目标：水印、打开密码、双格式（PDF+DOCX）并存、MinIO 缓存 PDF、DRM。

## 决策摘要

| 维度 | 决定 |
|---|---|
| 导出格式 | PDF，替代 DOCX（不再对外提供该报告 Word） |
| 生成方式 | ReportLab 直接绘制 |
| 中文字体 | 仓库内置 Noto Sans SC（SIL OFL） |
| 水印 | 无 |
| 防编辑 | PDF + 文档权限（禁止修改/组装；打开无需密码） |
| 内容 | 与现 `build_audit_report_docx` 章节结构一致 |
| 生成时机 | 仍即时生成、流式返回 |

## 架构

```
ReviewPage → GET /audit-report → build_audit_report_pdf
                                       ↓
                         review_report_content（章节/表格数据）
                                       ↓
                         ReportLab + 内置中文字体 → application/pdf
```

- 共享模块 `review_report_content.py`：issue/步骤表格行组装、摘要等纯数据逻辑。
- `review_report_pdf.py`：`build_audit_report_pdf(...) -> bytes`。
- 删除对外 DOCX 生成路径。

## API / 前端

- 端点不变；`media_type` 改为 `application/pdf`。
- 文件名：`{basename}_审核报告.pdf`。
- 前端 `reviewExportFilename` 后缀改为 `.pdf`。

## 诚实边界

PDF 与权限位可显著降低随意二次编辑；专业工具仍可能修改，不承诺绝对防篡改。

## 验收

1. 下载得到 `*_审核报告.pdf`，中文可读，结构与旧 Word 一致。
2. 打开无需密码；普通编辑受限或明显困难。
3. 「导出方案」仍为 DOCX。
4. 相关 pytest 通过。
