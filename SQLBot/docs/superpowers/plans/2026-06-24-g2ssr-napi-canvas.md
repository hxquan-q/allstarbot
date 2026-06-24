# g2-ssr 换 @napi-rs/canvas 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 g2-ssr 的 Node 出图 canvas 实现从 `node-canvas` 换成 `@napi-rs/canvas`，根除 Docker/Linux 下 node-canvas 编译失败与系统库缺失导致的静默失败/空白图。

**Architecture:** 仅改 3 个文件（`g2-ssr/package.json`、`g2-ssr/render.cjs`、`Dockerfile` [+ `Dockerfile-8888`]）。`@napi-rs/canvas` 是 node-canvas 的 drop-in 替代（基于 Google Skia、预编译、0 系统依赖），经 echarts 官方 `setPlatformAPI` 注入。PNG 输出、文件命名契约、`buildEChartsOption` builder、前端、LLM 契约全部不变。

**Tech Stack:** Node.js（宿主 v26 / Docker node18）、`@napi-rs/canvas`、`echarts ^5.6.0`、`pm2`。

**前置基线（已验证，2026-06-24）：** 宿主跑 `node g2-ssr/selfcheck.cjs` **失败**，报 `Cannot find module '../build/Release/canvas.node'`——node-canvas 原生二进制未编译。这就是要根除的症状。换 @napi-rs/canvas 后该 selfcheck 应转为 PASS。

**对应 spec：** `docs/superpowers/specs/2026-06-24-g2ssr-napi-canvas-design.md`

**约定：** 所有命令在 `SQLBot/` 根目录下执行（除非另注）。commit 信息末尾加 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。**只 `git add` 本任务涉及的文件**——working tree 有用户并行编辑的前端改动，绝不 `git add -A` / `git add .`。

---

### Task 1: package.json 换依赖（canvas → @napi-rs/canvas）

**Files:**
- Modify: `SQLBot/g2-ssr/package.json`

- [ ] **Step 1: 确认换前 selfcheck 红（基线）**

Run:
```bash
cd SQLBot/g2-ssr && node selfcheck.cjs 2>&1 | head -5
```
Expected: FAIL，含 `Cannot find module '../build/Release/canvas.node'`（node-canvas 未编译）。记录这条——Task 2 完成后它应消失。

- [ ] **Step 2: 改 package.json，移除 canvas、加 @napi-rs/canvas**

把 `SQLBot/g2-ssr/package.json` 的 `dependencies` 改为：
```json
{
  "name": "g2-ssr",
  "private": true,
  "version": "0.0.0",
  "dependencies": {
    "@napi-rs/canvas": "^0.1.55",
    "echarts": "^5.6.0",
    "pm2": "^6.0.13"
  },
  "devDependencies": {
    "@types/node": "^18.6.3"
  }
}
```
> 版本说明：`^0.1.55` 为下限锚点；Step 3 的 `npm install` 会拉取实际最新版并回写 `package.json`。如装到的版本更高，以 npm 回写值为准，无需手动改。

- [ ] **Step 3: 安装（同步依赖树：卸 canvas、装 @napi-rs/canvas 预编译）**

Run:
```bash
cd SQLBot/g2-ssr && npm install 2>&1 | tail -15
```
Expected: 成功；**无 node-gyp/源码编译输出**（@napi-rs/canvas 走预编译下载，对应宿主平台包如 `@napi-rs/canvas-linux-x64-gnu`）。

- [ ] **Step 4: 验证 @napi-rs/canvas 可加载（N-API 在 node26 兼容性冒烟）**

Run:
```bash
cd SQLBot/g2-ssr && node -e "const {createCanvas, GlobalFonts}=require('@napi-rs/canvas'); const c=createCanvas(10,10); console.log('OK', typeof c.getContext, 'canvas pkg gone:', !require('fs').existsSync('node_modules/canvas'))"
```
Expected: `OK function canvas pkg gone: true`。
> 若报 N-API/ABI 不兼容（node26 极新时低概率）：宿主降到 node20/22 验证；生产 Docker 是 node18，无此问题。记录现象，不阻塞——以 Docker（Task 4）为准。

- [ ] **Step 5: Commit**

