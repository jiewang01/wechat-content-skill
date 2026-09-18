#!/usr/bin/env python3
"""广告 Skill 发布反馈闭环工具（M4）。

按 knowledge/feedback-loop-rules.md、model-update-rules.md 执行：
PublishRecord + PerformanceRecord → Prediction vs Actual → Postmortem → Model Update 提案。

用法:
    # 1. 人工录入发布记录与表现数据（JSON），再生成复盘报告
    python3 tools/feedback_loop.py postmortem \\
        --adtask tests/cases/task-XXX.json --account data/account-example.json \\
        --decision tests/decisions/task-XXX.decision.json \\
        --publish tests/publish/task-XXX.publish.json \\
        --performance tests/performance/task-XXX.performance.json \\
        --angle "B-产品差异" --out tests/feedback/task-XXX.feedback.json

    # 2. 聚合多个已完成任务的复盘（plan §6.6）
    python3 tools/feedback_loop.py summary --feedback tests/feedback/
"""
import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

EMA_ALPHA = 0.2


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_case(case_or_task):
    if isinstance(case_or_task, dict) and "expected_adtask" in case_or_task:
        return case_or_task["expected_adtask"]
    return case_or_task


def ema(new, old, alpha=EMA_ALPHA) -> float:
    return alpha * new + (1 - alpha) * old


def delta_pct(pred, actual):
    """实际 vs 预测的偏差百分比；无基线返回 None。"""
    if pred is None or pred == 0:
        return None
    return round((actual - pred) / pred * 100, 1)


def verdict_of(delta):
    if delta is None:
        return "no_baseline"
    if delta > 50:
        return "above_baseline"
    if delta < -50:
        return "below_baseline"
    return "in_line"


def extract_cpm_price(settlement_rule: str):
    """从结算规则字符串提取阅读单价（如 0.5025 元/阅读）。"""
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:元)?\s*[/／度阅]*阅读", settlement_rule)
    if m:
        return float(m.group(1))
    m2 = re.search(r"每阅读?\s*([0-9]+(?:\.[0-9]+)?)\s*元", settlement_rule)
    if m2:
        return float(m2.group(1))
    m3 = re.search(r"单价[约为:：]*\s*([0-9]+(?:\.[0-9]+)?)\s*元", settlement_rule)
    if m3:
        return float(m3.group(1))
    return None


# ---------------------------------------------------------------- predictions

def derive_predictions(adtask, account) -> list:
    """按 feedback-loop-rules §3.1 推导各 metric 的预测基线（带来源）。"""
    perf = account.get("performance") or {}
    prod = account.get("production") or {}
    com = adtask.get("commercial") or {}
    rule = com.get("settlement_rule") or ""
    preds = []

    med = perf.get("median_views")
    preds.append({
        "metric": "views",
        "prediction": med,
        "source": "account.performance.median_views" if med else "no_baseline",
    })

    er = perf.get("avg_engagement_rate")
    preds.append({
        "metric": "engagement_rate",
        "prediction": er,
        "source": "account.performance.avg_engagement_rate" if er else "no_baseline",
    })

    ph = prod.get("avg_production_hours")
    preds.append({
        "metric": "production_hours",
        "prediction": ph,
        "source": "account.production.avg_production_hours" if ph else "no_baseline",
    })

    rev = (adtask.get("requirements") or {}).get("revision_limit")
    preds.append({
        "metric": "revision_count",
        "prediction": rev,
        "source": "adtask.requirements.revision_limit" if rev else "no_baseline",
    })

    fee = com.get("creator_fee")
    if fee is not None:
        preds.append({"metric": "revenue", "prediction": fee, "source": "adtask.commercial.creator_fee"})
    elif "单价" in rule or "阅读" in rule:
        price = extract_cpm_price(rule)
        if price and med:
            preds.append({
                "metric": "revenue",
                "prediction": round(med * price, 2),
                "source": "median_views×阅读单价(CPM估算)",
            })
        else:
            preds.append({"metric": "revenue", "prediction": None, "source": "no_baseline(CPM无单价/无基线)"})
    else:
        preds.append({"metric": "revenue", "prediction": None, "source": "no_baseline(未报价/置换)"})
    return preds


