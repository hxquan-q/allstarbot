import type { ChartAxis, ChartData } from '../BaseChart.ts'
import { endsWith } from 'lodash-es'

/**
 * 为数值添加千分符，保持原有小数位数不变（纯字符串处理，避免精度丢失）。
 */
export function formatNumber(value: any): string | number {
  if (value === null || value === undefined || value === '') {
    return value
  }

  let str: string
  if (typeof value === 'string') {
    str = value.trim()
  } else if (typeof value === 'number') {
    str = String(value)
  } else {
    return value
  }

  const match = str.match(/^([+-])?(\d+)(\.(\d+))?$/)
  if (!match) {
    return value
  }

  const sign = match[1] || ''
  const intPart = match[2]
  const decPart = match[3] || ''

  const formattedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')

  return sign + formattedInt + decPart
}

function toChartNumber(value: any): any {
  if (value === null || value === undefined || value === '') {
    return value
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0
  }
  const strValue = String(value).trim()
  if (!strValue) {
    return value
  }
  const isPercent = endsWith(strValue, '%')
  const numericText = (isPercent ? strValue.slice(0, -1) : strValue).replace(/,/g, '').trim()
  const numericPattern = /^[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[+-]?\d+)?$/i
  if (!numericPattern.test(numericText)) {
    return isPercent ? 0 : value
  }
  const numValue = Number(numericText)
  if (!Number.isFinite(numValue)) {
    return isPercent ? 0 : value
  }
  return numValue
}

function roundedNumber(value: number) {
  return Number(value.toFixed(6))
}

function isPercentAxis(axis: ChartAxis) {
  const text = `${axis.name || ''} ${axis.value || ''}`.toLowerCase()
  return (
    text.includes('%') ||
    text.includes('rate') ||
    text.includes('ratio') ||
    text.includes('percent') ||
    text.includes('率') ||
    text.includes('占比') ||
    text.includes('百分比')
  )
}

function groupKeyFor(row: ChartData, axes: Array<ChartAxis>) {
  return axes.map((axis) => String(row?.[axis.value] ?? '')).join('')
}

export function aggregateChartData(
  x: Array<ChartAxis>,
  y: Array<ChartAxis>,
  series: Array<ChartAxis>,
  data: Array<ChartData>
) {
  const groupAxes = [...x, ...series]
  if (groupAxes.length === 0 || y.length === 0 || data.length === 0) {
    return data
  }
  const counts = new Map<string, number>()
  for (const row of data) {
    const key = groupKeyFor(row, groupAxes)
    counts.set(key, (counts.get(key) || 0) + 1)
  }
  if (![...counts.values()].some((count) => count > 1)) {
    return data
  }
  const grouped = new Map<string, ChartData>()
  const stats = new Map<string, Record<string, { sum: number; count: number; percent: boolean }>>()
  for (const row of data) {
    const key = groupKeyFor(row, groupAxes)
    if (!grouped.has(key)) {
      const item: ChartData = {}
      for (const axis of groupAxes) {
        item[axis.value] = row?.[axis.value]
      }
      grouped.set(key, item)
      stats.set(key, {})
    }
    const groupStats = stats.get(key)!
    for (const axis of y) {
      const raw = row?.[axis.value]
      const numeric = toChartNumber(raw)
      if (typeof numeric !== 'number' || !Number.isFinite(numeric)) {
        continue
      }
      const current = groupStats[axis.value] || { sum: 0, count: 0, percent: false }
      current.sum += numeric
      current.count += 1
      current.percent = current.percent || isPercentAxis(axis) || String(raw).trim().endsWith('%')
      groupStats[axis.value] = current
    }
  }
  for (const [key, item] of grouped.entries()) {
    const groupStats = stats.get(key) || {}
    for (const axis of y) {
      const metricStats = groupStats[axis.value]
      if (!metricStats || metricStats.count === 0) {
        item[axis.value] = null
        continue
      }
      const value = metricStats.percent ? metricStats.sum / metricStats.count : metricStats.sum
      item[axis.value] = metricStats.percent ? `${roundedNumber(value)}%` : roundedNumber(value)
    }
  }
  return [...grouped.values()]
}