```bash
cd SQLBot && git add g2-ssr/package.json g2-ssr/package-lock.json
git commit -m "build(g2-ssr): 依赖 canvas → @napi-rs/canvas（Skia 预编译，0 系统依赖）" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
> 若 `package-lock.json` 不存在（g2-ssr 未纳入 lock），只 add `package.json`。

---

### Task 2: render.cjs 接入 @napi-rs/canvas（setPlatformAPI + 字体加载）

**Files:**
- Modify: `SQLBot/g2-ssr/render.cjs`

- [ ] **Step 1: 用以下完整内容覆盖 `SQLBot/g2-ssr/render.cjs`**

```js
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
  createCanvas: (w, h) => createCanvas(w, h),
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

module.exports = { render, WIDTH, HEIGHT }
```

- [ ] **Step 2: 验证 selfcheck 转绿（红→绿的关键证据）**

Run:
```bash
cd SQLBot/g2-ssr && node selfcheck.cjs
```
Expected: `PASS: /tmp/echarts-ssr-selfcheck.png = <size> bytes`（size ≥ 1000；中文柱状图非空）。
> 对照 Task 1 Step 1 的红基线——同样的 selfcheck，换实现后从 fail 变 pass，即根因被消除。

- [ ] **Step 3: 若 PASS 但中文疑似空白（字体没加载上），人工抽查**

Run:
```bash
ls -la /tmp/echarts-ssr-selfcheck.png && file /tmp/echarts-ssr-selfcheck.png
```
Expected: 文件存在、类型 `PNG image data, 640 x 480`。若 size 在 1000~3000 bytes 之间且怀疑空白，用图片查看器确认中文标签可见；不可见则检查 `GlobalFonts.loadSystemFonts()` 返回的字体列表（宿主需有中文字体；Docker 有 Arial Unicode MS）。

- [ ] **Step 4: Commit**

```bash
cd SQLBot && git add g2-ssr/render.cjs
git commit -m "feat(g2-ssr): render.cjs 改用 @napi-rs/canvas + setPlatformAPI + loadSystemFonts" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: 6 图型冒烟（复用现有样张脚本，覆盖全图型）

**Files:**
- 无改动（运行 `SQLBot/scripts/generate_chart_samples.js`，它 `require('../g2-ssr/render.cjs')`，自动用新实现）

- [ ] **Step 1: 跑全图型样张生成**

Run:
```bash
cd SQLBot && node scripts/generate_chart_samples.js 2>&1 | tail -20
```
Expected: 在 `/tmp/chart-render-check/` 下生成 `column.png`、`bar.png`、`line.png`、`pie.png`、`scatter.png`、`area.png`、`table.png`，无报错。

- [ ] **Step 2: 确认各图型非空**

Run:
```bash
cd SQLBot && for f in column bar line pie scatter area table; do printf "%-8s " "$f"; stat -c '%s bytes' /tmp/chart-render-check/$f.png 2>/dev/null || echo MISSING; done
```
Expected: 每个图型都有 bytes 且 > 1000（table 是原生 canvas 画的，可能更小但应存在）。任何 MISSING 或过小 → 回查 Task 2 的字体/渲染。
> 此步只读验证，不 commit（无文件改动）。

---

### Task 4: Dockerfile 去掉 build_from_source（生产构建免编译）

**Files:**
- Modify: `SQLBot/Dockerfile`（ssr-builder 段）
- Modify: `SQLBot/Dockerfile-8888`（若含同样的 `npm_config_build_from_source=true`）

- [ ] **Step 1: 定位两处 build_from_source**

Run:
```bash
cd SQLBot && grep -n "build_from_source" Dockerfile Dockerfile-8888
```
Expected: 各显示一行，形如 `RUN npm_config_build_from_source=true npm install`。记录行号。

- [ ] **Step 2: 改 `Dockerfile`，去掉 build_from_source**

将该行：
```dockerfile
RUN npm_config_build_from_source=true npm install
```
改为：
```dockerfile
RUN npm install
```
> @napi-rs/canvas 预编译，无需 build_from_source；去掉它让 Docker 构建不再要求 cairo/pango 编译工具链。

- [ ] **Step 3: 同样改 `Dockerfile-8888`（若 Step 1 命中）**

