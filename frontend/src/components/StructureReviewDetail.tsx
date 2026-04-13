import { FileTextOutlined, RedoOutlined } from '@ant-design/icons'
import {
  App as AntApp,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Modal,
  Row,
  Space,
  Tag,
  Timeline,
  Tooltip,
  Tree,
  Typography,
} from 'antd'
import type { DataNode } from 'antd/es/tree'
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type {
  ReportIssue,
  ReportStep,
  ReviewTask,
  TemplateNode,
  TemplatePublic,
} from '../api/types'

function asStringArray(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.map((x) => String(x ?? '')).filter(Boolean)
}

function structureKind(issue: ReportIssue): string {
  return String(issue.related?.kind ?? '')
}

function aggregateStructureIssues(issues: ReportIssue[]) {
  let missing = 0
  let order = 0
  let extra = 0
  for (const it of issues) {
    const k = structureKind(it)
    if (k === 'missing_section') missing += 1
    else if (k === 'order_mismatch') order += 1
    else if (k === 'extra_section') extra += 1
  }
  return { missing, order, extra, total: issues.length }
}

const KIND_LABEL: Record<string, string> = {
  missing_section: '缺失',
  order_mismatch: '顺序不当',
  extra_section: '多余章节',
}

const KIND_DETAIL: Record<string, string> = {
  missing_section: '必备章节缺失',
  order_mismatch: '章节顺序与模板不一致',
  extra_section: '文档中多出模板未要求的章节',
}

function templateNodesToTreeData(nodes: TemplateNode[]): DataNode[] {
  return nodes.map((n) => ({
    key: n.id,
    title: n.title,
    children:
      n.children && n.children.length > 0
        ? templateNodesToTreeData(n.children)
        : undefined,
  }))
}

function findKeyPath(
  nodes: TemplateNode[],
  targetId: string,
  acc: string[] = [],
): string[] | null {
  for (const n of nodes) {
    const cur = [...acc, n.id]
    if (n.id === targetId) return cur
    const ch = n.children
    if (ch?.length) {
      const found = findKeyPath(ch, targetId, cur)
      if (found) return found
    }
  }
  return null
}

export interface StructureReviewDetailProps {
  task: ReviewTask
  step: ReportStep
  onNavigateEdit: () => void
}

