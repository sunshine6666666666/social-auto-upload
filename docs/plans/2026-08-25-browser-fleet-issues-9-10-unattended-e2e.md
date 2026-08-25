# 浏览器生命周期、Issue #9/#10 与真实发布无监督实施计划

> **Executor:** 低能力自主执行 agent。你没有此前对话上下文，必须从第一行读到最后一行，逐项更新 Progress Ledger。不得猜测、省略验收、另起架构或要求离开电脑的用户处理常规问题。

**Goal:** 在 `/Users/yelin/Developer/agent-tools/social-auto-upload` 当前 `main` 工作区及现有未提交改动之上，修正全局 `browser-fleet-manager` 的运行状态模型，使账本不再持久化在线状态或 PID；让 SAU 在收到已登记的浏览器名称、端口或本地 CDP URL 时按需启动对应 Chrome 且任务结束后保持运行；最小修复 GitHub Issue #9 和 #10；通过自动化测试后，使用 9225 当前实时核验出的抖音与 YouTube 登录账号，各创建且仅创建一条 2026-08-26/27 的真实定时测试投稿，并留下不含 Cookie/Token 的验收证据。

**Done when:** 本文九个任务全部完成；全局浏览器 Skill 不保存活动浏览器的 `running/stopped` 或 PID，机器重启和手动关浏览器不会产生假冲突；9225、9226 在全部关闭的前提下可由 SAU 输入自动启动且任务后仍在线；未登记端口不会被创建或接管；外部 CDP 会话结束不再调用会关闭长期 Chrome 的动作；YouTube 中文“预定”成功且失败路径返回草稿 ID/URL 和可恢复状态；抖音首次上传和重试对大于 50MB 的本地 CDP 文件均使用现有 `DOM.setFileInputFiles` helper；全局 Skill 测试、SAU 165 项基线及新增测试全部通过；抖音与 YouTube 真实投稿各只有一条、账号稳定 ID 与发布前扫描一致、排期正确；9225、9226 最终均为实时健康运行；README 与真实实现一致；无新增依赖、无秘密泄漏、无 commit/push/branch/PR/删除线上作品。

**Workspace root:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Repository root:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Plan file:** `/Users/yelin/Developer/agent-tools/social-auto-upload/docs/plans/2026-08-25-browser-fleet-issues-9-10-unattended-e2e.md`
**Target environment:** 本地开发环境；macOS Darwin 24.6.0 arm64；shell `zsh 5.9`；项目 `.venv/bin/python` 为 Python 3.11.15；系统 Python 3.14.6 只用于全局 Skill 测试；Patchright 1.58.2；标准库 `unittest`。
**Execution mode:** `unattended`
**Live permission contract:** 计划作者于 2026-08-25 Asia/Shanghai 核验：运行时为 `workspace-write`；仓库根、`/private/tmp` 和当前会话临时目录可写；`/Users/yelin/.codex/skills/browser-fleet-manager` 与 `/Users/yelin/Desktop/ManagedBrowsers` 位于仓库外，精确写入/启动 GUI Chrome 需要 `require_escalated` 并由 `auto_review` 审查；网络默认受限；当前暴露 `create_goal`、`get_goal`、`update_goal`，且 `get_goal({})` 返回无活动 Goal。Auto-review 不是权限扩张；若明确拒绝，不得绕过或重复同一动作。
**Architecture/approved approach:** 复用现有 `browser_fleet.py start`、`utils/browser_selector.py`、`BrowserSession`、本地 CDP 文件 helper 和平台 uploader，不创建第二套浏览器服务、守护进程、数据库或 Profile 模板。账本只保存长期身份锚点和退役事实，运行状态每次由进程、端口和 Profile 实时计算。SAU 可按需启动已登记浏览器，但从不在任务结束时停止浏览器。
**Tech stack:** Python、`argparse`、`asyncio`、Patchright/Playwright CDP、Chrome DevTools Protocol、标准库 `json/subprocess/pathlib/unittest`；不得新增第三方包。

## Required Skills

- `openai-docs`
  - SKILL.md: `/Users/yelin/.codex/skills/.system/openai-docs/SKILL.md`
  - Lessons: `none found`
  - Use for: 执行开始时刷新 Sandbox、Auto-review、审批与 Goal 官方合同。
- `writing-plans`
  - SKILL.md: `/Users/yelin/.codex/skills/writing-plans/SKILL.md`
  - Lessons: `/Users/yelin/.codex/skills/writing-plans/references/lessons.md`
  - Use for: Goal、无监督恢复、权限边界、Progress Ledger 和完成门。
- `ponytail:ponytail`
  - SKILL.md: `/Users/yelin/.codex/plugins/cache/devkeeper-ponytail-local/ponytail/4.8.4/skills/ponytail/SKILL.md`
  - Lessons: `none found`
  - Use for: 先复用现有 helper，禁止新框架、新依赖和无关重构。
- `browser-fleet-manager`
  - SKILL.md: `/Users/yelin/.codex/skills/browser-fleet-manager/SKILL.md`
  - Lessons: `/Users/yelin/.codex/skills/browser-fleet-manager/references/lessons.md`
  - Use for: 修改并验证全局受管浏览器生命周期；个人 Chrome 只识别不操作。
- `skill-creator-new`
  - SKILL.md: `/Users/yelin/.codex/skills/skill-creator-new/SKILL.md`
  - Lessons: `/Users/yelin/.codex/skills/skill-creator-new/references/lessons.md`
  - Use for: 修改现有 Skill 时保留触发边界、最少补充 eval 提示和目标 Skill lessons。

## Applicable Rules

- `/Users/yelin/Developer/agent-tools/social-auto-upload/AGENTS.md`：始终简体中文；路径双引号；普通命令先用 `rtk`，认证/安全/完整 diff 使用 raw；先读后写；仓库文件使用 `apply_patch`；不得擅自创建分支、worktree、commit、push；任何仓库行为变化必须同步 `README.md`。
- `/Users/yelin/.codex/skills/browser-fleet-manager/SKILL.md`：个人浏览器绝不启动、停止、迁移或删除；受管对象必须以名称、端口、Profile 三锚点核验；不读取 Cookie、Token、密码或验证码；不得直接手改真实 `registry.json`。
- PONYTAIL full：只修改根因所在的共享函数；现有 helper 足够时不得复制；不引入守护进程、状态服务、ORM、数据库、抽象工厂或新依赖。

## Scope

### In scope

- 全局浏览器账本移除活动实例的持久化在线状态和 PID；兼容读取现有旧账本并在下一次安全写入时清理旧字段。
- `audit`、`resolve`、`start`、`stop`、`update`、`retire`、`restore`、`delete` 改为依据实时进程和明确退役字段工作。
- SAU 的名称、数字端口、已登记本地 CDP URL三种输入在浏览器离线时复用全局 `start` 自动启动；未登记对象继续 fail closed。
- 任务结束后不停止任何受管浏览器；成功关闭本任务新页，失败/待交互只保留最后一个现场页，执行前页面不动。
- Issue #9：YouTube 中文预约最终按钮、草稿证据、可恢复失败状态、外部 Chrome 所有权保护和真实预约回读。
- Issue #10：抖音 >50MB 本地 CDP 首次上传与失败重试使用现有 `requires_local_cdp_file_input()` 和 `set_local_file_input_via_cdp()`。
- README、单元测试、CodeGraph 同步、真实 9225/9226 启动验证和两条真实定时投稿。
- 全局 Skill 的 `SKILL.md`、脚本、单元测试、`evals/evals.json` 与 `references/lessons.md`。

### Out of scope

