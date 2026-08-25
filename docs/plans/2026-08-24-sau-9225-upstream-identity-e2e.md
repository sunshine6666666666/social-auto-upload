# SAU 9225 上游整合、账号身份闸门与三平台真实验收实施计划

> **Executor:** 低能力自主执行 agent，在下述实时权限与工具合同下工作。必须从头读完本文，严格按顺序执行；不得猜测省略项、扩大范围或要求用户做例行选择。

**Goal:** 在 `social-auto-upload` 当前 `main` 工作区中完成选定抖音/哔哩哔哩上游能力的择优整合、9225/浏览器名选择、YouTube/哔哩哔哩/抖音稳定账号身份校验、Bilibili CDP→biliup 转换，并用 2026-08-29 20:00 Asia/Shanghai 的三平台真实定时发布完成验收；保留用户现有改动且不提交、不推送、不删除测试作品。

**Done when:** 10 个任务全部通过；三平台 `identity` 命令均返回包含稳定 ID 的 JSON；发布前与提交前稳定 ID 一致，否则程序阻止提交；`9225` 和 `SAU-自媒体运营-9225` 均解析到同一个健康浏览器；选定上游功能有逐提交对照与测试；所有本地测试通过；YouTube、哔哩哔哩、抖音后台各存在且仅存在一条标题含唯一测试标识、计划于 `2026-08-29 20:00 Asia/Shanghai` 发布的作品，并记录账号、封面、排期和作品标识的脱敏读回证据。

**Workspace root:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Repository root:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Plan file:** `/Users/yelin/Developer/agent-tools/social-auto-upload/docs/plans/2026-08-24-sau-9225-upstream-identity-e2e.md`
**Target environment:** 本地开发环境；macOS Darwin 24.6.0 arm64；zsh；Python 3.14.6（项目声明支持 3.10–3.12，因此执行测试时优先复用仓库现有虚拟环境中的受支持 Python，若没有则先用当前解释器做基线并记录兼容结果）；ffmpeg 8.0。
**Execution mode:** `unattended`
**Live permission contract:** 2026-08-24 21:51 CST 核验；`workspace-write`，审批 reviewer 为 `auto_review`；仓库根、`/private/tmp`、当前可视化目录可写；网络受限；桌面受管浏览器目录与 GUI/CDP 连接需范围精确的自动审查升级。Auto-review 是审查器，不等于 Full Access；被拒绝时只能走本文给出的更安全路径，不得绕过。
**Architecture/approved approach:** 保留当前 fork 的 CDP 运行时与定时发布能力，不整库合并上游。逐个比较选定的 Bilibili/Douyin 提交，只移植仍有价值且测试证明更好的行为。新增一个最小浏览器选择器，把名称或端口解析为现有 `cdp_url`，不在仓库硬编码 9225；三平台输出同一最小身份结构，并在不可逆提交前进行稳定 ID 二次校验。Bilibili 不复制整个 Chrome Profile，只从指定 CDP 会话导出所需 Cookie 到现有 biliup JSON 载体。
**Tech stack:** Python、`argparse`、`asyncio`、Patchright/Playwright CDP、`requests`、标准库 `unittest`、外部 `biliup`、ffmpeg；不得新增第三方依赖。

## Required Skills

- `writing-plans`
  - SKILL.md: `/Users/yelin/.codex/skills/writing-plans/SKILL.md`
  - Lessons: `/Users/yelin/.codex/skills/writing-plans/references/lessons.md`
  - Use for: 无人值守续跑、权限/失败/验收边界、Progress Ledger。
- `openai-docs`
  - SKILL.md: `/Users/yelin/.codex/skills/.system/openai-docs/SKILL.md`
  - Lessons: `none found`
  - Use for: 启动时刷新 Auto-review、sandbox、长任务与 Goal 合同。
- `browser-fleet-manager`
  - SKILL.md: `/Users/yelin/.codex/skills/browser-fleet-manager/SKILL.md`
  - Lessons: `/Users/yelin/.codex/skills/browser-fleet-manager/references/lessons.md`
  - Use for: 9225 名称、端口、Profile、进程、CDP 多锚点校验。不得读取 Cookie/密码/Token。
- `understand-anything:understand-chat`
  - SKILL.md: `/Users/yelin/.agents/skills/understand-chat/SKILL.md`
  - Lessons: `none found`
  - Use for: 仅在 CodeGraph 与源码关系冲突时，用现有知识图交叉验证；不得重建索引。

## Applicable Rules

- `/Users/yelin/Developer/agent-tools/social-auto-upload/AGENTS.md`: 始终简体中文；先读后写；KISS/DRY/YAGNI/SOLID；普通命令优先 `rtk`，安全、认证、完整 diff 使用 raw；路径双引号；不得未经要求创建分支、commit、push；Browser Harness 先打开页面再 `page_info()`，发现 `domain_skill_files` 后必须先读完全部 Markdown。
- `/Users/yelin/.codex/skills/browser-fleet-manager/SKILL.md`: 个人 Chrome 与 9223/9224 不操作；只管理已登记的 `SAU-自媒体运营-9225`；名称、端口、Profile、进程任一冲突立即停止浏览器动作。
- PONYTAIL full: 复用 `utils/browser_runtime.py`、当前 CLI、biliup 与 unittest；不增加框架、数据库、账号账本或依赖。

## Scope

- In scope:
  - Bilibili 提交 `945bf8e`（封面）及其 merge 包装 `d32280c` 的有效行为。
  - Douyin 提交 `77b372a`、`fa59d50`、`be77aae`、`395c643`、`723f703`、`e89d3a8`、`f83225c`、`dde0eac`、`ad49eba`、`5628f76` 的逐项对照；revert/merge 包装仅作为历史语义，不机械重复应用。
  - `--browser 9225` 或 `--browser "SAU-自媒体运营-9225"` 到健康 CDP 的解析，同时保留现有 `--cdp-url`/`SAU_CDP_URL` 兼容。
  - YouTube、Bilibili、Douyin 账号身份 JSON、发布前后二次稳定 ID 校验、错账号阻断。
  - Bilibili 从 CDP 导出为 biliup JSON；不复制 Profile。
  - 单元、集成、回归和三平台真实定时发布验收。
- Out of scope:
  - 上游其余平台、其余 34 个独立功能提交、前端、数据库、账号相似度算法、浏览器账号账本、跨平台统一账号 ID、自动删除测试作品。
  - 修改个人浏览器 PID 610、9223、9224，或直接编辑 `/Users/yelin/Desktop/ManagedBrowsers/registry.json`。
  - 创建分支/worktree、commit、push、PR、release、部署。
