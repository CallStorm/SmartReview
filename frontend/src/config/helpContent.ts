const base = import.meta.env.BASE_URL

export type HelpVideo = {
  id: string
  title: string
  description: string
  src: string
}

export type HelpDownload = {
  id: string
  title: string
  description: string
  href: string
  filename: string
}

export type HelpGuideStep = {
  title: string
  content: string
}

export type HelpFaqItem = {
  question: string
  answer: string
}

export const helpIntro = {
  summary:
    '智能方案审核系统面向施工方案的全流程管理与智能审核，帮助编制人员快速完成方案上传与自动审查，也帮助管理员维护审核规则与知识库，使审核结果更准确、稳定。',
  userRole:
    '普通用户的主要工作是：下载模版 → 本地编写 → 上传审核 → 查看审阅结果 → 导出带批注 Word。',
  adminRole:
    '管理员的主要工作是：配置大模型与知识库连接、维护方案类型与编制依据、上传 Word 模版并按规则录入章节审核配置，以及将规范文件上传至 Dify 知识库。',
}

export const userGuideSteps: HelpGuideStep[] = [
  {
    title: '登录与进入方案审核',
    content:
      '使用账号或手机号与密码登录。普通用户登录后自动进入「方案审核」页面，可在此查看任务统计、选择方案类型并管理审核任务。',
  },
  {
    title: '下载模版',
    content:
      '在「选择方案类型」下拉框中选择对应类型（仅显示已配置模版的方案类型），点击「下载模版」获取 Word 模版。请保持文档标题层级与模版一致（使用 Word「标题 1」至「标题 9」样式），否则上传后可能无法通过结构审核。',
  },
  {
    title: '上传发起审核',
    content:
      '选择方案类型后点击「方案审核」，在弹窗中上传 `.docx` 文件并提交。仅支持 docx 格式，上传文件的章节结构须与所选方案类型的模版一致。',
  },
  {
    title: '跟踪任务状态',
    content:
      '任务提交后系统自动审核。状态包括：排队中、处理中（可能显示结构审核、编制依据审核、上下文一致性、内容审核、通篇审核等阶段）、已完成、失败。任务列表会定期刷新。',
  },
  {
    title: '人工审阅',
    content:
      '任务状态为「已完成」或「失败」后，点击「人工审阅」查看结构化审核报告。左侧为审核步骤链，右侧为当前步骤的审核详情，包括问题列表、通过/有问题状态与修改建议。问题级别分为严重、警告、提示。',
  },
  {
    title: '预览、编辑与导出',
    content:
      '在任务列表或人工审阅页可「导出报告」下载带批注 Word。若管理员已配置 OnlyOffice，还可在人工审阅页进行在线预览与编辑。',
  },
]

export const adminGuideSteps: HelpGuideStep[] = [
  {
    title: '设置 → 模型配置',
    content: '接入大语言模型，审核流程必需。',
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
    title: '设置 → 审核配置',
    content: '调整并发、超时、调试开关等运行参数。',
  },
  {
    title: '（可选）设置 → OnlyOffice',
    content: '配置在线预览与编辑能力，供用户审阅后在线修改文档。',
  },
]

export const helpVideos: HelpVideo[] = [
  {
    id: 'format-adjustment',
    title: '格式调整操作演示',
    description:
      '演示如何将用户编写的不规范方案章节结构，调整为与系统模版一致的标题层级，以便通过结构审核。',
    src: `${base}help/assets/format-adjustment.mp4`,
  },
]

export const helpDownloads: HelpDownload[] = [
  {
    id: 'sample-high-support-formwork',
    title: '沙泘沱高支模专项施工方案',
    description:
      '高支模专项施工方案示例文档，可作为编写方案时的结构与内容参考。下载后在 Word 或 WPS 中打开查看。',
    href: `${base}help/assets/sample-high-support-formwork.docx`,
    filename: '沙泘沱高支模专项施工方案.docx',
  },
]

export const helpFaq: HelpFaqItem[] = [
  {
    question: '无法下载模版',
    answer: '该方案类型尚未上传模版，请联系管理员完成模版配置。',
  },
  {
    question: '下拉框中找不到方案类型',
    answer: '列表仅显示已配置模版的方案类型，请联系管理员。',
  },
  {
    question: '提交失败',
    answer: '检查文件是否为 `.docx`、方案类型是否已选、文件是否过大。',
  },
  {
    question: '任务状态为「失败」',
    answer:
      '常见原因为结构审核未通过（章节与模版不一致），请对照模版调整 Word 标题结构后重新上传。可参考上方「格式调整操作演示」视频。',
  },
  {
    question: '「暂无带批注文档」',
    answer: '任务未完成，或结构审核未通过导致未生成输出文档。',
  },
  {
    question: '预览/编辑不可用',
    answer: '管理员尚未配置 OnlyOffice，或任务尚未生成输出文档。',
  },
]
