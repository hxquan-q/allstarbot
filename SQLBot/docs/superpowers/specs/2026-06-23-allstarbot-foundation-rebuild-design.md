# allstarbot 底层重建 — 设计文档（Phase 1）

- 日期：2026-06-23
- 范围：`/home/ubuntu/agent/SQLBot`（allstarbot，基于 SQLBot 二次开发）
- 决策：**原地现代化**（保留代码库与全部产品特性，把底层用 `~/dev/asagent` 的模式重写）
- 本轮：**Phase 1 做透后汇报**，质量优先

## 1. 背景与现状（调研结论）

### 1.1 关键发现：`~/dev/asagent` 是同一作者的"SQLBot v2"
asagent 用 LangGraph `create_react_agent` + 工具包（`describe_schema`/`query_database`/`visualize`/`render`）+ 类型化 content blocks + 渐进式披露 + 线程化流式运行时（带看门狗）+ 单一 OpenAI-compat LLM 工厂 + AST-first `db_safety`，整体明显先进于当前 `LLMService` 过程式管线。**但 asagent 主动砍掉了**：多方言（仅 PG）、表级 embedding 检索、DDL+样本+few-shot 注入、行级权限、查询缓存——这些恰好是 SQLBot 的看家本领（≈ Vanna 的 RAG 思路）。

**结论**：不照搬 asagent（会丢产品广度），而是把 asagent 的架构模式**移植进 SQLBot**，同时保留并强化 SQLBot 独有的 RAG 检索能力。

### 1.2 当前底层病灶（带 file:line）
- `chat/task/llm.py` 2312 行上帝对象，`run_task` 单生成器 425 行，整条链零测试覆盖
- 检索弱：表/datasource embedding 存 JSON 文本、numpy 算余弦（项目已依赖 pgvector 仅用于 terminology/training）；每表每请求 `SELECT ... LIMIT 3` 取样本不缓存；无列级裁剪（`datasource/embedding/table_embedding.py`、`crud/datasource.py:490`）
- Prompt 臃肿自相矛盾：`templates/template.yaml` 1038 行，"标识符保留"规则重复 3+ 次，图表选择+生产规则全塞进 SQL prompt
- 假流式：`ThreadPoolExecutor(200)` + 轮询 `chunk_list`（`llm.py:65,1436`）
- 只读校验重复两份：`db.check_sql_read`（`db.py:777`）vs `sql_checker.get_read_only_violation`（`sql_checker.py:308`）
- 无真正 agent 循环；靠一堆 JSON-repair fallback 兜底
- 前端：贪婪 SSE 正则 `data:.*}\n\n`（`ChartAnswer.vue:185`）；markdown 每 90ms 全量重解析；图表渲染失败静默空白；block 分发靠 `v-if` 看 FK id

### 1.3 保留的强项
SQL 安全层（sqlglot 表校验 + 只读 + 修复重试）、`data_profile` 启发式、图表"LLM 出轴映射、前端出 G2"架构。

## 2. 总体架构（目标态）

分层、依赖注入、可独立单测：

```
chat/agent/            LangGraph 图 + 工具（describe_schema/query_database/...）← Phase 2 接线
chat/prompts/          模块化、去重、版本化 prompt builder（替代 1038 行 yaml 大杂烩）
datasource/retrieval/  RAG 检索核心（纯逻辑）+ pgvector 适配器
   ├ packer.py         三通道 token-budget 上下文打包（DDL/schema + docs/术语 + question→SQL 范例）
   ├ ranker.py         候选打分（向量相似度 + 阈值 + top-k），候选可注入
   ├ fk_expander.py    FK-sphere / 最短路径 join 桥发现（QueryWeaver 思路，轻量）
   └ pgvector_store.py pgvector 适配器（懒导入 pgvector，镜像 terminology 的 <=> 模式）
db/safety.py           统一 AST-first 只读校验（asagent db_safety + sql_checker + db.check_sql_read 取并集）
```

