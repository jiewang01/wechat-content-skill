"""LLM Provider 接口层：消息 / 结果模型 + Provider 协议（蓝图十八章⑤）。

供应商可替换（OpenAI / Claude / Gemini / Qwen / DeepSeek …），
核心 Workflow 只依赖本模块的抽象，不 import 任何具体 SDK。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict


class LLMMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class LLMResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""
    model: str = ""
    finish_reason: str = ""


class LLMProvider(Protocol):
    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResult: ...
