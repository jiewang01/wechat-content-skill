#!/usr/bin/env python3
"""广告 Skill 内容生产工具（M3）：Decision → CampaignBrief → Draft → Self Review。

按 knowledge/brief-generator-rules.md、content-strategy-rules.md、self-review-rules.md 执行。
纯规则化骨架：无固定模板匹配时输出通用框架并标注"待人工补全/审核"。

用法:
    python3 tools/brief_generator.py --brief \
        --adtask tests/cases/task-XXX.json --account data/account-example.json \
        --decision tests/decisions/task-XXX.decision.json --out tests/task-XXX.brief.json
    （--draft 增加草稿与自检输出；无 --out 时打印到终端）
"""
import argparse
import json
import sys
from datetime import datetime, timezone

PLATFORM_STYLE = {
    "公众号": "温和科普、结构化图文、以财经知识切入降低广告感",
    "小红书": "真实种草、场景化、口语化、带话题标签",
    "抖音": "快节奏口播、前3秒钩子、字幕强化卖点",
    "知乎": "专业客观、长文回答、逻辑链完整",
    "B站": "深度测评、参数实测、长视频脚本分段",
}

NOW = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_case(case_or_task):
    """支持直接传入 test-case 文件（自动取 expected_adtask）。"""
    if isinstance(case_or_task, dict) and "expected_adtask" in case_or_task:
        return case_or_task["expected_adtask"], case_or_task.get("expected_evidence") or []
    return case_or_task, []


def build_brief(adtask, account, decision, ev_refs) -> dict:
    campaign = adtask.get("campaign") or {}
    brand = adtask.get("brand") or {}
    account_content = account.get("content") or {}
    account_com = account.get("commercial") or {}
    risk = adtask.get("risk") or {}
    req = adtask.get("requirements") or {}
    plat = adtask.get("source", {}).get("platform") or "公众号"

    mandatory = campaign.get("mandatory_points") or []
    forbidden = campaign.get("forbidden_points") or []
    cat = (brand.get("category") or "").strip()
    usp = (campaign.get("key_messages") or [])[:4]
    if usp == [] and brand.get("product"):
        usp = [f"{brand['product']} 核心信息" ]

    # Content Strategy：三角度 + 选择（按历史同类先验 + 生产成本）
    angles = [
        ("A-人群共鸣", "从目标人群关注点切入（男粉/财富信息需求）", 0.6),
        ("B-产品差异", "围绕产品 USP 单点放大", 0.8 if usp else 0.4),
        ("C-场景植入", "从日常理财/阅读场景自然植入", 0.7),
    ]
    # historical 先验：账号历史涉及测评/科普类则加权对应角度
    hist = "".join((account.get("performance") or {}).get("historical_campaigns") or [])
    if "科普" in hist or "测评" in hist:
        angles[2] = (angles[2][0], angles[2][1], min(angles[2][2] + 0.1, 0.95))
    chosen = max(angles, key=lambda a: a[2])

    # target_audience：优先任务明确人群；否则由账号画像导出自然语言描述
    ta = campaign.get("target_audience")
    if not ta or "：" in ta:
        gender = (account.get("audience") or {}).get("gender_distribution") or {}
        male = gender.get("male")
        gender_desc = "男粉为主" if male and (male > 50 or male > 0.5) else "女性为主"
        ta = f"{gender_desc}、关注{cat or '该品类'}信息的公众号读者"
    risk_checklist = []
    if forbidden:
        risk_checklist.append("禁用点：%s" % "；".join(forbidden))
    if risk.get("policy_risk"):
        risk_checklist.append(f"政策风险：{risk['policy_risk']}")
    if risk.get("claim_risk"):
        risk_checklist.append(f"宣称风险：{risk['claim_risk']}")
    if risk.get("account_reputation_risk"):
        risk_checklist.append(f"账号声誉：{risk['account_reputation_risk']}")
    if req.get("approval_required"):
        risk_checklist.append("发布前需品牌/法务审核")
    unknown_notes = [u for u in (decision.get("confidence") or {}).get("uncertainty_reasons", [])]
    if unknown_notes:
        risk_checklist.append("待确认项：%s" % "；".join(unknown_notes[:3]))

    return {
        "brief_id": "BRF-20260918-0001",
        "task_id": adtask.get("task_id"),
        "decision_id": decision.get("decision_id"),
        "campaign_objective": campaign.get("objective") or "结合决策维度推断的传播目标（人工确认）",
        "target_audience": ta,
        "product_usp": usp,
        "mandatory_claims": mandatory,
        "forbidden_claims": forbidden,
        "content_angle": chosen[0],
        "hook": "用一句与读者利益强相关的话开场（草稿阶段人工打磨）",
        "storyline": f"采用角度「{chosen[0]}」：{chosen[1]}",
        "cta": "引导至官方承接位/链接（按任务要求：官方短链或组件，禁止私域导流）",
        "platform_style": PLATFORM_STYLE.get(plat, "按平台惯例"),
        "account_style": account_content.get("style") or "账号既定风格",
        "risk_checklist": risk_checklist,
        "evidence_refs": ev_refs,
        "angle_alternatives": [a[0] for a in angles if a[0] != chosen[0]],
        "preferred_categories_hint": account_com.get("preferred_categories") or [],
        "created_at": now_iso(),
    }


