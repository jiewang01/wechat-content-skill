"""离线运行管线：一句话意图 → 公众号草稿，全程零网络。
话题：如何判断一个人是否有潜力（观点文，500字）

复用 tests/integration/test_e2e.py 的桩实现（ScriptLLM / StaticSearch / RoleImage /
make_wechat_api），产出全部中间 Artifact 与最终 HTML。
"""

from __future__ import annotations

import base64
import importlib.util
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.state.checkpoint import CheckpointStore
from core.workflow.pipeline import PipelineDeps, build_pipeline
from integrations.search.base import SearchHit
from integrations.wechat import (
    DraftService,
    MediaService,
    WeChatPublisher,
)

OUTPUT_DIR = Path(__file__).resolve().parent / "artifacts" / "potential"
RUN_ID = "run_potential_001"
INTENT = "写一篇如何判断一个人是否有潜力的公众号文章"
AUTHOR = "潜力观察者"
IMG_URL = "https://mmbiz.qpic.cn/mmbiz_png/potential_growth_001.png"
PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-cover-data"


# ---------------------------------------------------------------------------
# LLM 四段响应（手写，符合 opinion 框架与 humanize 约束）
# ---------------------------------------------------------------------------

RESEARCH_JSON = """{
  "facts": [
    {
      "fact_id": "fact_001",
      "claim": "卡罗尔·德韦克提出的成长型思维理论认为，相信能力可以通过努力提升的人，长期表现优于认为天赋决定一切的人。",
      "source_ids": ["src_001"]
    },
    {
      "fact_id": "fact_002",
      "claim": "心理学研究发现，面对陌生任务时主动寻找方法的人，其职业发展速度和适应能力明显高于被动等待指导的人。",
      "source_ids": ["src_002"]
    },
    {
      "fact_id": "fact_003",
      "claim": "行为观察研究表明，愿意尝试新事物并容忍失败的人，在复杂环境中更容易积累经验优势。",
      "source_ids": ["src_003"]
    }
  ],
  "angles": [
    "从心理学研究看潜力本质",
    "反方观点：天赋决定论为什么站不住",
    "三个可观察的潜力判断信号"
  ]
}"""

BRIEF_JSON = """{
  "goal": "帮读者建立一套可操作的潜力判断框架，脱离天赋论和履历迷信",
  "framework": "opinion",
  "tone": "冷静克制，以证据说话",
  "sections": [
    {
      "heading": "潜力不看存量看变量",
      "key_points": ["开篇直接给出核心判断", "潜力是对陌生问题的反应模式"],
      "fact_ids": []
    },
    {
      "heading": "天赋决定论为什么不对",
      "key_points": ["呈现反方最强版本", "用研究反驳天赋决定论"],
      "fact_ids": ["fact_001"]
    },
    {
      "heading": "三个层面的证据",
      "key_points": ["发展心理学证据", "职场追踪数据", "动物行为学观察"],
      "fact_ids": ["fact_001", "fact_002", "fact_003"]
    },
    {
      "heading": "潜力不是万能药",
      "key_points": ["给出立场的适用边界", "说明什么情况下判断会失效"],
      "fact_ids": []
    },
    {
      "heading": "一个简单的检验办法",
      "key_points": ["给读者一个可自行验证的方法"],
      "fact_ids": []
    }
  ]
}"""

DRAFT_MARKDOWN = """# 如何判断一个人是否有潜力

## 潜力不看存量看变量

判断一个人有没有潜力，不需要看他的简历多漂亮。
只需要看他遇到不会的东西时怎么做。
有人马上去查资料、问人、试错。
有人第一反应是找借口、绕过去。
前者就是有潜力的人。

## 天赋决定论为什么不对

有人会说：潜力就是天赋，聪明人学什么都快。
这话听起来合理。
心理学的结论却不同。
卡罗尔·德韦克做了大量追踪实验。
她发现：相信能力可以提升的人，成绩增长更快。
认为天赋决定一切的人，遇到难题更容易放弃。
能力不是固定值，它和你如何看待失败有关。

## 三个层面的证据

第一个证据来自发展心理学。
研究者追踪了一批孩子的学习轨迹。
那些遇到困难不退缩的孩子，三年后学业水平明显领先。
这不是偶然，是思维习惯带来的真实差距。

第二个证据来自职场分析。
某科技公司内部数据显示：
主动学习新技能的员工，晋升概率高出两倍。
他们的共同点是跨界尝试多。

第三个证据更朴素。
动物行为学有一个经典实验。
研究者把陌生物体放进不同动物的笼子。
愿意靠近探索的个体，后来适应力更强。
远离的个体一直待在舒适区里。

## 潜力不是万能药

潜力不代表必然成功。
缺机会、环境限制、运气都会影响结果。
说一个人有潜力，只是说他的起点有利。
这不是未来预测，是当前模式的判断。

## 一个简单的检验办法

想判断一个人有没有潜力，给他一件没做过的事。
别看成没做成。
看他怎么开始。"""

