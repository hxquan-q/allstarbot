# g2-ssr 出图：node-canvas → @napi-rs/canvas（根除 Docker 静默失败）

- 日期：2026-06-24
- 范围：`SQLBot/g2-ssr` Node 出图服务的 canvas 实现（`render.cjs` + `package.json` + `Dockerfile`）
- 决策人：用户拍板 canvas 实现 = `@napi-rs/canvas`（放弃 SVG-SSR / 换 Vega / 修补 node-canvas）
- 状态：设计待用户复核 → 转实现计划
- 前置：承接 `2026-06-23-chart-render-echarts-rebuild-design.md`（G2→ECharts 重构已完成）。注意：那份 spec 把 `/record/{id}/image` 端点列为"保留死路径"，但当前未提交改动已**重新激活该端点**（前端 `api/chat.ts` 加了 `get_chart_image`）——因此 g2-ssr 现在又是活的，其可靠性直接影响前端取图体验。

---

## 1. 问题诊断（根因）

用户反馈：**Linux/Docker 环境下 g2-ssr 经常静默失败或只渲染出空白图片。**

根因**不是 echarts，也不是字体**（g2-ssr 已带 `Arial_Unicode.ttf` = Arial Unicode MS，含中文 CJK），而是 **`node-canvas` 的原生编译与系统图形库依赖**：

1. 当前 `g2-ssr/render.cjs` 走 `require('canvas')` → `createCanvas()` → `echarts.init(canvas, {renderer:'canvas'})` → `canvas.toBuffer('image/png')`，依赖 **node-canvas**。
2. `Dockerfile` 用 `npm_config_build_from_source=true npm install` **从源码编译** node-canvas，要求 base image 具备 cairo/pango/libjpeg/libpng 开发头文件 + python/make/g++ 工具链。
3. node-canvas 运行时**动态链接** cairo/pango/fontconfig/libpng。Docker 环境任一库版本不符/缺失 → 编译失败或运行时静默失败/空白。
4. 这是 canvas 图形栈的通病，与 G2/echarts 无关——上周 G2→echarts 重构已消除引擎层问题，但 node-canvas 这层未动，故 Docker 静默失败依旧。

## 2. 目标 / 非目标

**目标**
- 用 `@napi-rs/canvas`（Google Skia 的 Node-API 绑定，**0 系统依赖、预编译多平台二进制**）替换 node-canvas，根除 Docker 编译失败与系统库缺失导致的静默失败。
- 改动封闭在 g2-ssr 内部（3 个文件）；**PNG 输出、文件命名契约、echarts 渲染逻辑、builder、前端、LLM 契约全部不变**。

**非目标（本次不做）**
- 不改输出格式（PNG→SVG 不做，保留 PNG 链路）。
- 不换 echarts 为 Vega（已评估放弃，见 §3）。
- 不改 `buildEChartsOption` builder、前端 vue-echarts、后端 LLM chart-config 契约（`record.chart` 结构）。
- base image 里 cairo/pango 的瘦身留作后续可选（不影响 @napi-rs/canvas）。
- `request_picture` 的运行时错误暴露（它不检查 g2-ssr HTTP 500）留作后续可选改进。

## 3. 方案选型（已拍板）

**选定：`@napi-rs/canvas`。** 理由：node-canvas 的 drop-in 替代，基于 Skia 静态链接、预编译、0 系统依赖，直击编译/系统库根因；同时**保留 PNG 输出与 echarts canvas renderer**，契约零改动，改动面最小。

放弃项：
- **echarts SVG-SSR**（`renderToSVGString`）：同样能绕开 node-canvas（纯 JS SVG），但要改输出格式 PNG→SVG，连带后端 image 端点 `media_type`、文件命名、潜在下游 PNG 消费者；改动涟漪更大。作为 @napi-rs/canvas 若不达标时的备选。
- **换 Vega**：`view.toSVG()` 同样绕开 canvas，但需重写 chart-config→Vega spec builder、推翻刚完成的 ECharts 重构、前端要重写或造成两套真源、Vega-Lite spec 更冗长易使 LLM 生成更不准。性价比远低于 @napi-rs/canvas。
- **修补 node-canvas**（运行时校验/重试/字体固定/Docker 装库）：治标不治本，用户已"经常静默失败"。

## 4. 架构（文件地图）

改动 3 个文件：

| 文件 | 改动 |
|---|---|
| `g2-ssr/package.json` | 移除 `canvas`，加 `@napi-rs/canvas`（最新稳定） |
| `g2-ssr/render.cjs` | `require('canvas')`→`require('@napi-rs/canvas')`；接入 `echarts.setPlatformAPI`；启动加载系统字体 |
| `Dockerfile`（ssr-builder 段） | 去掉 `npm_config_build_from_source=true`；`Arial_Unicode.ttf` COPY 保留 |

