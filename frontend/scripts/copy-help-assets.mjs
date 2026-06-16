import { copyFileSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const frontendRoot = resolve(__dirname, '..')
const defaultDocsRoot = resolve(frontendRoot, '..', 'docs')
const docsRoot = process.env.DOCS_SOURCE || defaultDocsRoot
const outDir = join(frontendRoot, 'public', 'help', 'assets')

/** @type {{ src: string; dest: string }[]} */
const ASSET_MAP = [
  { src: '格式调整操作视频.mp4', dest: 'format-adjustment.mp4' },
  { src: '沙泘沱高支模专项施工方案.docx', dest: 'sample-high-support-formwork.docx' },
]

mkdirSync(outDir, { recursive: true })

let copied = 0
for (const { src, dest } of ASSET_MAP) {
  const sourcePath = join(docsRoot, src)
  const targetPath = join(outDir, dest)
  if (!existsSync(sourcePath)) {
    console.warn(`[copy-help-assets] skip missing: ${sourcePath}`)
    continue
  }
  copyFileSync(sourcePath, targetPath)
  copied += 1
  console.log(`[copy-help-assets] ${src} -> public/help/assets/${dest}`)
}

console.log(`[copy-help-assets] done (${copied}/${ASSET_MAP.length} files)`)
