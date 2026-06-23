# 图表渲染引擎重建：G2 → ECharts（vue-echarts）

- 日期：2026-06-23
- 范围：前端图表渲染引擎与展示层（`SQLBot/frontend`）
- 决策人：用户拍板渲染引擎 = ECharts + vue-echarts；其余自审批
- 状态：已自审批 → 进入实现

---

## 1. 问题诊断（根因）

"图表还是出问题"不是单个 bug，是三个架构性缺陷叠加：

1. **渲染引擎不可靠（核心病灶）**：`@antv/g2 ^5.3.3`（G2 v5）异步 canvas/WebGL 渲染会间歇性画空白。正因不可信，`ChartComponent.vue:213-243` 才写了一段**对 canvas 做像素采样判断全白**的 hack，空白则回退静态图。像素采样 × 异步渲染 = 竞态，正是反复遇到的"图出不来/白屏"。
2. **前后端两套配置手工同步且已漂移**：前端 `charts/{Bar,Column,Line,Pie,Area}.ts`（G2 v5）与 `g2-ssr/charts/*.js`（@antv/g2-ssr，跑在 `:3000` 的独立 Node 进程，带 23MB 字体）是两份手抄副本，已不一致（label 开关、`elementHighlight.region`、`tooltip.shared` 均不同）→ 回退静态图与实时图长得不同；`utils.ts`/`utils.js` 各一份 `aggregateChartData/checkIsPercent/processMultiQuotaData`。
3. **表现力天花板**：固定 bar/column/line/pie/area/scatter/table 七种，无双轴/组合/树图/漏斗/热力/桑基/地理 → "sqlbot 原来的局限"。

LLM → 图表的契约设计是好的：`backend/apps/chat/task/multi_dimension.py` 让 LLM 产出 `{type, axis:{x,y,series,multi-quota}, columns, title, summary, insights, alternatives}`，这是**图表意图**而非某库语法。**此契约保留不动。**

## 2. 目标 / 非目标

**目标**
- 用 ECharts（Apache echarts + vue-echarts）替换 G2 v5 作为唯一前端渲染引擎，根除白屏/不可靠渲染。
- 删除像素采样 hack 与运行时 SSR 回退链；单一配置源消灭前后端漂移。
- 突破图型限制：原生支持 30+ 图型，并保留一条"高级图逃生口"。
- 改动**封闭在前端图表引擎内部**，两个消费者（`ChartBlock.vue` 聊天路径、`sq-view` 仪表盘）的公共 props 契约不变。

**非目标（v1 不做）**
- 不改后端 LLM 契约 / `multi_dimension.py` prompt（`record.chart` 结构不变）。
- 不删后端 `/record/{id}/image` 端点与 `request_picture`（保留为非破坏性死路径，后续清理）；仅从前端渲染链路移除调用。
- 不动 `@antv/s2`（Table）与 `@antv/x6`。
- 不引入 Vega-Lite（已评估并放弃，见 §3）。

## 3. 引擎选型（已拍板）

**选定：ECharts + vue-echarts。** 理由：同步/确定性渲染、社区与文档最强、原生 30+ 图型、官方 SSR（`renderToSVGString`）可去独立 Node 进程、Vue 3 一等支持。

放弃项：`v-g2`（仅给 G2 套壳，治不了 G2 的渲染病）；`antvis/chart-visualization-skills`（prompt 参考集，非引擎，留作后续选图 prompt 参考）；Vega-Lite（`vue-vega` 失维、bundle 大、默认样式约束、LLM 产出更易错、SSR 需 vega+canvas——表达力最强但工程风险最高，本次不取）。

## 4. 架构（文件地图）

### 新增
- `frontend/src/views/chat/component/echarts/setup.ts` — 按需注册 echarts core（renderer/charts/components），tree-shaking 友好，导出供 `vue-echarts` 使用的 `VChart`。
- `frontend/src/views/chat/component/echarts/data.ts` — **唯一**数据加工源：移植并合并 `charts/utils.ts` 的 `formatNumber / toChartNumber / aggregateChartData / checkIsPercent / processMultiQuotaData / getAxesWithFilter`，新增 `normalizeChartData(...)` 一次性产出 `{ rows, isPercent }`。
- `frontend/src/views/chat/component/echarts/theme.ts` — 移植 `SQLBOT_PALETTE` 为 echarts `color`，集中数值/坐标轴/tooltip formatter（千分符 + 百分号）。
- `frontend/src/views/chat/component/echarts/builders/{bar,column,line,area,pie,scatter}.ts` — 每种图型一个 builder，输入归一化后的 `{axis, data, showLabel, isPercent}`，输出 echarts `option`。
- `frontend/src/views/chat/component/echarts/options.ts` — 调度器 `buildEChartsOption(config, data, showLabel)`：按 `config.type` 路由到 builder，再合并逃生口 `config.echarts`，返回最终 option。

