"""渲染器单测：微信安全白名单、禁用模式、主题驱动样式、纯文本降级、确定性。"""

import re
import shutil

import pytest
import yaml

from renderer.ast import parse
from renderer.html import HtmlRenderer
from renderer.themes import THEMES_DIR, ThemeError, load_theme
from validators import lint_gzh, lint_html

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


def test_tag_whitelist(rendered: str):
    tags = {t.lstrip("/") for t in re.findall(r"</?([a-zA-Z]+)", rendered)}
    assert tags <= {"section", "span", "strong", "em", "img"}


def test_forbidden_patterns_absent(rendered: str):
    forbidden = ("<div", "<style", "<script", "<br", "<hr", "<a ", "class=", "id=", "javascript:")
    for pattern in forbidden:
        assert pattern not in rendered


def test_output_is_deterministic():
    renderer = HtmlRenderer()
    ast = parse(DOC)
    assert renderer.render(ast) == renderer.render(ast)


def test_root_section_carries_body_styles(rendered: str):
    assert rendered.startswith('<section style="')
    assert "font-size:" in rendered
    assert "line-height:" in rendered
    assert "word-break:" in rendered


def test_inline_markdown_conversion(rendered: str):
    assert '<strong style="color:#07c160;">加粗</strong>' in rendered
    assert "<em>斜体</em>" in rendered
    assert "链接（https://example.com）" in rendered
    assert rendered.count("<span") >= 1


def test_html_escaping():
    ast = parse('<script>alert("x")</script> 与 & 符号')
    out = HtmlRenderer().render(ast)
    assert "<script" not in out
    assert "&lt;script&gt;" in out
    assert "&amp;" in out


def test_hr_is_background_section_not_hr_tag(rendered: str):
    assert "<hr" not in rendered
    assert "text-align:center" in rendered
    assert "display:inline-block" in rendered
    assert "background:#07c160" in rendered
    assert "width:60px" in rendered
    assert "height:4px" in rendered


def test_strong_border_radius_has_px_unit():
    theme = load_theme("orange-heart")
    html = HtmlRenderer(theme).render(parse("正文 **加粗** 一处。"))
    assert "border-radius:3px" in html
    assert "border-radius:3;" not in html


def test_code_block_uses_pre_wrap_without_br(rendered: str):
    assert "white-space:pre-wrap" in rendered
    assert "x = 1\ny = 2" in rendered
    assert "<br" not in rendered


def test_image_inline_styles(rendered: str):
    assert '<img src="https://example.com/i.png"' in rendered
    assert "max-width:" in rendered


def test_list_markers_rendered(rendered: str):
    assert "•" in rendered
    assert "1." in rendered and "2." in rendered


def test_include_title_flag():
    ast = parse("正文。", title="独特标题甲乙丙")
    without = HtmlRenderer().render(ast)
    with_title = HtmlRenderer().render(ast, include_title=True)
    assert "独特标题甲乙丙" not in without
    assert "独特标题甲乙丙" in with_title


def test_plain_text_degradation():
    plain = HtmlRenderer().render_plain_text(parse(DOC))
    assert "<" not in plain
    assert "[" not in plain and "**" not in plain and "`" not in plain
    assert "加粗" in plain and "链接" in plain
    assert "—— 张三" in plain
    assert "注意" in plain and "警告正文。" in plain
    assert "- 要点一" in plain and "要点二" in plain
    assert "步骤一" in plain


NESTED_DOC = """:::card title="嵌套要点卡" footer="完"
- 文本要点一
:::note
嵌套说明内容。
:::
:::quote cite="嵌套引用人"
嵌套原话内容。
:::
:::callout type="warning" title="嵌套注意"
嵌套警示正文。
:::
- 文本要点二
:::
"""


def test_nested_card_children_rendered_inline():
    out = HtmlRenderer().render(parse(NESTED_DOC))
    assert "嵌套说明内容。" in out
    assert "嵌套原话内容。" in out
    assert "嵌套注意" in out and "嵌套警示正文。" in out
    assert "文本要点一" in out and "文本要点二" in out


