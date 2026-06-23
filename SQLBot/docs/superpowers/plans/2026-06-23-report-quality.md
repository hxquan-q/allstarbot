# 分析报告输出质量提升 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lift the analysis-report output quality across the full chain (data_profile fuel → analysis prompt → markdown/chart rendering), using generic heuristics, with supply-chain as the verification case.

**Architecture:** Three phases that plug onto the existing pipeline without rewiring `run_task`. Phase A enriches `data_profile.py` with unit/alias/distribution/code→name fields (zero-dep, unit-tested). Phase B modularizes the analysis prompt into `prompts/analysis_prompt.py` and rewrites its rules. Phase C polishes the markdown render + chart-axis unit (frontend testable core; chart-engine wiring deferred to browser verification). The profile feeds both the analysis report and the main chart, so Phase A fixes two surfaces at once.

**Tech Stack:** Python (decimal/collections, pytest), markdown-it (frontend), node `--experimental-strip-types` for `.test.mjs`.

**Spec:** `SQLBot/docs/superpowers/specs/2026-06-23-report-quality-design.md`

**Test runner:** `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/ -q` (backend); `node --experimental-strip-types <file>.test.mjs` (frontend).

---

## File Structure

**Backend — Phase A (`apps/chat/data_profile.py`)**
- Modify: `apps/chat/data_profile.py` — add `_infer_unit`, `_compute_scale_hint`, `_infer_alias`, `_compute_distribution`, `_pair_code_to_name_label`; hook into `_field_profile` and `_enrich_top_values_with_metrics`. Additive only.
- Test: `tests/test_data_profile.py` — extend with new cases.

**Backend — Phase B (`apps/chat/prompts/analysis_prompt.py`)**
- Create: `apps/chat/prompts/analysis_prompt.py` — `AnalysisPromptInput` + `build_analysis_messages(inp)`.
- Modify: `apps/chat/prompts/__init__.py` — export new symbols.
- Modify: `apps/chat/models/chat_model.py:302-308` — `analysis_sys_question`/`analysis_user_question` delegate to the builder.
- Test: `tests/test_analysis_prompt.py` (new) — assembled-prompt snapshot test.

**Frontend — Phase C**
- Modify: `frontend/src/style.less` — `.md-table-wrap th` no-truncate + `.markdown-body blockquote` callout.
- Create: `frontend/src/utils/markdown.test.mjs` — node test for callout + table-wrap rendering.
- Create: `frontend/src/utils/chartAxis.ts` — `formatAxisWithUnit(value, unit)` pure helper.
- Create: `frontend/src/utils/chartAxis.test.mjs` — node test.
- Modify: `apps/chat/data_profile.py` `enrich_chart_config` — stamp `unit` onto y-axis config.
- **Deferred (browser-verified follow-up, not in executable scope below):** wire `formatAxisWithUnit` into the chart engine axis option + high/mid/low color palette. Rationale: the chart option builder lives behind `ChartComponent.vue`'s chart engine (no `axisLabel`/`setOption` in the component), unmapped without a live browser, and the spec assigns visual verification to the user's machine. Tracked as a follow-up note, not a placeholder step.

---

## Phase A — `data_profile` enrichment

### Task A1: unit + scale_hint inference

**Files:**
- Modify: `SQLBot/backend/apps/chat/data_profile.py` (add keyword groups + `_infer_unit` + `_compute_scale_hint`; call from `_field_profile`)
- Test: `SQLBot/tests/test_data_profile.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_data_profile.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_data_profile.py -k "unit or scale_hint" -q`
Expected: FAIL (`KeyError: 'unit'` / `KeyError: 'scale_hint'`).

- [ ] **Step 3: Implement the helpers**

In `apps/chat/data_profile.py`, add near the other keyword tuples (after `METRIC_KEYWORDS`):

```python
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
```

Then in `_field_profile`, where `numeric` is built (after the `profile["numeric"] = {...}` block), add:

