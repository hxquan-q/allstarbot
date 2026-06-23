"""Modular analysis-report prompt builder (mirrors sql_prompt.py).

Produces a layered, decision-ready business analysis report in Markdown.
Rules are stated exactly once (dedup invariant) and consume the enriched
data_profile (alias / unit / scale_hint / distribution / top_values.label /
metric_values) so the model has real numbers and Chinese labels to cite
instead of inventing them.
"""
from __future__ import annotations

from dataclasses import dataclass


_SYSTEM_PREAMBLE = (
    "你是智能问数小助手：\"{sqlbot_name}\"。根据给定的查询数据与数据画像，输出一份分层、可决策的业务分析报告（Markdown）。\n"
    "信息块：<terminologies> 为术语（同义词与描述/公式）；<fields> 为字段或别名；<data> 为 JSON 数据；"
    "<data-profile> 为系统预计算的数据画像（字段角色、维度/指标、alias 中文名、unit 单位、"
    "scale_hint 量级换算、distribution 分桶与极值计数、top_values.label 名称与 metric_values 真实数字）。\n"
    "使用语言：{lang}（含思考过程）。"
)

_RULES = [
    ("critical", "## 🎯 总览结论：1-3 句，必须同时含①核心判断(好/差/异常)②关键数字(带单位)③业务影响。禁止只罗列数字。"),
    ("critical", "## 📌 数据口径（报告最前）：先给出统一口径说明——统计周期、单位体系(统一一种主单位并标注万/亿换算，取 scale_hint)、"
                 "关键字段中文别名(取 alias；若某字段 alias 为空则直接用其字段名，原英文名仅在此出现一次)。"),
    ("critical", "## 📊 关键指标：用表格 | 指标(中文名) | 数值(带单位) | 趋势(📈/📉/➡️) | 业务含义 |。"
                 "存在易混口径(如 计划/要货/出库、需求/可用/供应)时，必须用一句话讲清逻辑关系与口径差异。"),
    ("critical", "## 🔍 分层发现：按 2-4 维度展开，每个维度用一个 ### 三级标题。"
                 "禁止在同一段内混用两个维度(如 仓库 与 物料)；每个 ### 只展开一个维度，每条=具体数字→业务含义。"),
    ("critical", "## ⚠️ 重点问题定位：必须点名 TOP 3-5 个具体对象(取 top_values.label 的名称)，"
                 "每项=对象名+真实数字(取 metric_values，带单位)+风险等级+量化阈值判断(如 偏差>20% 属严重)。"
                 "首部用一个以 `> 🔴 TOP1` 开头的引用块单独置顶最大问题，格式固定："
                 "`> 🔴 TOP1：{对象} {指标} {数字}{单位}（{阈值判断}）`。严禁只说\"有N个异常\"不点名。"),
    ("normal", "## 📈 趋势与变化：量化变化幅度(增长 X%)，指出拐点位置。"),
    ("critical", "## 🛠️ 行动建议：按 🔴高/🟡中/🟢低 三层，每条必须三要素——对象 + 具体抓手(采购加急/库存调拨/替代料/安全库存调整参考值) + "
                 "解决什么 + 兜底影响(不处理会影响哪些产品线、预估停线天数或损失)。禁止泛泛\"建立跟踪清单\"。"),
    ("normal", "## 📊 图表建议：每种图表说明解决什么具体业务疑问(非泛泛\"看趋势\")。"),
    ("normal", "术语(supply_gap_total、gap_rate_percent、BOM关键性 等)首次出现必须括注通俗解释。"),
    ("normal", "数据时效脚注：报告末尾标注统计周期、是否含预测订单、是否剔除呆滞库存；无法确定则标\"未说明\"。"),
    ("normal", "明细数据表全报告只出现一次；不要反复复述同一组基础数字。"),
    ("normal", "某维度在数据中不存在时不要编造，说明\"当前数据不足以分析该维度\"。"),
]


def _format_rules() -> str:
    lines = ["你必须遵守以下规则："]
    for priority, text in _RULES:
        lines.append(f'- [{"critical" if priority == "critical" else "normal"}] {text}')
    return "\n".join(lines)


@dataclass
class AnalysisPromptInput:
    lang: str = "简体中文"
    sqlbot_name: str = "小爱同学"
    terminologies: str = ""
    custom_prompt: str = ""
    fields: str = "[]"
    data: str = "[]"
    data_profile: str = "{}"


def build_analysis_messages(inp: AnalysisPromptInput) -> list[dict[str, str]]:
    """Build deterministic ``[system, user]`` messages for analysis-report generation."""
    system = "\n\n".join([
        _SYSTEM_PREAMBLE.format(lang=inp.lang, sqlbot_name=inp.sqlbot_name),
        _format_rules(),
        f"<terminologies>\n{inp.terminologies}\n</terminologies>",
        inp.custom_prompt,
    ])
    user = "\n\n".join([
        f"<fields>\n{inp.fields}\n</fields>",
        f"<data>\n{inp.data}\n</data>",
        f"<data-profile>\n{inp.data_profile}\n</data-profile>",
    ])
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
