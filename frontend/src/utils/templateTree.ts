import type { TemplateNode } from '../api/types'

export function cloneTemplateStructure(
  s: { nodes: TemplateNode[] },
): { nodes: TemplateNode[] } {
  return JSON.parse(JSON.stringify(s)) as { nodes: TemplateNode[] }
}

export function findNodeById(nodes: TemplateNode[], id: string): TemplateNode | null {
  for (const n of nodes) {
    if (n.id === id) return n
    const found = n.children?.length ? findNodeById(n.children, id) : null
    if (found) return found
  }
  return null
}

/** Immutable update of one node (by id) in the tree. */
export function patchNodeInTree(
  nodes: TemplateNode[],
  id: string,
  patch: Partial<TemplateNode>,
): TemplateNode[] {
  return nodes.map((n) => {
    if (n.id === id) {
      return { ...n, ...patch, children: n.children ?? [] }
    }
    if (n.children?.length) {
      return { ...n, children: patchNodeInTree(n.children, id, patch) }
    }
    return n
  })
}

/** Flat list for「引用」选择器（缩进展示层级）。 */
export function flattenNodePickerItems(
  nodes: TemplateNode[],
  depth = 0,
): { id: string; label: string }[] {
  const out: { id: string; label: string }[] = []
  const pad = '　'.repeat(depth)
  for (const n of nodes) {
    out.push({ id: n.id, label: `${pad}[L${n.level}] ${n.title}` })
    if (n.children?.length) {
      out.push(...flattenNodePickerItems(n.children, depth + 1))
    }
  }
  return out
}

export function collectDescendantIds(node: TemplateNode): Set<string> {
  const ids = new Set<string>([node.id])
  for (const c of node.children ?? []) {
    for (const x of collectDescendantIds(c)) {
      ids.add(x)
    }
  }
  return ids
}
