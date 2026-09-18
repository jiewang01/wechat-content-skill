#!/usr/bin/env python3
"""广告 Skill 决策引擎（M2 可执行版）。

按 knowledge/decision-engine-rules.md 等 5 份规则实现：
  Hard Constraint 先行 → 五维软评分（Revenue/AccountFit/ProductionCost/OpportunityCost/Risk）
  → Decision Score + Confidence → Action 判定 → 结构化 Decision。

用法:
    python3 tools/decision_engine.py servertask-021 <adtask.json> <account.json> [evidence-n.json ...]
    python3 tools/decision_engine.py task-021 --adtask tests/cases/task-021.json --account data/account-example.json
"""
import argparse
import json
import sys
from datetime import datetime, timezone

# ---------- 配置（权重 / 阈值，取自 knowledge/decision-engine-rules.md v1） ----------
W = {"revenue": 0.30, "account_fit": 0.30, "production_cost": 0.15,
     "opportunity_cost": 0.05, "risk": 0.20}
ACCEPT_MIN = 70
OBSERVE_MIN = 50
MIN_LEAD_DAYS = 1
RISK_DOWNGRADE = 45

NEGATIVE_KEYWORDS = ("竞", "禁止", "不可", "不得", "不可以用", "医疗", "保本", "稳赚")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------- 1. Hard Constraints ----------
def hard_constraints(adtask, account) -> list[dict]:
    result = []
    cat = (adtask.get("brand") or {}).get("category")
    rejected = (account.get("commercial") or {}).get("rejected_categories") or []
    if cat and cat in rejected:
        result.append({"constraint": "H1 account_rejects_category", "status": "fail",
                        "detail": f"账号拒绝品类 {cat}"})
    else:
        result.append({"constraint": "H1 account_rejects_category", "status": "pass"})

    plat = adtask.get("source", {}).get("platform")
    if plat and account.get("platform") and plat != account["platform"]:
        result.append({"constraint": "H2 platform_mismatch", "status": "fail",
                        "detail": f"任务平台 {plat} ≠ 账号平台 {account.get('platform')}"})
    else:
        result.append({"constraint": "H2 platform_mismatch", "status": "pass"})

    forbid = set((account.get("content") or {}).get("forbidden_topics") or [])
    mandatory = (adtask.get("campaign") or {}).get("mandatory_points") or []
    clash = [p for p in mandatory if any(f in p for f in forbid) or p in forbid]
    result.append({"constraint": "H3 mandatory_forbidden_clash", "status": "fail" if clash else "pass",
                    "detail": f"冲突要求: {clash}" if clash else None})

    deadline = adtask.get("production", {}).get("deadline")
    lead_ok = True
    if deadline:
        try:
            lead_days = (datetime.fromisoformat(deadline.replace("Z", "+00:00")) - datetime.now(timezone.utc)).days
            lead_ok = lead_days >= MIN_LEAD_DAYS
        except ValueError:
            lead_ok = True
    result.append({"constraint": "H4 deadline_feasible", "status": "pass" if lead_ok else "fail"})

    # H5 合规：高敏品类 + 无合规保护
    sensitive = ("金融", "医美", "财富", "保健")
    compliance_guard = bool((adtask.get("requirements") or {}).get("brand_review")) or \
                       bool((adtask.get("requirements") or {}).get("approval_required"))
    risk_high = bool((adtask.get("risk") or {}).get("policy_risk")) or \
                bool((adtask.get("risk") or {}).get("claim_risk"))
    h5_fail = cat in sensitive and risk_high and not compliance_guard
    result.append({"constraint": "H5 compliance_acceptable", "status": "fail" if h5_fail else "pass"})

    # H6 账号能力门槛（扫描 platform_rules / mandatory_points / special_requirements 中的数字门槛）
    req_texts = (adtask.get("requirements") or {}).get("platform_rules") or []
    req_texts += (adtask.get("campaign") or {}).get("mandatory_points") or []
    req_texts += (adtask.get("production") or {}).get("special_requirements") or []
    gate_hint = any(("播放" in t or "粉丝" in t or "门槛" in t or "≥" in t or "以上" in t) for t in req_texts)
    avg_views = (account.get("performance") or {}).get("avg_views")
    if gate_hint and avg_views is None:
        result.append({"constraint": "H6 capability_gate", "status": "unknown",
                        "detail": "任务含播放/粉丝门槛且账号无 performance 基线，需人工确认"})
    else:
        result.append({"constraint": "H6 capability_gate", "status": "pass"})
    return result