- Allowed side effects:
  - 编辑本仓库内明确列出的源文件与测试；在 `/private/tmp/sau-e2e-20260829` 生成测试媒体和脱敏证据。
  - 只读连接并打开 `SAU-自媒体运营-9225` 的标签页；把 9225 已登录会话导出到仓库忽略的 `cookies/*` 本地文件，绝不打印其内容。
  - 用户已在本任务中明确授权：在 YouTube、Bilibili、Douyin 各创建一条计划于 `2026-08-29 20:00 Asia/Shanghai` 发布的真实定时作品。每平台最多一次最终提交；失败后未经去重读回不得再次提交。
- Human-gated side effects:
  - 除上述三条定时作品以外的任何外部写入、立即发布、评论/消息、删除作品、修改账号、安装全局包、删除/移动文件、停止/改名/退役浏览器均未授权，禁止执行。用户将离开，不能留下扫码、验证码、权限或选择问题；出现此类真正前置条件时完成所有安全本地工作并按 Goal 实时规则处理 blocker，不得伪造完成。

## Goal Contract

- 第一动作先重新读取 `openai-docs`，刷新官方 Auto-review、sandbox、Goal 页面；记录时间与 URL。随后检查当前 permission profile 和实际 Goal tool schema。只有 live contract 仍支持本计划，才开始昂贵工作。
- 首次执行且 `create_goal` 实际可用时，调用它，`objective` 必须逐字使用本计划顶部 **Goal**，不得设置 token budget。不要输入字面 `/goal`。
- 恢复执行时先调用实际可用的 `get_goal`，不得重复创建 Goal；重读本文、Lessons、Progress Ledger、`git status --short` 与相关进程。
- 持续执行所有安全且已授权步骤，不询问用户例行权限或实现选择。需要越界时使用当前工具的 `require_escalated` 交给 Auto-review，justification 必须精确到 9225、目标站点和只读/已授权发布动作；若拒绝，仅用本文安全 fallback，不能重复同一请求或绕过。
- 只在全部验收通过后按 live schema 调用 `update_goal(status="complete")`。`blocked` 只按当时工具说明允许的真实阈值使用；预算将尽、测试暂时失败、三平台只成功两平台都不是完成。

## Live OpenAI Contract Evidence

- 官方文档检索日期：`2026-08-24`。
- Sandbox: `https://learn.chatgpt.com/docs/sandboxing`
- Auto-review: `https://learn.chatgpt.com/docs/sandboxing/auto-review`
- Agent approvals & security: `https://learn.chatgpt.com/docs/agent-approvals-security`
- Long-running work: `https://learn.chatgpt.com/docs/long-running-work`
- Follow a goal: `https://learn.chatgpt.com/use-cases/follow-goals`
- 作者运行时已暴露 `create_goal({objective, token_budget?})`、`get_goal({})`、`update_goal({status: complete|blocked})`；执行器仍必须以自己的实时 schema 为准。

## Permission Feasibility

| 资源/副作用 | 需要 | 当前路径 | 判定与 fallback |
| --- | --- | --- | --- |
| 仓库源文件、测试、计划 | 写 | workspace-write | 可自动执行；用 `apply_patch`，保留脏文件。 |
| `/private/tmp/sau-e2e-20260829` | 写 | 允许根 | 可自动执行；不放秘密。 |
| Desktop 受管浏览器 Profile | 只通过 Chrome/CDP 使用 | 精确 Auto-review | 已验证 audit 成功；不得直接读 Profile/Cookie DB。 |
| 9225 CDP | 本机连接 | 精确 Auto-review | 已验证运行健康；失败先 audit/resolve，一次安全重试。 |
| GitHub upstream | fetch/read | `git fetch upstream` 已批准 | 可读；不得 push。网络拒绝时使用已 fetch 的对象。 |
| YouTube/Bilibili/Douyin | 读身份及各一次定时发布 | 用户已明确授权，Auto-review 审查 | 发布前做去重和身份闸门；审查拒绝时不得绕过，保留本地证据。 |
| 系统 TTS/ffmpeg | 本地生成 | `/usr/bin/say`、`/opt/homebrew/bin/ffmpeg` | 无外部版权素材；命令缺失时用 ffmpeg 纯合成音并记录偏差，但视频仍需 AAC 音轨。 |
| Cookie/Token | 本地敏感数据 | `cookies/` ignored | 只能程序读写，禁止 stdout、计划、截图、git diff。 |

## Current-State Evidence

- 当前分支 `main`，HEAD `0a2052b`；`upstream/main` 为 `1c66b7d`；`HEAD...upstream/main = 16 46`。
- 脏树仅见下列用户文件，全部保留：`.codegraph/`、`.understand-anything/`、`AGENTS.md`、`_devkeeper_xhs_publish_smoke.png`、`architecture-overview.html`、`qrcode.png`。
- `.codegraph` 已存在且 up to date：95 files、1581 nodes、4018 edges；不要初始化或删除。
- 现有 `utils/browser_runtime.py` 已实现 `open_browser_session(..., cdp_url=...)`，连接 CDP 时复用持久 context；显式 `storage_state` 时创建专用 context，避免共享浏览器当前账号偷偷覆盖指定账号。
- YouTube CLI 已贯通 `cdp_url`、`--no-submit`、schedule 与 Studio 读回；Douyin request/uploader 已有 `cdp_url`，但 `sau_cli.upload_video()`/`upload_note()` 的 `douyin_setup(..., handle=False)` 没有传它，`check` 也只校验 Cookie 文件；Bilibili 只使用 biliup JSON，无 CDP 入口。
- 9225 audit（2026-08-24）：`SAU-自媒体运营-9225`，端口 9225，PID 49375，Profile `/Users/yelin/Desktop/ManagedBrowsers/active/SAU-自媒体运营-9225--9225/profile`，`status=running`、`health=ok`、无 problems；CDP `http://127.0.0.1:9225`。
- 受保护对象：个人 Chrome PID 610；`AgentPool-共享主浏览器-9223` PID 21881；`热点监控-9224` PID 25773。不得操作。
- 只读预检成功停留在 `https://studio.youtube.com/`（标题 YouTube 创作者工作室）、`https://member.bilibili.com/platform/home`（创作中心）、`https://creator.douyin.com/creator-micro/home`（抖音创作者中心），均未跳登录域。YouTube 额外 DOM probe 曾超时，不能据此判定登出；执行期必须以新身份命令的稳定 ID 为唯一硬判据。
- ffmpeg 8.0 可用；`browser-harness` 路径 `/Users/yelin/.local/bin/browser-harness`。Browser Harness 当前不支持 `-c`，脚本必须 stdin 输入。

