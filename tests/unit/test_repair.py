"""修复循环单测（蓝图十章，计划 M4-T4，约束 H3/H4/H6）。

三条主线：
1. 定向修复：unsupported_css 两类修复（受限取值→回退值、白名单外属性→删除声明），
   只动 issue 归属段（H3），一轮内清理段内全部出现；
2. 循环控制：轮数 ≤3（H4）、越界抛 ValueError、无可修复项提前终止、
   无确定性修复手段的错误原样保留在最终 ErrorReport（gate="render"）；
3. 归属契约：段 node_id 是错误归属的唯一事实来源（覆盖 lint 提供的 node）；
   富语义文档走完整闭环零修复零误报（H8 渲染器锚定的下游复验）。
"""

from __future__ import annotations

import pytest

from core.artifacts.models import ValidationIssue
from core.workflow.repair import HtmlSegment, Linter, repair_document, repair_rendered
from renderer.ast import parse
from renderer.html import HtmlRenderer
from validators.html import lint_html

RICH_DOC = """# 标题一

普通段落，含 **加粗**、*斜体*、`code` 与 [链接](https://example.com)。

:::note
说明文字。
:::

:::quote cite="张三"
原话内容。
:::

:::callout type="warning" title="注意"
警告正文。
:::

:::card title="要点卡" footer="完"
- 要点一
- 要点二
:::

![配图](https://example.com/i.png)

```python
x = 1
y = 2
```

- 项目甲
- 项目乙

1. 步骤一
2. 步骤二

---

> 引用块形式。
"""


def make_segments(count: int = 18) -> list[HtmlSegment]:
    """构造 count 个合规段：component_1..component_N。"""
    return [
        HtmlSegment(f"component_{i}", f'<section style="display:block;">组件 {i}</section>')
        for i in range(1, count + 1)
    ]


def staged_lint(properties: list[str]) -> Linter:
    """每次验证弹出一个预置问题，模拟逐轮才暴露的存量非法声明。"""
    queue = list(properties)

    def lint(html: str) -> list[ValidationIssue]:
        if not queue:
            return []
        return [ValidationIssue(type="unsupported_css", property=queue.pop(0))]

    return lint


def test_clean_segments_pass_without_repair():
    """合规段不触发修复：0 轮、无修复节点、html 为原样拼接。"""
    segments = make_segments()
    outcome = repair_document(segments)
    assert outcome.report.status == "passed"
    assert outcome.report.gate == "render"
    assert outcome.rounds == 0
    assert outcome.repaired_nodes == []
    assert outcome.html == "\n".join(s.html for s in segments)


def test_dod_unsupported_css_at_component_17():
    """DoD：component_17 的 unsupported_css 只改该节点即复检通过。"""
    segments = make_segments()
    untouched = [s.html for s in segments]
    bad = '<section style="display:grid;gap:10px;">网格布局</section>'
    segments[16] = HtmlSegment("component_17", bad)
    outcome = repair_document(segments)

    assert outcome.report.status == "passed"
    assert outcome.rounds == 1
    assert outcome.repaired_nodes == ["component_17"]
    assert outcome.segments[16].html == '<section style="display:block;">网格布局</section>'
    for position, html in enumerate(untouched):
        if position != 16:
            assert outcome.segments[position].html == html
    assert lint_html(outcome.html) == []


def test_restricted_value_replaced_with_fallback():
    """受限取值 display:grid → 回退值 display:block（网格布局标准降级）。"""
    html = '<section style="display:grid;">标题</section>'
    outcome = repair_document([HtmlSegment("component_1", html)])
    assert outcome.report.status == "passed"
    assert outcome.segments[0].html == '<section style="display:block;">标题</section>'


def test_unsupported_prop_dropped_but_others_kept():
    """白名单外属性 position:fixed 删除，合规声明保留。"""
    html = '<section style="color:#333;position:fixed;margin-top:10px;">正文</section>'
    outcome = repair_document([HtmlSegment("component_1", html)])
    assert outcome.report.status == "passed"
    fixed = '<section style="color:#333;margin-top:10px;">正文</section>'
    assert outcome.segments[0].html == fixed


def test_style_attribute_removed_when_empty():
    """删除声明后 style 为空 → 连属性一并移除。"""
    html = '<section style="position:fixed;">提示</section>'
    outcome = repair_document([HtmlSegment("component_1", html)])
    assert outcome.report.status == "passed"
    assert outcome.segments[0].html == "<section>提示</section>"


def test_multiple_occurrences_fixed_in_one_pass():
    """同一节点内多处非法声明一轮清理，repaired_nodes 去重。"""
    html = '<section style="display:grid;">a</section><section style="display:grid;">b</section>'
    outcome = repair_document([HtmlSegment("component_1", html)])
    assert outcome.report.status == "passed"
    assert outcome.rounds == 1
    assert outcome.repaired_nodes == ["component_1"]
    fixed = '<section style="display:block;">a</section><section style="display:block;">b</section>'
    assert outcome.segments[0].html == fixed


