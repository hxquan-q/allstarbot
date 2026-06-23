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
