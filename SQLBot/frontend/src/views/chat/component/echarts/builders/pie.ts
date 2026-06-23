import type { NormalizedChartData } from '../data.ts'
import { makeValueFormatter } from '../theme.ts'

export function buildPie(norm: NormalizedChartData, showLabel: boolean) {
  const nameField = norm.series[0]?.value ?? norm.x[0]?.value
  const valueField = norm.y[0]?.value
  const data = norm.rows.map((row) => ({
    name: String(row?.[nameField] ?? ''),
    value: row?.[valueField] ?? null,
  }))
  const fmt = makeValueFormatter(norm.isPercent, norm.y[0]?.unit)
  return {
    tooltip: {
      trigger: 'item',
      formatter: (p: any) =>
        `${p.name}<br/>${norm.y[0]?.name ?? ''}: ${fmt(p.value)} (${p.percent}%)`,
    },
    legend: { type: 'scroll', orient: 'vertical', left: 'left' },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['60%', '50%'],
        avoidLabelOverlap: true,
        data,
        label: showLabel ? { show: true, formatter: '{b}: {d}%' } : { show: false },
        labelLine: { show: showLabel },
      },
    ],
  }
}
