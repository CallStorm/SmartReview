import { FileTextOutlined } from '@ant-design/icons'
import {
  App as AntApp,
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type { BasisItem, SchemeType } from '../api/types'
import PageShell from '../components/PageShell'
import { DEFAULT_TABLE_PAGINATION } from '../config/tablePagination'

/** 文献类型（前端内置，与后端存字符串一致） */
const DOC_TYPE_OPTIONS = [
  { label: '国家标准（国标）', value: '国家标准（国标）' },
  { label: '行业标准（行标）', value: '行业标准（行标）' },
  { label: '地方标准', value: '地方标准' },
  { label: '团体标准', value: '团体标准' },
  { label: '企业标准', value: '企业标准' },
  { label: '法律', value: '法律' },
  { label: '行政法规', value: '行政法规' },
  { label: '部门规章', value: '部门规章' },
  { label: '规范性文件', value: '规范性文件' },
  { label: '技术规范', value: '技术规范' },
  { label: '其他', value: '其他' },
]

/** 效力状态（前端内置） */
const EFFECT_STATUS_OPTIONS = [
  { label: '现行', value: '现行' },
  { label: '废止', value: '废止' },
  { label: '即将实施', value: '即将实施' },
  { label: '征求意见/草案', value: '征求意见/草案' },
  { label: '部分废止', value: '部分废止' },
  { label: '其他', value: '其他' },
]

function resolveSchemeSelection(
  schemes: SchemeType[],
  category: string,
  name: string,
): number | undefined {
  return schemes.find((s) => s.category === category && s.name === name)?.id
}

export default function BasisPage() {
  const qc = useQueryClient()
  const { message } = AntApp.useApp()
  const { data = [], isLoading } = useQuery({
    queryKey: ['basis'],
    queryFn: async () => {
      const { data: rows } = await api.get<BasisItem[]>('/basis')
      return rows
    },
  })

  const { data: schemes = [] } = useQuery({
    queryKey: ['schemes'],
    queryFn: async () => {
      const { data: rows } = await api.get<SchemeType[]>('/scheme-types')
      return rows
    },
  })

  const schemeSelectOptions = useMemo(
    () =>
      schemes.map((s) => ({
        value: s.id,
        label: `${s.category} / ${s.name}`,
      })),
    [schemes],
  )

  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<BasisItem | null>(null)
  const [keyword, setKeyword] = useState('')
  const [form] = Form.useForm()

  const filteredData = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase()
    if (!normalizedKeyword) return data
    return data.filter((item) => {
      const standardNo = item.standard_no?.toLowerCase() ?? ''
      const docName = item.doc_name?.toLowerCase() ?? ''
      return standardNo.includes(normalizedKeyword) || docName.includes(normalizedKeyword)
    })
  }, [data, keyword])

  const saveMutation = useMutation({
    mutationFn: async (values: Record<string, unknown>) => {
      const schemeTypeId = values.scheme_type_id as number | undefined
      const st = schemeTypeId != null ? schemes.find((s) => s.id === schemeTypeId) : undefined
      const { scheme_type_id: _sid, basis_id: _bid, ...rest } = values
      const body = {
        ...rest,
        scheme_category: st?.category ?? '',
        scheme_name: st?.name ?? '',
      }
      if (editing) {
        await api.patch(`/basis/${editing.id}`, body)
      } else {
        await api.post('/basis', body)
      }
    },
    onSuccess: async () => {
      message.success('已保存')
      setOpen(false)
      setEditing(null)
      form.resetFields()
      await qc.invalidateQueries({ queryKey: ['basis'] })
    },
    onError: () => message.error('保存失败'),
  })

  const delMutation = useMutation({
    mutationFn: async (id: number) => api.delete(`/basis/${id}`),
    onSuccess: async () => {
      message.success('已删除')
      await qc.invalidateQueries({ queryKey: ['basis'] })
    },
    onError: () => message.error('删除失败'),
  })

  return (
    <PageShell
      icon={<FileTextOutlined />}
      description=""
      extra={
        <Space>
          <Input
            allowClear
            placeholder="按标准号或文献名称过滤"
            style={{ width: 260 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <Button
            type="primary"
            onClick={() => {
              setEditing(null)
              form.resetFields()
              setOpen(true)
            }}
          >
            新建编制依据
          </Button>
        </Space>
      }
    >
      <Table
        rowKey="id"
        size="middle"
        loading={isLoading}
        scroll={{ x: 1200 }}
        dataSource={filteredData}
        locale={{ emptyText: '暂无编制依据' }}
        pagination={DEFAULT_TABLE_PAGINATION}
        columns={[
          { title: '文献类型', dataIndex: 'doc_type', width: 120 },
          { title: '标准号', dataIndex: 'standard_no', width: 140 },
          { title: '文献名称', dataIndex: 'doc_name', width: 220 },
          { title: '效力状态', dataIndex: 'effect_status', width: 100 },
          {
            title: '必引',
            dataIndex: 'is_mandatory',
            width: 72,
            render: (v: boolean) => (v ? '是' : '否'),
          },
          { title: '方案大类', dataIndex: 'scheme_category', width: 160 },
          { title: '方案名称', dataIndex: 'scheme_name', width: 140 },
          { title: '备注', dataIndex: 'remark' },
          {
            title: '操作',
            key: 'actions',
            fixed: 'right',
            width: 160,
            render: (_: unknown, row: BasisItem) => (
              <Space>
                <Button
                  type="link"
                  onClick={() => {
                    setEditing(row)
                    form.setFieldsValue({
                      ...row,
                      scheme_type_id: resolveSchemeSelection(
                        schemes,
                        row.scheme_category,
                        row.scheme_name,
                      ),
                    })
                    setOpen(true)
                  }}
                >
                  编辑
                </Button>
                <Popconfirm title="确定删除？" onConfirm={() => delMutation.mutate(row.id)}>
                  <Button type="link" danger>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={editing ? '编辑编制依据' : '新建编制依据'}
        open={open}
        width={640}
        onCancel={() => {
          setOpen(false)
          setEditing(null)
          form.resetFields()
        }}
        onOk={() => form.submit()}
        confirmLoading={saveMutation.isPending}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(v) => saveMutation.mutate(v)}
          initialValues={{
            doc_type: undefined,
            standard_no: '',
            doc_name: '',
            effect_status: undefined,
            is_mandatory: false,
            scheme_type_id: undefined,
            remark: '',
          }}
        >
          <Form.Item name="doc_type" label="文献类型">
            <Select
              allowClear
              placeholder="请选择文献类型"
              options={DOC_TYPE_OPTIONS}
              showSearch
              optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item name="standard_no" label="标准号">
            <Input />
          </Form.Item>
          <Form.Item name="doc_name" label="文献名称">
            <Input />
          </Form.Item>
          <Form.Item name="effect_status" label="效力状态">
            <Select
              allowClear
              placeholder="请选择效力状态"
              options={EFFECT_STATUS_OPTIONS}
              showSearch
              optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item name="is_mandatory" label="是否必引" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            name="scheme_type_id"
            label="方案类型"
            extra="选项来自「方案类型管理」中的大类与名称"
          >
            <Select
              allowClear
              placeholder="请选择方案类型"
              options={schemeSelectOptions}
              showSearch
              optionFilterProp="label"
              disabled={schemes.length === 0}
              notFoundContent={schemes.length === 0 ? '请先在方案类型管理中添加方案类型' : undefined}
            />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  )
}
