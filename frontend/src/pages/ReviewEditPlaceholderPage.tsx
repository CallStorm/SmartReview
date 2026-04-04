import { ArrowLeftOutlined } from '@ant-design/icons'
import { Alert, Button, Spin, Tooltip, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { OnlyofficeEditorConfigResponse, ReviewTask } from '../api/types'

const EDITOR_DIV_ID = 'onlyoffice-editor-root'

declare global {
  interface Window {
    DocsAPI?: {
      DocEditor: new (
        id: string,
        cfg: Record<string, unknown>,
      ) => { destroyEditor: () => void }
    }
  }
}

function loadOnlyofficeScript(docsUrl: string): Promise<void> {
  const base = docsUrl.replace(/\/$/, '')
  const src = `${base}/web-apps/apps/api/documents/api.js`
  return new Promise((resolve, reject) => {
    if (window.DocsAPI) {
      resolve()
      return
    }
    const existing = document.getElementById('onlyoffice-api-script')
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('脚本加载失败')))
      return
    }
    const script = document.createElement('script')
    script.id = 'onlyoffice-api-script'
    script.src = src
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('无法加载 OnlyOffice 脚本'))
    document.body.appendChild(script)
  })
}

export default function ReviewEditPlaceholderPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const navigate = useNavigate()
  const id = Number(taskId)
  const editorRef = useRef<{ destroyEditor: () => void } | null>(null)
  const [bootError, setBootError] = useState<string | null>(null)

  const { data: task, isLoading: taskLoading } = useQuery({
    queryKey: ['review-task', id],
    queryFn: async () => {
      const { data } = await api.get<ReviewTask>(`/review-tasks/${id}`)
      return data
    },
    enabled: Number.isFinite(id) && id > 0,
  })

  const canEdit = Boolean(task?.output_object_key?.trim())

  const {
    data: ooData,
    isLoading: ooLoading,
    error: ooError,
  } = useQuery({
    queryKey: ['onlyoffice-editor-config', id],
    queryFn: async () => {
      const { data } = await api.get<OnlyofficeEditorConfigResponse>(
        `/review-tasks/${id}/onlyoffice/editor-config`,
      )
      return data
    },
    enabled: Number.isFinite(id) && id > 0 && canEdit,
    retry: false,
  })

  const mountEditor = useCallback(async (payload: OnlyofficeEditorConfigResponse) => {
    const fallback =
      (import.meta.env.VITE_ONLYOFFICE_DOCS_URL as string | undefined) ||
      'http://127.0.0.1:9080'
    const docsBase = (payload.docs_url || fallback).replace(/\/$/, '')
    await loadOnlyofficeScript(docsBase)
    const el = document.getElementById(EDITOR_DIV_ID)
    if (!el || !window.DocsAPI) {
      throw new Error('编辑器容器未就绪')
    }
    if (editorRef.current) {
      editorRef.current.destroyEditor()
      editorRef.current = null
    }
    editorRef.current = new window.DocsAPI.DocEditor(EDITOR_DIV_ID, {
      ...payload.config,
      token: payload.token,
      width: '100%',
      height: '100%',
    })
  }, [])

  useEffect(() => {
    if (!ooData) return
    setBootError(null)
    let cancelled = false
    void mountEditor(ooData).catch((e: unknown) => {
      if (!cancelled) {
        setBootError(e instanceof Error ? e.message : '加载编辑器失败')
      }
    })
    return () => {
      cancelled = true
      if (editorRef.current) {
        editorRef.current.destroyEditor()
        editorRef.current = null
      }
    }
  }, [ooData, mountEditor])

  if (!Number.isFinite(id) || id <= 0) {
    return (
      <div style={{ padding: 24 }}>
        <Typography.Text type="danger">无效的任务 ID</Typography.Text>
      </div>
    )
  }

  const axDetail = axios.isAxiosError(ooError)
    ? (ooError.response?.data as { detail?: string } | undefined)?.detail
    : undefined

  const backTarget = `/review/${taskId}/manual`

  return (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'stretch',
        overflow: 'hidden',
        background: '#fff',
      }}
    >
      <aside
        style={{
          width: 48,
          flexShrink: 0,
          display: 'flex',
          justifyContent: 'center',
          paddingTop: 10,
          borderRight: '1px solid var(--ant-color-border-secondary)',
          background: '#fafafa',
        }}
      >
        <Tooltip title="返回审阅">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(backTarget)}
            aria-label="返回审阅"
            className="app-collapse-btn"
            style={{ width: 40, height: 40 }}
          />
        </Tooltip>
      </aside>

      <div
        style={{
          flex: 1,
          minWidth: 0,
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {taskLoading ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Spin />
          </div>
        ) : !canEdit ? (
          <div style={{ padding: 24, overflow: 'auto' }}>
            <Alert
              type="info"
              showIcon
              message="暂无可编辑文档"
              description="任务尚未生成带批注的结果 Word，请待审核完成后再试。"
            />
          </div>
        ) : ooLoading ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Spin tip="正在准备编辑器…" />
          </div>
        ) : ooError ? (
          <div style={{ padding: 24, overflow: 'auto' }}>
            <Alert
              type="error"
              showIcon
              message="无法启动编辑器"
              description={
                axDetail ||
                (ooError instanceof Error ? ooError.message : '请检查系统设置中的 OnlyOffice 配置')
              }
            />
          </div>
        ) : bootError ? (
          <div style={{ padding: 24, overflow: 'auto' }}>
            <Alert type="error" showIcon message={bootError} />
          </div>
        ) : (
          <div id={EDITOR_DIV_ID} style={{ flex: 1, minHeight: 0, minWidth: 0 }} />
        )}
      </div>
    </div>
  )
}
