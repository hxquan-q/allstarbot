# 分析报告输出质量提升 — 设计文档（全链路 / 通用启发式）

- 日期：2026-06-23
- 范围：`/home/ubuntu/agent/SQLBot` 的「数据分析报告」输出（`generate_analysis` + `data_profile` + markdown/图表渲染管线）
- 路线：Approach 1 — Prompt-anchored · profile-fueled · render-polished
- 领域定位：**通用 BI**，供应链为验证场景（不内置领域逻辑）
- 关联：续接 `2026-06-23-allstarbot-foundation-rebuild-design.md`（Phase 1/2 已建立「模块化 prompt + 增强 profile」模式，本轮把同一模式应用到 analysis 通道）

## 1. 背景与根因

用户对一次供应链缺口分析报告给出了系统性批评，覆盖 6 大类约 40 个问题。调研后定位到三层根因：

| 层 | 代码位置 | 驱动的批评点 |
|---|---|---|
| **分析 prompt** | `templates/template.yaml:777-850`（固定 7 段报告）+ `apps/chat/task/multi_dimension.py` | 口径混淆、分层维度混用、行动建议不落地、不点名阈值、术语不通俗、总览结论缺三要素（约 60%） |
| **数据画像** | `apps/chat/data_profile.py`（喂给 prompt 与图表） | 英文字段无中文别名（`demand_total` 等）、单位缺失（万/pcs 混用）、阈值临近物料未统计、分类维度只有编码无名称（约 25%） |
| **前端渲染** | `frontend/src/utils/markdown.ts` + `views/chat/component/MdComponent.vue` + `views/chat/chat-block/ChartBlock.vue` | 表头截断、图表横轴无单位、配色分层弱、明细表格重复渲染（约 15%，polish） |

**关键事实**：
1. analysis prompt 是最大杠杆，且**尚未被 Phase 1/2 模块化**（SQL prompt 已进 `prompts/sql_prompt.py`，analysis 仍是 template.yaml 原文）。
2. 分析报告本身是**纯 markdown**，经唯一共享渲染器 `markdown.ts` → `MdComponent.vue`（表格外包 `.md-table-wrap`，90ms 节流重渲染）。
3. 批评中"带坐标轴的图表"（横轴物料编码）来自**主图表**（`generate_chart` → `ChartBlock`），而非分析 markdown；该图表也由 `data_profile` 经 `enrich_chart_config` 喂养 → **增强 profile 可同时修好报告与主图表**。

## 2. 目标 / 非目标

### 目标
- 消除单位与口径歧义：报告顶部统一口径说明，每个数字带单位，总额统一主单位并标注换算。
- 消除英文字段阅读门槛：关键字段给中文名（alias），prompt 以中文名为主标签。
- 让 TOP 缺料/问题被点名、量化、置顶突出。
- 修好分层分析的维度混淆：每层单一维度，禁止同段混用仓库+物料。
- 行动建议落到"对谁/做什么/解决什么/兜底影响"。
- 主图表显示物料名称而非编码，轴带单位，配色区分度提升。
- 表头不截断、明细表不重复。

### 非目标
- 结构化 JSON 报告 + 前端专用卡片组件（Approach 3，本轮超范围）。
- `multi_dimension` 重写（仅顺便对齐新规则）。
- live Postgres + pgvector + LLM 硬接线（Phase 2 遗留）。
- 前端视觉重设计（遵循"只打磨不重设计"既有偏好）。
- 自动单位换算（如 万↔pcs，安全起见只标注不换算）。

## 3. 架构与数据流（不动主管线接线）

三条增强挂载在现有数据流上，不重写 `run_task`：

```
SQL执行结果 → build_data_profile()            ←【Phase A 注入新字段】
                 ↓ data_profile JSON
        ┌────────┴────────────┐
        ↓                     ↓
 analysis_user_question()   enrich_chart_config()   ←【Phase A 的 code→name/单位 也修好主图表】
 【Phase B 重写规则】              ↓
        ↓                     ChartBlock 渲染         ←【Phase C 轴单位/配色】
   MdComponent.vue                                       ←【Phase C 表头/卡片/去重】
```

**设计原则**：
- Phase A 新字段全部 **additive**，旧消费方零改动，向后兼容。
- profile 同时喂"分析报告"与"主图表"，code→name 配对与单位标注**一次修复两处**。
- 核心启发式零外部依赖（numpy/decimal/字段名），沙箱内全单测。
- prompt builder 确定性、可快照测试；保留 `template.yaml` 加载路径向后兼容。

## 4. Phase A — `data_profile` 加燃料（`apps/chat/data_profile.py`）

