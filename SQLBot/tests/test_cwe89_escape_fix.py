"""
Tests for the CWE-89 SQL injection fix in row_permission.py.

These tests import the production helpers directly so they fail if the real
SQL fragment construction regresses.
"""

import os
import sys
from types import SimpleNamespace


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from apps.datasource.crud import row_permission  # noqa: E402


_escape_sql_value = row_permission._escape_sql_value
_VALID_LOGIC_OPS = row_permission._VALID_LOGIC_OPS


class FakeQuery:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.value


class FakeSession:
    def __init__(self, field):
        self.field = field

    def query(self, model):
        return FakeQuery(self.field)


def _field(field_name="field", field_type="varchar"):
    return SimpleNamespace(field_name=field_name, field_type=field_type)


def _datasource(ds_type="pg"):
    return SimpleNamespace(type=ds_type)


def _filter_item(**overrides):
    item = {
        "field_id": "1",
        "type": "item",
        "filter_type": "value",
        "term": "eq",
        "value": "safe",
    }
    item.update(overrides)
    return item


class TestEscapeSqlValue:
    def test_normal_string(self):
        assert _escape_sql_value("hello") == "hello"

    def test_empty_string(self):
        assert _escape_sql_value("") == ""

    def test_numeric_string(self):
        assert _escape_sql_value("12345") == "12345"

    def test_none_returns_none(self):
        assert _escape_sql_value(None) is None

    def test_unicode_string(self):
        assert _escape_sql_value("日本語テスト") == "日本語テスト"

    def test_spaces_and_punctuation(self):
        assert _escape_sql_value("hello world! @#$%") == "hello world! @#$%"

    def test_single_quote_escaped(self):
        result = _escape_sql_value("' OR 1=1 --")
        assert result == "'' OR 1=1 --"

    def test_double_single_quotes(self):
        result = _escape_sql_value("it''s")
        assert result == "it''''s"

    def test_name_with_apostrophe(self):
        result = _escape_sql_value("O'Malley")
        assert result == "O''Malley"

    def test_backslash_escaped(self):
        result = _escape_sql_value("test\\value")
        assert result == "test\\\\value"

    def test_combined_quote_and_backslash(self):
        result = _escape_sql_value("test\\'; DROP TABLE users; --")
        assert result == "test\\\\''; DROP TABLE users; --"

    def test_union_injection(self):
        payload = "' UNION SELECT password FROM users --"
        result = _escape_sql_value(payload)
        assert result == "'' UNION SELECT password FROM users --"
        assert "'" not in result.replace("''", "")

    def test_stacked_query_injection(self):
        payload = "'; DELETE FROM users; --"
        result = _escape_sql_value(payload)
        assert result == "''; DELETE FROM users; --"

    def test_numeric_input_coerced_to_string(self):
        result = _escape_sql_value(42)
        assert result == "42"

    def test_already_escaped_quotes(self):
        result = _escape_sql_value("it''s already")
        assert result == "it''''s already"

    def test_backslash_quote_bypass_attempt(self):
        payload = "\\'"
        result = _escape_sql_value(payload)
        assert "''" in result
        assert "\\\\" in result


class TestValidLogicOps:
    def test_and_accepted(self):
        assert "AND" in _VALID_LOGIC_OPS

    def test_or_accepted(self):
        assert "OR" in _VALID_LOGIC_OPS

    def test_injection_via_logic_rejected(self):
        assert "AND 1=1) UNION SELECT" not in _VALID_LOGIC_OPS

    def test_semicolon_rejected(self):
        assert ";" not in _VALID_LOGIC_OPS

    def test_drop_rejected(self):
        assert "DROP" not in _VALID_LOGIC_OPS

    def test_empty_string_rejected(self):
        assert "" not in _VALID_LOGIC_OPS

    def test_only_two_operators(self):
        assert len(_VALID_LOGIC_OPS) == 2

    def test_case_insensitive_validation(self):
        assert "and".upper() in _VALID_LOGIC_OPS
        assert "or".upper() in _VALID_LOGIC_OPS
        assert "Or".upper() in _VALID_LOGIC_OPS

    def test_trans_tree_rejects_injected_logic(self):
        tree = {
            "logic": "AND 1=1) UNION SELECT",
            "items": [],
        }

        assert row_permission.transTreeToWhere(None, None, tree, _datasource()) is None


class TestSqlFragmentSafety:
    def test_enum_in_clause_safe(self):
        item = _filter_item(
            filter_type="enum",
            enum_value=["safe", "' OR 1=1 --", "also_safe"],
        )

        sql = row_permission.transTreeItem(
            FakeSession(_field()),
            current_user=None,
            item=item,
            ds=_datasource(),
        )

        assert "'' OR 1=1 --" in sql
        assert sql == '("field" IN (\'safe\',\'\'\' OR 1=1 --\',\'also_safe\'))'
        assert sql.count("'") % 2 == 0

    def test_like_clause_safe(self):
        item = _filter_item(term="like", value="' OR 1=1 --")

        sql = row_permission.transTreeItem(
            FakeSession(_field()),
            current_user=None,
            item=item,
            ds=_datasource(),
        )

        assert "'' OR 1=1 --" in sql
        assert sql == "\"field\" LIKE '%'' OR 1=1 --%'"
        assert sql.count("'") % 2 == 0

    def test_eq_clause_safe(self):
        item = _filter_item(term="eq", value="'; DROP TABLE users; --")

        sql = row_permission.transTreeItem(
            FakeSession(_field()),
            current_user=None,
            item=item,
            ds=_datasource(),
        )

        assert "''; DROP TABLE users; --" in sql
        assert sql == "\"field\" = '''; DROP TABLE users; --'"
        assert sql.count("'") % 2 == 0

    def test_nvarchar_enum_in_clause_safe(self):
        item = _filter_item(
            filter_type="enum",
            enum_value=["normal", "O'Brien"],
        )

        sql = row_permission.transTreeItem(
            FakeSession(_field(field_type="nvarchar")),
            current_user=None,
            item=item,
            ds=_datasource("sqlServer"),
        )

        assert "O''Brien" in sql
        assert sql == "([field] IN (N'normal',N'O''Brien'))"
        assert sql.count("'") % 2 == 0

    def test_value_in_clause_splits_commas_for_legacy_input_format(self):
        item = _filter_item(term="in", value="New York, NY")

        sql = row_permission.transTreeItem(
            FakeSession(_field()),
            current_user=None,
            item=item,
            ds=_datasource(),
        )

        assert sql == '"field" IN (\'New York\', \' NY\')'
