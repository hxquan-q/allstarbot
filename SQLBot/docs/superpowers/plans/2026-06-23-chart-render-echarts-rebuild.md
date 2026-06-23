# 图表渲染引擎重建 G2→ECharts 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 ECharts（echarts + vue-echarts）替换 `@antv/g2` 作为前端图表渲染引擎，根除白屏/不可靠渲染，删除像素采样 hack 与运行时 SSR 回退，单一配置源消灭前后端漂移，并保留 `type='table'`（S2）路径与所有公共 props 契约不变。

**Architecture:** 新增 `echarts/` 模块（setup 注册 + data 单一数据源 + theme + builders + options 调度器）。`ChartComponent.vue` 改用 `<VChart>`（SVG 渲染、autoresize），table 分支保留 S2 `Table` 类。删除 G2 引擎文件与依赖。纯函数模块 TDD（`node --experimental-strip-types`），Vue 组件靠 `vue-tsc` + 手测矩阵。

**Tech Stack:** Vue 3.5 / vite 6 / TS 5.7 / element-plus / lodash-es / echarts 5 / vue-echarts 7 / @antv/s2（table 保留）。

参考 spec：`docs/superpowers/specs/2026-06-23-chart-render-echarts-rebuild-design.md`

---

## 文件结构

**新增**
- `frontend/src/views/chat/component/echarts/setup.ts` — echarts core 按需注册，导出 `VChart`（SVG 渲染器）。
- `frontend/src/views/chat/component/echarts/data.ts` — 唯一数据加工源（formatNumber / aggregate / percent / multi-quota / normalizeChartData）。
- `frontend/src/views/chat/component/echarts/theme.ts` — 调色板 + 数值 formatter。
- `frontend/src/views/chat/component/echarts/builders/cartesian.ts` — bar/column/line/area（共享 buildSeries）。
- `frontend/src/views/chat/component/echarts/builders/pie.ts` — pie。
- `frontend/src/views/chat/component/echarts/builders/scatter.ts` — scatter。
- `frontend/src/views/chat/component/echarts/options.ts` — 调度器 `buildEChartsOption`（含逃生口合并/消毒）。
- 测试：`echarts/data.test.mjs`、`echarts/options.test.mjs`。

**重写**
- `frontend/src/views/chat/component/ChartComponent.vue` — VChart + table 分支；公共 props/expose 不变。
- `frontend/src/views/chat/component/DisplayChartBlock.vue` — 增传 `:echarts`（可选，逃生口）。
- `frontend/src/views/chat/component/charts/Table.ts` — `formatNumber` import 改指 `echarts/data.ts`。
- `frontend/src/views/chat/component/charts/chartAggregation.test.mjs` — import 改指 `echarts/data.ts`。

**删除（迁完后）**
- `frontend/src/views/chat/component/BaseG2Chart.ts`
- `frontend/src/views/chat/component/charts/{Bar,Column,Line,Pie,Area,Scatter}.ts`
- `frontend/src/views/chat/component/charts/utils.ts`
- `frontend/src/views/chat/component/index.ts`（G2 实例注册表）
- `frontend/package.json` 中 `@antv/g2` 依赖

---

### Task 1: 安装依赖 + echarts setup 模块

**Files:**
- Modify: `SQLBot/frontend/package.json`
- Create: `SQLBot/frontend/src/views/chat/component/echarts/setup.ts`

- [ ] **Step 1: 安装 echarts 与 vue-echarts**

Run（在 `SQLBot/frontend` 下）:
```bash
npm install echarts@^5.5 vue-echarts@^7
```
Expected: 两个包写入 `package.json` `dependencies`，`node_modules` 安装成功。

- [ ] **Step 2: 创建 setup.ts（按需注册 + 导出 VChart）**

Create `SQLBot/frontend/src/views/chat/component/echarts/setup.ts`:
```ts
import { use } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DatasetComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'

use([
  SVGRenderer,
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DatasetComponent,
])

export default VChart
```

- [ ] **Step 3: 类型检查通过**