四个纯启发式增强，挂在现有 `_field_profile` / `build_data_profile` / `_enrich_top_values_with_metrics` 上。

### 4.1 单位与量级（标注，不换算）
- 新增 `fields[].unit`（中文单位标签）与 `fields[].scale_hint`（量级提示）。
- 推断来源（优先级从高到低）：
  1. 同行 unit 列：若存在名为 `*_unit` / `单位` 的列且值稳定，直接取其值。
  2. 字段名关键词：`金额/收入/利润/成本/单价/price/cost/amount` → 元（量级大时提示"万元"）；`数量/pcs/件/个/台/kg/吨/qty/quantity` → 计数/重量；`率/占比/percent/rate/ratio` → %。
  3. 值域：全落在 [0,1] 或 [0,100] 且名含率 → 视为百分比。
- **安全红线：只标注、不换算**。`scale_hint` 仅作文字提示（如"总量级≈821 万"），不改变原值。
- 允许术语/`custom_prompt` 覆盖。

### 4.2 中文字段别名
- 新增 `fields[].alias`。
- 来源：
  1. 解析已注入的 `<terminologies>`（术语→描述）建字段名映射。
  2. snake_case 分词 + 翻译表（demand→需求、total→总量、available→可用、gap→缺口、rate→率、percent→百分比、material→物料、code→编码、name→名称、qty→数量、amount→金额…），未知 token 保留原文，再拼回。
- prompt 以 alias 为主标签，原字段名在口径块出现一次。

### 4.3 指标分布与阈值临近计数
- 新增 `fields[].distribution`：
  - `bands`：数据驱动四分位分桶，每桶 `{label, min, max, count}`。**不硬编码 8%/15%**。
  - `extreme_count`：距峰值（max）20% 以内的行数（"极值/高风险"计数）。
  - 识别为率类指标时（率类识别口径见 §4.1：名含率/占比 或 值域落 [0,1]/[0,100]），额外给 `near_ceiling_count`（接近上限的计数；上限取观测 max 或术语注入的阈值）。
- 解决"12.09% 临近阈值但没统计""低/中缺口各占多少未细分"。

### 4.4 分类维度 code→name 配对
- 为 category_dimension 的 `top_values` 增加 `label`。
- 启发式：在该分类维度列之外，找一个**非数值、非 ID** 的伴生列，其值与分类维度值呈 1:1 或 many:1，则用它做显示名。
- 保守条件防误配：名称列须含 CJK，或长度明显大于编码列，或字段名含 `name/名称/描述`。
- 结果：`MECH.000085` → `"MECH.000085 硅胶密封圈(VMQ 70A)"`。该 label 同时被 `enrich_chart_config` 与 chart prompt 用于主图轴标签。

### 4.5 Phase A 测试
扩 `tests/test_data_profile.py`，沿用现有无依赖 pytest 风格，每启发式至少一例：
- 单位识别（金额→元、数量→计数、率→%）+ unit 列覆盖。
- 别名翻译（`demand_total`→需求总量、未知 token 保留）。
- 分布分桶计数 + extreme_count + 率类 near_ceiling_count。
- code→name 正确配对 + 伴生列误配被拒绝（保守条件）。
- 向后兼容：旧字段不变，新字段缺失时不报错。

## 5. Phase B — analysis prompt 模块化与规则重写（`apps/chat/prompts/analysis_prompt.py`）

- 仿 `sql_prompt.py`：`AnalysisPromptInput` dataclass + `build_analysis_messages(inp) -> [system, user]`，规则每条只说一次（去重）。
- `analysis_sys_question/analysis_user_question`（`chat_model.py:302-308`）改为委托新 builder；保留 `template.yaml` 加载路径向后兼容。
- 消费 Phase A 新字段（alias/unit/distribution/label）。

### 新增/强化规则（每条对应批评点）
1. **口径单位置顶**：报告开头强制「数据口径」块 = 统计周期 + 单位体系 + 关键字段中文别名表（取自 alias/unit）。无前置摘要堆砌。
2. **单位强制标注**：每个数字带单位；总额统一一种主单位，跨段出现时标注换算关系。
3. **分层维度单一**：每个 `###` 三级标题只展开一个维度；**禁止同段混用仓库+物料两个维度**；需关联时单设「交叉归因」节，把头部维度的对应物料清单同步展示。
4. **TOP 点名+量化**：重点问题定位必须 = 对象名（取 `top_values.label`）+ 真实数字（取 `metric_values`）+ 阈值/等级判断；**TOP1 单独置顶**用约定结构（见 §6.2）。
5. **行动建议三要素**：每条 = 对象 + 具体抓手（采购加急/库存调拨/替代料/安全库存调整参考…）+ 解决什么 + 兜底影响（影响哪些产品线/预估停线天数或损失）。
6. **术语通俗化**：术语（`supply_gap_total`、`gap_rate_percent`、`BOM关键性` 等）首次出现括注通俗解释。
7. **数据时效脚注**：报告末尾标注统计周期、是否含预测订单、是否剔除呆滞库存；从数据/profile 推断，不确定则标"未说明"。
8. **不重复**：明细表只出现一次；不得反复复述同一组基础数字。