def test_nested_render_passes_html_and_gzh_gates():
    html = HtmlRenderer().render(parse(NESTED_DOC))
    assert [issue for issue in lint_html(html) if issue.severity == "error"] == []
    assert [issue for issue in lint_gzh(html) if issue.severity == "error"] == []


def test_render_segments_keeps_top_level_granularity_for_nested_card():
    """嵌套子节点 HTML 并入父段 —— 修复循环按顶层段定位（v0.3 N1-T7）。"""
    segments = HtmlRenderer().render_segments(parse(NESTED_DOC))
    assert [node_id for node_id, _ in segments] == ["component_1"]
    assert "嵌套说明内容。" in segments[0][1]
    assert "嵌套警示正文。" in segments[0][1]


def test_plain_text_unrolls_nested_children():
    plain = HtmlRenderer().render_plain_text(parse(NESTED_DOC))
    assert "<" not in plain
    assert "- 文本要点一" in plain and "- 文本要点二" in plain
    assert "嵌套说明内容。" in plain
    assert "—— 嵌套引用人" in plain
    assert "嵌套注意" in plain and "嵌套警示正文。" in plain


def test_callout_variants_render_distinctly():
    renderer = HtmlRenderer()
    outputs = []
    for variant in ("info", "warning", "tip", "danger"):
        ast = parse(f':::callout type="{variant}" title="标题{variant}"\n正文{variant}。\n:::')
        out = renderer.render(ast)
        assert f"标题{variant}" in out
        assert f"正文{variant}。" in out
        outputs.append(out)
    assert len(set(outputs)) == 4


FIGURE_DOC = """# 标题

正文段落。

:::figure
「上升趋势」概念插画：登山者立于山脊远眺日出。现代扁平概念插画，干净的几何构图与柔和渐变，横构图（16:9）。低饱和中性色调，以主题色 #ef7060 为点缀。画面中不出现任何文字、无水印、无 logo。
:::
"""


def test_figure_renders_placeholder_card():
    html = HtmlRenderer().render(parse(FIGURE_DOC))
    assert "配图 · 生图提示词" in html
    assert "登山者立于山脊远眺日出" in html
    assert ":::figure" not in html


def test_figure_passes_html_and_gzh_gates():
    html = HtmlRenderer().render(parse(FIGURE_DOC))
    assert [issue for issue in lint_html(html) if issue.severity == "error"] == []
    assert [issue for issue in lint_gzh(html) if issue.severity == "error"] == []


def test_figure_prompt_keeps_markup_literal():
    doc = ":::figure\nprompt 含 **加粗记号** 与 `代码记号`，必须字面呈现。\n:::"
    html = HtmlRenderer().render(parse(f"# 标题\n\n{doc}"))
    assert "**加粗记号**" in html
    assert "`代码记号`" in html


def test_figure_plain_text_keeps_prompt():
    plain = HtmlRenderer().render_plain_text(parse(FIGURE_DOC))
    assert "<" not in plain
    assert "登山者立于山脊远眺日出" in plain


def test_unknown_theme_raises():
    with pytest.raises(ThemeError):
        load_theme("no-such-theme")


def test_custom_theme_changes_styles_without_code(tmp_path):
    shutil.copytree(THEMES_DIR / "default", tmp_path / "custom")
    typo = tmp_path / "custom" / "typography.yaml"
    data = yaml.safe_load(typo.read_text(encoding="utf-8"))
    data.setdefault("h1", {})["color"] = "#123456"
    typo.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    theme = load_theme("custom", themes_dir=tmp_path)
    out = HtmlRenderer(theme).render(parse("# 大标题\n\n正文。"))
    assert "#123456" in out


def test_theme_with_disabled_required_component_raises(tmp_path):
    shutil.copytree(THEMES_DIR / "default", tmp_path / "broken")
    theme_yaml = tmp_path / "broken" / "theme.yaml"
    data = yaml.safe_load(theme_yaml.read_text(encoding="utf-8"))
    data["components"]["note"] = False
    theme_yaml.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ThemeError, match="未启用必需组件"):
        load_theme("broken", themes_dir=tmp_path)
