"""渲染 eval 回归测试（v0.2 计划 N3-T3）：5 个内置主题渲染同一份全组件样张。

对应 DoD：
- 5 主题渲染同一 ContentPackage（scripts/run_evals.py 的 RENDER_DOC）；
- 组件门 + HTML 门 + 公众号门全部零 error，任一失败即 eval FAIL。

判分逻辑来自 run_render_eval（内部走 repair_rendered 定向修复并统计轮次）。
"""

import scripts.run_evals as evals


def test_render_eval_covers_all_builtin_themes():
    results = evals.run_render_eval()
    assert [case["case"] for case in results] == [
        f"render/{theme}" for theme in evals.BUILTIN_THEMES
    ]
    assert [case["theme"] for case in results] == list(evals.BUILTIN_THEMES)


def test_render_eval_all_themes_pass_gates():
    results = evals.run_render_eval()
    assert len(results) == 5
    for case in results:
        assert case["ok"], f"主题 {case['theme']} 渲染未过门：{case}"
        assert case["error_types"] == []
        assert "reason" not in case
        assert case["html_bytes"] > 0
        assert case["repair_rounds"] >= 0