export function getAxesWithFilter(axes: ChartAxis[]): {
  x: ChartAxis[]
  y: ChartAxis[]
  series: ChartAxis[]
  multiQuota: string[]
  multiQuotaName?: string
} {
  const groups = {
    x: [] as ChartAxis[],
    y: [] as ChartAxis[],
    series: [] as ChartAxis[],
    multiQuota: [] as string[],
    multiQuotaName: undefined as string | undefined,
  }
  axes.forEach((axis) => {
    if (axis.type === 'x') groups.x.push(axis)
    else if (axis.type === 'y') groups.y.push(axis)
    else if (axis.type === 'series') groups.series.push(axis)
    else if (axis.type === 'other-info') groups.multiQuotaName = axis.value
  })
  if (groups.series.length > 0) {
    groups.y = groups.y.slice(0, 1)
  } else {
    const multiQuotaY = groups.y.filter((item) => item['multi-quota'] === true)
    groups.multiQuota = multiQuotaY.map((item) => item.value)
    if (multiQuotaY.length > 0) {
      groups.y = multiQuotaY
    }
  }
  return groups
}

export function processMultiQuotaData(
  x: Array<ChartAxis>,
  y: Array<ChartAxis>,
  multiQuota: Array<string>,
  multiQuotaName: string = 'sqlbot_auto_series',
  data: Array<ChartData>
) {
  const _list: Array<ChartData> = []
  const _map: { [propName: string]: string } = {}
  y.forEach((axis) => {
    _map[axis.value] = axis.name
  })
  for (const datum of data) {
    multiQuota.forEach((quota) => {
      const _data: { [propName: string]: any } = {}
      for (const xAxis of x) {
        _data[xAxis.value] = datum[xAxis.value]
      }
      _data['sqlbot_auto_quota'] = datum[quota]
      _data['sqlbot_auto_series'] = _map[quota]
      _list.push(_data)
    })
  }
  return {
    data: _list,
    y: [{ name: 'sqlbot_auto_quota', value: 'sqlbot_auto_quota', type: 'y' } as ChartAxis],
    series: [{ name: multiQuotaName, value: 'sqlbot_auto_series', type: 'series' } as ChartAxis],
  }
}

export function checkIsPercent(
  valueAxes: Array<ChartAxis>,
  data: Array<ChartData>
): { isPercent: boolean; data: Array<ChartData> } {
  const result = { isPercent: false, data: [] as Array<ChartData> }
  for (let i = 0; i < data.length; i++) {
    result.data.push({ ...data[i] })
  }
  for (let i = 0; i < data.length; i++) {
    for (const valueAxis of valueAxes) {
      const value = data[i]?.[valueAxis.value]
      if (value !== null && value !== undefined && value !== '') {
        const strValue = String(value).trim()
        if (endsWith(strValue, '%')) {
          result.isPercent = true
        }
        result.data[i][valueAxis.value] = toChartNumber(value)
      }
    }
  }
  return result
}

export interface NormalizedChartData {
  x: ChartAxis[]
  y: ChartAxis[]
  series: ChartAxis[]
  rows: ChartData[]
  isPercent: boolean
}

/** 一次性完成 multi-quota 展开 → 聚合 → 百分比探测，返回 builder 所需全部信息。 */
export function normalizeChartData(axis: ChartAxis[], data: ChartData[]): NormalizedChartData {
  const grouped = getAxesWithFilter(axis)
  let rows = data
  let y = grouped.y
  let series = grouped.series
  if (grouped.multiQuota.length > 0) {
    const unfolded = processMultiQuotaData(
      grouped.x,
      y,
      grouped.multiQuota,
      grouped.multiQuotaName,
      rows
    )
    rows = unfolded.data
    y = unfolded.y
    series = unfolded.series
  }
  const aggregated = aggregateChartData(grouped.x, y, series, rows)
  const checked = checkIsPercent(y, aggregated)
  return { x: grouped.x, y, series, rows: checked.data, isPercent: checked.isPercent }
}
