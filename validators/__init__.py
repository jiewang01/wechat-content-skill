"""质量门验证器集合（蓝图 9）：component / html / wechat / content 四层。

所有验证器共用同一契约：输入文档，输出 list[ValidationIssue]（空列表 = 通过），
不抛异常 —— 与 parser 的 fail-fast 互补，供 Error Report 与修复循环消费。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from validators.component.lint import lint_components
from validators.content.qa import lint_content
from validators.html.checks import lint_html
from validators.wechat.gzh import lint_gzh

if TYPE_CHECKING:
    from core.artifacts.models import ValidationIssue


def validate_wechat_html(html: str, *, max_bytes: int | None = None) -> list[ValidationIssue]:
    """公众号 HTML 全量检查：HTML 通用层 + 平台层（蓝图 9.3 完整九项）。"""
    return lint_html(html) + lint_gzh(html, max_bytes=max_bytes)


__all__ = [
    "lint_components",
    "lint_content",
    "lint_html",
    "lint_gzh",
    "validate_wechat_html",
]