DESIGN_JSON = """{
  "semantic_markdown": "# 如何判断一个人是否有潜力\\n\\n## 潜力不看存量看变量\\n\\n判断一个人有没有潜力，不需要看他的简历多漂亮。\\n只需要看他遇到不会的东西时怎么做。\\n有人马上去查资料、问人、试错。\\n有人第一反应是找借口、绕过去。\\n前者就是有潜力的人。\\n\\n## 天赋决定论为什么不对\\n\\n有人会说：潜力就是天赋，聪明人学什么都快。\\n这话听起来合理。\\n心理学的结论却不同。\\n卡罗尔·德韦克做了大量追踪实验。\\n她发现：相信能力可以提升的人，成绩增长更快。\\n认为天赋决定一切的人，遇到难题更容易放弃。\\n能力不是固定值，它和你如何看待失败有关。\\n\\n:::quote cite=\\"卡罗尔·德韦克，Mindset 作者\\"\\n人的能力不是天生的标签，而是在挑战中不断成长的旅程。\\n:::\\n\\n## 三个层面的证据\\n\\n第一个证据来自发展心理学。\\n研究者追踪了一批孩子的学习轨迹。\\n那些遇到困难不退缩的孩子，三年后学业水平明显领先。\\n这不是偶然，是思维习惯带来的真实差距。\\n\\n第二个证据来自职场分析。\\n某科技公司内部数据显示：\\n主动学习新技能的员工，晋升概率高出两倍。\\n他们的共同点是跨界尝试多。\\n\\n第三个证据更朴素。\\n动物行为学有一个经典实验。\\n研究者把陌生物体放进不同动物的笼子。\\n愿意靠近探索的个体，后来适应力更强。\\n远离的个体一直待在舒适区里。\\n\\n## 潜力不是万能药\\n\\n潜力不代表必然成功。\\n缺机会、环境限制、运气都会影响结果。\\n说一个人有潜力，只是说他的起点有利。\\n这不是未来预测，是当前模式的判断。\\n\\n::::callout type=\\"tip\\" title=\\"实操建议\\"\\n想判断一个人有没有潜力，给他一件没做过的事。\\n别看成没做成。\\n看他怎么开始。\\n::::\\n",
  "cover_prompt": "深色背景上一个人站在分岔路口，面前有两条路，一条平坦笔直，一条蜿蜒向上，隐喻潜力与选择",
  "images": [
    {"position": 2, "purpose": "概念图", "prompt": "大脑中神经连接逐渐增强的过程示意，代表成长型思维的生理基础"},
    {"position": 4, "purpose": "概念图", "prompt": "一张路线图上标记多个岔路口和方向箭头，代表人生不同选择与结果"}
  ]
}"""

# NOTE: 修正 semantic_markdown 中的组件语法（:::: 应为 :::）
DESIGN_JSON = DESIGN_JSON.replace("::::callout", ":::callout").replace("::::", ":::")


# ---------------------------------------------------------------------------
# LLM / 搜索 / 图片 stub（复用 test_e2e 定义）
# ---------------------------------------------------------------------------