## Requirement Traceability

| Requirement | Implemented by | Verified by |
| --- | --- | --- |
| 选择性整合 Bilibili/Douyin 上游 | Task 2、7 | 逐提交矩阵、focused tests、完整 diff |
| 端口/名称选择且不硬编码 9225 | Task 3 | `test_sau_browser_cli.py` 名称/端口/冲突测试 |
| 三平台尽可能多的账号信息 | Task 4、5 | 三个 `identity --browser ...` JSON |
| 身份缺失/变化阻止发布 | Task 4、5 | 单元测试 + E2E 提交前日志 |
| Bilibili 复用 9225 登录态 | Task 6 | CDP→biliup 转换、UID 一致、`renew` 成功 |
| 抖音短信/声明/封面/合集稳健性 | Task 2、7 | 上游对照与 Douyin regression tests |
| Bilibili 自定义封面 | Task 2、7、10 | 参数测试 + 后台读回封面 |
| 三平台真实排期 | Task 9、10 | 每平台一条 2026-08-29 20:00 读回证据 |

## File Map

| Action | Absolute path | Responsibility |
| --- | --- | --- |
| Create | `/Users/yelin/Developer/agent-tools/social-auto-upload/utils/browser_selector.py` | 仅把 `--browser` 名称/端口解析为已核验 `BrowserTarget`，复用 fleet manager，不管理生命周期。 |
| Create | `/Users/yelin/Developer/agent-tools/social-auto-upload/utils/account_identity.py` | 最小统一 `AccountIdentity` 数据结构、JSON、稳定 ID 前后校验。 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/sau_cli.py` | 新 CLI 参数/action、解析 target、调用身份闸门、Bilibili 转换。 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/uploader/youtube_uploader/main.py` | 从 Studio 获取 identity，并在最终点击前二次核对。 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/uploader/douyin_uploader/main.py` | CDP auth/identity、短信/声明/封面/合集择优整合、最终点击前核对。 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/uploader/bilibili_uploader/runtime.py` | CDP Cookie→biliup JSON、Bilibili identity、脱敏读回辅助。 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_sau_browser_cli.py` | 浏览器 selector、CDP 传递、冲突阻断。 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_sau_bilibili_cli.py` | converter contract、identity guard、封面/排期命令。 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_bilibili_runtime.py` | biliup JSON、nav identity、敏感输出保护。 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_sau_douyin_cli.py` | SMS、声明、封面、合集、CDP setup、身份变化阻断。 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_youtube_schedule.py` | YouTube identity 与提交前二次核对。 |
| Optional create only if existing test files become incoherent | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_account_identity.py` | 仅放跨平台共享数据结构测试；能放进已有测试则不创建。 |

## Interface Contracts

- `BrowserTarget` in `utils/browser_selector.py`
  - Fields: `name: str`, `port: int`, `cdp_url: str`。
  - `resolve_browser_target(selector: str | None, legacy_cdp_url: str | None = None) -> BrowserTarget | None`。
  - `selector` 为纯数字时：调用 fleet `audit` JSON，找到唯一 `registered.port`，要求 `status=running`、`health=ok`、`problems=[]`，再按名称调用 `resolve --name` 复核；为名称时直接 `resolve --name`。两者同时指定或解析不唯一、未运行、冲突、URL 非 localhost 均 `ValueError/RuntimeError`，CLI exit 1；不得自动创建/启动/改端口。
  - `legacy_cdp_url` 单独存在时保持兼容，解析 localhost 端口；若能在 audit 中匹配受管浏览器则返回完整 target，不能匹配则允许旧 CDP 流程但 identity 中 `browser_name=null`；`--browser` 与 `--cdp-url` 同时出现立即拒绝。
- `AccountIdentity` in `utils/account_identity.py`
  - Fields: `platform: str`, `logged_in: bool`, `stable_id: str | None`, `display_name: str | None`, `handle: str | None = None`, `profile_url: str | None = None`, `browser_name: str | None = None`, `cdp_port: int | None = None`, `observed_at: str`（UTC ISO-8601），`extra: dict[str, str | int | bool | None]`。
  - `to_dict()` 只返回 JSON 可序列化值，禁止 Cookie/Token/CSRF。
  - `require_publish_identity(identity)` 要求 `logged_in is True` 且 `stable_id` 非空，否则 `RuntimeError`。
  - `assert_same_publish_identity(expected, observed)` 要求 platform 和 stable_id 完全一致；nickname/handle 变化只记录不阻断，稳定 ID 变化或缺失阻断。
- CLI contract in `sau_cli.py`
  - `add_runtime_flags()` 增加 `--browser`，默认 `SAU_BROWSER`；与 `--cdp-url`/`SAU_CDP_URL` 做运行时互斥校验，避免 argparse 默认环境值绕过互斥组。
  - YouTube/Douyin/Bilibili 都增加 `identity --account NAME [--browser NAME_OR_PORT] [--cdp-url URL]`；Bilibili 的 `login/check/upload-video` 也接受 runtime flags。
  - Identity stdout 必须只有一行 JSON；诊断写 stderr；成功 exit 0，未登录/无稳定 ID exit 1。
- Platform stable IDs:
  - YouTube: channel ID（`UC...`）为 stable_id；display_name=channel name；handle/profile URL 尽力提供。
  - Bilibili: numeric MID/UID 为 stable_id；display_name=uname；profile URL=`https://space.bilibili.com/{mid}`。
  - Douyin: 优先 creator API/页面状态中的 `uid`，其次 `sec_uid`/douyin_id 中最稳定的非昵称标识；extra 可含其余 ID。任何只拿到昵称的情况视为无稳定 ID并阻止发布。
- Bilibili converter:
  - `async export_bilibili_cdp_account(cdp_url: str, account_file: Path, target: BrowserTarget | None) -> AccountIdentity`。
  - 通过 `open_browser_session` 连接现有 context，获取 Bilibili 域 Cookie并调用 nav/creator endpoint确认 MID；原子写入 `account_file.tmp`，验证 JSON 与 identity 后 `replace`。失败不得覆盖已有文件。
  - JSON 至少包含 `cookie_info.cookies`（biliup 可读的 name/value/domain/path/expires/http_only/secure/same_site 字段）、`token_info.mid`、`platform`；具体键值以本机 biliup `renew` 和现有测试 schema为准，禁止猜 token。
  - stdout/stderr/异常不得包含 Cookie value、CSRF、Authorization。

## Progress Ledger

