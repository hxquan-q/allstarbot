import type { NormalizedChartData } from '../data.ts'
import { axisLabelFormatter, valueFormatter } from '../theme.ts'

export function buildScatter(norm: NormalizedChartData, _showLabel: boolean) {
  const xField = norm.x[0]?.value
  const yField = norm.y[0]?.value
  const sField = norm.series[0]?.value
  let series: Array<Record<string, any>>
  if (sField) {
    const groups = new Map<string, Array<[any, any]>>()
    for (const row of norm.rows) {
      const key = String(row?.[sField] ?? '')
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push([row?.[xField], row?.[yField]])
    }
    series = [...groups.entries()].map(([name, data]) => ({ name, type: 'scatter', data }))
  } else {
    series = [
      { type: 'scatter', data: norm.rows.map((row) => [row?.[xField], row?.[yField]]) },
    ]
  }
  return {
    tooltip: { trigger: 'item', valueFormatter: valueFormatter(norm.isPercent) },
    xAxis: {
      type: 'value',
      name: norm.x[0]?.name,
      axisLabel: { formatter: axisLabelFormatter(norm.isPercent) },
    },
    yAxis: {
      type: 'value',
      name: norm.y[0]?.name,
      axisLabel: { formatter: axisLabelFormatter(norm.isPercent) },
    },
    series,
  }
}
