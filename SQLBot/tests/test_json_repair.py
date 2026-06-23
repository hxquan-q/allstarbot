import json
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from apps.chat.task.json_repair import repair_json_string_literals  # noqa: E402


def test_repairs_real_newlines_inside_string():
    """summary 字符串内的真实换行必须被修复为 \\n，使整体 JSON 可解析。"""
    raw = '{"summary":"## 总结论\n偏差 18.5%\n\n## 分层发现\n大客户 6%"}'
    repaired = repair_json_string_literals(raw)
    parsed = json.loads(repaired)
    assert "总结论" in parsed["summary"]
    assert "18.5%" in parsed["summary"]
    assert "分层发现" in parsed["summary"]


def test_preserves_already_escaped_sequences():
    """已经是合法转义的 \\n / \\t 不得被二次处理。"""
    raw = '{"summary":"line1\\nline2\\ttab"}'
    repaired = repair_json_string_literals(raw)
    assert json.loads(repaired)["summary"] == "line1\nline2\ttab"


def test_collapses_crlf_and_lone_cr_to_single_newline():
    assert json.loads(repair_json_string_literals('{"s":"a\r\nb"}'))["s"] == "a\nb"
    assert json.loads(repair_json_string_literals('{"s":"a\rb"}'))["s"] == "a\nb"


def test_strips_line_comments_outside_strings():
    raw = '{\n  // 这是一行注释\n  "type": "table"\n}'
    assert json.loads(repair_json_string_literals(raw))["type"] == "table"


def test_preserves_double_slash_inside_string():
    """字符串内的 // （如 URL）不得被误判为注释。"""
    raw = '{"url":"http://example.com/x"}'
    assert json.loads(repair_json_string_literals(raw))["url"] == "http://example.com/x"


def test_drops_trailing_comma():
    assert json.loads(repair_json_string_literals('{"type":"table",}'))["type"] == "table"
    assert json.loads(repair_json_string_literals('{"a":[1,2,]}'))["a"] == [1, 2]


def test_does_not_touch_content_outside_strings():
    """真实换行只出现在字符串内才需要修复；字符串外的结构保持不变。"""
    raw = '{\n  "type": "table",\n  "columns": []\n}'
    repaired = repair_json_string_literals(raw)
    assert json.loads(repaired) == {"type": "table", "columns": []}


def test_full_chart_config_with_multiline_summary_roundtrips():
    """端到端：含多段 Markdown summary 的图表配置整体可被解析，内容不损坏。"""
    raw = (
        '{"type":"column","title":"客户履约偏差",'
        '"summary":"## 🎯 总结论\n整体偏差率 18.5%，高于 15% 阈值。\n\n'
        '## ⚠️ 重点问题定位\n- TOP1 华东：偏差 40%\n- TOP2 蓝海：偏差 29%",'
        '"axis":{"x":{"name":"客户","value":"customer"},'
        '"y":[{"name":"偏差率","value":"deviation_rate"}]}}'
    )
    parsed = json.loads(repair_json_string_literals(raw))
    assert parsed["type"] == "column"
    assert "TOP1 华东" in parsed["summary"]
    assert "18.5%" in parsed["summary"]
