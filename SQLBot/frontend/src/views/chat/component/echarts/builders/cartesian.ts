import { formatNumber, type NormalizedChartData } from '../data.ts'
import { axisLabelFormatter } from '../theme.ts'

function categoryValues(norm: NormalizedChartData): string[] {
  const field = norm.x[0]?.value
  return norm.rows.map((row) => String(row?.[field] ?? ''))
}

function buildSeries(
  norm: NormalizedChartData,
  type: 'bar' | 'line',
  showLabel: boolean,
  stacked: boolean,
  area: boolean
): Array<Record<string, any>> {
  const yField = norm.y[0]?.value
  const labelFormatter = (value: any) => `${formatNumber(value)}${norm.isPercent ? '%' : ''}`
  const baseLabel = showLabel
    ? { show: true, formatter: (p: any) => labelFormatter(p.value) }
    : undefined

  if (norm.series.length > 0) {
    const sField = norm.series[0].value
    const xField = norm.x[0].value
    const cats = categoryValues(norm)
    const seriesNames = Array.from(new Set(norm.rows.map((row) => String(row?.[sField] ?? ''))))
    return seriesNames.map((name) => ({
      name,
      type,
      stack: stacked ? 'total' : undefined,
      areaStyle: area ? {} : undefined,
      data: cats.map((cat) => {
        const row = norm.rows.find(
          (r) => String(r?.[xField]) === cat && String(r?.[sField]) === name
        )
        return row ? row?.[yField] ?? null : null
      }),
      label: baseLabel,
    }))
  }

  return [
    {
      name: norm.y[0]?.name,
      type,
      areaStyle: area ? {} : undefined,
      data: norm.rows.map((row) => row?.[yField] ?? null),
      label: baseLabel,
    },
  ]
}

export function buildColumn(norm: NormalizedChartData, showLabel: boolean) {
  return {
    xAxis: { type: 'category', data: categoryValues(norm), axisLabel: { hideOverlap: true } },
    yAxis: { type: 'value', axisLabel: { formatter: axisLabelFormatter(norm.isPercent) } },
    series: buildSeries(norm, 'bar', showLabel, norm.series.length > 0, false),
  }
}

export function buildBar(norm: NormalizedChartData, showLabel: boolean) {
  const series = buildSeries(norm, 'bar', showLabel, norm.series.length > 0, false).map((s) => ({
    ...s,
    label: showLabel
      ? { show: true, position: 'right', formatter: s.label?.formatter }
      : undefined,
  }))
  return {
    yAxis: { type: 'category', data: categoryValues(norm), axisLabel: { hideOverlap: true } },
    xAxis: { type: 'value', axisLabel: { formatter: axisLabelFormatter(norm.isPercent) } },
    series,
  }
}

function buildTrend(norm: NormalizedChartData, showLabel: boolean, area: boolean) {
  return {
    xAxis: {
      type: 'category',
      data: categoryValues(norm),
      boundaryGap: false,
      axisLabel: { hideOverlap: true },
    },
    yAxis: { type: 'value', axisLabel: { formatter: axisLabelFormatter(norm.isPercent) } },
    series: buildSeries(norm, 'line', showLabel, false, area),
  }
}

export function buildLine(norm: NormalizedChartData, showLabel: boolean) {
  return buildTrend(norm, showLabel, false)
}

export function buildArea(norm: NormalizedChartData, showLabel: boolean) {
  return buildTrend(norm, showLabel, true)
}