| Task | Status | Completion evidence |
| --- | --- | --- |
| Task 1 | complete | 2026-08-24 22:05 CST；已刷新官方文档：`https://learn.chatgpt.com/docs/sandboxing`、`/docs/sandboxing/auto-review`、`/docs/agent-approvals-security`、`/docs/long-running-work`、`/use-cases/follow-goals`；实时 `get_goal({})` 无 active goal，已用顶部 Goal 原文 `create_goal({objective})` 创建 active Goal（未设预算）。权限为 workspace-write、auto_review，仓库/`/private/tmp` 可写；`rtk codegraph status`：95 files/1581 nodes/4018 edges，up to date；browser audit/resolve：9225 名称、端口、Profile、PID 49375、CDP 与 running/ok 四锚点一致；个人 PID 610、9223/9224 仅审计未操作。基线：系统 Python 3.14 缺 `requests`/`patchright`，仓库 `.venv` Python 3.11.15 运行 `88 tests`，`OK`。`rtk git status --short` 保留原始脏项，并记录计划目录为既有未跟踪项；`git diff --check` 待代码任务完成后复核。 |
| Task 2 | complete | 2026-08-24 22:12 CST；已 `git fetch upstream`，`HEAD...upstream/main = 16 46`。逐提交 raw 对照矩阵：`945bf8e` Bilibili 自定义封面为 `port-minimal`，但当前 fork 已含 `thumbnail_file`→`--cover`、parser 与回归测试，保留现状；`d32280c` merge wrapper 为 `context-only`，不重复应用；`77b372a` SMS 弹窗检测为 `port-minimal`（移植检测/阻断，不移植等待或读取验证码）；`fa59d50` revert 为 `context-only`；`be77aae` SMS 最终行为为 `port-minimal`；`395c643` 交互输入为 `port-minimal`（只保留可测试检测，unattended 不读/猜码）；`723f703` merge wrapper 为 `context-only`；`e89d3a8` 显式声明/失败闭环为 `port-minimal`；`f83225c` 位置兼容为 `combine`（与 fork 的 cdp_url 字段共同保持旧位置参数）；`dde0eac` merge wrapper 为 `context-only`；`ad49eba` 封面、合集、声明稳健性为 `combine`（复用 CDP 运行时，采用最小原生点击/浮层清理/合集可选跳过）；`5628f76` merge wrapper 为 `context-only`。未运行 cherry-pick。 |
| Task 3 | complete | 2026-08-24 22:20 CST；新增 `utils/browser_selector.py`：仅通过 fleet audit/resolve 校验名称、端口、running/ok、problems=[]、localhost CDP 与端口一致，不硬编码 9225/9223 或名称；legacy localhost CDP 保持兼容，`--browser`/`--cdp-url` 互斥。`tests.test_sau_browser_cli`：28 tests OK，覆盖名称、端口 audit→resolve、未运行/冲突、legacy URL、CLI flags、CDP 传递；live 只读 `youtube check --browser 9225` 与名称版本均解析到账号检查并返回 `invalid`（无参数错误）。|
| Task 4 | complete | 2026-08-24 22:27 CST；新增 `utils/account_identity.py` 与 `tests/test_account_identity.py`。`AccountIdentity` 输出 JSON-safe UTC `observed_at`，extra 拒绝 cookie/token/authorization/csrf/password 键；`require_publish_identity` 与 `assert_same_publish_identity` 对缺失/登出/stable_id 变化返回 blocked，昵称/handle 变化不阻断。测试 `5 tests`，`OK`。 |
| Task 5 | in_progress | 2026-08-24 22:47 CST；YouTube/Douyin identity 提取、JSON CLI、发布前稳定 ID 二次校验已实现；YouTube 页面仍只读可见频道 URL `.../channel/UC04E0U6ZAZoD5y3lcVNUNHQ`（已脱敏结构化读取），抖音页面稳定字段仍为空，不能伪造 stable_id。清理本任务遗留的三个 9225 Browser Harness daemon 后，Node 原生 WebSocket 只读 `Browser.getVersion` 成功，但 `.venv` Patchright `connect_over_cdp` 仍在 15s 内超时并出现 Network session closed，故外部 identity CLI 仍未恢复。 |
| Task 6 | in_progress | 2026-08-24 22:47 CST；`export_bilibili_cdp_account` 已实现 CDP Cookie→biliup JSON、MID/nav 登录校验、0600 临时文件原子 replace、失败保留旧文件；`read_bilibili_account_identity` 与 CLI `login/check/identity/upload-video --browser` 接入。`tests.test_bilibili_runtime tests.test_sau_bilibili_cli tests.test_sau_browser_cli` 50 tests OK；Browser Harness 9225 哔哩哔哩创作中心重复只读检查仍为 `loggedIn:false, uid:null`；Node CDP 探针成功但 Patchright converter/renew/identity 仍超时，未读取/输出 Cookie，未宣称成功。 |
| Task 7 | complete | 2026-08-24 22:38 CST；采用 `be77aae/395c643` 的短信弹窗检测但无人值守直接 blocked，不读取/猜码；采用 `e89d3a8/f83225c` 的显式声明与位置兼容；采用 `ad49eba` 的描述填充、封面原生点击重试/双比例输入、合集可选跳过；CDP 路径复用 9225 现有 context，短信/身份 blocked 不被发布重试吞掉；保留当前 CDP 运行时。Douyin/Bili focused 37 tests OK；未重复 revert/merge wrapper。 |
| Task 8 | complete | 2026-08-24 22:38 CST；focused `tests.test_sau_browser_cli tests.test_sau_douyin_cli tests.test_sau_bilibili_cli tests.test_bilibili_runtime tests.test_youtube_schedule tests.test_youtube_duration`：89 tests OK；YouTube identity HTML fallback补测 16 tests OK；full `.venv/bin/python -m unittest discover -s tests`：110 tests OK；py_compile changed source/tests OK；`git diff --check` OK；security scan仅命中新增测试中的拒绝字段 fixture及既有未改动 `uploader/xhs_uploader/xhs_login_qrcode.py:31` cookie输出；未新增依赖/跳过测试。随后修正 Douyin CDP 上传不再误用本地 storage_state，并让短信/身份 blocked 异常不被发布重试循环吞掉；同时让已注册但不健康的 legacy CDP 目标 fail-closed，聚焦 44 tests 与 full 110 tests 均再次 OK。最终 `rtk codegraph sync .`：2 changed files/62 nodes；`rtk codegraph status`：98 files/1687 nodes/4322 edges up to date；`rtk codegraph affected` 无受影响测试文件（另以全量测试覆盖）。raw diff 已复核，工作区原始脏项保留，未创建分支/提交/推送。 |
| Task 9 | pending | — |
| Task 10 | pending | — |

