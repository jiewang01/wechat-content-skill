"""HTML 通用检查（蓝图 9.3）：标签白名单 / 属性 / 结构 / CSS 白名单 / 空节点。"""

from validators.html.checks import (
    ALLOWED_CSS_PROPS,
    ALLOWED_TAGS,
    RESTRICTED_CSS_VALUES,
    lint_html,
)

__all__ = ["ALLOWED_CSS_PROPS", "ALLOWED_TAGS", "RESTRICTED_CSS_VALUES", "lint_html"]