Run:
```bash
cd SQLBot/frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | tail -20
```
Expected: 无关于 `echarts/setup.ts` 的错误（项目原有无关报错可忽略，重点看新文件无错）。若 `tsconfig.app.json` 不存在则用 `npx vue-tsc --noEmit`。

- [ ] **Step 4: Commit**

```bash
git add SQLBot/frontend/package.json SQLBot/frontend/package-lock.json SQLBot/frontend/src/views/chat/component/echarts/setup.ts
git commit -m "feat(chart): 引入 echarts + vue-echarts 并注册 SVG 渲染器"
```

---

### Task 2: 单一数据源 echarts/data.ts（TDD）

**Files:**
- Create: `SQLBot/frontend/src/views/chat/component/echarts/data.ts`
- Test: `SQLBot/frontend/src/views/chat/component/echarts/data.test.mjs`

- [ ] **Step 1: 写失败测试（含 normalizeChartData 行为）**

Create `SQLBot/frontend/src/views/chat/component/echarts/data.test.mjs`:
```js
// Run with: node --experimental-strip-types src/views/chat/component/echarts/data.test.mjs
import assert from 'node:assert/strict'
import {
  aggregateChartData,
  checkIsPercent,
  formatNumber,
  getAxesWithFilter,
  normalizeChartData,
  processMultiQuotaData,
} from './data.ts'

// formatNumber: 千分符
assert.equal(formatNumber(1234567), '1,234,567')
assert.equal(formatNumber('1234.5'), '1,234.5')
assert.equal(formatNumber(''), '')

// aggregateChartData: 同维度求和
const x = [{ name: '供应商等级', value: '供应商等级', type: 'x' }]
const data = [
  { '供应商等级': 'B', '采购总量': 10, '收货达成率': '70%' },
  { '供应商等级': 'B', '采购总量': 20, '收货达成率': '80%' },
  { '供应商等级': 'A', '采购总量': 5, '收货达成率': '90%' },
]
const totals = aggregateChartData(x, [{ name: '采购总量', value: '采购总量', type: 'y' }], [], data)
assert.deepEqual(
  Object.fromEntries(totals.map((row) => [row['供应商等级'], row['采购总量']])),
  { B: 30, A: 5 }
)

// checkIsPercent: 探测 % 并转数值
const yRate = [{ name: '收货达成率', value: '收货达成率', type: 'y' }]
const checked = checkIsPercent(yRate, aggregateChartData(x, yRate, [], data))
assert.equal(checked.isPercent, true)

// processMultiQuotaData: 多指标展开为 long 表
const multi = processMultiQuotaData(
  x,
  [{ name: '采购总量', value: '采购总量', type: 'y' }, { name: '收货总量', value: '收货总量', type: 'y' }],
  ['采购总量', '收货总量'],
  '指标',
  [{ '供应商等级': 'A', '采购总量': 1, '收货总量': 2 }]
)
assert.equal(multi.data.length, 2)
assert.equal(multi.series[0].value, 'sqlbot_auto_series')
assert.equal(multi.y[0].value, 'sqlbot_auto_quota')

// normalizeChartData: 一次性 multi-quota + 聚合
const axis = [
  { name: '供应商等级', value: '供应商等级', type: 'x' },
  { name: '采购总量', value: '采购总量', type: 'y', 'multi-quota': true },
  { name: '收货总量', value: '收货总量', type: 'y', 'multi-quota': true },
  { name: '指标', value: '指标', type: 'other-info' },
]
const norm = normalizeChartData(axis, [{ '供应商等级': 'A', '采购总量': 3, '收货总量': 4 }])
assert.equal(norm.series.length, 1)
assert.equal(norm.rows.length, 2) // 两个指标各一行
assert.equal(norm.y[0].value, 'sqlbot_auto_quota')

// getAxesWithFilter
const grouped = getAxesWithFilter(axis)
assert.deepEqual(grouped.multiQuota.sort(), ['收货总量', '采购总量'])

console.log('data.test.mjs OK')
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd SQLBot/frontend && node --experimental-strip-types src/views/chat/component/echarts/data.test.mjs
```
Expected: FAIL（`Cannot find module './data.ts'`）。

