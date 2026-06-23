import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from apps.chat.data_profile import build_data_profile, enrich_chart_config  # noqa: E402


def test_build_data_profile_detects_dimensions_metrics_and_chart_options():
    profile = build_data_profile(
        ["month", "region", "sales", "profit"],
        [
            {"month": "2026-01", "region": "华东", "sales": 1200, "profit": 120},
            {"month": "2026-02", "region": "华南", "sales": 1800, "profit": 240},
        ],
    )

    assert profile["time_dimensions"] == ["month"]
    assert profile["category_dimensions"] == ["region"]
    assert profile["metrics"] == ["sales", "profit"]
    assert profile["insights"]
    assert {item["type"] for item in profile["chart_alternatives"]} >= {"line", "column"}


def test_enrich_chart_config_adds_profile_insights_and_alternatives():
    profile = build_data_profile(
        ["category", "amount"],
        [
            {"category": "A", "amount": 10},
            {"category": "B", "amount": 20},
        ],
    )

    chart = enrich_chart_config({"type": "table", "title": "明细", "columns": []}, profile)

    assert chart["insights"]
    assert chart["alternatives"]
    assert len(chart["alternatives"]) <= 3


def test_top_values_enriched_with_per_object_metric_values():
    """分类维度的 top_values 必须带上每个对象的指标合计值（供报告点名引用真实数字）。"""
    profile = build_data_profile(
        ["customer", "deviation_rate"],
        [
            {"customer": "华东", "deviation_rate": 34},
            {"customer": "华东", "deviation_rate": 6},  # 华东 合计 = 40
            {"customer": "蓝海", "deviation_rate": 29},
            {"customer": "顺达", "deviation_rate": 24},
        ],
    )

    customer_field = next(f for f in profile["fields"] if f["name"] == "customer")
    assert customer_field["role"] == "category_dimension"
    tops = customer_field.get("top_values")
    assert tops, "category dimension should expose top_values"

    huanan = next(t for t in tops if t["value"] == "华东")
    assert "metric_values" in huanan
    # 每对象指标合计 = 该对象所有行的指标之和
    assert huanan["metric_values"]["deviation_rate"] == 40

    lanhai = next(t for t in tops if t["value"] == "蓝海")
    assert lanhai["metric_values"]["deviation_rate"] == 29


def test_enrich_top_values_without_metrics_does_not_crash():
    """没有数值指标时不应给 top_values 加 metric_values，也不得报错。"""
    profile = build_data_profile(
        ["category"],
        [{"category": "A"}, {"category": "B"}, {"category": "A"}],
    )

    cat_field = next(f for f in profile["fields"] if f["name"] == "category")
    for top in cat_field.get("top_values", []):
        assert "metric_values" not in top
