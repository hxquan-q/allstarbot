// ponytail: echarts node 出图——契约 {path,type,data,axis}（data/axis 为 JSON 字符串）
// 与前端 buildEChartsOption 共用单一 builder（g2-ssr/lib/chart-option.cjs 由 frontend 打包产出）
// canvas 实现用 @napi-rs/canvas（Skia 预编译，0 系统依赖），根除 node-canvas 在 Docker 的编译/缺库静默失败
const fs = require('fs')
const { createCanvas, GlobalFonts } = require('@napi-rs/canvas')
const echarts = require('echarts')
const { buildEChartsOption } = require('./lib/chart-option.cjs')

const WIDTH = 640
const HEIGHT = 480

// @napi-rs/canvas 默认不加载系统字体（与 node-canvas 关键差异）——漏了中文回到空白
// 读取 /usr/share/fonts（Docker 已 COPY Arial_Unicode.ttf，含中文 CJK）+ 宿主系统字体
GlobalFonts.loadSystemFonts()

// echarts 经官方扩展点注入 canvas 实现（echarts 5.3+，当前 ^5.6.0 支持）
// ponytail: 复用一个 1x1 measurer context 扛 measureText，避免每次渲染新建
const _measurer = createCanvas(1, 1).getContext('2d')
echarts.setPlatformAPI({
  // ponytail: echarts 内部多处 argless 调 createCanvas()（decal/heatmap/progressive）；|| 0 兜底，否则 @napi-rs/canvas 对 undefined throw
  createCanvas: (w, h) => createCanvas(w || 0, h || 0),
  measureText: (text, font) => {
    _measurer.font = font || ''
    return _measurer.measureText(text)
  },
})

function render(obj) {
  const option = buildEChartsOption({
    type: obj.type,
    axis: JSON.parse(obj.axis || '[]'),
    data: JSON.parse(obj.data || '[]'),
    showLabel: true, // 静态图带标签，与旧 G2 出图行为对齐
  })
  option.animation = false // node 无 rAF：关动画，setOption 同步绘出最终态，toBuffer 不抓空白帧
  const canvas = createCanvas(WIDTH, HEIGHT)
  const chart = echarts.init(canvas, null, { renderer: 'canvas', width: WIDTH, height: HEIGHT })
  try {
    chart.setOption(option)
    const file = (obj.path || 'chart') + '.png' // 后端 request_picture 读 {file_name}.png，后缀锁死
    fs.writeFileSync(file, canvas.toBuffer('image/png'))
    return file
  } finally {
    chart.dispose() // pm2 长驻：不 dispose 按请求泄漏 canvas
  }
}

module.exports = { render, WIDTH, HEIGHT, createCanvas }