### 重写
- `frontend/src/views/chat/component/ChartComponent.vue` — 改用 `<VChart :option autoresize :loading>`；删除 canvas 像素采样、ResizeObserver、`getChartInstance` 注册表、`loadFallbackImage`/`get_chart_image` 调用。**公共 props 保持不变**（见 §7）。

### 删除（迁完后）
- `frontend/src/views/chat/component/BaseG2Chart.ts`
- `frontend/src/views/chat/component/charts/{Bar,Column,Line,Pie,Area,Scatter}.ts`
- `frontend/src/views/chat/component/charts/utils.ts`（逻辑迁入 `echarts/data.ts`；保留 `formatNumber` 再导出口子以防他处引用）
- `frontend/src/views/chat/component/index.ts`（G2 实例注册表，由 `options.ts` 调度取代）

### 保留（不动）
- `frontend/src/views/chat/component/chartConfig.ts` — 归一化/推断逻辑（与库无关），继续复用。
- `frontend/src/views/chat/component/DisplayChartBlock.vue` — 仅微调：把传给 ChartComponent 的 props 来源对齐（无新增 prop，行为不变）。
- `frontend/src/views/chat/component/charts/Table.ts` — S2 表格，非 G2。
- `frontend/src/views/chat/component/charts/chartAggregation.test.mjs`、`chartConfig.test.mjs` — 改为从 `echarts/data.ts` import（断言不变）。
- 后端全部文件。

## 5. 契约（不变 + 逃生口）

`NormalizedChartConfig` 继续来自 `chartConfig.ts`。新增**可选**字段：

```ts
type ChartConfig = {
  type?: 'table'|'bar'|'column'|'line'|'pie'|'scatter'|'area' | string
  title?, summary?, insights?, alternatives?
  axis?: { x?, y?, series?, 'multi-quota'?: {name, value[]} }
  columns?: Array<...>
  echarts?: object            // 新增：逃生口，LLM 可传部分 echarts option 覆盖/扩展
}
```

- v1 不改后端 prompt，LLM 不会被要求产出 `echarts` 字段；但 builder 已支持合并它（便于后续无成本扩图型）。
- 合并规则：基础 option 先由确定性 builder 产出 → `JSON.parse(JSON.stringify(config.echarts || {}))` 消毒（剥离函数/不可序列化值）→ `lodash.merge(base, sanitized)` 覆盖。

## 6. 数据加工（单一源）

`echarts/data.ts` 统一：
- `getAxesWithFilter(axis)` — 拆 x/y/series/multi-quota（行为同现版）。
- `processMultiQuotaData(...)` — 多指标展开为 long 表（行为同现版）。
- `aggregateChartData(...)` — 同维度聚合（求和/率取均值）（行为同现版，迁移现有测试）。
- `checkIsPercent(...)` — 探测 `%` 并转数值（行为同现版）。
- `normalizeChartData(axis, rawRows)` — 组合：multi-quota 展开 → 聚合 → 百分比探测，一次性返回 `{ rows, isPercent }`。
- `formatNumber(value)` — 千分符（保持原签名与原样输出）。

新增单测 `echarts/data.test.mjs`（`node --experimental-strip-types`），覆盖聚合/百分比/multi-quota；并迁移 `chartAggregation.test.mjs` 断言不回归。

## 7. ChartComponent 重写（核心，公共契约不变）

**保留 props（与 `sq-view/index.vue`、`DisplayChartBlock.vue` 完全一致）**：
`id, type, data, columns, x, y, series, multiQuotaName, showLabel, recordId`。

内部从"axis 数组"组装归一化意图（沿用现 `axis` computed 思路）→ `buildEChartsOption` → `<VChart>`。

```vue
<script setup lang="ts">
import VChart from './echarts/setup'           // 已注册 core 的 vue-echarts
import { computed } from 'vue'
import { buildEChartsOption } from './echarts/options'
// ... props 同上 ...
const option = computed(() => buildEChartsOption(
  buildConfigFromProps(props), props.data, props.showLabel
))
</script>
<template>
  <div class="chart-container-wrap">
    <VChart class="chart-container" :option="option" :autoresize="true"
            :update-options="{ notMerge: true }" />
  </div>
</template>
```

要点：
- **渲染器用 SVG**（确定性、清晰、可无障碍、利于后续 SSR；数据量小场景无性能顾虑）。在 `setup.ts` 注册 `SVGRenderer`。
- `autoresize` 替代手写 ResizeObserver。
- 删除：`isChartCanvasBlank`、`loadFallbackImage`、`get_chart_image` 调用、`renderToken`/`renderFrame` 调度。失败改为 `el-empty` 提示（沿用 `DisplayChartBlock` 的 `chart_render_blocked` 文案路径）。
- `defineExpose({ renderChart, destroyChart, getExcelData })` 接口保留（`ChartBlock`/`sq-view` 通过 ref 调用），内部转发到 VChart 的 `resize()`/`dispose()`，或为兼容保留同名空/转发方法。