### Task 1: 启动门、Goal、基线与安全快照

**Purpose:** 确认执行环境仍能无人值守，冻结可比较的基线，不改业务代码。
**Prerequisites:** 当前 checkout 必须就是 `/Users/yelin/Developer/agent-tools/social-auto-upload`。
**Risk level:** safe。

- [ ] **1.1 刷新官方合同并创建/恢复 Goal**
  - 读完整 `openai-docs` 与 writing-plans Lessons；只访问本文列出的官方域。记录 retrieval time、URL、permission profile、Goal schema。
  - 调用 live `get_goal`；无 active goal 才用本文 Goal 调 `create_goal`，不设预算。
  - Success: Goal objective 逐字一致，状态 active，合同支持 workspace 写、精确 Auto-review 与 Goal 续跑。
  - Failure: Goal tools缺失或外部发布必需能力变成人工确认时，不开始外部动作；完成可做的只读证据后按 live blocker 规则处理。
- [ ] **1.2 核验仓库和浏览器**
  - Run from repo:
    - `rtk git status --short`
    - `rtk codegraph status`
    - `python3 "/Users/yelin/.codex/skills/browser-fleet-manager/scripts/browser_fleet.py" audit`
    - `python3 "/Users/yelin/.codex/skills/browser-fleet-manager/scripts/browser_fleet.py" resolve --name "SAU-自媒体运营-9225"`
  - Expected: 仅本文列出的 6 个原始脏项外加本计划；CodeGraph up to date；9225 running/ok 且四锚点一致。
  - Failure: 名称/端口/Profile/进程冲突立即停止所有浏览器与发布动作；不得 start/stop/update。
- [ ] **1.3 建立基线**
  - Run: `rtk python -m unittest discover -s tests`
  - 若 RTK 输出截断/混淆或失败，立即 raw：`rtk proxy python -m unittest discover -s tests -v`。
  - 记录测试数、失败名。任何既有失败必须完整记录且与改动分开，不得默认为可忽略。
- [ ] **Task acceptance**
  - `git diff --check` exit 0；原始脏文件未改变；Ledger 有时间戳、Goal、权限、浏览器、基线测试证据。

### Task 2: 逐提交比较选定上游行为

**Purpose:** 只移植有效行为，避免 cherry-pick merge/revert 重复或覆盖 fork 改动。
**Prerequisites:** Task 1。
**Risk level:** safe（只读）。

- [ ] **2.1 刷新 upstream 并确认分叉**
  - Run: `git fetch upstream`，然后 `rtk git rev-list --left-right --count HEAD...upstream/main`。
  - Expected baseline: `16 46`；若 upstream 又前进，只研究本文列出的 commit，不扩 scope。
  - 网络被拒时直接用本地已 fetch 对象，不循环请求。
- [ ] **2.2 建立 Bilibili 对照**
  - Raw commands: `RTK_DISABLED=1 git show --stat --patch 945bf8e -- "sau_cli.py" "tests/test_sau_bilibili_cli.py"` 与 `RTK_DISABLED=1 git show d32280c --stat`。
  - 记录：上游封面参数、biliup `--cover`、测试；对照当前 fork 已有实现。当前 fork 若已等价或更强，只保留并补回归测试，不重复改。
- [ ] **2.3 建立 Douyin 10 提交状态矩阵**
  - 对每个 hash 分别运行 raw `git show --stat --patch HASH -- "sau_cli.py" "uploader/douyin_uploader/main.py" "tests"`。
  - 矩阵状态只能是：`context-only(revert/merge)`、`already-superior`、`port-minimal`、`combine`。
  - 明确 77b372a 被 fa59d50 完整撤销；723f703/dde0eac/5628f76 是包装；最终行为重点来自 be77aae、395c643、e89d3a8、f83225c、ad49eba，并与 fork 当前 CDP/封面/合集逻辑组合。
  - 禁止运行 `git cherry-pick`。
- [ ] **Task acceptance**
  - Ledger 附 12 个 hash（含 merge wrapper）的状态、涉及文件、采用/不采用原因；不得出现“全部拉下来再看”。

### Task 3: 最小浏览器名称/端口选择器

**Purpose:** 用户传 `9225` 或名称即可复用已有 CDP，不硬编码仓库端口，不重复造浏览器管理器。
**Prerequisites:** Task 2。
**Risk level:** reversible mutation。

- [ ] **3.1 先写失败测试**
  - 在 `tests/test_sau_browser_cli.py` 增加：名称 resolve、数字端口 audit→resolve、未运行/冲突拒绝、`--browser` 与 `--cdp-url`/env 冲突、legacy cdp 兼容、Bilibili runtime flags。
  - 全部 mock subprocess JSON，不读取真实 Desktop。
  - Run: `rtk python -m unittest tests.test_sau_browser_cli`；Expected: 新测试因 symbol/flag 不存在而失败。
- [ ] **3.2 实现 `utils/browser_selector.py`**
  - 只用 dataclass/json/subprocess/pathlib/urllib.parse；fleet script 路径从 `Path.home()/".codex/skills/browser-fleet-manager/scripts/browser_fleet.py"` 推导。
  - subprocess 使用参数数组、timeout=15、capture_output；解析失败只输出脱敏诊断。
  - 端口范围只校验 1–65535；不内置 9225、9223–9299 或浏览器名字。
- [ ] **3.3 接入 CLI**
  - `add_runtime_flags` 加 `--browser`；dispatch 在创建 request 前统一 resolve，再把 target.cdp_url 传给现有字段。不要给每个平台复制解析代码。
  - `--browser`/`SAU_BROWSER` 与 `--cdp-url`/`SAU_CDP_URL` 同时非空时明确 exit 1。
- [ ] **Task acceptance**
  - `rtk python -m unittest tests.test_sau_browser_cli` 全绿。
  - 只读 live commands：`python sau_cli.py youtube check --account sau9225 --browser 9225` 与名称版本至少走到账号检查而非参数错误；此时不以 cookie valid 作为 Task 3 成败。
  - `git diff --check`；scope 仅 selector、CLI、对应测试。

### Task 4: 统一身份数据结构与硬闸门

**Purpose:** 给未来平台一个稳定、机器可比较的最小输出；不建立人工维护账号账本。
**Prerequisites:** Task 3。
**Risk level:** reversible mutation。

