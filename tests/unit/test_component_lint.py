"""组件 lint 单测（蓝图 9.2）：五类错误检出 + 与 parser 编号一致 + 容错全收集。"""

from __future__ import annotations

from renderer.components.registry import COMPONENT_SPECS, ComponentSpec
from renderer.themes import Theme, load_theme
from validators.component import lint_components

CLEAN_DOC = (
    "# 标题\n\n"
    ":::note\n补充说明。\n:::\n\n"
    ':::quote cite="《指南》"\n原话引用。\n:::\n\n'
    ':::callout type="warning" title="注意"\n警示内容。\n:::\n\n'
    ':::card title="要点" footer="共 3 条"\n- 要点一\n- 要点二\n- 要点三\n:::'
)


def test_clean_document_with_default_theme_passes():
    assert lint_components(CLEAN_DOC, load_theme("default")) == []


def test_clean_document_without_theme_passes():
    assert lint_components(CLEAN_DOC) == []


def test_unknown_component_reported_with_node_id():
    issues = lint_components(":::spoiler\n内容\n:::")
    assert len(issues) == 1
    issue = issues[0]
    assert issue.type == "unknown_component"
    assert issue.node == "component_1"
    assert issue.severity == "error"
    assert "spoiler" in issue.message


def test_unsupported_attribute_carries_prop_for_targeted_repair():
    issues = lint_components(':::note foo="x"\n内容\n:::')
    assert len(issues) == 1
    assert issues[0].type == "unsupported_attribute"
    assert issues[0].node == "component_1"
    assert issues[0].property == "foo"


def test_invalid_prop_value_carries_prop():
    issues = lint_components(':::callout type="bogus"\n内容\n:::')
    assert issues[0].type == "invalid_prop_value"
    assert issues[0].property == "type"


def test_missing_required_prop_detected_via_registered_spec(monkeypatch):
    """v0.1 四组件均无必填属性，用注册表注入临时 spec 验证检出机制（H8：规则外置）。"""
    monkeypatch.setitem(
        COMPONENT_SPECS,
        "panel",
        ComponentSpec(
            name="panel",
            description="测试专用组件",
            allowed_props=frozenset({"title"}),
            required_props=frozenset({"title"}),
        ),
    )
    issues = lint_components(":::panel\n内容\n:::")
    assert len(issues) == 1
    assert issues[0].type == "missing_required_prop"
    assert issues[0].node == "component_1"
    assert issues[0].property == "title"


def test_theme_component_missing_when_disabled():
    theme = Theme(name="broken", components_enabled={"note": False}, components={"note": {}})
    issues = lint_components(":::note\n内容\n:::", theme)
    assert len(issues) == 1
    assert issues[0].type == "theme_component_missing"
    assert issues[0].node == "component_1"
    assert "未启用" in issues[0].message


def test_theme_component_missing_when_unstyled():
    theme = Theme(name="broken", components_enabled={"note": True}, components={})
    issues = lint_components(":::note\n内容\n:::", theme)
    assert len(issues) == 1
    assert issues[0].type == "theme_component_missing"
    assert "样式定义" in issues[0].message


def test_invalid_nesting_points_at_outer_component():
    issues = lint_components(":::note\n:::quote\n嵌套\n:::\n:::")
    types = [issue.type for issue in issues]
    assert types[0] == "invalid_nesting"
    assert issues[0].node == "component_1"
    assert "stray_marker" in types


def test_unclosed_marker_reported_at_eof():
    issues = lint_components("正文。\n\n:::note\n没有闭合")
    assert len(issues) == 1
    assert issues[0].type == "unclosed_marker"
    assert issues[0].node == "component_1"
    assert "第 3 行" in issues[0].message


def test_stray_closing_marker_reported():
    issues = lint_components("正文。\n\n:::")
    assert len(issues) == 1
    assert issues[0].type == "stray_marker"
    assert issues[0].node == ""
    assert "第 3 行" in issues[0].message


def test_malformed_marker_line_reported():
    issues = lint_components(":::note foo\n正文。")
    assert len(issues) == 1
    assert issues[0].type == "invalid_marker_syntax"


def test_card_body_must_be_list():
    issues = lint_components(':::card title="要点"\n- 要点一\n不是列表\n:::')
    assert len(issues) == 1
    assert issues[0].type == "invalid_card_content"
    assert issues[0].node == "component_1"
    assert "第 3 行" in issues[0].message


def test_code_fence_shields_marker_examples():
    markdown = "```markdown\n:::note\n示例写法\n:::\n```"
    assert lint_components(markdown) == []


def test_unclosed_code_block_reported():
    issues = lint_components("```python\nprint(1)")
    assert len(issues) == 1
    assert issues[0].type == "unclosed_code_block"
    assert "第 1 行" in issues[0].message


def test_all_issues_collected_in_one_pass():
    markdown = ':::spoiler\n内容\n:::\n\n正文一段。\n\n:::note bad="x"\n说明\n:::\n\n:::'
    issues = lint_components(markdown)
    assert [(issue.type, issue.node) for issue in issues] == [
        ("unknown_component", "component_1"),
        ("unsupported_attribute", "component_2"),
        ("stray_marker", ""),
    ]


def test_component_numbering_matches_parser_scheme():
    """lint 的 component_N 与 parser 分配的 id 同构 —— 修复循环可跨层定位（H3）。"""
    markdown = ':::note\n一\n:::\n\n:::quote cite="x"\n二\n:::\n\n:::callout type="bogus"\n三\n:::'
    issues = lint_components(markdown)
    assert len(issues) == 1
    assert issues[0].node == "component_3"