- [ ] **Step 3: 实现 data.ts（从 charts/utils.ts 移植 + normalizeChartData）**

Create `SQLBot/frontend/src/views/chat/component/echarts/data.ts`:
```ts
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
  return axes.map((axis) => String(row?.[axis.value] ?? '')).join('')
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

export function checkIsPercent(valueAxes: Array<ChartAxis>, data: Array<ChartData>): {
  isPercent: boolean
  data: Array<ChartData>
} {
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
    const unfolded = processMultiQuotaData(grouped.x, y, grouped.multiQuota, grouped.multiQuotaName, rows)
    rows = unfolded.data
    y = unfolded.y
    series = unfolded.series
  }
  const aggregated = aggregateChartData(grouped.x, y, series, rows)
  const checked = checkIsPercent(y, aggregated)
  return { x: grouped.x, y, series, rows: checked.data, isPercent: checked.isPercent }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
cd SQLBot/frontend && node --experimental-strip-types src/views/chat/component/echarts/data.test.mjs
```
Expected: 输出 `data.test.mjs OK`。

- [ ] **Step 5: Commit**

```bash
git add SQLBot/frontend/src/views/chat/component/echarts/data.ts SQLBot/frontend/src/views/chat/component/echarts/data.test.mjs
git commit -m "feat(chart): 单一数据加工源 echarts/data.ts（含 normalizeChartData）"
```

---

### Task 3: theme.ts（调色板 + formatter）

**Files:**
- Create: `SQLBot/frontend/src/views/chat/component/echarts/theme.ts`

- [ ] **Step 1: 创建 theme.ts**

Create `SQLBot/frontend/src/views/chat/component/echarts/theme.ts`:
```ts
import { formatNumber } from './data'

/** 与原 G2 版本一致的 SQLBOT 配色。 */
export const SQLBOT_PALETTE = [
  '#5B8FF9',
  '#5AD8A6',
  '#F6BD16',
  '#E8684A',
  '#6DC8EC',
  '#9270CA',
  '#FF9D4D',
  '#269A99',
  '#FF99C3',
  '#BDD2FD',
]

/** 坐标轴刻度 formatter：千分符 + 百分号。 */
export function axisLabelFormatter(isPercent = false) {
  return (value: any) => `${formatNumber(value)}${isPercent ? '%' : ''}`
}

/** tooltip / label 的数值 formatter。 */
export function valueFormatter(isPercent = false) {
  return (value: any) => `${formatNumber(value)}${isPercent ? '%' : ''}`
}
```

- [ ] **Step 2: Commit**

```bash
git add SQLBot/frontend/src/views/chat/component/echarts/theme.ts
git commit -m "feat(chart): echarts theme（调色板 + 数值 formatter）"
```

---

### Task 4: builders（cartesian / pie / scatter）+ options 调度器（TDD）

**Files:**
- Create: `SQLBot/frontend/src/views/chat/component/echarts/builders/cartesian.ts`
- Create: `SQLBot/frontend/src/views/chat/component/echarts/builders/pie.ts`
- Create: `SQLBot/frontend/src/views/chat/component/echarts/builders/scatter.ts`
- Create: `SQLBot/frontend/src/views/chat/component/echarts/options.ts`
- Test: `SQLBot/frontend/src/views/chat/component/echarts/options.test.mjs`

- [ ] **Step 1: 写失败测试（每种图型 option 结构断言）**

