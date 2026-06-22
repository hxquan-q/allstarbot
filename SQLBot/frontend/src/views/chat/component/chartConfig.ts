import type { ChartAxis, ChartData, ChartTypes } from '@/views/chat/component/BaseChart.ts'

export type ChartAxisItem = ChartAxis & { [key: string]: any }

export type ChartConfig = {
  type?: ChartTypes | string
  title?: string
  reason?: string
  summary?: string
  insights?: Array<string>
  alternatives?: Array<ChartConfig>
  axis?: {
    x?: ChartAxisItem | string
    y?: ChartAxisItem | string | Array<ChartAxisItem | string>
    series?: ChartAxisItem | string
    'multi-quota'?: {
      name: string
      value: Array<string> | string
    }
  }
  columns?: Array<ChartAxisItem | string>
  [key: string]: any
}

export const CHART_TYPES: Array<ChartTypes> = [
  'table',
  'bar',
  'column',
  'line',
  'pie',
  'scatter',
  'area',
]

function isRecord(value: unknown): value is Record<string, any> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function stripCodeFence(value: string) {
  const trimmed = value.trim()
  return trimmed
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/\s*```$/i, '')
    .trim()
}

function extractJsonCandidate(value: string) {
  const text = stripCodeFence(value)
  const start = text.search(/[{[]/)
  if (start < 0) {
    return text
  }

  const stack: string[] = []
  let inString = false
  let escaped = false
  for (let i = start; i < text.length; i++) {
    const char = text[i]
    if (escaped) {
      escaped = false
      continue
    }
    if (char === '\\') {
      escaped = true
      continue
    }
    if (char === '"') {
      inString = !inString
      continue
    }
    if (inString) {
      continue
    }
    if (char === '{' || char === '[') {
      stack.push(char)
    } else if (char === '}' || char === ']') {
      const last = stack[stack.length - 1]
      const matched = (char === '}' && last === '{') || (char === ']' && last === '[')
      if (!matched) {
        stack.length = 0
        continue
      }
      stack.pop()
      if (stack.length === 0) {
        return text.slice(start, i + 1)
      }
    }
  }

  return text
}

export function safeJsonParse<T>(value: unknown, fallback: T): T {
  if (isRecord(value) || Array.isArray(value)) {
    return value as T
  }
  if (typeof value !== 'string' || !value.trim()) {
    return fallback
  }

  const candidate = extractJsonCandidate(value)
  try {
    return JSON.parse(candidate)
  } catch (error) {
    console.warn('Failed to parse JSON:', error, candidate)
    return fallback
  }
}

export function normalizeFieldName(value?: string) {
  return String(value || '')
    .trim()
    .replace(/^[`"'[]+|[`"'\]]+$/g, '')
    .split('.')
    .pop()
    ?.replace(/\s+/g, '')
    .toLowerCase()
}

function isNumericValue(value: any) {
  if (typeof value === 'number') {
    return Number.isFinite(value)
  }
  if (typeof value !== 'string') {
    return false
  }
  const text = value.trim().replace(/,/g, '').replace(/%$/, '')
  return text !== '' && Number.isFinite(Number(text))
}

export function isNumericField(field: string, data: Array<ChartData>) {
  const values = data
    .map((row) => row?.[field])
    .filter((value) => value !== null && value !== undefined && value !== '')
  if (values.length === 0) {
    return false
  }
  return values.some(isNumericValue) && values.every((value) => isNumericValue(value))
}

export function dataFieldsFrom(data: Array<ChartData>, fields?: Array<string>) {
  const result: Array<string> = []
  for (const field of fields || []) {
    if (field !== undefined && field !== null && !result.includes(String(field))) {
      result.push(String(field))
    }
  }
  for (const row of data || []) {
    if (!isRecord(row)) {
      continue
    }
    for (const field of Object.keys(row)) {
      if (!result.includes(field)) {
        result.push(field)
      }
    }
  }
  return result
}

export function toAxisItem(item: any): ChartAxisItem | undefined {
  if (!item) {
    return undefined
  }
  if (typeof item === 'string') {
    return { name: item, value: item }
  }
  if (isRecord(item)) {
    const value = item.value ?? item.name
    if (!value) {
      return undefined
    }
    return { ...item, name: item.name ?? value, value: String(value) }
  }
  return undefined
}

export function isAxisItem(item: unknown): item is ChartAxisItem {
  return isRecord(item) && typeof item.value === 'string' && item.value.length > 0
}

export function resolveField(item: ChartAxisItem | undefined, dataFields: Array<string>) {
  if (!item || dataFields.length === 0) {
    return item?.value
  }
  if (dataFields.includes(item.value)) {
    return item.value
  }
  if (dataFields.includes(item.name)) {
    return item.name
  }

  const normalizedValue = normalizeFieldName(item.value)
  const normalizedName = normalizeFieldName(item.name)
  return dataFields.find((field) => {
    const normalizedField = normalizeFieldName(field)
    return normalizedField === normalizedValue || normalizedField === normalizedName
  })
}