- 新建、迁移、改名、换端口、退役或删除任何现有 Profile。
- 修改个人 Chrome、9223、9224；不得关闭个人浏览器。
- Browser Harness 作为 SAU 的运行依赖；不得通过 Browser Harness 代替 SAU 的账号识别或发布闭环。
- Bilibili、快手、小红书、视频号、百家号、TikTok 的新功能。
- 账号模糊匹配、账号账本、守护进程、登录态复制、Profile 模板、并行发布。
- 删除本次或历史线上作品；用户会在验收后自行删除。
- Git commit、push、branch、worktree、PR、Issue 状态修改、release、部署、全局包安装。
- Skill benchmark/eval viewer。现有确定性单元测试与 2 条新增触发提示足够；没有用户在线做人工盲评。

### Allowed side effects

- 修改 File Map 明确列出的仓库文件，保留所有无关用户改动。
- 精确修改 `/Users/yelin/.codex/skills/browser-fleet-manager` 下列出的 Skill 文件；通过脚本命令而非手改真实账本迁移旧字段。
- 启动已登记的 `SAU-自媒体运营-9225` 和 `SAU-自媒体运营-2号-9226`；启动后保持运行。
- 在 `/private/tmp/sau-issues-9-10-20260825` 写入权限 0600 的脱敏日志、JSON 回执和运行脚本。
- 用户已明确授权使用 9225 当前实时账号创建两条测试内容：一条抖音定时投稿，一条 YouTube Studio 原生预约。仅允许本文固定 task-id 各一次。
- 访问 GitHub Issue #9/#10 只读；不得关闭或编辑 Issue。

### Forbidden side effects

- 禁止立即发布；排期必须是本文允许的 2026-08-26 或 2026-08-27。
- 禁止在账号稳定 ID 为空、变化、多重命中或登录待交互时提交。
- 禁止因失败重新使用新 task-id 投稿；不确定结果只能读回，不能重传。
- 禁止停止、kill 或退出 9225/9226；即使它们由本次自动启动，也保持运行。
- 禁止打印、保存或提交 Cookie、Token、CSRF、验证码、Profile 数据库内容或浏览器原始命令行。
- 禁止 `git reset`、`git checkout --`、`git clean`、宽泛删除或覆盖脏工作树。

## Goal Contract

- 第一动作重新读取 `openai-docs`，并在 Progress Ledger 记录检索时间与以下官方页面：
  - `https://learn.chatgpt.com/docs/sandboxing`
  - `https://learn.chatgpt.com/docs/sandboxing/auto-review`
  - `https://learn.chatgpt.com/docs/agent-approvals-security`
  - `https://learn.chatgpt.com/use-cases/follow-goals`
- 检查执行器自己的 permission profile、writable roots、network、reviewer 和实际 Goal tool schemas。不得把字面 `/goal` 当成工具。
- 若 `create_goal` 存在且 `get_goal` 显示无活动 Goal，使用本计划顶部 **Goal** 原文调用 `create_goal({objective})`，不得设置 token budget。
- 恢复时调用 `get_goal`，重读本计划、Required Skills、Lessons、Progress Ledger、`git status --short` 和实时 browser audit；不得创建重复 Goal。
- 同一失败最多两次：第一次用 raw 完整输出定位根因；修复后再试一次。第二次同因失败时切换到本文已定义的安全 fallback；禁止无新证据循环。
- 单测失败、网络暂时失败、真实发布未完成或预算接近上限都不是 complete。只有九项任务和最终验收全部通过，才按实时 schema 调用 `update_goal(status="complete")`。
- `blocked` 仅按执行器实时 tool instruction 使用。权限被 Auto-review 明确拒绝时不得绕过；先完成所有仍可安全完成的任务并保留证据。

## Permission Feasibility

| 资源/副作用 | 当前合同 | 无监督路径 | 失败处理 |
| --- | --- | --- | --- |
| 仓库源文件、测试、README、计划 | workspace 可写 | `apply_patch` | 读回、`git diff --check`；不得换工作树。 |
| 全局 browser Skill | 仓库外，需精确升级 | `require_escalated` + Auto-review；用户已明确授权修改该 Skill | 明确拒绝后不绕过；保留仓库修改和拒绝证据，按 Goal 规则处理。 |
| Desktop ManagedBrowsers | 仓库外，GUI/进程 | 只通过 Skill 脚本 `audit/start/resolve`；已有精确命令前缀授权 | 不直接改账本/Profile；冲突即停止浏览器动作。 |
| `/private/tmp/sau-issues-9-10-20260825` | writable root | 可写脱敏证据 | 不清空整个 `/private/tmp`。 |
| localhost 9225/9226 | 本地网络/浏览器 | 通过已登记 CDP；必要时精确升级 | 不尝试远程 CDP，不接管未知端口。 |
| 抖音/YouTube 外部写入 | 用户已授权各一条定时投稿 | 固定 task-id、账号双检、只运行一次 | 结果不确定时不重试；保留最后现场页和本地 receipt。 |
| GitHub | 网络受限，只读非关键 | Issue 内容已记录；无需再次联网即可开发 | 不创建/编辑/关闭 Issue。 |
| Git metadata | 只读 | status/diff/log | 不 commit/reset/switch。 |

## Current-State Evidence

- 当前 checkout：`/Users/yelin/Developer/agent-tools/social-auto-upload`，分支 `main`；origin 为 `sunshine6666666666/social-auto-upload`，upstream 为 `dreammis/social-auto-upload`。
- 工作树很脏：`README.md`、`sau_cli.py`、三平台 uploader/runtime 和多份测试已有用户/前序修改；`utils/account_identity.py`、`utils/browser_selector.py`、`utils/direct_cdp.py` 等为未跟踪文件。全部视为需要保留，禁止 reset/clean/覆盖。
- CodeGraph 1.4.1 于 2026-08-25 00:48:19 索引：101 files、1909 nodes、4889 edges、无 pending changes。
- 作者于 2026-08-25 运行 `.venv/bin/python -m unittest discover -s tests`：165 tests，全部 `OK`，耗时约 11.8 秒；`git diff --check` 通过。
- 作者运行全局 Skill 测试：4 tests，全部 `OK`。现有测试错误地把 `status=running` 写进账本后才能 resolve，正是本次需替换的旧合同。
- 实时 audit 已证明账本漂移：`SAU-自媒体运营-2号-9226` 实际无进程，但账本仍为 `running`，被标记 `registered_running_but_not_live`；这是持久化在线状态必须删除的直接证据。
- 当前全局脚本 `make_entry()` 写 `status=stopped`；`start/stop` 写 `status` 与 `pid`；`audit/resolve` 信任这些字段；SAU `browser_selector.py` 对 stopped 直接拒绝，不会自动启动。
- 本次启动门复核于 2026-08-25：已读取 `openai-docs`、writing-plans、ponytail、browser-fleet-manager、skill-creator-new 及 lessons；官方页面已刷新：`https://learn.chatgpt.com/docs/sandboxing`、`https://learn.chatgpt.com/docs/sandboxing/auto-review`、`https://learn.chatgpt.com/docs/agent-approvals-security`、`https://learn.chatgpt.com/use-cases/follow-goals`。当前 Goal active；permission profile 为 managed/workspace-write，workspace writable root 为本仓库，Auto-review reviewer 为 `auto_review`。
- 2026-08-25 Task 7 后实时 audit：9225 `running/ok`，9226 `stopped/ok`，无 conflict；9225 未关闭，故未运行 accounts scan、runner 或任何真实外部写入。
- `BrowserSession.close()` 当前最终总会调用 `browser.close()`；Issue #9 的真实现场显示这可能关闭外部长期托管 Chrome，不能继续依赖“只断开连接”的注释假设。
- YouTube 当前未提交代码已有中文 `预定` selector、`#done-button` 内层 button 点击、预约读回和任务页清理雏形；应审计补缺，不得重写 uploader。
- 抖音 `upload()` 的主视频 input 和 `handle_upload_error()` 重试仍直接调用 `set_input_files()`；没有复用现有大文件 CDP helper。
- 最终真实验收于 2026-08-25 完成：从 9225/9226 均 `stopped/ok` 开始，SAU accounts scan 自动启动两者；9225 抖音/YouTube stable ID 分别为 `202851389`、`UC04E0U6ZAZoD5y3lcVNUNHQ`，9226 为允许的 `interaction_required`。
- 抖音真实结果：`issue10-douyin-20260826-2000-v1` receipt `complete`，`status=success`，`scheduled_at=2026-08-26T20:00:00`，大文件日志确认走本机 CDP 路径。
- YouTube 真实结果：`issue9-youtube-20260827-2000-v1` receipt `complete`，`status=success`，`videoId=P8XDAONHbDQ`，`publishUrl` 存在，`visibility=scheduled`，`scheduledAt=2026-08-27T20:00:00+08:00`，`timezone=Asia/Shanghai`。
- 真实发布后两次独立 audit 及最终 audit 均显示 9225、9226 `running/ok`，Profile/端口未变，无 `registered_running_but_not_live`；未删除线上作品，未 commit/push/branch。
- GitHub 仅有两个 OPEN Issue：
  - #9 `https://github.com/sunshine6666666666/social-auto-upload/issues/9`
  - #10 `https://github.com/sunshine6666666666/social-auto-upload/issues/10`