def build_draft(brief, adtask) -> dict:
    """按 Brief 生成草稿骨架（文字由规则模板 + 占位组成，需人工补全）。"""
    brand = adtask.get("brand") or {}
    brand_name = brand.get("name") or "品牌"
    product = brand.get("product") or "产品"

    claims = brief["mandatory_claims"]
    claim_block = "；".join(claims) if claims else "（按任务要求补充必选点）"
    forb = "；".join(brief["forbidden_claims"]) if brief["forbidden_claims"] else "无（按任务核对）"

    body = (
        f"# 草稿（DRAFT — 需人工补全并审核）\n\n"
        f"标题（待拟定）：关于{product}，理性财富信息你需要知道的 N 件事\n\n"
        f"正文骨架：\n"
        f"1. 开头钩子：{brief['hook']}\n"
        f"2. 主体段落：围绕「{brief['content_angle']}」展开，必须覆盖：{claim_block}\n"
        f"3. 风险红线：禁止出现 {forb}\n"
        f"4. 结尾 CTA：{brief['cta']}\n\n"
        f"风格：{brief['platform_style']}；账号调性：{brief['account_style']}。\n"
        f"字数：按任务要求（当前任务未明确时 600-800 字）。"
    )
    return {
        "draft_id": "DRF-20260918-0001",
        "task_id": adtask.get("task_id"),
        "brief_id": brief["brief_id"],
        "brand": brand_name,
        "product": product,
        "format": "公众号图文（约 600-800 字）",
        "content": body,
        "is_draft": True,
        "generated_at": now_iso(),
    }


def self_review(draft, brief, adtask) -> dict:
    items = []
    mandatory_needed = brief["mandatory_claims"]
    # Requirement Check：草稿骨架显式列出了 claim_block ⇒ 规则 PASS，实际需人工复核正文
    req_status = "WARN" if not mandatory_needed else "PASS"
    items.append({"check": "Requirement", "status": req_status,
                  "note": "必选点已列入骨架；正文漏点需人工复核（plan §5.6 核心指标）"})

    forbidden_hit = [f for f in brief["forbidden_claims"] if f and f in draft["content"]]
    items.append({"check": "Claim", "status": "FAIL" if forbidden_hit else "WARN",
                  "note": f"草稿为骨架，宣称合规需逐句核对；禁用点：{ '；'.join(brief['forbidden_claims']) if brief['forbidden_claims'] else '无' }"})

    plat = adtask.get("source", {}).get("platform") or "公众号"
    items.append({"check": "Platform", "status": "PASS" if plat in PLATFORM_STYLE else "WARN",
                  "note": f"已套用 {plat} 风格约定"})

    items.append({"check": "Brand", "status": "WARN", "note": "品牌名/产品事实待人工核对（ad 主未署名场景）"})
    items.append({"check": "Account Style", "status": "PASS" if brief["account_style"] else "WARN",
                  "note": f"账号风格：{brief['account_style'] or '未配置'}"})

    has_fail = any(i["status"] == "FAIL" for i in items)
    has_warn = any(i["status"] == "WARN" for i in items)
    return {
        "review_id": "SRV-20260918-0001",
        "task_id": adtask.get("task_id"),
        "result": "FAIL" if has_fail else ("WARN_PASS" if has_warn else "PASS"),
        "items": items,
        "human_review_required": True,
        "gate": "需人工审核后方可发布（plan §5.5）",
        "reviewed_at": now_iso(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adtask", required=True)
    ap.add_argument("--account", required=True)
    ap.add_argument("--decision", required=True)
    ap.add_argument("--brief-out", default=None)
    ap.add_argument("--draft", action="store_true", help="同时生成 draft 与 self-review")
    ap.add_argument("--draft-out", default=None)
    args = ap.parse_args()

    adtask_raw = load_json(args.adtask)
    account = load_json(args.account)
    decision = load_json(args.decision)
    adtask, ev_list = resolve_case(adtask_raw)
    ev_refs = decision.get("evidence_refs") or [e.get("evidence_id") for e in ev_list]

    brief = build_brief(adtask, account, decision, ev_refs)
    if args.brief_out:
        with open(args.brief_out, "w", encoding="utf-8") as f:
            json.dump(brief, f, ensure_ascii=False, indent=2)
        print("brief written to", args.brief_out)
    else:
        print(json.dumps(brief, ensure_ascii=False, indent=2))

    if args.draft:
        draft = build_draft(brief, adtask)
        review = self_review(draft, brief, adtask)
        if args.draft_out:
            with open(args.draft_out, "w", encoding="utf-8") as f:
                json.dump({"brief": brief, "draft": draft, "self_review": review},
                          f, ensure_ascii=False, indent=2)
            print("draft+review written to", args.draft_out)
        else:
            print(json.dumps({"draft": draft, "self_review": review}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())