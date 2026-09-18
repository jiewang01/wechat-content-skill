#!/usr/bin/env python3
"""广告 Skill 自适应 Agent（M5，plan §7）。

按 knowledge/adaptive-agent-rules.md 执行：
  Adaptive AccountProfile（§7.1）→ Adaptive Cost Model（§7.2）
  → Adaptive Decision 校准（§7.3）→ Decision Debugging（§7.4）

用法:
    # 1. 将 M4 复盘提案应用为账号画像 v2（含版本日志，不改 v1）
    python3 tools/adaptive_agent.py profile-update \\
        --account data/account-example-xhs.json --feedback tests/feedback/task-002.feedback.json \\
        --out data/accounts/account-example-xhs.v2.json --log tests/version-log.json

    # 2. 按画像基线 + 任务特征预测生产成本
    python3 tools/adaptive_agent.py cost-predict \\
        --task tests/cases/task-002.json --account data/accounts/account-example-xhs.v2.json

    # 3. 用历史复盘校准决策参数（样本门槛 A07）
    python3 tools/adaptive_agent.py calibrate --feedback tests/feedback/

    # 4. 回放一次决策：Task→Evidence→Analysis→Score→Decision→Actual + Counterfactual
    python3 tools/adaptive_agent.py debug \\
        --adtask tests/cases/task-002.json --account data/account-example-xhs.json \\
        --decision tests/decisions/task-002.decision.json --feedback tests/feedback/task-002.feedback.json
"""
import argparse
import copy
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decision_engine import W, ACCEPT_MIN, OBSERVE_MIN  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def resolve_case(obj):
    if isinstance(obj, dict) and "expected_adtask" in obj:
        return obj["expected_adtask"]
    return obj


def _locate_path(root, target):
    """路径归一化：M4 提案的 target 形如 account.production.avg_production_hours，
    但画像文件顶层即 production/performance（schema 顶层属性）。
    优先按去掉 account. 前缀解析，否则按字面路径。"""
    parts = target.split(".")
    if parts and parts[0] == "account" and len(parts) > 1:
        alt = parts[1:]
        if alt and isinstance(root.get(alt[0]), dict):
            return alt
    return parts


def get_by_path(root, path):
    cur = root
    for p in _locate_path(root, path):
        cur = cur.get(p) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur


def set_by_path(root, path, value):
    cur = root
    parts = _locate_path(root, path)
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


def next_version(account) -> str:
    cur = account.get("profile_version") or "v1"
    m = re.fullmatch(r"v(\d+)", cur)
    return f"v{int(m.group(1)) + 1}" if m else f"{cur}.1"


# ---------------------------------------------------------------- profile-update

def run_profile_update(account_path, feedback_path, out_path, log_path) -> int:
    account = load_json(account_path)
    feedback = load_json(feedback_path)
    version = next_version(account)
    proposals = [p for p in feedback.get("model_update_proposals", []) if p.get("method") != "noop"]

    entries = []
    applied = 0
    for p in proposals:
        target = p.get("target") or ""
        to = p.get("to")
        if target == "account.performance.historical_campaigns":
            val = to.split("；") if isinstance(to, str) else to
            set_by_path(account, target, val)
        else:
            set_by_path(account, target, to)
        entries.append({
            "target": target, "from": p.get("from"), "to": to,
            "method": p.get("method"), "feedback_id": feedback.get("feedback_id"),
            "status": "applied",
        })
        applied += 1

    account["profile_version"] = version
    dump_json(out_path, account)

    log = {
        "log_id": f"VERLOG-{datetime.now(timezone.utc).strftime('%Y%m%d')}-0001",
        "target_model": "AccountProfile",
        "profile_version": version,
        "account_id": account.get("account_id"),
        "applied_at": now_iso(),
        "entries": entries,
    }
    if log_path:
        dump_json(log_path, log)
    print(f"[profile-update] {account.get('account_id')} → {version}（applied {applied} 条）")
    print(f"  写入: {out_path}")
    if log_path:
        print(f"  版本日志: {log_path}")
    return 0


# ---------------------------------------------------------------- cost-predict

