"""Image Provider 接口层：图片资产模型 + Provider 协议（蓝图十八章⑤）。

source 字段记录三级降级层级（蓝图十二章）：
- generated：图片生成成功；
- search：生成失败，降级为图片搜索命中；
- placeholder：生成与搜索均不可用，使用确定性占位图。
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict


class ImageAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    source: Literal["generated", "search", "placeholder"]
    prompt: str = ""
    reason: str = ""


class ImageProvider(Protocol):
    def generate(self, prompt: str, *, size: str = "1024x1024") -> ImageAsset: ...