## 8. 各图型 builder 设计（echarts option 形状）

调度器据 `type` 路由；通用层（theme/color/grid/tooltip/legend/formatter）在 `options.ts` 统一注入，builder 只填 `series`+`xAxis/yAxis`。

- **column**（竖向柱）：`xAxis:{type:'category', data:xValues}`，`yAxis:{type:'value', axisLabel formatter}`，`series:[{type:'bar', data, label?}]`；有 series→多 series 分组；堆叠→`stack`。
- **bar**（横向柱）：交换轴，`xAxis:{type:'value'}`，`yAxis:{type:'category', data:xValues}`，`series type:'bar'`。
- **line / area**：`series:[{type:'line', smooth, areaStyle?(area 时开启)}]`；series→多条线。
- **pie**：`series:[{type:'pie', radius:['40%','70%'], data:[{name,value}]}]`，`name` 取 series 字段，`value` 取 y。
- **scatter**：`series:[{type:'scatter', data:[[x,y]], symbolSize}]`，x/y 数值字段。
- 百分比：`isPercent` 时值轴 formatter 追加 `%`，饼图 label 追加 `%`。
- label：`showLabel` 时 `series.label.show=true`（沿用现版策略：柱尾、线点、饼外）。

每个 builder 输出纯数据 option（无函数 formatter 依赖闭包外部可变量除外——formatter 内部调用 `formatNumber`，安全）。

## 9. 依赖变更

`frontend/package.json`：
- 新增 `echarts ^5.5`、`vue-echarts ^7`（Vue 3）。
- 移除 `@antv/g2 ^5.3.3`（确认仅被本引擎 7 文件引用，迁完即删）。
- 保留 `@antv/s2`、`@antv/x6`、`lodash-es`、`element-plus`。

## 10. 导出 / 静态图路径

- 运行时回退删除：`get_chart_image` 在前端无调用方。
- 导出/下载（若有）：用 echarts `getDataURL` 客户端出图，不再依赖 `:3000` 进程。
- 后端 `request_picture`/g2-ssr：保留代码不删（非破坏性），标记为待清理死路径。

## 11. 测试策略

- 现有：`node --experimental-strip-types *.test.mjs`（Node 原生剥类型，`.mjs` 可直接 import `.ts`）。
- 新增 `echarts/options.test.mjs`：对每个 type 给定 fixture data，断言 option 结构正确（series 类型、轴方向、堆叠、pie 的 name/value、scatter 的坐标对、逃生口合并、空/畸形配置→退化为 table 提示）。
- `echarts/data.test.mjs`：聚合/百分比/multi-quota（迁移现有断言）。
- 构建与类型：`vue-tsc -b` 通过；`vite build` 通过。
- 手测矩阵：每图型 × {有数据/无数据/单系列/多系列/百分比/multi-quota} × {首屏/resize/切换图型}。

## 12. 构建顺序（实现计划骨架）

1. 装依赖 + `echarts/setup.ts`（core 注册 + 导出 VChart）；本地起一个最小 `<VChart>` 冒烟。
2. `echarts/data.ts`（合并 utils）+ `data.test.mjs`；迁移旧测试 import 路径，保持绿。
3. `echarts/theme.ts` + `options.ts` 调度器骨架（含逃生口合并/消毒）。
4. builders：bar/column/line/area/pie/scatter 逐个实现 + `options.test.mjs` 覆盖。
5. 重写 `ChartComponent.vue`（VChart，删 hack），保持 props 与 `defineExpose` 契约。
6. `DisplayChartBlock.vue` 对齐微调；跑聊天路径 + dashboard `sq-view` 回归。
7. 删 G2 旧文件；从 `package.json` 移除 `@antv/g2`。
8. 全量回归：`vue-tsc`、`vite build`、测试矩阵、手测。

## 13. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `vue-echarts` 与 Vue 3.5 / vite 6 兼容 | vue-echarts v7 官方支持 Vue 3；先冒烟再铺开 |
| echarts bundle 变大 | `echarts/core` 按需注册（仅注册用到的 charts/components） |
| `sq-view` dashboard 回归 | ChartComponent 公共 props/expose 不变；手测覆盖 |
| 逃生口 option 破坏布局 | `JSON.parse(JSON.stringify())` 消毒 + 基础 option 先行、`merge` 覆盖 |
| `.mjs` 测试 import `.ts` | 已验证 Node `--experimental-strip-types` 可行 |
| 字段名含中文/特殊字符 | echarts 以列名做 dimension，原生支持；沿用现 `formatNumber` |

## 14. 出范围 / 延后

- 后端 prompt 让 LLM 主动产出 `echarts` 高级图配置（双轴/组合）。
- 删除 `request_picture` 与 g2-ssr 后端死代码（单独 PR）。
- echarts 服务端 SVG 预渲染缓存（如导出量大再做）。