Create `SQLBot/frontend/src/views/chat/component/echarts/options.test.mjs`:
```js
// Run with: node --experimental-strip-types src/views/chat/component/echarts/options.test.mjs
import assert from 'node:assert/strict'
import { buildEChartsOption } from './options.ts'

const rows = [
  { 城市: '北京', 销量: 100, 利润: 30 },
  { 城市: '上海', 销量: 120, 利润: 40 },
  { 城市: '广州', 销量: 80, 利润: 20 },
]
function axisOf(type) {
  if (type === 'pie') {
    return [
      { name: '城市', value: '城市', type: 'series' },
      { name: '销量', value: '销量', type: 'y' },
    ]
  }
  if (type === 'scatter') {
    return [
      { name: '销量', value: '销量', type: 'x' },
      { name: '利润', value: '利润', type: 'y' },
    ]
  }
  return [
    { name: '城市', value: '城市', type: 'x' },
    { name: '销量', value: '销量', type: 'y' },
  ]
}

// column
let opt = buildEChartsOption({ type: 'column', axis: axisOf('column'), data: rows })
assert.equal(opt.xAxis.type, 'category')
assert.deepEqual(opt.xAxis.data, ['北京', '上海', '广州'])
assert.equal(opt.yAxis.type, 'value')
assert.equal(opt.series[0].type, 'bar')
assert.deepEqual(opt.series[0].data, [100, 120, 80])

// bar（横向）
opt = buildEChartsOption({ type: 'bar', axis: axisOf('bar'), data: rows })
assert.equal(opt.xAxis.type, 'value')
assert.equal(opt.yAxis.type, 'category')
assert.equal(opt.series[0].type, 'bar')

// line
opt = buildEChartsOption({ type: 'line', axis: axisOf('line'), data: rows })
assert.equal(opt.series[0].type, 'line')
assert.equal(opt.series[0].areaStyle, undefined)

// area
opt = buildEChartsOption({ type: 'area', axis: axisOf('area'), data: rows })
assert.equal(opt.series[0].type, 'line')
assert.deepEqual(opt.series[0].areaStyle, {})

// pie
opt = buildEChartsOption({ type: 'pie', axis: axisOf('pie'), data: rows })
assert.equal(opt.series[0].type, 'pie')
assert.deepEqual(opt.series[0].data.map((d) => d.name), ['北京', '上海', '广州'])
assert.deepEqual(opt.series[0].data.map((d) => d.value), [100, 120, 80])

// scatter
opt = buildEChartsOption({ type: 'scatter', axis: axisOf('scatter'), data: rows })
assert.equal(opt.series[0].type, 'scatter')
assert.deepEqual(opt.series[0].data[0], [100, 30])

// 逃生口合并（echarts 字段覆盖）
opt = buildEChartsOption({
  type: 'column',
  axis: axisOf('column'),
  data: rows,
  echarts: { yAxis: { max: 200 } },
})
assert.equal(opt.yAxis.max, 200)
assert.equal(opt.series[0].type, 'bar') // 基础结构仍在

// 逃生口消毒：函数被剥离（JSON 序列化丢弃）
opt = buildEChartsOption({
  type: 'column',
  axis: axisOf('column'),
  data: rows,
  echarts: { title: { fn: () => 'x' } },
})
assert.equal(opt.title.fn, undefined)

console.log('options.test.mjs OK')
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd SQLBot/frontend && node --experimental-strip-types src/views/chat/component/echarts/options.test.mjs
```
Expected: FAIL（`Cannot find module './options.ts'`）。

- [ ] **Step 3: 实现 builders/cartesian.ts**

Create `SQLBot/frontend/src/views/chat/component/echarts/builders/cartesian.ts`:
```ts
import type { ChartAxis, ChartData } from '../../BaseChart.ts'
import { formatNumber, type NormalizedChartData } from '../data'
import { axisLabelFormatter } from '../theme'

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
    label: showLabel ? { show: true, position: 'right', formatter: s.label?.formatter } : undefined,
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
```

- [ ] **Step 4: 实现 builders/pie.ts**

Create `SQLBot/frontend/src/views/chat/component/echarts/builders/pie.ts`:
```ts
import type { NormalizedChartData } from '../data'
import { formatNumber } from '../data'

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
```

- [ ] **Step 5: 实现 builders/scatter.ts**

Create `SQLBot/frontend/src/views/chat/component/echarts/builders/scatter.ts`:
```ts
import type { NormalizedChartData } from '../data'
import { axisLabelFormatter, valueFormatter } from '../theme'

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
```

- [ ] **Step 6: 实现 options.ts（调度器 + 逃生口）**

