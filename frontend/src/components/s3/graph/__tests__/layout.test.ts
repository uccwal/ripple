import { describe, expect, it } from 'vitest'
import type { GraphEdge, GraphNode, Layer } from '@/api/types'
import { edgePath, layoutGraph, resolveCenters } from '../layout'

const node = (id: string, layer: Layer): GraphNode => ({
  id,
  label: id,
  layer,
  confidence: 'high',
  factor_id: null,
  direction_text: '',
  evidence: [],
})
const edge = (source: string, target: string): GraphEdge => ({ source, target, direction: '-', confidence: 'high' })

// 프로토타입 D().N 구성
const NODES = [
  node('n1', 'policy'),
  node('n2', 'industry'),
  node('n3', 'industry'),
  node('n4', 'macro'),
  node('n5', 'macro'),
  node('n6', 'macro'),
  node('n7', 'asset'),
  node('n8', 'asset'),
  node('n9', 'asset'),
]
const EDGES = [
  edge('n1', 'n2'),
  edge('n1', 'n3'),
  edge('n1', 'n6'),
  edge('n2', 'n4'),
  edge('n2', 'n5'),
  edge('n3', 'n5'),
  edge('n4', 'n7'),
  edge('n5', 'n7'),
  edge('n5', 'n8'),
  edge('n6', 'n9'),
]

describe('resolveCenters', () => {
  it('겹치지 않으면 목표 위치 그대로', () => {
    expect(resolveCenters([50, 200], 90, 0, 400)).toEqual([50, 200])
  })
  it('겹치면 목표 평균을 중심으로 묶는다', () => {
    expect(resolveCenters([180, 180], 90, 0, 400)).toEqual([135, 225])
  })
  it('경계를 넘지 않는다', () => {
    const c = resolveCenters([10, 10, 10], 90, 32, 328)
    expect(c[0]).toBe(32)
    expect(c[2]).toBe(212)
  })
})

describe('layoutGraph', () => {
  const W = 1000
  const L = layoutGraph(NODES, EDGES, W)

  it('4열 x 위치와 노드 폭은 스펙 비율', () => {
    expect(L.positions.n1!.x).toBeCloseTo(10)
    expect(L.positions.n2!.x).toBeCloseTo(280)
    expect(L.positions.n4!.x).toBeCloseTo(550)
    expect(L.positions.n7!.x).toBeCloseTo(820)
    expect(L.nodeW).toBeCloseTo(170)
    expect(L.nodeH).toBeCloseTo(64)
    expect(L.height).toBeCloseTo(360)
  })

  it('열 안 순서가 교차를 줄이는 방향 (n4 → n5 → n6, n7 → n8 → n9)', () => {
    const y = (id: string) => L.positions[id]!.y
    expect(y('n4')).toBeLessThan(y('n5'))
    expect(y('n5')).toBeLessThan(y('n6'))
    expect(y('n7')).toBeLessThan(y('n8'))
    expect(y('n8')).toBeLessThan(y('n9'))
  })

  it('노드가 캔버스 안에 있고 같은 열에서 겹치지 않는다', () => {
    for (const p of Object.values(L.positions)) {
      expect(p.y).toBeGreaterThanOrEqual(-0.001)
      expect(p.y + L.nodeH).toBeLessThanOrEqual(L.height + 0.001)
    }
    const macro = ['n4', 'n5', 'n6'].map((id) => L.positions[id]!.y)
    expect(macro[1]! - macro[0]!).toBeGreaterThanOrEqual(L.nodeH)
  })

  it('좁은 폭에서도 노드 최소 높이를 지킨다', () => {
    const narrow = layoutGraph(NODES, EDGES, 600)
    expect(narrow.nodeH).toBe(60)
    expect(narrow.height).toBeGreaterThanOrEqual(600 * 0.36)
  })

  it('한 열에 노드가 많으면 캔버스가 세로로 늘어난다', () => {
    const many = [node('p', 'policy'), ...Array.from({ length: 6 }, (_, i) => node(`a${i}`, 'asset'))]
    const L2 = layoutGraph(many, [], 1000)
    expect(L2.height).toBeGreaterThan(360)
  })
})

describe('edgePath', () => {
  it('인접 열은 제어점이 중점 (프로토타입 M180,152 C230,152 230,52 280,52)', () => {
    expect(edgePath(180, 152, 280, 52, 1000).d).toBe('M180,152 C230,152 230,52 280,52')
  })
  it('열을 건너뛰면 제어점 오프셋 80 (M180,152 C260,152 470,312 550,312)', () => {
    expect(edgePath(180, 152, 550, 312, 1000).d).toBe('M180,152 C260,152 470,312 550,312')
  })
  it('같은 높이는 직선, 라벨은 중점', () => {
    const p = edgePath(450, 142, 550, 142, 1000)
    expect(p.d).toBe('M450,142 L550,142')
    expect([p.mx, p.my]).toEqual([500, 142])
  })
})