- [ ] **4.1 测试共享 contract**
  - 覆盖 JSON 可序列化、UTC observed_at、logged_out/空 stable_id 阻断、stable_id 变化阻断、仅 nickname/handle 变化不阻断、禁止 secret 键名进入 output。
  - Secret 键扫描至少拒绝大小写无关的 `cookie`、`token`、`authorization`、`csrf`、`password` 出现在 `extra`。
- [ ] **4.2 实现 `AccountIdentity` 与 guard**
  - 严格按 Interface Contracts；不要加数据库、registry、provider interface 或 similarity 逻辑。
  - 异常文本只含 platform、browser name/port 与缺失字段，不含页面状态原文中的秘密。
- [ ] **Task acceptance**
  - `rtk python -m unittest tests.test_account_identity`（若测试合入现有文件则运行对应 module）全绿；一个 expected/observed stable_id 不同的 fixture 必须抛出且消息含 `blocked` 或中文“阻止”。

### Task 5: YouTube 与 Douyin 身份读取及提交前复核

**Purpose:** 输出真实发布账号，并在 UI 最终不可逆点击前防止账号切换。
**Prerequisites:** Task 4。
**Risk level:** reversible mutation；本任务不真实提交。

- [ ] **5.1 YouTube identity**
  - 在现有 uploader 内复用其已打开的 Studio page/context，优先读 Studio 自身可见 channel ID/handle 或页面内 API；不得只用 account 文件名。
  - `identity` action 可单独连接 target；upload 进入 Studio 后获取 expected；最终 publish/schedule click 前再次获取 observed 并 `assert_same_publish_identity`。
  - 保持当前 `--no-submit` 和 schedule readback。
- [ ] **5.2 Douyin identity 与 CDP readiness**
  - 给 `cookie_auth(account_file, cdp_url=None)` 增加 CDP 路径：cdp 存在时复用 existing context检查 creator 页面，不能再启动另一个 Chrome；`douyin_setup(...handle=False)` 必须传 request.cdp_url。
  - `check` 接受 runtime flags；identity 提取优先稳定 uid/sec_uid/douyin_id，昵称不是 stable_id。
  - `DouYinVideo` 进入发布页后取 expected，点击“发布/定时发布”前再取 observed。
- [ ] **5.3 单独 identity CLI**
  - 三平台 stdout 单行 JSON；本 Task 先接 YouTube/Douyin。错误写 stderr，exit 1。
- [ ] **Task acceptance**
  - Run: `rtk python -m unittest tests.test_youtube_schedule tests.test_sau_douyin_cli tests.test_sau_browser_cli`。
  - Live read-only: 两个平台分别以 `--browser 9225` 和名称运行 identity；两种 selector 对同平台返回相同 non-empty stable_id。将脱敏 JSON 写 `/private/tmp/sau-e2e-20260829/identity-preflight.json`，不得含 secrets。
  - 任一平台无稳定 ID：禁止进入 Task 9/10 的该平台提交，但继续完成本地实现和其他测试；不要让昵称兜底。

### Task 6: Bilibili 9225→biliup 转换与身份校验

**Purpose:** 让 SAU 仅收浏览器名称/端口就能使用 9225 的 Bilibili 登录态，同时保持 biliup 上传链。
**Prerequisites:** Task 4、5。
**Risk level:** reversible sensitive local mutation；不发布。

- [ ] **6.1 写 converter/identity 单元测试**
  - Mock CDP cookies与 `/x/web-interface/nav`：成功写 `cookie_info.cookies`、`token_info.mid`、`platform`；MID不一致、无关键 Cookie、nav logged_out、temp write失败均不覆盖旧文件；日志不含 fake secret值。
  - 用 `tempfile.TemporaryDirectory`，不得读取真实 `cookies/bilibili_peach-english.json`。
- [ ] **6.2 实现原子导出**
  - 在 `runtime.py` 使用现有 `open_browser_session`；连接 9225 的 existing context；获取 Bilibili domains cookies；调用 nav确认 `isLogin`、mid、uname。
  - 临时文件 mode 0600；JSON验证后 replace；finally 只关闭 Playwright连接/自己创建的 page，不关闭用户 Chrome/context。
  - 现有旧文件不能绕过此次 identity；每次指定 `--browser` 的 login/check/upload 都先 refresh 导出。
- [ ] **6.3 接 CLI 与 biliup renew**
  - `sau bilibili login --account sau9225 --browser 9225` 表示“从该浏览器导出”，非 interactive QR。
  - `check` 指定 browser 时先导出，再 `biliup renew`，并同时校验 renew identity MID == CDP identity stable_id。
  - 未指定 browser时保留旧 biliup login/check兼容。
- [ ] **Task acceptance**
  - `rtk python -m unittest tests.test_bilibili_runtime tests.test_sau_bilibili_cli tests.test_sau_browser_cli` 全绿。
  - Live：导出到 ignored `cookies/bilibili_sau9225.json`，`check` exit 0，`identity` 返回 numeric stable_id；不得输出文件内容。
  - `git status --short --ignored` 确认 cookie 文件 ignored；`git diff` 不含 secret。

### Task 7: 择优整合 Douyin/Bilibili 上游行为

**Purpose:** 在不破坏 fork CDP/排期/身份闸门的前提下完成用户选定上游功能。
**Prerequisites:** Task 2、6。
**Risk level:** reversible mutation。

- [ ] **7.1 Bilibili cover**
  - 若当前 `BilibiliVideoUploadRequest.thumbnail_file`→`--cover` 与 `945bf8e` 等价，保留当前代码，只确保 parser/dispatch/test 完整；不要制造无意义 diff。
- [ ] **7.2 Douyin SMS**
  - 采用最终有效行为：检测短信验证码弹窗；有交互终端时允许一次安全输入；无人值守真实流程若弹出验证码，严禁等待用户或猜码，阻止该平台提交并保留其他平台进度。
  - 不恢复被 revert 的多余浏览器启动参数；CDP 路径优先现有 9225。
- [ ] **7.3 declaration/cover/collection**
  - `declaration` 显式选择并保持旧位置参数兼容；CLI 默认行为必须与当前用户已认可值一致，测试锁定。
  - landscape/portrait cover 按 UI要求分别设置；可选 collection 不存在时记录并跳过，不能阻断主发布；选择了存在 collection则校验选中值。
  - 复用当前 helper，根因修在共享路径，不复制 selector块。
- [ ] **Task acceptance**
  - `rtk python -m unittest tests.test_sau_douyin_cli tests.test_sau_bilibili_cli` 全绿。
  - 对 Task 2 矩阵每个 adopted行为都有测试；revert/merge wrapper 无重复代码。
  - Raw diff review: `RTK_DISABLED=1 git diff -- "sau_cli.py" "uploader/douyin_uploader/main.py" "uploader/bilibili_uploader/runtime.py"`。