# ---------- 2. 五维软评分 ----------
def score_revenue(adtask, account) -> tuple[float, list, list]:
    com = adtask.get("commercial") or {}
    fee = com.get("creator_fee")
    commission = com.get("commission")
    rule = com.get("settlement_rule") or ""
    unc = []
    if fee is not None:
        s = 50 if fee < 100 else (60 if fee < 500 else 70 if fee < 1500 else 80)
        if commission:
            s = min(s + 10, 95)
    elif commission:
        s = 55
    elif "阅读单价" in rule or "单价" in rule or "按阅读" in rule:
        # CPM：用账号同类基线预估，无基线 ⇒ 中性 + uncertainty
        avg = (account.get("performance") or {}).get("avg_views")
        if avg:
            s = 65 if avg >= 1000 else 60
        else:
            s = 55
            unc.append("CPM 任务无账号阅读基线，预期收入为区间预测")
    elif "置换" in rule or "寄样" in rule or "无稿费" in rule:
        s = 45
        unc.append("实物置换价值需折算，未计现金收入")
    else:  # 未报价 / 需询价
        s = 45
        unc.append("报价未公开")
    return s, [f"计价方式: {fee or commission or rule or 'unknown'}"], unc


def score_account_fit(adtask, account) -> tuple[float, list, list]:
    unc = []
    audience = account.get("audience") or {}
    tags = audience.get("interest_tags") or []
    cat = (adtask.get("brand") or {}).get("category") or ""
    target = (adtask.get("campaign") or {}).get("target_audience") or ""

    # Audience Fit
    af = 50
    if cat:
        af = 55 if any(cat in (t or "") for t in tags) else 45
    if "男粉" in target:
        gd = audience.get("gender_distribution") or {}
        male = gd.get("male")
        # 语义：male 可为比例（如 0.72）或百分比（如 72），按数值量级判断
        male_ratio = male / 100.0 if male and male > 1 else male
        af = 85 if (male_ratio is None and cat == "财富") else (70 if male_ratio and male_ratio > 0.5 else 40)
        if male_ratio is None:
            unc.append("账号性别分布缺失，男粉匹配按品类推断")

    niches = (account.get("content") or {}).get("niches") or []
    cf = 55 if (cat and cat in niches) or not cat else 50

    pref = (account.get("commercial") or {}).get("preferred_categories") or []
    rej = (account.get("commercial") or {}).get("rejected_categories") or []
    bf = 30 if cat in rej else (75 if cat in pref else 60)
    if cat in rej:
        unc.append("命中账号拒绝品类")

    hist = (account.get("performance") or {}).get("historical_campaigns") or []
    hf = 65 if hist else 50
    if not hist:
        unc.append("无同类历史任务样本")

    s = 0.3 * af + 0.3 * cf + 0.2 * bf + 0.2 * hf
    return s, [f"受众匹配评估(品类={cat or '未知'}, 目标人群='{target or '未指定'}')"], unc


def score_production_cost(adtask) -> tuple[float, list, list]:
    prod = adtask.get("production") or {}
    req = adtask.get("requirements") or {}
    special = prod.get("special_requirements") or []
    rev_limit = req.get("revision_limit")
    s = 60
    unc = []
    if prod.get("estimated_hours") is None:
        unc.append("预估工时未写明")
    if rev_limit == 0 or any("代发" in s for s in special):
        s = 85  # 纯素材代发
    elif "到店" in " ".join(special) or "寄拍" in " ".join(special) or "拍摄" in " ".join(special):
        s = 45  # 需外出/寄拍/素材拍摄
    if prod.get("video_required"):
        s -= 5
    if rev_limit is None:
        unc.append("修改轮次未写明")
    return max(s, 20), [f"生产形态评估(特殊要求数={len(special)}, 修改上限={rev_limit})"], unc


def score_opportunity_cost(adtask) -> tuple[float, list, list]:
    prod = adtask.get("production") or {}
    deadline = prod.get("deadline")
    unc = []
    if not deadline:
        s = 65
        unc.append("截止未写明或长窗口，机会成本按中性评估")
    else:
        try:
            lead_days = (datetime.fromisoformat(deadline.replace("Z", "+00:00")) - datetime.now(timezone.utc)).days
            s = 70 if lead_days > 14 else (55 if lead_days > 3 else 40)
        except ValueError:
            s = 60
            unc.append("截止时间格式异常")
    return s, [], unc


