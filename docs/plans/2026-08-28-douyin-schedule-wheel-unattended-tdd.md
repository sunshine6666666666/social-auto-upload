# 抖音普通视频定时滚轮健壮化：Go/Auto-review 无监督 TDD 实施计划

> **Executor:** 低能力自治执行模型；它没有本次对话历史。必须从头逐字读取本计划，严格按复选框执行，不得猜测、省略、扩展范围或向离席用户询问常规选择。

**Goal:** 在现有 SAU 抖音普通视频上传链路中，使用测试驱动开发修复定时滚轮的间歇性偏移，并通过三次连续真实 `no-submit` 验收证明稳定性；全过程真实投稿次数为 0。
**Done when:** 所有新增行为均有先 RED 后 GREEN 的证据；213 个基线测试及新增测试全部通过；9225 浏览器上同一短视频以三个不同未来时间连续完成三次 `no-submit`，每次结构化回执均为 `status=prepared`、`submitted=false`、`account_match=true`、`scheduled_at` 与目标完全一致；README 已同步；没有点击发布、没有提交、推送或生产晋级。
**Workspace root:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Repository root:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Plan file:** `/Users/yelin/Developer/agent-tools/social-auto-upload/docs/plans/2026-08-28-douyin-schedule-wheel-unattended-tdd.md`
**Target environment:** 本机开发环境，macOS Darwin arm64，shell `/bin/zsh`，Python 3.11.15，Patchright 1.58.2，受管 Chrome CDP 9225。
**Execution mode:** `unattended`；用户将离开电脑，执行模型不得要求用户确认常规实现、文件写入、测试、网络访问或已授权的 `no-submit` 浏览器操作。
**Live permission contract:** 计划作者运行时为 unrestricted/full-access、approval policy `never`、网络可用；预期执行者运行时为 workspace-write + Auto-review。执行者必须以自己的实时工具和权限为准。用户已明确授权：修改本仓库范围内文件、运行本地测试、只读访问指定外部视频、连接 9225、访问抖音并执行三次 `no-submit`。未授权：真实发布、删除用户数据、提交、推送、PR、生产晋级或回滚。
**Architecture/approved approach:** 只修现有普通视频链路，不新增框架或依赖。复用 `DouYinBaseUploader.set_schedule_time_douyin()`、`_spin_wheel_to()`、现有 CLI、账号双重核验和 `submit=False` 发布前闸门。滚轮采用“每步回读、按最新值动态纠偏、目标稳定复读”；完整日期时间最终回读失败时在同一表单内做有界重试，仍不一致则 fail closed。
**Tech stack:** Python `>=3.10,<3.13`；标准库 `unittest`/`unittest.mock`；Patchright `1.58.2`；项目虚拟环境 `/Users/yelin/Developer/agent-tools/social-auto-upload/.venv`；无新增依赖。

## Required Skills

- `openai-docs`
  - SKILL.md: `/Users/yelin/.codex/skills/.system/openai-docs/SKILL.md`
  - Lessons: `none found`
  - Use for: 执行开始时刷新官方 Auto-review、权限和 Goal 指南。
- `ponytail:ponytail`（full）
  - SKILL.md: `/Users/yelin/.codex/plugins/cache/devkeeper-ponytail-local/ponytail/4.8.4/skills/ponytail/SKILL.md`
  - Lessons: `none found`
  - Use for: 强制 KISS/YAGNI；只做最小根因修复，不创建新抽象或依赖。
- `test-driven-development`
  - SKILL.md: `/Users/yelin/.codex/skills/test-driven-development/SKILL.md`
  - Lessons: `none found`
  - Use for: 严格 RED → GREEN → REFACTOR；生产代码前必须看见正确失败。
- `systematic-debugging`
  - SKILL.md: `/Users/yelin/.codex/skills/systematic-debugging/SKILL.md`
  - Lessons: `/Users/yelin/.codex/skills/systematic-debugging/references/lessons.md`
  - Use for: 基于已有三次现场偏移与聚焦测试定位根因；禁止随机改魔法数字。
- `browser-fleet-manager`
  - SKILL.md: `/Users/yelin/.codex/skills/browser-fleet-manager/SKILL.md`
  - Lessons: `/Users/yelin/.codex/skills/browser-fleet-manager/references/lessons.md`
  - Use for: 每次真实验收前核验 9225 的名称、端口、Profile、进程和 CDP 健康状态。
- `production-toolchain-manager`
  - SKILL.md: `/Users/yelin/.codex/skills/production-toolchain-manager/SKILL.md`
  - Lessons: `/Users/yelin/.codex/skills/production-toolchain-manager/references/lessons.md`
  - Use for: 只读确认 SAU 生产 v1 保持不变；本计划禁止 promote/rollback。

## Applicable Rules

- `/Users/yelin/Developer/agent-tools/social-auto-upload/AGENTS.md`
  - 普通命令优先 `rtk`，完整 diff/安全判断使用 `RTK_DISABLED=1` 或 `rtk proxy`。
  - Python 测试使用标准库 `unittest`，浏览器/文件系统/网络边界必须 mock。
  - 所有行为变更必须同步 `/Users/yelin/Developer/agent-tools/social-auto-upload/README.md`。
  - 不得提交 `conf.py`、Cookie、数据库、视频、日志、二维码或其他凭据。
  - 用户未要求时不得 commit、push、创建分支或 worktree。
- `/Users/yelin/Developer/agent-tools/social-auto-upload/CLAUDE.md`
  - 新抖音 CLI 工作使用 `sau douyin ...`，不得退回 legacy examples。
- 本计划中的用户授权
  - 仅普通视频；图文不纳入真实验收。
  - 三次连续不同未来时间 `no-submit`；任一次失败整体不通过。
  - 用户离席；不要询问权限或常规选择。

## Official OpenAI Contract Evidence

检索日期：2026-08-28（Asia/Shanghai）。执行者必须在开始时重新读取这些官方页面并在 Progress Ledger 记录新的检索时间：

