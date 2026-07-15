const base = import.meta.env.BASE_URL

export type ManualStep = {
  title: string
  content: string
}

export type ManualTable = {
  headers: string[]
  rows: string[][]
}

export type ManualImage = {
  src: string
  caption: string
}

export type ManualSection = {
  id: string
  title: string
  intro?: string
  steps?: ManualStep[]
  tables?: ManualTable[]
  notes?: string[]
  image?: ManualImage
  subsections?: ManualSection[]
}

function img(filename: string): string {
  return `${base}admin-manual/${filename}`
}

export const adminManualIntro =
  '管理员登录后，左侧菜单包含：数据看板、方案审核、方案类型管理、编制依据管理、模板管理、用户管理、设置等模块。本手册说明从零配置到日常运维的完整流程。'

export const adminManualSections: ManualSection[] = [
  {
    id: 'overview',
    title: '1. 概述与推荐配置顺序',
    intro: adminManualIntro,
    steps: [
      {
        title: '设置 → 模型配置',
        content: '接入大语言模型，审核流程必需。配置后使用「测试连接」验证，并设置默认供应商。',
      },
      {
        title: '设置 → 知识库',
        content:
          '连接 Dify 服务并填写 API 密钥。规范原文须在 Dify 管理界面中创建知识库并上传，再回到本系统绑定。',
      },
      {
        title: '方案类型管理',
        content: '创建「方案大类 + 方案名称」，作为模版与审核规则的组织单元。',
      },
      {
        title: '编制依据管理',
        content: '录入编制依据库，供编制依据审核环节引用比对。',
      },
      {
        title: '模板管理',
        content:
          '上传 Word 模版 → 规则设置 → 审核工作流 →（可选）通篇审核。系统当前不支持 Excel 一键导入审核规则，需参照 Excel 模版在系统中逐条手工录入。',
      },
      {
        title: 'Dify 控制台',
        content: '在 Dify 中创建知识库并上传规范原文文档。',
      },
      {
        title: '设置 → 审核配置',
        content: '调整并发、超时、调试开关及系统品牌展示。',
      },
      {
        title: '（可选）设置 → OnlyOffice',
        content: '配置在线预览与编辑能力，供用户审阅后在线修改文档。',
      },
    ],
  },
  {
    id: 'settings',
    title: '2. 系统设置',
    intro: '路径：设置。集中管理知识库、大模型、审核策略、数据看板刷新与 OnlyOffice。',
    subsections: [
      {
        id: 'settings-kb',
        title: '2.1 知识库连接',
        intro: '路径：设置 → 知识库',
        tables: [
          {
            headers: ['配置项', '说明'],
            rows: [
              ['Dify 服务地址', '您的 Dify Open API 根地址，如 https://your-dify-host/v1'],
              ['API 密钥', 'Dify 平台生成的 API Key'],
              ['知识库名称前缀过滤', '可选，用于下拉列表筛选知识库'],
            ],
          },
        ],
        notes: [
          'SmartReview 不在本系统内上传知识库文档，仅连接 Dify 进行检索。',
          '规范原文须在 Dify 管理界面中上传，再回到本系统绑定。',
        ],
        image: { src: img('settings-kb.png'), caption: '图 2-1  Dify 知识库设置' },
      },
      {
        id: 'settings-model',
        title: '2.2 模型配置',
        intro:
          '路径：设置 → 模型配置。分别配置火山引擎、MiniMax、Deepseek 等供应商，保存后可「测试连接」，并设置默认模型。',
        image: { src: img('settings-model.png'), caption: '图 2-2  模型设置' },
      },
      {
        id: 'settings-review',
        title: '2.3 审核配置',
        intro:
          '路径：设置 → 审核配置。可调整超时（30–600 秒）、并发、提示词调试开关及系统名称、Logo、Tab 图标等品牌展示。并发与调试类设置仅对新提交的任务生效。',
        image: { src: img('settings-review.png'), caption: '图 2-3  审核设置' },
      },
      {
        id: 'settings-onlyoffice',
        title: '2.4 OnlyOffice（可选）',
        intro:
          '路径：设置 → OnlyOffice。配置 Document Server 地址、回调与文档 URL 基址、编辑器语言及 JWT 密钥，以支持在线预览与编辑。',
        image: { src: img('settings-onlyoffice.png'), caption: '图 2-4  OnlyOffice 设置' },
      },
    ],
  },
  {
    id: 'schemes',
    title: '3. 方案类型管理',
    intro:
      '路径：方案类型管理。新建方案类型时填写「方案大类」和「方案名称」。Excel「方案类型代码」在系统中无对应字段，请以「方案大类 + 方案名称」为准。',
    image: { src: img('schemes.png'), caption: '图 3-1  方案类型管理' },
  },
  {
    id: 'basis',
    title: '4. 编制依据管理',
    intro:
      '路径：编制依据管理 → 新建编制依据。参照 Excel「编制依据库」Sheet 逐条录入文献类型、标准号、文献名称、效力状态、必引标志，并绑定方案大类与方案名称。',
    image: { src: img('basis.png'), caption: '图 4-1  编制依据管理' },
  },
  {
    id: 'templates',
    title: '5. 模板管理与规则设置',
    intro: '路径：模板管理。按方案类型上传 Word 模版、配置标题树规则与审核工作流。',
    image: { src: img('templates-list.png'), caption: '图 5-1  模板管理列表' },
    subsections: [
      {
        id: 'templates-upload',
        title: '5.1 上传 Word 模版',
        steps: [
          { title: '定位方案类型', content: '在模板管理列表中找到目标方案类型，点击「更新 Word」。' },
          { title: '选择文件', content: '选择 .docx 模版文件上传。' },
          { title: '解析标题树', content: '系统自动解析 Word 标题（标题 1–9），生成标题树。' },
        ],
      },
      {
        id: 'templates-rules',
        title: '5.2 规则设置',
        intro: '点击「规则设置」，在左侧标题树中选择章节节点，在右侧配置该节点的审核规则。',
        tables: [
          {
            headers: ['配置项', '作用'],
            rows: [
              ['引用', '内容审核时注入其他章节文本'],
              ['知识库（Dify）', '绑定外部知识库检索规范条文'],
              ['关键字', '知识库检索关键词（TAG）'],
              ['审核提示词', '章节审核指令；填写后才执行内容审核'],
              ['上下文一致性校验', '跨章节比对节点与检查说明'],
              ['编制依据审核', '开关；开启后执行编制依据校验'],
            ],
          },
        ],
        image: { src: img('template-rules.png'), caption: '图 5-2  规则设置' },
      },
      {
        id: 'templates-workflow',
        title: '5.3 审核工作流',
        intro:
          '点击「审核工作流」按需开启：编制依据、上下文一致性、内容审核、通篇审核。结构审核始终执行，无需单独开关。',
        notes: [
          '结构匹配模式：',
          '精确 — 标题须与模版逐字一致（规范化空白与标点后比对）。',
          '模糊（语义） — 允许编号、标点、轻微错字差异，由 LLM 辅助判定章节对应关系；适合用户文档标题与模版略有出入的场景。',
        ],
        image: { src: img('template-workflow.png'), caption: '图 5-3  审核工作流与结构匹配模式' },
      },
      {
        id: 'templates-full-doc',
        title: '5.4 通篇审核（可选）',
        intro:
          '点击「通篇审核」填写通篇审核提示词，可选绑定 Dify 知识库与关键字。须同时在审核工作流中开启「通篇审核」步骤才会执行。',
        image: { src: img('template-full-doc.png'), caption: '图 5-4  通篇审核配置' },
      },
    ],
  },
  {
    id: 'dify-upload',
    title: '6. Dify 知识库文档上传',
    intro: '规范原文不在 SmartReview 内上传，须在 Dify 控制台完成以下步骤：',
    steps: [
      {
        title: '创建知识库',
        content: '在 Dify 管理界面进入知识库，创建与 Excel 或业务一致的知识库名称（如「脚手架工程」）。',
      },
      {
        title: '上传文档',
        content: '按 Excel「内容引用」列逐条上传规范、通知等原文文件。',
      },
      {
        title: '保存系统连接',
        content: '在 SmartReview 设置 → 知识库 中保存 Dify 服务地址与 API 密钥。',
      },
      {
        title: '绑定到章节规则',
        content: '在模板管理 → 规则设置 中为各章节选择知识库并填写 TAG 关键字。',
      },
    ],
  },
  {
    id: 'users',
    title: '7. 用户管理',
    intro:
      '路径：用户管理。可新建用户并分配普通用户或管理员角色。系统要求至少保留一名管理员，无法删除或降级最后一名管理员，也不能删除当前登录的自己的账号。',
    image: { src: img('users.png'), caption: '图 7-1  用户管理' },
  },
  {
    id: 'dashboard',
    title: '8. 数据看板',
    intro:
      '路径：数据看板。汇总注册用户、方案类型、审核任务、Token 消耗、Dify 知识库规模等运行概况。可在设置 → 数据看板 中调整统计快照刷新间隔（5–240 分钟）。',
    image: { src: img('dashboard.png'), caption: '图 8-1  数据看板' },
  },
  {
    id: 'review-admin',
    title: '9. 方案审核（管理员视角）',
    intro:
      '管理员在方案审核页可查看全部用户的任务（含「用户名」列），并使用普通用户不可见的「审核日志」与跨用户「删除」能力。可展开 Token 明细（输入/输出）排查资源消耗。',
    image: { src: img('review-admin.png'), caption: '图 9-1  方案审核（管理员视图）' },
  },
  {
    id: 'appendix',
    title: '附录',
    intro:
      '参考 Excel：专项方案审核模版示例。系统无 Excel 导入功能，须按下列对照表逐条手工录入。',
    subsections: [
      {
        id: 'appendix-a1',
        title: 'A.1 Sheet「说明与版本」',
        tables: [
          {
            headers: ['Excel 字段', '系统对应', '录入方式'],
            rows: [
              ['模版版本', '—', '自行记录，系统不存版本号'],
              ['方案类型代码', '—', '用「方案大类 + 方案名称」代替'],
              ['方案名称', '方案类型管理', '创建方案类型'],
            ],
          },
        ],
      },
      {
        id: 'appendix-a2',
        title: 'A.2 Sheet「章节结构_完整性」',
        tables: [
          {
            headers: ['Excel 字段', '系统对应', '录入方式'],
            rows: [
              ['章节编码 / 章节标题', '标题树节点', '上传 Word 模版后自动生成'],
              ['是否校验', '结构审核', '系统自动比对，无需单独开关'],
              ['完整性依据 / 备注', '—', '参考说明，不入库'],
            ],
          },
        ],
      },
      {
        id: 'appendix-a3',
        title: 'A.3 Sheet「编制依据库」',
        tables: [
          {
            headers: ['Excel 字段', '系统字段', '说明'],
            rows: [
              ['文献类型', '文献类型', '下拉选择'],
              ['标准号或文号', '标准号', ''],
              ['文献名称', '文献名称', ''],
              ['版本或施行日期说明', '效力状态', '现行 / 废止 / 即将实施 等'],
              ['是否必引', '必引', '是/否'],
              ['类别', '—', '可写入备注'],
              ['分类', '方案大类 + 方案名称', '绑定方案类型'],
            ],
          },
        ],
      },
      {
        id: 'appendix-a4',
        title: 'A.4 Sheet「一致性规则」',
        tables: [
          {
            headers: ['Excel 字段', '系统字段', '说明'],
            rows: [
              ['源/目标章节编码', '上下文一致性比对节点', '在标题树中按章节标题选取'],
              ['检查说明', '一致性检查说明', '文本框'],
              ['是否启用', '审核工作流总开关 + 节点配置', '未配置则跳过'],
              ['严重等级', '严重/警告/提示', '由模型输出，Excel 作参考'],
            ],
          },
        ],
      },
      {
        id: 'appendix-a5',
        title: 'A.5 Sheet「章节审查配置」',
        tables: [
          {
            headers: ['Excel 字段', '系统字段', '说明'],
            rows: [
              ['章节编码', '标题树节点', '点击对应章节'],
              ['依赖章节编码', '引用', '内容审核注入引用章节'],
              ['知识库引用', '知识库 + 关键字', '选 Dify 库 + 填 tag'],
              ['人工提示词', '审核提示词', '直接粘贴'],
              ['数值审核 / 审查侧重点', '—', '可合并写入审核提示词'],
              ['编制依据', '编制依据审核开关', '需校验的章节开启'],
            ],
          },
        ],
      },
      {
        id: 'appendix-a6',
        title: 'A.6 Sheet「知识库」',
        tables: [
          {
            headers: ['Excel 字段', '系统对应', '录入方式'],
            rows: [
              ['知识库名称', 'Dify 数据集名称', '在 Dify 控制台创建知识库'],
              ['TAG 信息', '规则设置 → 关键字', '如「落地脚手架」'],
              ['内容引用', 'Dify 上传文档', '在 Dify 控制台上传原文'],
              ['是否启用', 'Dify 状态 + 系统绑定', ''],
            ],
          },
        ],
      },
      {
        id: 'appendix-a7',
        title: 'A.7 Sheet「审核流程图」',
        tables: [
          {
            headers: ['Excel 内容', '系统对应'],
            rows: [
              ['AI 上下文构造模板', '编写审核提示词的参考'],
              ['流程顺序', '审核工作流开关及环节顺序'],
            ],
          },
        ],
      },
      {
        id: 'appendix-b',
        title: 'B. 术语表',
        tables: [
          {
            headers: ['术语', '含义'],
            rows: [
              ['方案类型', '施工方案分类，由「方案大类 + 方案名称」组成'],
              ['模版', 'Word 格式的标准方案结构文件'],
              ['结构审核', '比对上传文档标题树与模版是否一致'],
              ['编制依据审核', '检查必引/废止规范引用情况'],
              ['上下文一致性', '跨章节数据与表述一致性检查'],
              ['内容审核', '按章节提示词与知识库进行合规审查'],
              ['通篇审核', '全文级别综合审查'],
              ['带批注文档', '审核结果写入 Word 后的输出文件'],
            ],
          },
        ],
      },
      {
        id: 'appendix-c',
        title: 'C. 权限说明',
        tables: [
          {
            headers: ['功能', '普通用户', '管理员'],
            rows: [
              ['方案审核 / 人工审阅 / 导出', '✓', '✓'],
              ['预览 / 在线编辑', '✓', '✓'],
              ['数据看板 / 方案类型 / 模版 / 依据 / 设置 / 用户', '—', '✓'],
              ['查看全部用户任务 / 审核日志', '—', '✓'],
            ],
          },
        ],
      },
    ],
  },
]

/** Flatten sections for Anchor menu (top-level + subsections one level deep). */
export function flattenManualAnchors(sections: ManualSection[]): { id: string; title: string }[] {
  const items: { id: string; title: string }[] = []
  for (const section of sections) {
    items.push({ id: section.id, title: section.title })
    if (section.subsections) {
      for (const sub of section.subsections) {
        items.push({ id: sub.id, title: sub.title })
      }
    }
  }
  return items
}
