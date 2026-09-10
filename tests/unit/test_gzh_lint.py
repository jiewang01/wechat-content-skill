"""公众号平台约束单测（蓝图 9.3 GZH 侧）：五项检查各有正反用例 + 组合器契约。"""

from __future__ import annotations

import pytest

from renderer.ast import parse
from renderer.html import HtmlRenderer
from validators import validate_wechat_html
from validators.html import lint_html
from validators.wechat import DEFAULT_MAX_HTML_BYTES, lint_gzh

DOC = """# 标题一

普通段落，含 **加粗** 与 [链接](https://example.com)。

:::note
说明文字。
:::

![配图](https://example.com/i.png)

- 项目甲
- 项目乙
"""

GOOD_IMG = (
    '<img src="https://mmbiz.qpic.cn/a.png" alt="图" '
    'style="width:100%;max-width:100%;margin-top:8px;margin-bottom:8px;" />'
)


@pytest.fixture()
def rendered() -> str:
    return HtmlRenderer().render(parse(DOC))


def test_renderer_output_with_image_passes(rendered: str):
    """锚定：渲染器产出（https 图 + width 声明）经平台层检查零误报。"""
    assert lint_gzh(rendered) == []


def test_good_image_clean():
    assert lint_gzh(f"<section>{GOOD_IMG}</section>") == []


@pytest.mark.parametrize(
    ("html", "error_type"),
    [
        ('<section><img alt="图" style="width:100%;" /></section>', "broken_image"),
        ('<section><img src="" alt="图" style="width:100%;" /></section>', "broken_image"),
        (
            '<section><img src="http://example.com/i.png" alt="图" '
            'style="width:100%;" /></section>',
            "insecure_image_url",
        ),
        (
            '<section><img src="/static/i.png" alt="图" style="width:100%;" /></section>',
            "insecure_image_url",
        ),
        (
            '<section><img src="https://mmbiz.qpic.cn/a.png" alt="图" '
            'style="color:#333;" /></section>',
            "missing_image_dimensions",
        ),
    ],
)
def test_image_violations(html, error_type):
    issues = lint_gzh(html)
    assert [i.type for i in issues] == [error_type]


def test_insecure_image_url_carries_full_src():
    issues = lint_gzh('<section><img src="http://a.com/i.png" style="width:1px;" /></section>')
    assert issues[0].property == "http://a.com/i.png"


@pytest.mark.parametrize(
    "tag",
    ["script", "iframe", "embed", "object", "video", "audio", "source", "track", "link"],
)
def test_external_resource_tags(tag):
    issues = lint_gzh(f"<{tag} src='https://x/y'></{tag}>")
    assert [i.type for i in issues] == ["external_resource"]
    assert tag in issues[0].message


def test_external_resource_url_in_style():
    html = '<section style="background: url( https://x/b.png )">内容</section>'
    issues = lint_gzh(html)
    assert [i.type for i in issues] == ["external_resource"]
    assert "url()" in issues[0].message


def test_plain_background_color_allowed():
    assert lint_gzh('<section style="background:#f7f7f7">内容</section>') == []


def test_html_too_large_custom_limit():
    issues = lint_gzh("<section>内容</section>", max_bytes=10)
    assert [i.type for i in issues] == ["html_too_large"]
    assert "25 字节" in issues[0].message


def test_html_too_large_default_limit_constant():
    assert DEFAULT_MAX_HTML_BYTES == 1_000_000


def test_size_uses_utf8_bytes():
    issues = lint_gzh("<section>中文内容</section>", max_bytes=20)
    assert [i.type for i in issues] == ["html_too_large"]


def test_validate_wechat_html_combines_both_layers():
    html = '<div><img src="http://a.com/i.png"></div>'
    assert validate_wechat_html(html) == lint_html(html) + lint_gzh(html)


def test_full_pipeline_clean_via_combiner(rendered: str):
    """端到端锚定：渲染器产出经九项组合检查零误报（蓝图 9.3 全绿）。"""
    assert validate_wechat_html(rendered) == []