# ---------------------------------------------------------------- actual

def actual_of(publish, performance) -> dict:
    pub, perf = publish, (performance or {})
    m = perf.get("metrics") or {}
    views = m.get("views")
    er = None
    if views and views > 0:
        inter = sum(x for x in (m.get("likes"), m.get("comments"), m.get("saves"), m.get("shares")) if x)
        er = round(inter / views, 4)
    return {
        "views": views,
        "engagement_rate": er if er is not None else m.get("engagement_rate"),
        "production_hours": pub.get("actual_production_hours"),
        "revision_count": pub.get("revision_count"),
        "revenue": pub.get("actual_revenue"),
    }


# ---------------------------------------------------------------- postmortem

def build_postmortem(pva: list, actual: dict, account, adtask, conf) -> tuple:
    """按 feedback-loop-rules §3.3/§3.4 生成 worked/failed/errors/confidence_verdict。"""
    worked, failed, errors = [], [], []
    cat = (adtask.get("brand") or {}).get("category") or "未知品类"
    angle = "n/a"

    def get(metric):
        for row in pva:
            if row["metric"] == metric:
                return row
        return None

    # production_hours（F08）
    row = get("production_hours")
    ph_a = actual.get("production_hours")
    if row and row.get("prediction") and ph_a is not None:
        if ph_a > row["prediction"] * 1.3:
            errors.append({"type": "production", "detail": f"生产成本低估：实际 {ph_a}h vs 基线 {row['prediction']}h（delta +{(ph_a/row['prediction']-1)*100:.0f}%）", "impact": "high"})
            failed.append(f"生产成本低估（实际 {ph_a}h > 基线 {row['prediction']}h）")

    # views（F09/F10）
    row = get("views")
    if row and row.get("verdict") == "below_baseline":
        errors.append({"type": "prediction", "detail": f"阅读低于账号基线：实际 {actual['views']} vs 预测 {row['prediction']}（delta {row['delta_pct']}%）", "impact": "medium"})
        failed.append("内容表现低于账号基线（阅读量需人工核对）")
    elif row and row.get("verdict") == "above_baseline":
        worked.append(f"阅读超基线（实际 {actual['views']} > 预测 {row['prediction']}）")

    # engagement_rate（F13）
    row = get("engagement_rate")
    if row and row.get("verdict") == "above_baseline":
        worked.append(f"互动率超基线（实际 {actual['engagement_rate']} > 预测 {row['prediction']}）")

    # revision_count（F11）
    row = get("revision_count")
    rc_a = actual.get("revision_count")
    if rc_a:
        limit = row.get("prediction") if row else None
        if (limit and rc_a > limit) or rc_a > 2:
            errors.append({"type": "commercial", "detail": f"品牌修改频繁：实际 {rc_a} 轮（上限 {limit if limit else '未设'}）", "impact": "medium"})
            failed.append(f"品牌修改 {rc_a} 轮，超出预期")

    # revenue（F12）
    row = get("revenue")
    rv_a = actual.get("revenue")
    if row and row.get("prediction") and rv_a is not None and rv_a < row["prediction"]:
        errors.append({"type": "commercial", "detail": f"结算低于报价：实际 {rv_a} < 报价 {row['prediction']}", "impact": "low"})
        failed.append(f"结算低于报价（{rv_a} < {row['prediction']}）")

    # Confidence verdict（F14）
    cstatus = (conf or {}).get("status")
    deviation = any(r.get("verdict") in ("above_baseline", "below_baseline") for r in pva)
    if cstatus in ("high", "very_high"):
        cv = "high-confidence-inline" if not deviation else "high-confidence-deviation"
    elif cstatus in ("medium", "low"):
        cv = "low-confidence-inline" if not deviation else "low-confidence-deviation"
    else:
        cv = "unknown"
    return worked, failed, errors, cv


