import './DashboardPage.css'

import { Bar, Column, Line, Pie } from '@ant-design/plots'
import { BarChartOutlined, FullscreenExitOutlined, FullscreenOutlined } from '@ant-design/icons'
import { App as AntApp, Card, Col, Row, Select, Space, Spin, Statistic } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { DashboardSummary } from '../api/types'
import { formatApiErrorMessage } from '../utils/apiError'

const STATUS_LABEL: Record<string, string> = {
  pending: '等待中',
  processing: '处理中',
  succeeded: '成功',
  failed: '失败',
}

/** G2 轴默认还会套一层 labelOpacity，与半透明 fill 叠乘后对比度不足 */
const CHART_AXIS_LABEL = {
  labelFill: '#262626',
  labelOpacity: 1,
  labelFontSize: 12,
} as const

const chartAxisY = { title: false, ...CHART_AXIS_LABEL } as const
const chartAxisX = { title: false, ...CHART_AXIS_LABEL } as const
const chartLegendText = {
  itemLabelFill: '#262626',
  itemLabelFillOpacity: 1,
  itemLabelFontSize: 12,
} as const

function fillDailySeries(rows: { date: string; count: number }[], days: number) {
  const map = new Map(rows.map((r) => [r.date, r.count]))
  const out: { date: string; count: number }[] = []
  const end = new Date()
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(end)
    d.setUTCDate(d.getUTCDate() - i)
    const key = d.toISOString().slice(0, 10)
    out.push({ date: key, count: map.get(key) ?? 0 })
  }
  return out
}

