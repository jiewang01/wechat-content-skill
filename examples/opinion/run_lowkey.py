from __future__ import annotations

import base64
import importlib.util
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.state.checkpoint import CheckpointStore
from core.workflow.pipeline import PipelineDeps, build_pipeline
from integrations.wechat import (
    DraftService,
    MediaService,
    WeChatPublisher,
)

OPINION_DIR = Path(__file__).resolve().parent
RUN_ID = "run_20260915_001"


def _load_e2e_module():
    path = REPO_ROOT / "tests" / "integration" / "test_e2e.py"
    spec = importlib.util.spec_from_file_location("opinion_e2e", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_COVER_PROMPT = (
    "沉稳的深蓝色调书房一隅，柔和顶光打在木书桌一角，"
    "桌面放着一本合上的书和一支钢笔，画面安静克制，无人物。"
)
_BODY_IMAGE_PROMPT = "一个人安静坐在图书馆角落阅读，窗外柔光透入，画面安静专注，概念插画。"


def _brief_response() -> str:
    return json.dumps(
        {
            "goal": "阐释真正有本事的人为何选择低调，帮助读者理解低调背后的实力自信",
            "framework": "opinion",
            "tone": "克制平和，用事实说话",
            "sections": [
                {
                    "heading": "立场亮相",
                    "key_points": [
                        "低调是实力自信的表现，并非美德特权",
                        "越有能力的人越不需要外显证明",
                    ],
                    "fact_ids": [],
                },
                {
                    "heading": "反方最强",
                    "key_points": [
                        "低调可能被忽视、错失机会",
                        "埋头苦干不等于有效表达",
                    ],
                    "fact_ids": [],
                },
                {
                    "heading": "论据推进",
                    "key_points": [
                        "专注产生的复利远大于关注",
                        "被低估是成长过程中的护身符",
                    ],
                    "fact_ids": [],
                },
                {
                    "heading": "让步与边界",
                    "key_points": [
                        "低调不等于沉默",
                        "在需要表态的场合要站出来",
                    ],
                    "fact_ids": [],
                },
                {
                    "heading": "可检验判断",
                    "key_points": [
                        "观察一个人不需要证明自己时的状态",
                        "时间会给出最终答案",
                    ],
                    "fact_ids": [],
                },
            ],
        },
        ensure_ascii=False,
    )


def _draft_markdown() -> str:
    return (
        "# 有本事的人往往很低调\n\n"
        "我见过两种人。一种刚做出点成绩就急着告诉全世界。"
        "另一种把本事藏在手里，不到关键时候不出手。"
        "几年下来，后者走得更远。\n\n"
        "## 立场亮相\n\n"
        "低调不是什么美德，而是一种自信。"
        "你不需要别人认可，因为你知道自己知道。"
        "真正做事的人心里清楚，结果才是最好的语言。\n\n"
        "我以前也不懂。总觉得要让人看到自己的付出，怕沉默等于不存在。"
        "后来观察那些我佩服的人，发现一个规律。"
        "他们很少谈论自己做了什么，但每次开口都让人记很久。\n\n"
        "## 反方最强\n\n"
        "有人说低调容易被忽视。这个时代注意力就是资源。"
        "不出声别人就不知道你，机会就被抢走了。这话有道理。\n\n"
        "我也见过埋头苦干多年却始终不得重用的工程师。"
        "他们的教训是，光做不说不一定有用。"
        "但这里有一个关键区别。不做宣传和不表达不是一回事。"
        "表达是传递价值。宣传是放大存在感。"
        "低调的人拒绝的是后者，不是前者。\n\n"
        "## 论据推进\n\n"
        "把本事练扎实的人，往往在做减法。"
        "拒绝无效社交，减少公开表态，把精力留给真正重要的事。"
        "专注带来的复利，远大于关注。\n\n"
        "我有个朋友，创业前几年几乎不参加任何行业会议。"
        "同行以为他做不下去了。第五年公司营收破亿。"
        "大家才明白他这几年在干什么。他说，被低估是创业者的护身符。\n\n"
        "现实世界里，信息越多噪音越大。"
        "低调让人保持清醒，不被外界评价牵着走。心态稳了，判断力就准了。\n\n"
        "## 让步与边界\n\n"
        "低调不等于沉默。在需要负责的场合要站出来。"
        "在别人需要帮助的时候要开口。"
        "什么时候该表态，标准只有一个。"
        "这句话是为自己说的，还是为事情说的。\n\n"
        "## 可检验判断\n\n"
        "一个人有没有真本事。看他不需要证明自己的时候是什么状态。"
        "不需要说服谁，不需要解释，不需要回应质疑。安静地做，做完交给时间。"
    )


def _design_response() -> str:
    semantic_md = _draft_markdown() + "\n\n"
    semantic_md += (
        ':::quote cite="— 查理·芒格"\n'
        "反过来想，总是反过来想。\n"
        ":::\n\n"
    )
    semantic_md += (
        ':::callout type="tip" title="判断标准"\n'
        "一个人有没有真本事，看他不需要证明自己的时候是什么状态。\n"
        ":::"
    )
    return json.dumps(
        {
            "semantic_markdown": semantic_md,
            "cover_prompt": _COVER_PROMPT,
            "images": [
                {
                    "position": 3,
                    "purpose": "概念插画",
                    "prompt": _BODY_IMAGE_PROMPT,
                }
            ],
        },
        ensure_ascii=False,
    )


def _llm_responses() -> list[str]:
    return [_brief_response(), _draft_markdown(), _design_response()]


def main() -> None:
    e2e = _load_e2e_module()
    run_dir = OPINION_DIR / RUN_ID
    if run_dir.exists():
        shutil.rmtree(run_dir)
    relative_run_dir = Path("examples/opinion") / RUN_ID

    cover_uri = "data:image/png;base64," + base64.b64encode(e2e.PNG_BYTES).decode()
    llm = e2e.ScriptLLM(_llm_responses())
    search = e2e.StaticSearch([])
    image = e2e.RoleImage(_COVER_PROMPT, cover_uri, e2e.IMG_URL)
    client, tokens, requests, state = e2e.make_wechat_api()
    publisher = WeChatPublisher(
        client,
        tokens,
        media=MediaService(client, tokens),
        drafts=DraftService(client, tokens),
        output_dir=relative_run_dir,
    )
    deps = PipelineDeps(
        llm=llm,
        search=search,
        image=image,
        publisher=publisher,
        author="示例作者",
        audience="公众号读者",
        word_target=500,
    )
    try:
        run = build_pipeline(CheckpointStore("examples/opinion"), deps).start(
            '写一篇500字"有本事的人往往很低调"公众号文章', run_id=RUN_ID
        )
    finally:
        client.close()

    print(f"run_id: {run.run_id}")
    print(f"state:  {run.state}")
    print(f"runs:   {len(run.checkpoint.adversarial_history)} adversarial rounds")
    for gate in run.checkpoint.adversarial_history:
        print(f"  - {gate.gate}: {gate.verdict.decision}")
    for name in sorted(run.checkpoint.artifacts):
        print(f"  - {name}.json")
    html_files = sorted(path.name for path in run_dir.glob("*.html"))
    for name in html_files:
        print(f"  - {name}")


if __name__ == "__main__":
    main()