"""微信公众号平台约束检查（蓝图 9.3）：图片 / 外部资源 / HTML 体积。"""

from validators.wechat.gzh import DEFAULT_MAX_HTML_BYTES, lint_gzh

__all__ = ["DEFAULT_MAX_HTML_BYTES", "lint_gzh"]