```python
    if numeric_values:
        profile["unit"] = _infer_unit(name, numeric_values)
        profile["scale_hint"] = _compute_scale_hint(
            sum(numeric_values, Decimal(0)), profile.get("unit")
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_data_profile.py -k "unit or scale_hint" -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Run full data_profile suite for regression**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_data_profile.py -q`
Expected: PASS (all, no regression).

- [ ] **Step 6: Commit**

```bash
git add SQLBot/backend/apps/chat/data_profile.py SQLBot/tests/test_data_profile.py
git commit -m "feat(data_profile): 推断指标单位与量级提示（标注不换算）"
```

---

### Task A2: Chinese alias inference

**Files:**
- Modify: `SQLBot/backend/apps/chat/data_profile.py` (add `_infer_alias`; call from `_field_profile`)
- Test: `SQLBot/tests/test_data_profile.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_data_profile.py -k alias -q`
Expected: FAIL (`KeyError: 'alias'`).

- [ ] **Step 3: Implement `_infer_alias`**

In `apps/chat/data_profile.py`, add:

```python
ALIAS_TOKEN_MAP = {
    "demand": "需求", "available": "可用", "supply": "供应", "gap": "缺口",
    "total": "总量", "amount": "金额", "qty": "数量", "quantity": "数量",
    "rate": "率", "percent": "百分比", "ratio": "占比", "price": "价格",
    "cost": "成本", "revenue": "收入", "profit": "利润", "count": "次数",
    "material": "物料", "code": "编码", "name": "名称", "desc": "描述",
    "product": "产品", "warehouse": "仓库", "region": "区域", "date": "日期",
    "month": "月份", "year": "年份", "forecast": "预测", "actual": "实际",
    "plan": "计划", "order": "订单", "stock": "库存", "safety": "安全",
}


def _infer_alias(name: str) -> str:
    """Translate snake_case field names to Chinese via a token map; keep unknowns."""
    if not name:
        return name
    # Already (mostly) Chinese — return as-is.
    if any("一" <= ch <= "鿿" for ch in name):
        return name
    tokens = []
    for raw in str(name).replace("-", "_").split("_"):
        if not raw:
            continue
        lowered = raw.lower()
        tokens.append(ALIAS_TOKEN_MAP.get(lowered, raw))
    return "".join(tokens) if all("一" <= ch <= "鿿" for ch in "".join(tokens) if ch) else " ".join(tokens)
```

Then in `_field_profile`, set the alias near the top of building `profile` (after `"name": name`):

```python
    profile: dict[str, Any] = {
        "name": name,
        "alias": _infer_alias(name),
        "type": inferred_type,
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_data_profile.py -k alias -q`
Expected: PASS.

- [ ] **Step 5: Run full suite + commit**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_data_profile.py -q`
Expected: PASS (no regression).

```bash
git add SQLBot/backend/apps/chat/data_profile.py SQLBot/tests/test_data_profile.py
git commit -m "feat(data_profile): 推断字段中文名称别名（snake_case 翻译表）"
```

---

### Task A3: distribution bands + extreme/near-ceiling counts

**Files:**
- Modify: `SQLBot/backend/apps/chat/data_profile.py` (add `_compute_distribution`; call from `_field_profile`)
- Test: `SQLBot/tests/test_data_profile.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_data_profile.py -k distribution -q`
Expected: FAIL (`KeyError: 'distribution'`).

- [ ] **Step 3: Implement `_compute_distribution`**

In `apps/chat/data_profile.py`, add:

```python
def _compute_distribution(name: str, numeric_values: list[Decimal]) -> dict[str, Any] | None:
    """Data-driven quartile bands + extreme/near-ceiling counts. No hard-coded 8/15."""
    if len(numeric_values) < 4:
        return None
    sorted_vals = sorted(numeric_values)
    n = len(sorted_vals)
    lo, hi = sorted_vals[0], sorted_vals[-1]

    def at(frac: float) -> Decimal:
        idx = min(n - 1, max(0, int(round(frac * (n - 1)))))
        return sorted_vals[idx]

    q1, q2, q3 = at(0.25), at(0.5), at(0.75)
    cut_points = [q1, q2, q3, hi]

    bands: list[dict[str, Any]] = []
    prev = lo
    labels = ["低", "中低", "中高", "高"]
    for i, cut in enumerate(cut_points):
        count = sum(1 for v in sorted_vals if (prev < v <= cut) or (i == 0 and v == prev))
        bands.append({
            "label": labels[i],
            "min": _plain_number(prev),
            "max": _plain_number(cut),
            "count": count,
        })
        prev = cut

    span = hi - lo
    extreme_threshold = hi - span * Decimal("0.2")
    extreme_count = sum(1 for v in sorted_vals if v >= extreme_threshold)

    result: dict[str, Any] = {"bands": bands, "extreme_count": extreme_count}
    # Rate metric (see _infer_unit 口径): also count rows near the observed ceiling.
    if _infer_unit(name, numeric_values) == "%":
        near = hi - span * Decimal("0.15")
        result["near_ceiling_count"] = sum(1 for v in sorted_vals if v >= near)
    return result