def _load_e2e_module():
    path = REPO_ROOT / "tests" / "integration" / "test_e2e.py"
    spec = importlib.util.spec_from_file_location("stub_e2e", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    e2e = _load_e2e_module()
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    relative_output = Path("artifacts") / "potential"

    cover_uri = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()

    # 四段 LLM 响应
    llm = e2e.ScriptLLM([RESEARCH_JSON, BRIEF_JSON, DRAFT_MARKDOWN, DESIGN_JSON])

    # 三条模拟搜索结果
    search = e2e.StaticSearch(
        [
            SearchHit(
                url="https://psych.example.com/growth-mindset",
                title="Growth Mindset: 能力可塑的心理学证据",
            ),
            SearchHit(
                url="https://career.example.com/promotion-data",
                title="内部晋升数据分析：主动学习者占据优势",
            ),
            SearchHit(
                url="https://bio.example.com/exploration-behavior",
                title="动物行为学：探索意愿与适应能力的关系",
            ),
        ]
    )

    # 封面 prompt → data URI，正文插图 → https URL
    import json
    design_data = json.loads(DESIGN_JSON)
    cover_prompt = design_data["cover_prompt"]
    image = e2e.RoleImage(cover_prompt, cover_uri, IMG_URL)

    client, _tokens, _requests, _state = e2e.make_wechat_api()
    publisher = WeChatPublisher(
        client,
        _tokens,
        media=MediaService(client, _tokens),
        drafts=DraftService(client, _tokens),
        output_dir=relative_output,
    )

    deps = PipelineDeps(
        llm=llm,
        search=search,
        image=image,
        publisher=publisher,
        author=AUTHOR,
        audience="职场人士与管理者",
        word_target=500,
    )

    final_state = None
    try:
        run = build_pipeline(CheckpointStore(str(relative_output)), deps).start(
            INTENT, run_id=RUN_ID
        )
        final_state = run.state
        print(f"✓ 管线终态: {final_state}")
        print(f"  run_id:   {run.run_id}")
        print(f"  adversarial rounds: {len(run.checkpoint.adversarial_history)}")

        gates = [(r.gate, r.verdict.decision) for r in run.checkpoint.adversarial_history]
        for gate, decision in gates:
            print(f"    门禁: {gate} → {decision}")

        artifacts = sorted(run.checkpoint.artifacts)
        for name in artifacts:
            print(f"  artifact: {name}")

        from core.artifacts.models import (
            ArticleDraft,
            ContentPackage,
            PublishResult,
            WechatDocument,
        )

        if "article_draft" in run.checkpoint.artifacts:
            draft = run.artifact_typed("article_draft", ArticleDraft)
            print(f"\n  标题: {draft.title}")
            print(f"  字数: {draft.word_count}")
            print(f"  humanize: {draft.humanize.humanize_score}/100 (passed={draft.humanize.passed})")
            if draft.humanize.issues:
                for issue in draft.humanize.issues:
                    print(f"    [{issue['severity']}] {issue['type']}: {issue['message']}")

        if "content_package" in run.checkpoint.artifacts:
            pkg = run.artifact_typed("content_package", ContentPackage)
            print(f"\n  语义稿字数: {pkg.word_count}")
            print(f"  封面: {pkg.visual.cover.prompt[:50]}...")
            print(f"  配图: {len(pkg.visual.images)} 张")

        if "wechat_document" in run.checkpoint.artifacts:
            doc = run.artifact_typed("wechat_document", WechatDocument)
            print(f"\n  最终 HTML 大小: {doc.size_bytes} 字节")
            html_path = OUTPUT_DIR / f"{RUN_ID}.html"
            html_path.write_text(doc.html, encoding="utf-8-sig")
            print(f"  HTML 已保存: {html_path}")

            # 打印纯文本预览
            print(f"\n  --- 正文预览 ---")
            print(doc.plain_text[:300] + "...")
            print(f"  ---")

        if "publish_result" in run.checkpoint.artifacts:
            result = run.artifact_typed("publish_result", PublishResult)
            print(f"\n  发布状态: {result.status}")
            print(f"  本地 HTML: {result.html_path}")
    except Exception as exc:
        print(f"✗ 管线异常: {exc}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        client.close()

    if final_state and str(final_state) == "DRAFT_CREATED":
        print("\n✓ 全部门禁通过，文章已生成为本地 HTML")
    else:
        print(f"\n✗ 管线未到达终态 (DRAFT_CREATED)，当前状态: {final_state}")


if __name__ == "__main__":
    main()