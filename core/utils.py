"""跨阶段共享的纯工具函数。"""

from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*")


def estimate_word_count(text: str) -> int:
    """混合字数统计：每个 CJK 字符计 1，每个西文单词计 1。"""
    if not text:
        return 0
    return len(_CJK_RE.findall(text)) + len(_LATIN_WORD_RE.findall(text))
