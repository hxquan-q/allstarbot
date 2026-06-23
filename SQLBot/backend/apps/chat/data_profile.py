import json
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


NUMERIC_RATIO_THRESHOLD = 0.7
DATETIME_RATIO_THRESHOLD = 0.7
MAX_PROFILE_ROWS = 200

TIME_KEYWORDS = (
    "date", "time", "day", "week", "month", "quarter", "year",
    "日期", "时间", "日", "周", "月", "季度", "年",
)
ID_KEYWORDS = ("id", "_id", "编号", "编码", "代码", "主键")
METRIC_KEYWORDS = (
    "count", "sum", "avg", "average", "amount", "total", "rate", "ratio", "num",
    "qty", "quantity", "price", "cost", "revenue", "profit", "value", "score",
    "数量", "次数", "金额", "总", "合计", "平均", "均值", "收入", "利润", "成本",
    "价格", "单价", "占比", "比例", "率", "得分", "分数", "指标",
)
UNIT_CURRENCY_KEYWORDS = (
    "price", "cost", "amount", "金额", "收入", "利润", "成本", "单价", "营业额", "总价", "总额",
)
UNIT_COUNT_KEYWORDS = (
    "qty", "quantity", "数量", "件", "个", "台", "套", "pcs", "count", "次数",
)
UNIT_WEIGHT_KEYWORDS = ("weight", "kg", "克", "吨", "重量")
UNIT_PERCENT_KEYWORDS = ("rate", "ratio", "percent", "率", "占比", "百分比")


def _infer_unit(name: str, numeric_values: list[Decimal]) -> str | None:
    """Infer a unit LABEL from the field name and value range. Never converts."""
    if _keyword_match(name, UNIT_PERCENT_KEYWORDS):
        return "%"
    if numeric_values:
        sample = numeric_values[:200]
        nonneg = [v for v in sample if v >= 0]
        if nonneg and all(v <= 1 for v in nonneg):
            return "%"
    if _keyword_match(name, UNIT_CURRENCY_KEYWORDS):
        return "元"
    if _keyword_match(name, UNIT_WEIGHT_KEYWORDS):
        return "kg"
    if _keyword_match(name, UNIT_COUNT_KEYWORDS):
        return "pcs"
    return None


def _compute_scale_hint(total: Decimal | None, unit: str | None) -> str | None:
    """Give a 万/亿 magnitude label for large sums so the model has the conversion."""
    if total is None or total == 0:
        return None
    magnitude = abs(total)
    if unit == "元":
        if magnitude >= Decimal("100000000"):
            return f"≈ {_plain_number(total / Decimal('100000000'))} 亿元"
        if magnitude >= Decimal("10000"):
            return f"≈ {_plain_number(total / Decimal('10000'))} 万元"
    elif magnitude >= Decimal("10000"):
        return f"≈ {_plain_number(total / Decimal('10000'))} 万{unit or ''}".strip()
    return None


def _field_names(fields: list[str] | None, data: list[dict] | None) -> list[str]:
    names: list[str] = []
    for field in fields or []:
        if field is not None and str(field) not in names:
            names.append(str(field))

    for row in data or []:
        if not isinstance(row, dict):
            continue
        for key in row.keys():
            if key is not None and str(key) not in names:
                names.append(str(key))
    return names


def _is_empty(value: Any) -> bool:
    return value is None or value == ""


def _parse_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or _is_empty(value):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("%"):
            raw = raw[:-1].strip()
        raw = raw.replace(",", "")
        if not re.fullmatch(r"[+-]?\d+(\.\d+)?", raw):
            return None
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None
    if re.fullmatch(r"[+-]?\d+(\.\d+)?", raw):
        return None

    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=None)
    except ValueError:
        pass

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m",
        "%Y/%m",
        "%Y%m%d",
        "%Y年%m月%d日",
        "%Y年%m月",
    )
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _keyword_match(name: str, keywords: tuple[str, ...]) -> bool:
    lowered = name.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _plain_number(value: Decimal | None) -> int | float | str | None:
    if value is None:
        return None
    if value == value.to_integral_value():
        text = str(value.quantize(Decimal(1)))
        if len(text.lstrip("-")) > 15:
            return text
        return int(value)
    text = format(value.normalize(), "f")
    if len(text.replace(".", "").replace("-", "")) > 15:
        return text
    return round(float(value), 6)


