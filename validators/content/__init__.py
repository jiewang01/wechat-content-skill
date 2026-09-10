"""Content QA v1（蓝图 9.1）：结构完整性 / 字数 / AI 味复检 / 引用 ID 一致性。"""

from validators.content.qa import lint_content

__all__ = ["lint_content"]