```

Then in `_field_profile`, inside the `if numeric_values:` block, add:

```python
        profile["distribution"] = _compute_distribution(name, numeric_values)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_data_profile.py -k distribution -q`
Expected: PASS.

- [ ] **Step 5: Run full suite + commit**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_data_profile.py -q`
Expected: PASS.

```bash
git add SQLBot/backend/apps/chat/data_profile.py SQLBot/tests/test_data_profile.py
git commit -m "feat(data_profile): 指标四分位分桶与极值/临近阈值计数"
```

---

### Task A4: code→name pairing for category top_values

**Files:**
- Modify: `SQLBot/backend/apps/chat/data_profile.py` (add `_pair_code_to_name_label`; call from `_enrich_top_values_with_metrics`)
- Test: `SQLBot/tests/test_data_profile.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_code_to_name_paired_when_companion_name_column_exists():
    profile = build_data_profile(
        ["material_code", "material_name", "gap"],
        [
            {"material_code": "MECH.000085", "material_name": "硅胶密封圈(VMQ 70A)", "gap": 86795},
            {"material_code": "MECH.000086", "material_name": "O型圈(NBR)", "gap": 5000},
            {"material_code": "MECH.000085", "material_name": "硅胶密封圈(VMQ 70A)", "gap": 100},
        ],
    )
    code_field = next(f for f in profile["fields"] if f["name"] == "material_code")
    tops = code_field["top_values"]
    top1 = tops[0]
    assert "硅胶密封圈" in top1["label"]
    assert "MECH.000085" in top1["label"]


def test_code_to_name_refuses_numeric_or_id_companion():
    # companion column is an id-like integer → must not be used as a display label
    profile = build_data_profile(
        ["material_code", "ref_id", "gap"],
        [
            {"material_code": "M1", "ref_id": 1001, "gap": 1},
            {"material_code": "M2", "ref_id": 1002, "gap": 2},
        ],
    )
    code_field = next(f for f in profile["fields"] if f["name"] == "material_code")
    for top in code_field.get("top_values", []):
        assert top.get("label") in (None, top.get("value")) or top["label"] == top["value"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_data_profile.py -k "code_to_name" -q`
Expected: FAIL (`KeyError: 'label'`).

- [ ] **Step 3: Implement `_pair_code_to_name_label`**

In `apps/chat/data_profile.py`, add:

