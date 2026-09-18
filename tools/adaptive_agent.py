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

def run_calibrate(feedback_dir: str, out_path=None, audit_dir=None) -> int:
    paths = sorted(glob.glob(os.path.join(feedback_dir, "**", "*feedback*.json"), recursive=True))
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

    # 拒单审计（A08/A14）：reject/need_information 未接任务的回访
    audits = []
    if audit_dir and os.path.isdir(audit_dir):
        for p in sorted(glob.glob(os.path.join(audit_dir, "*.json"))):
            try:
                audits.append(load_json(p))
            except Exception:
                continue
    fn = [a for a in audits if a.get("verdict") == "false_negative"]
    tn = [a for a in audits if a.get("verdict") == "true_negative"]
    if audits:
        fn_summary = f"{len(fn)}/{len(audits)} 拒单判定为 FalseNegative（实际可接），具体任务：" + \
                     ("，".join(a.get("task_id", "?") for a in fn) if fn else "无")
    else:
        fn_summary = "无法评估：缺拒单审计数据（A08/A14，需回填 reject/observe 未接任务的实际表现）"

    result = {
        "sample_count": n,
        "note": note,
        "production_hours": {"n": len(hours),
                             "mean_delta_pct": round(sum(h["delta_pct"] for h in hours) / len(hours), 1) if hours else None},
        "false_positive_candidates": fp,
        "audit_summary": {"n": len(audits), "true_negative": len(tn), "false_negative": len(fn),
                          "detail": fn_summary},
        "false_negative_note": fn_summary,
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


# ---------------------------------------------------------------- apply-calibration

def run_apply_calibration(report_path: str, config_out: str, regress_out: str) -> int:
    """自适应上生产（M5 遗留落地）：
    1) 将 calibrate 输出中 status=confirm 的权重提案落配置 tools/engine_config.json；
    2) 权重重算回归：内置权重 vs 新权重跑全量 cases，对比 action/score 变化。
    显式 --config 才被决策引擎加载（M02/A13 人工 gate 双重保障）。"""
    report = load_json(report_path)
    confirms = [c for c in report.get("calibration_proposals", []) if c.get("status") == "confirm"]
    if not confirms:
        print("[apply-calibration] 无 confirm 级提案（校准未达样本门槛），不生成配置")
        return 1

    import pathlib
    from decision_engine import W as _W, build_decision, select_account

    rationales = "；".join(f"{c['from']}→{c['to']}：{c.get('rationale','')}" for c in confirms)
    weights = dict(_W)
    for c in confirms:
        weights[c["target"].split(".")[-1]] = c["to"]
    # 权重保持归一化（总和=1）：避免确认调整后 score 系统性上浮/下移
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        weights = {k: round(v / total, 4) for k, v in weights.items()}
    config = {
        "meta": {"version": "v1.1", "applied_at": now_iso(),
                 "sample_count": report.get("sample_count"),
                 "source": "adaptive_agent.apply-calibration（calibrate confirm 级提案）",
                 "rationale": rationales},
        "weights": weights,
    }
    dump_json(config_out, config)

    def _batch() -> dict:
        res = {}
        for p in sorted(pathlib.Path("tests/cases").glob("task-*.json")):
            case = load_json(p)
            adtask = case["expected_adtask"]
            evs = case.get("expected_evidence") or []
            d = build_decision(adtask, select_account(adtask), evs)
            res[p.stem] = (d["action"], d["decision_score"])
        return res

    old_res = _batch()
    old_w = dict(_W)          # 备份内置权重，供回归后恢复（防污染）
    _W.update(weights)
    new_res = _batch()
    _W.clear(); _W.update(old_w)

    changed = []
    for k in old_res:
        if old_res[k] != new_res[k]:
            changed.append({"case": k, "action": {"from": old_res[k][0], "to": new_res[k][0]},
                            "score": {"from": old_res[k][1], "to": new_res[k][1]}})
    regress = {"config_version": config["meta"]["version"], "cases_total": len(old_res),
               "cases_changed": len(changed), "changes": changed,
               "generated_at": now_iso()}
    dump_json(regress_out, regress)

    print(f"[apply-calibration] config -> {config_out}（{len(confirms)} 条 confirm 应用）")
    print(f"[apply-calibration] regression -> {regress_out}（{len(changed)}/{len(old_res)} 例 action/score 变化）")
    for c in changed:
        print(f"   {c['case']}: {c['action']['from']}/{c['score']['from']} -> {c['action']['to']}/{c['score']['to']}")
    return 0


# ---------------------------------------------------------------- auto-apply

def run_auto_apply(accounts_dir, feedback_dir, accounts_out, log_path,
                   config_out, regress_out, max_flips=0) -> int:
    """全自动应用（放开人工 gate，A13 演进版）：
    1) 按 account_id 聚合 feedback 的 proposed 提案，自动升级各账号画像（数值 last-write-wins、
       historical_campaigns union；每账号独立版本 + VersionLog，旧版保留可回滚）；
    2) 全量校准：≥3 例且生产偏差一致 → confirm 权重 → 归一化 → 落 engine_config.json；
    3) 权重重算回归：action 翻转数 ≤ max_flips 时设置 meta.auto_enabled=true，
       decision_engine 无 --config 自动加载该配置（否则仅落盘不自动启用）。
    安全护栏仍保留：版本化留痕、权重归一化、回归护栏（翻转即拒自动启用）。"""
    fdb_paths = sorted(glob.glob(os.path.join(feedback_dir, "**", "*feedback*.json"), recursive=True))
    reports = [load_json(p) for p in fdb_paths]
    by_account = {}
    for r in reports:
        by_account.setdefault(r.get("account_id") or "?", []).append(r)

    account_files = sorted(glob.glob(os.path.join(accounts_dir, "account-example*.json")))
    log_dir = os.path.dirname(log_path) or "."
    log_base = os.path.splitext(os.path.basename(log_path))[0]
    upgraded = []
    for acc_path in account_files:
        account = load_json(acc_path)
        acc_id = account.get("account_id")
        acc_feedbacks = by_account.get(acc_id, [])
        if not acc_feedbacks:
            continue
        version = next_version(account)
        proposals = [p for r in acc_feedbacks
                     for p in r.get("model_update_proposals", []) if p.get("method") != "noop"]
        entries = []
        for p in proposals:
            target = p.get("target") or ""
            if target.endswith("historical_campaigns"):
                cur = get_by_path(account, target) or []
                to_list = p["to"].split("；") if isinstance(p["to"], str) else (p["to"] or [])
                merged = list(cur)
                for it in to_list:
                    if it not in merged:
                        merged.append(it)
                set_by_path(account, target, merged)
                entries.append({"target": target, "from": "；".join(cur) if cur else "（空）",
                                "to": "；".join(merged), "method": "append",
                                "feedback_id": p.get("feedback_id"), "status": "applied"})
            else:
                set_by_path(account, target, p["to"])  # last-write-wins，历史在 VersionLog 回溯
                entries.append({"target": target, "from": p.get("from"), "to": p.get("to"),
                                "method": p.get("method"), "feedback_id": p.get("feedback_id"),
                                "status": "applied"})
        account["profile_version"] = version
        out_path = os.path.join(accounts_out, os.path.basename(acc_path).replace(".json", f".{version}.json"))
        dump_json(out_path, account)
        if entries:
            dump_json(os.path.join(log_dir, f"{log_base}-{acc_id}.json"), {
                "log_id": f"VERLOG-AUTO-{acc_id}",
                "target_model": "AccountProfile", "profile_version": version,
                "account_id": acc_id, "applied_at": now_iso(), "entries": entries,
            })
        upgraded.append((acc_id, version, len(proposals)))

    # ---- 全量校准：confirm 提案 + 归一化 ----
    hours = []
    for r in reports:
        for row in r.get("prediction_vs_actual", []):
            if row["metric"] == "production_hours" and row.get("verdict") != "no_baseline" \
                    and row.get("delta_pct") is not None:
                hours.append(row)
    confirms = []
    if len(hours) >= 3:
        mean = sum(h["delta_pct"] for h in hours) / len(hours)
        if mean > 30:
            confirms.append({"target": "decision_engine.W.production_cost", "from": 0.15, "to": 0.18,
                             "status": "confirm",
                             "rationale": f"{len(hours)} 例生产成本均值 +{mean:.0f}%（自动校准，A07 门槛已过）"})

    auto_on = False
    if confirms:
        import decision_engine as de
        weights = dict(de.W)
        for c in confirms:
            weights[c["target"].split(".")[-1]] = c["to"]
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-9:
            weights = {k: round(v / total, 4) for k, v in weights.items()}

        def _batch() -> dict:
            import pathlib
            res = {}
            for p in sorted(pathlib.Path("tests/cases").glob("task-*.json")):
                case = load_json(p)
                adtask = case["expected_adtask"]
                evs = case.get("expected_evidence") or []
                d = de.build_decision(adtask, de.select_account(adtask), evs)
                res[p.stem] = (d["action"], d["decision_score"])
            return res

        old_res = _batch()
        old_w = dict(de.W)
        de.W.update(weights)
        new_res = _batch()
        de.W.clear(); de.W.update(old_w)
        flips = [k for k in old_res if old_res[k] != new_res[k] and old_res[k][0] != new_res[k][0]]
        score_moved = [k for k in old_res if old_res[k] != new_res[k] and old_res[k][0] == new_res[k][0]]
        auto_on = len(flips) <= max_flips

        config = {
            "meta": {"version": "v1.1", "applied_at": now_iso(),
                     "sample_count": len(reports), "auto_enabled": auto_on,
                     "source": "adaptive_agent.auto-apply（全自动校准）",
                     "rationale": "；".join(c["rationale"] for c in confirms),
                     "regression": {"action_flips": len(flips), "score_only_changes": len(score_moved),
                                    "flips": flips}},
            "weights": weights,
        }
        dump_json(config_out, config)
        dump_json(regress_out, {"config_version": config["meta"]["version"],
                                "cases_total": len(old_res), "action_flips": len(flips),
                                "score_only_changes": len(score_moved), "flips": flips,
                                "generated_at": now_iso()})
    else:
        print("[auto-apply] 校准未达 confirm 门槛（<3 例或偏差 <30%），不落权重配置")

    print(f"[auto-apply] feedback={len(reports)} 账号升级={len(upgraded)} config->{config_out} auto_enabled={auto_on}")
    for acc_id, ver, n in upgraded:
        print(f"    {acc_id} → {ver}（{n} 条提案 applied，VersionLog 已写）")
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

    k = sub.add_parser("calibrate", help="用历史复盘校准决策参数（A07 样本门槛）；--audit 纳拒单审计 FN 统计")
    k.add_argument("--feedback", required=True)
    k.add_argument("--audit", default=None)
    k.add_argument("--out", default=None)

    d = sub.add_parser("debug", help="决策回放：Task→Evidence→Analysis→Score→Decision→Actual + Counterfactual")
    d.add_argument("--adtask", required=True)
    d.add_argument("--account", required=True)
    d.add_argument("--decision", required=True)
    d.add_argument("--feedback", required=True)
    d.add_argument("--out", default=None)

    a = sub.add_parser("apply-calibration", help="校准 confirm 落配置 + 权重重算回归（自适应上生产）")
    a.add_argument("--report", required=True)
    a.add_argument("--config-out", default="tools/engine_config.json")
    a.add_argument("--regress-out", default="tests/calibration-regression.json")

    aa = sub.add_parser("auto-apply", help="全自动应用（放开人工 gate）：按账号聚合升级画像 + 校准落配置 + 回归护栏")
    aa.add_argument("--accounts-dir", default="data")
    aa.add_argument("--feedback", required=True)
    aa.add_argument("--accounts-out", default="data/accounts")
    aa.add_argument("--log", default="tests/version-log-auto.json")
    aa.add_argument("--config-out", default="tools/engine_config.json")
    aa.add_argument("--regress-out", default="tests/calibration-regression.json")
    aa.add_argument("--max-flips", type=int, default=0,
                    help="回归允许的 action 翻转上限，超过则不自动启用（保持落盘）")

    args = ap.parse_args()

    if args.cmd == "profile-update":
        return run_profile_update(args.account, args.feedback, args.out, args.log)
    if args.cmd == "cost-predict":
        return run_cost_predict(args.task, args.account, args.out)
    if args.cmd == "calibrate":
        return run_calibrate(args.feedback, args.out, args.audit)
    if args.cmd == "debug":
        return run_debug(args.adtask, args.account, args.decision, args.feedback, args.out)
    if args.cmd == "apply-calibration":
        return run_apply_calibration(args.report, args.config_out, args.regress_out)
    if args.cmd == "auto-apply":
        return run_auto_apply(args.accounts_dir, args.feedback, args.accounts_out, args.log,
                              args.config_out, args.regress_out, args.max_flips)
    return 1


if __name__ == "__main__":
    sys.exit(main())