export type UserRole = 'user' | 'admin'

export interface UserPublic {
  id: number
  username: string
  phone: string
  role: UserRole
}

export interface KnowledgeBaseSettings {
  dify_base_url: string
  api_key_configured: boolean
}

export type LlmApiProtocol = 'openai_compatible' | 'anthropic'

export type ProviderId = 'volcengine' | 'minimax'

export interface VolcengineSettingsPart {
  api_protocol: 'openai_compatible'
  base_url: string
  endpoint_id: string
  api_key_configured: boolean
}

export interface MinimaxSettingsPart {
  api_protocol: 'anthropic'
  base_url: string
  model: string
  api_key_configured: boolean
}

export interface ModelProviderSettings {
  default_provider: ProviderId | null
  volcengine: VolcengineSettingsPart
  minimax: MinimaxSettingsPart
}

export interface ModelTestResult {
  ok: boolean
  preview?: string | null
  error?: string | null
  latency_ms?: number | null
}

export interface DifyDatasetItem {
  id: string
  name: string
}

export type WorkflowStepId =
  | 'start'
  | 'structure'
  | 'compilation_basis'
  | 'context_consistency'
  | 'content'
  | 'end'

export interface ReviewWorkflowData {
  steps: WorkflowStepId[]
}

export interface SchemeType {
  id: number
  category: string
  name: string
  remark: string | null
  created_at: string | null
  updated_at: string | null
  /** 已解析且标题结构非空 */
  template_configured: boolean
  /** 已保存审核工作流 */
  workflow_configured: boolean
}

export interface BasisItem {
  id: number
  basis_id: string
  doc_type: string
  standard_no: string
  doc_name: string
  effect_status: string
  is_mandatory: boolean
  scheme_category: string
  scheme_name: string
  remark: string | null
  created_at: string | null
  updated_at: string | null
}

export interface TemplateNode {
  id: string
  level: number
  title: string
  content: string[]
  children: TemplateNode[]
  /** 引用同树中其他节点 id */
  ref_node_ids?: string[]
  /** 上下文一致性比对：与本章节对照校验的节点 id（用于发现跨章节语义冲突等） */
  context_consistency_ref_node_ids?: string[]
  /** Dify 知识库（数据集）id */
  dify_dataset_id?: string | null
  knowledge_keywords?: string[]
  review_prompt?: string
}

export interface TemplatePublic {
  id: number
  scheme_type_id: number
  minio_bucket: string
  object_key: string
  original_filename: string
  parsed_structure: { nodes: TemplateNode[] } | null
  review_workflow: ReviewWorkflowData | null
  parsed_at: string | null
  updated_at: string | null
}

export type ReviewTaskStatus = 'pending' | 'processing' | 'succeeded' | 'failed'

export interface ReviewTask {
  id: number
  scheme_type_id: number
  scheme_category: string
  scheme_name: string
  status: ReviewTaskStatus
  result_text: string | null
  error_message: string | null
  original_filename: string
  created_at: string
  updated_at: string
}