**不改**：`app.js`（HTTP/POST/错误处理）、`selfcheck.cjs`（仅改走新实现，逻辑不变）、`scripts/generate_chart_samples.js`、后端 `chat.py`/`request_picture`/`config.py`、前端任何文件。

## 5. 关键实现要点

### 5.1 render.cjs 目标形态
```js
const fs = require('fs')
const { createCanvas, GlobalFonts } = require('@napi-rs/canvas')
const echarts = require('echarts')
const { buildEChartsOption } = require('./lib/chart-option.cjs')

// @napi-rs/canvas 默认不加载系统字体（与 node-canvas 关键差异）——漏了中文空白
GlobalFonts.loadSystemFonts() // 读取 /usr/share/fonts（含已 COPY 的 Arial Unicode MS）

// echarts 经官方扩展点注入 canvas 实现（echarts 5.3+，当前 ^5.6.0 支持）
const _measurer = createCanvas(1, 1).getContext('2d')
echarts.setPlatformAPI({
  createCanvas: (w, h) => createCanvas(w, h),
  measureText: (text, font) => { _measurer.font = font || ''; return _measurer.measureText(text) },
})

function render(obj) {
  const option = buildEChartsOption({
    type: obj.type,
    axis: JSON.parse(obj.axis || '[]'),
    data: JSON.parse(obj.data || '[]'),
    showLabel: true,
  })
  option.animation = false // node 无 rAF：关动画，setOption 同步绘出最终态
  const W = 640, H = 480
  const canvas = createCanvas(W, H)
  const chart = echarts.init(canvas, null, { renderer: 'canvas', width: W, height: H })
  try {
    chart.setOption(option)
    const file = (obj.path || 'chart') + '.png' // 契约不变：后端 request_picture 读 {file_name}.png
    fs.writeFileSync(file, canvas.toBuffer('image/png'))
    return file
  } finally {
    chart.dispose() // pm2 长驻：不 dispose 按请求泄漏 canvas
  }
}

module.exports = { render, WIDTH: 640, HEIGHT: 480 }
```

### 5.2 字体加载差异（核心坑）
- node-canvas 自动经 fontconfig 发现系统字体。
- @napi-rs/canvas **默认不加载**任何字体，必须 `GlobalFonts.loadSystemFonts()`（或 `GlobalFonts.registerFromPath(path, family)` 逐个注册）。漏了这步 → 中文回到空白。
- 护栏：`selfcheck.cjs` 用中文样本，出图 < 1000 bytes 判失败。

### 5.3 echarts.setPlatformAPI
- echarts 不直接 `require('canvas')`，而是经 `setPlatformAPI({ createCanvas, measureText, loadImage })` 注入平台实现（官方为非浏览器环境设计的扩展点）。
- `measureText(text, font)`：@napi-rs/canvas 的 measureText 在 2d context 上，需先 set `ctx.font`。

### 5.4 PNG 契约不变
- 输出仍 `.png`、`image/png`；`request_picture` 写 `c_{chat_id}_r_{record_id}.png`，image 端点读同路径、返回 `media_type="image/png"`——**全部不动**。

## 6. 验证策略

1. **本地 selfcheck**：`node g2-ssr/selfcheck.cjs`，中文柱状图出 PNG 非空（≥1000 bytes）。
2. **Docker 构建冒烟**：`docker build` 成功且**无 canvas 源码编译**（@napi-rs/canvas 预编译下载）；构建后跑 selfcheck 非空。
3. **端到端**：触发一次 `request_picture`（经 image 端点），确认 `/opt/sqlbot/images/c_*_r_*.png` 生成且前端能展示，中文标签非空白。

## 7. 风险与回退

| 风险 | 应对 |
|---|---|
| @napi-rs/canvas 与 echarts canvas renderer 个别 API 不兼容 | `setPlatformAPI` 是官方扩展点；若发现渲染差异，回退到 SVG-SSR 方案（§3 备选） |
| 预编译二进制平台不匹配（musl/glibc、arm64） | base image 是 `dataease/sqlbot-base`（glibc x64），对应 `@napi-rs/canvas-linux-x64-gnu`；实现时确认 base 平台后选对应包 |
| 字体加载 API 变动 | selfcheck 中文样本是护栏；若 `loadSystemFonts` 不可用，改 `registerFromPath` 显式注册 `Arial_Unicode.ttf` |
| 回退 | git revert 3 个文件改动即完全回到 node-canvas 现状，无数据/契约影响 |

## 8. 参考资料

- [@napi-rs/canvas — 0 system dependencies Skia canvas](https://github.com/Brooooooklyn/canvas)
- [ECharts `setPlatformAPI` for non-browser environments](https://github.com/apache/echarts-doc/blob/master/en/api/echarts.md)
