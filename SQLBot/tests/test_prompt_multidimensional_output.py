import os


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(PROJECT_ROOT, "backend", "templates", "template.yaml")


def test_chart_prompt_requires_insights_and_alternatives():
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        content = f.read()

    assert "multi-format-chart-output" in content
    assert '"alternatives"' in content
    assert '"insights"' in content


def test_chart_prompt_requires_dashboard_narrative_summary():
    """summary 必须是看板式高密度简报，而非列表墙式数据复述"""
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        content = f.read()

    assert "narrative-summary" in content
    assert "dashboard-architecture" in content
    assert "EXECUTIVE DASHBOARD" in content
    assert "STRATEGIC INSIGHTS" in content
    assert "EXCEPTION RADAR" in content
    assert "ACTION ROADMAP" in content
    assert "轻量级 Markdown 表格" in content
    assert "chart-text-anchoring" in content
    assert "👉" in content
    assert "24小时内" in content


def test_sql_prompt_requires_comparison_layering():
    """SQL 必须主动产出对比分层与派生指标，支撑分级分析"""
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        content = f.read()

    assert "comparison-layering" in content
    assert "derived-metric" in content


def test_analysis_prompt_requires_layered_business_report():
    """手动深度分析同样必须是分层、可决策的业务报告"""
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        content = f.read()

    assert "总览结论" in content
    assert "分层发现" in content
    assert "重点问题定位" in content   # 必须点名 TOP 问题对象
    assert "行动建议" in content       # 必须分级行动
    assert "图表建议" in content


def test_query_limit_respects_explicit_count():
    """用户显式指定数量（即使 >1000）必须以用户为准，不回退默认 1000"""
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        content = f.read()

    assert "explicit-limit-overrides" in content
    # 明确说明大于 1000 也以用户为准
    assert "大于 1000" in content or "大于1000" in content


def test_no_redundant_multi_table_field_rule():
    """多表字段限定规则应只在 multi_table_condition 单一来源承载，删除散句"""
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        content = f.read()

    # 这条曾与 multi_table_condition 重复的散句应已删除
    assert "不论查询的表字段是否有重名" not in content
    # 权威规则块仍在
    assert "multi_table_condition" in content


def test_chart_series_multi_quota_deadlock_resolution():
    """series 与 multi-quota 死锁场景必须有降级策略，不得返回 error"""
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        content = f.read()

    assert "chart-config-decision" in content
    assert "死锁场景降级" in content


def test_permissions_sql_injection_defense():
    """permissions 动态过滤注入必须有 SQL 注入防御规则"""
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        content = f.read()

    assert "sql-injection-defense" in content
    # 必须覆盖典型注入特征
    for token in ("UNION", "DROP", "1=1"):
        assert token in content


def test_summary_json_escape_safety():
    """summary 字段必须有高强度 JSON 转义防错指令"""
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        content = f.read()

    assert "format-escape" in content
    assert "未转义的双引号" in content
    # 生成流程中必须有转义自检步骤
    assert "强制转义自检" in content
