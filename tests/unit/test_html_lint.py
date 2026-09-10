"""HTML 通用检查单测（蓝图 9.3 HTML 侧）：六项检查各有正反用例 + 渲染器锚定。

锚定测试保证 ALLOWED_CSS_PROPS 与渲染器实际发射的属性同步 ——
渲染器新增属性而白名单未跟进时，此测试立刻红。
"""

from __future__ import annotations

import pytest

from renderer.ast import parse
from renderer.html import HtmlRenderer
from validators.html import lint_html

DOC = """# 标题一

普通段落，含 **加粗**、*斜体*、`code` 与 [链接](https://example.com)。

:::note
说明文字。
:::

:::quote cite="张三"
原话内容。
:::

:::callout type="warning" title="注意"
警告正文。
:::

:::card title="要点卡" footer="完"
- 要点一
- 要点二
:::

![配图](https://example.com/i.png)

```python
x = 1
y = 2
```

- 项目甲
- 项目乙

1. 步骤一
2. 步骤二

---

> 引用块形式。
"""


@pytest.fixture()
def rendered() -> str:
    return HtmlRenderer().render(parse(DOC))


def test_renderer_output_is_clean(rendered: str):
    """锚定：渲染器产出（全部 8 类节点）经 HTML 层检查零误报。"""
    assert lint_html(rendered) == []


def test_allowed_tags_pass():
    html = (
        '<section style="color:#333;">正文 <strong>加粗</strong> '
        "<em>斜体</em> <span>片段</span></section>"
    )
    assert lint_html(html) == []


def test_forbidden_tag():
    issues = lint_html("<div>内容</div>")
    assert [i.type for i in issues] == ["forbidden_tag"]
    assert "<div>" in issues[0].message


def test_void_forbidden_tag_reports_no_structure_error():
    issues = lint_html("第一行<br>第二行")
    assert [i.type for i in issues] == ["forbidden_tag"]


@pytest.mark.parametrize("tag", ["style", "link"])
def test_style_block_tag(tag):
    if tag == "style":
        html = "<style>p { color: red; }</style>"
    else:
        html = '<link rel="stylesheet" href="x.css">'
    issues = lint_html(html)
    types = [i.type for i in issues]
    assert "style_block" in types
    assert "forbidden_tag" not in types


def test_disallowed_attribute_carries_prop():
    html = '<section class="x" id="y" onclick="a()">正文</section>'
    issues = lint_html(html)
    assert [i.type for i in issues] == ["disallowed_attribute"] * 3
    assert [i.property for i in issues] == ["class", "id", "onclick"]


def test_structure_mismatched_tags():
    issues = lint_html("<section><span>内容</section></span>")
    assert [i.type for i in issues] == ["html_structure", "html_structure"]
    assert "未闭合" in issues[0].message
    assert "多余" in issues[1].message


def test_structure_unclosed_at_eof():
    issues = lint_html("<section><span>内容")
    assert [i.type for i in issues] == ["html_structure"]
    assert "section/span" in issues[0].message


def test_structure_stray_endtag():
    issues = lint_html("内容</span>")
    assert [i.type for i in issues] == ["html_structure"]
    assert "多余" in issues[0].message


def test_img_is_void_no_structure_error():
    html = (
        '<section><img src="https://mmbiz.qpic.cn/a.png" alt="图" style="width:100%;" /></section>'
    )
    assert lint_html(html) == []


def test_unsupported_css_property():
    issues = lint_html('<section style="position:absolute">内容</section>')
    assert [i.type for i in issues] == ["unsupported_css"]
    assert issues[0].property == "position:absolute"


def test_unsupported_css_display_grid_matches_blueprint():
    """蓝图 ch10 修复循环场景：property 形如 "display:grid"。"""
    issues = lint_html('<section style="display:grid">内容</section>')
    assert [i.type for i in issues] == ["unsupported_css"]
    assert issues[0].property == "display:grid"


def test_display_block_allowed():
    assert lint_html('<section style="display:block">内容</section>') == []


def test_empty_node_detected():
    issues = lint_html("<section><span></span></section>")
    assert [i.type for i in issues] == ["empty_node"]
    assert "<span>" in issues[0].message


def test_empty_node_nested_inner_only():
    issues = lint_html("<section><span></span></section>")
    assert len(issues) == 1
    assert "span" in issues[0].message


def test_hr_single_space_section_exempt():
    """渲染器将 hr 产为带单个空格的 section —— 空白计为内容，予以豁免。"""
    html = '<section style="height:1px;background:#eee;font-size:0;line-height:0"> </section>'
    assert lint_html(html) == []


def test_self_closing_non_void_is_empty_node():
    issues = lint_html("<span/>")
    assert [i.type for i in issues] == ["empty_node"]


def test_all_issues_collected_in_one_pass():
    html = '<div class="x" style="display:grid"><span></span></div>'
    types = [i.type for i in lint_html(html)]
    assert "forbidden_tag" in types
    assert "disallowed_attribute" in types
    assert "unsupported_css" in types
    assert "empty_node" in types
