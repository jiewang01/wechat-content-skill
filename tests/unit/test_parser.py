"""解析器单测：全节点类型、往返序列化稳定性、node_id 方案、标记错误分类。"""

import re
from pathlib import Path

import pytest

from renderer.ast import (
    CalloutNode,
    CardNode,
    ContentAST,
    ListNode,
    ParseError,
    QuoteNode,
    parse,
    serialize,
)

FULL_DOC = """# 一级标题

普通段落，包含 **加粗** 与 `code`。

## 二级标题

:::note
这是一条说明。
:::

:::quote cite="某工程师"
聊天记录里的原话。
:::

:::callout type="warning" title="注意"
升级前先备份数据。
:::

:::card title="要点" footer="以上三条"
- 第一条
- 第二条
- 第三条
:::

![封面图](https://example.com/cover.png)

```python
print("hello")
```

- 无序列表项
- 另一项

1. 有序项
2. 第二项

---

> 块引用形式的一句话。
"""

NESTED_DOC = """:::card title="嵌套要点" footer="完"
- 文本要点
:::note
嵌套说明。
:::
:::quote cite="嵌套引用人"
嵌套原话。
:::
:::callout type="warning" title="嵌套注意"
嵌套警示。
:::
- 结尾要点
:::
"""


def _strip_ids(ast: ContentAST) -> list[dict]:
    return [node.model_dump(exclude={"node_id"}) for node in ast.nodes]


def test_parse_full_doc_node_sequence():
    ast = parse(FULL_DOC, title="标题", digest="摘要")
    assert [node.type for node in ast.nodes] == [
        "heading",
        "paragraph",
        "heading",
        "note",
        "quote",
        "callout",
        "card",
        "image",
        "code",
        "list",
        "list",
        "hr",
        "quote",
    ]
    assert ast.title == "标题"
    assert ast.digest == "摘要"
    assert ast.word_count > 0


def test_roundtrip_is_stable_across_all_node_types():
    ast1 = parse(FULL_DOC)
    markdown = serialize(ast1)
    ast2 = parse(markdown)
    assert _strip_ids(ast1) == _strip_ids(ast2)
    assert serialize(ast2) == markdown


def test_node_id_scheme_blocks_vs_components():
    ast = parse("# 标题\n\n:::note\n说明\n:::\n\n段落。")
    assert [node.node_id for node in ast.nodes] == ["node_1", "component_1", "node_2"]


def test_marker_attributes_land_on_nodes():
    quote = parse(':::quote cite="张三"\n原话\n:::').nodes[0]
    assert isinstance(quote, QuoteNode)
    assert quote.cite == "张三"

    callout = parse(':::callout type="tip" title="小技巧"\n正文\n:::').nodes[0]
    assert isinstance(callout, CalloutNode)
    assert callout.variant == "tip"
    assert callout.title == "小技巧"

    card = parse(':::card title="清单" footer="完"\n- 一\n- 二\n:::').nodes[0]
    assert isinstance(card, CardNode)
    assert card.title == "清单"
    assert card.footer == "完"
    assert card.items == ["一", "二"]


def test_callout_defaults_to_info_variant():
    callout = parse(":::callout\n正文\n:::").nodes[0]
    assert isinstance(callout, CalloutNode)
    assert callout.variant == "info"
    assert callout.title == ""


def test_blockquote_parses_to_quote_and_serializes_as_marker():
    ast = parse("> 第一行\n> 第二行")
    quote = ast.nodes[0]
    assert isinstance(quote, QuoteNode)
    assert quote.text == "第一行\n第二行"
    assert quote.cite == ""
    assert ":::quote" in serialize(ast)


def test_ordered_list_accepts_chinese_enumerator():
    node = parse("1、第一\n2、第二").nodes[0]
    assert isinstance(node, ListNode)
    assert node.ordered is True
    assert node.items == ["第一", "第二"]


def test_decimal_number_line_is_not_a_list():
    nodes = parse("3.14 是圆周率的近似值。").nodes
    assert nodes[0].type == "paragraph"

    nodes = parse("1.第一").nodes
    assert nodes[0].type == "paragraph"