设计原则：
- **核心逻辑零外部依赖**：packer/ranker/fk_expander/safety 只依赖 numpy/sqlglot，向量和候选以参数注入 → 无需 live Postgres+pgvector+LLM 即可深度单测。
- **薄适配器**：pgvector SQL、embedding 模型、LLM 都在适配器层，懒导入，可被 fake 替换。
- **向后兼容**：`sql_checker.py`、`db.check_sql_read`、`table_embedding.py` 改为对新模块的薄委托，调用方零改动。

## 3. Phase 1 范围（本轮做透）

> 用户期望 Phase 1 含"检索层 + 安全层去重 + agent 化核心 + 流式修复"。其中**流式修复依赖 agent 路径接线，属 Phase 2**。Phase 1 把前三个做成**全单测覆盖的新地基模块**，并对安全层与检索层完成向后兼容迁移；agent 核心做成**经单测验证的图（feature-flag，默认关闭）**，全量替换 `run_task` 留给 Phase 2。

### 3A. 统一 SQL 安全层 `apps/db/safety.py`
- 单一 AST-first 只读校验器：注释/字面量剥离 → 首关键字白名单（SELECT/WITH）→ 写操作 AST 节点拒绝（Insert/Update/Delete/Create/Drop/Alter/Merge/Copy/Truncate）→ 危险函数/模式黑名单（`INTO OUTFILE`、`LOAD_FILE`、`COPY ... TO PROGRAM`、`XP_CMDSHELL`、`SP_EXECUTESQL` 等）→ 多语句拒绝。
- 多方言：通过 `sqlglot` dialect 映射（复用现有 `_SQLGLOT_DIALECTS`）。
- 兼容：`sql_checker.get_read_only_violation`/`ensure_read_only_sql` 与 `db.check_sql_read` 改为委托；保留对外签名与行为（含 metadata 查询放行等既有细节）。
- 测试：方言矩阵（pg/mysql/oracle/ck/sqlserver）、字面量内关键字（`SELECT 'DELETE'`）、注释剥离、多语句、危险函数、空 SQL。

### 3B. 检索层 RAG `apps/datasource/retrieval/`
- `packer.py` `ContextPacker`：三通道（schema/DDL、docs/术语、question→SQL 范例）+ 样本数据，按通道优先级与**每通道 token 预算**贪心打包；输出结构化 `BuildContext`。端口 Vanna `base.py:535-684` 的 token-budget 思路。
- `ranker.py` `CandidateRanker`：对注入的候选（表/列/datasource，各带 embedding 与元数据）算余弦、阈值过滤、top-k；复用 `embedding/utils.batch_cosine_similarity`。
- `fk_expander.py` `FkExpander`：给定命中表集合 + 关系图（`table_relation` JSON 抽象），做 1 跳 FK 邻域扩展 + 命中表间最短路径补桥（≤N 跳），返回需追加的 join 桥表。
- `pgvector_store.py` `PgvectorSchemaStore`：懒导入 `pgvector.sqlalchemy`；为表/列/datasource 提供 `<=>` 相似查询 SQL（镜像 `terminology.py:782` 模式），支持阈值 + top-k + datasource/oid 过滤。
- Alembic 迁移：为 `core_table`/`core_datasource` 增加 pgvector 列（dim 取自 embedding 模型），附回填说明（从现有 JSON embedding 反序列化写入）。迁移**编写并 review**，因本地无 live PG，适配器用 fake store 单测。
- 样本数据缓存钩子：以 `table+schema` 为 key 复用 `chat/cache/query_cache` 基础设施。
- 测试：packer 预算/优先级/截断、ranker 阈值/top-k/空候选、fk_expander 桥发现/无解、pgvector SQL 形态快照。

### 3C. Prompt 模块化 `apps/chat/prompts/`
- 拆分 `template.yaml`：SQL-gen / chart / datasource-select / safety 各成独立、去重、版本化 builder（Python）。删除重复 3+ 次的"标识符保留"规则。
- 保留 `template.yaml` 既有加载路径（向后兼容），新代码走 builder。
- 启发式生产规则参考 QueryWeaver AnalysisAgent 的 P1–P13（输出粒度、禁造公式、COUNT 语义、NULL 处理、最小 join）。
- 测试：给定输入的组装 prompt 快照测试（确定性）。