对 `Dockerfile-8888` 中匹配的同一行做相同替换。若 8888 无此行，跳过本步并记录。

- [ ] **Step 4: 确认字体 COPY 仍在（中文依赖）**

Run:
```bash
cd SQLBot && grep -n "Arial_Unicode\|\.ttf" Dockerfile Dockerfile-8888
```
Expected: 仍含 `COPY g2-ssr/*.ttf ...`（Arial Unicode MS 含中文，必须保留）。**不应改动字体 COPY 行。**

- [ ] **Step 5: Docker 构建冒烟（验证免编译 + 出图）**

Run:
```bash
cd SQLBot && docker build -t sqlbot:ssr-smoke -f Dockerfile . 2>&1 | grep -iE "canvas|napi|skia|error|FAIL" | tail -20
```
Expected: 构建成功；日志中**无 node-canvas 源码编译**（无 `node-gyp`/`cairo`/`pango` 编译输出）；`@napi-rs/canvas-linux-x64-gnu` 预编译包被下载安装。
> 若 Docker 不可用，跳过本步并在交付说明里标注"生产构建待 CI/Docker 环境验证"——不阻塞本地已验证的 Task 2/3。

- [ ] **Step 6: Commit**

```bash
cd SQLBot && git add Dockerfile Dockerfile-8888
git commit -m "build(docker): g2-ssr 去掉 npm_config_build_from_source（@napi-rs/canvas 预编译免编译）" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
> 若 8888 无改动，只 add `Dockerfile`。

---

### Task 5: 端到端冒烟（可选，需完整运行环境）

**Files:** 无改动

- [ ] **Step 1: 触发一次真实出图链路**

在运行中的 SQLBot（backend + g2-ssr pm2）里，经前端或直接调 `/chat/record/{id}/image` 端点，触发一次 `request_picture` → g2-ssr 出图。

- [ ] **Step 2: 确认产物**

Run（容器内或挂载目录）:
```bash
ls -la /opt/sqlbot/images/c_*_r_*.png
```
Expected: 生成 `c_{chat_id}_r_{record_id}.png`，非空、中文标签可见，前端能正常展示。

- [ ] **Step 3: 回归确认无副作用**

确认 `request_picture`（`backend/apps/chat/task/llm.py:2096`）行为不变：写 `c_{chat_id}_r_{record_id}.png`，image 端点读同路径。无需改后端代码。
> 此任务依赖完整运行栈，若环境不具备可后置到部署阶段。

---

## Self-Review

**1. Spec coverage**
- §1 根因（node-canvas 编译/系统库）→ Task 1/2/4 替换实现，红基线（Task1 Step1）印证。✅
- §2 目标（保 PNG/builder/前端/LLM 契约）→ render.cjs 输出仍 `.png`/`toBuffer('image/png')`，无前端/后端/builder 改动。✅
- §3 选型 @napi-rs/canvas → Task 1。✅
- §4 文件地图（3 文件）→ Task 1/2/4。Dockerfile-8888 一致性在 Task 4 Step 1/3 覆盖。✅
- §5.2 字体加载差异（核心坑）→ render.cjs `GlobalFonts.loadSystemFonts()` + Task 2 Step 3 抽查 + Task 4 Step 4 字体 COPY 保留。✅
- §5.3 setPlatformAPI → render.cjs 注入 + Task 2。✅
- §5.4 PNG 契约不变 → render.cjs 后缀 `.png`、后端零改动。✅
- §6 验证（selfcheck/Docker/端到端）→ Task 2/4/5。✅
- §7 风险（平台包/字体 API/回退）→ Task 1 Step 4（node26 兼容）、Task 4 Step 5（Docker 冒烟）、git revert 回退路径明确。✅

**2. Placeholder scan**：无 TBD/TODO；每步含完整代码或 exact 命令 + 预期。✅

**3. Type consistency**：`render(obj)` 签名、`buildEChartsOption({type,axis,data,showLabel})` 契约、`WIDTH/HEIGHT=640/480`、文件名 `c_{chat_id}_r_{record_id}.png`、selfcheck 阈值 `< 1000` FAIL——前后一致，与现有 `request_picture`/`selfcheck.cjs` 对齐。✅

无 gap，计划可执行。
