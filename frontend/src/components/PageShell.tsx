import './PageShell.css'

import type { ReactNode } from 'react'

export type PageShellProps = {
  /** 与顶栏标题重复时可省略，仅用 icon + 说明区分模块 */
  title?: string
  description?: string
  icon?: ReactNode
  extra?: ReactNode
  children: ReactNode
}

export default function PageShell({ title, description, icon, extra, children }: PageShellProps) {
  const showTitleRow = Boolean(icon || title)

  return (
    <div className="page-shell">
      <header className="page-shell__head">
        <div className="page-shell__head-main">
          {showTitleRow ? (
            <div className="page-shell__title-row">
              {icon ? <span className="page-shell__icon">{icon}</span> : null}
              {title ? <h2 className="page-shell__title">{title}</h2> : null}
            </div>
          ) : null}
          {description ? <p className="page-shell__desc">{description}</p> : null}
        </div>
        {extra ? <div className="page-shell__extra">{extra}</div> : null}
      </header>
      <div className="page-shell__body">{children}</div>
    </div>
  )
}
