# v0.1 真实环境验证清单（人工执行）

> **目标（M6-T4 DoD）**：在测试号或正式号完成一次真实「一句话 → 公众号草稿箱」。
>
> 离线链路已由 274 个自动化用例覆盖（`pytest -q`，含 httpx.MockTransport 模拟的端到端）。
> 本清单只覆盖自动化无法触达的部分：**真实凭证、真实网络、真实微信后台**。
> 全部命令默认在仓库根目录执行。

## 0. 前置条件

- [ ] Python ≥ 3.11：`python --version`
- [ ] `pip install -e ".[dev]"` 安装成功
- [ ] 基线全绿：`pytest -q` 显示 274 passed
- [ ] 一家 OpenAI 兼容 LLM 网关的 API Key（OpenAI / Qwen / DeepSeek / Gemini 兼容模式均可）
- [ ] Tavily API Key（https://tavily.com 注册，免费额度即可）
- [ ] 微信公众平台账号：**测试号**（公众平台官网 → 开发者工具 → 测试号，推荐）或已认证正式号
  - 注意：草稿箱接口（`/cgi-bin/draft/add`）需要账号具备相应权限；未授权账号会返回
    api unauthorized（`errcode=48001`），此时按 §5 第 4 项记录为已知限制，不判管线失败

## 1. 环境变量

装配语义（实现契约，勿凭记忆配置）：

- **LLM / 搜索 Key 缺失 → 装配期（`load_deps`）抛 `ProviderError`**，属硬前置；
  运行期的网络故障 / 限流才走降级。
- **图片 Key 可选**：缺失不报错，运行期三级降级（生成 → 搜索 → 占位图）。
- **微信凭证缺失 → 装配期抛 `RuntimeError`**。

| 分组 | 变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| LLM | `LLM_API_KEY` | ✅ | — | OpenAI 兼容网关凭证 |
| | `LLM_BASE_URL` | | `https://api.openai.com/v1` | 自有网关（Qwen / DeepSeek 等）覆盖 |
| | `LLM_MODEL` | | `gpt-4o-mini` | |
| | `LLM_TIMEOUT` | | `30`（秒） | |
| | `LLM_PROVIDER` | | `openai_compat` | 当前唯一实现 |
| 搜索 | `TAVILY_API_KEY` | ✅ | — | Tavily Web Search |
| | `TAVILY_TIMEOUT` | | `20`（秒） | |
| | `SEARCH_PROVIDER` | | `tavily` | 当前唯一实现 |
| 图片 | `IMAGE_API_KEY` | ❌ | — | 缺省走占位图降级 |
| | `IMAGE_BASE_URL` | | `https://api.openai.com/v1` | |
| | `IMAGE_MODEL` | | `dall-e-3` | |
| | `IMAGE_TIMEOUT` | | `60`（秒） | |
| 微信 | `WECHAT_APP_ID_A` | ✅ | — | 变量名由 `accounts/<name>.yaml` 的 `env` 段决定 |
| | `WECHAT_APP_SECRET_A` | ✅ | — | secret 只存在于环境变量，不落盘 |

示例（以 DeepSeek 为例）：

```bash
export LLM_API_KEY="sk-..."
export LLM_BASE_URL="https://api.deepseek.com/v1"
export LLM_MODEL="deepseek-chat"
export TAVILY_API_KEY="tvly-..."
export IMAGE_API_KEY="sk-..."          # 可选，不配置则用占位图
export WECHAT_APP_ID_A="wx..."
export WECHAT_APP_SECRET_A="..."
```

## 2. 账号配置（secret 不落盘）

- [ ] `cp accounts/accounts.example.yaml accounts/default.yaml`
      （`load_deps` 默认读取 `accounts/default.yaml`；`env` 段只引用环境变量名，无需改动）
- [ ] 多账号：复制多份 yaml（如 `accounts/tech.yaml`），运行时传 `load_deps(account="tech")`
- [ ] 自检：`grep -rn "app_secret" accounts/` —— 只应出现 `WECHAT_APP_SECRET_A` 这类
      **变量名**，不应出现任何真实 secret

## 3. 执行真实链路

整段约 5–15 分钟（取决于 LLM 与图片生成速度）。

```bash
python - <<'PY'
from core.state.checkpoint import CheckpointStore
from core.workflow.pipeline import build_pipeline, load_deps

deps = load_deps(author="你的署名", audience="初中级后端工程师", word_target=1500)
runner = build_pipeline(CheckpointStore("outputs"), deps)
run = runner.start("写一篇讲清 Redis 缓存穿透的公众号文章")
print("run_id:", run.run_id)
print("state:", run.state)  # 期望：WorkflowState.DRAFT_CREATED
print(run.artifact("publish_result").model_dump_json(indent=2))
PY
```

