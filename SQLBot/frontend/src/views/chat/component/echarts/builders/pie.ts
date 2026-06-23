import type { NormalizedChartData } from '../data.ts'
import { formatNumber } from '../data.ts'

export function buildPie(norm: NormalizedChartData, showLabel: boolean) {
  const nameField = norm.series[0]?.value ?? norm.x[0]?.value
  const valueField = norm.y[0]?.value
  const data = norm.rows.map((row) => ({
    name: String(row?.[nameField] ?? ''),
    value: row?.[valueField] ?? null,
  }))
  return {
    tooltip: {
      trigger: 'item',
      valueFormatter: (value: any) => `${formatNumber(value)}${norm.isPercent ? '%' : ''}`,
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
