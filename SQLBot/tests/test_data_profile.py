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


def test_unit_inferred_from_field_name():
    profile = build_data_profile(
        ["material_name", "amount", "gap_rate", "qty"],
        [{"material_name": "A", "amount": 100, "gap_rate": 0.12, "qty": 5}],
    )
    by_name = {f["name"]: f for f in profile["fields"]}
    assert by_name["amount"]["unit"] == "元"
    assert by_name["qty"]["unit"] == "pcs"
    assert by_name["gap_rate"]["unit"] == "%"
    assert by_name["material_name"].get("unit") is None


def test_unit_percent_by_value_range_when_name_has_rate():
    profile = build_data_profile(
        ["rate"],
        [{"rate": 12.0}, {"rate": 7.0}, {"rate": 15.0}],
    )
    assert profile["fields"][0]["unit"] == "%"


def test_unit_percent_by_value_range_without_keyword():
    profile = build_data_profile(
        ["completion"],
        [{"completion": 0.12}, {"completion": 0.07}, {"completion": 0.15}],
    )
    assert profile["fields"][0]["unit"] == "%"


def test_scale_hint_wan_for_large_currency_sum():
    profile = build_data_profile(
        ["amount"],
        [{"amount": 8216389}, {"amount": 3361000}],
    )
    field = profile["fields"][0]
    assert field["scale_hint"] is not None
    assert "万" in field["scale_hint"]


def test_unit_none_when_no_signal():
    profile = build_data_profile(
        ["mystery"], [{"mystery": 42}, {"mystery": 7}],
    )
    assert profile["fields"][0].get("unit") is None


def test_alias_translates_known_snake_case_tokens():
    profile = build_data_profile(
        ["demand_total", "available_total", "supply_gap", "gap_rate_percent"],
        [{"demand_total": 1, "available_total": 1, "supply_gap": 1, "gap_rate_percent": 1}],
    )
    by_name = {f["name"]: f for f in profile["fields"]}
    assert by_name["demand_total"]["alias"] == "需求总量"
    assert by_name["supply_gap"]["alias"] == "供应缺口"
    assert by_name["gap_rate_percent"]["alias"] == "缺口率百分比"


def test_alias_keeps_unknown_tokens_and_skips_already_chinese():
    profile = build_data_profile(
        ["weird_xyz", "物料编码"], [{"weird_xyz": 1, "物料编码": "M1"}],
    )
    by_name = {f["name"]: f for f in profile["fields"]}
    assert by_name["weird_xyz"]["alias"] == "weird xyz"
    # Already-Chinese names alias to themselves
    assert by_name["物料编码"]["alias"] == "物料编码"


def test_distribution_quartile_bands_and_extreme_count():
    profile = build_data_profile(
        ["gap"],
        [{"gap": v} for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 50, 60]],
    )
    dist = profile["fields"][0]["distribution"]
    assert sum(b["count"] for b in dist["bands"]) == 12
    assert dist["extreme_count"] >= 1  # 50, 60 are within 20% of max(60)
    assert all("label" in b and "count" in b for b in dist["bands"])


def test_distribution_none_for_too_few_values():
    profile = build_data_profile(["gap"], [{"gap": 1}, {"gap": 2}])
    assert profile["fields"][0].get("distribution") is None


def test_distribution_near_ceiling_for_rate_metric():
    profile = build_data_profile(
        ["gap_rate"], [{"gap_rate": v} for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 14, 14.9]],
    )
    dist = profile["fields"][0]["distribution"]
    assert dist["near_ceiling_count"] >= 1


def test_distribution_all_equal_constant_column():
    profile = build_data_profile(["gap"], [{"gap": 7}, {"gap": 7}, {"gap": 7}, {"gap": 7}])
    dist = profile["fields"][0]["distribution"]
    assert sum(b["count"] for b in dist["bands"]) == 4
    assert dist["extreme_count"] == 0  # constant column → no extremes
