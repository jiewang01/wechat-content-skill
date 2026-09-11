"""正式发布：草稿箱文章提交 freepublish 群发并查询发布状态（蓝图十三章，计划 N2-T2）。

微信 freepublish 语义（publish_state）：
- 0：发布成功（article_detail.item[].article_url 为正式文章链接）；
- 1：发布过程中失败（审核失败）；2：原创申明失败；3：常见错误（原文章已删除等）；
- 4：发布中（异步任务，需轮询直至终态）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from integrations.errors import ProviderError

from .auth import TokenManager, call_with_token_retry
from .client import WeChatClient

FREEPUBLISH_SUBMIT_PATH = "cgi-bin/freepublish/submit"
FREEPUBLISH_GET_PATH = "cgi-bin/freepublish/get"

STATE_SUCCESS = 0
STATE_IN_PROGRESS = 4

_STATE_MESSAGES = {
    1: "发布过程中失败（审核未通过）",
    2: "原创申明失败",
    3: "常见错误（发布任务异常或原文章已删除）",
}


@dataclass(frozen=True)
class FreepublishStatus:
    """freepublish/get 的结构化结果：上层不触碰微信原始 JSON。"""

    publish_id: str
    state: int
    article_id: str = ""
    article_url: str = ""
    fail_idx: int = -1

    @property
    def success(self) -> bool:
        return self.state == STATE_SUCCESS

    @property
    def in_progress(self) -> bool:
        return self.state == STATE_IN_PROGRESS

    @property
    def message(self) -> str:
        if self.success:
            return "发布成功"
        if self.in_progress:
            return "发布中"
        if self.fail_idx >= 0:
            reason = _STATE_MESSAGES.get(self.state, "发布失败")
            return f"{reason}（失败文章 index={self.fail_idx}）"
        return _STATE_MESSAGES.get(self.state, f"发布失败（publish_state={self.state}）")


def _status_from_response(publish_id: str, response: dict) -> FreepublishStatus:
    state = int(response.get("publish_state", -1))
    detail = response.get("article_detail") or {}
    items = detail.get("item") or []
    article_url = str(items[0].get("article_url", "")) if items else ""
    return FreepublishStatus(
        publish_id=publish_id,
        state=state,
        article_id=str(response.get("article_id", "")),
        article_url=article_url,
        fail_idx=int(response.get("fail_idx", -1)),
    )


class FreepublishService:
    """蓝图十三章 FreepublishService 角色：草稿 media_id → 发布任务 → 终态。"""

    def __init__(self, client: WeChatClient, tokens: TokenManager) -> None:
        self._client = client
        self._tokens = tokens

    def submit(self, draft_media_id: str) -> str:
        """把草稿箱文章提交群发，返回 publish_id（异步发布任务句柄）。"""

        def _do() -> str:
            token = self._tokens.get_token()
            response = self._client.post(
                FREEPUBLISH_SUBMIT_PATH,
                params={"access_token": token},
                json={"media_id": draft_media_id},
            )
            publish_id = response.get("publish_id", "")
            if not publish_id:
                raise ProviderError("微信发布响应缺少 publish_id")
            return str(publish_id)

        return call_with_token_retry(self._tokens, _do)

    def status(self, publish_id: str) -> FreepublishStatus:
        """查询发布任务状态；publish_state=4 表示仍在异步发布中。"""

        def _do() -> FreepublishStatus:
            token = self._tokens.get_token()
            response = self._client.post(
                FREEPUBLISH_GET_PATH,
                params={"access_token": token},
                json={"publish_id": publish_id},
            )
            return _status_from_response(publish_id, response)

        return call_with_token_retry(self._tokens, _do)

    def wait(
        self,
        publish_id: str,
        *,
        max_polls: int = 10,
        poll_interval: float = 1.0,
        sleep=time.sleep,
    ) -> FreepublishStatus:
        """轮询直至终态；超时返回最后一次仍为发布中的状态（调用方按降级处理）。"""
        status = self.status(publish_id)
        polls = 0
        while status.in_progress and polls < max_polls:
            sleep(poll_interval)
            status = self.status(publish_id)
            polls += 1
        return status
