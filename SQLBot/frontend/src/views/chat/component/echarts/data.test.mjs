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