def test_multiple_issue_types_repaired_in_one_round():
    """同段两类 unsupported_css（白名单外 + 受限取值）并入同一轮修复。"""
    html = '<section style="position:fixed;display:grid;">x</section>'
    outcome = repair_document([HtmlSegment("component_1", html)])
    assert outcome.report.status == "passed"
    assert outcome.rounds == 1
    assert outcome.segments[0].html == '<section style="display:block;">x</section>'


def test_unrepairable_error_kept_and_attributed():
    """forbidden_tag 无确定性修复手段：原样留档并归属到段节点。"""
    outcome = repair_document([HtmlSegment("component_3", "<div>违规</div>")])
    assert outcome.report.status == "failed"
    assert outcome.rounds == 0
    assert outcome.repaired_nodes == []
    assert [e.type for e in outcome.report.errors] == ["forbidden_tag"]
    assert outcome.report.errors[0].node == "component_3"
    assert outcome.segments[0].html == "<div>违规</div>"


def test_mixed_repairable_and_unrepairable():
    """可修复段修好、不可修复段字节不变，整体仍 failed。"""
    segments = [
        HtmlSegment("component_1", '<section style="display:grid;">a</section>'),
        HtmlSegment("component_2", "<div>b</div>"),
    ]
    outcome = repair_document(segments)
    assert outcome.report.status == "failed"
    assert outcome.rounds == 1
    assert outcome.repaired_nodes == ["component_1"]
    assert outcome.segments[0].html == '<section style="display:block;">a</section>'
    assert outcome.segments[1].html == "<div>b</div>"
    assert [e.node for e in outcome.report.errors] == ["component_2"]


def test_lint_node_overridden_by_segment_attribution():
    """段 node_id 是错误归属唯一事实来源：覆盖 lint 返回的 node。"""

    def fake_lint(html: str) -> list[ValidationIssue]:
        if "display:grid" in html:
            return [
                ValidationIssue(
                    type="unsupported_css", node="component_999", property="display:grid"
                )
            ]
        return []

    outcome = repair_document(
        [HtmlSegment("component_1", '<section style="display:grid;">x</section>')],
        lint=fake_lint,
    )
    assert outcome.report.status == "passed"
    assert outcome.rounds == 1
    assert outcome.repaired_nodes == ["component_1"]


def test_rounds_capped_at_max():
    """存量问题多于预算：3 轮封顶后仍 failed，剩余问题留档（H4）。"""
    html = '<section style="position:fixed;top:10px;left:5px;right:5px;">x</section>'
    outcome = repair_document(
        [HtmlSegment("component_1", html)],
        lint=staged_lint(["position:fixed", "top:10px", "left:5px", "right:5px"]),
    )
    assert outcome.report.status == "failed"
    assert outcome.rounds == 3
    assert [e.property for e in outcome.report.errors] == ["right:5px"]
    assert "right:5px" in outcome.segments[0].html
    assert "position:fixed" not in outcome.segments[0].html


def test_rounds_use_full_budget_then_pass():
    """存量问题恰好用满预算：3 轮修复后复检通过。"""
    html = '<section style="position:fixed;top:10px;left:5px;">x</section>'
    outcome = repair_document(
        [HtmlSegment("component_1", html)],
        lint=staged_lint(["position:fixed", "top:10px", "left:5px"]),
    )
    assert outcome.report.status == "passed"
    assert outcome.rounds == 3
    assert outcome.segments[0].html == "<section>x</section>"


def test_max_rounds_bounds_enforced():
    """max_rounds 越界（<1 或 >3）直接 ValueError（H4）。"""
    segment = make_segments(1)
    with pytest.raises(ValueError, match="H4"):
        repair_document(segment, max_rounds=0)
    with pytest.raises(ValueError, match="H4"):
        repair_document(segment, max_rounds=4)
    assert repair_document(segment, max_rounds=1).report.status == "passed"
    assert repair_document(segment, max_rounds=3).report.status == "passed"


def test_duplicate_node_id_rejected():
    """段 node_id 重复会让归属歧义，直接 ValueError。"""
    segments = [
        HtmlSegment("component_1", "<section>a</section>"),
        HtmlSegment("component_1", "<section>b</section>"),
    ]
    with pytest.raises(ValueError, match="重复"):
        repair_document(segments)


def test_render_reuses_render_segments_body():
    """render() 与 render_segments() 同源：正文逐字节一致，归属不漂移。"""
    ast = parse(RICH_DOC)
    renderer = HtmlRenderer()
    rendered = renderer.render(ast)
    body = "\n".join(chunk for _, chunk in renderer.render_segments(ast))
    assert rendered.endswith("\n" + body + "\n</section>")


def test_rendered_pipeline_zero_rounds_on_clean_ast():
    """富语义文档完整闭环：渲染即合规，0 修复 0 误报（H8 锚定下游复验）。"""
    ast = parse(RICH_DOC)
    renderer = HtmlRenderer()
    outcome = repair_rendered(ast, renderer)
    assert outcome.report.status == "passed"
    assert outcome.rounds == 0
    assert outcome.repaired_nodes == []
    assert [(s.node_id, s.html) for s in outcome.segments] == list(renderer.render_segments(ast))
    assert lint_html(outcome.html) == []
