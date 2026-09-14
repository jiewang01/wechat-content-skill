"""ContentAST 节点定义：渲染管线的中间表示（LLM 与 HTML 之间的隔离层）。

每个节点携带稳定 node_id（块级 node_N / 组件 component_N），
对抗修复循环据此做节点级定向修复（H3）。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _ASTNodeBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str


class HeadingNode(_ASTNodeBase):
    type: Literal["heading"] = "heading"
    level: int = Field(ge=1, le=6)
    text: str


class ParagraphNode(_ASTNodeBase):
    type: Literal["paragraph"] = "paragraph"
    text: str


class QuoteNode(_ASTNodeBase):
    type: Literal["quote"] = "quote"
    text: str
    cite: str = ""


class NoteNode(_ASTNodeBase):
    type: Literal["note"] = "note"
    text: str


class CalloutNode(_ASTNodeBase):
    type: Literal["callout"] = "callout"
    variant: Literal["info", "warning", "tip", "danger"] = "info"
    title: str = ""
    text: str


CardItem = str | NoteNode | QuoteNode | CalloutNode


class CardNode(_ASTNodeBase):
    type: Literal["card"] = "card"
    title: str = ""
    items: list[CardItem] = Field(default_factory=list)
    footer: str = ""


class FigureNode(_ASTNodeBase):
    type: Literal["figure"] = "figure"
    prompt: str


class ImageNode(_ASTNodeBase):
    type: Literal["image"] = "image"
    src: str
    alt: str = ""


class CodeNode(_ASTNodeBase):
    type: Literal["code"] = "code"
    language: str = ""
    text: str


class ListNode(_ASTNodeBase):
    type: Literal["list"] = "list"
    ordered: bool = False
    items: list[str] = Field(default_factory=list)


class HrNode(_ASTNodeBase):
    type: Literal["hr"] = "hr"


AnyASTNode = Annotated[
    HeadingNode
    | ParagraphNode
    | QuoteNode
    | NoteNode
    | CalloutNode
    | CardNode
    | FigureNode
    | ImageNode
    | CodeNode
    | ListNode
    | HrNode,
    Field(discriminator="type"),
]


class ContentAST(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    digest: str = ""
    nodes: list[AnyASTNode] = Field(default_factory=list)
    word_count: int = Field(default=0, ge=0)
