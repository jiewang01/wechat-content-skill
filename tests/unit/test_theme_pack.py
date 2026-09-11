"""主题包测试：5 个内置主题全部可加载、可渲染、通过三层渲染门，且视觉互异。

对应 v0.2 计划 N1-T5 的 DoD：
- load_theme("<name>") 成功；
- 全组件渲染 HTML 通过 lint_html + lint_gzh。
"""

import re

import pytest

from renderer.ast import parse
from renderer.html import HtmlRenderer
from renderer.themes import THEMES_DIR, load_theme
from validators.html.checks import lint_html
from validators.wechat.gzh import lint_gzh

BUILTIN_THEMES = ("default", "editorial", "minimal", "tech", "magazine")

DOC = """# 标题一

普通段落，含 **加粗**、*斜体*、`code` 与 [链接](https://example.com)。

:::note
说明文字。
:::

:::quote cite="张三"
原话内容。
:::

:::callout type="info" title="信息"
信息正文。
:::

:::callout type="warning" title="注意"
警告正文。
:::

:::callout type="tip" title="提示"
提示正文。
:::

:::callout type="danger" title="危险"
危险正文。
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


@pytest.mark.parametrize("theme_name", BUILTIN_THEMES)
def test_theme_loads_and_renders_all_components(theme_name: str):
    theme = load_theme(theme_name)
    html = HtmlRenderer(theme).render(parse(DOC))

    assert html, f"主题 {theme_name} 渲染输出为空"
    assert "要点卡" in html and "原话内容。" in html
    assert "信息正文。" in html and "危险正文。" in html
    assert "x = 1" in html and "步骤一" in html


@pytest.mark.parametrize("theme_name", BUILTIN_THEMES)
def test_theme_passes_render_gates(theme_name: str):
    html = HtmlRenderer(load_theme(theme_name)).render(parse(DOC))

    html_issues = lint_html(html)
    assert not html_issues, f"主题 {theme_name} 未通过 HTML 门：{html_issues}"
    gzh_issues = lint_gzh(html)
    assert not gzh_issues, f"主题 {theme_name} 未通过公众号门：{gzh_issues}"


@pytest.mark.parametrize("theme_name", BUILTIN_THEMES)
def test_theme_tag_whitelist(theme_name: str):
    html = HtmlRenderer(load_theme(theme_name)).render(parse(DOC))
    tags = {t.lstrip("/") for t in re.findall(r"</?([a-zA-Z]+)", html)}
    assert tags <= {"section", "span", "strong", "em", "img"}


def test_all_themes_visually_distinct():
    outputs = [HtmlRenderer(load_theme(name)).render(parse(DOC)) for name in BUILTIN_THEMES]
    assert len(set(outputs)) == len(BUILTIN_THEMES), "各主题渲染结果应互不相同"


def test_builtin_theme_dirs_discovered():
    available = sorted(d.name for d in THEMES_DIR.iterdir() if d.is_dir())
    for name in BUILTIN_THEMES:
        assert name in available
