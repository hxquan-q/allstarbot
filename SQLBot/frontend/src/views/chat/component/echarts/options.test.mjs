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

// 单位标注（unit）：通用后缀追加，不写死任何折叠特例
const yuanRows = [
  { 城市: '北京', 金额: 8216389 },
  { 城市: '上海', 金额: 50000 },
]
const yuanAxis = [
  { name: '城市', value: '城市', type: 'x' },
  { name: '金额', value: '金额', type: 'y', unit: '元' },
]
opt = buildEChartsOption({ type: 'column', axis: yuanAxis, data: yuanRows, showLabel: true })
assert.equal(opt.yAxis.axisLabel.formatter(8216389), '8,216,389 元') // 通用：千分符 + 单位后缀
assert.equal(opt.tooltip.valueFormatter(50000), '50,000 元') // tooltip 同样
assert.equal(opt.series[0].label.formatter({ value: 8216389 }), '8,216,389 元') // 标注

const tonAxis = [
  { name: '城市', value: '城市', type: 'x' },
  { name: '重量', value: '重量', type: 'y', unit: '吨' },
]
opt = buildEChartsOption({ type: 'column', axis: tonAxis, data: [{ 城市: '北京', 重量: 1500 }] })
assert.equal(opt.yAxis.axisLabel.formatter(1500), '1,500 吨') // 任意单位一视同仁

// 任意非中文单位同样通用追加
const pcsAxis = [
  { name: '城市', value: '城市', type: 'x' },
  { name: '件数', value: '件数', type: 'y', unit: 'pcs' },
]
opt = buildEChartsOption({ type: 'column', axis: pcsAxis, data: [{ 城市: '北京', 件数: 1200 }] })
assert.equal(opt.yAxis.axisLabel.formatter(1200), '1,200 pcs')

// 百分比数据优先：直接显示百分数
const pctAxis = [
  { name: '城市', value: '城市', type: 'x' },
  { name: '达成率', value: '达成率', type: 'y', unit: '%' },
]
opt = buildEChartsOption({ type: 'column', axis: pctAxis, data: [{ 城市: '北京', 达成率: '85%' }] })
assert.equal(opt.yAxis.axisLabel.formatter(85), '85%') // isPercent → 85%

// bar 横向：value 轴是 xAxis，通用追加
opt = buildEChartsOption({ type: 'bar', axis: yuanAxis, data: yuanRows })
assert.equal(opt.xAxis.axisLabel.formatter(8216389), '8,216,389 元')

console.log('options.test.mjs OK')