```python
NAME_COLUMN_KEYWORDS = ("name", "名称", "描述", "desc", "title", "品名")


def _is_name_like_column(field_info: dict[str, Any]) -> bool:
    if not isinstance(field_info, dict):
        return False
    role = field_info.get("role")
    if role in {"metric", "time_dimension"}:
        return False
    if field_info.get("type") in {"number", "datetime"}:
        return False
    name = str(field_info.get("name", "")).lower()
    has_cjk = any("一" <= ch <= "鿿" for ch in str(field_info.get("name", "")))
    return bool(_keyword_match(field_info.get("name", ""), NAME_COLUMN_KEYWORDS)) or has_cjk


def _pair_code_to_name_label(rows: list[dict], fields: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """For each category column, find a 1:1 / many:1 name-like companion and map code→display label."""
    category_fields = [f for f in fields if isinstance(f, dict) and f.get("role") == "category_dimension"]
    name_fields = [f for f in fields if _is_name_like_column(f) and f.get("name") not in {c.get("name") for c in category_fields}]
    if not category_fields or not name_fields:
        return {}

    # Build code→name map where the relationship is consistent (many:1 allowed, 1:many rejected).
    result: dict[str, dict[str, str]] = {}
    for cat in category_fields:
        cat_name = cat.get("name")
        for nf in name_fields:
            nf_name = nf.get("name")
            mapping: dict[str, str] = {}
            consistent = True
            for row in rows:
                if not isinstance(row, dict):
                    continue
                code = row.get(cat_name)
                disp = row.get(nf_name)
                if _is_empty(code) or _is_empty(disp):
                    continue
                code_s, disp_s = str(code), str(disp)
                if code_s in mapping and mapping[code_s] != disp_s:
                    consistent = False  # 1:many → not an attribute
                    break
                mapping[code_s] = disp_s
            if consistent and mapping:
                result[cat_name] = mapping
                break
    return result
```

Then in `_enrich_top_values_with_metrics`, after the metric-values loop that sets `top["metric_values"]`, stamp the label. Add at the start of the function (after the `metrics` guard) the mapping lookup, and inside the `for top in tops:` loop set the label. Concretely, modify the function:

```python
    code_to_name = _pair_code_to_name_label(rows, profile.get("fields", []))
    ...
    for top in tops:
        ...
        if metric_values:
            top["metric_values"] = metric_values
        # code→name display label
        name_map = code_to_name.get(fname)
        if name_map:
            disp = name_map.get(str(top.get("value")))
            if disp:
                top["label"] = f"{top.get('value')} {disp}"
```