def score_risk(adtask) -> tuple[float, list, list]:
    r = adtask.get("risk") or {}
    cat = (adtask.get("brand") or {}).get("category") or ""
    s = 85.0
    unc = []
    sensitive = ("金融", "医美", "财富", "保健")
    if cat in sensitive:
        s -= 25
        unc.append(f"敏感性品类：{cat}")
    if r.get("policy_risk"):
        s -= 15
    if r.get("claim_risk"):
        s -= 10
    if r.get("account_reputation_risk"):
        s -= 5
    if r.get("copyright_risk"):
        s -= 5
    guard = bool((adtask.get("requirements") or {}).get("brand_review")) or \
            bool((adtask.get("requirements") or {}).get("approval_required"))
    if guard:
        s += 10  # 有审核/法务把关是保护
    return max(s, 20), [f"风险类目评估(当前分{s:.0f})"], unc


# ---------- 3. Confidence ----------
def compute_confidence(unknown_in: int, avg_reliability: float = 0.9) -> tuple[float, str, list]:
    # v1 公式（decision-engine-rules.md §3）：
    #   base = 0.75 − 0.06×unknown维度数 + 0.25×平均 Evidence Reliability，夹取 [0.3, 0.95]
    base = 0.75 - 0.06 * unknown_in + 0.25 * avg_reliability
    c = max(0.3, min(0.95, base))
    level = "low" if c < 0.4 else ("medium" if c < 0.7 else "high")
    return c, level, []


# ---------- 4. 引擎 ----------
ACCOUNT_BY_PLATFORM = {
    "公众号": "data/account-example.json",
    "小红书": "data/account-example-xhs.json",
    "抖音": "data/account-example-dy.json",
    "知乎": "data/account-example-zh.json",
    "B站": "data/account-example-bz.json",
}


def select_account(adtask) -> dict:
    """按任务平台自动选择示例账号（无命中平台则回退小红书）。"""
    plat = adtask.get("source", {}).get("platform") or "小红书"
    path = ACCOUNT_BY_PLATFORM.get(plat, "data/account-example-xhs.json")
    return load_json(path)


