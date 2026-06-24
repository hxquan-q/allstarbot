// 出图样张生成：复用 g2-ssr/render.cjs（与生产同一条 echarts 链路），不再依赖 G2。
const fs = require('fs')
const path = require('path')
const { render, createCanvas } = require('../g2-ssr/render.cjs')

const outputDir = '/tmp/chart-render-check'

const regionData = [
  { region: '华东', sales: 126, profit: 32, category: 'A类' },
  { region: '华南', sales: 98, profit: 22, category: 'A类' },
  { region: '华北', sales: 86, profit: 18, category: 'B类' },
  { region: '西南', sales: 72, profit: 14, category: 'B类' },
  { region: '西北', sales: 55, profit: 10, category: 'C类' },
]

const trendData = [
  { month: '1月', value: 34, category: '线上' },
  { month: '2月', value: 42, category: '线上' },
  { month: '3月', value: 53, category: '线上' },
  { month: '4月', value: 61, category: '线上' },
  { month: '5月', value: 76, category: '线上' },
  { month: '1月', value: 28, category: '线下' },
  { month: '2月', value: 36, category: '线下' },
  { month: '3月', value: 41, category: '线下' },
  { month: '4月', value: 48, category: '线下' },
  { month: '5月', value: 58, category: '线下' },
]

const scatterData = [
  { cost: '18', revenue: '36', segment: '成熟客户' },
  { cost: '28', revenue: '48', segment: '成熟客户' },
  { cost: '35', revenue: '58', segment: '成熟客户' },
  { cost: '24', revenue: '30', segment: '新客户' },
  { cost: '42', revenue: '55', segment: '新客户' },
  { cost: '57', revenue: '72', segment: '新客户' },
  { cost: '62', revenue: '96', segment: '重点客户' },
  { cost: '73', revenue: '118', segment: '重点客户' },
]

const cases = [
  { type: 'column', name: '柱状图', axis: [{ name: '地区', value: 'region', type: 'x' }, { name: '销售额', value: 'sales', type: 'y' }], data: regionData },
  { type: 'bar', name: '条形图', axis: [{ name: '地区', value: 'region', type: 'x' }, { name: '利润', value: 'profit', type: 'y' }], data: regionData },
  { type: 'line', name: '折线图', axis: [{ name: '月份', value: 'month', type: 'x' }, { name: '指标值', value: 'value', type: 'y' }, { name: '渠道', value: 'category', type: 'series' }], data: trendData },
  { type: 'pie', name: '饼图', axis: [{ name: '销售额', value: 'sales', type: 'y' }, { name: '地区', value: 'region', type: 'series' }], data: regionData },
  { type: 'scatter', name: '散点图', axis: [{ name: '成本', value: 'cost', type: 'x' }, { name: '收入', value: 'revenue', type: 'y' }, { name: '客户分层', value: 'segment', type: 'series' }], data: scatterData },
  { type: 'area', name: '面积图', axis: [{ name: '月份', value: 'month', type: 'x' }, { name: '指标值', value: 'value', type: 'y' }, { name: '渠道', value: 'category', type: 'series' }], data: trendData },
]

// ponytail: 明细表前端走 @antv/s2，这里用原生 canvas 画一张展示样张（与 echarts 无关，独立保留）
function renderTableSample() {
  const file = path.join(outputDir, 'table.png')
  const canvas = createCanvas(760, 460)
  const ctx = canvas.getContext('2d')
  const columns = [
    { title: '地区', key: 'region', width: 160 },
    { title: '销售额', key: 'sales', width: 150 },
    { title: '利润', key: 'profit', width: 140 },
    { title: '分类', key: 'category', width: 150 },
  ]
  const rows = regionData
  const left = 55
  const top = 72
  const rowHeight = 46

  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, 760, 460)
  ctx.fillStyle = '#1f2329'
  ctx.font = 'bold 24px sans-serif'
  ctx.fillText('明细表', left, 42)
  ctx.font = '13px sans-serif'
  ctx.fillStyle = '#646a73'
  ctx.fillText('前端实际由 @antv/s2 渲染；此样张用于报告展示。', left + 90, 42)

  ctx.strokeStyle = '#dee0e3'
  ctx.lineWidth = 1
  ctx.fillStyle = '#f5f7fb'
  ctx.fillRect(left, top, 600, rowHeight)
  ctx.strokeRect(left, top, 600, rowHeight * (rows.length + 1))

  let x = left
  ctx.font = 'bold 15px sans-serif'
  ctx.fillStyle = '#1f2329'
  columns.forEach((column) => {
    ctx.strokeRect(x, top, column.width, rowHeight)
    ctx.fillText(column.title, x + 16, top + 29)
    x += column.width
  })

  ctx.font = '14px sans-serif'
  rows.forEach((row, rowIndex) => {
    const y = top + rowHeight * (rowIndex + 1)
    ctx.fillStyle = rowIndex % 2 === 0 ? '#ffffff' : '#fafafa'
    ctx.fillRect(left, y, 600, rowHeight)
    x = left
    columns.forEach((column) => {
      ctx.strokeStyle = '#eff0f1'
      ctx.strokeRect(x, y, column.width, rowHeight)
      ctx.fillStyle = '#1f2329'
      ctx.fillText(String(row[column.key]), x + 16, y + 29)
      x += column.width
    })
  })

  fs.writeFileSync(file, canvas.toBuffer('image/png'))
  return file
}

function renderAll() {
  fs.mkdirSync(outputDir, { recursive: true })
  const tableFile = renderTableSample()
  const results = [
    {
      type: 'table',
      name: '明细表',
      status: 'pass',
      note: `前端 Table 使用 @antv/s2；样张 PNG ${fs.statSync(tableFile).size} bytes`,
      file: 'table.png',
    },
  ]

  for (const item of cases) {
    const file = render({
      type: item.type,
      axis: JSON.stringify(item.axis),
      data: JSON.stringify(item.data),
      path: path.join(outputDir, item.type),
    })
    const size = fs.statSync(file).size
    results.push({
      type: item.type,
      name: item.name,
      status: size > 1000 ? 'pass' : 'fail',
      note: size > 1000 ? `生成 PNG ${size} bytes` : `PNG 过小 ${size} bytes`,
      file: `${item.type}.png`,
    })
  }

  fs.writeFileSync(path.join(outputDir, 'results.json'), JSON.stringify(results, null, 2))
  console.log(JSON.stringify(results, null, 2))
}

try {
  renderAll()
} catch (error) {
  console.error(error)
  process.exit(1)
}