def build_recommendations(pva, actual, adtask, errors, proposals) -> list:
    recs = []
    cat = (adtask.get("brand") or {}).get("category") or "未知品类"
    for e in errors:
        if e["type"] == "production":
            for p in proposals:
                if p["target"].endswith("avg_production_hours"):
                    recs.append(f"上调生产成本基线至 {p['to']}h（见 model_update_proposals）")
        elif e["type"] == "prediction":
            recs.append("该内容表现低于账号基线：接同类任务前先核对品类/角度与账号匹配度")
        elif e["type"] == "commercial" and "修改频繁" in e["detail"]:
            recs.append("接单前要求品牌明确修改轮次上限")
        elif e["type"] == "commercial" and "结算" in e["detail"]:
            recs.append("核对佣金/结算条件后再接同类任务")
    for row in pva:
        if row["metric"] == "views" and row.get("verdict") == "above_baseline":
            recs.append(f"品类「{cat}」阅读超基线：可列为优先接单方向")
    if not recs:
        recs.append("人工复盘未发现需调整项（或数据不足，保持现状观察）")
    return recs


def build_proposals(pva, actual, account, adtask) -> list:
    """model-update-rules §1：基于复盘差异生成 Proposed 更新提案（不直接改文件）。"""
    proposals = []
    perf = account.get("performance") or {}
    prod = account.get("production") or {}

    def get(metric):
        for row in pva:
            if row["metric"] == metric and row.get("prediction") is not None:
                return row
        return None

    row = get("production_hours")
    if row and actual.get("production_hours") is not None:
        old = row["prediction"]
        new = round(ema(actual["production_hours"], old), 2)
        if abs(new - old) >= 0.1:
            proposals.append({
                "target": "account.production.avg_production_hours", "from": old, "to": new,
                "method": "ema", "status": "proposed",
                "rationale": f"生产成本复盘偏差（实际 {actual['production_hours']}h vs 基线 {old}h，基于 1 例）",
            })

    row = get("views")
    if row and actual.get("views") is not None:
        old = row["prediction"]
        new = round(ema(actual["views"], old))
        if abs(new - old) >= 10:
            proposals.append({
                "target": "account.performance.median_views", "from": old, "to": new,
                "method": "ema", "status": "proposed",
                "rationale": f"阅读复盘偏差（实际 {actual['views']} vs 基线 {old}，基于 1 例）",
            })

    cat = (adtask.get("brand") or {}).get("category") or "未知"
    fmt = (adtask.get("production") or {}).get("content_format") or "内容"
    existing = "；".join(perf.get("historical_campaigns") or [])
    existed = [c for c in (perf.get("historical_campaigns") or []) if f"{cat}{fmt}" in c]
    if not existed:
        proposals.append({
            "target": "account.performance.historical_campaigns",
            "from": existing or "（空）",
            "to": (existing + "；" if existing else "") + f"{cat} {fmt} ×1",
            "method": "append", "status": "proposed",
            "rationale": f"已发布 {cat} {fmt} 内容，追加历史样本（基于 1 例）",
        })

    if not proposals:
        proposals.append({
            "target": "（无）", "from": None, "to": None,
            "method": "noop", "status": "proposed",
            "rationale": "复盘确认无显著偏差或实际数据不足，无需更新（留痕）",
        })
    return proposals


# ---------------------------------------------------------------- report

def build_report(adtask, account, decision, publish, performance, angle) -> dict:
    adtask = resolve_case(adtask)
    preds = derive_predictions(adtask, account)
    actual = actual_of(publish, performance)

    pva = []
    for p in preds:
        a = actual.get(p["metric"])
        d = delta_pct(p["prediction"], a) if a is not None else None
        pva.append({**p, "actual": a, "delta_pct": d, "verdict": verdict_of(d)})

    worked, failed, errors, cv = build_postmortem(pva, actual, account, adtask, (decision or {}).get("confidence"))
    proposals = build_proposals(pva, actual, account, adtask)
    recs = build_recommendations(pva, actual, adtask, errors, proposals)

    return {
        "feedback_id": f"FDB-{datetime.now(timezone.utc).strftime('%Y%m%d')}-0001",
        "task_id": adtask.get("task_id"),
        "publish_id": publish.get("publish_id"),
        "decision_id": (decision or {}).get("decision_id"),
        "campaign_category": (adtask.get("brand") or {}).get("category") or "未知品类",
        "content_angle": angle or "n/a",
        "prediction_vs_actual": pva,
        "what_worked": worked,
        "what_failed": failed,
        "errors": errors,
        "confidence_verdict": cv,
        "next_recommendations": recs,
        "model_update_proposals": proposals,
        "created_at": now_iso(),
    }


