import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from apps.chat.prompts.analysis_prompt import AnalysisPromptInput, build_analysis_messages  # noqa: E402


def test_build_analysis_messages_returns_system_and_user():
    inp = AnalysisPromptInput(
        lang="简体中文",
        sqlbot_name="小爱同学",
        terminologies="<terminologies></terminologies>",
        custom_prompt="",
        fields='["demand_total","supply_gap"]',
        data='[{"demand_total":1}]',
        data_profile='{"metrics":["demand_total"],"fields":[]}',
    )
    msgs = build_analysis_messages(inp)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_system_prompt_enforces_critical_rules():
    inp = AnalysisPromptInput(
        lang="简体中文", sqlbot_name="小爱同学", terminologies="", custom_prompt="",
        fields="[]", data="[]", data_profile="{}",
    )
    system = build_analysis_messages(inp)[0]["content"]
    for needle in ["数据口径", "单位", "分层", "TOP", "行动建议", "术语", "统计周期"]:
        assert needle in system, f"system prompt missing rule block: {needle}"


def test_user_prompt_injects_fields_data_profile():
    inp = AnalysisPromptInput(
        lang="简体中文", sqlbot_name="小爱同学", terminologies="", custom_prompt="",
        fields='["demand_total"]', data='[{"demand_total":1}]',
        data_profile='{"metrics":["demand_total"]}',
    )
    user = build_analysis_messages(inp)[1]["content"]
    assert "demand_total" in user
    assert "metrics" in user


from apps.chat.models.chat_model import AiModelQuestion  # noqa: E402


def test_analysis_sys_user_question_use_builder():
    q = AiModelQuestion()
    q.lang = "简体中文"
    q.sqlbot_name = "小爱同学"
    q.terminologies = "<terminologies></terminologies>"
    q.custom_prompt = ""
    q.fields = '["demand_total"]'
    q.data = '[{"demand_total": 1}]'
    q.data_profile = '{"metrics": ["demand_total"]}'
    system = q.analysis_sys_question()
    user = q.analysis_user_question()
    assert "数据口径" in system      # new critical rule present
    assert "demand_total" in user   # fields injected
    assert "metrics" in user        # profile injected