### 3D. Agent 核心（受限、feature-flag）`apps/chat/agent/`
- LangGraph 图：SQL 生成 → 执行 → 观察 → 修复（healer 多轮、方言感知错误提示，参考 QueryWeaver HealerAgent）循环。
- 工具：`describe_schema`（调 3B 检索）、`query_database`（调 3A 安全层 + 现有 `exec_sql`）。
- 经 `FakeListChatModel`/假工具单测：图转移、工具分发、修复循环终止条件。
- **默认关闭**（config flag），不接线 `run_task`；接线 + 真异步流式 = Phase 2。

## 4. 不在本轮范围（Phase 2+）
- 用 agent 图全量替换 `run_task`（含多方言执行、行级权限、动态子 SQL、data_training 注入、多维度分析）
- 真异步原生流式（替换 200 线程池 + 轮询）
- 前端 SSE 增量解析器、图表渲染失败可见态、block 显式 kind 字段、markdown 增量解析、ChartBlock 拆分
- 结构化输出（function-calling/JSON mode）替换 JSON-repair fallback

## 5. 测试策略（"深度测试确定质量"）
- **TDD**：每个新模块先写失败测试（红）→ 实现（绿）→ 重构。
- 纯逻辑模块用 fake/注入，无需 live DB/LLM。
- 既有测试（`tests/test_sql_checker.py` 等 16 项）保持全绿——迁移以委托实现，行为不变。
- 覆盖目标：新模块行/分支覆盖核心路径；安全层与检索层为重点。
- 运行：`/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/ -q`（该 env 已具备 langchain 0.3.30 / langgraph / sqlglot / pytest 9.1.0）。

## 6. 风险与缓解
- **行为漂移**：安全层/检索层迁移用委托 + 既有测试护栏；新逻辑独立加测试。
- **pgvector 缺失**：核心逻辑零 pgvector 依赖；适配器懒导入 + fake 单测；迁移文件单独 review。

## 7. Phase 1 完成情况（2026-06-23）

全部 4 个地基模块以 TDD 完成，**200 passed / 3 skipped**，新增 111 个单测全绿，零回归（唯一失败 `test_summary_json_escape_safety` 为 template.yaml 既有问题，与本次无关，经 stash 验证）。

| 子项 | 产物 | 测试 |
|---|---|---|
| 3A 安全层 | `apps/db/safety.py`（统一 AST-first 只读校验）；`sql_checker.py` 与 `db.check_sql_read`/`get_sqlglot_dialect` 改委托 | test_sql_safety 65 + 既有 test_sql_checker 16 |
| 3B 检索层 | `apps/datasource/retrieval/`（ranker/fk_expander/packer/pgvector_store）+ alembic `070_schema_embedding_vector.py` | test_retrieval 28 |
| 3C Prompt | `apps/chat/prompts/sql_prompt.py`（去重 + 生产规则 + 确定性 builder） | test_sql_prompts 8 |
| 3D Agent | `apps/chat/agent/sql_agent.py`（LangGraph generate→execute→repair，注入式，默认未接线） | test_sql_agent 10 |

设计原则落实：核心逻辑零外部依赖（pgvector/LLM/live DB 全部注入或懒导入），全部可纯单测；向后兼容（调用方零改动）。