def _field_profile(name: str, values: list[Any], row_count: int) -> dict[str, Any]:
    non_empty = [value for value in values if not _is_empty(value)]
    null_count = row_count - len(non_empty)
    unique_values = Counter(str(value) for value in non_empty)
    unique_count = len(unique_values)

    numeric_values = [parsed for value in non_empty if (parsed := _parse_decimal(value)) is not None]
    datetime_values = [parsed for value in non_empty if (parsed := _parse_datetime(value)) is not None]

    numeric_ratio = len(numeric_values) / len(non_empty) if non_empty else 0
    datetime_ratio = len(datetime_values) / len(non_empty) if non_empty else 0
    is_time_named = _keyword_match(name, TIME_KEYWORDS)
    is_id_named = _keyword_match(name, ID_KEYWORDS)
    is_metric_named = _keyword_match(name, METRIC_KEYWORDS)

    inferred_type = "text"
    role = "text"
    if datetime_ratio >= DATETIME_RATIO_THRESHOLD or (is_time_named and datetime_values):
        inferred_type = "datetime"
        role = "time_dimension"
    elif numeric_ratio >= NUMERIC_RATIO_THRESHOLD and is_time_named and not is_id_named:
        inferred_type = "number"
        role = "time_dimension"
    elif numeric_ratio >= NUMERIC_RATIO_THRESHOLD and not is_id_named:
        inferred_type = "number"
        role = "metric" if is_metric_named or unique_count > 2 else "metric"
    elif unique_count <= min(50, max(12, row_count * 0.6)):
        inferred_type = "category"
        role = "category_dimension"

    profile: dict[str, Any] = {
        "name": name,
        "type": inferred_type,
        "role": role,
        "non_empty_count": len(non_empty),
        "null_count": null_count,
        "unique_count": unique_count,
    }

    if numeric_values:
        total = sum(numeric_values, Decimal(0))
        profile["numeric"] = {
            "min": _plain_number(min(numeric_values)),
            "max": _plain_number(max(numeric_values)),
            "avg": _plain_number(total / len(numeric_values)),
            "sum": _plain_number(total),
        }
        profile["unit"] = _infer_unit(name, numeric_values)
        profile["scale_hint"] = _compute_scale_hint(
            total, profile.get("unit")
        )

    if datetime_values:
        profile["datetime"] = {
            "min": min(datetime_values).isoformat(sep=" "),
            "max": max(datetime_values).isoformat(sep=" "),
        }

    if unique_values and role in {"category_dimension", "time_dimension"}:
        profile["top_values"] = [
            {"value": value, "count": count}
            for value, count in unique_values.most_common(5)
        ]

    return profile


def _axis(name: str, axis_type: str | None = None) -> dict[str, str]:
    item = {"name": name, "value": name}
    if axis_type:
        item["type"] = axis_type
    return item


def _build_chart_alternatives(profile: dict[str, Any]) -> list[dict[str, Any]]:
    fields = profile.get("fields", [])
    metrics = profile.get("metrics", [])
    time_dimensions = profile.get("time_dimensions", [])
    category_dimensions = profile.get("category_dimensions", [])

    alternatives: list[dict[str, Any]] = []
    table_alternative = {
        "type": "table",
        "title": "明细数据",
        "reason": "适合查看完整字段和原始明细",
        "columns": [_axis(field.get("name")) for field in fields[:12] if field.get("name")],
    } if fields else None

    def add(item: dict[str, Any]):
        if len(alternatives) >= 4:
            return
        signature = json.dumps({"type": item.get("type"), "axis": item.get("axis"), "columns": item.get("columns")},
                               ensure_ascii=False, sort_keys=True)
        existing = {
            json.dumps({"type": alt.get("type"), "axis": alt.get("axis"), "columns": alt.get("columns")},
                       ensure_ascii=False, sort_keys=True)
            for alt in alternatives
        }
        if signature not in existing:
            alternatives.append(item)

    if time_dimensions and metrics:
        y_axis = [_axis(metric) for metric in metrics[:3]]
        axis: dict[str, Any] = {"x": _axis(time_dimensions[0]), "y": y_axis}
        if len(y_axis) > 1:
            axis["multi-quota"] = {"name": "指标", "value": metrics[:3]}
        add({
            "type": "line",
            "title": f"{time_dimensions[0]}趋势",
            "reason": "适合观察指标随时间的变化和波动",
            "axis": axis,
        })

    # 面积图推荐：有时间维度且单指标时，面积图更适合强调变化幅度
    if time_dimensions and metrics and len(metrics) == 1:
        add({
            "type": "area",
            "title": f"{metrics[0]}累积趋势",
            "reason": "面积图适合强调数值的变化幅度和累积效果",
            "axis": {
                "x": _axis(time_dimensions[0]),
                "y": [_axis(metrics[0])],
            },
        })

    if category_dimensions and metrics:
        add({
            "type": "column",
            "title": f"{category_dimensions[0]}对比",
            "reason": "适合比较不同类别之间的指标差异",
            "axis": {
                "x": _axis(category_dimensions[0]),
                "y": [_axis(metrics[0])],
            },
        })
        add({
            "type": "bar",
            "title": f"{category_dimensions[0]}排名",
            "reason": "适合展示类别排名和长名称类别",
            "axis": {
                "x": _axis(category_dimensions[0]),
                "y": [_axis(metrics[0])],
            },
        })
        category_profile = next((item for item in fields if item.get("name") == category_dimensions[0]), {})
        if category_profile.get("unique_count", 999) <= 12:
            add({
                "type": "pie",
                "title": f"{category_dimensions[0]}占比",
                "reason": "适合观察低基数类别的构成占比",
                "axis": {
                    "series": _axis(category_dimensions[0]),
                    "y": _axis(metrics[0]),
                },
            })

    # 散点图推荐：有2个及以上数值字段且无时间维度时
    if len(metrics) >= 2 and not time_dimensions:
        add({
            "type": "scatter",
            "title": f"{metrics[0]} vs {metrics[1]}",
            "reason": "散点图适合观察两个数值变量之间的相关性和分布",
            "axis": {
                "x": _axis(metrics[0]),
                "y": [_axis(metrics[1])],
            },
        })

    if table_alternative:
        if len(alternatives) >= 3 and all(item.get("type") != "table" for item in alternatives):
            alternatives[-1] = table_alternative
        else:
            add(table_alternative)

    return alternatives[:3]


