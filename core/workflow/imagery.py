"""确定性配图规划器：从 ContentPackage + Theme 生成配图 prompt 方案。

不依赖 LLM 与图片 provider：既是 design 阶段的确定性兜底（蓝图 ch12 三级降级
的 image 一级），也可通过 scripts/imagery.py 对既有 content_package 补跑。

Prompt 模板遵循 skills/visual/prompts/image-prompt-guide.md 的五要素规范，
借鉴 GitHub awesome-gpt-image-2 的结构化模板模式（主体 / 风格 / 构图 / 色调 /
约束 + 负向收尾）：

    [主体] + [风格] + [构图/比例] + [色调] + [约束]

硬规则：图内不要求可读文字（prompt 以「无文字、无水印」收尾）；封面 2.35:1、
正文 16:9；风格与主题色系锁定（theme.colors.primary 动态注入）；每 600 字
最多 1 张、全文至多 4 张；每条 prompt 自包含，可直接粘贴到任意文生图工具。

optimize_prompt 是全部 prompt 的统一出口：LLM 设计稿与确定性兜底产出的
prompt 进入 VisualPlan 前都经它补齐画幅与负向约束（幂等、不重写主体），
保证 figure 占位卡片、配图方案与成稿内嵌的是同一份优化 prompt。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from core.artifacts.models import ContentPackage, CoverSpec, ImageSpec, VisualPlan
from renderer.themes import Theme

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_WORDS_PER_IMAGE = 600
_MAX_IMAGES = 4
_SUMMARY_LIMIT = 40

_DEFAULT_PROFILE: dict[str, str] = {
    "style": "现代扁平概念插画，干净的几何构图与柔和渐变",
    "palette": "低饱和中性色调，大量留白",
    "mood": "沉静、克制、有呼吸感",
    "negative": "画面中不出现任何文字、无水印、无 logo",
}

_RATIO_HINTS = {
    "2.35:1": "横向封面构图（2.35:1），主体居中",
    "16:9": "横构图（16:9），视觉焦点居中",
}


@dataclass(frozen=True)
class ImageryProfile:
    """主题的配图风格画像：来自 themes/<name>/imagery.yaml，缺失时用中性默认。"""

    style: str
    palette: str
    mood: str
    negative: str
    primary: str

    @classmethod
    def from_theme(cls, theme: Theme) -> ImageryProfile:
        raw = getattr(theme, "imagery", None) or {}
        merged = {
            **_DEFAULT_PROFILE,
            **{
                key: str(value).strip()
                for key, value in raw.items()
                if isinstance(value, str) and str(value).strip()
            },
        }
        merged["primary"] = str(theme.colors.get("primary") or "").strip() or "#333333"
        return cls(**merged)


@dataclass(frozen=True)
class SectionAnchor:
    """正文锚点：position 与 pipeline._insert_images 的语义一致
    （插入到第 N 个非首标题之前，1-based）。"""

    position: int
    title: str
    summary: str


def image_quota(word_count: int) -> int:
    """配额：每 600 字 1 张，下限 1、上限 4。"""
    return max(1, min(_MAX_IMAGES, math.ceil(max(word_count, 1) / _WORDS_PER_IMAGE)))


def _strip_inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.strip()


def extract_anchors(markdown: str) -> list[SectionAnchor]:
    """提取插图锚点：跳过第一个标题（文章标题），其余标题各为一个锚点。"""
    lines = markdown.split("\n")
    heading_lines = [(i, line) for i, line in enumerate(lines) if _HEADING_RE.match(line.strip())]
    anchors: list[SectionAnchor] = []
    for idx, (line_no, line) in enumerate(heading_lines[1:], start=1):
        match = _HEADING_RE.match(line.strip())
        title = _strip_inline(match.group(2)) if match else ""
        if not title:
            continue
        end = heading_lines[idx + 1][0] if idx + 1 < len(heading_lines) else len(lines)
        summary = ""
        for body_line in lines[line_no + 1 : end]:
            text = _strip_inline(body_line)
            if text and not text.startswith((":::", "#", ">", "-", "|", "!")):
                summary = text[:_SUMMARY_LIMIT]
                break
        anchors.append(SectionAnchor(position=idx, title=title, summary=summary))
    return anchors


def _pick_anchors(anchors: list[SectionAnchor], quota: int) -> list[SectionAnchor]:
    """均匀选位：避开第一个锚点（文章开头由封面承担），从第 2 个起均匀采样。"""
    if not anchors:
        return []
    candidates = [a for a in anchors if a.position >= 2]
    if not candidates:
        return anchors[:1]
    if quota >= len(candidates):
        return candidates
    if quota == 1:
        return [candidates[(len(candidates) - 1) // 2]]
    step = (len(candidates) - 1) / (quota - 1)
    return [candidates[round(i * step)] for i in range(quota)]


def optimize_prompt(prompt: str, *, ratio: str, profile: ImageryProfile) -> str:
    """把任意来源的生图 prompt 归一为可直贴生图工具的优化格式（幂等、不重写主体）。

    统一规则：压平空白为单行并去掉尾部句读；补齐缺失的画幅段（封面 2.35:1 /
    正文 16:9）与负向约束段（profile.negative）；段间以「；」分隔、以「。」
    收尾。主体与风格措辞保持原样，已合规的 prompt 再过一次结果不变。
    """
    text = re.sub(r"\s+", " ", prompt).strip().rstrip("。；;")
    if not text:
        return ""
    segments = [text]
    if ratio and ratio not in text:
        segments.append(_RATIO_HINTS.get(ratio, f"构图（{ratio}），视觉焦点居中"))
    if "无水印" not in text:
        segments.append(profile.negative)
    return "；".join(segments) + "。"


def cover_prompt(title: str, digest: str, profile: ImageryProfile) -> str:
    digest_core = digest.split("。")[0].strip() if digest else ""
    subject = f"{title}——{digest_core}" if digest_core else f"{title}的概念意象"
    return optimize_prompt(
        f"{subject}；{profile.style}，{profile.mood}；横向封面构图（2.35:1），主体居中；"
        f"{profile.palette}，以主题色 {profile.primary} 为视觉强调",
        ratio="2.35:1",
        profile=profile,
    )


def section_prompt(anchor: SectionAnchor, profile: ImageryProfile) -> str:
    summary_core = anchor.summary.split("。")[0].strip() if anchor.summary else ""
    subject = f"{anchor.title}：{summary_core}" if summary_core else anchor.title
    return optimize_prompt(
        f"「{subject}」的视觉隐喻概念插画；{profile.style}，{profile.mood}；"
        f"横构图（16:9），视觉焦点居中；{profile.palette}，以主题色 {profile.primary} 为点缀",
        ratio="16:9",
        profile=profile,
    )


def plan_visual(package: ContentPackage, theme: Theme) -> VisualPlan:
    """确定性生成完整 VisualPlan：封面 prompt + 正文插图 prompts（asset_path 留空）。"""
    profile = ImageryProfile.from_theme(theme)
    anchors = extract_anchors(package.semantic_markdown)
    picked = _pick_anchors(anchors, image_quota(package.word_count))
    return VisualPlan(
        cover=CoverSpec(
            style="editorial",
            ratio="2.35:1",
            prompt=cover_prompt(package.title, package.digest, profile),
        ),
        images=[
            ImageSpec(
                position=anchor.position,
                purpose="concept",
                prompt=section_prompt(anchor, profile),
            )
            for anchor in picked
        ],
        diagrams=[],
        degraded=False,
    )


def figure_block(prompt: str) -> str:
    """把生图 prompt 包成 :::figure 占位块（语义 Markdown 层的图片占位符）。"""
    return f":::figure\n{prompt.strip()}\n:::"


def strip_figure_blocks(markdown: str) -> str:
    """移除正文中已有的 :::figure 占位块（幂等重插的基础）。

    状态机扫描：`:::figure` 开栈后丢弃整块（含闭合 `:::`）；figure 契约上
    无嵌套子组件，块内出现的 `:::` 一律视为闭合行。块前的空行一并收掉，
    使「strip → insert → strip」空运转完全幂等。
    """
    out: list[str] = []
    in_figure = False
    for line in markdown.split("\n"):
        stripped = line.strip()
        if in_figure:
            if stripped == ":::":
                in_figure = False
            continue
        if stripped == ":::figure":
            in_figure = True
            while out and not out[-1].strip():
                out.pop()
            continue
        out.append(line)
    return "\n".join(out)


def insert_images(markdown: str, images: list[ImageSpec], *, placeholders: bool = False) -> str:
    """把插图插到第 N 个小节标题之前（首标题视为文章标题，不作为锚点）。

    有资产的插图插入 `![purpose](asset)`；无资产的插图在 placeholders=True
    时插入 :::figure 占位块（prompt 直接呈现给读者，供生图替换），
    否则跳过（防 broken image）。
    """
    if not images:
        return markdown
    lines = markdown.split("\n")
    heading_indices = [i for i, line in enumerate(lines) if _HEADING_RE.match(line.strip())]
    anchors = heading_indices[1:]
    insertions: dict[int, str] = {}
    for spec in images:
        index = spec.position - 1
        if not 0 <= index < len(anchors):
            continue
        if spec.asset_path:
            insertions[anchors[index]] = f"![{spec.purpose}]({spec.asset_path})"
        elif placeholders and spec.prompt.strip():
            insertions[anchors[index]] = figure_block(spec.prompt)
    if not insertions:
        return markdown
    out: list[str] = []
    for i, line in enumerate(lines):
        if i in insertions:
            out.extend(["", insertions[i], ""])
        out.append(line)
    return "\n".join(out)


def build_brief(package: ContentPackage, theme: Theme) -> str:
    """生成可直接交付的 Markdown 配图方案文档。"""
    profile = ImageryProfile.from_theme(theme)
    anchors = extract_anchors(package.semantic_markdown)
    picked = _pick_anchors(anchors, image_quota(package.word_count))
    lines = [
        f"# 《{package.title}》配图方案",
        "",
        f"- 主题：{theme.name}（主色 {profile.primary}）",
        f"- 风格：{profile.style}",
        f"- 篇幅：{package.word_count} 字 ｜ 小节 {len(anchors)} 个 ｜ 配图 {len(picked)} 张",
        "- 规范：五要素（主体/风格/构图/色调/约束），"
        "见 skills/visual/prompts/image-prompt-guide.md",
        "",
        "## 封面（2.35:1 · editorial）",
        "",
        "```text",
        cover_prompt(package.title, package.digest, profile),
        "```",
        "",
    ]
    for i, anchor in enumerate(picked, 1):
        lines += [
            f"## 正文插图 {i}（16:9 · concept · 第 {anchor.position} 节「{anchor.title}」之前）",
            "",
            "```text",
            section_prompt(anchor, profile),
            "```",
            "",
        ]
    lines += [
        "## 使用说明",
        "",
        "1. 以上 prompt 均自包含，可直接粘贴到任意文生图工具（即梦、DALL·E、SDXL 等）。",
        "2. 成图后把 https:// 图片链接回填到 content_package.json 的 "
        "`visual.images[i].asset_path`，重跑 render.py 即可入文。",
        "3. 未回填 asset_path 时，管线以 :::figure 占位块把 prompt 呈现在正文占位"
        "（主题启用 figure 组件时），回填重渲染即替换为真图。",
    ]
    return "\n".join(lines)