export default function DashboardPage() {
  const { message } = AntApp.useApp()
  const [days, setDays] = useState(30)
  const [full, setFull] = useState(false)

  const toggleFullscreen = useCallback(() => {
    const el = document.documentElement
    if (!document.fullscreenElement) {
      el.requestFullscreen?.().catch(() => message.warning('无法进入全屏'))
    } else {
      document.exitFullscreen?.()
    }
  }, [message])

  useEffect(() => {
    const onFs = () => setFull(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', onFs)
    return () => document.removeEventListener('fullscreenchange', onFs)
  }, [])

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['admin-dashboard', days],
    queryFn: async () => {
      const { data: body } = await api.get<DashboardSummary>('/admin/dashboard/summary', {
        params: { days },
      })
      return body
    },
    refetchInterval: 60_000,
  })

  useEffect(() => {
    if (isError) {
      message.error(formatApiErrorMessage(error, '加载看板失败'))
    }
  }, [isError, error, message])

  const trendData = useMemo(() => {
    if (!data) return []
    return fillDailySeries(data.tasks_per_day, days)
  }, [data, days])

  const statusPieData = useMemo(() => {
    if (!data) return []
    return data.tasks_by_status.map((s) => ({
      type: STATUS_LABEL[s.status] ?? s.status,
      value: s.count,
    }))
  }, [data])

  const schemeBarData = useMemo(() => {
    if (!data) return []
    return data.tasks_by_scheme_type.map((s) => ({
      label:
        s.scheme_category && s.scheme_name
          ? `${s.scheme_category} · ${s.scheme_name}`
          : s.scheme_name || `类型 #${s.scheme_type_id}`,
      count: s.count,
    }))
  }, [data])

  const difyBarData = useMemo(() => {
    if (!data?.dify.datasets.length) return []
    return [...data.dify.datasets]
      .sort((a, b) => b.segment_count - a.segment_count)
      .slice(0, 12)
      .map((d) => ({
        label: d.name?.trim() || d.id.slice(0, 8),
        count: d.segment_count,
      }))
  }, [data])

  const pct = (v: number | null | undefined) =>
    v == null ? '—' : `${Math.round(v * 1000) / 10}%`

  const refreshedAtText = useMemo(() => {
    if (!data?.refreshed_at) return '等待后台生成首个快照'
    const dt = new Date(data.refreshed_at)
    if (Number.isNaN(dt.getTime())) return data.refreshed_at
    return dt.toLocaleString()
  }, [data?.refreshed_at])

  return (
    <div className="dashboard-wall">
      <div className="dashboard-wall__toolbar">
        <Space align="center" size="middle" wrap>
          <BarChartOutlined style={{ fontSize: 22, color: '#1677ff' }} />
          <span className="dashboard-wall__title">运营概览</span>
          <Select
            value={days}
            onChange={setDays}
            options={[
              { value: 7, label: '近 7 天' },
              { value: 30, label: '近 30 天' },
              { value: 90, label: '近 90 天' },
            ]}
            style={{ width: 120 }}
            getPopupContainer={(n) => n.parentElement ?? document.body}
          />
        </Space>
        <Space>
          <button
            type="button"
            className="ant-btn ant-btn-default"
            onClick={toggleFullscreen}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            {full ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
            {full ? '退出全屏' : '全屏'}
          </button>
        </Space>
      </div>
      <p className="dashboard-wall__hint">
        最近刷新：{refreshedAtText}。任务趋势按 UTC 日历日聚合；完成率 = 成功 / (成功 + 失败)。
      </p>

      {isLoading || !data ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 64 }}>
          <Spin size="large" />
        </div>
      ) : (
        <>
          <Row className="dashboard-wall__kpi-cards-row" gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} sm={12} lg={6}>
              <Card size="small" className="dashboard-wall__kpi-card">
                <Statistic title="审核任务总数" value={data.review_tasks_total} />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card size="small" className="dashboard-wall__kpi-card">
                <Statistic title="今日新建（UTC）" value={data.review_tasks_today} />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card size="small" className="dashboard-wall__kpi-card">
                <Statistic title="近 7 日提交人数" value={data.active_submitters_7d} />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card size="small" className="dashboard-wall__kpi-card">
                <Statistic title="完成率" value={pct(data.completion_rate)} />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card size="small" className="dashboard-wall__kpi-card">
                <Statistic title="注册用户" value={data.users_total} suffix={`/ 管理员 ${data.users_admin}`} />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card size="small" className="dashboard-wall__kpi-card">
                <Statistic title="方案类型" value={data.scheme_types_total} suffix={`/ 模板 ${data.templates_total}`} />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card size="small" className="dashboard-wall__kpi-card">
                <Statistic title="编制依据条目" value={data.basis_items_total} />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card size="small" className="dashboard-wall__kpi-card">
                <div className="dashboard-wall__dify-kpi">
                  <Statistic
                    title="Dify 分片总数"
                    value={
                      data.dify.configured && !data.dify.error ? data.dify.segment_total : '—'
                    }
                    formatter={(val) =>
                      val === '—' ? (
                        '—'
                      ) : (
                        <span className="dashboard-wall__dify-inline-values">
                          <span className="dashboard-wall__dify-metric">
                            <span className="dashboard-wall__dify-metric-label">知识库</span>
                            <span className="dashboard-wall__dify-metric-num">{data.dify.dataset_count}</span>
                            <span className="dashboard-wall__dify-metric-unit">个</span>
                          </span>
                          <span className="dashboard-wall__dify-metric-sep" aria-hidden>
                            ·
                          </span>
                          <span className="dashboard-wall__dify-metric">
                            <span className="dashboard-wall__dify-metric-label">分片</span>
                            <span className="dashboard-wall__dify-metric-num">{val}</span>
                          </span>
                        </span>
                      )
                    }
                  />
                  {!data.dify.configured ? (
                    <div className="dashboard-wall__dify-warn dashboard-wall__dify-warn--emphasis">
                      未配置 Dify
                    </div>
                  ) : data.dify.error ? (
                    <div className="dashboard-wall__dify-warn dashboard-wall__dify-warn--emphasis">
                      {data.dify.error}
                    </div>
                  ) : data.dify.truncated ? (
                    <div className="dashboard-wall__dify-warn">统计已截断</div>
                  ) : null}
                </div>
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} lg={14}>
              <Card title={`近 ${days} 日新建任务（UTC）`} size="small">
                <div className="dashboard-wall__chart">
                  <Line
                    data={trendData}
                    xField="date"
                    yField="count"
                    height={300}
                    autoFit
                    axis={{
                      x: { ...chartAxisX, labelAutoRotate: false },
                      y: {
                        ...chartAxisY,
                        gridStroke: 'rgba(0, 0, 0, 0.08)',
                        gridStrokeOpacity: 1,
                      },
                    }}
                    style={{ stroke: '#1677ff', lineWidth: 2 }}
                  />
                </div>
              </Card>
            </Col>
            <Col xs={24} lg={10}>
              <Card title="任务状态分布" size="small">
                <div className="dashboard-wall__chart">
                  {statusPieData.length === 0 ? (
                    <div className="dashboard-wall__empty">暂无任务</div>
                  ) : (
                    <Pie
                      data={statusPieData}
                      angleField="value"
                      colorField="type"
                      height={300}
                      autoFit
                      label={{
                        text: (d: { type: string; value: number }) => `${d.type} ${d.value}`,
                        style: {
                          fill: '#1f1f1f',
                          fillOpacity: 1,
                          fontSize: 12,
                          fontWeight: 600,
                        },
                      }}
                      legend={{
                        color: chartLegendText,
                      }}
                    />
                  )}
                </div>
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card title="方案类型任务量 Top" size="small">
                <div className="dashboard-wall__chart">
                  {schemeBarData.length === 0 ? (
                    <div className="dashboard-wall__empty">暂无数据</div>
                  ) : (
                    <Bar
                      data={schemeBarData}
                      xField="count"
                      yField="label"
                      height={320}
                      autoFit
                      transpose
                      axis={{
                        x: {
                          ...chartAxisX,
                          labelAutoRotate: false,
                          labelAutoEllipsis: true,
                        },
                        y: {
                          ...chartAxisY,
                          gridStroke: 'rgba(0, 0, 0, 0.08)',
                          gridStrokeOpacity: 1,
                        },
                      }}
                      style={{ fill: '#52c41a' }}
                    />
                  )}
                </div>
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card title="Dify 知识库分片数" size="small">
                <div className="dashboard-wall__chart">
                  {!data.dify.configured || data.dify.error ? (
                    <div className="dashboard-wall__empty dashboard-wall__dify-warn--emphasis">
                      {data.dify.error || '未配置或无法获取 Dify 数据'}
                    </div>
                  ) : difyBarData.length === 0 ? (
                    <div className="dashboard-wall__empty">暂无知识库</div>
                  ) : (
                    <Column
                      data={difyBarData}
                      xField="label"
                      yField="count"
                      height={320}
                      autoFit
                      axis={{
                        x: {
                          ...chartAxisX,
                          labelAutoRotate: false,
                          labelAutoEllipsis: true,
                        },
                        y: {
                          ...chartAxisY,
                          gridStroke: 'rgba(0, 0, 0, 0.08)',
                          gridStrokeOpacity: 1,
                        },
                      }}
                      style={{ fill: '#faad14' }}
                    />
                  )}
                </div>
              </Card>
            </Col>
          </Row>
        </>
      )}
    </div>
  )
}
