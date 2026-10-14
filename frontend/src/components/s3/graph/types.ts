import type { Confidence, Direction, GraphNode } from '@/api/types'

export interface FlowNodeData {
  node: GraphNode
  /** 보조 문구 (확신도 · 근거 수 / 정책 · 발표일) */
  sub: string
  selected: boolean
  onSelect: (id: string) => void
}

export interface FlowEdgeData {
  direction: Direction
  confidence: Confidence
  /** 캔버스 폭(px) — 제어점 오프셋 계산용 */
  canvasWidth: number
}
