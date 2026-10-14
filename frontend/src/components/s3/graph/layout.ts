import type { GraphEdge, GraphNode, Layer } from '@/api/types'
import { LAYERS } from '@/utils/labels'

/**
 * 파급 경로 그래프 배치 (README S3 탭①)
 * - 좌→우 4열(정책/산업/거시 변수/자산군), 캔버스 비율 1000:360
 * - 노드 폭 17%(170/1000), 높이 64/1000 · W. 열 x = 1% / 28% / 55% / 82%
 * - 열 안 순서는 선행 노드 순위의 무게중심(barycenter)으로 정해 교차를 줄이고,
 *   y는 선행 노드 중심의 평균을 목표로 겹치지 않게 묶음(cluster) 단위로 맞춘다.
 *
 * 화면 폭 W(px) 기준으로 직접 px 좌표를 낸다. Vue Flow는 zoom 1로 쓰므로
 * 글자 크기(12.5px/11px)는 캔버스 폭과 무관하게 스펙 그대로 유지된다.
 */

export const COLUMN_X = [0.01, 0.28, 0.55, 0.82] as const
export const NODE_W_RATIO = 0.17
export const NODE_H_RATIO = 0.064
export const CANVAS_RATIO = 0.36
/** 노드 사이 최소 세로 여백 (26/1000 · W) */
export const GAP_RATIO = 0.026
/** 제목 두 줄 + 보조 한 줄이 넘치지 않는 최소 높이(px) */
export const MIN_NODE_H = 60
export const MIN_GAP = 14
/** 열을 건너뛰는 긴 엣지의 베지어 제어점 최대 오프셋 (80/1000 · W) */
export const MAX_CTRL_RATIO = 0.08

export interface LayoutResult {
  width: number
  height: number
  nodeW: number
  nodeH: number
  /** 노드 좌상단 px */
  positions: Record<string, { x: number; y: number }>
  /** 열 머리글 x(px) */
  columnX: number[]
}

interface Item {
  id: string
  order: number
  desired: number
}

/** 정렬된 항목들을 최소 간격 이상 떨어뜨리되, 목표 위치와의 차이를 최소화한다. */
export function resolveCenters(desired: number[], spacing: number, min: number, max: number): number[] {
  type Block = { start: number; size: number; sumOffsetDesired: number; pos: number }
  const blocks: Block[] = []
  desired.forEach((d, i) => {
    let b: Block = { start: i, size: 1, sumOffsetDesired: d, pos: d }
    // 앞 블록과 겹치면 합친다 (블록 위치 = 구성원 목표의 평균 - 오프셋)
    while (blocks.length > 0) {
      const prev = blocks[blocks.length - 1]!
      if (prev.pos + prev.size * spacing <= b.pos) break
      blocks.pop()
      const merged: Block = {
        start: prev.start,
        size: prev.size + b.size,
        sumOffsetDesired: prev.sumOffsetDesired + b.sumOffsetDesired - b.size * prev.size * spacing,
        pos: 0,
      }
      merged.pos = merged.sumOffsetDesired / merged.size
      b = merged
    }
    blocks.push(b)
  })
  const out: number[] = new Array<number>(desired.length)
  for (const b of blocks) {
    for (let k = 0; k < b.size; k++) out[b.start + k] = b.pos + k * spacing
  }
  // 경계 안으로: 아래로 넘치면 위로, 위로 넘치면 아래로 민다.
  for (let i = out.length - 1; i >= 0; i--) {
    const limit = i === out.length - 1 ? max : out[i + 1]! - spacing
    if (out[i]! > limit) out[i] = limit
  }
  for (let i = 0; i < out.length; i++) {
    const limit = i === 0 ? min : out[i - 1]! + spacing
    if (out[i]! < limit) out[i] = limit
  }
  return out
}

const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length

