"""组件注册表：四种语义标记的唯一权威契约（H8 确定性优先）。

native 技能只允许按本注册表标注属性；超出契约的标记在解析期即报错，
错误类型可直接被渲染门的 Attack 使用（H2：报错必带证据）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


class MarkerValidationError(ValueError):
    """标记校验失败；error_type 为机器可读的错误分类。"""

    error_type = "invalid_marker"

    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type


class UnknownComponentError(MarkerValidationError):
    """使用了注册表之外的组件名。"""


class InvalidPropError(MarkerValidationError):
    """属性级错误：unsupported_attribute / missing_required_prop / invalid_prop_value。"""


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    description: str
    allowed_props: frozenset[str]
    required_props: frozenset[str] = frozenset()
    prop_enums: dict[str, frozenset[str]] = field(default_factory=dict)
    content: str = "text"

    def validate(self, attrs: dict[str, str]) -> None:
        for key in attrs:
            if key not in self.allowed_props:
                raise InvalidPropError(
                    "unsupported_attribute",
                    f"组件 {self.name} 不支持属性 {key!r}，允许的属性：{sorted(self.allowed_props)}",
                )
        for key in self.required_props:
            if not attrs.get(key):
                raise InvalidPropError(
                    "missing_required_prop",
                    f"组件 {self.name} 缺少必填属性 {key!r}",
                )
        for key, allowed in self.prop_enums.items():
            value = attrs.get(key)
            if value is not None and value not in allowed:
                raise InvalidPropError(
                    "invalid_prop_value",
                    f"组件 {self.name} 的属性 {key}={value!r} 不在允许值 {sorted(allowed)} 内",
                )


COMPONENT_SPECS: dict[str, ComponentSpec] = {
    "note": ComponentSpec(
        name="note",
        description="中性补充说明或背景信息",
        allowed_props=frozenset(),
        content="text",
    ),
    "quote": ComponentSpec(
        name="quote",
        description="引用原话；cite 标注出处",
        allowed_props=frozenset({"cite"}),
        content="text",
    ),
    "callout": ComponentSpec(
        name="callout",
        description="强调级提示框；type 决定配色",
        allowed_props=frozenset({"type", "title"}),
        prop_enums={"type": frozenset({"info", "warning", "tip", "danger"})},
        content="text",
    ),
    "card": ComponentSpec(
        name="card",
        description="要点卡片；正文为列表",
        allowed_props=frozenset({"title", "footer"}),
        content="list",
    ),
}


def get_spec(name: str) -> ComponentSpec:
    spec = COMPONENT_SPECS.get(name)
    if spec is None:
        raise UnknownComponentError(
            "unknown_component", f"未知组件 {name!r}，v0.1 仅支持：{sorted(COMPONENT_SPECS)}"
        )
    return spec


def marker_names() -> frozenset[str]:
    return frozenset(COMPONENT_SPECS)


def validate_marker(name: str, attrs: dict[str, str]) -> ComponentSpec:
    spec = get_spec(name)
    spec.validate(attrs)
    return spec
