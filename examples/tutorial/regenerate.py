"""再生成 examples/tutorial/ 离线示例（M6-T5：首个可复现示例）。

复用 tests/integration/test_e2e.py 的桩实现（fixtures 驱动的四段 LLM 响应 +
httpx.MockTransport 模拟微信 API），把一次完整「一句话 → 公众号草稿」运行的
全部中间 Artifact、checkpoint 与最终 HTML 落入本目录的 run_20260910_001/。

特性：
- 100% 离线：不访问外网，不读取任何环境变量 / 凭证；
- 确定性：run_id 固定，同一份 fixtures 每次再生成结果一致；
- 单一事实源：LLM 响应与断言全部来自 tests/fixtures（《缓存穿透》故事线）。

用法（仓库根目录执行）：
    python examples/tutorial/regenerate.py
"""

from __future__ import annotations

import base64
import importlib.util
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.state.checkpoint import CheckpointStore  # noqa: E402
from core.workflow.pipeline import PipelineDeps, build_pipeline  # noqa: E402
from integrations.search.base import SearchHit  # noqa: E402
from integrations.wechat import (  # noqa: E402
    DraftService,
    MediaService,
    WeChatPublisher,
)

TUTORIAL_DIR = Path(__file__).resolve().parent
RUN_ID = "run_20260910_001"


def _load_e2e_module():
    path = REPO_ROOT / "tests" / "integration" / "test_e2e.py"
    spec = importlib.util.spec_from_file_location("tutorial_e2e", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    e2e = _load_e2e_module()
    run_dir = TUTORIAL_DIR / RUN_ID
    if run_dir.exists():
        shutil.rmtree(run_dir)
    # 相对路径（相对仓库根）：publish_result.html_path 落盘后可移植，不携带本机绝对前缀
    relative_run_dir = Path("examples/tutorial") / RUN_ID

    cover_uri = "data:image/png;base64," + base64.b64encode(e2e.PNG_BYTES).decode()
    llm = e2e.ScriptLLM(e2e._llm_responses())
    search = e2e.StaticSearch(
        [
            SearchHit(url="https://docs.example.com/cache-penetration.html", title="缓存穿透详解"),
            SearchHit(url="https://blog.example.com/bloom-filter.html", title="布隆过滤器入门"),
        ]
    )
    image = e2e.RoleImage(e2e._fixture("visual_plan")["cover"]["prompt"], cover_uri)
    client, _tokens, _requests, _state = e2e.make_wechat_api()
    publisher = WeChatPublisher(
        client,
        _tokens,
        media=MediaService(client, _tokens),
        drafts=DraftService(client, _tokens),
        output_dir=relative_run_dir,
    )
    deps = PipelineDeps(
        llm=llm,
        search=search,
        image=image,
        publisher=publisher,
        author=e2e.AUTHOR,
        audience="初中级后端工程师",
        word_target=600,
    )
    try:
        run = build_pipeline(CheckpointStore("examples/tutorial"), deps).start(
            e2e.INTENT, run_id=RUN_ID
        )
    finally:
        client.close()

    print(f"run_id: {run.run_id}")
    print(f"state:  {run.state}")
    print(f"runs:   {len(run.checkpoint.adversarial_history)} adversarial rounds")
    for name in sorted(run.checkpoint.artifacts):
        print(f"  - {name}.json")
    html_files = sorted(path.name for path in run_dir.glob("*.html"))
    for name in html_files:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