### Task 8: 全量自动化回归与安全检查

**Purpose:** 在真实外部副作用前把本地错误清零。
**Prerequisites:** Task 3–7。
**Risk level:** safe/reversible。

- [ ] **8.1 focused suites**
  - Run: `rtk python -m unittest tests.test_sau_browser_cli tests.test_sau_douyin_cli tests.test_sau_bilibili_cli tests.test_bilibili_runtime tests.test_youtube_schedule tests.test_youtube_duration`。
- [ ] **8.2 full suite**
  - Run: `rtk python -m unittest discover -s tests`；若失败或输出不完整 raw rerun `rtk proxy python -m unittest discover -s tests -v`。
- [ ] **8.3 static/scope/security**
  - `git diff --check`
  - `rtk rg -n "T[B]D|TO[D]O|FIX[M]E|print\(.*cookie|print\(.*token|Authorization" "sau_cli.py" "utils" "uploader" "tests"`
  - Raw `git diff` 检查所有改动；确认无 secret、无 skipped/disabled tests、无新增依赖。
  - 运行 `rtk codegraph sync` 仅在源代码已改变后；再 `rtk codegraph affected` 或等价支持命令检查影响。若 CLI flag不同先看 `codegraph --help`，不猜。
- [ ] **Task acceptance**
  - 所有测试 exit 0；没有新警告；changed paths只在 File Map和本计划；原始 6 个脏文件内容/mtime不由本任务改变。

### Task 9: 生成无版权测试素材并做无提交预演

**Purpose:** 用唯一、短小、可识别素材验证媒体、封面、账号、表单、排期输入，不产生额外公开作品。
**Prerequisites:** Task 8 全绿；当前时间早于 2026-08-29 20:00 Asia/Shanghai；三平台身份均有 stable_id。
**Risk level:** reversible local mutation；浏览器表单填写但不提交。

- [ ] **9.1 生成素材**
  - 目录 `/private/tmp/sau-e2e-20260829`；若已存在先检查是否是本计划同一 marker，禁止 `rm -rf`，只覆盖本文明确命名的生成文件。
  - Marker: `SAU-REAL-UPLOAD-TEST-20260829-2000`。
  - Narration 文本逐字：`This is an automated publishing test scheduled for August twenty-ninth, twenty twenty-six.`
  - 用 `/usr/bin/say` 生成 AIFF；ffmpeg 生成 12 秒 1080x1920、H.264 yuv420p、AAC、30fps 视频，画面持续包含 `SAU REAL UPLOAD TEST`、`DELETE AFTER TEST`、`2026-08-29` 和 marker。用 ffprobe断言 duration 11.5–12.5 秒、一个 video stream、一个 audio stream。
  - 生成：YouTube/Bilibili 1280x720 封面各一张；Douyin landscape 1280x960、portrait 960x1280；不同底色和平台标签，均含 marker。
  - 禁止下载音乐、视频、图片或使用有版权素材。
- [ ] **9.2 三平台身份快照**
  - 运行三次 identity，写脱敏 `identity-before.json`；浏览器名称/端口应为 `SAU-自媒体运营-9225`/9225；stable_id非空。
- [ ] **9.3 无提交预演**
  - YouTube 使用现有 `--no-submit`，上传视频/封面并走到 final page，验证标题、封面、账号，不点击最终按钮。
  - Douyin 若 Task 7 可以用最小改动安全支持 `--no-submit`，同样走到最终页；否则不要为了测试添加通用 dry-run框架，使用 uploader已有内部 submit seam的集成测试 + 真实页面只读 identity/上传入口可达检查。
  - Bilibili biliup 无安全 no-submit：只运行 converter、`renew`、命令构造测试、素材/cover文件检查；不得为了预演制造第二份投稿。
  - 关闭自动化新建的测试标签页可以做，但不得关闭 Chrome或用户原有标签页。
- [ ] **Task acceptance**
  - `/private/tmp/sau-e2e-20260829` 有 video、narration、4 covers、identity-before、ffprobe证据；均无 secret。
  - 没有平台新增已提交作品；如果无法可靠证明无提交，Task 10 前先后台按 marker去重。

### Task 10: 三平台各一次真实定时发布、读回与最终验收

**Purpose:** 证明真实用户结果；这是已授权外部副作用，也是最终验收门。
**Prerequisites:** Task 1–9 全部 complete；三平台身份与 9225 健康；时间仍早于排期；没有短信/扫码/验证码门；全量测试 fresh green。
**Risk level:** 用户已明确授权的外部写入。不得扩大到立即发布、重复发布或删除。

- [ ] **10.1 发布前去重与身份二次确认**
  - Browser Harness 每个平台必须：先 `new_tab(url)`/`goto_url(url)`，再 `print(page_info())`；若返回 `domain_skill_files`，立即读完所有 Markdown后才继续。
  - 在各创作后台搜索 marker；若已存在同排期作品，把它作为该平台结果并禁止再次提交。若存在不同排期/状态的同 marker，停止该平台避免重复，记录证据。
  - 再次运行 identity；与 Task 9 stable_id完全一致。任一不一致立即阻止该平台。
- [ ] **10.2 YouTube 一次提交**
  - CLI 参数：account=`sau9225`，browser=`SAU-自媒体运营-9225`，视频/YouTube cover，title=`SAU REAL UPLOAD TEST · DELETE AFTER TEST · 2026-08-29 · YOUTUBE`，desc含 marker，schedule=`2026-08-29 20:00`，timezone=`Asia/Shanghai`，visibility=`public`。
  - 最终点击前 uploader 内部必须完成 observed identity校验。命令成功后读取其 JSON，并在 Studio 内容页读回 video ID、账号 stable_id、标题、scheduled状态、当地排期、封面可见。
- [ ] **10.3 Bilibili 一次提交**
  - 先从同一 browser重新导出 `cookies/bilibili_sau9225.json` 并确认 MID不变；参数 account=`sau9225`，Bilibili cover，title=`SAU REAL UPLOAD TEST · DELETE AFTER TEST · 2026-08-29 · BILIBILI`，desc含 marker，tags=`SAU测试,自动化测试`，schedule=`2026-08-29 20:00`。
  - `tid` 必须从创作中心/现有账号允许的普通非敏感分区中读取一个有效值；优先选择与“知识/科技”对应且无需额外资质的现有选项。不要猜硬编码失效 ID；选择结果记录在 evidence。collection 不传，charging-pay 不启用。
  - biliup 成功后在稿件管理读回 aid/bvid（若审核中只有 aid也记录）、MID、标题、定时状态/时间、封面。
