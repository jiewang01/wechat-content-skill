"""主题引擎：从 themes/<name>/ 读取 theme.yaml / typography.yaml / components.yaml。

新增主题 = 新建目录放入三个 YAML 文件，零代码改动（借鉴 wechat-skill 的组件系统）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

THEMES_DIR = Path(__file__).parent

REQUIRED_FILES = ("theme.yaml", "typography.yaml", "components.yaml")
REQUIRED_COMPONENTS = ("note", "quote", "callout", "card")


class ThemeError(ValueError):
    """主题缺失或结构非法。"""


class Theme(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str = "1"
    colors: dict[str, str] = Field(default_factory=dict)
    components_enabled: dict[str, bool] = Field(default_factory=dict)
    typography: dict[str, Any] = Field(default_factory=dict)
    components: dict[str, Any] = Field(default_factory=dict)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ThemeError(f"主题文件缺失：{path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ThemeError(f"主题文件必须是映射结构：{path}")
    return data


def load_theme(name: str = "default", themes_dir: str | Path | None = None) -> Theme:
    """加载指定主题；默认在本包 themes/ 目录下查找。"""
    base = Path(themes_dir) if themes_dir is not None else THEMES_DIR
    theme_dir = base / name
    if not theme_dir.is_dir():
        available = (
            sorted(d.name for d in base.iterdir() if d.is_dir()) if base.is_dir() else []
        )
        raise ThemeError(f"主题 {name!r} 不存在（可用主题：{available}）")

    data: dict[str, dict[str, Any]] = {}
    for fname in REQUIRED_FILES:
        data[fname.removesuffix(".yaml")] = _load_yaml(theme_dir / fname)

    theme_data = data["theme"]
    theme = Theme(
        name=str(theme_data.get("name", name)),
        version=str(theme_data.get("version", "1")),
        colors=theme_data.get("colors", {}),
        components_enabled=theme_data.get("components", {}),
        typography=data["typography"],
        components=data["components"],
    )

    enabled = {key for key, value in theme.components_enabled.items() if value}
    not_enabled = [c for c in REQUIRED_COMPONENTS if c not in enabled]
    if not_enabled:
        raise ThemeError(f"主题 {name!r} 未启用必需组件（theme.yaml components）：{not_enabled}")
    unstyled = [c for c in REQUIRED_COMPONENTS if c not in theme.components]
    if unstyled:
        raise ThemeError(f"主题 {name!r} 缺少组件样式（components.yaml）：{unstyled}")
    return theme