export default function StructureReviewDetail({
  task,
  step,
  onNavigateEdit,
}: StructureReviewDetailProps) {
  const { message } = AntApp.useApp()
  const [templateOpen, setTemplateOpen] = useState(false)
  const [focusTemplateNodeId, setFocusTemplateNodeId] = useState<string | null>(
    null,
  )

  const canExportWord = Boolean(task.output_object_key?.trim())

  const stats = useMemo(
    () => aggregateStructureIssues(step.issues),
    [step.issues],
  )

  const { data: templateData, isLoading: templateLoading } = useQuery({
    queryKey: ['scheme-template', task.scheme_type_id, templateOpen],
    queryFn: async () => {
      const { data } = await api.get<TemplatePublic>(
        `/scheme-types/${task.scheme_type_id}/template`,
      )
      return data
    },
    enabled: templateOpen,
  })

  const templateRoots = templateData?.parsed_structure?.nodes ?? []
  const treeData = useMemo(
    () => templateNodesToTreeData(templateRoots),
    [templateRoots],
  )

  const { expandedKeys, selectedKeys } = useMemo(() => {
    if (!focusTemplateNodeId || templateRoots.length === 0) {
      return { expandedKeys: [] as string[], selectedKeys: [] as string[] }
    }
    const path = findKeyPath(templateRoots, focusTemplateNodeId)
    if (!path?.length) {
      return { expandedKeys: [] as string[], selectedKeys: [] as string[] }
    }
    const parents = path.slice(0, -1)
    return {
      expandedKeys: parents,
      selectedKeys: [focusTemplateNodeId],
    }
  }, [focusTemplateNodeId, templateRoots])

  const openTemplateModal = (templateNodeId?: string) => {
    setFocusTemplateNodeId(templateNodeId?.trim() ? templateNodeId : null)
    setTemplateOpen(true)
  }

  const handleDownloadTemplateWord = async () => {
    try {
      const { data } = await api.get<{ url: string }>(
        `/scheme-types/${task.scheme_type_id}/template/download-url`,
      )
      window.open(data.url, '_blank', 'noopener,noreferrer')
    } catch {
      message.warning('无法获取模板下载链接')
    }
  }

  const statusBannerStyle: CSSProperties = step.passed
    ? {
        borderRadius: 8,
        padding: '14px 16px',
        marginBottom: 16,
        background: '#f6ffed',
        border: '1px solid #b7eb8f',
      }
    : {
        borderRadius: 8,
        padding: '14px 16px',
        marginBottom: 16,
        background: '#fff2f0',
        border: '1px solid #ffccc7',
      }

  const statusTitle = step.passed
    ? '审核结果：文档结构符合模板要求'
    : `审核结果：文档结构不合规（共 ${stats.total} 项问题${
        stats.missing ? `，缺失 ${stats.missing} 项` : ''
      }${stats.order ? `，顺序问题 ${stats.order} 项` : ''}${
        stats.extra ? `，多余章节 ${stats.extra} 项` : ''
      }）`

  const templateModalBody =
    templateLoading ? (
      <Typography.Text type="secondary">加载中…</Typography.Text>
    ) : treeData.length === 0 ? (
      <Typography.Text type="secondary">暂无解析后的模板结构</Typography.Text>
    ) : (
      <Tree
        key={focusTemplateNodeId ?? 'expand-all'}
        showLine
        treeData={treeData}
        defaultExpandAll={!focusTemplateNodeId}
        defaultExpandedKeys={
          focusTemplateNodeId && expandedKeys.length ? expandedKeys : undefined
        }
        defaultSelectedKeys={
          selectedKeys.length ? selectedKeys : undefined
        }
      />
    )

  const templateModal = (
    <Modal
      title="模板章节结构"
      open={templateOpen}
      onCancel={() => setTemplateOpen(false)}
      width={720}
      footer={[
        <Button key="dl" onClick={() => void handleDownloadTemplateWord()}>
          下载模板 Word
        </Button>,
        <Button key="close" type="primary" onClick={() => setTemplateOpen(false)}>
          关闭
        </Button>,
      ]}
    >
      {templateModalBody}
    </Modal>
  )

  if (step.passed || step.issues.length === 0) {
    return (
      <>
        <div style={statusBannerStyle}>
          <Typography.Text strong style={{ fontSize: 15 }}>
            {statusTitle}
          </Typography.Text>
          <div style={{ marginTop: 8 }}>
            <Typography.Text type="secondary">{step.summary}</Typography.Text>
          </div>
          <Space style={{ marginTop: 12 }} wrap>
            <Tooltip title="请重新在方案审核页上传文档以发起新的检测">
              <Button icon={<RedoOutlined />} disabled>
                重新检测
              </Button>
            </Tooltip>
            <Button
              icon={<FileTextOutlined />}
              onClick={() => openTemplateModal()}
            >
              查看模板结构
            </Button>
          </Space>
        </div>
        {templateModal}
      </>
    )
  }

  return (
    <>
    <div>
      <div style={statusBannerStyle}>
        <Typography.Text strong style={{ fontSize: 15 }}>
          {statusTitle}
        </Typography.Text>
        <Typography.Paragraph
          style={{ marginTop: 8, marginBottom: 0 }}
          type="secondary"
        >
          请按照《{task.scheme_name}》标准模板检查并调整以下章节。
        </Typography.Paragraph>
        <Typography.Paragraph style={{ marginBottom: 0 }} type="secondary">
          {step.summary}
        </Typography.Paragraph>
        <Space style={{ marginTop: 12 }} wrap>
          <Tooltip title="请重新在方案审核页上传文档以发起新的检测">
            <Button icon={<RedoOutlined />} disabled>
              重新检测
            </Button>
          </Tooltip>
          <Button
            icon={<FileTextOutlined />}
            onClick={() => openTemplateModal()}
          >
            查看模板结构
          </Button>
        </Space>
      </div>

      <Typography.Title level={5} style={{ marginTop: 8 }}>
        问题时间轴
      </Typography.Title>
      <Timeline
        style={{ marginBottom: 20 }}
        items={step.issues.map((it) => {
          const kind = structureKind(it)
          const path = asStringArray(it.anchor?.title_path)
          const tail = path.length ? path[path.length - 1] : it.message
          const color =
            kind === 'missing_section'
              ? 'red'
              : kind === 'order_mismatch'
                ? 'orange'
                : 'gray'
          return {
            color,
            children: (
              <div>
                <Typography.Text strong>{tail}</Typography.Text>
                <div>
                  <Tag color={it.severity === 'error' ? 'red' : 'gold'}>
                    {KIND_LABEL[kind] ?? kind}
                  </Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                    {path.join(' > ')}
                  </Typography.Text>
                </div>
              </div>
            ),
          }
        })}
      />

      <Typography.Title level={5}>待处理项</Typography.Title>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {step.issues.map((it, idx) => {
          const kind = structureKind(it)
          const path = asStringArray(it.anchor?.title_path)
          const pathStr = path.join(' > ')
          const expectedTitle =
            kind === 'extra_section'
              ? '（模板不要求此位置出现该章节）'
              : pathStr || '—'
          const userTitle =
            typeof it.anchor?.user_title === 'string'
              ? it.anchor.user_title
              : ''
          let docLine = it.message
          if (kind === 'missing_section') {
            docLine = '未在文档中找到与模板对应的章节标题'
          } else if (kind === 'extra_section') {
            docLine = userTitle
              ? `文档中出现：「${userTitle}」`
              : '文档中多出章节'
          }
          const tidRaw = it.anchor?.template_node_id
          const templateNodeId =
            tidRaw !== undefined && tidRaw !== null ? String(tidRaw) : ''

          const techItems = [
            pathStr
              ? { key: 'tp', label: 'title_path', children: pathStr }
              : null,
            templateNodeId
              ? { key: 'tid', label: 'template_node_id', children: templateNodeId }
              : null,
            it.anchor?.heading_para_index !== undefined
              ? {
                  key: 'hpi',
                  label: 'heading_para_index',
                  children: String(it.anchor.heading_para_index),
                }
              : null,
          ].filter(Boolean) as { key: string; label: string; children: string }[]

          return (
            <Card
              key={it.issue_id || `struct-${idx}`}
              size="small"
              style={{
                boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
                borderRadius: 8,
              }}
              title={
                <Space wrap>
                  <Tag color={it.severity === 'error' ? 'red' : 'gold'}>
                    {it.severity === 'error' ? '严重' : '警告'}
                  </Tag>
                  <Tag>{KIND_DETAIL[kind] ?? KIND_LABEL[kind] ?? kind}</Tag>
                </Space>
              }
            >
              <Row gutter={[16, 12]}>
                <Col xs={24} md={12}>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    模板要求
                  </Typography.Text>
                  <Typography.Paragraph style={{ marginBottom: 0, marginTop: 4 }}>
                    {expectedTitle}
                  </Typography.Paragraph>
                </Col>
                <Col xs={24} md={12}>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    实际检测
                  </Typography.Text>
                  <div style={{ marginTop: 4 }}>
                    <Tag
                      color={
                        kind === 'missing_section'
                          ? 'red'
                          : kind === 'order_mismatch'
                            ? 'orange'
                            : 'default'
                      }
                    >
                      {KIND_LABEL[kind] ?? kind}
                    </Tag>
                    <Typography.Paragraph style={{ marginBottom: 0 }}>
                      {docLine}
                    </Typography.Paragraph>
                  </div>
                </Col>
              </Row>
              <Space style={{ marginTop: 12 }} wrap>
                <Button
                  size="small"
                  icon={<FileTextOutlined />}
                  onClick={() =>
                    openTemplateModal(templateNodeId || undefined)
                  }
                >
                  查看模板规范
                </Button>
                <Tooltip
                  title={
                    canExportWord
                      ? '打开在线编辑器补全章节'
                      : '结构审核未通过时暂无批注稿，请在本地按模板修改 Word 后，在方案审核页重新上传'
                  }
                >
                  <Button
                    size="small"
                    type="primary"
                    disabled={!canExportWord}
                    onClick={onNavigateEdit}
                  >
                    立即前往补全
                  </Button>
                </Tooltip>
              </Space>
              {techItems.length > 0 ? (
                <Collapse
                  ghost
                  style={{ marginTop: 8 }}
                  items={[
                    {
                      key: 'tech',
                      label: '技术详情',
                      children: (
                        <Descriptions size="small" column={1} items={techItems} />
                      ),
                    },
                  ]}
                />
              ) : null}
            </Card>
          )
        })}
      </Space>
    </div>
    {templateModal}
    </>
  )
}