Create `SQLBot/frontend/src/views/chat/component/echarts/options.ts`:
```ts
import { merge } from 'lodash-es'
import type { ChartAxis, ChartData } from '../BaseChart.ts'
import { formatNumber, normalizeChartData } from './data'
import { SQLBOT_PALETTE } from './theme'
import { buildArea, buildBar, buildColumn, buildLine } from './builders/cartesian'
import { buildPie } from './builders/pie'
import { buildScatter } from './builders/scatter'

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

  const common: Record<string, any> = {
    color: SQLBOT_PALETTE,
    grid: { left: 12, right: 24, top: norm.series.length > 0 ? 40 : 20, bottom: 12, containLabel: true },
    tooltip: {
      trigger: type === 'pie' || type === 'scatter' ? 'item' : 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: (value: any) => `${formatNumber(value)}${norm.isPercent ? '%' : ''}`,
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
```

- [ ] **Step 7: 运行测试确认通过**

Run:
```bash
cd SQLBot/frontend && node --experimental-strip-types src/views/chat/component/echarts/options.test.mjs
```
Expected: 输出 `options.test.mjs OK`。

- [ ] **Step 8: Commit**

```bash
git add SQLBot/frontend/src/views/chat/component/echarts/builders SQLBot/frontend/src/views/chat/component/echarts/options.ts SQLBot/frontend/src/views/chat/component/echarts/options.test.mjs
git commit -m "feat(chart): echarts builders + options 调度器（含逃生口消毒合并）"
```

---

### Task 5: 重写 ChartComponent.vue（VChart + table 分支）

**Files:**
- Modify: `SQLBot/frontend/src/views/chat/component/ChartComponent.vue`（整体重写）

约束：公共 props（`id, type, data, columns, x, y, series, multiQuotaName, showLabel, recordId`）与 `defineExpose({ renderChart, destroyChart, getExcelData })` 保持不变；新增**可选** `echarts?: object`（逃生口，向后兼容）。`type === 'table'` 继续用 S2 `Table` 类。

- [ ] **Step 1: 整体重写 ChartComponent.vue**

Replace the entire contents of `SQLBot/frontend/src/views/chat/component/ChartComponent.vue` with:
```vue
<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import VChart from '@/views/chat/component/echarts/setup'
import { buildEChartsOption } from '@/views/chat/component/echarts/options'
import { Table } from '@/views/chat/component/charts/Table.ts'
import type { BaseChart, ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
import { useEmitt } from '@/utils/useEmitt.ts'

const params = withDefaults(
  defineProps<{
    id: string | number
    type: string
    data?: Array<ChartData>
    columns?: Array<ChartAxis>
    x?: Array<ChartAxis>
    y?: Array<ChartAxis>
    series?: Array<ChartAxis>
    multiQuotaName?: string | undefined
    showLabel?: boolean
    recordId?: number
    echarts?: Record<string, any>
  }>(),
  {
    data: () => [],
    columns: () => [],
    x: () => [],
    y: () => [],
    series: () => [],
    multiQuotaName: undefined,
    showLabel: false,
    recordId: undefined,
    echarts: undefined,
  }
)

const chartId = computed(() => 'chart-component-' + params.id)
const isTable = computed(() => params.type === 'table')

const axis = computed(() => {
  const _list: Array<ChartAxis> = []
  params.columns.forEach((column) => {
    _list.push({ name: column.name, value: column.value })
  })
  params.x.forEach((column) => {
    _list.push({ name: column.name, value: column.value, type: 'x' })
  })
  params.y.forEach((column) => {
    _list.push({
      name: column.name,
      value: column.value,
      type: 'y',
      'multi-quota': column['multi-quota'],
    })
  })
  params.series.forEach((column) => {
    _list.push({ name: column.name, value: column.value, type: 'series' })
  })
  if (params.multiQuotaName) {
    _list.push({ name: params.multiQuotaName, value: params.multiQuotaName, type: 'other-info', hidden: true })
  }
  return _list
})

const option = computed(() =>
  isTable.value
    ? {}
    : buildEChartsOption({
        type: params.type,
        axis: axis.value,
        data: params.data,
        showLabel: params.showLabel,
        echarts: params.echarts,
      })
)

// --- table（S2）分支：沿用原 Table 类 ---
let tableInstance: BaseChart | undefined
const vchartRef = ref<any>(undefined)

function renderTable() {
  if (!isTable.value) {
    return
  }
  tableInstance?.destroy?.()
  tableInstance = new Table(chartId.value)
  tableInstance.showLabel = params.showLabel
  tableInstance.init(axis.value, params.data)
  tableInstance.render()
}

function renderChart() {
  if (isTable.value) {
    nextTick(renderTable)
  } else {
    vchartRef.value?.resize?.()
  }
}

function destroyChart() {
  if (tableInstance) {
    tableInstance.destroy?.()
    tableInstance = undefined
  }
  // VChart 随组件卸载自动 dispose
}

function getExcelData() {
  return {
    axis: axis.value,
    data: params.data,
  }
}

useEmitt({
  name: 'view-render-all',
  callback: renderChart,
})

useEmitt({
  name: `view-render-${params.id}`,
  callback: renderChart,
})

defineExpose({
  renderChart,
  destroyChart,
  getExcelData,
})

watch(
  [() => params.type, () => params.data, axis, () => params.showLabel],
  () => {
    if (isTable.value) {
      nextTick(renderTable)
    }
  },
  { deep: true }
)

onMounted(() => {
  if (isTable.value) {
    nextTick(renderTable)
  }
})

onUnmounted(() => {
  destroyChart()
})
</script>

<template>
  <div class="chart-container-wrap">
    <VChart
      v-if="!isTable"
      ref="vchartRef"
      class="chart-container"
      :option="option"
      :autoresize="true"
      :update-options="{ notMerge: true }"
    />
    <div v-else :id="chartId" class="chart-container"></div>
  </div>
</template>

<style scoped lang="less">
.chart-container-wrap {
  position: relative;
  height: 100%;
  min-height: 320px;
  width: 100%;
}

.chart-container {
  height: 100%;
  min-height: 320px;
  width: 100%;
}
</style>
```