# ---------------------------------------------------------------- summary

def run_summary(feedback_dir: str) -> dict:
    paths = sorted(glob.glob(os.path.join(feedback_dir, "**", "*feedback*.json"), recursive=True))
    reports = [load_json(p) for p in paths]
    n = len(reports)
    out = {"sample_count": n, "note": "", "metrics": {}, "by_category": {}, "by_angle": {}, "confidence_verdicts": {}}

    if n == 0:
        out["note"] = "暂无复盘样本，无法聚合（plan §6.6 需 30+ 已完成任务）"
        return out

    met_map = {"views": [], "engagement_rate": [], "production_hours": [], "revision_count": [], "revenue": []}
    for r in reports:
        for row in r.get("prediction_vs_actual", []):
            m = row["metric"]
            if m in met_map and row.get("verdict") != "no_baseline":
                met_map[m].append(row)
    for m, rows in met_map.items():
        if rows:
            deltas = [r["delta_pct"] for r in rows if r["delta_pct"] is not None]
            out["metrics"][m] = {
                "n": len(rows),
                "mean_delta_pct": round(sum(deltas) / len(deltas), 1) if deltas else None,
                "above": sum(1 for r in rows if r["verdict"] == "above_baseline"),
                "below": sum(1 for r in rows if r["verdict"] == "below_baseline"),
                "inline": sum(1 for r in rows if r["verdict"] == "in_line"),
            }

    for key, field, metric in (("by_category", "campaign_category", "views"), ("by_angle", "content_angle", "views")):
        groups = {}
        for r in reports:
            k = r.get(field) or "n/a"
            row = next((x for x in r.get("prediction_vs_actual", []) if x["metric"] == metric and x.get("verdict") != "no_baseline"), None)
            groups.setdefault(k, []).append(row)
        for k, rows in groups.items():
            rows = [r for r in rows if r]
            if rows:
                deltas = [r["delta_pct"] for r in rows if r["delta_pct"] is not None]
                out[key][k] = {"n": len(rows), "mean_views_delta_pct": round(sum(deltas) / len(deltas), 1) if deltas else None}

    for r in reports:
        cv = r.get("confidence_verdict") or "unknown"
        out["confidence_verdicts"][cv] = out["confidence_verdicts"].get(cv, 0) + 1

    out["note"] = "样本 <30，结论仅作参考（plan §6.6 验收基线为 30+ 已完成任务）" if n < 30 else "样本充足"
    return out


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="广告 Skill 发布反馈闭环工具（M4）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("postmortem", help="生成发布复盘报告（Postmortem + Model Update 提案）")
    p.add_argument("--adtask", required=True)
    p.add_argument("--account", required=True)
    p.add_argument("--decision", required=True)
    p.add_argument("--publish", required=True)
    p.add_argument("--performance", required=True)
    p.add_argument("--angle", default=None)
    p.add_argument("--out", default=None)

    s = sub.add_parser("summary", help="聚合多个已完成任务的复盘（plan §6.6）")
    s.add_argument("--feedback", required=True)

    args = ap.parse_args()

    if args.cmd == "postmortem":
        report = build_report(
            load_json(args.adtask), load_json(args.account),
            load_json(args.decision), load_json(args.publish),
            load_json(args.performance), args.angle,
        )
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out:
            os.makedirs(os.path.dirname(args.out), exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text + "\n")
            print(f"feedback written to {args.out}")
        else:
            print(text)
        return 0

    if args.cmd == "summary":
        print(json.dumps(run_summary(args.feedback), ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())