def run_cost_predict(task_path, account_path, out_path=None) -> int:
    adtask = resolve_case(load_json(task_path))
    account = load_json(account_path)
    base = get_by_path(account, "production.avg_production_hours")
    if base is None:
        result = {"base_hours": None, "adjustments": [], "predicted_hours": None,
                  "source": "no_baseline（账号无生产成本基线）", "generated_at": now_iso()}
    else:
        prod = adtask.get("production") or {}
        fmt = prod.get("content_format") or ""
        special = "；".join(prod.get("special_requirements") or [])
        adjustments = []
        if re.search(r"视频|短视频|直播", fmt):
            adjustments.append({"factor": "content_format 含视频", "value": 0.4})
        if re.search(r"出镜|实拍|探店|拍摄", special):
            adjustments.append({"factor": "特要求含实拍/出镜", "value": 0.3})
        est = prod.get("estimated_hours")
        if est:
            adjustments.append({"factor": f"任务标注预估工时 {est}h（取大值）", "value": max(0.0, (est - base) / (base or 1))})
            base = max(base, est)
        predicted = round(base * (1 + sum(a["value"] for a in adjustments)), 1) if adjustments else round(base, 1)
        v = account.get("profile_version") or "v1"
        result = {
            "base_hours": base, "adjustments": adjustments,
            "predicted_hours": predicted,
            "source": f"account.production.avg_production_hours(@{v})+任务特征调整",
            "generated_at": now_iso(),
        }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if out_path:
        dump_json(out_path, result)
        print(f"cost prediction written to {out_path}")
    else:
        print(text)
    return 0


# ---------------------------------------------------------------- calibrate

