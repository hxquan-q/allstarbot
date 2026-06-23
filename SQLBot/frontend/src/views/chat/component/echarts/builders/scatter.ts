import type { NormalizedChartData } from '../data.ts'
import { makeValueFormatter } from '../theme.ts'

export function buildScatter(norm: NormalizedChartData, _showLabel: boolean) {
  const xField = norm.x[0]?.value
  const yField = norm.y[0]?.value
  const sField = norm.series[0]?.value
  const fmtX = makeValueFormatter(norm.isPercent, norm.x[0]?.unit)
  const fmtY = makeValueFormatter(norm.isPercent, norm.y[0]?.unit)
  const xName = norm.x[0]?.name ?? ''
  const yName = norm.y[0]?.name ?? ''

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
    tooltip: {
      trigger: 'item',
      formatter: (p: any) =>
        `${p.seriesName ? p.seriesName + '<br/>' : ''}${xName}: ${fmtX(
          Array.isArray(p.value) ? p.value[0] : p.value
        )}<br/>${yName}: ${fmtY(Array.isArray(p.value) ? p.value[1] : p.value)}`,
    },
    xAxis: { type: 'value', name: xName, axisLabel: { formatter: fmtX } },
    yAxis: { type: 'value', name: yName, axisLabel: { formatter: fmtY } },
    series,
  }
}