- [ ] **Step 2: 类型检查**

Run:
```bash
cd SQLBot/frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -i "ChartComponent\|echarts/" | head
```
Expected: 无输出（无相关错误）。若 `tsconfig.app.json` 不存在，去掉 `-p` 参数。

- [ ] **Step 3: 启动 dev server 冒烟（手测）**

Run（后台或新终端）:
```bash
cd SQLBot/frontend && npm run dev
```
人工验证：打开聊天页，触发任意会出图的问题，确认 column/bar/line/area/pie/scatter 均渲染（SVG）、resize 正常、切到 table 仍为 S2 表格、无白屏。结束后停止 dev server。

- [ ] **Step 4: Commit**

```bash
git add SQLBot/frontend/src/views/chat/component/ChartComponent.vue
git commit -m "feat(chart): ChartComponent 改用 vue-echarts（SVG），table 分支保留 S2"
```

---

### Task 6: DisplayChartBlock 透传逃生口 + Table/测试 import 改指

**Files:**
- Modify: `SQLBot/frontend/src/views/chat/component/DisplayChartBlock.vue`
- Modify: `SQLBot/frontend/src/views/chat/component/charts/Table.ts`（import 行）
- Modify: `SQLBot/frontend/src/views/chat/component/charts/chartAggregation.test.mjs`（import 行）

- [ ] **Step 1: DisplayChartBlock 透传 echarts 字段**

在 `SQLBot/frontend/src/views/chat/component/DisplayChartBlock.vue` 的 `<ChartComponent>` 上增加 `:echarts` 绑定。定位模板中 `<ChartComponent ... :record-id="message.record.id" />`，改为：
```vue
    <ChartComponent
      v-if="message.record.id && data?.length > 0 && canRender"
      :id="id ?? 'default_chat_id'"
      ref="chartRef"
      :type="normalizedChartObject.type || chartType"
      :columns="columns"
      :x="xAxis"
      :y="yAxis"
      :series="series"
      :data="data"
      :multi-quota-name="multiQuotaName"
      :show-label="showLabel"
      :record-id="message.record.id"
      :echarts="normalizedChartObject.echarts"
    />
```

