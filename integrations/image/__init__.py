"""Image 集成层：环境变量选择供应商 + 三级降级链（蓝图十二章/十八章⑤，计划 M5-T3）。

    IMAGE_PROVIDER=openai_compat（默认）→ OpenAI 兼容图片生成网关
                                        （DALL·E / Flux / Gemini Image 兼容模式）

三级降级：生成失败 → 图片搜索 → 确定性占位图（data URI SVG，离线可用）。
- load_image_provider：严格模式，配置错误显式抛 ProviderError；
- load_fallback_image_provider：降级模式，构造失败不抛错，缺哪级跳哪级，
  最差情况返回占位图（发布流程不因外网故障中断）。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from integrations.errors import ProviderError
from integrations.search import load_search_provider

from .base import ImageAsset, ImageProvider
from .fallback import FallbackImageProvider
from .openai_compat import OpenAIImageProvider

__all__ = [
    "FallbackImageProvider",
    "ImageAsset",
    "ImageProvider",
    "OpenAIImageProvider",
    "ProviderError",
    "load_fallback_image_provider",
    "load_image_provider",
]

_REGISTRY: dict[str, Callable[[Mapping[str, str]], ImageProvider]] = {
    "openai_compat": OpenAIImageProvider.from_env,
}


def load_image_provider(env: Mapping[str, str] | None = None) -> ImageProvider:
    """按 IMAGE_PROVIDER 环境变量构造 Provider；未知名称或缺凭证抛 ProviderError。"""
    env = os.environ if env is None else env
    name = env.get("IMAGE_PROVIDER", "openai_compat")
    constructor = _REGISTRY.get(name)
    if constructor is None:
        options = "、".join(sorted(_REGISTRY))
        raise ProviderError(f"未知 IMAGE_PROVIDER：{name}（可选：{options}）")
    return constructor(env)


def load_fallback_image_provider(env: Mapping[str, str] | None = None) -> FallbackImageProvider:
    """三级降级入口：生成 → 搜索 → 占位图。构造失败不抛错，缺哪级跳哪级。"""
    env = os.environ if env is None else env
    try:
        generator = load_image_provider(env)
    except ProviderError:
        generator = None
    try:
        searcher = load_search_provider(env)
    except ProviderError:
        searcher = None
    return FallbackImageProvider(generator, searcher)