def test_list_continues_across_blank_line():
    node = parse("- 甲\n\n- 乙").nodes[0]
    assert isinstance(node, ListNode)
    assert node.ordered is False
    assert node.items == ["甲", "乙"]


def test_empty_input():
    ast = parse("")
    assert ast.nodes == []
    assert ast.word_count == 0


def test_serialize_escapes_quotes_in_attributes():
    ast = ContentAST(nodes=[QuoteNode(node_id="component_1", text="原话", cite='他说"你好"')])
    markdown = serialize(ast)
    assert "他说'你好'" in markdown


def test_nested_card_items_mix_strings_and_child_nodes():
    card = parse(NESTED_DOC).nodes[0]
    assert isinstance(card, CardNode)
    assert [type(item).__name__ for item in card.items] == [
        "str",
        "NoteNode",
        "QuoteNode",
        "CalloutNode",
        "str",
    ]
    assert card.items[0] == "文本要点"
    assert card.items[4] == "结尾要点"


def test_nested_children_carry_dotted_node_ids():
    card = parse(NESTED_DOC).nodes[0]
    assert card.node_id == "component_1"
    assert [item.node_id for item in card.items if not isinstance(item, str)] == [
        "component_1.1",
        "component_1.2",
        "component_1.3",
    ]


def test_nested_child_attributes_land_on_nodes():
    card = parse(NESTED_DOC).nodes[0]
    quote, callout = card.items[2], card.items[3]
    assert isinstance(quote, QuoteNode)
    assert quote.cite == "嵌套引用人"
    assert isinstance(callout, CalloutNode)
    assert callout.variant == "warning"
    assert callout.title == "嵌套注意"


def test_nested_children_counted_in_word_count():
    bare = parse(':::card title="要点"\n- 只有文本要点\n:::')
    nested = parse(NESTED_DOC)
    assert nested.word_count > bare.word_count


def test_nested_roundtrip_is_stable():
    ast1 = parse(NESTED_DOC, title="嵌套", digest="往返")
    markdown = serialize(ast1)
    ast2 = parse(markdown)
    assert _strip_ids(ast1) == _strip_ids(ast2)
    assert serialize(ast2) == markdown


@pytest.mark.parametrize(
    ("markdown", "error_type"),
    [
        (":::foo\n内容\n:::", "unknown_component"),
        (':::note foo="x"\n内容\n:::', "unsupported_attribute"),
        (':::callout type="bogus"\n内容\n:::', "invalid_prop_value"),
        (":::note\n没有闭合", "unclosed_marker"),
        ("```python\nprint(1)", "unclosed_code_block"),
        (":::note\n:::quote\n嵌套\n:::\n:::", "invalid_nesting"),
        (":::card\n:::note\n:::quote\n三层\n:::\n:::\n:::", "invalid_nesting"),
        (":::card\n不是列表\n:::", "invalid_card_content"),
        (":::", "stray_marker"),
        ("正文。\n\n:::note foo\n正文。", "invalid_marker_syntax"),
    ],
)
def test_parse_errors_carry_machine_readable_type(markdown: str, error_type: str):
    with pytest.raises(ParseError) as exc_info:
        parse(markdown)
    assert exc_info.value.error_type == error_type
    assert exc_info.value.line >= 1
    assert str(exc_info.value)


def test_native_doc_examples_parse_and_roundtrip():
    """文档即测试：native 技能文档里的 markdown 示例块必须可解析且往返稳定。"""
    root = Path(__file__).resolve().parents[2]
    doc_paths = [
        root / "skills" / "native" / "SKILL.md",
        *(root / "skills" / "native" / "components" / f"{name}.md"
          for name in ("card", "note", "quote", "callout")),
    ]
    checked = 0
    for doc in doc_paths:
        text = doc.read_text(encoding="utf-8")
        blocks = re.findall(r"```markdown\n(.*?)\n```", text, flags=re.DOTALL)
        assert blocks, f"{doc.name} 未找到 markdown 示例块"
        for index, block in enumerate(blocks):
            ast = parse(block)
            markdown = serialize(ast)
            assert _strip_ids(parse(markdown)) == _strip_ids(ast), (
                f"{doc.name} 第 {index + 1} 个示例块往返序列化不稳定"
            )
            checked += 1
    assert checked >= 10