- [Permissions](https://learn.chatgpt.com/docs/permission-modes)：sandbox 决定可访问边界，approval/reviewer 决定越界请求交给用户还是 Auto-review；Auto-review 不扩大 sandbox。
- [Long-running work](https://learn.chatgpt.com/docs/long-running-work)：Goal 需要明确 outcome、constraints、verification；Goal 不扩大权限；自动审查只评估符合条件的请求。
- [Follow a goal](https://learn.chatgpt.com/use-cases/follow-goals)：长任务需要单一目标、可验证停止条件、检查点和进度记录。
- [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model)：明确授权边界和成功标准可减少不必要暂停；安全本地编辑和测试无需重复询问。

执行时刷新：2026-08-28 17:15:40 CST；当前运行时为 unrestricted/full-access、approval policy never、网络可用、仓库文件系统 unrestricted；已调用实时 `get_goal`，目标状态为 active。

公开文档展示 `/goal` 为人类交互入口；本执行环境若暴露 `create_goal/get_goal/update_goal` 工具，必须使用工具的实时 schema，禁止把 `/goal` 文本当作工具调用。

## Scope

- In scope:
  - 抖音普通视频 CLI 支持同时传 `--schedule` 与 `--no-submit`。
  - `_spin_wheel_to()` 对滚动无效、跨格、过冲、动画漂移和短暂命中进行闭环纠偏。
  - `set_schedule_time_douyin()` 对最终输入框回读做最多三次完整设置尝试。
  - `no-submit` 结构化回执包含已严格验证的 `scheduled_at`。
  - 单元测试、全量回归、README、三次真实 `no-submit`。
- Out of scope:
  - 抖音图文真实验收或图文新功能。
  - 付费视频逻辑变化、Peach、Cron、Browser Harness 源码、其他平台。
  - 新依赖、新模块、新重试框架、配置项、数据库或后台服务。
  - commit、push、PR、merge、生产 promote/rollback、真实发布。
- Allowed side effects:
  - 修改本计划 File Map 列出的仓库文件。
  - 运行测试；读取 `/Users/yelin/Documents/english-media-materials/hyperframes/render-workspace/news-video-local-preview/output.mp4`。
  - 连接受管浏览器 9225；打开抖音发布页面、上传测试视频、填写普通视频表单、设置预约时间；在发布按钮前返回。
  - Auto-review 对上述精确范围的网络/外部路径请求进行自动审查。
- Human-gated side effects:
  - 本计划没有必须完成的人类 gate。
  - 真实发布、git commit/push、生产晋级即使技术上可用也没有授权，必须跳过，不能向离席用户申请。

## Permission Feasibility

| 操作 | 路径/目的地 | 授权 | 预期执行权限 | 无监督处理 |
| --- | --- | --- | --- | --- |
| 仓库读写 | `/Users/yelin/Developer/agent-tools/social-auto-upload` | 已授权 | workspace-write | 直接执行；保留无关改动 |
| Skill 读取 | `/Users/yelin/.codex/...` | 只读已授权 | 通常可读 | 读取失败时用已安装 Skill 解析能力定位；不得猜路径 |
| 视频读取 | `/Users/yelin/Documents/english-media-materials/hyperframes/render-workspace/news-video-local-preview/output.mp4` | 已明确授权 | 可能需要 Auto-review | 只请求该文件的 read；不复制进仓库 |
| 本机 CDP | `http://127.0.0.1:9225` | 已明确授权 | 可能需要 Auto-review | 只请求 9225；禁止 9223/9224/9226 |
| 抖音网络 | `https://creator.douyin.com` | 三次 no-submit 已授权 | 可能需要 Auto-review | 精确说明“no-submit、绝不点击发布”；不得询问用户 |
| `/tmp` | 脱敏临时诊断 | 已授权 | 可写 | 不保存 HTML、Cookie、Token、账号 ID、截图 |
| Git 外部写入 | GitHub | 未授权 | 不适用 | 不执行 |
| 生产版本 | production-toolchain | 未授权 | 不适用 | 只读 status/verify；不 promote/rollback |

## Goal Contract

- 启动后先读取 `openai-docs` 并刷新上面的官方页面；记录时间、URL、执行时 sandbox、approval reviewer、网络与可写根。
- 检查执行时是否暴露 Goal 工具，并读取它们的实时说明/schema。
- 若 `get_goal` 存在，先调用。若没有未完成 Goal 且 `create_goal` 存在，调用：
  - `objective`: `用严格 TDD 修复 SAU 抖音普通视频定时滚轮间歇性偏移，完成全量测试和 9225 上三次连续 no-submit 验收，真实投稿次数为 0；不提交、不推送、不晋级生产。`
  - 不设置 `token_budget`，因为用户没有指定预算。
- 若已有同一目标，继续；不得创建重复 Goal。
- 每次恢复：重新读取本计划、Required Skills/lessons、Progress Ledger、`git status --short --branch` 和当前 diff，从第一个未完成且前置条件满足的步骤继续。
- 只有所有任务和 Final Acceptance Gate 全部通过才能 `update_goal(status="complete")`。
- `blocked` 只能按执行时工具说明使用。登录态失效、短信验证、9225 身份冲突或 Auto-review 永久拒绝是可能的外部阻塞；不得向离席用户反复提问或绕过安全边界。

## Current-State Evidence

计划编写时（2026-08-28 16:44 Asia/Shanghai）已验证：

- 仓库 `/Users/yelin/Developer/agent-tools/social-auto-upload`，分支 `main`，HEAD `b29951f971295ee0e11bd12586e8f54a090aa1eb`，与 `origin/main` 对齐，除本计划文件外原始工作树干净。
- CodeGraph 1.4.1 索引健康，无 pending changes；`_spin_wheel_to()` 的生产调用者只有 `set_schedule_time_douyin()`，后者被视频和图文共用。真实范围只覆盖普通视频，但单元回归不得破坏共享调用。
- 现生产 SAU 为 v1，release `b29951f97129-0432f18e-622efad4`；本计划禁止改变它。
- Browser Harness 当前生产 v2；本计划无需修改或调用其源码。
- Browser Fleet 中 `SAU-自媒体运营-9225` 正在运行、health `ok`、CDP `http://127.0.0.1:9225`。
- 测试视频 `/Users/yelin/Documents/english-media-materials/hyperframes/render-workspace/news-video-local-preview/output.mp4`：30.016 秒、5,397,258 字节。
- 聚焦定时测试：3 tests，PASS。
- 当前 CLI 测试确认 `--schedule` 与 `--no-submit` 被互斥组拒绝。
- 全量基线：213 tests in 13.155s，PASS。
- 现场故障：目标小时 13，三次最终回读分别为 16、14、15；均在发布按钮前停止，真实投稿 0。
- 上游 `dreammis/main` 仍使用键盘输入时间且 Issue #142 未解决；无可直接复用的滚轮修复。当前滚轮实现来自本 Fork 提交 `ff19397`。

## Root-Cause Statement

根因候选已经有足够证据进入 TDD：当前 `_spin_wheel_to()` 在第一次读到目标值时立即返回，且滚动方向只按初始值计算一次。Semi ScrollList 的选中值会在 wheel 动画/吸附期间短暂变化；事件也可能不生效或跨多格。于是 helper 可能把“瞬时 13”当成完成，随后控件最终吸附到 14/15/16。最终输入框回读虽然安全地阻止发布，但当前只尝试一次，无法从可恢复的控件漂移中自动恢复。

禁止把根因简化为“36px 不对”并随意调成另一个常量。36px 保持不变，修复闭环和稳定判定。

现场补充根因：验收目标跨到下一个月份时，日期面板仍停留在当前月，旧 selector 直接点日号未切换月份，导致输入框保留当天日期；当天时间轮的最小值又阻止目标小时向下滚动。修复同一现有定时函数中的月份导航后，才可对目标日期进行滚轮收敛。

## Requirement Traceability

| Requirement | Source | Implemented by | Verified by |
| --- | --- | --- | --- |
| 仅普通视频 | 用户选择 1 | Tasks 2–5 | E2E 仅调用 `douyin upload-video`；scope diff |
| CLI 可安全 schedule + no-submit | no-submit 验收 | Task 2 | parser RED/GREEN + help +真实命令 |
| 处理过冲/漂移/吞事件 | 用户要求健壮 | Task 3 | 过冲、稳定复读、动画窗口三组 RED/GREEN + 现有 forward/backward |
| 最终回读失败可恢复且有界 | 现场三次错时 | Task 4 | 一次失败后成功、三次失败后抛错 |
| 任何错时都不发布 | 安全边界 | Tasks 4–5 | no-submit 单元测试不查询发布按钮；E2E receipts |
| 三次连续成功 | 用户确认 | Task 5 | 三个不同未来时间 receipts |
| README 同步 | AGENTS.md | Task 5 | diff + 文档内容检查 |
| 不晋级生产 | 用户范围 | Final Gate | production status 仍为 SAU v1 |

## Progress Ledger

| Task | Status | Completion evidence |
| --- | --- | --- |
| Task 1 — Startup and baseline | complete | 2026-08-28 17:14–17:15 CST：`codegraph status` healthy（1.4.1，pending 0）；browser audit 确认 `SAU-自媒体运营-9225` port 9225 running/ok 且无冲突；production status 确认 SAU v1 `b29951f97129-0432f18e-622efad4` 未变；素材 `30.016s/5397258B`；基线 `DouyinScheduleTests` 3 PASS、互斥拒绝测试 1 PASS、全量 213 PASS；test fake 重构后 `DouyinScheduleTests` 3 PASS（exit 0），生产代码未改。 |
| Task 2 — CLI schedule + no-submit | complete | 2026-08-28 17:21–17:23 CST：parser 接受测试 RED/GREEN；`PaidVideoCliTests` 9 PASS，help 显示独立 `--schedule`/`--no-submit`，其他平台 parser 未改。 |
| Task 3 — Wheel convergence | complete | 2026-08-28 17:16–17:32 CST：过冲 RED 指向固定方向并最终到 93；动态方向 GREEN 3 PASS；瞬时命中 RED 观测 `[36]`；稳定复读 GREEN；真实动画窗口测试在 250ms/500ms 下 RED，1s GREEN；最终 `DouyinScheduleTests` 7 PASS，保留 36px/80 guard。 |
| Task 4 — Final readback retry and receipt | complete | 2026-08-28 17:18–17:50 CST：回读恢复 RED/GREEN；三次不匹配 RED/GREEN（6 次 wheel helper）；scheduled receipt RED 观测 `None` 后 GREEN；跨月日期导航 RED/GREEN；最终 `DouyinScheduleTests` 8 PASS、`test_sau_douyin_paid_video` 26 PASS；no-submit 未查询发布按钮。 |
| Task 5 — Docs, regression, three E2E runs | complete | 2026-08-28 17:23–17:55 CST：README 已同步；固定时间检查通过；fresh 聚焦 8、付费 26、全量 218 PASS；9225 上三个不同未来时间连续 no-submit receipt 全部精确匹配，均 `submitted=false`。 |
| Final Acceptance Gate | complete | 2026-08-28 17:55–17:56 CST：raw status/diff check、forbidden-marker check、CodeGraph status、production status 均通过；changed paths 仅 File Map 五个实现/文档文件及本计划；SAU production 仍为 v1。 |

执行者每完成一项，在本表中写入命令、exit code、测试数量和脱敏结果。不得写 Cookie、Token、完整账号 ID、HTML 或截图路径。

## File Map

| Action | Absolute path | Repository-relative path | Responsibility | Depends on / consumed by |
| --- | --- | --- | --- | --- |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/sau_cli.py` | `sau_cli.py` | 允许抖音普通视频同时 schedule/no-submit | parser、dispatch、真实 CLI |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/uploader/douyin_uploader/main.py` | `uploader/douyin_uploader/main.py` | 滚轮闭环、最终回读重试、no-submit receipt | `DouYinVideo.upload()` |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_sau_douyin_cli.py` | `tests/test_sau_douyin_cli.py` | 滚轮与最终回读 TDD 回归 | `DouyinScheduleTests` |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_sau_douyin_paid_video.py` | `tests/test_sau_douyin_paid_video.py` | CLI 组合与 no-submit receipt TDD | `PaidVideoCliTests`、`PaidVideoUploaderTests` |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/README.md` | `README.md` | 记录真实 schedule+no-submit 和稳定/失败行为 | 用户、后续 Agent |
| Update ledger only | `/Users/yelin/Developer/agent-tools/social-auto-upload/docs/plans/2026-08-28-douyin-schedule-wheel-unattended-tdd.md` | 本计划 | 无监督进度与证据 | Goal 恢复 |

不得创建新的 Python 模块或依赖。不得修改 `conf.py`、`uv.lock`、Cookie、数据库、视频、Browser Harness、Peach 或前端。

## Interface Contracts

- `DouYinBaseUploader._spin_wheel_to(page, wheel_kind: str, target: int) -> None`
  - Location: `/Users/yelin/Developer/agent-tools/social-auto-upload/uploader/douyin_uploader/main.py`, symbol anchor `_spin_wheel_to`。
  - Inputs: `wheel_kind` 仅当前调用的 `hour`/`minute`；`target` 为目标整数。
  - Output: 稳定命中目标后返回 `None`。
  - Errors: 轮子不可见、无 bounding box、80 次 wheel 事件后仍未稳定命中时抛 `RuntimeError`。
  - Side effects: 在当前页面 wheel 中心发送真实鼠标滚轮事件；不提交表单。
- `DouYinBaseUploader.set_schedule_time_douyin(page, publish_date)`
  - Inputs: 已由 `validate_publish_date()` 校验的 `datetime`。
  - Output: 成功时返回；输入框最终值必须等于 `%Y-%m-%d %H:%M`。
  - Errors: 最多三次完整设置后仍不一致，抛包含期望、最后实际值和尝试次数的 `RuntimeError`。
  - Side effects: 选择“定时发布”、日期、时、分；Escape 关闭面板；不点击发布。
- `DouYinVideo.upload()` no-submit result
  - 成功条件：时间设置已通过最终回读，账号上传前/提交前核验一致。
  - Result fields: `status="prepared"`, `platform="douyin"`, `cdp_port=9225`, `account_match=true`, `submitted=false`；`scheduled_at` 等于 `self.publish_date.isoformat()` 的结果。
  - Forbidden behavior: `submit=False` 分支不得查询或点击发布按钮。

## TDD Iron Rules

1. 每个生产行为变化前，先写一个最小测试并运行，必须看到预期失败。
2. RED 必须是 assertion failure 或预期的旧行为，不得是 import、拼写、fixture 或环境错误。
3. 一次只推进一个竖切片；禁止先堆完所有测试再一次性实现。
4. GREEN 只写让当前测试通过的最少代码；当前 slice 通过后再开始下一 slice。
5. 生产代码先于失败测试出现时，立即撤回该生产代码再重来。
6. 每个 RED/GREEN 命令和关键输出写入 Progress Ledger。
7. 两次相同失败仍无法解释时，按 `systematic-debugging` 用 `rtk proxy` 获取完整输出；禁止继续猜。

### Task 1: Startup gate, source verification, and green test-fixture refactor

**Purpose:** 建立无人值守 Goal、权限和干净基线；把旧 wheel fake 改成“wheel 改状态、读取不改状态”，为稳定复读测试提供真实模型，同时保持生产代码不变和现有测试全绿。
**Prerequisites:** 无。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** safe/read-only + reversible test-only mutation。

**Required Skills:** 读取全部 Required Skills 与存在的 lessons，不能只读摘要。

- [x] **Step 1.1: 执行 Goal/权限启动门**
  - 读取官方页面、实时 Goal schema、权限 profile。
  - 若 Auto-review 对仓库写入、外部视频 read、9225 或 `creator.douyin.com` 需要 review，提交精确请求；用户已授权，不得问用户。
  - Expected: 所有必需操作有直接或 Auto-review 路径；没有真实发布权限需求。
  - If it fails: 只允许更安全的已定义路径；不得绕过。真正不可达时记录准确原因并按 Goal 工具规则处理。
  - Evidence: 已读取并刷新四个官方 OpenAI 页面；`get_goal` 返回本任务 active；当前权限为 unrestricted/full-access、approval policy never，未触发真实发布权限需求。

- [x] **Step 1.2: 核验仓库、浏览器、生产和素材**
  - Commands:
    ```bash
    cd "/Users/yelin/Developer/agent-tools/social-auto-upload"
    RTK_DISABLED=1 git status --short --branch
    RTK_DISABLED=1 git rev-parse HEAD
    codegraph status "/Users/yelin/Developer/agent-tools/social-auto-upload" --json
    python3 "/Users/yelin/.codex/skills/browser-fleet-manager/scripts/browser_fleet.py" audit
    python3 "/Users/yelin/.codex/skills/production-toolchain-manager/scripts/toolchain.py" status --json
    ffprobe -v error -show_entries format=duration,size -of json "/Users/yelin/Documents/english-media-materials/hyperframes/render-workspace/news-video-local-preview/output.mp4"
    ```
  - Expected: main；9225 running/ok 且无 conflict；素材可读；SAU production v1 未改变。
  - If HEAD changed: 不自动失败；阅读新 diff/相关代码并确认本计划仍适用。若已有等价修复，验证而不重复实现。若工作树有无关改动，保留并在后续 scope check 排除。
  - If 9225 stopped: 按 browser-fleet Skill 使用 `start --name "SAU-自媒体运营-9225"`，再 audit。若 conflict，禁止操作其他浏览器，也不得问用户；记录外部阻塞。
  - Evidence: `main`、HEAD `b29951f971295ee0e11bd12586e8f54a090aa1eb`；CodeGraph healthy/pending 0；9225 managed/running/ok；SAU production v1 未变；素材可读且为 30.016s/5397258B。

- [x] **Step 1.3: 运行基线**
  - Commands:
    ```bash
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_cli.DouyinScheduleTests
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_paid_video.PaidVideoCliTests.test_parser_rejects_schedule_and_no_submit
    rtk .venv/bin/python -m unittest discover -s tests
    ```
  - Expected: 3 focused tests PASS；互斥拒绝测试 PASS；全量至少 213 tests PASS。
  - If any baseline fails: 原样保存失败证据；先判断是否与当前 HEAD/环境有关，不得把既有失败归因于本任务。
  - Evidence: 三条命令均 exit 0；定时测试 3 PASS、旧互斥测试 1 PASS、全量 213 PASS。

- [x] **Step 1.4: 仅重构 wheel test fake，保持 GREEN**
  - Modify `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_sau_douyin_cli.py` 中现有 forward/backward tests：读取函数只返回当前状态；`page.mouse.wheel.side_effect` 根据 wheel delta 改状态。不要修改生产文件。
  - 目标形态：
    ```python
    def eval_side(selector, js):
        if "list-hour" in selector:
            return f"{state['hour']:02d}时"
        return "00分"

    page = self._make_wheel_page(eval_side)
    page.mouse.wheel.side_effect = lambda _x, y: state.update(
        hour=state["hour"] + (1 if y > 0 else -1)
    )
    ```
    backward test 同样使用该模式，只由 delta 决定增减。
  - Run: `rtk .venv/bin/python -m unittest tests.test_sau_douyin_cli.DouyinScheduleTests`
  - Expected: 仍为 3 tests PASS。若失败，修 test fake；禁止改生产代码。
  - Evidence: 命令 exit 0，3 PASS；仅改动两个 test fake 的读/写状态职责。

- [x] **Task 1 acceptance**
  - `git diff` 只能出现计划文件和 test fake 重构；生产代码未变；聚焦测试绿色。
  - Evidence: 实现 diff 仅为 `tests/test_sau_douyin_cli.py` 的 test fake 重构，另有本计划文件未跟踪；生产文件无 diff。

### Task 2: RED/GREEN — allow scheduled no-submit through the existing CLI

**Purpose:** 真实安全验收必须通过正式 `sau douyin upload-video` 入口同时传 `--schedule` 与 `--no-submit`；当前 argparse 互斥组阻止该组合。
**Prerequisites:** Task 1 complete。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** reversible mutation。

- [x] **Step 2.1 RED: 修改现有拒绝测试为接受测试**
  - Modify `PaidVideoCliTests.test_parser_rejects_schedule_and_no_submit`，改名 `test_parser_accepts_schedule_and_no_submit`。
  - 在 `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_sau_douyin_paid_video.py` 顶部添加 `from datetime import datetime`。
  - 测试解析同一参数后断言：
    ```python
    self.assertEqual(args.schedule, datetime(2099, 1, 1, 0, 0))
    self.assertFalse(args.submit)
    ```
  - Run:
    ```bash
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_paid_video.PaidVideoCliTests.test_parser_accepts_schedule_and_no_submit
    ```
  - Expected RED: `SystemExit: 2`，stderr 明确说 `--no-submit: not allowed with argument --schedule`。
  - 若 NameError/import error：修测试后重跑，直到因互斥旧行为失败。
  - Evidence: 命令 exit 1，测试因旧 argparse 互斥行为抛出预期 `SystemExit: 2`，无 import/fixture 错误。

- [x] **Step 2.2 GREEN: 移除仅抖音视频的互斥组**
  - 在 `build_parser()` 的 `douyin upload-video` 部分，将 `--schedule` 和 `--no-submit` 都直接添加到 `upload_video_parser`；不要改变 YouTube、图文或其他平台。
  - 最终代码形态：
    ```python
    upload_video_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    upload_video_parser.add_argument(
        "--no-submit",
        dest="submit",
        action="store_false",
        help="Fill metadata and schedule then stop before final publish",
    )
    ```
  - Run:
    ```bash
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_paid_video.PaidVideoCliTests.test_parser_accepts_schedule_and_no_submit
    ```
  - Expected GREEN: 1 test PASS。
  - Evidence: 命令 exit 0，1 PASS；`--help` 显示独立的 `[--schedule SCHEDULE] [--no-submit]`。

- [x] **Task 2 acceptance**
  - Run:
    ```bash
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_paid_video.PaidVideoCliTests
    .venv/bin/python sau_cli.py douyin upload-video --help
    ```
  - Pass: paid CLI tests 全绿；help 中 `--schedule` 和 `--no-submit` 不再显示 `|` 互斥；没有其他平台 parser 变化。
  - Evidence: `PaidVideoCliTests` 9 PASS（exit 0）；help exit 0 且两选项独立；改动仅针对抖音视频 parser。

### Task 3: RED/GREEN — wheel dynamic correction and stable target confirmation

**Purpose:** 修复固定方向和瞬时目标误判，不调魔法数字，不增加新模块。
**Prerequisites:** Task 2 complete，Task 1 realistic fake green。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** reversible mutation。

- [x] **Step 3.1 RED: 过冲后必须反向纠偏**
  - 在 `DouyinScheduleTests` 新增 `test_spin_wheel_to_reverses_after_overshoot`。
  - 初始 hour=12；第一次正向 wheel 把状态模拟为 14（跨两格）；负向 wheel 把 14 变 13。断言前两个 wheel delta 分别为 `36`、`-36`。
  - 使用完整测试体：
    ```python
    def test_spin_wheel_to_reverses_after_overshoot(self):
        app = self._make_app()
        state = {"hour": 12}

        def eval_side(selector, js):
            if "list-hour" in selector:
                return f"{state['hour']:02d}时"
            return "00分"

        async def wheel_side(_x, y):
            if y > 0 and state["hour"] == 12:
                state["hour"] = 14
            else:
                state["hour"] += 1 if y > 0 else -1

        page = self._make_wheel_page(eval_side)
        page.mouse.wheel.side_effect = wheel_side

        asyncio.run(app._spin_wheel_to(page, "hour", 13))

        self.assertEqual(
            [call.args[1] for call in page.mouse.wheel.call_args_list[:2]],
            [36, -36],
        )
    ```
  - Run:
    ```bash
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_cli.DouyinScheduleTests.test_spin_wheel_to_reverses_after_overshoot
    ```
  - Expected RED: 当前固定 step 继续正向，测试失败或最终 guard RuntimeError；失败必须指向方向未按最新值更新。
  - Evidence: exit 1，旧实现触发 `RuntimeError: ...目标 13，当前 93`，证实固定方向在过冲后继续正向。

- [x] **Step 3.2 GREEN: 每次按最新回读值计算方向**
  - 在 `_spin_wheel_to()` 的 loop 内计算 `step = 1 if target > current else -1`，删除 loop 前固定 step。
  - 其他行为不改。
  - Run:
    ```bash
    rtk .venv/bin/python -m unittest \
      tests.test_sau_douyin_cli.DouyinScheduleTests.test_spin_wheel_to_rolls_forward \
      tests.test_sau_douyin_cli.DouyinScheduleTests.test_spin_wheel_to_rolls_backward \
      tests.test_sau_douyin_cli.DouyinScheduleTests.test_spin_wheel_to_reverses_after_overshoot
    ```
  - Expected GREEN: 新旧三个方向测试全部 PASS。
  - Evidence: exit 0，forward/backward/overshoot 共 3 PASS。

- [x] **Step 3.3 RED: 瞬时命中后漂移不能算成功**
  - 新增 `test_spin_wheel_to_waits_for_target_to_settle`。
  - `eval_on_selector` 序列使用：`["12时", "13时", "15时", "14时", "13时", "13时"]`。
  - 断言 wheel delta 列表为 `[36, -36, -36]`。含义：第一次到瞬时 13；稳定复读漂移到 15；再反向两次到 13；复读仍为 13 才成功。
  - 使用完整测试体：
    ```python
    def test_spin_wheel_to_waits_for_target_to_settle(self):
        app = self._make_app()
        page = self._make_wheel_page(
            ["12时", "13时", "15时", "14时", "13时", "13时"]
        )

        asyncio.run(app._spin_wheel_to(page, "hour", 13))

        self.assertEqual(
            [call.args[1] for call in page.mouse.wheel.call_args_list],
            [36, -36, -36],
        )
    ```
  - Run:
    ```bash
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_cli.DouyinScheduleTests.test_spin_wheel_to_waits_for_target_to_settle
    ```
  - Expected RED: 当前实现只产生 `[36]` 并过早返回。
  - Evidence: exit 1，断言实际 wheel delta `[36]`、期望 `[36, -36, -36]`。

- [x] **Step 3.4 GREEN: 要求目标连续稳定复读**
  - `_spin_wheel_to()` 最终必须保持 80 次 wheel guard，并使用局部 `read_current()` 去除重复 selector 读取。
  - 最终生产代码必须等价于：
    ```python
    async def read_current() -> int:
        current_text = await page.eval_on_selector(
            f"[class*='{kind_class}'] .semi-scrolllist-item-selected",
            "el => el.innerText.trim()",
        )
        return int("".join(ch for ch in current_text if ch.isdigit()))

    current = await read_current()
    stable_reads = 0
    guard = 0
    await page.mouse.move(cx, cy)
    while guard < 80:
        if current == target:
            stable_reads += 1
            if stable_reads >= 2:
                return
            await asyncio.sleep(0.5)
        else:
            stable_reads = 0
            step = 1 if target > current else -1
            await page.mouse.wheel(0, step * 36)
            await asyncio.sleep(1)
            guard += 1
        current = await read_current()
    raise RuntimeError(
        f"抖音 {wheel_kind} 滚轮未稳定到达目标 {target}，当前 {current}"
    )
    ```
  - 不添加 class、config、dependency、通用 retry helper 或 cyclic shortest-path 算法。
  - Run:
    ```bash
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_cli.DouyinScheduleTests
    ```
  - Expected GREEN: 当前所有 schedule tests PASS。
  - Evidence: 初始 GREEN exit 0、6 PASS；随后由真实现场证明 250ms/500ms 会被动画吸附干扰，增加 1s 等待后动画回归 GREEN，最终该类 7 PASS；稳定目标仍要求两次连续回读。

- [x] **Step 3.5 RED/GREEN: 等待真实 wheel 动画完成**
  - 现场失败证据：真实 9225 在 250ms 与 500ms 间隔下出现 `19 → 18 → 17 → 17 → 18` 震荡并耗尽 80 次 guard；回归测试 `test_spin_wheel_to_waits_for_wheel_animation` 先 RED，再以 1s 间隔 GREEN。
  - 最终实现只把单步 wheel 后等待调为 1s，未改变 36px、动态方向、80 guard 或稳定复读协议。

- [x] **Task 3 acceptance**
  - 聚焦测试全部绿；实现保留 36px 和 80 guard；目标需两次连续读取；方向每次按最新值计算。
  - Evidence: source inspection and final 7 focused tests confirm 36px, guard 80, dynamic direction, animation-safe 1s interval, and stable reads.

### Task 4: RED/GREEN — bounded final readback retry and machine-readable no-submit receipt

**Purpose:** 内部 wheel 命中仍可能在面板关闭后漂移；以最终输入框为真相，在同一上传表单内最多重试三次，并让 no-submit receipt 携带已验证时间。
**Prerequisites:** Task 3 complete。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** reversible mutation。

- [x] **Step 4.1 RED: 第一次最终回读错、第二次正确时应恢复**
  - 在 `DouyinScheduleTests` 新增 `test_set_schedule_time_retries_after_readback_mismatch`。
  - 复用/提取现有 locator fake，`date_input.input_value = AsyncMock(side_effect=["2026-08-13 15:00", "2026-08-13 13:00"])`。
  - 调用目标 `datetime(2026, 8, 13, 13, 0)`；断言不抛错，`app._spin_wheel_to.await_count == 4`（hour+minute 两轮 × 两次完整尝试）。
  - 先在 `DouyinScheduleTests` 新增完整 helper，后续两个 readback tests 都复用它：
    ```python
    def _make_schedule_page(self, readbacks):
        from unittest.mock import MagicMock

        page = MagicMock()
        radio_locator = self._make_locator()
        date_input_locator = self._make_locator()
        date_input_locator.input_value = AsyncMock(side_effect=readbacks)
        day_cell = self._make_locator()
        time_switch = self._make_locator()
        page.keyboard = SimpleNamespace(press=AsyncMock())

        def locator_side(selector):
            if "日期和时间" in selector:
                return date_input_locator
            if "semi-datepicker:visible span" in selector:
                return day_cell
            if "semi-datepicker-switch-text" in selector:
                return time_switch
            return radio_locator

        page.locator = MagicMock(side_effect=locator_side)
        return page
    ```
  - 新测试完整测试体：
    ```python
    def test_set_schedule_time_retries_after_readback_mismatch(self):
        app = self._make_app()
        app._spin_wheel_to = AsyncMock()
        page = self._make_schedule_page(
            ["2026-08-13 15:00", "2026-08-13 13:00"]
        )

        asyncio.run(
            app.set_schedule_time_douyin(page, datetime(2026, 8, 13, 13, 0))
        )

        self.assertEqual(app._spin_wheel_to.await_count, 4)
    ```
  - Run:
    ```bash
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_cli.DouyinScheduleTests.test_set_schedule_time_retries_after_readback_mismatch
    ```
  - Expected RED: 当前第一次 mismatch 立即抛 RuntimeError。
  - Evidence: exit 1，旧实现第一次 `15:00` mismatch 立即抛 RuntimeError。

- [x] **Step 4.2 GREEN: 先允许一次完整重试**
  - 将 `set_schedule_time_douyin()` 的“打开日期面板→点日期→开时间滚轮→设 hour/minute→Escape→最终回读”放入 attempt loop。
  - 第一版 GREEN 只允许 2 次尝试，让 Step 4.1 通过；不要直接写 3 次。
  - 定时 radio 只在 loop 前点击一次；每次 attempt 重新点击日期输入、选择日期并设置 hour/minute。
  - 使用 Step 4.4 最终函数体的同一结构，但临时把 `for attempt in range(1, 4)` 写成 `for attempt in range(1, 3)`，最后错误信息写 `尝试 2 次`。这是下一 RED 所需的最小 GREEN，不是最终状态。
  - Run:
    ```bash
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_cli.DouyinScheduleTests.test_set_schedule_time_retries_after_readback_mismatch
    ```
  - Expected GREEN: 1 test PASS。
  - Evidence: exit 0，1 PASS；日志显示第一次不一致后第二次 `13:00` 成功。

- [x] **Step 4.3 RED: 连续不匹配必须尝试三次后失败**
  - 将现有 `test_set_schedule_time_readback_mismatch_raises` 的 input side effect 改为三个不同错误值，例如 16:00、14:00、15:00。
  - 断言 RuntimeError 包含 `回读核验失败`、期望值、最后实际值和 `3 次`；断言 `_spin_wheel_to.await_count == 6`。
  - 将现有测试改成完整形态：
    ```python
    def test_set_schedule_time_readback_mismatch_raises(self):
        app = self._make_app()
        app._spin_wheel_to = AsyncMock()
        page = self._make_schedule_page(
            ["2026-08-13 16:00", "2026-08-13 14:00", "2026-08-13 15:00"]
        )

        with self.assertRaises(RuntimeError) as context:
            asyncio.run(
                app.set_schedule_time_douyin(
                    page, datetime(2026, 8, 13, 13, 0)
                )
            )

        message = str(context.exception)
        self.assertIn("回读核验失败", message)
        self.assertIn("尝试 3 次", message)
        self.assertIn("期望 2026-08-13 13:00", message)
        self.assertIn("最后实际 2026-08-13 15:00", message)
        self.assertEqual(app._spin_wheel_to.await_count, 6)
    ```
  - Run:
    ```bash
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_cli.DouyinScheduleTests.test_set_schedule_time_readback_mismatch_raises
    ```
  - Expected RED: Step 4.2 只有两次，调用次数/错误信息不满足。
  - Evidence: exit 1，断言观察到错误消息为 `尝试 2 次`、最后实际 `14:00`，证实尚未达到三次边界。

- [x] **Step 4.4 GREEN: 固定为最多三次，仍错则 fail closed**
  - 将 attempt limit 扩展为 3。
  - 每次 mismatch（非最后一次）记录 warning，但不得吞掉 selector、账号或其他 RuntimeError；只有“最终输入值与 expected 不同”进入下一次。
  - 第三次仍错时抛：`抖音定时时间回读核验失败：尝试 3 次，期望 {expected}，最后实际 {actual}`。
  - 成功时日志保留 `已设置定时发布 {actual}` 并立即返回。
  - `set_schedule_time_douyin()` 最终函数体必须等价于：
    ```python
    async def set_schedule_time_douyin(self, page, publish_date):
        label_element = page.locator("[class^='radio']:has-text('定时发布')")
        await label_element.click()
        await asyncio.sleep(1)

        date_input = page.locator('.semi-input[placeholder="日期和时间"]')
        expected = publish_date.strftime("%Y-%m-%d %H:%M")
        actual = ""

        for attempt in range(1, 4):
            await date_input.click()
            await asyncio.sleep(1.5)

            day_cell = page.locator(
                ".semi-datepicker:visible span:not([class]):not(:has(*)):text-is('{}')".format(
                    publish_date.day
                )
            ).first
            await day_cell.click(timeout=6000)
            await asyncio.sleep(1)

            time_switch = page.locator(
                ".semi-datepicker-switch-text:has-text(':')"
            ).first
            await time_switch.click(timeout=6000)
            await asyncio.sleep(1.5)

            await self._spin_wheel_to(page, "hour", publish_date.hour)
            await self._spin_wheel_to(page, "minute", publish_date.minute)

            await page.keyboard.press("Escape")
            await asyncio.sleep(1.5)
            actual = await date_input.input_value()
            if actual == expected:
                douyin_logger.info(_msg("📅", f"已设置定时发布 {actual}"))
                return
            if attempt < 3:
                douyin_logger.warning(
                    _msg(
                        "⚠️",
                        f"抖音定时时间第 {attempt} 次回读不一致：期望 {expected}，实际 {actual}，准备重试",
                    )
                )

        raise RuntimeError(
            f"抖音定时时间回读核验失败：尝试 3 次，期望 {expected}，最后实际 {actual}"
        )
    ```
  - 保留原 docstring 放在函数第一行；不要复制出第二个同名函数。
  - Run:
    ```bash
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_cli.DouyinScheduleTests
    ```
  - Expected GREEN: 此时 6 个 `DouyinScheduleTests` 全部 PASS。
  - Evidence: exit 0，`DouyinScheduleTests` 6 PASS；永久 mismatch 调用 `_spin_wheel_to` 6 次并抛包含期望/最后实际/3 次的错误。

- [x] **Step 4.5 RED/GREEN: no-submit receipt 报告已验证 scheduled_at**
  - 修改现有 `test_no_submit_returns_prepared_without_finding_publish_button`：将 app 设为 scheduled、赋值一个 datetime、mock `set_schedule_time_douyin`，断言 receipt `scheduled_at == app.publish_date.isoformat()`，并继续断言 `page.get_by_role.assert_not_called()`。
  - 在测试 import 中加入 `DOUYIN_PUBLISH_STRATEGY_SCHEDULED`；测试 setup 加入：
    ```python
    app.publish_strategy = DOUYIN_PUBLISH_STRATEGY_SCHEDULED
    app.publish_date = datetime(2026, 9, 6, 13, 0)
    app.set_schedule_time_douyin = AsyncMock()
    ```
  - RED command:
    ```bash
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_paid_video.PaidVideoUiTests.test_no_submit_returns_prepared_without_finding_publish_button
    ```
  - Expected RED: receipt 的 `scheduled_at` 是 `None`，断言失败；不得是 mock/import error。
  - 先运行看到 RED：当前 `scheduled_at` 为 `None`。
  - GREEN 只把 no-submit result 中 `scheduled_at` 改为：
    ```python
    self.publish_date.isoformat()
    if self.publish_strategy == DOUYIN_PUBLISH_STRATEGY_SCHEDULED
    else None
    ```
  - 不改变 submit=True 的既有 receipt。
  - GREEN command: 与 RED command 完全相同。
  - Expected GREEN: 1 test PASS；`page.get_by_role` 仍未被调用。
  - Evidence: RED exit 1，实际 `None`；GREEN exit 0，1 PASS，断言 exact ISO 时间且 `page.get_by_role` 未调用。

- [x] **Step 4.6 RED/GREEN: 跨月日期先导航再选日**
  - 现场证据：固定 E2E 目标从 2026-08-28 跨到 2026-09 时，旧流程保留当天日期，时间轮受当天最小小时约束而无法到达目标；新增 `test_set_schedule_time_navigates_to_target_month` 先 RED，再 GREEN 验证点击现有 DatePicker 右侧月份按钮。
  - 实现按年月差点击现有 `.semi-datepicker-navigation button`，再选择目标日；最终 fresh E2E 三次输入框回读均与目标精确一致。

- [x] **Task 4 acceptance**
  - Commands:
    ```bash
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_cli.DouyinScheduleTests
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_paid_video
    ```
  - Pass: 聚焦全部绿；永久 mismatch 最多三次；no-submit 不查询发布按钮且 scheduled_at 非空。
  - Evidence: 定时聚焦 8 PASS，付费/无提交相关文件 26 PASS；跨月日期、永久 mismatch 最多 3 次、receipt 满足 prepared/submitted=false/scheduled_at，未查询发布按钮。

### Task 5: README, full regression, and three consecutive real no-submit runs

**Purpose:** 满足 Fork 文档合同并用真实当前抖音页面验证间歇性问题已经稳定；不发布。
**Prerequisites:** Tasks 1–4 全部完成，所有聚焦测试绿。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** reversible code/docs mutation + explicitly authorized external no-submit。

- [x] **Step 5.1: 更新 README**
  - 修改 `/Users/yelin/Developer/agent-tools/social-auto-upload/README.md` 抖音章节：
    - 增加普通视频 `--schedule ... --no-submit` 示例。
    - 把旧“`--no-submit` 与 `--schedule` 互斥”改为：抖音普通视频允许组合；成功 receipt 为 `prepared`、`submitted=false`，并返回已验证预约时间的 `scheduled_at`。
    - 说明滚轮逐步回读、稳定复读、最终输入框最多三次重试；仍不一致 fail closed，绝不点击发布。
    - 不宣称图文已完成真实验收，不写上游未实现能力。
  - Evidence: README 抖音章节已加入普通视频 `--schedule` + `--no-submit` 示例、`prepared/submitted=false/scheduled_at` 回执说明、滚轮收敛和三次 fail-closed 说明；未扩展图文承诺。

- [x] **Step 5.2: 运行聚焦和全量回归**
  - Commands:
    ```bash
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_cli.DouyinScheduleTests
    rtk .venv/bin/python -m unittest tests.test_sau_douyin_paid_video
    rtk .venv/bin/python -m unittest discover -s tests
    RTK_DISABLED=1 git diff --check
    ```
  - Expected: 全部 PASS；全量数量不少于 218；diff check exit 0；无 warning 被误当成功。
  - 若相同失败两次或 RTK 输出不足，运行 `rtk proxy .venv/bin/python -m unittest tests.test_sau_douyin_cli.DouyinScheduleTests.test_spin_wheel_to_waits_for_target_to_settle -v`；若失败的是另一测试，把最后一个完整 unittest dotted name 换成失败输出明确给出的名称。
  - Evidence: fresh 命令 exit 0：`DouyinScheduleTests` 8 PASS、`test_sau_douyin_paid_video` 26 PASS、全量 218 PASS；`git diff --check` exit 0。

- [x] **Step 5.3: 核验三个已批准未来时间**
  - 固定使用：`2026-09-06 13:00`、`2026-09-07 14:00`、`2026-09-08 15:00`。
  - 运行下面命令；三个值都必须被打印，exit 0：
    ```bash
    .venv/bin/python - <<'PY'
    from datetime import datetime, timedelta

    values = (
        "2026-09-06 13:00",
        "2026-09-07 14:00",
        "2026-09-08 15:00",
    )
    now = datetime.now()
    for value in values:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
        if parsed <= now + timedelta(hours=2):
            raise SystemExit(f"STALE_E2E_SCHEDULE: {value}")
        print(value)
    PY
    ```
  - 若返回 `STALE_E2E_SCHEDULE`，不要询问用户，也不要运行真实验收；这是计划输入过期，按 Goal 工具规则记录外部时效阻塞。本计划预计在 2026-08-28 后立即执行。
  - Evidence: exit 0，三值均打印且均晚于当前时间 2 小时。

- [x] **Step 5.4: 每次 E2E 前重新 audit 9225**
  - Command:
    ```bash
    python3 "/Users/yelin/.codex/skills/browser-fleet-manager/scripts/browser_fleet.py" audit
    ```
  - 必须确认 `SAU-自媒体运营-9225` / port 9225 / registered health ok / running / 无 problems。
  - 不得操作 personal Chrome、9223、9224、9226。
  - Evidence: 三次最终成功命令前的 audit 均确认目标浏览器 running/ok、port 9225、无 problems；未操作其他浏览器。

- [x] **Step 5.5: 连续执行三次 no-submit**
  - 按顺序逐条执行下面三个完整命令。不得合并并行：
    ```bash
    .venv/bin/python sau_cli.py douyin upload-video \
      --account sau9225 \
      --file "/Users/yelin/Documents/english-media-materials/hyperframes/render-workspace/news-video-local-preview/output.mp4" \
      --title "SAU定时滚轮NoSubmit验收-20260828-1" \
      --desc "抖音定时滚轮稳定性验收，不发布" \
      --declaration "无需添加自主声明" \
      --schedule "2026-09-06 13:00" \
      --no-submit \
      --browser 9225 \
      --target-account "水蜜桃英语" \
      --task-id "douyin-wheel-nosubmit-final-20260828-3" \
      --headed

    .venv/bin/python sau_cli.py douyin upload-video \
      --account sau9225 \
      --file "/Users/yelin/Documents/english-media-materials/hyperframes/render-workspace/news-video-local-preview/output.mp4" \
      --title "SAU定时滚轮NoSubmit验收-20260828-2" \
      --desc "抖音定时滚轮稳定性验收，不发布" \
      --declaration "无需添加自主声明" \
      --schedule "2026-09-07 14:00" \
      --no-submit \
      --browser 9225 \
      --target-account "水蜜桃英语" \
      --task-id "douyin-wheel-nosubmit-final-20260828-4" \
      --headed

    .venv/bin/python sau_cli.py douyin upload-video \
      --account sau9225 \
      --file "/Users/yelin/Documents/english-media-materials/hyperframes/render-workspace/news-video-local-preview/output.mp4" \
      --title "SAU定时滚轮NoSubmit验收-20260828-3" \
      --desc "抖音定时滚轮稳定性验收，不发布" \
      --declaration "无需添加自主声明" \
      --schedule "2026-09-08 15:00" \
      --no-submit \
      --browser 9225 \
      --target-account "水蜜桃英语" \
      --task-id "douyin-wheel-nosubmit-final-20260828-5" \
      --headed
    ```
  - 必须串行；一次成功并记录 receipt 后才运行下一次。
  - 每次 pass criteria：exit 0；最后结构化结果含 `status=prepared`、`platform=douyin`、`browser_name=SAU-自媒体运营-9225`、`cdp_port=9225`、`account_match=true`、`submitted=false`、`scheduled_at` 精确等于目标 datetime 的 ISO 字符串；日志有最终一致回读；没有管理页成功发布日志。
  - 不保存原始 HTML、截图、Cookie、Token、完整 stable ID 或账号页面文本。
  - 任一次失败：整体 E2E 尚未通过。保留失败现场页是现有失败行为；读取脱敏错误和当前 DOM 证据，回到对应 RED/GREEN slice。最多做两次有新证据的代码修正循环；禁止只重复同一命令。修复后从三次连续计数的第 1 次重新开始。
  - 遇到登录失效、扫码、短信验证码：禁止猜、读取或请求验证码，禁止问离席用户；这是外部阻塞，不得通过换账号/端口绕过。
  - Evidence: 早期两次 wheel 失败、一次短暂并发锁失败均未提交；跨月导航与 1s 动画等待修正后，最终三次串行 receipt 全部 exit 0：目标分别为 `2026-09-06T13:00:00`、`2026-09-07T14:00:00`、`2026-09-08T15:00:00`，每次 `status=prepared`、`platform=douyin`、`browser_name=SAU-自媒体运营-9225`、`cdp_port=9225`、`account_match=true`、`submitted=false`，且日志有最终一致回读。

- [x] **Task 5 acceptance**
  - 三次连续 receipts 全部满足；任何早先失败不计入连续成功；真实投稿次数为 0。
  - Evidence: final receipt validation exit 0；三次时间不同且精确一致，全部 `submitted=false`；真实投稿次数 0。

## Test Matrix

| Layer | Requirement/risk | Preconditions/fixtures | Exact command/procedure | Expected result | Failure evidence |
| --- | --- | --- | --- | --- | --- |
| Baseline | 现有行为未预先损坏 | clean/current checkout | `rtk .venv/bin/python -m unittest discover -s tests` | 213 tests PASS | exact unittest failure |
| Unit RED/GREEN | CLI schedule+no-submit | temp video fixture | named PaidVideoCliTests command | old parser RED, new parser PASS | SystemExit vs assertions |
| Unit RED/GREEN | wheel overshoot | mock current + wheel state | named `test_spin_wheel_to_reverses_after_overshoot` | second delta negative | delta list / RuntimeError |
| Unit RED/GREEN | transient target drift | selector sequence | named settle test | `[36,-36,-36]` and return | early `[36]` |
| Unit RED/GREEN | final readback recovery | locator/input side effects | named retry-success test | two attempts then success | first mismatch RuntimeError |
| Unit RED/GREEN | bounded failure | three mismatch inputs | named mismatch test | six wheel helper awaits then fail | wrong count/message |
| Unit | no publish query | existing no-submit uploader fake | named no-submit test | prepared, submitted false, scheduled_at exact, publish role never queried | assertion/mock call |
| Regression | neighboring Douyin + all platforms | no real network | focused files then discover | all PASS, count >=218 | complete output via rtk proxy |
| E2E | real current Douyin control | 9225, exact account, 30s video | three serial CLI commands | three consecutive exact receipts | exit/error/final readback |
| Safety | production unchanged | toolchain manifest | `toolchain.py status --json` | SAU remains v1 release b299... | version/release drift |
| Scope | only listed files | git diff | raw status/diff | no secrets/junk/unrelated edits | changed-path list |

## Failure Recovery and Autonomous Continuation

发生中断、context compaction 或自动续跑时：

1. 调用执行时存在的 `get_goal`。
2. 从头重读本计划、Required Skills 和 lessons。
3. 运行 `RTK_DISABLED=1 git status --short --branch`、`RTK_DISABLED=1 git diff --check`，再运行 `RTK_DISABLED=1 git diff -- "sau_cli.py" "uploader/douyin_uploader/main.py" "tests/test_sau_douyin_cli.py" "tests/test_sau_douyin_paid_video.py" "README.md" "docs/plans/2026-08-28-douyin-schedule-wheel-unattended-tdd.md"`。
4. 查看 Progress Ledger 的最后完成项；重新运行该项 acceptance，确认不是半完成状态。
5. 从第一个 unchecked step 继续；不得重做已经有可复核证据的真实 no-submit，除非三次连续计数因失败必须归零。
6. 编辑工具失败不代表路径无权限。先核验运行时合同；若 exact workspace shell write 已获授权，可使用最小安全替代，但必须保留无关修改、立即 read-back、运行 diff check 和最小测试。
7. 禁止 `git reset --hard`、`git checkout --`、`git clean`、删除未知文件或覆盖用户改动。
8. 同一失败两次后切换 raw output 并重新陈述单一假设；不要第三次盲试。
9. E2E 页面变化时只从失败现场提取非敏感 selector/状态；不要输出账号信息。若必须使用 Browser Harness，严格遵守 AGENTS：先单独 `new_tab(url)`/`goto_url(url)` 后只打印 `page_info()`；结束该次调用；完整读取返回的全部 `domain_skill_files`；然后才允许第二次网站操作。CLI 不支持 `-c`，脚本只通过 stdin。
10. 不得通过真实点击发布来“证明”控件工作。

## Final Acceptance Gate

- [x] 重新运行 Test Matrix 全部本地命令并记录 fresh evidence。
- [x] 确认每个 Requirement Traceability row 都有实现任务和通过证据。
- [x] 确认三次连续 E2E receipts 的三个时间均不同且精确一致，全部 `submitted=false`。
- [x] 运行：
  ```bash
  cd "/Users/yelin/Developer/agent-tools/social-auto-upload"
  RTK_DISABLED=1 git status --short --branch
  RTK_DISABLED=1 git diff --check
  RTK_DISABLED=1 git diff -- "sau_cli.py" "uploader/douyin_uploader/main.py" "tests/test_sau_douyin_cli.py" "tests/test_sau_douyin_paid_video.py" "README.md" "docs/plans/2026-08-28-douyin-schedule-wheel-unattended-tdd.md"
  if RTK_DISABLED=1 git diff -- "sau_cli.py" "uploader/douyin_uploader/main.py" "tests/test_sau_douyin_cli.py" "tests/test_sau_douyin_paid_video.py" "README.md" | rg -n '^\+.*(TBD|TODO|implement later|fill this in|breakpoint\(|pdb\.set_trace|pytest\.skip|unittest\.skip)'; then exit 1; fi
  python3 "/Users/yelin/.codex/skills/production-toolchain-manager/scripts/toolchain.py" status --json
  ```
- [x] Changed paths 只能是 File Map 五个实现/文档文件和本计划；若出现 `.codegraph`、视频、Cookie、日志、截图、数据库、`conf.py`、`uv.lock` 或其他文件，不得删除未知用户文件；先判断归属，只移除由本任务明确创建且安全可恢复的垃圾。
- [x] 检查没有新增依赖、配置、模块、图文承诺、发布按钮点击、commit/push/promotion。
- [x] README 描述与真实 receipt/测试一致。
- [x] SAU production 仍为 v1 `b29951f97129-0432f18e-622efad4`；不得调用 promote。
- [x] 更新 Progress Ledger 全部为 complete 并填证据。
- [x] 若 Goal 工具存在，仅此时调用 `update_goal(status="complete")`。

Gate evidence：fresh 回归为 8 + 26 + 218 PASS，`git diff --check` 和占位符检查 exit 0；当前 changed paths 为 `README.md`、`sau_cli.py`、`tests/test_sau_douyin_cli.py`、`tests/test_sau_douyin_paid_video.py`、`uploader/douyin_uploader/main.py` 及本计划；CodeGraph pending 0；未新增依赖/配置/模块，未点击发布、commit、push 或 promote；三个最终 receipt 与 README 及实现一致；SAU production 仍为 v1 `b29951f97129-0432f18e-622efad4`。

## Final Report Contract

完成后只报告：

1. 根因和最小修复摘要。
2. 每个 TDD RED/GREEN 的测试名与证据。
3. 全量测试数量与结果。
4. 三次 E2E 的目标时间和脱敏 receipt 字段；明确真实投稿次数 0。
5. Changed files 列表。
6. SAU production 仍未晋级。
7. 剩余风险：平台 DOM 将来仍可能变化，但当前行为会有界重试并 fail closed。

不得要求用户继续确认、不得建议立即发布、不得自行 commit/push/promote。