- [ ] **Step 2: Table.ts 的 formatNumber import 改指 echarts/data**

在 `SQLBot/frontend/src/views/chat/component/charts/Table.ts` 顶部，将：
```ts
import { formatNumber } from '@/views/chat/component/charts/utils.ts'
```
改为：
```ts
import { formatNumber } from '@/views/chat/component/echarts/data.ts'
```

- [ ] **Step 3: chartAggregation.test.mjs import 改指 echarts/data**

在 `SQLBot/frontend/src/views/chat/component/charts/chartAggregation.test.mjs` 顶部，将：
```js
import { aggregateChartData } from './utils.ts'
```
改为：
```js
import { aggregateChartData } from '../echarts/data.ts'
```

- [ ] **Step 4: 运行迁移后的旧测试**

Run:
```bash
cd SQLBot/frontend && node --experimental-strip-types src/views/chat/component/charts/chartAggregation.test.mjs && node --experimental-strip-types src/views/chat/component/chartConfig.test.mjs
```
Expected: 两个测试均无断言失败（chartConfig.test.mjs 不依赖 utils，应原样通过）。

- [ ] **Step 5: Commit**

```bash
git add SQLBot/frontend/src/views/chat/component/DisplayChartBlock.vue SQLBot/frontend/src/views/chat/component/charts/Table.ts SQLBot/frontend/src/views/chat/component/charts/chartAggregation.test.mjs
git commit -m "refactor(chart): 透传 echarts 逃生口 + Table/测试 import 改指 echarts/data"
```

---

### Task 7: 删除 G2 引擎文件 + 移除依赖

**Files:**
- Delete: `SQLBot/frontend/src/views/chat/component/BaseG2Chart.ts`
- Delete: `SQLBot/frontend/src/views/chat/component/charts/Bar.ts`
- Delete: `SQLBot/frontend/src/views/chat/component/charts/Column.ts`
- Delete: `SQLBot/frontend/src/views/chat/component/charts/Line.ts`
- Delete: `SQLBot/frontend/src/views/chat/component/charts/Pie.ts`
- Delete: `SQLBot/frontend/src/views/chat/component/charts/Area.ts`
- Delete: `SQLBot/frontend/src/views/chat/component/charts/Scatter.ts`
- Delete: `SQLBot/frontend/src/views/chat/component/charts/utils.ts`
- Delete: `SQLBot/frontend/src/views/chat/component/index.ts`
- Modify: `SQLBot/frontend/package.json`（移除 `@antv/g2`）

- [ ] **Step 1: 确认待删文件无残留引用**

Run:
```bash
cd SQLBot/frontend && grep -rn "charts/utils\|charts/Bar\|charts/Column\|charts/Line\|charts/Pie\|charts/Area\|charts/Scatter\|BaseG2Chart\|component/index\|getChartInstance\|@antv/g2" src/ || echo "NO_REFS"
```
Expected: `NO_REFS`（`charts/Table.ts`、`chartConfig.test.mjs` 已在 Task 6 改指；`ChartComponent.vue` 已在 Task 5 去除 `getChartInstance`）。若有残留，先修正再继续。

- [ ] **Step 2: 删除文件**

Run:
```bash
cd SQLBot/frontend && rm -f \
  src/views/chat/component/BaseG2Chart.ts \
  src/views/chat/component/charts/Bar.ts \
  src/views/chat/component/charts/Column.ts \
  src/views/chat/component/charts/Line.ts \
  src/views/chat/component/charts/Pie.ts \
  src/views/chat/component/charts/Area.ts \
  src/views/chat/component/charts/Scatter.ts \
  src/views/chat/component/charts/utils.ts \
  src/views/chat/component/index.ts
```

- [ ] **Step 3: 从 package.json 移除 @antv/g2**

编辑 `SQLBot/frontend/package.json`，删除依赖行：
```json
    "@antv/g2": "^5.3.3",
```
（保留 `@antv/s2`、`@antv/x6`。）然后：
```bash
cd SQLBot/frontend && npm install
```
Expected: `package-lock.json` 更新，`@antv/g2` 从 `node_modules` 移除（若无其他依赖间接需要）。

