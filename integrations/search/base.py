"""Search Provider 接口层：命中模型 + 降级结果契约 + Provider 协议（蓝图十二章）。"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str = ""
    snippet: str = ""


class SearchOutcome(BaseModel):
    """搜索结果 + 降级标记：degraded=True 时上层复用既有 sources 继续（蓝图十二章）。"""

    model_config = ConfigDict(extra="forbid")

    hits: list[SearchHit] = Field(default_factory=list)
    degraded: bool = False
    reason: str = ""


class SearchProvider(Protocol):
    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]: ...
