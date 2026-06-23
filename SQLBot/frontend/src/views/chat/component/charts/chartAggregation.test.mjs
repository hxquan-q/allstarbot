// Run with: node --experimental-strip-types src/views/chat/component/charts/chartAggregation.test.mjs
import assert from 'node:assert/strict'
import { aggregateChartData } from '../echarts/data.ts'

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

const rates = aggregateChartData(x, [{ name: '收货达成率', value: '收货达成率', type: 'y' }], [], data)
assert.deepEqual(
  Object.fromEntries(rates.map((row) => [row['供应商等级'], row['收货达成率']])),
  { B: '75%', A: '90%' }
)

console.log('chartAggregation: 2 passed')