- [ ] **10.4 Douyin 一次提交**
  - 参数 account=`sau9225`，browser=`9225`，两张 Douyin cover，title=`SAU REAL UPLOAD TEST · DELETE AFTER TEST · 2026-08-29 · DOUYIN`，desc含 marker，schedule=`2026-08-29 20:00`，declaration=`无需添加自主声明`，不传 collection/product。
  - 最终点击前 observed identity必须一致；若短信验证码弹窗出现，本无人值守执行不能输入，严禁提交/重试。
  - 成功后在作品管理读回作品标识（平台能提供什么就记录什么）、stable_id、标题、scheduled状态、当地排期、横竖封面应用结果。
- [ ] **10.5 最终证据与完整验收**
  - 将脱敏结果写 `/private/tmp/sau-e2e-20260829/final-evidence.json`：每平台 `stable_id`、display_name、browser、port、title、marker、scheduled_at、status、work_id/url、cover_check、submitted_once；不得含 Cookie/Token。
  - fresh run全部 Test Matrix；raw完整 diff；列 changed files；确认无 secrets、placeholder、debug、禁用测试、生成垃圾、遗留自动化进程。
  - 不删除三个测试作品；用户已说明稍后自己删除。
  - 只有每平台 exactly one、排期一致、账号一致、cover通过、测试全绿才更新所有 Ledger 为 complete，再调用 live `update_goal(status="complete")`。
  - 若某平台因验证码/登录失效/Auto-review拒绝不能提交：不要伪造 complete；其他平台先做完且防重复，然后按 live Goal blocker规则保留准确证据。

## Test Matrix

| Layer | Requirement/risk | Exact command/procedure | Expected result |
| --- | --- | --- | --- |
| Baseline | 识别既有失败 | `rtk python -m unittest discover -s tests` | 记录测试数和全部结果。 |
| Unit | selector/identity/converter | focused unittest modules in Tasks 3–7 | 所有新增分支有确定性 fixture，exit 0。 |
| Regression | Douyin/Bili/YouTube 邻接功能 | Task 8 focused command | SMS、declaration、cover、collection、schedule、duration/CDP无回归。 |
| Full | 仓库整体 | `rtk python -m unittest discover -s tests` | exit 0；若失败 raw -v。 |
| Security | secrets/账号错误 | raw diff + secret scan + mismatch fixtures | diff/log/evidence无秘密；stable_id mismatch阻断。 |
| Integration | 9225 + identity + biliup renew | live identity、Bili export/check | name/port同 target；三 stable_id非空；renew成功。 |
| Media | 真实文件可上传 | ffprobe + image dimensions | 12s H.264/AAC 1080x1920；4 covers尺寸正确。 |
| E2E | 用户结果 | Task 10 | 三平台各且仅一条 2026-08-29 20:00 scheduled作品，正确账号/封面。 |

## Browser Harness Exact Rules

- 命令范式：`printf 'new_tab("URL")\nprint(page_info())\n' | env BH_DOMAIN_SKILLS=1 BU_NAME=sau-e2e BU_CDP_URL=http://127.0.0.1:9225 browser-harness`。
- 当前 CLI 不支持 `-c`；不得使用旧示例。
- `page_info()` 只要给出 `domain_skill_files`，必须在任何后续该站动作前逐个完整读取。
- 正式技能目录 `/Users/yelin/Developer/agent-tools/browser-harness/agent-workspace/domain-skills/`；只读回后台，不用浏览器去发现已有 API。
- 输出/截图前检查页面是否含手机号、邮箱、Cookie、Token、二维码；有则不保存原图，只记录结构化脱敏字段。

## Failure Recovery and Autonomous Continuation

1. 每次恢复先 `get_goal`，重读本文、Required Skills、Lessons、Ledger。
2. 查看 `git status --short`、raw relevant diff、9225 audit、`/private/tmp/sau-e2e-20260829` 和后台 marker 去重结果。
3. 从第一个未勾选且 precondition满足的步骤继续；已可能提交的平台必须先读回去重，绝不盲重跑上传命令。
4. 同一测试失败最多两次：第一次依据完整 traceback修根因；第二次仍失败切 raw并追 caller/callee。不得无新证据重复第三次。
5. 网络失败：本地测试继续；上游用已 fetch对象；平台读回一次重试，之后保留证据，不绕过。
6. CDP失败：只执行 audit/resolve；不自动 start/stop浏览器。冲突是真 blocker。
7. 登录/扫码/短信：没有无人值守 fallback，不请求熟睡用户、不猜验证码；阻止相应外部提交。
8. 外部命令返回超时：先后台按 marker查状态；存在则读回，不再提交；不存在且能证明未提交才允许一次重试。
9. 写文件中断：源代码用 `git diff`恢复判断；Bili cookie只保留原文件或完整新文件，temp不当成功；绝不 `git reset --hard`、`git checkout --`、`rm -rf`。

## Final Acceptance Gate

- [ ] Test Matrix每行 fresh执行并记录。
- [ ] Requirement Traceability每行都有 passing evidence。
- [ ] Raw完整 diff列出全部 changed files，范围只在 File Map与本计划。
- [ ] 原始用户脏文件仍完整，未创建 branch/worktree/commit/push。
- [ ] 没有 placeholder、debug print、skipped test、新依赖、secret或生成媒体进入 Git diff。
- [ ] 9225四锚点仍健康，个人浏览器/9223/9224未被操作。
- [ ] 三平台 identity stable_id完整且提交前后一致。
- [ ] 三平台后台各且仅一条 marker作品，均为 `2026-08-29 20:00 Asia/Shanghai`，封面正确。
- [ ] 三平台作品不删除；final-evidence脱敏且完整。
- [ ] 所有 Ledger complete后才调用 `update_goal(status="complete")`，汇报 tests、changed files、三平台 work IDs/URLs、排期与残余风险。

## Plan Self-Review

- 范围已锁定到 Bilibili/Douyin选定提交、三平台身份、9225和真实排期；没有扩展其他平台。
- 外部副作用只含用户已明确授权的三条定时作品，每平台 exactly once且有去重闸门。
- 人工扫码/验证码没有伪装成可自动步骤；出现时阻止平台提交。
- 复用现有 `cdp_url`、browser runtime、biliup、unittest和fleet manager；没有新依赖/数据库/账号账本。
- 所有关键失败都有安全 continuation，禁止破坏 Git、浏览器或用户作品。