- [ ] 期望输出：`state` 为 `DRAFT_CREATED`；`publish_result` 的 `status` 为
      `draft_created`，`media_id` / `draft_id` 非空，`html_path` 指向本地留档 HTML
- [ ] （可选）中断恢复演示：进程中断后 `runner.resume("<run_id>")` 从 checkpoint 续跑，
      已产出的 artifact 不重复生成

## 4. 逐项验收（Happy Path）

产物落盘（`outputs/<run_id>/`，7 份 artifact + checkpoint）：

- [ ] `research_result.json` / `content_brief.json` / `article_draft.json` /
      `content_package.json` / `validation_report.json` / `wechat_document.json` /
      `publish_result.json` 全部存在
- [ ] `checkpoint.json`：`state` 为 `DRAFT_CREATED`；`adversarial_history` 共 3 条
      （`content` / `render` / `publish` 三道门禁），每条 `verdict.decision` 均为 `PASS`
- [ ] 攻防留痕完整（H6）：每条记录含 `attack_report`，`defense_report` 在有修复时非空

产物可独立二次校验（不信任缓存，H8）：

- [ ] `python scripts/validate.py outputs/<run_id>/content_package.json`
      → stderr 显示 `PASS`，退出码 0
- [ ] `python scripts/lint.py outputs/<run_id>/article_draft.json` → 无 error

微信后台人工核对：

- [ ] 公众平台后台「草稿箱」出现一条新草稿：标题 = `article_draft.json` 的 `title`；
      作者 = 运行时传入的 `author`；封面为已上传素材（`publish_result.media_id`）
- [ ] 草稿正文可在后台预览，图片走公众号域名（`mmbiz.qpic.cn`）正常显示

本地留档（发布不是唯一出口）：

- [ ] `publish_result.json` 的 `html_path` 指向的本地 HTML 存在，内容与
      `wechat_document.json` 的 `html` 字段一致；浏览器打开排版正常

## 5. 降级出口验证（建议全部执行）

每项独立重跑 §3，验证「外部依赖故障不中断管线」：

1. [ ] **图片缺 Key**：`unset IMAGE_API_KEY` 后重跑 → 仍 `DRAFT_CREATED`；
       `content_package.json` 中 `visual.cover.asset_path` / `visual.images[].asset_path`
       为 `data:image/svg+xml;utf8,` 开头的占位图
2. [ ] **搜索运行期故障**：`export TAVILY_API_KEY=invalid-key` 重跑 → 装配成功、
       运行期 401 被降级包装吞掉 → 管线继续至 `DRAFT_CREATED`
       （`research_result` 的 sources 可能减少，不视为失败）
3. [ ] **微信链路故障**：`export WECHAT_APP_SECRET_A=wrong-secret` 重跑 →
       token 接口 `errcode≠0` → `publish_result.status` 为 `degraded`、`degraded=true`、
       `html_path` 仍有本地留档；run 终态仍为 `DRAFT_CREATED`
4. [ ] （仅无权限账号）**draft/add 返回 `errcode=48001`**：同样落入 `degraded` 出口，
       本地 HTML 留档；记录截图，归档为账号权限限制

## 6. 安全自检

- [ ] `grep -rn "app_secret" accounts/` 只含变量名（同 §2）
- [ ] `git status --short`：`accounts/`（example 除外）与 `outputs/` 均未进入版本库
      （`.gitignore` 已覆盖，此处复核）
- [ ] `outputs/<run_id>/` 下所有 JSON（含 `checkpoint.json`、`publish_result.json`）
      无 app_secret / api key 明文
- [ ] 本轮验证使用的 key 均来自环境变量，未写入任何仓库文件

## 7. 结果记录

| 项 | 值 |
| --- | --- |
| 验证人 / 日期 | |
| 账号类型 | 测试号 / 正式号 |
| 一句话意图 | |
| run_id | |
| 最终状态 | `DRAFT_CREATED` |
| publish_result.status | `draft_created` / `degraded` |
| 草稿箱截图 | （链接） |
| §5 降级验证结果 | 1 / 2 / 3（/ 4） |
| 异常与备注 | |

## 附：常见错误速查

| 现象 | 原因与处理 |
| --- | --- |
| `ProviderError: 缺少环境变量 LLM_API_KEY` | 装配期硬前置；配置后重跑 |
| `ProviderError: 缺少环境变量 TAVILY_API_KEY` | 同上 |
| `RuntimeError: missing credentials for account ...` | 未设置 `WECHAT_APP_ID_A` / `WECHAT_APP_SECRET_A` |
| `FileNotFoundError: account config not found` | 缺 `accounts/default.yaml`，从 example 复制 |
| `errcode=40164`（invalid ip） | 出口 IP 不在公众平台 IP 白名单，后台添加后重试 |
| `errcode=40001 / 40125` | app_secret 错误或已被重置 |
| `errcode=48001`（api unauthorized） | 账号无草稿箱接口权限，见 §5 第 4 项 |
