"""多维度分析管线

在主查询完成后，自动基于 data_profile 生成 2-3 个补充分析维度。
每个维度包含一个推荐图表类型、分析要点和洞察。
"""
import json
import traceback
from typing import Any, List, Optional

import orjson
from langchain_core.messages import HumanMessage

from apps.chat.data_profile import build_data_profile
from apps.chat.models.chat_model import SystemPromptMessage
from apps.template.template import get_template
from common.utils.utils import SQLBotLogUtil, extract_nested_json


class MultiDimensionAnalyzer:
    """基于 data_profile 自动推荐并生成多维度分析"""

    # 支持的分析维度类型
    DIMENSION_TYPES = {
        "time_trend": {
            "title": "时间趋势分析",
            "chart_type": "line",
            "description_template": "观察 {metric} 随 {time_dim} 的变化规律、趋势和周期性",
        },
        "category_comparison": {
            "title": "分类对比分析",
            "chart_type": "column",
            "description_template": "对比不同 {category} 之间 {metric} 的差异和分布",
        },
        "proportion": {
            "title": "占比分布分析",
            "chart_type": "pie",
            "description_template": "分析各 {category} 在 {metric} 中的占比结构",
        },
        "ranking": {
            "title": "排名分析",
            "chart_type": "bar",
            "description_template": "按 {metric} 排名展示 Top/Bottom {category}",
        },
        "correlation": {
            "title": "相关性分析",
            "chart_type": "scatter",
            "description_template": "探索 {metric1} 与 {metric2} 之间的相关关系",
        },
    }

    def suggest_dimensions(self, data_profile: dict, question: str) -> list[dict]:
        """基于 data_profile 自动推荐分析维度

        Args:
            data_profile: 数据画像
            question: 原始用户问题

        Returns:
            推荐的分析维度列表（最多3个）
        """
        dimensions = []
        metrics = data_profile.get("metrics", [])
        time_dimensions = data_profile.get("time_dimensions", [])
        category_dimensions = data_profile.get("category_dimensions", [])

        if not metrics:
            return []

        primary_metric = metrics[0]

        # 维度1：时间趋势（如果有时间字段）
        if time_dimensions:
            time_dim = time_dimensions[0]
            dim_type = self.DIMENSION_TYPES["time_trend"]
            dimensions.append({
                "type": "time_trend",
                "title": dim_type["title"],
                "chart_type": dim_type["chart_type"],
                "description": dim_type["description_template"].format(
                    metric=primary_metric, time_dim=time_dim
                ),
                "fields": {"metric": primary_metric, "dimension": time_dim},
            })

        # 维度2：分类对比（如果有分类字段）
        if category_dimensions:
            cat_dim = category_dimensions[0]
            dim_type = self.DIMENSION_TYPES["category_comparison"]
            dimensions.append({
                "type": "category_comparison",
                "title": dim_type["title"],
                "chart_type": dim_type["chart_type"],
                "description": dim_type["description_template"].format(
                    category=cat_dim, metric=primary_metric
                ),
                "fields": {"metric": primary_metric, "dimension": cat_dim},
            })

        # 维度3：占比分布（如果分类字段基数较低）
        if category_dimensions:
            cat_dim = category_dimensions[0]
            fields_profiles = data_profile.get("fields", [])
            cat_profile = next(
                (f for f in fields_profiles if f.get("name") == cat_dim), {}
            )
            unique_count = cat_profile.get("unique_count", 999)
            if unique_count <= 15:
                dim_type = self.DIMENSION_TYPES["proportion"]
                dimensions.append({
                    "type": "proportion",
                    "title": dim_type["title"],
                    "chart_type": dim_type["chart_type"],
                    "description": dim_type["description_template"].format(
                        category=cat_dim, metric=primary_metric
                    ),
                    "fields": {"metric": primary_metric, "dimension": cat_dim},
                })

        # 维度4：相关性分析（如果有多个数值字段且无时间维度）
        if len(metrics) >= 2 and not time_dimensions:
            dim_type = self.DIMENSION_TYPES["correlation"]
            dimensions.append({
                "type": "correlation",
                "title": dim_type["title"],
                "chart_type": dim_type["chart_type"],
                "description": dim_type["description_template"].format(
                    metric1=metrics[0], metric2=metrics[1]
                ),
                "fields": {"metric1": metrics[0], "metric2": metrics[1]},
            })

        # 维度5：排名（如果有分类字段且未被占比分析覆盖）
        if category_dimensions and len(dimensions) < 3:
            cat_dim = category_dimensions[0]
            if not any(d.get("type") == "proportion" for d in dimensions):
                dim_type = self.DIMENSION_TYPES["ranking"]
                dimensions.append({
                    "type": "ranking",
                    "title": dim_type["title"],
                    "chart_type": dim_type["chart_type"],
                    "description": dim_type["description_template"].format(
                        category=cat_dim, metric=primary_metric
                    ),
                    "fields": {"metric": primary_metric, "dimension": cat_dim},
                })

        return dimensions[:3]

    def generate_dimension_analysis(self, llm, dimension: dict, data_profile: dict,
                                     question: str, lang: str = "简体中文") -> dict:
        """为单个维度生成 LLM 分析

        Args:
            llm: LLM 实例
            dimension: 维度配置
            data_profile: 数据画像
            question: 原始问题
            lang: 输出语言

        Returns:
            维度分析结果 dict
        """
        template = get_template()
        multi_dim_template = template.get("multi_dimension", {})

        system_prompt = multi_dim_template.get("system", self._default_system_prompt())
        user_prompt = multi_dim_template.get("user", self._default_user_prompt())

        # 填充模板变量
        user_content = user_prompt.format(
            question=question,
            data_profile=json.dumps(data_profile, ensure_ascii=False)[:3000],  # 限制长度
            chart_type=dimension.get("chart_type", ""),
            dimension_type=dimension.get("type", ""),
            dimension_title=dimension.get("title", ""),
            dimension_description=dimension.get("description", ""),
            lang=lang,
        )

        messages = [
            SystemPromptMessage(content=system_prompt.format(lang=lang)),
            HumanMessage(content=user_content),
        ]

        try:
            full_text = ""
            for chunk in llm.stream(messages):
                if chunk.content:
                    full_text += chunk.content

            # 尝试解析 JSON 结果
            json_str = extract_nested_json(full_text)
            if json_str:
                result = orjson.loads(json_str)
                result["dimension_type"] = dimension.get("type")
                result["dimension_title"] = dimension.get("title")
                return result
            else:
                # 如果无法解析 JSON，将文本作为洞察返回
                return {
                    "dimension_type": dimension.get("type"),
                    "dimension_title": dimension.get("title"),
                    "chart_type": dimension.get("chart_type"),
                    "insight": full_text.strip(),
                    "chart_config": None,
                }
        except Exception as e:
            SQLBotLogUtil.exception(f"Multi-dimension analysis failed for {dimension.get('type')}: {e}")
            return {
                "dimension_type": dimension.get("type"),
                "dimension_title": dimension.get("title"),
                "chart_type": dimension.get("chart_type"),
                "insight": f"分析生成失败: {str(e)}",
                "chart_config": None,
            }

    @staticmethod
    def _default_system_prompt() -> str:
        return """你是数据分析专家。基于已有的查询结果和数据画像，为用户从特定维度进行深度分析。
请使用语言：{lang} 回答。

你需要输出一个 JSON 对象，格式如下：
{{
  "insight": "该维度的核心发现（1-3句话）",
  "details": ["详细分析点1", "详细分析点2", "详细分析点3"],
  "chart_config": {{
    "type": "推荐图表类型",
    "title": "图表标题",
    "axis": {{...}}
  }}
}}

如果无法生成有效的图表配置，chart_config 可以为 null。
请直接返回 JSON，不要包含其他文本。"""

    @staticmethod
    def _default_user_prompt() -> str:
        return """原始问题: {question}
分析维度: {dimension_title} - {dimension_description}
推荐图表类型: {chart_type}

数据画像:
{data_profile}

请从"{dimension_title}"的角度分析数据，给出核心洞察和推荐的图表配置。使用语言：{lang}"""
