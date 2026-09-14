"""渲染 eval 回归测试（v0.2 计划 N3-T3；v0.3 N1-T8 扩展嵌套样张）。

对应 DoD：
- 全组件样张（RENDER_DOC）+ 嵌套样张（tests/evals/cases/render_nested.md）
  各在全部内置主题下渲染；
- 组件门 + HTML 门 + 公众号门全部零 error，任一失败即 eval FAIL。

判分逻辑来自 run_render_eval（内部走 repair_rendered 定向修复并统计轮次）。
"""

import scripts.run_evals as evals


def test_render_eval_covers_all_builtin_themes():
    results = evals.run_render_eval()
    assert [case["case"] for case in results] == [
        f"render/{theme}" for theme in evals.BUILTIN_THEMES
    ] + [f"render_nested/{theme}" for theme in evals.BUILTIN_THEMES]
    assert [case["theme"] for case in results] == list(evals.BUILTIN_THEMES) * 2


def test_render_eval_all_themes_pass_gates():
    results = evals.run_render_eval()
    assert len(results) == len(evals.BUILTIN_THEMES) * 2
    for case in results:
        assert case["ok"], f"主题 {case['theme']} 渲染未过门：{case}"
        assert case["error_types"] == []
        assert "reason" not in case
        assert case["html_bytes"] > 0
        assert case["repair_rounds"] >= 0


def test_render_eval_nested_cases_cover_child_components():
    """嵌套样张用例名以 render_nested/ 前缀区分，且逐主题成对出现。"""
    results = evals.run_render_eval()
    nested = [case for case in results if case["case"].startswith("render_nested/")]
    assert len(nested) == len(evals.BUILTIN_THEMES)
    assert {case["theme"] for case in nested} == set(evals.BUILTIN_THEMES)
