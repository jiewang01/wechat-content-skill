"""配图 CLI（prompt-first）：ContentPackage JSON → 配图方案 / 资产回填。

用法：
    # 规划模式：离线生成配图方案 brief；--apply 回写 visual 并插入 :::figure 占位块
    python scripts/imagery.py pkg.json --theme orange-heart
    python scripts/imagery.py pkg.json -o brief.md --apply

    # 回填模式：人工按 prompt 生图后，把真图资产写回包内并重排正文引用
    python scripts/imagery.py pkg.json --apply --asset 2=https://cdn/a.png --asset 3=./b.png

回填模式不重新规划：仅更新既有 visual.images 的 asset_path，并把正文重排为
「已回填 → ![purpose](asset) 图片引用；未回填 → :::figure 占位块」，
与 validators.visual.lint_visual_consistency 的一致性契约保持一致。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import json
import re

from core.artifacts.models import ContentPackage
from core.workflow.imagery import (
    build_brief,
    insert_images,
    plan_visual,
    strip_figure_blocks,
)
from renderer.themes import ThemeError, load_theme

_ASSET_LINE_RE = re.compile(r"^\s*!\[[^\]]*\]\(([^)]+)\)\s*$")


def _parse_assets(pairs: list[str]) -> dict[int, str] | None:
    """解析 --asset 插入位=资产路径（可重复）；格式非法返回 None。"""
    assets: dict[int, str] = {}
    for pair in pairs:
        position, sep, path = pair.partition("=")
        if not sep or not position.strip().isdigit() or not path.strip():
            return None
        assets[int(position)] = path.strip()
    return assets


def _strip_known_images(markdown: str, assets: set[str]) -> str:
    """移除正文中已知资产的独立图片行（多轮回填幂等的基础）。

    与 strip_figure_blocks 同款约定：删行的同时收掉前导空行，
    使「strip → insert → strip」往返字节级稳定、空行不累积。
    """
    if not assets:
        return markdown
    out: list[str] = []
    for line in markdown.split("\n"):
        match = _ASSET_LINE_RE.match(line)
        if match and match.group(1) in assets:
            while out and not out[-1].strip():
                out.pop()
            continue
        out.append(line)
    return "\n".join(out)


def _write_package(in_path: Path, package: ContentPackage) -> None:
    in_path.write_text(
        json.dumps(package.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="imagery.py", description="ContentPackage JSON → 配图 prompt 方案 / 资产回填"
    )
    parser.add_argument("input", help="ContentPackage JSON 文件路径")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="配图方案 Markdown 输出路径（默认 <输入目录>/imagery_brief.md）",
    )
    parser.add_argument("--theme", default=None, help="主题名（默认：取包内 theme 字段）")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="规划模式：把生成的 VisualPlan 回写到输入文件的 visual 字段（--theme 时同步 theme 字段）",
    )
    parser.add_argument(
        "--asset",
        action="append",
        default=[],
        metavar="插入位=路径",
        help="回填模式（需 --apply）：把该插入位的真图资产写回包内，"
        "可重复，如 --asset 2=https://cdn/a.png",
    )
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"错误：输入文件不存在：{in_path}", file=sys.stderr)
        return 1
    out_dir = in_path.parent
    brief_path = Path(args.output) if args.output else out_dir / "imagery_brief.md"

    try:
        package = ContentPackage.model_validate(json.loads(in_path.read_text(encoding="utf-8")))
    except Exception as exc:
        print(f"错误：ContentPackage 校验失败：{exc}", file=sys.stderr)
        return 1

    try:
        theme = load_theme(args.theme or package.theme or "default")
    except ThemeError as exc:
        print(f"错误：主题加载失败：{exc}", file=sys.stderr)
        return 1

    assets = _parse_assets(args.asset)
    if args.asset and assets is None:
        print(
            "错误：--asset 格式应为 插入位=资产路径，如 --asset 2=https://cdn/a.png",
            file=sys.stderr,
        )
        return 1

    if args.asset:
        if not args.apply:
            print("错误：--asset 回填需配合 --apply 使用", file=sys.stderr)
            return 1
        visual = package.visual
        if not visual or not visual.images:
            print("错误：包内 visual.images 为空，请先在规划模式下生成配图方案", file=sys.stderr)
            return 1
        by_position = {spec.position for spec in visual.images}
        unknown = sorted(set(assets) - by_position)
        if unknown:
            print(f"错误：插入位 {unknown} 不在 visual.images 中", file=sys.stderr)
            return 1
        images = [
            spec.model_copy(update={"asset_path": assets.get(spec.position, spec.asset_path)})
            for spec in visual.images
        ]
        package.visual = visual.model_copy(update={"images": images})
        known = {spec.asset_path for spec in images if spec.asset_path}
        package.semantic_markdown = _strip_known_images(
            strip_figure_blocks(package.semantic_markdown), known
        )
        if theme.components_enabled.get("figure"):
            package.semantic_markdown = insert_images(
                package.semantic_markdown, images, placeholders=True
            )
        _write_package(in_path, package)
        print(f"updated {in_path} (assets backfilled: {sorted(assets)})")
        return 0

    package.semantic_markdown = strip_figure_blocks(package.semantic_markdown)
    plan = plan_visual(package, theme)
    brief = build_brief(package, theme)

    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(brief, encoding="utf-8")
    print(f"wrote {brief_path} (cover + {len(plan.images)} section prompts)")

    if args.apply:
        if args.theme:
            package.theme = args.theme
        package.visual = plan
        if theme.components_enabled.get("figure"):
            package.semantic_markdown = insert_images(
                package.semantic_markdown, plan.images, placeholders=True
            )
        _write_package(in_path, package)
        print(f"updated {in_path} (visual + semantic_markdown)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