def _build_insights(profile: dict[str, Any]) -> list[str]:
    insights: list[str] = []
    row_count = profile.get("row_count", 0)
    field_count = profile.get("field_count", 0)
    if row_count:
        insights.append(f"当前结果包含 {row_count} 行、{field_count} 个字段，可用于表格查看和进一步拆解。")

    fields = profile.get("fields", [])
    metrics = profile.get("metrics", [])
    time_dimensions = profile.get("time_dimensions", [])
    category_dimensions = profile.get("category_dimensions", [])

    if metrics:
        metric_name = metrics[0]
        metric_profile = next((item for item in fields if item.get("name") == metric_name), {})
        numeric = metric_profile.get("numeric") or {}
        summary_parts = []
        if numeric.get("sum") is not None:
            summary_parts.append(f"合计 {numeric.get('sum')}")
        if numeric.get("avg") is not None:
            summary_parts.append(f"均值 {numeric.get('avg')}")
        if numeric.get("min") is not None and numeric.get("max") is not None:
            summary_parts.append(f"范围 {numeric.get('min')} 至 {numeric.get('max')}")
        if summary_parts:
            insights.append(f"核心指标“{metric_name}”的" + "，".join(summary_parts) + "。")

    if time_dimensions:
        time_name = time_dimensions[0]
        time_profile = next((item for item in fields if item.get("name") == time_name), {})
        time_range = time_profile.get("datetime") or {}
        if time_range:
            insights.append(f"结果包含时间维度“{time_name}”，时间范围为 {time_range.get('min')} 至 {time_range.get('max')}。")
        else:
            insights.append(f"结果包含时间维度“{time_name}”，适合继续观察趋势和周期变化。")

    if category_dimensions:
        category_name = category_dimensions[0]
        category_profile = next((item for item in fields if item.get("name") == category_name), {})
        unique_count = category_profile.get("unique_count")
        if unique_count is not None:
            insights.append(f"可按“{category_name}”进行分类对比，该维度包含 {unique_count} 个取值。")

    if not metrics:
        insights.append("当前结果未识别到稳定的数值指标，优先使用表格展示，并可补充聚合指标后再做图表分析。")

    return insights[:5]