def run_calibrate(feedback_dir: str, out_path=None) -> int:
    paths = sorted(glob.glob(os.path.join(feedback_dir, "*.json")))
    reports = [load_json(p) for p in paths]
    n = len(reports)

    hours = []
    for r in reports:
        for row in r.get("prediction_vs_actual", []):
            if row["metric"] == "production_hours" and row.get("verdict") != "no_baseline" \
                    and row.get("delta_pct") is not None:
                hours.append(row)

    cal = []
    if n == 0:
        note = "暂无复盘样本，校准不执行（A07/A14）"
    elif len(hours) < 3:
        cal.append({"target": "decision_engine.W.production_cost", "from": 0.15, "to": 0.18,
                    "status": "research",
                    "rationale": f"生产成本偏差候选：仅 {len(hours)} 例（均值 {sum(h['delta_pct'] for h in hours) / len(hours):.0f}%），单样本不显著，不动权重（A07）"})
        note = "样本 <3，仅输出 research 候选，权重保持现状"
    else:
        mean = sum(h["delta_pct"] for h in hours) / len(hours)
        if mean > 30:
            cal.append({"target": "decision_engine.W.production_cost", "from": 0.15, "to": 0.18,
                        "status": "confirm",
                        "rationale": f"{len(hours)} 例生产成本均值偏差 +{mean:.0f}%（系统性低估），建议上调权重"})
        note = "样本充足，产出 confirm 级校准建议"

    fp = []
    for r in reports:
        has_low_rev = any(e["type"] == "commercial" and "结算" in e["detail"] for e in r.get("errors", []))
        row = next((x for x in r.get("prediction_vs_actual", [])
                    if x["metric"] == "views" and x.get("verdict") == "below_baseline"), None)
        if has_low_rev and row:
            fp.append({"task_id": r.get("task_id"), "why": "结算低于报价且阅读低于基线（A08 FP 候选）"})

    result = {
        "sample_count": n,
        "note": note,
        "production_hours": {"n": len(hours),
                             "mean_delta_pct": round(sum(h["delta_pct"] for h in hours) / len(hours), 1) if hours else None},
        "false_positive_candidates": fp,
        "false_negative_note": "无法评估：缺拒单审计数据（A08/A14，需回填 reject/observe 未接任务的实际表现）",
        "calibration_proposals": cal,
        "generated_at": now_iso(),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if out_path:
        dump_json(out_path, result)
        print(f"calibration report written to {out_path}")
    else:
        print(text)
    return 0


# ---------------------------------------------------------------- debug

def run_debug(adtask_path, account_path, decision_path, feedback_path, out_path=None) -> int:
    adtask = resolve_case(load_json(adtask_path))
    account = load_json(account_path)
    decision = load_json(decision_path)
    feedback = load_json(feedback_path)

    pva = feedback.get("prediction_vs_actual", [])
    find = lambda m: next((x for x in pva if x["metric"] == m), None)  # noqa: E731
    actual = {m: (find(m) or {}).get("actual") for m in
              ("views", "engagement_rate", "production_hours", "revision_count", "revenue")}
    plant_ev = decision.get("evidence_refs") or []

    base_hours = get_by_path(account, "production.avg_production_hours")
    act_hours = actual.get("production_hours")
    cf = None
    if act_hours is not None and base_hours:
        r = (act_hours - base_hours) / base_hours
        penalty = min(30, round(r * 30))
        cost_old = decision.get("dimensions", {}).get("production_cost", 60)
        cost_new = max(20, cost_old - penalty)
        score_old = decision.get("decision_score")
        score_new = round(score_old - W["production_cost"] * (cost_old - cost_new), 1) \
            if score_old is not None else None
        action_new = None
        if score_new is not None:
            action_new = "accept" if score_new >= ACCEPT_MIN else ("observe" if score_new >= OBSERVE_MIN else "reject")
        cf = {
            "trigger": f"实际工时 {act_hours}h > 决策时基线 {base_hours}h（A11）",
            "r": round(r, 3), "penalty": penalty,
            "production_cost": {"from": cost_old, "to": cost_new},
            "score": {"from": score_old, "to": score_new},
            "action": {"from": decision.get("action"), "to": action_new},
        }

    changed = []
    if cf and cf["action"]["to"] != cf["action"]["from"]:
        changed.append(f"production_hours 实际 {act_hours}h vs 基线 {base_hours}h → "
                       f"production_cost {cf['production_cost']['from']}→{cf['production_cost']['to']}，"
                       f"score {cf['score']['from']}→{cf['score']['to']}，结论 {cf['action']['from']}→{cf['action']['to']}")
    else:
        changed.append("现有偏差证据不足以翻转结论（需更多复盘样本，A12）")

    result = {
        "replay": {
            "task_id": adtask.get("task_id"),
            "evidence_count": len(plant_ev),
            "dimensions": decision.get("dimensions"),
            "score": decision.get("decision_score"),
            "action": decision.get("action"),
            "confidence": decision.get("confidence", {}).get("status"),
            "actual": actual,
            "feedback_errors": feedback.get("errors", []),
        },
        "counterfactual": cf,
        "changed_evidence": changed,
        "conclusion": (f"当时证据链（{len(plant_ev)} 条 Evidence）支撑 {decision.get('action')}；"
                       + "；".join(changed)),
        "generated_at": now_iso(),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if out_path:
        dump_json(out_path, result)
        print(f"debug report written to {out_path}")
    else:
        print(text)
    return 0


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="广告 Skill 自适应 Agent（M5）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("profile-update", help="将 M4 复盘提案应用为画像新版本（含版本日志）")
    p.add_argument("--account", required=True)
    p.add_argument("--feedback", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--log", required=True)

    c = sub.add_parser("cost-predict", help="按画像基线 + 任务特征预测生产成本")
    c.add_argument("--task", required=True)
    c.add_argument("--account", required=True)
    c.add_argument("--out", default=None)

    k = sub.add_parser("calibrate", help="用历史复盘校准决策参数（A07 样本门槛）")
    k.add_argument("--feedback", required=True)
    k.add_argument("--out", default=None)

    d = sub.add_parser("debug", help="决策回放：Task→Evidence→Analysis→Score→Decision→Actual + Counterfactual")
    d.add_argument("--adtask", required=True)
    d.add_argument("--account", required=True)
    d.add_argument("--decision", required=True)
    d.add_argument("--feedback", required=True)
    d.add_argument("--out", default=None)

    args = ap.parse_args()

    if args.cmd == "profile-update":
        return run_profile_update(args.account, args.feedback, args.out, args.log)
    if args.cmd == "cost-predict":
        return run_cost_predict(args.task, args.account, args.out)
    if args.cmd == "calibrate":
        return run_calibrate(args.feedback, args.out)
    if args.cmd == "debug":
        return run_debug(args.adtask, args.account, args.decision, args.feedback, args.out)
    return 1


if __name__ == "__main__":
    sys.exit(main())