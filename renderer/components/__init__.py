"""组件注册表：四种语义标记的权威契约（H8）。"""

from renderer.components.registry import (
    COMPONENT_SPECS,
    ComponentSpec,
    InvalidPropError,
    MarkerValidationError,
    UnknownComponentError,
    get_spec,
    marker_names,
    validate_marker,
)

__all__ = [
    "COMPONENT_SPECS",
    "ComponentSpec",
    "InvalidPropError",
    "MarkerValidationError",
    "UnknownComponentError",
    "get_spec",
    "marker_names",
    "validate_marker",
]