- [ ] **Step 4: 类型检查 + 构建**

Run:
```bash
cd SQLBot/frontend && npx vue-tsc -b 2>&1 | tail -20
```
Expected: 无错误。若有 `@antv/g2` 相关报错说明有遗漏引用，回到 Step 1 排查。

- [ ] **Step 5: Commit**

```bash
git add -A SQLBot/frontend
git commit -m "refactor(chart): 删除 G2 引擎文件与 @antv/g2 依赖"
```

---

### Task 8: 全量回归（类型 + 构建 + 测试 + 手测矩阵）

**Files:**
- 验证性任务，不改代码

- [ ] **Step 1: 全部单测**

Run:
```bash
cd SQLBot/frontend && \
node --experimental-strip-types src/views/chat/component/echarts/data.test.mjs && \
node --experimental-strip-types src/views/chat/component/echarts/options.test.mjs && \
node --experimental-strip-types src/views/chat/component/charts/chartAggregation.test.mjs && \
node --experimental-strip-types src/views/chat/component/chartConfig.test.mjs
```
Expected: 四个测试均输出 OK / 无断言失败。

- [ ] **Step 2: 生产构建**

Run:
```bash
cd SQLBot/frontend && npm run build 2>&1 | tail -25
```
Expected: 构建成功，产物正常输出，无 `@antv/g2` / G2 相关报错。

- [ ] **Step 3: 手测矩阵（dev server）**

Run:
```bash
cd SQLBot/frontend && npm run dev
```
逐项验证（聊天页 + dashboard `sq-view` 各一遍）：
- column / bar / line / area / pie / scatter 六图型均正确渲染（SVG）
- 单系列 + 多系列（series）均正确
- 百分比字段（含 `%`/`率`）轴显示百分号
- multi-quota 多指标正确展开
- resize 容器后图表自适应（autoresize）
- 切换图型 ↔ table（S2）来回切换无残留/白屏
- 无数据 / 配置无法渲染 → `el-empty` 提示
- 逃生口：临时给某 record 的 `chart.echarts` 注入 `{ yAxis: { max: N } }` 验证覆盖生效

- [ ] **Step 4: 最终 Commit（如有手测中发现的小修）**

```bash
git add -A SQLBot/frontend && git commit -m "test(chart): 全量回归通过（echarts 引擎）" || echo "无需提交"
```

---

## 自检（计划 vs spec）

- **Spec §4 文件地图**：setup/data/theme/builders/options 全部有任务（T1-T4）；ChartComponent 重写（T5）；DisplayChartBlock/Table/test 改指（T6）；G2 文件删除 + 依赖移除（T7）。覆盖。
- **Spec §5 契约 + 逃生口**：T4 实现 sanitize+merge，T5 加可选 prop，T6 透传。覆盖。
- **Spec §6 单一数据源**：T2 data.ts + 测试。覆盖。
- **Spec §7 ChartComponent（公共 props/expose 不变、SVG、删 hack）**：T5 逐条实现；table 分支保留（探索阶段确认 ChartComponent 会收到 `type='table'`）。覆盖。
- **Spec §8 各图型 builder**：T3/T4 实现 column/bar/line/area/pie/scatter，含百分比/series/label。覆盖。
- **Spec §9 依赖变更**：T1 加 echarts/vue-echarts，T7 删 @antv/g2。覆盖。
- **Spec §10 导出/静态图路径**：T5 删除运行时 `get_chart_image` 调用与像素采样 hack；后端端点保留（非破坏性）。覆盖。
- **Spec §11 测试**：T2/T4/T8 纯函数 TDD + 手测矩阵。覆盖。
- **占位符扫描**：无 TBD/TODO，所有代码步骤含完整代码。
- **类型一致性**：`NormalizedChartData`（data.ts 定义）被 builders/options 一致使用；`BuildInput` 字段（type/axis/data/showLabel/echarts）在 options 与 ChartComponent 调用处一致；`formatNumber` 签名贯穿 data/theme/builders/options 一致。