## 8. Phase 2 计划（下一轮）
1. **检索层接线**：用 `PgvectorSchemaStore`+`CandidateRanker`+`FkExpander`+`ContextPacker` 替换 `datasource/embedding/table_embedding.py` 与 `crud/datasource.py:get_table_schema` 的 numpy-JSON 路径；运行 070 迁移；样本数据接入 `query_cache`。
2. **Agent 接线**：把 `SqlAgent` 图接入主流程替换 `run_task` 的 SQL 生成/执行/修复阶段（feature flag 渐进切换），用 `build_sql_messages` + 3B 检索喂 `describe_schema` 工具。
3. **真异步流式**：替换 `ThreadPoolExecutor(200)`+轮询为 agent 原生 async stream；移除假 SSE。
4. **结构化输出**：对支持 function-calling/JSON mode 的模型，用结构化输出替换 JSON-repair fallback。
5. **前端**（对应"优化渲染"）：SSE 增量解析器、图表渲染失败可见态、block 显式 kind、markdown 增量解析、拆分 ChartBlock。
6. 拆分 `llm.py` 2312 行上帝对象为分阶段模块（随 1–4 推进）。

> 接线类工作需 live Postgres+pgvector+LLM 验证，建议在能跑通真实管线时进行。

## 9. Phase 2 完成情况（2026-06-23）

按"可验证优先"原则推进：把接线所需的**编排/适配/解析 glue** 做成全测过的模块，把需要 live Postgres+pgvector+LLM 才能端到端验证的"硬接线"留到能跑真实管线时做。全量 **230 passed / 3 skipped**，零回归（唯一失败仍为既有 template.yaml 问题）。

| 子项 | 产物 | 测试 |
|---|---|---|
| P2-1 检索编排 | `retrieval/service.py` `RetrievalService`（embed→rank→FK 扩展→token 预算打包，注入式）；`build_retrieval_service_from_settings` 工厂 | test_retrieval_service 9 |
| P2-2 Agent 适配器 | `chat/agent/adapters.py`（`make_llm_generate`/`make_llm_repair` 包装 prompt+LLM+JSON 解析；`make_executor` 包装 exec_sql）；含端到端组装测试 | test_agent_adapters 11 |
| P2-3 开关与配置 | `config.py` 加 `AGENT_SQL_ENABLED`（默认关）+ 检索 token 预算/阈值/sphere/hops；注册布尔校验 | — |
| P2-4 前端 SSE | `frontend/src/utils/sse.ts` `extractSSEFrames`（修贪婪正则，返回原始 data 串保留各调用方 JSON/JSONBig）；接入 3 个 answer 组件 | node 15 + vue-tsc 全量通过(exit 0) |

### 关键设计点
- **RetrievalService** 让"低相关但为 join 桥/邻居"的表被纳入（FK sphere + 最短路径补桥），这是旧 numpy 路径做不到的。
- **Agent 适配器**使 `SqlAgent(make_llm_generate(llm), make_llm_repair(llm), make_executor(exec_sql, ds))` 即为生产可用，端到端单测验证 generate→execute→repair。
- **SSE 修复**用 `\n\n` 帧分隔的正确解析取代贪婪正则 `data:.*}\n\n/g`（旧逻辑会把两帧 `data:{a}\n\ndata:{b}\n\n` 吞成一个、丢失第二帧）；返回原始串不破坏 ChartAnswer 的 JSONBig 大整数安全。

### 仍需 live 栈验证（Phase 2 剩余硬接线）
以下改动触及主流程/真实数据，沙箱无 live Postgres+pgvector+LLM，盲改违背"深度测试"，留到能跑真实管线时做：
- **检索层接线**：`get_table_schema`/`table_embedding.py` 改走 `RetrievalService`+`PgvectorSchemaStore`，执行 070 迁移回填 `embedding_vector`。
- **Agent 接线**：在 `run_task` 顶部加 `if settings.AGENT_SQL_ENABLED` 分支委托 `SqlAgent`（默认关，老路径不变），渐进切换。
- **真异步流式**：替换 200 线程池+轮询为 agent 原生 async stream。
- **前端其余渲染项**：图表渲染失败可见态、block 显式 kind、markdown 增量解析、拆分 ChartBlock（需浏览器/dev server 验证）。


- **范围蔓延**：按 3A→3B→3C→3D 顺序，每个子阶段全绿再推进；agent 接线严格留到 Phase 2。
