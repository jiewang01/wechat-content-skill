"""配图 CLI：ContentPackage JSON → 配图方案（Markdown brief）+ 可选回写 visual。

用法：
    python scripts/imagery.py pkg.json --theme orange-heart
    python scripts/imagery.py pkg.json -o brief.md --apply
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import json

from core.artifacts.models import ContentPackage
from core.workflow.imagery import build_brief, plan_visual
from renderer.themes import ThemeError, load_theme


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="imagery.py", description="ContentPackage JSON → 配图 prompt 方案"
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
        help="把生成的 VisualPlan 回写到输入文件的 visual 字段（--theme 时同步 theme 字段）",
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

    plan = plan_visual(package, theme)
    brief = build_brief(package, theme)

    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(brief, encoding="utf-8")
    print(f"wrote {brief_path} (cover + {len(plan.images)} section prompts)")

    if args.apply:
        if args.theme:
            package.theme = args.theme
        package.visual = plan
        in_path.write_text(
            json.dumps(package.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"updated {in_path} (visual)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
