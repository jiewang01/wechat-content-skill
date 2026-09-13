"""发布数据统计：datacube getarticletotaldetail 封装（蓝图十三章，v0.3 计划 N2-T1/T2）。

微信 getarticletotaldetail 语义（v0.3 计划「接口要点」）：
- POST，body {begin_date, end_date}（YYYY-MM-DD）；仅支持 1 天跨度（begin = end），
  end_date 最大昨日；错误码 61500（日期格式）/ 61501（范围超限）；
- 返回当日统计窗口内的全部群发文章：ref_date / msgid / publish_type / title /
  content_url / is_delay / detail_list[]；detail_list[] 按 stat_date 逐日展开
  （每篇文章统计其发表日起 30 天）；
- 仅认证账号可用；数据自 2025-11-01 起存储。

查询型能力不进 pipeline 状态机：上层经 DatacubeService 拉取、scripts/stats.py 留档。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from integrations.errors import ProviderError

from .auth import TokenManager, call_with_token_retry
from .client import WeChatClient

DATACUBE_ARTICLE_TOTAL_DETAIL_PATH = "cgi-bin/datacube/getarticletotaldetail"

DATA_START_DATE = datetime.date(2025, 11, 1)

_ERRCODE_MESSAGES = {
    61500: "日期格式错误（需补零的 YYYY-MM-DD）",
    61501: "日期范围错误（仅支持 1 天跨度，最早 2025-11-01，最晚昨日）",
}


@dataclass(frozen=True)
class ReadSource:
    """read_user_source[] 元素：某一阅读来源的人数（type 为微信来源码，保持原值）。"""

    type: int
    value: int


@dataclass(frozen=True)
class JumpPosition:
    """read_jump_position[] 元素：position 1–5 对应 0–20% … 80–100% 跳出位置。"""

    position: int
    rate: float


@dataclass(frozen=True)
class ArticleDailyDetail:
    """detail_list[] 元素：一篇文章某统计日（stat_date）的明细指标。

    read_avg_activetime 单位为分钟；read_delivery_rate / read_finish_rate / rate
    保持微信原始数值口径。
    """

    stat_date: str
    read_user: int
    share_user: int
    zaikan_user: int
    like_user: int
    comment_count: int
    collection_user: int
    praise_money: int
    read_subscribe_user: int
    read_delivery_rate: float
    read_finish_rate: float
    read_avg_activetime: float
    read_user_source: tuple[ReadSource, ...] = ()
    read_jump_position: tuple[JumpPosition, ...] = ()


@dataclass(frozen=True)
class ArticleTotalDetail:
    """一篇文章在查询日的全量数据：msgid 格式为 msg_data_id_index。"""

    ref_date: str
    msgid: str
    title: str
    content_url: str
    publish_type: int = -1
    is_delay: int = 0
    detail_list: tuple[ArticleDailyDetail, ...] = ()

    @property
    def msg_data_id(self) -> str:
        """msgid（msg_data_id_index）中的群发消息 id 部分。"""
        if "_" not in self.msgid:
            return self.msgid
        return self.msgid.rsplit("_", 1)[0]

    @property
    def msg_index(self) -> int:
        """文章在群发消息内的序号；msgid 不带下标时视为头条（1）。"""
        if "_" not in self.msgid:
            return 1
        try:
            return int(self.msgid.rsplit("_", 1)[1])
        except ValueError:
            return 1

    @property
    def notified_subscribers(self) -> bool:
        """publish_type=0 已通知订阅用户；1 未开启通知。"""
        return self.publish_type == 0


def _read_sources(raw: list | None) -> tuple[ReadSource, ...]:
    return tuple(
        ReadSource(type=int(item.get("type", 0)), value=int(item.get("value", 0)))
        for item in raw or []
    )


def _jump_positions(raw: list | None) -> tuple[JumpPosition, ...]:
    return tuple(
        JumpPosition(position=int(item.get("position", 0)), rate=float(item.get("rate", 0.0)))
        for item in raw or []
    )


def _daily_from_response(entry: dict) -> ArticleDailyDetail:
    return ArticleDailyDetail(
        stat_date=str(entry.get("stat_date", "")),
        read_user=int(entry.get("read_user", 0)),
        share_user=int(entry.get("share_user", 0)),
        zaikan_user=int(entry.get("zaikan_user", 0)),
        like_user=int(entry.get("like_user", 0)),
        comment_count=int(entry.get("comment_count", 0)),
        collection_user=int(entry.get("collection_user", 0)),
        praise_money=int(entry.get("praise_money", 0)),
        read_subscribe_user=int(entry.get("read_subscribe_user", 0)),
        read_delivery_rate=float(entry.get("read_delivery_rate", 0.0)),
        read_finish_rate=float(entry.get("read_finish_rate", 0.0)),
        read_avg_activetime=float(entry.get("read_avg_activetime", 0.0)),
        read_user_source=_read_sources(entry.get("read_user_source")),
        read_jump_position=_jump_positions(entry.get("read_jump_position")),
    )


def _article_from_response(item: dict) -> ArticleTotalDetail:
    return ArticleTotalDetail(
        ref_date=str(item.get("ref_date", "")),
        msgid=str(item.get("msgid", "")),
        title=str(item.get("title", "")),
        content_url=str(item.get("content_url", "")),
        publish_type=int(item.get("publish_type", -1)),
        is_delay=int(item.get("is_delay", 0)),
        detail_list=tuple(
            _daily_from_response(entry) for entry in item.get("detail_list") or []
        ),
    )


def _parse_date(date: str) -> datetime.date:
    """严格解析 YYYY-MM-DD：strptime 宽松匹配后用 isoformat 回比对锁死补零格式。"""
    try:
        parsed = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ProviderError(f"日期格式错误（需补零的 YYYY-MM-DD，date={date!r}）") from exc
    if parsed.isoformat() != date:
        raise ProviderError(f"日期格式错误（需补零的 YYYY-MM-DD，date={date!r}）")
    return parsed


def _check_stats_date(date: str) -> None:
    """客户端预检：格式合法且不晚于昨日（end_date 最大昨日），免去注定失败的网络请求。"""
    parsed = _parse_date(date)
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    if parsed > yesterday:
        raise ProviderError(
            f"日期超出可查询范围（date={date}）：end_date 最大昨日（{yesterday.isoformat()}），"
            "请改用昨日或更早日期"
        )


class DatacubeService:
    """蓝图十三章查询型 Service：某日群发文章的阅读 / 分享 / 互动全量数据。"""

    def __init__(self, client: WeChatClient, tokens: TokenManager) -> None:
        self._client = client
        self._tokens = tokens

    def article_stats(self, date: str) -> tuple[ArticleTotalDetail, ...]:
        """拉取 date 当日的群发文章统计（begin = end = date，仅 1 天跨度）。"""

        _check_stats_date(date)

        def _do() -> tuple[ArticleTotalDetail, ...]:
            token = self._tokens.get_token()
            try:
                response = self._client.post(
                    DATACUBE_ARTICLE_TOTAL_DETAIL_PATH,
                    params={"access_token": token},
                    json={"begin_date": date, "end_date": date},
                )
            except ProviderError as exc:
                hint = _ERRCODE_MESSAGES.get(exc.errcode)
                if hint is not None:
                    raise ProviderError(
                        f"微信数据统计失败：{hint}（date={date}）：{exc}",
                        errcode=exc.errcode,
                    ) from exc
                raise
            items = response.get("list", []) if isinstance(response, dict) else response
            return tuple(_article_from_response(item) for item in items or [])

        return call_with_token_retry(self._tokens, _do)
