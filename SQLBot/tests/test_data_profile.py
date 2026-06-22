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
