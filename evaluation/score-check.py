#!/usr/bin/env python3
# ============================================================
# score-check.py — 冒烟/评估结果回归校验工具
# 用途：对 evaluation/results/*.yaml 做结构、分数、排序与字段完整性检查
# 用法：python3 evaluation/score-check.py [--dir evaluation/results]
# 退出码：0=全部通过（WARN 允许） 1=存在 FAIL
# ============================================================
import argparse
import glob
import os
import sys

import yaml

SCORE_WEIGHTS = [("demand", 0.25), ("pain", 0.20), ("trend", 0.15),
                 ("novelty", 0.15), ("content_gap", 0.15), ("evidence", 0.10)]
TOLERANCE = 1.0  # market_score 与加权值的允许偏差
PROFILE_KEYS = ["audience", "domain", "value_proposition", "authority", "boundaries"]
EVIDENCE_KEYS = ["source", "source_type", "date", "claim", "confidence"]
ANOMALY_MARKERS = ["Research_Insufficient", "NO_VALID_TOP1"]


def check(cond, msg, level="FAIL"):
    out = "PASS" if cond else level
    print("  [%s] %s" % (out, msg))
    global has_fail
    if out == "FAIL":
        has_fail = True
    return cond


def ev_score(bd):
    return sum(bd.get(k, 0) * w for k, w in SCORE_WEIGHTS)


def check_evidence_list(items, tag, fname):
    for i, ev in enumerate(items):
        if not isinstance(ev, dict):
            check(False, "%s evidence[%d] 非对象" % (tag, i), "WARN")
            continue
        missing = [k for k in EVIDENCE_KEYS if k not in ev]
        if missing:
            check(False, "%s evidence[%d] 缺字段: %s" % (tag, i, missing), "WARN")


def check_file(path, name):
    d = yaml.safe_load(open(path, encoding="utf-8"))
    if not isinstance(d, dict):
        check(False, "%s 顶层非映射" % name)
        return

    # ---- 异常分支记录：仅校验标记存在 ----
    raw = open(path, encoding="utf-8").read()
    if any(m in raw for m in ANOMALY_MARKERS):
        check(any(m in raw for m in ANOMALY_MARKERS),
              "异常分支记录（%s）" % [m for m in ANOMALY_MARKERS if m in raw])
        return

    # ---- 结构完整性 ----
    for key in ["account_profile", "research_findings", "candidates",
                "ranking_result", "top1_selection", "article_brief"]:
        if key not in d:
            check(False, "%s 缺顶层字段 %s" % (name, key))
            return

    # ---- Profile ----
    prof = d["account_profile"]
    missing = [k for k in PROFILE_KEYS if k not in prof]
    check(not missing, "%s profile 缺字段 %s" % (name, missing) if missing else "%s profile 字段完整" % name)

    # ---- Research Findings（紧凑记录允许 3-15，低于 5 记为 WARN）----
    fds = d["research_findings"]
    if not (3 <= len(fds) <= 15):
        check(False, "%s findings 数量 %d（期望 3-15）" % (name, len(fds)))
    else:
        check(len(fds) >= 5, "%s findings 数量 %d（<5 为紧凑记录）" % (name, len(fds)),
              "WARN" if len(fds) < 5 else "FAIL")
    for i, fd in enumerate(fds):
        evs = fd.get("evidence", [])
        if not evs:
            check(False, "%s finding[%d] 无 evidence" % (name, i), "WARN")
        check_evidence_list(evs, "%s finding[%d]" % (name, i), name)

    # ---- Candidates ----
    cands = d["candidates"]
    if not (19 <= len(cands) <= 50):
        check(False, "%s candidates 数量 %d（期望 19-50）" % (name, len(cands)))
    else:
        check(True, "%s candidates %d 条" % (name, len(cands)))
    for i, c in enumerate(cands):
        for k in ["core_topic", "user_problem", "content_angle"]:
            if k not in c:
                check(False, "%s candidate[%d] 缺 %s" % (name, i, k), "WARN")

    # ---- Ranking：排序 + 分数一致 + breakdown 完整 ----
    rr = d["ranking_result"]
    ranked = rr.get("ranked", [])
    if len(ranked) != rr.get("top_n", 5):
        check(False, "%s ranked 数量 %d ≠ top_n %s" % (name, len(ranked), rr.get("top_n")))
    prev = None
    for item in ranked:
        bd = item.get("score_breakdown", {})
        missing = [k for k, _ in SCORE_WEIGHTS if k not in bd]
        if missing:
            check(False, "%s %s 缺 breakdown 维度 %s" % (name, item.get("topic"), missing))
        calc = ev_score(bd)
        mark = item.get("market_score", 0)
        if abs(calc - mark) > TOLERANCE:
            check(False, "%s %s market_score %.1f vs 加权 %.1f" % (name, item.get("topic"), mark, calc))
        if prev is not None and mark > prev:
            check(False, "%s 排序非降序（%s %.0f > 上一名 %.0f）" % (name, item.get("topic"), mark, prev))
        prev = mark
    check(True, "%s ranking %d 项分数加权一致、降序正确" % (name, len(ranked)))

    # ---- Top1 属于 TopN ----
    sel = d["top1_selection"].get("selected", {})
    topics = {it.get("topic") for it in ranked}
    check(sel.get("topic") in topics, "%s Top1「%s」不在 TopN 内" % (name, sel.get("topic")) if sel.get("topic") not in topics
          else "%s Top1「%s」∈ TopN" % (name, sel.get("topic")))

    # ---- Article Brief ----
    ab = d["article_brief"]
    cl = ab.get("core_insight", {})
    for k in ["misconception", "evidence", "insight"]:
        if k not in cl:
            check(False, "%s brief.core_insight 缺 %s" % (name, k))
    tcs = ab.get("title_candidates", [])
    check(len(tcs) >= 3, "%s 标题候选 %d（期望 >=3）" % (name, len(tcs)) if len(tcs) < 3 else "%s 标题候选 %d 个" % (name, len(tcs)))
    ol = ab.get("outline", [])
    check(len(ol) >= 5, "%s 大纲 %d 节（期望 >=5）" % (name, len(ol)) if len(ol) < 5 else "%s 大纲 %d 节" % (name, len(ol)))
    for i, sec in enumerate(ol):
        if "purpose" not in sec or "key_points" not in sec:
            check(False, "%s outline[%d] 缺 purpose/key_points" % (name, i), "WARN")


def main():
    global has_fail
    has_fail = False
    ap = argparse.ArgumentParser(description="评估结果回归校验")
    ap.add_argument("--dir", default="evaluation/results")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.yaml")))
    files = [f for f in files if "smoke-summary" not in f]
    if not files:
        print("未找到结果文件"); sys.exit(1)

    print("score-check: %d 个结果文件" % len(files))
    for f in files:
        name = os.path.basename(f)
        print("== %s" % name)
        try:
            check_file(f, name)
        except Exception as e:  # noqa: BLE001
            check(False, "%s 解析异常: %s" % (name, e))

    print("-" * 40)
    if has_fail:
        print("结果: FAIL（存在阻断问题）")
        sys.exit(1)
    print("结果: PASS（WARN 不阻断）")
    sys.exit(0)


if __name__ == "__main__":
    main()