def build_decision(adtask, account, evidence_list=None) -> dict:
    evidence_list = evidence_list or []
    ev_refs = [e.get("evidence_id") for e in evidence_list if e.get("evidence_id")]

    hc = hard_constraints(adtask, account)
    failed = [h for h in hc if h["status"] == "fail"]

    rev, rev_note, rev_unc = score_revenue(adtask, account)
    fit, fit_note, fit_unc = score_account_fit(adtask, account)
    cost, cost_note, cost_unc = score_production_cost(adtask)
    opp, opp_note, opp_unc = score_opportunity_cost(adtask)
    risk, risk_note, risk_unc = score_risk(adtask)

    score = round(W["revenue"] * rev + W["account_fit"] * fit + W["production_cost"] * cost
                  + W["opportunity_cost"] * opp + W["risk"] * risk, 1)

    all_unc = rev_unc + fit_unc + cost_unc + opp_unc + risk_unc
    unknown_dim = len(all_unc)
    confidence, c_level, _ = compute_confidence(unknown_dim)

    # Action 判定（reject > need_information(未知约束/缺收益) > accept/observe）
    unknown_hc = [h for h in hc if h["status"] == "unknown"]
    blockers = [(h.get("detail") or h["constraint"]) for h in failed]
    if failed:
        action = "reject"
    elif unknown_hc:
        action = "need_information"
        blockers.extend([(h.get("detail") or h["constraint"]) for h in unknown_hc])
    elif (adtask.get("commercial") or {}).get("creator_fee") is None and \
         not (adtask.get("commercial") or {}).get("settlement_rule"):
        action = "need_information"
        blockers.append("关键收益信息缺失（无固定费且无结算规则）")
    elif score >= ACCEPT_MIN:
        if risk < RISK_DOWNGRADE:
            action = "observe"
            blockers.append(f"风险维度偏低({risk:.0f})，触发观察")
        else:
            action = "accept"
    elif score >= OBSERVE_MIN:
        action = "observe"
    else:
        action = "reject"

    next_actions = {
        "accept": ["生成 Campaign Brief", "确认品牌审核规则"],
        "observe": ["补齐缺失信息后再决策", "确认账号是否有同类历史样本"],
        "reject": ["记录拒绝原因入回归用例"],
        "need_information": ["确认账号 performance 基线（播放/粉丝门槛）", "确认报酬结构（固定/CPM/置换）", "确认硬性门槛是否满足"],
    }[action]

    reasons = []
    reasons.append({"statement": f"收益维度 {rev:.0f} 分：{(';'.join(rev_note))}", "evidence_refs": ev_refs or ["EVD-UNKNOWN"]})
    reasons.append({"statement": f"账号匹配 {fit:.0f} 分：{(';'.join(fit_note))}", "evidence_refs": ev_refs or ["EVD-UNKNOWN"]})
    for u in all_unc[:3]:
        reasons.append({"statement": f"不确定性：{u}", "evidence_refs": ev_refs or ["EVD-UNKNOWN"]})
    if failed:
        reasons.append({"statement": f"触发硬约束：{';'.join(d['constraint'] for d in failed)}", "evidence_refs": ev_refs or ["EVD-UNKNOWN"]})

    decision = {
        "decision_id": "DEC-20260918-0001",
        "task_id": adtask.get("task_id"),
        "action": action,
        "decision_score": score,
        "dimensions": {
            "revenue": round(rev), "account_fit": round(fit),
            "production_cost": round(cost), "opportunity_cost": round(opp), "risk": round(risk),
        },
        "reasons": reasons,
        "blockers": blockers,
        "next_actions": next_actions,
        "confidence": {"value": confidence, "status": c_level, "evidence_refs": ev_refs,
                        "uncertainty_reasons": all_unc[:5]},
        "evidence_refs": ev_refs,
        "hard_constraints": hc,
        "created_at": now_iso(),
    }
    return decision


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id", nargs="?", default="")
    ap.add_argument("--adtask", required=False)
    ap.add_argument("--account", required=False)
    ap.add_argument("--evidence", nargs="*", default=[])
    ap.add_argument("--out", default=None)
    ap.add_argument("--batch", action="store_true", help="批量跑 tests/cases/*.json，按平台选账号，输出 tests/decisions/")
    ap.add_argument("--no-baseline", action="store_true",
                    help="对抗回归：所有用例改用最小账号 data/account-minimal.json（无 performance 基线），验证 need_information")
    ap.add_argument("--config", default=None,
                    help="权重配置 JSON（自适应校准产物 tools/engine_config.json），覆盖内置 W；缺省用内置权重")
    args = ap.parse_args()

    if args.config:
        cfg = load_json(args.config)
        W.update(cfg.get("weights") or {})  # 校准落配置：显式传入才生效（M02/A13 人工 gate）

    if args.batch:
        import pathlib
        out_dir = pathlib.Path("tests/decisions")
        if args.no_baseline:
            out_dir = pathlib.Path("tests/decisions_nobaseline")
        out_dir.mkdir(exist_ok=True)
        summary = []
        for p in sorted(pathlib.Path("tests/cases").glob("task-*.json")):
            case = load_json(p)
            adtask = case["expected_adtask"]
            evs = case.get("expected_evidence") or []
            account = load_json("data/account-minimal.json") if args.no_baseline else select_account(adtask)
            d = build_decision(adtask, account, evs)
            out = out_dir / f"{p.stem}.decision.json"
            with open(out, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            summary.append((p.stem, d["action"], d["decision_score"],
                            round(d["confidence"]["value"], 2), d.get("blockers", [])))
        print(f"{'case':12} {'action':16} {'score':>6} {'conf':>6}  blockers")
        for row in summary:
            print(f"{row[0]:12} {row[1]:16} {row[2]:6.1f} {row[3]:6.2f}  {row[4]}")
        return 0

    assert args.adtask and args.account, "--batch 之外需要 --adtask 与 --account"
    adtask = load_json(args.adtask)
    account = load_json(args.account)
    evs = [load_json(p) for p in args.evidence]
    if not evs:
        # 用例文件内嵌 expected_evidence 时自动装载，保证回溯链
        case = load_json(args.adtask)
        if "expected_adtask" in case:
            adtask = case["expected_adtask"]
        if case.get("expected_evidence"):
            evs = case["expected_evidence"]

    decision = build_decision(adtask, account, evs)
    out = args.out
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(decision, f, ensure_ascii=False, indent=2)
        print(f"decision written to {out}")
    else:
        print(json.dumps(decision, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())