- 已选真实素材：
  - YouTube：`/Users/yelin/Documents/english-media-materials/hyperframes/render-workspace/videoFile-1787365813916-871203278/output.mp4`，106171885 bytes，313.386667 秒，H.264/AAC，1920×1080。
  - 抖音：`/Users/yelin/Documents/english-media-materials/hyperframes/render-workspace/videoFile-1787618151999-352662935/output.mp4`，104875180 bytes，312.768 秒，H.264/AAC，1920×1080。
- 用户会在执行前关闭受管浏览器；计划必须从全部离线状态验证 SAU 自动启动。个人 Chrome 即使仍运行也不属于关闭或启动范围。

## Requirement Traceability

| Requirement | Source | Implemented by | Verified by |
| --- | --- | --- | --- |
| 账本不记录在线状态/PID | 用户确认 | Task 2 | Skill schema/audit/unit tests、真实关机态 audit |
| SAU 输入离线名称/端口/CDP URL时自动启动 | 用户确认 | Task 3 | selector tests、9225/9226 live scan |
| 自动启动后任务结束不关闭浏览器 | 用户确认 | Tasks 3–4 | lifecycle tests、最终 audit |
| 未登记端口不创建 Profile | 安全边界 | Task 3 | fail-closed tests、目录前后不变 |
| Issue #10 大文件首次与重试 | Issue #10 | Task 5 | helper mock tests、104875180-byte真实抖音投稿 |
| Issue #9 中文预约 | Issue #9 | Task 6 | selector/unit tests、中文 Studio 真实预约 |
| Issue #9 草稿可恢复证据且不重传 | Issue #9 | Task 6 | failure simulation、固定 task-id/receipt |
| 外部 CDP 不关闭 Chrome | Issue #9 + 用户确认 | Task 4 | `browser.close` negative tests、9225/9226存活 |
| Skill 与 README 同步 | 用户要求 + AGENTS | Tasks 2、7 | 文件读回、README检查 |
| 两条真实定时投稿 | 用户授权 | Task 8 | 结构化返回、稳定 ID、时间、task receipt、最终 audit |

## Progress Ledger

| Task | Status | Completion evidence |
| --- | --- | --- |
| Task 1：启动门与基线 | complete | 已读取必需 Skills/lessons，刷新四个官方 URL；保留脏工作树，完成 Goal/权限/实时 audit 基线。 |
| Task 2：全局 Skill 运行状态根治 | complete | registry 已安全迁移为不持久化 `status/pid`；Skill 测试 10 tests OK；audit 改为实时派生状态。 |
| Task 3：SAU 按需启动 | complete | `browser_selector` 覆盖名称/端口/本地 CDP 的 audit→start→resolve；未登记、冲突、远程 CDP fail closed；SAU 相关测试通过。 |
| Task 4：外部 CDP 生命周期 | complete | 外部 CDP 不调用 `browser.close()`，只清理 owned pages/context；本地 launch 仍关闭 browser；CDP 测试 19 tests OK。 |
| Task 5：Issue #10 | complete | 抖音大文件首次/重试复用现有 CDP file-input helper；新增分支测试通过。 |
| Task 6：Issue #9 | complete | YouTube 中文“预定”、原生最终按钮、disabled 检查、草稿解析和 recoverable receipt/exit 1 已实现并测试。 |
| Task 7：README 与全量回归 | complete | README 已同步；SAU 全量 184 tests OK，Skill 10 tests OK，compileall、diff-check、CodeGraph sync/affected 通过。 |
| Task 8：真实发布 | complete | `/private/tmp/sau-issues-9-10-20260825/run_real_e2e.py --submit` 唯一执行并返回 0；抖音、YouTube 各一条成功定时投稿；固定 task receipt 均 `complete`；两次发布后 audit 与最终 audit 均 9225/9226 `running/ok`。 |
| Task 9：最终验收 | complete | fresh SAU 184 tests OK、Skill 10 tests OK、compileall/diff-check/CodeGraph 通过；结果 JSON、素材 size/duration、receipt、最终 audit 和变更/秘密/依赖扫描均已核对。 |

## File Map

| Action | Absolute path | Responsibility | Consumed by |
| --- | --- | --- | --- |
| Modify | `/Users/yelin/.codex/skills/browser-fleet-manager/scripts/browser_fleet.py` | 持久身份/退役合同、实时状态、启动停止 | Skill CLI、SAU selector |
| Modify | `/Users/yelin/.codex/skills/browser-fleet-manager/tests/test_browser_fleet.py` | 旧账本迁移、实时状态、启动/停止合同 | Skill regression |
| Modify | `/Users/yelin/.codex/skills/browser-fleet-manager/SKILL.md` | 明确不持久化在线状态、按需启动语义 | 后续所有浏览器管理调用 |
| Modify | `/Users/yelin/.codex/skills/browser-fleet-manager/evals/evals.json` | 增加断电漂移与 SAU 自动启动触发提示 | Skill 触发安全网 |
| Append | `/Users/yelin/.codex/skills/browser-fleet-manager/references/lessons.md` | 记录运行状态不得作为事实持久化 | 后续 Skill 维护 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/utils/browser_selector.py` | 已登记离线浏览器按需 start 后 resolve | CLI 单/多浏览器输入 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/utils/browser_runtime.py` | 外部 CDP 所有权、页面清理 | 三平台 uploader |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/uploader/douyin_uploader/main.py` | 主视频首次/重试复用本地 CDP 文件 helper | Issue #10 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/uploader/youtube_uploader/main.py` | 中文最终按钮、草稿引用、可恢复结果 | Issue #9 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/sau_cli.py` | YouTube 非成功结构化结果返回非零 | Issue #9 CLI |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_browser_runtime_cdp.py` | 外部/自有浏览器 close 合同 | Task 4 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_sau_browser_cli.py` | name/port/CDP 自动启动与 fail closed | Task 3 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_sau_douyin_cli.py` | 大文件首次与重试 | Task 5 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_youtube_schedule.py` | 中文按钮、草稿证据、recoverable failure | Task 6 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/README.md` | Fork 当前能力、限制、真实命令 | 用户和后续 agent |
| Create runtime only | `/private/tmp/sau-issues-9-10-20260825/run_real_e2e.py` | 固定 task-id、账号双检、两条投稿、脱敏证据 | Task 8；不纳入仓库 |