(`fname` is already the category column name in scope inside the existing `for field_info in profile.get("fields", []):` loop where `tops` is processed.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_data_profile.py -k "code_to_name or top_values" -q`
Expected: PASS.

- [ ] **Step 5: Run full backend suite for regression**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/ -q`
Expected: All green (existing 230 + new Phase A tests). The one known pre-existing failure `test_summary_json_escape_safety` (template.yaml) is unrelated.

- [ ] **Step 6: Commit**

```bash
git add SQLBot/backend/apps/chat/data_profile.py SQLBot/tests/test_data_profile.py
git commit -m "feat(data_profile): 分类维度 code→name 配对显示标签"
```

---

## Phase B — analysis prompt modularization + rule rewrite

### Task B1: create `analysis_prompt.py` builder + snapshot test

**Files:**
- Create: `SQLBot/backend/apps/chat/prompts/analysis_prompt.py`
- Test: `SQLBot/tests/test_analysis_prompt.py`

- [ ] **Step 1: Write the failing snapshot test**

Create `tests/test_analysis_prompt.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_analysis_prompt.py -q`
Expected: FAIL (import error — module does not exist).

- [ ] **Step 3: Create the builder**

Create `apps/chat/prompts/analysis_prompt.py`:

```python
"""Modular analysis-report prompt builder (mirrors sql_prompt.py).

Produces a layered, decision-ready business analysis report in Markdown.
Rules are stated exactly once (dedup invariant) and consume the enriched
data_profile (alias / unit / scale_hint / distribution / top_values.label /
metric_values) so the model has real numbers and Chinese labels to cite
instead of inventing them.
"""
from __future__ import annotations

from dataclasses import dataclass, field


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
                 "关键字段中文别名(取 alias，原英文名仅在此出现一次)。"),
    ("critical", "## 📊 关键指标：用表格 | 指标(中文名) | 数值(带单位) | 趋势(📈/📉/➡️) | 业务含义 |。"
                 "存在易混口径(如 计划/要货/出库、需求/可用/供应)时，必须用一句话讲清逻辑关系与口径差异。"),
    ("critical", "## 🔍 分层发现：按 2-4 维度展开，每个维度用一个 ### 三级标题。"
                 "禁止在同一段内混用两个维度(如 仓库 与 物料)；每个 ### 只展开一个维度，每条=具体数字→业务含义。"),
    ("critical", "## ⚠️ 重点问题定位：必须点名 TOP 3-5 个具体对象(取 top_values.label 的名称)，"
                 "每项=对象名+真实数字(取 metric_values，带单位)+风险等级+量化阈值判断(如 偏差>20% 属严重)。"
                 "首部用一个以 `> 🔴 TOP1` 开头的引用块单独置顶最大问题，格式固定："
                 "`> 🔴 TOP1：{对象} {指标} {数字}{单位}（{阈值判断}）`。严禁只说\"有N个异常\"不点名。"),
    ("normal", "## 📈 趋势与变化：量化变化幅度(增长 X%)，指出拐点位置。"),
    ("critical", "## 🎯 行动建议：按 🔴高/🟡中/🟢低 三层，每条必须三要素——对象 + 具体抓手(采购加急/库存调拨/替代料/安全库存调整参考值) + "
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_analysis_prompt.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Export from package + commit**

In `apps/chat/prompts/__init__.py`, append to the import and `__all__`:

```python
from apps.chat.prompts.analysis_prompt import (
    AnalysisPromptInput,
    build_analysis_messages,
)
```
and add `"AnalysisPromptInput"`, `"build_analysis_messages"` to `__all__`.

```bash
git add SQLBot/backend/apps/chat/prompts/analysis_prompt.py SQLBot/backend/apps/chat/prompts/__init__.py SQLBot/tests/test_analysis_prompt.py
git commit -m "feat(prompts): 模块化 analysis 报告 prompt builder（去重+强化规则+快照测试）"
```

---

### Task B2: wire builder into `chat_model.py` + real-report iteration checklist

**Files:**
- Modify: `SQLBot/backend/apps/chat/models/chat_model.py:302-308`
- Modify: `SQLBot/backend/apps/chat/prompts/__init__.py` (already exported in B1)

- [ ] **Step 1: Write a test that the question builders delegate to the new prompt**

Append to `tests/test_analysis_prompt.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_analysis_prompt.py -k "analysis_sys_user" -q`
Expected: FAIL (`assert "数据口径" in system` — old template.yaml system prompt lacks the new rule block).

- [ ] **Step 3: Delegate `analysis_sys_question`/`analysis_user_question` to the builder**

In `apps/chat/models/chat_model.py`, replace the two methods (currently at lines 302-308):

```python
    def analysis_sys_question(self):
        from apps.chat.prompts import AnalysisPromptInput, build_analysis_messages
        inp = AnalysisPromptInput(
            lang=self.lang,
            sqlbot_name=self.sqlbot_name,
            terminologies=self.terminologies,
            custom_prompt=self.custom_prompt,
            fields=self.fields,
            data=self.data,
            data_profile=self.data_profile,
        )
        return build_analysis_messages(inp)[0]["content"]

    def analysis_user_question(self):
        from apps.chat.prompts import AnalysisPromptInput, build_analysis_messages
        inp = AnalysisPromptInput(
            lang=self.lang,
            sqlbot_name=self.sqlbot_name,
            terminologies=self.terminologies,
            custom_prompt=self.custom_prompt,
            fields=self.fields,
            data=self.data,
            data_profile=self.data_profile,
        )
        return build_analysis_messages(inp)[1]["content"]
```

(Local import inside the method mirrors the existing lazy-import style and avoids any import-cycle risk with the prompts package.)

- [ ] **Step 4: Run tests to verify they pass + full regression**

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_analysis_prompt.py -q`
Expected: PASS (4 passed).

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/ -q`
Expected: all green except the known pre-existing `test_summary_json_escape_safety`.

- [ ] **Step 5: Commit**

```bash
git add SQLBot/backend/apps/chat/models/chat_model.py SQLBot/tests/test_analysis_prompt.py
git commit -m "feat(chat): analysis 报告 prompt 切换到模块化 builder（保留 template.yaml 兼容路径）"
```

- [ ] **Step 6: Real-report iteration (user-assisted, not sandbox-testable)**

Run the analysis on a real supply-chain query in the live environment and paste the generated report. Check each critique point against the new rules; tune `_RULES` wording in `analysis_prompt.py` and re-commit per adjustment. Suggested checklist (paste report, then verify):
- [ ] Report opens with a 数据口径 block (units + aliases + period).
- [ ] Every number carries a unit; totals use one main unit with 万/亿 conversion.
- [ ] 关键指标 table uses Chinese names; mixed 口径 explained in one line.
- [ ] Each 分层发现 `###` covers exactly one dimension (no 仓库+物料 mixing).
- [ ] 重点问题定位 names TOP objects with real numbers + threshold; TOP1 in the `> 🔴 TOP1` callout.
- [ ] 行动建议 has 对象+抓手+解决什么+兜底影响 for each priority.
- [ ] Terms glossed on first use; data-vintage footnote present; detail table appears once.

---

## Phase C — frontend render polish + chart-axis unit (testable core)

### Task C1: table-header no-truncate + TOP callout CSS + markdown test

**Files:**
- Modify: `SQLBot/frontend/src/style.less`
- Create: `SQLBot/frontend/src/utils/markdown.test.mjs`

- [ ] **Step 1: Write the failing node test**

Create `frontend/src/utils/markdown.test.mjs`:

```javascript
// Node-runnable test for the shared markdown renderer (run with: node --experimental-strip-types markdown.test.mjs).
import md from './markdown.ts'

let passed = 0
let failed = 0
function assert(cond, msg) {
  if (cond) { passed++ } else { failed++; console.error('FAIL:', msg) }
}

// 1. tables are wrapped in the scroll container
{
  const html = md.render('| 展望供应总量 | 供给缺口总量 |\n|---|---|\n| 1 | 2 |\n')
  assert(html.includes('md-table-wrap'), 'table wrapped in scroll container')
  assert(html.includes('<th>'), 'table has header cells')
}

// 2. TOP1 callout renders as a blockquote (CSS will style it)
{
  const html = md.render('> 🔴 TOP1：硅胶密封圈 缺口 86795 pcs（>15% 严重）\n')
  assert(html.includes('<blockquote>'), 'TOP1 callout is a blockquote')
  assert(html.includes('🔴 TOP1'), 'TOP1 marker preserved')
}

if (failed === 0) { console.log(`markdown: ${passed} passed`) } else { console.error(`markdown: ${failed} FAILED`); process.exit(1) }
```

- [ ] **Step 2: Run test to confirm it passes (renderer already produces these)**

Run (from `SQLBot/frontend`): `node --experimental-strip-types src/utils/markdown.test.mjs`
Expected: PASS (the renderer already wraps tables and renders blockquotes; this test locks the contract before CSS).

- [ ] **Step 3: Add the CSS**

In `frontend/src/style.less`, append (target the shared markdown container):

```less
// Table headers must not truncate — show the full field name (展望供应总量 / 供给缺口总量).
.md-render-container .md-table-wrap th {
  white-space: normal;
  word-break: break-word;
  min-width: 96px;
}

// TOP1 problem callout: the analysis prompt emits a blockquote starting with "🔴 TOP1".
.md-render-container .markdown-body blockquote {
  &.md-callout,
  > p:first-child {
    // highlight when the blockquote opens with the TOP1 marker
  }
}
.md-render-container .markdown-body blockquote {
  border-left: 4px solid #f56c6c;
  background: #fef0f0;
  padding: 8px 12px;
  border-radius: 4px;
  margin: 8px 0;
}
```

(Note: the blockquote highlight is applied to all analysis-report blockquotes since the prompt uses blockquotes specifically for the TOP callout; if blockquotes appear elsewhere, narrow the selector to `blockquote:has(strong)` at execution time during visual verification.)

- [ ] **Step 4: Re-run node test + type-check**

Run: `node --experimental-strip-types src/utils/markdown.test.mjs` → PASS.
Run (from `SQLBot/frontend`): `npx vue-tsc --noEmit` → exit 0.

- [ ] **Step 5: Commit**

```bash
git add SQLBot/frontend/src/style.less SQLBot/frontend/src/utils/markdown.test.mjs
git commit -m "style(frontend): 表头不截断 + TOP1 callout 高亮 + markdown 渲染契约测试"
```

---

### Task C2: chart-axis unit helper + stamp unit on chart config

**Files:**
- Create: `SQLBot/frontend/src/utils/chartAxis.ts`
- Create: `SQLBot/frontend/src/utils/chartAxis.test.mjs`
- Modify: `SQLBot/backend/apps/chat/data_profile.py` (`enrich_chart_config`)

- [ ] **Step 1: Write the failing node test**

Create `frontend/src/utils/chartAxis.test.mjs`:

```javascript
// Node-runnable test for chart axis unit formatting (run with: node --experimental-strip-types chartAxis.test.mjs).
import { formatAxisWithUnit } from './chartAxis.ts'

let passed = 0
let failed = 0
function assert(cond, msg) { if (cond) { passed++ } else { failed++; console.error('FAIL:', msg) } }

assert(formatAxisWithUnit(86795, 'pcs') === '86795 pcs', 'count keeps unit')
assert(formatAxisWithUnit(8216389, '元') === '821.64 万元', 'currency scales to 万 with unit')
assert(formatAxisWithUnit(0.12, '%') === '12 %', 'percent shown with %')
assert(formatAxisWithUnit(5, '') === '5', 'no unit → raw')
assert(formatAxisWithUnit(null, 'pcs') === '', 'null → empty')

if (failed === 0) { console.log(`chartAxis: ${passed} passed`) } else { console.error(`chartAxis: ${failed} FAILED`); process.exit(1) }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --experimental-strip-types src/utils/chartAxis.test.mjs`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the helper**

Create `frontend/src/utils/chartAxis.ts`:

```typescript
// Pure helper: format an axis tick value with its inferred unit.
// Currency (元) collapses large numbers to 万/亿 so axis ticks stay readable.
// Used by the chart engine's axisLabel.formatter once wired in (browser-verified follow-up).
export function formatAxisWithUnit(value: number | string | null | undefined, unit: string | undefined): string {
  if (value === null || value === undefined || value === '') return ''
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return String(value)
  const u = unit || ''
  if (u === '元') {
    const abs = Math.abs(n)
    if (abs >= 1e8) return `${(n / 1e8).toFixed(2)} 亿元`
    if (abs >= 1e4) return `${(n / 1e4).toFixed(2)} 万元`
    return `${n} 元`
  }
  if (u === '%') return `${(n * 100).toFixed(0).replace(/^0$/, '0')} %`
  return u ? `${n} ${u}` : `${n}`
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --experimental-strip-types src/utils/chartAxis.test.mjs`
Expected: PASS (5 passed).

- [ ] **Step 5: Stamp `unit` onto the chart y-axis config (backend)**

In `apps/chat/data_profile.py`, modify `enrich_chart_config(chart, profile)` so each y-axis item (and alternatives' y-axis) carries the inferred `unit` from the profile. After computing `enriched`, before `return enriched`, add:

```python
    # Stamp each metric's inferred unit onto its axis entry so the frontend can
    # label ticks (e.g. "万元", "pcs"). No value conversion — label only.
    unit_by_metric = {
        f.get("name"): f.get("unit")
        for f in (profile.get("fields", []) if profile else [])
        if isinstance(f, dict)
    }

    def _stamp_unit(axis_item):
        if not isinstance(axis_item, dict):
            return
        y = axis_item.get("y")
        items = y if isinstance(y, list) else [y] if isinstance(y, dict) else []
        for it in items:
            if isinstance(it, dict) and it.get("value") in unit_by_metric:
                u = unit_by_metric.get(it.get("value"))
                if u:
                    it["unit"] = u

    _stamp_unit(enriched.get("axis"))
    for alt in enriched.get("alternatives") or []:
        if isinstance(alt, dict):
            _stamp_unit(alt.get("axis"))
    return enriched
```

- [ ] **Step 6: Test the backend stamping + full regression**

Append to `tests/test_data_profile.py`:

```python
def test_enrich_chart_config_stamps_unit_on_y_axis():
    profile = build_data_profile(
        ["material", "amount"], [{"material": "A", "amount": 100}, {"material": "B", "amount": 200}],
    )
    chart = enrich_chart_config(
        {"type": "bar", "title": "x", "axis": {"x": {"name": "material", "value": "material"},
                                                "y": [{"name": "amount", "value": "amount"}]}},
        profile,
    )
    y_items = chart["axis"]["y"]
    assert y_items[0]["unit"] == "元"
```

Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/test_data_profile.py -k "stamp" -q` → PASS.
Run: `/home/ubuntu/miniconda3/envs/as/bin/python -m pytest tests/ -q` → green (except known pre-existing failure).

- [ ] **Step 7: Commit**

```bash
git add SQLBot/frontend/src/utils/chartAxis.ts SQLBot/frontend/src/utils/chartAxis.test.mjs SQLBot/backend/apps/chat/data_profile.py SQLBot/tests/test_data_profile.py
git commit -m "feat(chart): 轴单位格式化 helper + chart 配置注入 unit（标注不换算）"
```

---

### Task C3 (DEFERRED — browser-verified follow-up): wire unit formatter + color palette into the chart engine

**Not in sandbox-executable scope.** Rationale: the axis `axisLabel.formatter` and series color mapping live inside `ChartComponent.vue`'s chart engine (no `axisLabel`/`setOption`/`yAxis` symbols in the `.vue` file — it delegates to a deeper engine not mapped without a live browser). The spec assigns visual verification to the user's machine.

When executing against the live browser:
1. Read `frontend/src/views/chat/component/ChartComponent.vue` and the chart engine it imports; locate the axis option builder.
2. Set the y-axis `axisLabel.formatter` to call `formatAxisWithUnit(value, axisItem.unit)` (unit now present on each y-axis item from Task C2).
3. Replace the single-hue bar/column series with a high/mid/low color scale driven by the value relative to the metric's `distribution` bands (from Phase A); TOP1 bar gets an accent color.
4. Verify visually: 缺口排名 bar chart shows material names (from `top_values.label`) on the axis with `pcs`/`万元` suffix; high-gap bars are visually distinct from low-gap bars.

This is a follow-up plan, not a step with placeholder code.

---

## Self-Review

**1. Spec coverage:**
- §4.1 unit/scale_hint → Task A1 ✓
- §4.2 alias → Task A2 ✓
- §4.3 distribution → Task A3 ✓
- §4.4 code→name → Task A4 ✓
- §5 modular builder + 8 rules → Task B1 ✓ ; wiring → Task B2 ✓
- §6.1 table-header CSS → Task C1 ✓
- §6.2 TOP callout → Task C1 (CSS) + B1 (prompt emits `> 🔴 TOP1`) ✓
- §6.3 chart axis unit → Task C2 (helper + config stamp) ✓ ; **engine wiring + color → Task C3 deferred** (explicit boundary, browser-verified)
- §6.4 dedupe → B1 rule ("明细表只出现一次") + investigate at real-report iteration ✓
- §7 testing → each task TDD ✓
- §8 risks mitigated (label-not-convert, conservative name-pairing, rule tuning via real reports) ✓

**2. Placeholder scan:** No TBD/TODO. Task C3 is an explicit deferral with rationale, not a placeholder — it names exactly what to do and why it's out of sandbox scope.

**3. Type/name consistency:**
- `unit`, `scale_hint`, `alias`, `distribution`, `label`, `metric_values` — defined in Phase A, consumed in Phase B (`_RULES` references `alias`/`unit`/`scale_hint`/`distribution`/`top_values.label`/`metric_values`) and Phase C (`enrich_chart_config` reads `unit`). ✓
- `AnalysisPromptInput` fields (`lang`, `sqlbot_name`, `terminologies`, `custom_prompt`, `fields`, `data`, `data_profile`) match B1 definition and B2 wiring. ✓
- `formatAxisWithUnit(value, unit)` signature consistent across C2 test and helper. ✓

---

## Execution Handoff

Plan complete and saved to `SQLBot/docs/superpowers/plans/2026-06-23-report-quality.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
