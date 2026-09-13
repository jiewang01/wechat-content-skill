"""发布数据查询 CLI：datacube getarticletotaldetail → 终端摘要 + 回执留档（v0.3 计划 N2-T3）。

用法：
    python scripts/stats.py                      # 查昨日
    python scripts/stats.py --date 2025-12-01    # 查指定日（最早 2025-11-01，最晚昨日）
    python scripts/stats.py --account team-a     # 多账号（accounts/team-a.yaml）

凭据与 pipeline 同源：accounts/<account>.yaml 只存环境变量名（样例见
accounts/accounts.example.yaml），secret 一律来自环境变量。

输出：
    - stdout：人类可读摘要（每篇文章一行核心指标 + 合计行），stderr 一行状态；
    - 回执留档 outputs/stats/<date>_article_stats.json（含全量明细，重复运行幂等覆盖）。

退出码：0 = 查询成功；1 = 查询失败（日期预检拒绝 / 微信侧错误）；
2 = 环境 / 配置错误（账号配置缺失、凭据未设置）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import datetime
import json
from collections.abc import Sequence
from dataclasses import asdict

import httpx

from core.config.config import load_account, resolve_credentials
from integrations.errors import ProviderError
from integrations.wechat import (
    ArticleTotalDetail,
    DatacubeService,
    TokenManager,
    WeChatClient,
)

ACCOUNTS_DIR = Path("accounts")
RECEIPTS_DIR = Path("outputs/stats")


def _article_metrics(article: ArticleTotalDetail) -> str:
    """单篇文章指标行：取 detail_list 首日（发表当日）口径。"""
    if not article.detail_list:
        return f"    msgid={article.msgid}（无明细数据）"
    first = article.detail_list[0]
    return (
        f"    msgid={article.msgid} 阅读={first.read_user} 分享={first.share_user} "
        f"在看={first.zaikan_user} 点赞={first.like_user} 收藏={first.collection_user} "
        f"评论={first.comment_count} 完读率={first.read_finish_rate:.1f}% "
        f"送达率={first.read_delivery_rate:.1f}% 明细={len(article.detail_list)}天"
    )


def _print_summary(
    date: str,
    account: str,
    articles: tuple[ArticleTotalDetail, ...],
    receipt_path: Path,
) -> None:
    print(f"date={date} account={account} articles={len(articles)}")
    total_read = total_share = total_zaikan = total_like = 0
    for index, article in enumerate(articles, start=1):
        print(f"[{index}] {article.title}")
        print(_article_metrics(article))
        if article.detail_list:
            first = article.detail_list[0]
            total_read += first.read_user
            total_share += first.share_user
            total_zaikan += first.zaikan_user
            total_like += first.like_user
    if articles:
        print(
            f"合计（发表当日口径）：阅读 {total_read} · 分享 {total_share}"
            f" · 在看 {total_zaikan} · 点赞 {total_like}"
        )
    else:
        print("（当日无群发文章统计数据：可能当日未群发，或账号未认证）")
    print(f"回执：{receipt_path}")


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    today: datetime.date | None = None,
) -> int:
    """查询 date 当日群发文章数据；transport / today 注入口供测试使用（CI 零网络）。"""
    parser = argparse.ArgumentParser(
        prog="stats.py",
        description="查询某日群发文章的阅读 / 分享 / 互动数据（datacube getarticletotaldetail）",
    )
    parser.add_argument("--date", default=None, help="查询日期 YYYY-MM-DD（默认：昨日）")
    parser.add_argument(
        "--account", default="default", help="账号名（默认 default，对应 accounts/<name>.yaml）"
    )
    args = parser.parse_args(argv)

    current = today or datetime.date.today()
    date = args.date or (current - datetime.timedelta(days=1)).isoformat()

    try:
        account_config = load_account(ACCOUNTS_DIR, args.account)
        app_id, app_secret = resolve_credentials(account_config)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    client = WeChatClient(transport=transport)
    tokens = TokenManager(client, app_id=app_id, app_secret=app_secret)
    try:
        articles = DatacubeService(client, tokens).article_stats(date)
    except ProviderError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    receipt = {
        "date": date,
        "account": args.account,
        "article_count": len(articles),
        "articles": [asdict(article) for article in articles],
    }
    receipt_path = RECEIPTS_DIR / f"{date}_article_stats.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    _print_summary(date, args.account, articles, receipt_path)
    print(f"OK: {len(articles)} articles (date={date})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