## Interface Contracts

### 全局账本与实时状态

- 活动 entry 只允许长期字段：`name`、`port`、`instance_dir`、`profile_dir`、`created_at`、`updated_at`。不得保存 `pid`、`running` 或 `stopped`。
- 退役由 `retired_at`、`retired_until`、`original_port` 和 `port=null` 表达；不要新增另一套状态枚举。
- 增加 `is_retired(entry: dict) -> bool`，唯一判定为 `bool(entry.get("retired_at"))`。
- `audit` 输出中的 `status` 是临时结果：退役为 `retired`；活动且 `process_for` 命中为 `running`；否则为 `stopped`。正常关闭不是 conflict。
- conflict 只包括 Profile 缺失、实时进程与名称/端口/Profile 锚点冲突、端口被未知进程占用或 CDP 不健康；不得包含“账本曾写 running 但现在没进程”。
- `resolve` 不读取持久 status；直接验证未退役、实时 `process_for` 和 `cdp_ready`。
- `start` 已运行时幂等返回实时 `running`；未运行时启动并三锚点复核；不得写 PID/status 回账本。
- `stop` 只停止实时匹配进程并复核端口释放；不得写 PID/status。停止后 Profile 与端口绑定不变。
- 旧账本兼容：加载后允许读取旧 `status/pid`；任何 `write=True` 保存前删除活动 entry 的 `status` 与 `pid`。旧 `status=retired` 且有 `retired_at` 仍按退役读取。

### SAU 自动启动

- 保留 `BrowserTarget(name, port, cdp_url)` 与所有 CLI flag。
- 只对 audit 中唯一匹配且 `health=ok` 的登记对象自动启动。
- `status=stopped` 时调用现有 `_fleet_json("start", "--name", name)`，随后必须调用 `_fleet_json("resolve", "--name", name)` 复核。
- `status=running` 直接 resolve；`health=conflict`、多重端口匹配、未登记名称/端口、远程 CDP 一律拒绝。
- 数字 selector、名称 selector、指向已登记端口的 localhost CDP URL行为一致；不得创建 Profile、分配端口或调用 `create`。
- 9225/9226 被自动启动后不自动 stop。

### BrowserSession 所有权

- `connected_over_cdp=True` 时，`close()` 只关闭本任务拥有的 page 和 `should_close_context=True` 的专用 context；不得调用 `browser.close()`。
- `connected_over_cdp=False` 且由 SAU 自己 launch 时，仍调用 `browser.close()`，避免本地临时进程泄漏。
- 成功关闭全部新任务页；失败关闭除最后一个以外的新任务页；执行前 `initial_pages` 永不关闭。
- 关闭页面/context 的失败转 warning，但不得掩盖原始上传异常。

### 抖音大文件输入

在 `DouYinVideo` 内只增加一个共享方法，首次与重试都调用它：

```python
async def set_video_file_input(self, page: Page, selector: str) -> None:
    if requires_local_cdp_file_input(self.cdp_url, Path(self.file_path).stat().st_size):
        douyin_logger.info(_msg("📁", "大文件通过本机 CDP 路径交给 Chrome"))
        await set_local_file_input_via_cdp(page, selector, self.file_path)
        return
    await page.locator(selector).set_input_files(self.file_path)
```

- 从 `utils.browser_runtime` 导入现有两个 helper；不得复制 CDP 协议代码。
- 首次 selector 固定 `div[class^='container'] input`；重试 selector 固定 `div.progress-div [class^='upload-btn-input']`。
- 小文件或非 CDP 保持 Patchright `set_input_files()`。
- 封面不在 Issue #10 范围，不改封面上传路径。

### YouTube 可恢复失败

- 保留现有预约读回函数与 `SCHEDULE_BUTTON_SELECTOR`；不要重写上传流程。
- 最终按钮优先 `#done-button button`，兼容 host 点击，并允许稳定中文文本 `预定` 作为回退；只点击一个可见 enabled 按钮。
- 新增 `extract_youtube_draft_reference(html: str) -> dict[str, str]`：仅解析 11 字符视频 ID，支持 `video-id`、`videoId`、`youtu.be/`、`watch?v=`；返回有值时包含 `videoId` 和 `publishUrl`，无值返回空 dict。
- 找不到最终预约按钮时不再只抛字符串。返回：

```json
{
  "status": "interaction_required",
  "platform": "youtube",
  "reason": "final_schedule_button_missing",
  "recoverable": true,
  "submitted": false,
  "videoId": "仅在可提取时存在",
  "publishUrl": "仅在可提取时存在",
  "browser_name": "受管浏览器名",
  "cdp_port": 9225,
  "stable_id": "发布前核验的频道ID"
}
```

- `sau_cli.py` 打印该 JSON 并返回 exit code 1；固定 task-id receipt 标为 failed/uncertain，后续同 task-id 不重传。
- 成功时必须回读 `videoId`、`publishUrl`、`visibility=scheduled`、`scheduledAt`、`timezone`；任何缺失不是成功。

### 一次性 E2E runner 完整内容

Task 8 必须把下面代码原样写入 `/private/tmp/sau-issues-9-10-20260825/run_real_e2e.py`；只允许因已验证的 CLI JSON 字段差异做最小修正，并把修正原因写入 Ledger：