export function resolveAxisItem(item: any, dataFields: Array<string>) {
  const axisItem = toAxisItem(item)
  const field = resolveField(axisItem, dataFields)
  if (!axisItem || !field) {
    return undefined
  }
  return {
    ...axisItem,
    value: field,
  }
}

export function inferAxisItem(
  role: 'x' | 'y',
  dataFields: Array<string>,
  data: Array<ChartData>,
  chartType?: ChartTypes | string
) {
  if (dataFields.length === 0) {
    return undefined
  }
  if (chartType === 'scatter') {
    const numericFields = dataFields.filter((field) => isNumericField(field, data))
    const field = role === 'x' ? numericFields[0] : numericFields[1] ?? numericFields[0]
    return field ? { name: field, value: field } : undefined
  }
  const field =
    role === 'y'
      ? dataFields.find((item) => isNumericField(item, data))
      : dataFields.find((item) => !isNumericField(item, data)) ?? dataFields[0]
  return field ? { name: field, value: field } : undefined
}

function normalizeChartType(type?: string): ChartTypes {
  return CHART_TYPES.includes(type as ChartTypes) ? (type as ChartTypes) : 'table'
}

function normalizeColumns(columns: ChartConfig['columns'], dataFields: Array<string>) {
  const rawColumns = Array.isArray(columns) ? columns : columns ? [columns] : []
  const resolved = rawColumns
    .map((item) => resolveAxisItem(item, dataFields))
    .filter(Boolean) as Array<ChartAxisItem>
  if (resolved.length > 0) {
    return resolved
  }
  return dataFields.map((field) => ({ name: field, value: field }))
}

function normalizeAxis(config: ChartConfig, dataFields: Array<string>, data: Array<ChartData>) {
  const type = normalizeChartType(config.type)
  const axis = config.axis || {}
  const normalized: ChartConfig['axis'] = {}

  if (type === 'table') {
    return normalized
  }

  if (type === 'pie') {
    const series = resolveAxisItem(axis.series, dataFields) ?? inferAxisItem('x', dataFields, data, type)
    const y = resolveAxisItem(axis.y, dataFields) ?? inferAxisItem('y', dataFields, data, type)
    if (series) {
      normalized.series = series
    }
    if (y) {
      normalized.y = y
    }
    return normalized
  }

  const x = resolveAxisItem(axis.x, dataFields) ?? inferAxisItem('x', dataFields, data, type)
  const rawY = Array.isArray(axis.y) ? axis.y : axis.y ? [axis.y] : []
  const y = rawY
    .map((item) => resolveAxisItem(item, dataFields))
    .filter(Boolean) as Array<ChartAxisItem>
  const inferredY = y.length > 0 ? y : inferAxisItem('y', dataFields, data, type)
  const series = resolveAxisItem(axis.series, dataFields)
  const rawMultiQuotaValue = axis['multi-quota']?.value
  const rawMultiQuotaValues = Array.isArray(rawMultiQuotaValue)
    ? rawMultiQuotaValue
    : rawMultiQuotaValue
      ? [rawMultiQuotaValue]
      : []
  const multiQuotaValues = rawMultiQuotaValues
    .map((field) => resolveField({ name: field, value: field }, dataFields))
    .filter(Boolean) as Array<string>

  if (x) {
    normalized.x = x
  }
  normalized.y = Array.isArray(inferredY) ? inferredY : inferredY ? [inferredY] : []
  if (series) {
    normalized.series = series
  } else if (multiQuotaValues.length > 1) {
    normalized['multi-quota'] = {
      name: axis['multi-quota']?.name || '指标',
      value: multiQuotaValues,
    }
    normalized.y = (normalized.y as Array<ChartAxisItem>).map((item) => ({
      ...item,
      'multi-quota': multiQuotaValues.includes(item.value),
    }))
  }

  return normalized
}

export function normalizeChartConfig(
  config: ChartConfig | undefined,
  data: Array<ChartData>,
  fields?: Array<string>
): ChartConfig {
  const dataFields = dataFieldsFrom(data, fields)
  const type = normalizeChartType(config?.type)
  const normalized: ChartConfig = {
    ...(config || {}),
    type,
    title: config?.title || '',
  }

  if (type === 'table') {
    normalized.columns = normalizeColumns(config?.columns, dataFields)
    delete normalized.axis
    return normalized
  }

  normalized.axis = normalizeAxis(normalized, dataFields, data)
  if (
    !normalized.axis ||
    (type === 'pie' && (!normalized.axis.series || !normalized.axis.y)) ||
    (type !== 'pie' && (!normalized.axis.x || !(normalized.axis.y as Array<ChartAxisItem>)?.length))
  ) {
    normalized.type = 'table'
    normalized.columns = normalizeColumns(config?.columns, dataFields)
    delete normalized.axis
  }

  return normalized
}

export function canRenderChartConfig(config: ChartConfig | undefined) {
  if (!config) {
    return false
  }
  if (config.type === 'table') {
    return (config.columns || []).length > 0
  }
  if (config.type === 'pie') {
    return Boolean(config.axis?.series && config.axis?.y)
  }
  return Boolean(config.axis?.x && Array.isArray(config.axis?.y) && config.axis.y.length > 0)
}
