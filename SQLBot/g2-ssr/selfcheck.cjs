// ponytail: 自检——验证 echarts node 出图真能产出非空 PNG（中文标签依赖系统字体不出豆腐）
const fs = require('fs')
const { render } = require('./render.cjs')

const outPath = '/tmp/echarts-ssr-selfcheck'
const file = render({
  type: 'column',
  axis: JSON.stringify([
    { name: '区域', value: 'x', type: 'x' },
    { name: '销量', value: 'y', type: 'y' },
  ]),
  data: JSON.stringify([
    { x: '华东', y: 126 },
    { x: '华北', y: 86 },
    { x: '华南', y: 98 },
  ]),
  path: outPath,
})

const size = fs.statSync(file).size
if (size < 1000) {
  console.error(`FAIL: ${file} 过小（${size} bytes）—— 可能空白或中文出豆腐`)
  process.exit(1)
}
console.log(`PASS: ${file} = ${size} bytes`)