export function layoutGraph(nodes: GraphNode[], edges: GraphEdge[], width: number): LayoutResult {
  const W = Math.max(width, 1)
  const nodeW = NODE_W_RATIO * W
  const nodeH = Math.max(NODE_H_RATIO * W, MIN_NODE_H)
  const gap = Math.max(GAP_RATIO * W, MIN_GAP)
  const spacing = nodeH + gap

  const byLayer = new Map<Layer, GraphNode[]>(LAYERS.map((l) => [l, []]))
  nodes.forEach((n) => byLayer.get(n.layer)?.push(n))
  const columns = LAYERS.map((l) => byLayer.get(l) ?? [])

  const tallest = Math.max(1, ...columns.map((c) => c.length))
  const height = Math.max(CANVAS_RATIO * W, tallest * spacing - gap)
  const minC = nodeH / 2
  const maxC = height - nodeH / 2

  const preds = new Map<string, string[]>()
  const succs = new Map<string, string[]>()
  for (const e of edges) {
    preds.set(e.target, [...(preds.get(e.target) ?? []), e.source])
    succs.set(e.source, [...(succs.get(e.source) ?? []), e.target])
  }

  const rank = new Map<string, number>() // 열 안 정규화 순위 0..1
  const center = new Map<string, number>()
  const indexOf = new Map(nodes.map((n, i) => [n.id, i]))

  columns.forEach((col) => {
    const items: Item[] = col.map((n) => {
      const ps = (preds.get(n.id) ?? []).filter((p) => center.has(p))
      const order = ps.length ? mean(ps.map((p) => rank.get(p)!)) : Number.POSITIVE_INFINITY
      const desired = ps.length ? mean(ps.map((p) => center.get(p)!)) : height / 2
      return { id: n.id, order, desired }
    })
    // 선행 노드가 없는 노드는 원래 순서대로 뒤에 둔다.
    items.sort((a, b) => a.order - b.order || indexOf.get(a.id)! - indexOf.get(b.id)!)
    const centers = resolveCenters(
      items.map((it) => it.desired),
      spacing,
      minC,
      maxC,
    )
    items.forEach((it, i) => {
      center.set(it.id, centers[i]!)
      rank.set(it.id, items.length === 1 ? 0.5 : i / (items.length - 1))
    })
  })

  // 첫 열(정책)은 후행 노드 중심에 맞춘다.
  const first = columns[0] ?? []
  if (first.length) {
    const items = first
      .map((n) => {
        const ss = (succs.get(n.id) ?? []).filter((s) => center.has(s))
        return { id: n.id, desired: ss.length ? mean(ss.map((s) => center.get(s)!)) : center.get(n.id)! }
      })
      .sort((a, b) => center.get(a.id)! - center.get(b.id)!)
    const centers = resolveCenters(
      items.map((i) => i.desired),
      spacing,
      minC,
      maxC,
    )
    items.forEach((it, i) => center.set(it.id, centers[i]!))
  }

  // 전체를 캔버스 세로 가운데로
  const all = [...center.values()]
  if (all.length) {
    const top = Math.min(...all) - nodeH / 2
    const bottom = Math.max(...all) + nodeH / 2
    const shift = (height - (bottom - top)) / 2 - top
    for (const [id, c] of center) center.set(id, c + shift)
  }

  const positions: Record<string, { x: number; y: number }> = {}
  columns.forEach((col, ci) => {
    for (const n of col) {
      positions[n.id] = { x: COLUMN_X[ci]! * W, y: center.get(n.id)! - nodeH / 2 }
    }
  })

  return {
    width: W,
    height,
    nodeW,
    nodeH,
    positions,
    columnX: COLUMN_X.map((x) => (x - 0.01) * W),
  }
}

/** 수평 접선 베지어. 인접 열은 중점, 열을 건너뛰면 제어점 오프셋을 80/1000 · W로 제한. */
export function edgePath(sx: number, sy: number, tx: number, ty: number, width: number): { d: string; mx: number; my: number } {
  const mx = (sx + tx) / 2
  const my = (sy + ty) / 2
  if (Math.abs(sy - ty) < 0.5) return { d: `M${sx},${sy} L${tx},${ty}`, mx, my }
  const o = Math.min((tx - sx) / 2, MAX_CTRL_RATIO * width)
  return { d: `M${sx},${sy} C${sx + o},${sy} ${tx - o},${ty} ${tx},${ty}`, mx, my }
}