```python
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


REPO = Path("/Users/yelin/Developer/agent-tools/social-auto-upload")
PYTHON = REPO / ".venv/bin/python"
CLI = REPO / "sau_cli.py"
FLEET = Path("/Users/yelin/.codex/skills/browser-fleet-manager/scripts/browser_fleet.py")
EVIDENCE = Path("/private/tmp/sau-issues-9-10-20260825")
STATE = Path(os.environ.get("SAU_TASK_STATE_DIR", "/private/tmp/social-auto-upload-task-state"))
DOUYIN_VIDEO = Path("/Users/yelin/Documents/english-media-materials/hyperframes/render-workspace/videoFile-1787618151999-352662935/output.mp4")
YOUTUBE_VIDEO = Path("/Users/yelin/Documents/english-media-materials/hyperframes/render-workspace/videoFile-1787365813916-871203278/output.mp4")
ZONE = ZoneInfo("Asia/Shanghai")


def sanitize(text: str) -> str:
    return re.sub(
        r"(?i)(cookie|token|csrf|authorization)(\s*[:=]\s*)([^\s,;]+)",
        r"\1\2[REDACTED]",
        text,
    )


def save(name: str, text: str) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / name
    path.write_text(sanitize(text), encoding="utf-8")
    path.chmod(0o600)


def run(name: str, command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )
    save(f"{name}.stdout.log", result.stdout)
    save(f"{name}.stderr.log", result.stderr)
    save(f"{name}.command.json", json.dumps(command, ensure_ascii=False))
    if check and result.returncode != 0:
        raise RuntimeError(f"{name} failed with exit code {result.returncode}; do not retry upload")
    return result


def parse_last_json(text: str) -> dict:
    stripped = text.strip()
    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    for line in reversed(stripped.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError("command output did not contain a JSON object")


def probe(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(f"video missing: {path}")
    size = path.stat().st_size
    if size <= 50 * 1024 * 1024:
        raise RuntimeError(f"video is not larger than 50MiB: {path}")
    result = run(
        f"ffprobe-{path.parent.name}",
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration,size",
            "-of", "json", str(path),
        ],
    )
    data = json.loads(result.stdout)
    duration = float(data["format"]["duration"])
    if duration >= 15 * 60:
        raise RuntimeError(f"video duration is not safely below 15 minutes: {duration}")
    return {"path": str(path), "size": size, "duration": duration}


def audit(name: str) -> dict:
    result = run(name, [sys.executable, str(FLEET), "audit"])
    return json.loads(result.stdout)


def registered(audit_data: dict, port: int) -> dict:
    matches = [item for item in audit_data.get("registered", []) if item.get("port") == port]
    if len(matches) != 1:
        raise RuntimeError(f"port {port} is not uniquely registered")
    return matches[0]


def scan_accounts() -> dict:
    result = run(
        "accounts-scan",
        [
            str(PYTHON), str(CLI), "accounts", "scan",
            "--browsers", "9225,9226",
            "--platforms", "douyin,youtube,bilibili",
        ],
    )
    return parse_last_json(result.stdout)


def stable_id(scan: dict, platform: str) -> str:
    matches = []
    for item in scan.get("items", []):
        if item.get("platform") != platform or item.get("cdp_port") != 9225:
            continue
        if item.get("status") != "logged_in":
            continue
        identity = item.get("identity") or {}
        value = identity.get("stable_id")
        if isinstance(value, str) and value.strip():
            matches.append(value.strip())
    if len(matches) != 1:
        raise RuntimeError(f"9225 must expose exactly one logged-in {platform} stable ID")
    return matches[0]


def receipt(task_id: str) -> dict | None:
    path = STATE / f"{task_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    save(f"receipt-{task_id}.json", json.dumps(data, ensure_ascii=False, indent=2))
    return data


def allowed_schedules() -> tuple[str, str, str]:
    now = datetime.now(ZONE)
    douyin_26 = datetime(2026, 8, 26, 20, 0, tzinfo=ZONE)
    douyin_27 = datetime(2026, 8, 27, 20, 0, tzinfo=ZONE)
    youtube = datetime(2026, 8, 27, 20, 0, tzinfo=ZONE)
    if now + timedelta(hours=3) <= douyin_26:
        douyin = douyin_26
        douyin_task = "issue10-douyin-20260826-2000-v1"
    elif now + timedelta(hours=3) <= douyin_27:
        douyin = douyin_27
        douyin_task = "issue10-douyin-20260827-2000-v1"
    else:
        raise RuntimeError("both authorized Douyin schedules are too close or already past")
    if now >= youtube:
        raise RuntimeError("authorized YouTube schedule is already past")
    return douyin.strftime("%Y-%m-%d %H:%M"), douyin_task, youtube.strftime("%Y-%m-%d %H:%M")


def upload_once(name: str, task_id: str, command: list[str]) -> dict:
    previous = receipt(task_id)
    if previous is not None:
        if previous.get("state") == "complete":
            return {"task_id": task_id, "reused": True, "receipt": previous}
        raise RuntimeError(f"task {task_id} already has state {previous.get('state')}; do not retry")
    result = run(name, command, check=False)
    payload = parse_last_json(result.stdout) if result.stdout.strip() else {}
    save(f"{name}.result.json", json.dumps(payload, ensure_ascii=False, indent=2))
    receipt(task_id)
    if result.returncode != 0:
        raise RuntimeError(f"{name} returned {result.returncode}; evidence saved; do not retry")
    if payload.get("status") != "success":
        raise RuntimeError(f"{name} did not return success; do not retry")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()
    media = {"douyin": probe(DOUYIN_VIDEO), "youtube": probe(YOUTUBE_VIDEO)}
    before = audit("audit-before")
    for port in (9225, 9226):
        item = registered(before, port)
        if item.get("health") != "ok" or item.get("status") != "stopped":
            raise RuntimeError(f"precondition failed: port {port} must be stopped and healthy before auto-start test")
    scan = scan_accounts()
    douyin_id = stable_id(scan, "douyin")
    youtube_id = stable_id(scan, "youtube")
    after_scan = audit("audit-after-scan")
    for port in (9225, 9226):
        item = registered(after_scan, port)
        if item.get("health") != "ok" or item.get("status") != "running":
            raise RuntimeError(f"SAU did not leave port {port} running and healthy")
    douyin_schedule, douyin_task, youtube_schedule = allowed_schedules()
    preflight = {
        "media": media,
        "douyin_stable_id": douyin_id,
        "youtube_stable_id": youtube_id,
        "douyin_schedule": douyin_schedule,
        "douyin_task_id": douyin_task,
        "youtube_schedule": youtube_schedule,
        "youtube_task_id": "issue9-youtube-20260827-2000-v1",
    }
    save("preflight.json", json.dumps(preflight, ensure_ascii=False, indent=2))
    if not args.submit:
        print(json.dumps({"status": "preflight_ok", **preflight}, ensure_ascii=False, sort_keys=True))
        return 0
    douyin = upload_once(
        "douyin-real",
        douyin_task,
        [
            str(PYTHON), str(CLI), "douyin", "upload-video",
            "--account", "sau-e2e", "--file", str(DOUYIN_VIDEO),
            "--title", f"SAU-I10大文件测试-验收后删除-{douyin_schedule[:10].replace('-', '')}",
            "--desc", "自动化真实验收：Issue #10，素材超过50MB，请验收后删除。",
            "--tags", "SAU测试,自动化测试", "--declaration", "内容由AI生成",
            "--schedule", douyin_schedule, "--browser", "9225",
            "--target-account", douyin_id, "--task-id", douyin_task,
        ],
    )
    audit("audit-after-douyin")
    youtube_task = "issue9-youtube-20260827-2000-v1"
    youtube = upload_once(
        "youtube-real",
        youtube_task,
        [
            str(PYTHON), str(CLI), "youtube", "upload-video",
            "--account", "sau-e2e", "--file", str(YOUTUBE_VIDEO),
            "--title", "SAU Issue 9 E2E - Delete After Check - 20260827",
            "--desc", "Automated verification for Issue #9. Delete after acceptance.",
            "--tags", "SAU test,automation test", "--visibility", "public",
            "--schedule", youtube_schedule, "--timezone", "Asia/Shanghai",
            "--browser", "9225", "--target-account", youtube_id,
            "--task-id", youtube_task,
        ],
    )
    final_audit = audit("audit-final")
    for port in (9225, 9226):
        item = registered(final_audit, port)
        if item.get("health") != "ok" or item.get("status") != "running":
            raise RuntimeError(f"port {port} was not left running and healthy")
    summary = {"status": "success", "douyin": douyin, "youtube": youtube}
    save("summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Tasks

### Task 1：启动门、Goal 与不可破坏基线

**Purpose:** 让弱模型在任何修改前了解权限、脏树和外部副作用边界。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** safe/read-only

- [ ] **1.1 读取合同并创建或恢复 Goal**
  - 依次读取所有 Required Skills 及 lessons；刷新四个 OpenAI 官方 URL；检查实时 Goal schemas。
  - 无活动 Goal 时调用 `create_goal`，objective 必须与顶部 Goal 完全一致；已有 Goal 时只 resume 当前工作。
  - Expected: Progress Ledger 记录检索时间、URL、permission profile、Goal ID/状态；不得修改 Codex 配置。
  - If it fails: 官方网页暂时不可访问时可使用本计划记录的 URL 与实时工具 schema继续，但必须记录“官方刷新失败”；Goal tool 不存在时继续任务并只用 Ledger，不执行 slash command。

- [ ] **1.2 保存只读基线**
  - Run:
    - `rtk git status --short`
    - `RTK_DISABLED=1 git diff --check`
    - `rtk codegraph status . --json`
    - `rtk .venv/bin/python -m unittest discover -s tests`
    - `rtk python3 -m unittest discover -s "/Users/yelin/.codex/skills/browser-fleet-manager/tests"`
    - `RTK_DISABLED=1 python3 "/Users/yelin/.codex/skills/browser-fleet-manager/scripts/browser_fleet.py" audit`
  - Expected: SAU 至少 165 tests OK；Skill 至少 4 tests OK；diff check 通过。浏览器可全部 stopped；stopped 本身不是失败。
  - If it fails: 同一测试用 raw 输出重跑一次；确认是否为基线已有失败。不得在原因未知时继续真实发布。
  - Scope guard: 保存 `git status --short` 和 audit 的脱敏副本到 `/private/tmp/sau-issues-9-10-20260825`，权限设 0600；禁止保存原始进程命令行。

### Task 2：根治全局 Skill 的持久在线状态

**Purpose:** 消除关机/手动关闭后 registry 假冲突，并保持退役安全边界。
**Prerequisites:** Task 1 complete。
**Risk level:** reversible mutation；仓库外精确写入需 Auto-review。

- [ ] **2.1 先写失败测试**
  - Modify: `/Users/yelin/.codex/skills/browser-fleet-manager/tests/test_browser_fleet.py`。
  - 新增至少以下测试：
    - `test_active_registry_does_not_persist_runtime_status_or_pid`
    - `test_audit_derives_running_and_stopped_from_live_processes`
    - `test_resolve_ignores_stale_legacy_running_status_when_process_missing`
    - `test_start_and_stop_do_not_persist_runtime_state`
    - `test_retired_entry_remains_durable`
  - Tests 必须使用临时 `BROWSER_FLEET_ROOT` 和 mock `chrome_processes/port_open/cdp_ready/subprocess.Popen/os.kill`，不得依赖真实 ps 或启动 Chrome。
  - Run: `rtk python3 -m unittest discover -s "/Users/yelin/.codex/skills/browser-fleet-manager/tests"`
  - Expected before implementation: 新测试失败且原因精确指向 status/pid 持久化；旧测试不因 fixture 错误失败。

- [ ] **2.2 最小修改 browser_fleet.py**
  - 按“全局账本与实时状态”合同修改现有函数，不新增模块或依赖。
  - 将所有 `entry.get("status") == "retired"` 改为统一 `is_retired(entry)`。
  - `make_entry` 不写 status；`start/stop` 不写 status/pid；`audit/resolve` 实时推导；保存旧账本时清理活动 entry 的 status/pid。
  - `retire/restore/delete` 继续保留 30 天保护和精确名称确认；不得削弱删除门。
  - Run: Skill 全量测试。
  - Pass: 新旧测试全部 OK；临时 registry 的活动 entry 无 status/pid；retired 流程仍通过。

- [ ] **2.3 更新 Skill 文档、eval 与 lessons**
  - `SKILL.md` 明确：登记表不是在线事实；每次 status 从实时进程/端口/Profile推导；正常关机或手动关闭显示 stopped，不是 conflict；`start` 幂等且启动后保持运行。
  - `evals/evals.json` 保留已有 3 条，新增两条：
    - “电脑重启后 9226 显示 registry running，帮我核对，别把正常离线当冲突。”
    - “我把 SAU 浏览器全关了，现在用 9225 发布；应启动已登记浏览器，但任务后别关。”
  - 向 `references/lessons.md` 追加一条：在线状态属于瞬时事实，不能作为长期 registry 锚点；信号为关机后 `registered_running_but_not_live`；修复为实时推导。
  - 不运行 eval viewer；这是无监督确定性维护，单元测试已覆盖行为。

- [ ] **2.4 安全迁移真实账本**
  - 禁止手改 `/Users/yelin/Desktop/ManagedBrowsers/registry.json`。
  - 使用更新后的既有 `init` 命令触发一次幂等 schema normalization；`locked_registry(write=True)` 保存前清理活动 entry 的 legacy `status/pid`。不要增加新的迁移子命令。
  - 迁移不得启动/停止浏览器、移动 Profile 或改端口。
  - Verify: 连续两次 audit；9225/9226 离线时均为 `status=stopped, health=ok, problems=[]`；registry 活动 entry 不含 status/pid。
  - Rollback: 修改前保存 registry 的权限 0600 备份到 `/private/tmp/sau-issues-9-10-20260825/registry.before.json`；只在迁移写入损坏且验证失败时用精确文件恢复。不得删除原 Profile。

### Task 3：让 SAU 自动启动已登记的离线浏览器

**Purpose:** 输入 9225/9226、名称或本地 CDP URL即可完成启动与核验，不创建未知浏览器。
**Prerequisites:** Task 2 complete。
**Risk level:** reversible code mutation；测试安全，live 启动留到 Task 8。

- [ ] **3.1 扩展现有 selector 测试**
  - Modify: `tests/test_sau_browser_cli.py`。
  - Mock `_fleet_json`，覆盖：离线名称调用 start→resolve；离线数字端口调用 start→resolve；已登记 localhost CDP URL调用 start→resolve；running 不调用 start；conflict/未登记/多重匹配拒绝；start 失败不创建 Profile；9225,9226 数组分别启动且顺序保持。
  - 断言调用只出现 `audit/start/resolve`，不得出现 `create/adopt/update`。

- [ ] **3.2 修改 browser_selector.py**
  - 只增加一个私有 helper 统一三种输入的“唯一登记→必要时 start→resolve”。
  - 保留 `_target_from_resolve()` 三锚点检查与 localhost 限制。
  - `_fleet_json` timeout 若 15 秒不足，只允许调整到 30 秒；不要增加后台守护或轮询服务。
  - Run: `rtk .venv/bin/python -m unittest tests.test_sau_browser_cli tests.test_sau_batch tests.test_account_identity`
  - Pass: 全部 OK，未登记 selector fail closed。

### Task 4：修正外部 CDP 浏览器所有权与页面回收

**Purpose:** SAU 只能清理自己的页面，绝不能关闭长期 Chrome。
**Prerequisites:** Task 3 complete。
**Risk level:** reversible code mutation。

- [ ] **4.1 修正生命周期测试**
  - Modify: `tests/test_browser_runtime_cdp.py`。
  - 将当前 `test_success_close_closes_only_new_pages` 对 `browser.close()` 的正断言改为 CDP 场景 `assert_not_awaited()`。
  - 新增 local launch 场景，断言 `connected_over_cdp=False` 时 `browser.close()` 恰好一次。
  - 覆盖 CDP 专用 context：context close 一次，browser close 零次；共享 context：两者均不 close；页面 ownership 仍按成功/失败合同执行。

- [ ] **4.2 最小修改 BrowserSession.close**
  - 保留现有页面关闭循环与 warning。
  - 仅在 `not self.connected_over_cdp` 时调用 `self.browser.close()`。
  - CDP 连接由 `async_playwright` 生命周期自然断开，不显式发送关闭整个 browser 的动作。
  - Run: `rtk .venv/bin/python -m unittest tests.test_browser_runtime_cdp tests.test_direct_cdp`
  - Pass: 全部 OK；不存在 CDP `browser.close()` 正断言。

### Task 5：完成 Issue #10 抖音 >50MB 本地 CDP 上传

**Purpose:** 复用已由 YouTube 验证的 CDP helper，一处修复首次与重试。
**Prerequisites:** Task 4 complete。
**Risk level:** reversible code mutation。

- [ ] **5.1 添加最小失败测试**
  - Modify: `tests/test_sau_douyin_cli.py`。
  - 新增四个测试：CDP + 50MB以上首次调用 CDP helper；CDP + 50MB以上重试调用 helper；小文件调用 locator；非 CDP 大文件调用 locator。
  - 用临时稀疏文件或 mock `Path.stat().st_size`，不得复制 100MB 素材进仓库。

- [ ] **5.2 实现共享 set_video_file_input**
  - 严格使用 Interface Contracts 给出的完整方法。
  - `upload()` 与 `handle_upload_error()` 只改为调用该方法；不要改封面、标题、声明、合集、排期或发布按钮逻辑。
  - Run: `rtk .venv/bin/python -m unittest tests.test_sau_douyin_cli tests.test_youtube_schedule`
  - Pass: 新增四种分支全过；现有 YouTube helper 测试不回归。

### Task 6：完成 Issue #9 YouTube 中文预约和可恢复失败

**Purpose:** 成功路径确定性回读；失败路径保留草稿证据、现场页和长期浏览器。
**Prerequisites:** Task 4 complete。
**Risk level:** reversible code mutation。

- [ ] **6.1 添加 parser/按钮/失败结果测试**
  - Modify: `tests/test_youtube_schedule.py` 和必要的 CLI 测试。
  - 覆盖 `预定`、`Schedule`、`#done-button button`；disabled 按钮不点击；草稿 ID 从四种来源解析；频道 UC ID 不得误当 11 字符视频 ID；缺按钮返回 `interaction_required/recoverable=true/reason=final_schedule_button_missing`；CLI 打印 JSON 且 exit 1；成功仍返回原结构。

