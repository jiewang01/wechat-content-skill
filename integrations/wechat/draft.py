"""草稿创建：成品 HTML 连同封面提交公众号草稿箱（蓝图十三章 DraftService，M5-T6）。"""

from __future__ import annotations

from integrations.errors import ProviderError

from .auth import TokenManager, call_with_token_retry
from .client import WeChatClient

DRAFT_ADD_PATH = "cgi-bin/draft/add"


class DraftService:
    """蓝图十三章 DraftService 角色：一篇成稿 → 草稿箱 media_id。"""

    def __init__(self, client: WeChatClient, tokens: TokenManager) -> None:
        self._client = client
        self._tokens = tokens

    def add(
        self,
        *,
        title: str,
        html: str,
        thumb_media_id: str,
        digest: str = "",
        author: str = "",
    ) -> str:
        """在草稿箱新建一篇文章，返回草稿 media_id（后续群发 / 预览的句柄）。"""

        def _do() -> str:
            token = self._tokens.get_token()
            response = self._client.post(
                DRAFT_ADD_PATH,
                params={"access_token": token},
                json={
                    "articles": [
                        {
                            "title": title,
                            "author": author,
                            "digest": digest,
                            "content": html,
                            "thumb_media_id": thumb_media_id,
                            "show_cover_pic": 0,
                            "need_open_comment": 0,
                            "only_fans_can_comment": 0,
                        }
                    ]
                },
            )
            media_id = response.get("media_id", "")
            if not media_id:
                raise ProviderError("微信草稿响应缺少 media_id")
            return str(media_id)

        return call_with_token_retry(self._tokens, _do)
