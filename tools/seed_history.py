#!/usr/bin/env python3
"""生成 synthetic 历史完成案例库（M5 backlog：30+ 完成案例回填验证）。

用途：
  验证 plan §6.6（summary/校准在 30+ 已完成任务上的聚合）与 A07（≥3 例转 confirm）。
  数据为【合成验证数据】，非真实运营数据：pattern 由固定随机种子驱动，可复现；
  现象注入（成本低估 / 阅读超/低基线 / 修改频繁 / 结算不足 / 拒单审计）用于压测规则。

输出：
  tests/history/{seq:02d}/  adtask.json decision.json publish.json performance.json feedback.json
  tests/audits/audit-{seq:02d}.json   （reject/need_information 任务的拒单审计）

用法:
    python3 tools/seed_history.py [--min-record 30] [--out tests/history]
"""
import argparse
import glob
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decision_engine import select_account  # noqa: E402
from feedback_loop import build_report, now_iso  # noqa: E402

ANGLE_POOL = ["A-人群共鸣", "B-产品差异", "C-场景植入"]
PUBLISHABLE = {"accept", "observe"}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_dated(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-record", type=int, default=30)
    ap.add_argument("--out", default="tests/history")
    ap.add_argument("--audit-out", default="tests/audits")
    args = ap.parse_args()

    rnd = random.Random(20260918)
    histories, audits = [], []
    seq = 0
    base_day = datetime(2026, 8, 1, tzinfo=timezone.utc)

    cases = sorted(glob.glob("tests/cases/task-*.json"))
    dec_map = {os.path.basename(p).replace(".decision.json", ""): p
               for p in glob.glob("tests/decisions/task-*.decision.json")}

    for case_path in cases:
        case = load_json(case_path)
        adtask = case["expected_adtask"]
        task_id = adtask["task_id"]
        dec_path = dec_map.get(os.path.basename(case_path).replace(".json", ""))
        decision = load_json(dec_path) if dec_path else None
        account = select_account(adtask)
        action = (decision or {}).get("action", "need_information")
        cat = (adtask.get("brand") or {}).get("category") or "未知"
        fmt = (adtask.get("production") or {}).get("content_format") or "内容"

        # ---- 拒单审计：reject / need_information 未接任务 ----
        if action not in PUBLISHABLE:
            fake_positive = rnd.random() < 0.35  # 35% 判定为 FN（实际会好的拒单）
            seq += 1
            audit = {
                "audit_id": f"AUD-HIST-{seq:04d}",
                "task_id": task_id,
                "decision_id": (decision or {}).get("decision_id"),
                "decided_action": action,
                "verdict": "false_negative" if fake_positive else "true_negative",
                "evidence": (f"后续信息显示「{cat}」类任务在该平台表现稳定（synthetic 审计样本，"
                             f"{'实际可接' if fake_positive else '拒单正确'}）"),
                "generated_at": now_iso(),
            }
            audits.append(audit)
            dump_dated(os.path.join(args.audit_out, f"audit-{seq:04d}.json"), audit)
            continue

        # ---- 可发布任务：1~2 轮复投记录，直到总量达标 ----
        rounds = 2 if len(histories) + 2 <= args.min_record else 1
        for _ in range(rounds):
            seq += 1
            base_hours = (account.get("production") or {}).get("avg_production_hours") or 3.0
            med_views = (account.get("performance") or {}).get("median_views") or 5000
            base_er = (account.get("performance") or {}).get("avg_engagement_rate") or 0.05
            com = adtask.get("commercial") or {}

            # 现象注入（确定性）
            hours_f = 0.9 + rnd.random() * 0.9          # 0.90~1.80 → 多数成本偏高
            views_f = 0.4 + rnd.random() * 1.6          # 0.40~2.00
            rev_count = rnd.randint(0, 4)
            if "视频" in fmt or ("拍摄" in str((adtask.get("production") or {}).get("special_requirements") or [])):
                hours_f += 0.3
            actual_hours = round(base_hours * hours_f, 1)
            views = int(med_views * views_f)
            likes = int(views * base_er * (0.6 + rnd.random() * 0.8))
            comments = int(likes * 0.15)
            saves = int(likes * 0.5)
            shares = int(likes * 0.25)
            clicks = None if (adtask.get("source") or {}).get("platform") == "小红书" else int(views * 0.08)

            fee = com.get("creator_fee")
            if fee is not None:
                actual_rev = fee if rnd.random() > 0.15 else round(fee * 0.9, 2)
                rev_note = "固定费已结，佣金未达成" if actual_rev < fee else "固定费按报价结清"
            else:
                actual_rev = None
                rev_note = "结算规则为 CPM/置换，按平台导出折算（synthetic）"

            pub_time = base_day + timedelta(hours=seq * 13)
            publish = {
                "publish_id": f"PUB-HIST-{seq:04d}",
                "task_id": task_id,
                "account_id": account.get("account_id"),
                "decision_id": (decision or {}).get("decision_id"),
                "content_id": None,
                "publish_time": pub_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "published",
                "actual_production_hours": actual_hours,
                "revision_count": rev_count,
                "actual_revenue": actual_rev,
                "revenue_notes": rev_note,
                "created_at": now_iso(),
            }
            perf = {
                "performance_id": f"PERF-HIST-{seq:04d}",
                "publish_id": publish["publish_id"],
                "task_id": task_id,
                "window_hours": 72,
                "collected_at": (pub_time + timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "metrics": {"views": views, "likes": likes, "comments": comments,
                            "saves": saves, "shares": shares, "clicks": clicks,
                            "conversion": None, "revenue": actual_rev},
                "engagement_rate": None,
                "source": "synthetic（机制验证数据集）",
                "created_at": now_iso(),
            }
            angle = ANGLE_POOL[seq % 3]
            feedback = build_report(adtask, account, decision, publish, perf, angle)

            out_dir = os.path.join(args.out, f"{seq:02d}")
            dump_dated(os.path.join(out_dir, "adtask.json"), adtask)
            dump_dated(os.path.join(out_dir, "decision.json"), decision)
            dump_dated(os.path.join(out_dir, "publish.json"), publish)
            dump_dated(os.path.join(out_dir, "performance.json"), perf)
            dump_dated(os.path.join(out_dir, "feedback.json"), feedback)
            histories.append(feedback)

    print(f"[seed_history] records={len(histories)} audits={len(audits)} -> {args.out}/ {args.audit_out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())