- [ ] **6.2 补齐 uploader 与 CLI**
  - 复用当前 `_click_if_present`、`_click_required_final_button` 和预约读回，按 Interface Contracts 增加草稿 parser 与结构化失败结果。
  - 找不到按钮时不得重新导航到 upload URL，不得重新选择文件，不得把 `_upload_succeeded` 设为 true；`finally` 应留下最后一个新任务页。
  - 有 `--task-id` 时，非成功结果必须写 terminal receipt，使同一 task-id 后续返回既有状态而不再上传。
  - Run: `rtk .venv/bin/python -m unittest tests.test_youtube_schedule tests.test_browser_runtime_cdp tests.test_sau_batch tests.test_sau_browser_cli`
  - Pass: 全部 OK；失败结果包含可提取 draft 证据，外部 CDP browser close 为零。

### Task 7：README、CodeGraph 与全量回归

**Purpose:** 在真实账号写入前证明本地代码稳定且文档可信。
**Prerequisites:** Tasks 2–6 complete。
**Risk level:** safe/reversible mutation。

- [ ] **7.1 更新 README**
  - 说明：浏览器名称/端口/localhost CDP URL会自动启动已登记离线实例；任务结束不关闭浏览器；账本状态实时推导；未知端口拒绝；Issue #9 可恢复结果；抖音 >50MB 本地 CDP 支持；成功/失败页面清理语义。
  - 文档不得声称未真实验证的平台或“绝不发错账号”；必须写明真实发布仍需 `--target-account`。

