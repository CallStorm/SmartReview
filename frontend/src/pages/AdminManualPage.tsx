import './AdminManualPage.css'

import { ReadOutlined } from '@ant-design/icons'
import { Alert, Anchor, Card, Table, Typography } from 'antd'
import { useCallback, useEffect } from 'react'
import PageShell from '../components/PageShell'
import {
  adminManualSections,
  flattenManualAnchors,
  type ManualSection,
  type ManualTable,
} from '../config/adminManualContent'

const { Paragraph, Text } = Typography

function renderTable(table: ManualTable, index: number) {
  return (
    <div key={index} className="admin-manual__table-block">
      <Table
        columns={table.headers.map((header, colIndex) => ({
          title: header,
          dataIndex: String(colIndex),
          key: String(colIndex),
        }))}
        dataSource={table.rows.map((row, rowIndex) => ({
          key: String(rowIndex),
          ...Object.fromEntries(row.map((cell, colIndex) => [String(colIndex), cell])),
        }))}
        rowKey="key"
        pagination={false}
        size="middle"
        scroll={{ x: 'max-content' }}
      />
    </div>
  )
}

function SectionBody({ section }: { section: ManualSection }) {
  return (
    <>
      {section.intro ? <Paragraph className="admin-manual__intro">{section.intro}</Paragraph> : null}

      {section.steps && section.steps.length > 0 ? (
        <ol className="admin-manual__steps">
          {section.steps.map((step, index) => (
            <li key={step.title}>
              <Text strong>
                {index + 1}. {step.title}
              </Text>
              <Paragraph className="admin-manual__step-text">{step.content}</Paragraph>
            </li>
          ))}
        </ol>
      ) : null}

      {section.tables?.map(renderTable)}

      {section.notes && section.notes.length > 0 ? (
        <div className="admin-manual__notes">
          {section.notes.map((note) => (
            <Alert key={note} type="info" showIcon message={note} />
          ))}
        </div>
      ) : null}

      {section.image ? (
        <figure className="admin-manual__figure">
          <img src={section.image.src} alt={section.image.caption} loading="lazy" />
          <figcaption>{section.image.caption}</figcaption>
        </figure>
      ) : null}
    </>
  )
}

const SCROLL_OFFSET = 24

function getScrollContainer(): HTMLElement {
  const el = document.querySelector('.app-outlet--scroll')
  return el instanceof HTMLElement ? el : document.documentElement
}

function scrollToSection(id: string) {
  const target = document.getElementById(id)
  const container = getScrollContainer()
  if (!target) return

  if (container === document.documentElement) {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' })
    return
  }

  const containerTop = container.getBoundingClientRect().top
  const targetTop = target.getBoundingClientRect().top
  const top = container.scrollTop + (targetTop - containerTop) - SCROLL_OFFSET
  container.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
}

function ManualSectionCard({ section, nested }: { section: ManualSection; nested?: boolean }) {
  return (
    <section
      id={section.id}
      className={`admin-manual__section-wrap${nested ? ' admin-manual__section-wrap--nested' : ''}`}
    >
      <Card
        title={section.title}
        className={`admin-manual__section${nested ? ' admin-manual__section--nested' : ''}`}
        size={nested ? 'small' : 'default'}
      >
        <SectionBody section={section} />
        {section.subsections?.map((sub) => (
          <div key={sub.id} style={{ marginTop: nested ? 12 : 16 }}>
            <ManualSectionCard section={sub} nested />
          </div>
        ))}
      </Card>
    </section>
  )
}

export default function AdminManualPage() {
  const getContainer = useCallback(() => getScrollContainer(), [])

  const anchorItems = flattenManualAnchors(adminManualSections).map((item) => ({
    key: item.id,
    href: `#${item.id}`,
    title: item.title,
  }))

  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, '')
    if (!hash) return
    const timer = window.setTimeout(() => scrollToSection(hash), 0)
    return () => window.clearTimeout(timer)
  }, [])

  return (
    <PageShell
      icon={<ReadOutlined />}
      description="系统配置、模板规则与运维操作完整指南"
    >
      <div className="admin-manual">
        <nav className="admin-manual__nav" aria-label="手册目录">
          <Anchor
            items={anchorItems}
            getContainer={getContainer}
            targetOffset={SCROLL_OFFSET}
            onClick={(event, link) => {
              event.preventDefault()
              const id = link.href.replace(/^#/, '')
              scrollToSection(id)
              window.history.replaceState(null, '', `#${id}`)
            }}
          />
        </nav>
        <div className="admin-manual__content">
          {adminManualSections.map((section) => (
            <ManualSectionCard key={section.id} section={section} />
          ))}
        </div>
      </div>
    </PageShell>
  )
}
