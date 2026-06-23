import { merge } from 'lodash-es'
import type { ChartAxis, ChartData } from '../BaseChart.ts'
import { normalizeChartData } from './data.ts'
import { SQLBOT_PALETTE, makeValueFormatter } from './theme.ts'
import { buildArea, buildBar, buildColumn, buildLine } from './builders/cartesian.ts'
import { buildPie } from './builders/pie.ts'
import { buildScatter } from './builders/scatter.ts'

export interface BuildInput {
  type: string
  axis: ChartAxis[]
  data: ChartData[]
  showLabel?: boolean
  echarts?: Record<string, any>
}

function sanitizeEscape(echarts: Record<string, any> | undefined): Record<string, any> {
  if (!echarts || typeof echarts !== 'object') return {}
  try {
    return JSON.parse(JSON.stringify(echarts)) as Record<string, any>
  } catch {
    return {}
  }
}

export function buildEChartsOption(input: BuildInput): Record<string, any> {
  const { type, axis, data, showLabel = false, echarts } = input
  const norm = normalizeChartData(axis, data)
  const valueFmt = makeValueFormatter(norm.isPercent, norm.y[0]?.unit)

  const common: Record<string, any> = {
    color: SQLBOT_PALETTE,
    grid: {
      left: 12,
      right: 24,
      top: norm.series.length > 0 ? 40 : 20,
      bottom: 12,
      containLabel: true,
    },
    tooltip: {
      trigger: type === 'pie' || type === 'scatter' ? 'item' : 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: valueFmt,
    },
    legend:
      norm.series.length > 0 && type !== 'pie' && type !== 'scatter'
        ? { type: 'scroll', top: 0 }
        : undefined,
  }

  let base: Record<string, any>
  switch (type) {
    case 'bar':
      base = buildBar(norm, showLabel)
      break
    case 'line':
      base = buildLine(norm, showLabel)
      break
    case 'area':
      base = buildArea(norm, showLabel)
      break
    case 'pie':
      base = buildPie(norm, showLabel)
      break
    case 'scatter':
      base = buildScatter(norm, showLabel)
      break
    case 'column':
    default:
      base = buildColumn(norm, showLabel)
      break
  }

  const merged = merge({}, common, base)
  const escapePatch = sanitizeEscape(echarts)
  if (Object.keys(escapePatch).length > 0) {
    return merge({}, merged, escapePatch)
  }
  return merged
}