def _build_key_metrics(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """从数据画像中提取关键指标摘要，供前端指标卡片展示"""
    key_metrics: list[dict[str, Any]] = []
    fields = profile.get("fields", [])
    metrics = profile.get("metrics", [])
    row_count = profile.get("row_count", 0)

    for metric_name in metrics[:4]:  # 最多4个核心指标
        metric_profile = next((item for item in fields if item.get("name") == metric_name), {})
        numeric = metric_profile.get("numeric") or {}
        if not numeric:
            continue

        metric_item: dict[str, Any] = {
            "name": metric_name,
            "sum": numeric.get("sum"),
            "avg": numeric.get("avg"),
            "min": numeric.get("min"),
            "max": numeric.get("max"),
            "count": row_count,
        }

        # 计算变化趋势（基于首尾值的简单判断）
        if numeric.get("min") is not None and numeric.get("max") is not None:
            if numeric.get("max") != 0:
                spread = numeric.get("max") - numeric.get("min") if isinstance(numeric.get("max"), (int, float)) and isinstance(numeric.get("min"), (int, float)) else 0
                metric_item["spread"] = spread

        key_metrics.append(metric_item)

    return key_metrics


def _enrich_top_values_with_metrics(profile: dict[str, Any], rows: list[dict]) -> None:
    """为分类维度的 top_values 关联每个对象的指标合计值。

    报告"重点问题定位"需要点名具体对象并给出其指标数字（如每个客户的偏差率）。
    top_values 原本只有 {value, count}（仅对象名），模型拿不到数值便会打印推理困惑
    （"需在主表中查看…"）。这里补上 metric_values，让模型有真实数字可引用、无需编造。
    仅处理 category_dimension，focus 指标取前 3 个以控制 token 与速度。
    """
    metrics = [m for m in (profile.get("metrics") or []) if isinstance(m, str)]
    if not metrics or not rows:
        return

    def _is_derived_metric(name: str) -> bool:
        lowered = name.lower()
        return any(kw in name or kw in lowered for kw in
                   ("rate", "ratio", "deviation", "偏差", "率", "比", "达成", "占比", "同比", "环比"))

    # 优先纳入派生/关键指标（偏差率、达成率、占比、同环比…）——报告点名最常引用的就是这类；
    # 再按原顺序补齐其余指标，总数封顶以控制 data-profile 的 token 开销。
    focus_metrics = sorted(metrics, key=lambda m: (0 if _is_derived_metric(m) else 1, metrics.index(m)))[:4]

    for field_info in profile.get("fields", []):
        if not isinstance(field_info, dict) or field_info.get("role") != "category_dimension":
            continue
        tops = field_info.get("top_values")
        if not isinstance(tops, list) or not tops:
            continue
        fname = field_info.get("name")

        # 单次扫描数据，按对象名聚合每个 focus 指标（Decimal 精确累加）
        grouped: dict[Any, dict[str, list[Decimal]]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = row.get(fname)
            if value is None or value == "":
                continue
            bucket = grouped.setdefault(value, {m: [] for m in focus_metrics})
            for metric in focus_metrics:
                parsed = _parse_decimal(row.get(metric))
                if parsed is not None:
                    bucket[metric].append(parsed)

        for top in tops:
            if not isinstance(top, dict):
                continue
            bucket = grouped.get(top.get("value"))
            if not bucket:
                continue
            metric_values: dict[str, Any] = {}
            for metric in focus_metrics:
                values = bucket.get(metric) or []
                if values:
                    metric_values[metric] = _plain_number(sum(values, Decimal(0)))
            if metric_values:
                top["metric_values"] = metric_values


def build_data_profile(fields: list[str] | None, data: list[dict] | None, max_rows: int = MAX_PROFILE_ROWS) -> dict[str, Any]:
    rows = [row for row in (data or []) if isinstance(row, dict)]
    sampled_rows = rows[:max_rows]
    names = _field_names(fields, sampled_rows)

    field_profiles = [
        _field_profile(name, [row.get(name) for row in sampled_rows], len(sampled_rows))
        for name in names
    ]

    profile: dict[str, Any] = {
        "row_count": len(rows),
        "profiled_row_count": len(sampled_rows),
        "field_count": len(names),
        "fields": field_profiles,
        "time_dimensions": [item["name"] for item in field_profiles if item.get("role") == "time_dimension"],
        "category_dimensions": [item["name"] for item in field_profiles if item.get("role") == "category_dimension"],
        "metrics": [item["name"] for item in field_profiles if item.get("role") == "metric"],
    }
    profile["chart_alternatives"] = _build_chart_alternatives(profile)
    profile["insights"] = _build_insights(profile)
    profile["key_metrics"] = _build_key_metrics(profile)
    _enrich_top_values_with_metrics(profile, sampled_rows)
    return profile


def build_data_profile_text(fields: list[str] | None, data: list[dict] | None,
                            profile: dict[str, Any] | None = None) -> str:
    profile = profile or build_data_profile(fields, data)
    return json.dumps(profile, ensure_ascii=False)


def enrich_chart_config(chart: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return chart

    enriched = dict(chart)
    if not isinstance(enriched.get("insights"), list) or not enriched.get("insights"):
        enriched["insights"] = profile.get("insights", [])

    alternatives = enriched.get("alternatives")
    if not isinstance(alternatives, list):
        alternatives = []
    alternatives = [item for item in alternatives if isinstance(item, dict) and item.get("type")]

    generated = profile.get("chart_alternatives") or []
    existing_types = {(item.get("type"), item.get("title")) for item in alternatives}
    for item in generated:
        if len(alternatives) >= 3:
            break
        key = (item.get("type"), item.get("title"))
        if key not in existing_types:
            alternatives.append(item)
            existing_types.add(key)

    enriched["alternatives"] = alternatives[:3]
    return enriched
