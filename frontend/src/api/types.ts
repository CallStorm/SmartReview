export type UserRole = 'user' | 'admin'

export interface UserPublic {
  id: number
  username: string
  phone: string
  role: UserRole
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
}

export interface TemplatePublic {
  id: number
  scheme_type_id: number
  minio_bucket: string
  object_key: string
  original_filename: string
  parsed_structure: { nodes: TemplateNode[] } | null
  parsed_at: string | null
  updated_at: string | null
}
