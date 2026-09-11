"""微信集成层：官方 API 客户端 + token 管理 + 发布 Facade（蓝图十三章，M5 / N2）。

上层一律通过 WeChatPublisher.create_draft(doc) / release(draft_id) 访问（蓝图十三章），
不直接触碰 access_token / media_id / thumb_media_id / publish_id 等微信细节。
"""

from __future__ import annotations

from .auth import TokenManager, call_with_token_retry
from .client import WeChatClient
from .draft import DraftService
from .freepublish import FreepublishService, FreepublishStatus
from .media import MediaService, UploadedMedia
from .publish import WeChatPublisher

__all__ = [
    "DraftService",
    "FreepublishService",
    "FreepublishStatus",
    "MediaService",
    "TokenManager",
    "UploadedMedia",
    "WeChatClient",
    "WeChatPublisher",
    "call_with_token_retry",
]