### Phase B 测试
- 组装后 prompt 快照测试（确定性，仿 `tests/test_sql_prompts.py`）：给定 `AnalysisPromptInput` → 断言 system/user 含期望规则块与新字段槽位。
- **真实报告迭代**：用户贴真实模型输出，按批评点逐条对账调优规则。

## 6. Phase C — 前端渲染打磨（集中式 markdown 管线 + 图表块）

遵循"polish 非 redesign"：优先纯 CSS + prompt 约定，不改 JS 结构。

### 6.1 表头不截断
- `frontend/src/style.less`：`.md-table-wrap th` 加 `white-space: normal`/`word-break: break-word`/`min-width`，避免"展望供…"被截断。

### 6.2 TOP 置顶高亮卡片
- **唯一约定**：prompt 在「重点问题定位」节首部输出一个引用块 callout，首行以 `> 🔴 TOP1` 开头，格式固定为 `> 🔴 TOP1：{对象名} 缺口 {数字}{单位}（{阈值判断}）`。
- `MdComponent.vue` 的 `.markdown-body` 用 CSS 把"以 🔴 TOP1 开头的 `blockquote`"渲染成高亮 callout（左边框 + 底色 + 加粗）。**纯 CSS 选择器 + prompt 约定，不改 markdown.ts 解析逻辑**。
- 选 blockquote 而非自定义 HTML：markdown-it 原生产出 `<blockquote>`，CSS 可稳定命中；不需要新插件。

### 6.3 主图表轴单位与配色
- `ChartBlock.vue`（`views/chat/chat-block/`）：轴 formatter 追加 §4.1 推断的 unit 后缀（unit 经 `enrich_chart_config` 富化已可用）。
- 高/中/低用区分度更高的色阶（避免蓝绿堆叠）；TOP1 单独强调色。
- chart prompt 倾向用 §4.4 的 code→name `label` 列做轴（修"横轴全是物料编码"）。

### 6.4 明细表去重
- 先定位根因：prompt 重复输出 vs 流式 90ms 节流导致的视觉重影 vs markdown 解析。
- 从源头修（Phase B 规则 8 + 必要时 markdown.ts 调整），不引入额外 JS 去重。

### 6.5 Phase C 测试
- markdown：渲染样例报告 → 断言 th 样式类、callout 类存在。
- 图表：轴 formatter 单测 → 断言带单位后缀；配色映射单测。
- 视觉确认在用户机器（沙箱无 dev server/live 数据）。

## 7. 测试与验证总策略

- **Phase A**：沙箱内全单测（numpy/decimal，无依赖）。
- **Phase B**：组装 prompt 快照测试 + 真实报告迭代（用户可贴报告）。
- **Phase C**：组件/单测 + 用户机器视觉确认。
- **回归**：现有 230 测试保持全绿；profile 改动 additive、向后兼容；既有 `test_data_profile.py` 行为不变。

运行：`/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/ -q`（Phase 1/2 已用此 env）。

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 单位/别名误判 | 只标注不换算；术语/custom_prompt 可覆盖；保守关键词表 |
| code→name 伴生列误配 | 名称列须含 CJK 或明显长于编码或字段名含 name/名称；否则不配对 |
| prompt 规则过严 → 输出僵硬 | 真实报告迭代调优；规则分级（critical/normal） |
| 图表改动需视觉验证 | 标记为用户机器验证项；不盲改 |
| distribution 四分位对偏态数据不直观 | 同时给 extreme_count 与 near_ceiling_count；术语可注入阈值 |

## 9. 实现顺序（供 writing-plans 拆解）

1. Phase A（profile 增强 + 全单测）—— 独立、零依赖、可先行。
2. Phase B（prompt 模块化 + 规则 + 快照测试 + 真实报告迭代）—— 依赖 Phase A 字段。
3. Phase C（前端 CSS + 图表轴/配色 + 去重）—— 依赖 Phase A 字段透出到 chart config；可与 Phase B 并行后半段。

> 每阶段全绿再推进；profile 与 prompt 模块化先做（后端、可测），前端打磨随后。
