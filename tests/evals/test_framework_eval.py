"""框架 eval 回归测试（v0.2 计划 N3-T4）：7 个写作框架语料全链路三层门禁。

对应 DoD：
- 每框架 1 份 research / brief / draft 样例（_FRAMEWORK_META + 框架语料）；
- content 门 → 组件门 → 渲染 + 修复 → 公众号门，全部零 error。

判分逻辑来自 run_framework_eval；语料位于 tests/evals/cases/frameworks/。
"""

import scripts.run_evals as evals


def test_framework_eval_covers_all_frameworks():
    results = evals.run_framework_eval()
    assert [case["case"] for case in results] == [
        f"framework/{fw_id}" for fw_id in evals.FRAMEWORK_IDS
    ]
    assert [case["framework"] for case in results] == list(evals.FRAMEWORK_IDS)


def test_framework_eval_all_frameworks_pass_full_chain():
    results = evals.run_framework_eval()
    assert len(results) == 7
    for case in results:
        assert case["ok"], f"框架 {case['framework']} 未过全链路门禁：{case}"
        assert case["error_types"] == []
        assert "reason" not in case
        assert case["theme"] in evals.BUILTIN_THEMES
        assert case["html_bytes"] > 0
        assert case["repair_rounds"] >= 0