- [ ] **7.2 执行静态与全量回归**
  - Run:
    - `RTK_DISABLED=1 git diff --check`
    - `rtk .venv/bin/python -m compileall sau_cli.py utils uploader tests`
    - `rtk .venv/bin/python -m unittest discover -s tests`
    - `rtk python3 -m unittest discover -s "/Users/yelin/.codex/skills/browser-fleet-manager/tests"`
    - `rtk codegraph sync .`
    - `rtk codegraph affected --path . --json`
  - Pass: SAU 不少于 165 tests 且全部 OK；Skill 不少于 9 tests 且全部 OK；compile/diff check OK；CodeGraph 无 pending changes。
  - If fail: raw 重跑失败 suite，修根因；不得进入 Task 8。

### Task 8：从全部离线状态做 9225/9226 与两条真实发布验收

**Purpose:** 证明自动启动、账号防错、Issue #9/#10 和不关闭浏览器在真实环境成立。
**Prerequisites:** Task 7 complete；当前时间仍早于对应排期；用户已关闭受管浏览器。
**Risk level:** 已明确授权的外部写入。仅本文两条；不是额外人类门。

- [ ] **8.1 生成一次性 E2E runner**
  - Create: `/private/tmp/sau-issues-9-10-20260825/run_real_e2e.py`，权限 0600；使用上方“完整内容”，不得自由发挥另一套 runner。
  - runner 必须：验证两个素材的 exact path、size > 50MiB、ffprobe duration < 15min；验证固定 task receipt 不存在或处于终态；运行 accounts scan；从 JSON 精确选择 9225 的 douyin/youtube `logged_in` 且 stable_id 非空项；把该 stable_id 原样作为 `--target-account`；顺序执行抖音后 YouTube；保存 stdout/stderr/returncode；对 secrets 字样与长 Cookie-like 字符串做拒绝扫描；每个命令前后 audit 9225/9226。
  - 固定 task-id：
    - `issue10-douyin-20260826-2000-v1`
    - `issue9-youtube-20260827-2000-v1`
  - 固定命令语义：
    - 抖音：素材 `videoFile-1787618151999-352662935/output.mp4`；标题 `SAU-I10大文件测试-验收后删除-20260826`；描述 `自动化真实验收：Issue #10，素材超过50MB，请验收后删除。`；tags `SAU测试,自动化测试`；声明 `内容由AI生成`；browser `9225`；schedule `2026-08-26 20:00`。
    - YouTube：素材 `videoFile-1787365813916-871203278/output.mp4`；标题 `SAU Issue 9 E2E - Delete After Check - 20260827`；描述 `Automated verification for Issue #9. Delete after acceptance.`；tags `SAU test,automation test`；visibility public；browser `9225`；schedule `2026-08-27 20:00`；timezone `Asia/Shanghai`。
  - 若执行开始时距离抖音 2026-08-26 20:00 少于平台允许的最小提前量，则抖音唯一允许 fallback 为 `2026-08-27 20:00`，并把 task-id 改为 `issue10-douyin-20260827-2000-v1`；不得立即发布。YouTube 固定 2026-08-27 20:00，不得改到 8月28日以后。
  - runner 默认只做 preflight；必须显式 `--submit` 才运行两条已授权外部写入。

- [ ] **8.2 从关闭状态验证自动启动**
  - First audit：9225、9226 必须都是 stopped/health ok；如果仍有任一 running，不得自行 stop。先继续完成不依赖真实启动的本地检查，在自然检查点最多复核三次；仍未关闭则保留证据，不能把 live 自动启动验收标为完成。
  - 此步骤只运行 Skill `audit`，不要提前运行 accounts scan，也不要提前运行 runner 的无 `--submit` 模式；否则浏览器会先被启动，破坏 Task 8.3 的“单次从 stopped 开始”证据。
  - Expected: 保存一份同时证明 9225、9226 为 stopped/health ok 的 `audit-before`；下一步 runner 将在同一进程内完成 accounts scan、自动启动、账号读取与真实发布。
  - Safety: 任一 conflict、9225账号提取 error、stable_id 空或多重命中，禁止投稿；保留现场页并继续本地诊断，不扫码、不读验证码。

- [ ] **8.3 运行一次真实 E2E**
  - Run: `RTK_DISABLED=1 .venv/bin/python "/private/tmp/sau-issues-9-10-20260825/run_real_e2e.py" --submit`
  - runner 内部 accounts scan 是唯一的 live 自动启动动作。它必须证明 9225、9226 从 stopped 变为 running/healthy；9225 至少 douyin/youtube logged_in 且 stable_id 非空；9226 可 interaction_required，不是失败。
  - 抖音成功标准：returncode 0；结果 `status=success, platform=douyin, cdp_port=9225, submitted=true`；`stable_id` 必须严格等于 Step 8.2 扫描返回的抖音稳定 ID；`scheduled_at` 必须严格等于 Step 8.1 选择的允许时间；日志明确走 CDP local-file path；没有 50MB transfer 错误；管理页 URL存在。
  - YouTube 成功标准：returncode 0；结果 `status=success, platform=youtube, cdp_port=9225, videoId=11字符, publishUrl, visibility=scheduled, scheduledAt=2026-08-27T20:00:00+08:00, timezone=Asia/Shanghai`；`stable_id` 必须严格等于 Step 8.2 扫描返回的 YouTube 稳定 ID；中文 Studio 最终提交完成。
  - 两条任务任何一个结果 uncertain/interaction_required：不得改 task-id、不得重跑上传；读取 receipt 和保留的最后现场页，记录草稿 ID/URL。若平台已有相同 task-id success receipt，直接视为幂等重放并验证既有结果。

