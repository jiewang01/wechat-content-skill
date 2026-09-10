"""微信集成层：官方 API 客户端 + token 管理 + 发布 Facade（蓝图十三章，计划 M5-T4/T5/T6）。

上层一律通过 WeChatPublisher.create_draft(doc) 访问（蓝图十三章），
不直接触碰 access_token / media_id / thumb_media_id 等微信细节。
"""

from __future__ import annotations

from .auth import TokenManager, call_with_token_retry
from .client import WeChatClient
from .draft import DraftService
from .media import MediaService, UploadedMedia
from .publish import WeChatPublisher

__all__ = [
    "DraftService",
    "MediaService",
    "TokenManager",
    "UploadedMedia",
    "WeChatClient",
    "WeChatPublisher",
    "call_with_token_retry",
]