- [ ] **8.4 验证浏览器未被关闭**
  - Run 两次 audit，中间间隔用正常操作时间而非固定长 sleep。
  - Pass: 9225、9226 均 running/health ok；Profile 和端口未变；无 `registered_running_but_not_live`；执行前页面未关闭；成功任务新页已清理。
  - 禁止 stop/kill 作为清理。浏览器保持运行交给用户后续使用。

### Task 9：最终验收与 Goal completion

**Purpose:** 只有代码、Skill、文档和真实证据全部成立时结束。
**Prerequisites:** Tasks 1–8 complete。
**Risk level:** safe/read-only。

- [ ] **9.1 重跑全部 Test Matrix**
  - 使用 fresh 输出，不复用 Task 7 缓存；记录测试数量、耗时和 exact commands。
  - 检查两个固定 task receipt、真实返回 JSON、最终 browser audit 和素材 stat/ffprobe。

- [ ] **9.2 完整 diff 与秘密扫描**
  - Run:
    - `RTK_DISABLED=1 git status --short`
    - `RTK_DISABLED=1 git diff --stat`
    - `RTK_DISABLED=1 git diff --check`
    - 对 File Map 逐文件 raw diff；全局 Skill 文件用独立 diff/读回，不通过 Git 猜测。
    - `rtk rg -n "FIXME|temporary-debug|cookie|token|csrf|authorization" README.md sau_cli.py utils uploader tests docs/plans`
  - 检查新增匹配是否只是已有字段名/安全文档；任何真实 secret 立即从证据和 diff 移除，不输出其值。

- [ ] **9.3 验收 Requirement Traceability**
  - 每一行必须有实现文件和 passing evidence；无实现、无真实证据或浏览器被关闭，均不得 complete。
  - 不关闭 GitHub Issue；只报告“本地已满足，Issue 仍由用户决定是否关闭”。

- [ ] **9.4 完成 Goal**
  - 更新所有 Ledger 行为 complete，并记录 changed files、测试、两个平台结果、浏览器最终状态、残余风险。
  - 仅此时调用 `update_goal(status="complete")`。
  - 最终回复必须明确：没有 commit/push；两条线上测试内容不会自动删除；9225/9226 保持运行。

## Test Matrix

| Layer | Requirement/risk | Exact command/procedure | Expected result | Failure evidence |
| --- | --- | --- | --- | --- |
| Baseline | 保留现有能力 | `rtk .venv/bin/python -m unittest discover -s tests` | 至少 165 tests OK | raw failing suite |
| Skill unit | 账本实时状态 | `rtk python3 -m unittest discover -s "/Users/yelin/.codex/skills/browser-fleet-manager/tests"` | 至少 9 tests OK | 临时 registry JSON + traceback |
| Selector unit | 离线按需启动/fail closed | `rtk .venv/bin/python -m unittest tests.test_sau_browser_cli tests.test_sau_batch` | name/port/CDP/array全过，无 create | mock call list |
| Runtime unit | 外部 Chrome 所有权 | `rtk .venv/bin/python -m unittest tests.test_browser_runtime_cdp tests.test_direct_cdp` | CDP browser.close=0；local=1 | AsyncMock assertions |
| Douyin unit | >50MB 首次与重试 | `rtk .venv/bin/python -m unittest tests.test_sau_douyin_cli` | 四分支全过 | helper/locator call assertions |
| YouTube unit | 中文按钮和草稿证据 | `rtk .venv/bin/python -m unittest tests.test_youtube_schedule` | 成功/失败结构均通过 | parsed JSON/selector assertions |
| Static | 语法、diff、图索引 | compileall、diff check、CodeGraph sync/affected | 全绿，无 pending | raw output |
| Live integration | 全关后自动启动 | accounts scan 9225,9226 + audit | 两端口 running/healthy，9225身份可读 | scan JSON + audit JSON |
| Live E2E | Issue #10 | 固定抖音 task-id + 104875180-byte素材 | 定时投稿成功，无50MB错误 | stdout/stderr/receipt/现场页 |
| Live E2E | Issue #9 | 固定 YouTube task-id + 中文 Studio | videoId/URL/scheduledAt回读 | structured recoverable result/receipt |
| Final safety | 不关闭浏览器/不重复/无秘密 | final audit + receipts + secret scan | 9225/9226在线，各一条，证据脱敏 | audit/status/receipt |

## Failure Recovery and Autonomous Continuation

1. 每次恢复先 `get_goal`，重读计划、Required Skills、lessons 和 Ledger，再看 `git status --short`、全局 Skill 文件、browser audit、task receipts。
2. 以第一个未完成且前置条件满足的 checkbox 继续；不要重做已通过的外部投稿。
3. 若真实命令被打断，先检查固定 task receipt：`complete/skipped_duplicate` 只读验证；`started/uncertain` 禁止重传；`failed` 也不得更换 task-id自动重试。
4. 若浏览器离线，调用 SAU selector 触发 start；若三锚点 conflict，不得 stop/kill/create，保留 audit 证据并继续纯本地任务。
5. 若抖音短信验证、YouTube 登录或账号 ID 不可读，返回 interaction_required并保留最后现场页；不读取验证码、不扫码、不换账号投稿。
6. 若 YouTube 最终按钮失败但已有 draft ID/URL，记录 recoverable result，不重新上传。只能修 selector 后在同一现场页继续；若不能确定是否提交，保持 uncertain。
7. 若排期已过去，不得立即发布或改到 8月28日以后；完成所有本地任务，按实时 Goal 规则处理剩余真实验收。
8. Auto-review 明确拒绝全局 Skill 写入或 GUI 启动时，不得通过 shell 包装、临时复制或替代路径绕过；保存拒绝证据，继续所有权限内步骤。
9. 不使用 `git reset/checkout/clean` 恢复。仓库编辑出错时用 `apply_patch` 反向恢复本次小块，保留用户原改动。

## Final Acceptance Checklist

- [ ] 活动 registry entry 无 status/pid；退役保护仍有效。
- [ ] 关闭浏览器后 audit 为 stopped/healthy，不是假 conflict。
- [ ] SAU 通过 9225、9226、名称、本地 CDP URL可按需启动；未知端口拒绝。
- [ ] 自动启动后任务结束浏览器保持运行。
- [ ] CDP session 不调用 browser.close；页面清理合同通过。
- [ ] Issue #10 首次和重试都复用现有 CDP file helper。
- [ ] Issue #9 中文预约成功；失败有 draft/recoverable 证据且不重传。
- [ ] SAU tests ≥165 全绿；Skill tests ≥9 全绿；compile/diff/CodeGraph全绿。
- [ ] README 与实际命令、限制一致。
- [ ] 抖音和 YouTube 各且仅一条固定 task-id真实定时测试。
- [ ] 两次最终 audit 均显示 9225、9226 running/healthy。
- [ ] 无秘密、无新增依赖、无 commit/push/branch/PR/Issue修改、无线上删除。
