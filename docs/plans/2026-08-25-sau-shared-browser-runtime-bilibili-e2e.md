# SAU 公共浏览器运行时、账号路由与 Bilibili 9225 真实验收实施计划

> **Executor:** 低能力自主执行 agent，在执行时实时存在的权限和工具合同下工作。你没有任何此前对话上下文。必须从第一行读到最后一行，按任务顺序执行，不得猜测省略内容、扩大范围、另起框架或要求离开电脑的用户处理例行问题。

**Goal:** 在 `/Users/yelin/Developer/agent-tools/social-auto-upload` 当前 `main` 工作区和现有未提交改动之上，复用 `browser_selector.py`、`browser_runtime.py`、`account_identity.py`、`direct_cdp.py` 与当前平台 uploader，完成抖音、YouTube、Bilibili 三个平台的公共浏览器输入、账号盘点与唯一路由、后台页面优先、确定性标签页回收、结构化登录状态、批量任务、浏览器互斥和任务防重复；保持现有抖音/YouTube 发布能力不回归，并由 SAU 自身使用 `SAU-自媒体运营-9225` 在正确 Bilibili UID 下创建且仅创建一条定时于 `2026-08-29 20:00 Asia/Shanghai` 的真实测试投稿，取得脱敏读回证据。

**Done when:** 本文九个任务全部完成；全量测试不低于当前 132 项且全部通过；单浏览器名称/端口/CDP URL 兼容；多浏览器扫描和唯一账号路由可执行；登录过期与提取错误可区分；同一端口并发被阻止；相同 task ID 不会重复提交；CDP 页面默认后台创建，后台创建失败只允许一次前台兜底并在结果中标记；成功关闭本任务全部新页，失败或待登录只保留最后一个新页，执行前已有页面永不关闭；Bilibili 真实投稿账号稳定 ID 为 `526557505`，标题唯一、排期正确、封面存在、投稿数量为一；没有新增第三方依赖、没有秘密泄漏、没有 commit/push/分支/PR/发布包操作。

**Workspace root:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Repository root:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Plan file:** `/Users/yelin/Developer/agent-tools/social-auto-upload/docs/plans/2026-08-25-sau-shared-browser-runtime-bilibili-e2e.md`
**Target environment:** 本地开发环境；macOS Darwin arm64；shell `/bin/zsh`；仓库 `.venv/bin/python` 为 Python 3.11.15；`uv` 0.11.7；项目声明 Python `>=3.10,<3.13`；Patchright 1.58.2；biliup v1.2.2；不得使用系统 Python 3.9.6 运行项目测试。
**Execution mode:** `unattended`
**Live permission contract:** 计划作者于 `2026-08-25 Asia/Shanghai` 核验：当前宿主是 `workspace-write`，reviewer 为 `auto_review`，仓库根和 `/private/tmp` 可写，网络受限，`.git`、`.agents`、`.codex` 受保护；当前运行时暴露 `create_goal`、`get_goal`、`update_goal`。用户声明执行器将获得最高权限，但执行器仍必须以自己的实时 permission profile 为准。Auto-review 是审查器而不是权限扩张；拒绝后禁止绕过或重复同一动作。
**Architecture/approved approach:** 不创建第二套浏览器框架，不复制 Chrome Profile，不引入服务、数据库或依赖。扩展现有四个公共模块：selector 负责一个或多个受管浏览器，runtime 负责后台任务页、页面所有权与端口互斥，identity 负责稳定账号合同，direct CDP 负责 Patchright 失败时的最小读取并回收自己创建的 target；CLI 只做顺序编排和批量清单。只接入抖音、YouTube、Bilibili，其他平台保持现状。
**Tech stack:** Python、`argparse`、`asyncio`、Patchright/Playwright CDP、Node 内置 WebSocket fallback、`requests`、标准库 `unittest`、外部 biliup、ffmpeg/ffprobe；不得新增第三方依赖。

## Required Skills

- `openai-docs`
  - SKILL.md: `/Users/yelin/.codex/skills/.system/openai-docs/SKILL.md`
  - Lessons: `none found`
  - Use for: 启动时刷新官方 Sandbox、Auto-review、审批安全和 Goal 长任务合同。
- `writing-plans`
  - SKILL.md: `/Users/yelin/.codex/skills/writing-plans/SKILL.md`
  - Lessons: `/Users/yelin/.codex/skills/writing-plans/references/lessons.md`
  - Use for: 无监督恢复、Progress Ledger、权限边界和最终完成门。
- `browser-fleet-manager`
  - SKILL.md: `/Users/yelin/.codex/skills/browser-fleet-manager/SKILL.md`
  - Lessons: `/Users/yelin/.codex/skills/browser-fleet-manager/references/lessons.md`
  - Use for: 只读核验 `SAU-自媒体运营-9225` 的名称、端口、Profile、进程和健康；不得读取 Profile Cookie DB。
- `ponytail:ponytail`
  - SKILL.md: `/Users/yelin/.codex/plugins/cache/devkeeper-ponytail-local/ponytail/4.8.4/skills/ponytail/SKILL.md`
  - Lessons: `none found`
  - Use for: 复用现有代码、最少文件、标准库优先、不做推测性抽象。

## Applicable Rules

- `/Users/yelin/Developer/agent-tools/social-auto-upload/AGENTS.md`: 简体中文；路径使用双引号；普通命令先用 `rtk`；认证、安全、完整 diff 用 raw；先读后写；`apply_patch` 修改仓库文件；不创建分支、worktree、commit、push；真实外部副作用只限本文明确授权内容。
- `/Users/yelin/Developer/agent-tools/social-auto-upload/CLAUDE.md`: CLI 新工作使用 `sau` 入口；平台自动化保持异步；平台特有行为留在对应 uploader。
- `/Users/yelin/.codex/skills/browser-fleet-manager/SKILL.md`: 个人 Chrome、9223、9224 只识别不操作；9225 锚点冲突时停止所有浏览器动作；不得直接改 `registry.json`。
- PONYTAIL full: 不添加基础类层级、插件系统、队列服务、数据库表、账号账本或依赖；已有 helper 能解决时禁止重写。

## Scope

### In scope

- 保留单个 `--browser` 和 `--cdp-url`，增加明确的候选浏览器数组输入与唯一账号路由。
- 三平台账号扫描矩阵：浏览器、平台、登录状态、昵称、稳定 ID、handle、Profile URL。
- 登录状态区分：`logged_in`、`interaction_required`、`error`；提取器异常不能伪装成未登录。
- 发布前准备阶段与最终提交前稳定 ID 二次校验。
- 默认后台创建任务标签页；只有 CDP 后台 target 创建失败时，允许一次 `context.new_page()` 前台兜底，并输出 `focus_fallback_used=true`。
- 只管理当前任务新建页面：成功全关；失败/待登录留最后一个；原有页面不动。
- 三平台顺序批量任务、单项结果隔离、浏览器端口互斥、task ID 防重复。
- Bilibili 的只读账号识别、9225 Web Cookie 到 biliup 凭证转换、定时投稿、封面和投稿读回。
- 本地单元/集成测试和一次已授权 Bilibili 真实定时投稿。

### Out of scope

- 快手、小红书、视频号、百家号、TikTok 的新公共闭环接入。
- 前端、Flask API、SQLite、账号相似度算法、模糊匹配、跨平台统一账号 ID。
- 批量并行执行；本轮批量按顺序运行，避免共享浏览器竞争。
- 用 JavaScript `element.click()` 批量替换 Playwright `locator.click()`。Playwright 点击本身不移动系统鼠标；焦点问题在任务页创建和激活，禁止破坏 actionability 检查。
- 清理执行前已经存在的 44 个标签页。它们的归属不可证明，必须保存；本计划只保证未来任务不新增残留。
- 删除现有 YouTube 草稿、YouTube/抖音测试作品、Bilibili 测试作品。
- Browser Harness 作为 SAU 运行依赖或验收依赖。
- 创建分支/worktree、commit、push、PR、release、部署、全局安装包。

### Allowed side effects

- 修改 File Map 中列出的仓库文件，保留所有其他用户改动。
- 在 `/private/tmp/social-auto-upload-task-state` 写入 0600 的任务锁和脱敏 receipt；仅允许删除当前进程拥有的锁或已验证 PID 不存在的 stale lock。
- 在 `/private/tmp/sau-e2e-20260829` 复用/补充脱敏测试证据；不得删除现有媒体。
- 只读审计 9225；通过 Chrome/CDP 使用 9225 当前登录态；程序内部读取 Cookie 但绝不输出值。
- 用户已明确授权：使用 9225、Bilibili UID `526557505`、测试视频和封面创建一条且仅一条定时于 `2026-08-29 20:00 Asia/Shanghai` 的真实 Bilibili 投稿。
- 关闭当前 SAU 命令创建并记录为 owned 的标签页；不得关闭执行前页面。

### Forbidden and human-gated side effects

- 禁止停止、kill、重启、改名、换端口、退役或删除任何 Chrome；禁止操作个人 Chrome、9223、9224。
- 禁止关闭未被当前 `BrowserSession` 记录为新建的页面。
- 禁止立即发布、第二条 Bilibili 投稿、重新提交现有 YouTube/抖音测试、评论、私信、账号资料修改、购买、付费、删除平台内容。
- 禁止删除/覆盖用户文件、重置 Git、清理脏树、修改 Cookie 文件内容以伪造身份。
- 用户将离开电脑。本文不存在需要执行器再次询问的例行权限或产品选择。若执行器实时合同把某个已授权动作变成人类必审且 Auto-review/Full Access 均不可用，先完成全部本地安全工作；只有按实时 Goal 规则确已满足 blocker 条件时才标记 blocked，禁止循环请求用户。

## Goal Contract

- 第一动作读取 `openai-docs`，从官方页面刷新 Sandbox、Auto-review、Agent approvals & security、Long-running work，记录 URL 与时间。官方参考：
  - `https://learn.chatgpt.com/docs/sandboxing`
  - `https://learn.chatgpt.com/docs/sandboxing/auto-review`
  - `https://learn.chatgpt.com/docs/agent-approvals-security`
  - `https://learn.chatgpt.com/docs/long-running-work`
- 检查执行器自己的 permission profile、writable roots、network、approval reviewer 和实际 Goal tool schema。Goal 不扩大权限；Auto-review 只更换审查者。
- 当前作者运行时 `get_goal({})` 返回无 active goal。首次执行且 `create_goal` 存在时，以本文顶部 **Goal** 的完整原文调用 `create_goal({objective})`；不得设置 token budget；不得把字面 `/goal` 当成工具。
- 恢复时先调用实际存在的 `get_goal`，不得重复创建 Goal；重读本文、Required Skills、Lessons、Progress Ledger、`git status --short` 和 9225 audit。
- 持续执行所有安全且已授权步骤。一个本地测试失败、一次网络超时、预算接近上限、部分平台成功都不是 blocker，也不是 complete。
- 同一失败最多执行两次：第一次获取 raw 完整证据并修根因；第二次仍失败则换用本文明确的安全 fallback。禁止第三次无新证据重复。
- 只有本文所有 acceptance 条件通过后，按执行器实时 schema 调用 `update_goal(status="complete")`。`blocked` 只按实时 tool instruction 使用，不复制旧阈值。

## Permission Feasibility

| 资源或副作用 | 权限需求 | 已验证路径 | 执行规则 |
| --- | --- | --- | --- |
| 仓库源文件、测试、计划 | workspace write | 当前根可写 | 用 `apply_patch`，不得覆盖无关改动。 |
| `/private/tmp` 证据与 task state | 临时写 | writable root | 文件名固定、0600、无秘密；不使用宽泛删除。 |
| Git metadata | 只读 | `.git` 受保护可读 | 可 status/diff/log，不 commit/reset/switch。 |
| Browser fleet audit | 进程/端口只读 | 作者通过精确 Auto-review 成功 | 使用 Skill 脚本；不输出原始进程命令行。 |
| 9225 CDP | localhost 网络和浏览器连接 | 作者通过精确 Auto-review 成功 | 必要时 `require_escalated`，理由精确到 9225 只读或已授权发布。 |
| Bilibili 登录态读取 | 敏感内部数据 | 现有代码读取且不打印 | stdout/stderr/diff/evidence 禁止 Cookie、Token、CSRF。 |
| Bilibili 外部定时投稿 | 已授权外部写入 | 用户明确授权一条 | 先 UID 双检和标题去重；不确定提交结果时先读回，禁止重发。 |
| GitHub/upstream | 非必需网络读取 | 本轮无需 fetch | 不 fetch、不 push，避免无关权限和漂移。 |
| 浏览器进程/Profile | 禁止变更 | audit 显示健康 | 不 start/stop/kill，不直接读 Profile DB。 |

## Current-State Evidence

- 当前 checkout：`/Users/yelin/Developer/agent-tools/social-auto-upload`，分支 `main`；origin 为用户 fork，upstream 为 `dreammis/social-auto-upload`。
- 工作树已有大量用户/前序实现改动，全部视为必须保留。已修改：`sau_cli.py`、五个测试文件、三个平台 uploader/runtime。已新增未跟踪：`utils/account_identity.py`、`utils/browser_selector.py`、`utils/direct_cdp.py`、对应测试、计划、CodeGraph/Understand Anything 产物、HTML、图片和二维码。不得 reset、checkout、clean 或重建工作树。
- 当前 diff 约 1423 additions / 53 deletions；前序工作已实现单 target 解析、三平台 identity、稳定 ID 闸门、Bilibili CDP→biliup、YouTube/抖音真实发布修复。
- `.codegraph` 2026-08-24 23:18 索引：100 files、1801 nodes、4561 edges、无 pending changes；`open_browser_session` 影响 72 个 symbol，因此兼容默认行为是硬要求。
- 当前 `.venv/bin/python -m unittest discover -s tests`：132 tests，全部 `OK`；`compileall` 和 `git diff --check` 通过。
- 9225 audit：`SAU-自媒体运营-9225`，端口 9225，PID 49375，Profile `/Users/yelin/Desktop/ManagedBrowsers/active/SAU-自媒体运营-9225--9225/profile`，`running`、`health=ok`、`problems=[]`。
- 受保护浏览器：个人 Chrome PID 610；`AgentPool-共享主浏览器-9223` PID 21881；`热点监控-9224` PID 25773。
- 9225 当前 Bilibili nav API 只读实测：`isLogin=true`，MID `526557505`，uname `Stella英语听力磨耳朵`。这只是执行前事实；真实投稿前必须重新读取，MID 不一致立即阻止。
- 9225 执行前共有 44 个页面：Douyin 16、Bilibili 17、YouTube 11。不得根据域名猜测并批量关闭；所有页面 ID 都是 baseline protected pages。
- `/private/tmp/sau-e2e-20260829` 已有 12 秒 H.264/AAC 测试视频、Bilibili/YouTube 封面、Douyin 横竖封面、narration。
- 已存在一条 YouTube 定时测试：video ID `9_OuM_Vi_QE`，标题 `SAU REAL UPLOAD TEST · DELETE AFTER TEST · 2026-08-29 · YOUTUBE`；还有一份未提交 draft。禁止再次投稿或删除。
- 已存在一条 Douyin 定时测试，正文含 marker `SAU-REAL-UPLOAD-TEST-20260829-2000`，状态 `定时发布中`，时间 `2026年08月29日 20:00`。禁止再次投稿或删除。
- Bilibili 还没有本计划要求的真实测试投稿；本计划只允许这一平台一次最终提交。
- biliup binary：`/Users/yelin/.social-auto-upload/tools/biliup/macos-aarch64/biliup`，v1.2.2；已核验 `upload` 支持 `--title`、`--desc`、`--tid`、`--tag`、`--cover`、`--dtime`。

## Requirement Traceability

| Requirement | Source | Implemented by | Verified by |
| --- | --- | --- | --- |
| 复用现有公共层，不另造框架 | 用户确认 + Ponytail | Tasks 2–6 | File scope、无新依赖、raw diff |
| 名称/端口/CDP/数组输入 | 用户需求 | Task 3 | selector 与 CLI tests、live scan |
| 账号盘点与唯一路由 | 用户需求 | Task 3 | scan matrix、0/1/多命中 tests |
| 登录闭环和错误区分 | 用户需求 | Task 3、5 | `logged_in`/`interaction_required`/`error` tests |
| 发布前稳定 ID 双检 | 用户需求 | Task 5 | 三平台 mismatch tests |
| 后台优先、前台一次兜底 | 用户确认 | Task 2、5 | CDP background contract test、live result flag |
| 成功全关、失败留一、旧页不动 | 用户确认 | Task 2、7 | page ownership tests、live page ID equality |
| 批量单项隔离 | 用户需求 | Task 4 | manifest tests、结果数组 |
| 浏览器互斥与 task ID 防重复 | 用户需求 | Task 4 | lock/receipt tests、重复 batch replay |
| Bilibili 9225 真实定时投稿 | 用户确认 | Task 8 | UID、exactly-one、aid、dtime、cover 读回 |
| 不依赖 Browser Harness | 用户确认 | Tasks 3–8 | import/command scan、SAU 自身 E2E |

## File Map

| Action | Absolute path | Responsibility | Consumed by |
| --- | --- | --- | --- |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/utils/browser_runtime.py` | `BrowserSession` 页面 ownership、后台新页、确定性 close、端口锁与 task receipt | 三平台 uploader、CLI batch |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/utils/direct_cdp.py` | direct CDP 创建 background target，并只回收自己创建的 target | 三平台 identity fallback |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/utils/browser_selector.py` | 复用单 target resolver，增加有序去重的 target 数组解析 | CLI scan/router |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/utils/account_identity.py` | 账号 selector 精确匹配和无秘密结构化状态 helper | CLI scan/router |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/sau_cli.py` | accounts scan、browser pool、target account、batch manifest、task ID、结构化结果 | `sau` CLI |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/uploader/youtube_uploader/main.py` | 使用 owned task page、finally cleanup、结果标记 | YouTube identity/upload |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/uploader/douyin_uploader/main.py` | 使用 owned task page、finally cleanup、确定性发布读回结果 | Douyin identity/upload |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/uploader/bilibili_uploader/runtime.py` | 只读 Bilibili identity、export 复用、exact-title 投稿读回 | Bilibili CLI/router/E2E |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_browser_runtime_cdp.py` | background、fallback、ownership、success/failure close、lock | Task 2/4 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_direct_cdp.py` | existing target 不关、created target 后台且回收 | Task 2 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_sau_browser_cli.py` | pool flags、互斥、target 数组和 scan dispatch | Task 3 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_account_identity.py` | stable ID/handle/name 精确匹配与 secret safety | Task 3 |
| Create | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_sau_batch.py` | batch schema、顺序隔离、task receipt、防重复 | Task 4 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_bilibili_runtime.py` | read-only identity、export UID 一致、archive readback | Task 5/8 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_sau_bilibili_cli.py` | target account、task ID、schedule timezone、JSON result | Task 5/8 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_sau_douyin_cli.py` | cleanup/result/interaction 状态 | Task 5 |
| Modify | `/Users/yelin/Developer/agent-tools/social-auto-upload/tests/test_youtube_schedule.py` | cleanup/result/background flag | Task 5 |

## Interface Contracts

### BrowserSession

Location: `/Users/yelin/Developer/agent-tools/social-auto-upload/utils/browser_runtime.py`, existing `BrowserSession` and `open_browser_session`.

- Preserve every existing `open_browser_session` argument and default.
- Extend `BrowserSession` with:
  - `initial_pages`: 执行前捕获的不可变 `Page` 元组
  - `connected_over_cdp: bool`
  - `focus_fallback_used: bool = False`
- `async new_task_page() -> Page`:
  - For reused CDP persistent context, first use `browser.new_browser_cdp_session()` and `Target.createTarget` with `url="about:blank"` and `background=True` while awaiting `context.expect_page()`.
  - If that single attempt fails, close the target by returned target ID when available, call `context.new_page()` once, and set `focus_fallback_used=True`.
  - For locally launched or dedicated contexts, use `context.new_page()`; this is not reported as a focus fallback because there is no shared visible user context.
- `async close(*, success: bool = True) -> None`:
  - Compute open pages currently in `context.pages` whose object identity was absent from `initial_pages`.
  - `success=True`: close every such page.
  - `success=False`: close all such pages except the last open one.
  - Never close a page from `initial_pages`.
  - Then preserve current context/browser close semantics: close context only when `should_close_context=True`; `browser.close()` on CDP only disconnects Patchright.
  - Page-close failures are collected as warnings but must not prevent disconnect; never swallow the original upload exception.

### Direct CDP target ownership

Location: `/Users/yelin/Developer/agent-tools/social-auto-upload/utils/direct_cdp.py`.

- `_target_for_url(cdp_url, target_url) -> tuple[dict[str, Any], bool]`; the boolean is `created_by_call`.
- Exact URL target is reused with `created_by_call=False` and must never be closed.
- New target uses `Target.createTarget` with `background=True`; after `evaluate_cdp` completes or raises, call `Target.closeTarget` only when `created_by_call=True`.
- Never navigate a different same-domain user tab. Preserve existing regression.

### Browser pool

Location: `/Users/yelin/Developer/agent-tools/social-auto-upload/utils/browser_selector.py`.

```python
def resolve_browser_targets(
    selectors: Sequence[str] | None,
    legacy_cdp_url: str | None = None,
) -> list[BrowserTarget]:
```

- Reuse `resolve_browser_target` for every selector; no duplicate fleet calls implementation is required beyond this helper.
- Preserve order; deduplicate by port; if the same port resolves to conflicting names/URLs, raise `RuntimeError`.
- Empty selectors with one legacy URL returns zero or one target exactly as current behavior.
- Remote CDP remains rejected.

### Account matching and observation status

Location: `/Users/yelin/Developer/agent-tools/social-auto-upload/utils/account_identity.py`.

```python
def identity_matches(identity: AccountIdentity, selector: str) -> bool:
```

- Stable ID exact match has priority.
- Handle matches case-insensitively after stripping one leading `@` from both values.
- Display name matches case-insensitively after surrounding whitespace trim.
- No substring, fuzzy, similarity or transliteration matching.
- Empty selector is invalid.
- Scan item schema is a plain JSON dict, not a new class:

```json
{
  "status": "logged_in",
  "platform": "bilibili",
  "browser_name": "SAU-自媒体运营-9225",
  "cdp_port": 9225,
  "identity": {},
  "reason": null
}
```

- Allowed status values: `logged_in`, `interaction_required`, `error`.
- A successfully parsed but logged-out identity maps to `interaction_required` with `reason="login_required"`.
- Transport/parser exceptions map to `error` and retain a sanitized message; they must not map to logged out.

### CLI contracts

- Preserve existing single-browser commands unchanged.
- `add_runtime_flags` adds `--browsers`, a comma-separated browser name/port list. Runtime rejects any simultaneous nonempty combination among `--browser`, `--browsers`, and `--cdp-url`, including environment-derived defaults.
- A-platform upload commands add `--target-account` and `--task-id`.
- Multiple candidates require `--target-account`; exactly one identity must match. Zero or multiple matches block before media upload.
- New command:

```text
sau accounts scan --browsers 9225,9226 --platforms douyin,youtube,bilibili
```

- `accounts scan` supports only the three named platforms, scans candidates sequentially, prints one JSON object with `items` and `summary`, and exits 0 when at least one scan completed; individual logged-out/error items do not abort other scans.
- New command:

```text
sau batch --file /private/tmp/sau-batch.json
```

- Manifest schema is exact:

```json
{
  "tasks": [
    {
      "id": "bili-20260829-2000",
      "argv": ["bilibili", "identity", "--account", "sau9225", "--browser", "9225"]
    }
  ]
}
```

- `id` must match `[A-Za-z0-9._-]{1,128}` and be unique; `argv` is a nonempty list of strings; nested `batch` is rejected; unknown keys are rejected.
- Batch executes sequentially. It captures each task outcome, continues after a single failure, and prints one final JSON summary. It never automatically retries an item.

### Browser lock and task receipt

Location: `/Users/yelin/Developer/agent-tools/social-auto-upload/utils/browser_runtime.py`.

- 精确公开调用面为：同步上下文管理器 `browser_task_lock(port: int)`、返回任务状态字典的 `begin_task(task_id: str, argv: Sequence[str])`、以及无返回值的 `finish_task(task_id: str, result: dict[str, Any])`。三者直接放入现有 `browser_runtime.py`，不要再创建类、repository、manager 或 service 包装层。
- State root: environment `SAU_TASK_STATE_DIR` when set, otherwise `/private/tmp/social-auto-upload-task-state`.
- Lock file: `browser-PORT.lock`, created atomically with `os.open(O_CREAT | O_EXCL | O_WRONLY, 0o600)`, containing only PID.
- Existing live PID means `RuntimeError("browser PORT is already in use by another SAU task")`.
- Existing invalid/dead PID lock may be unlinked once, then acquisition retried once. Never use glob or recursive deletion.
- Receipt file: `TASK_ID.json`, written atomically with mode 0600; contains task ID, SHA-256 of canonical argv JSON, state, timestamps, and sanitized result. No Cookie/Token/CSRF.
- Existing `complete` receipt with same argv hash returns `skipped_duplicate` and the stored result without re-execution.
- Existing `started`/`uncertain` receipt with same hash returns `uncertain` and never re-executes.
- Same task ID with different argv hash is rejected.
- On ordinary pre-submit validation failure, state is `failed`; batch does not retry automatically. On timeout or process interruption where submission cannot be disproved, state is `uncertain`.

### Platform result

Every A-platform upload returns or prints a JSON-serializable dict containing:

```json
{
  "status": "success",
  "platform": "bilibili",
  "browser_name": "SAU-自媒体运营-9225",
  "cdp_port": 9225,
  "stable_id": "526557505",
  "submitted": true,
  "work_id": "123456",
  "url": "",
  "scheduled_at": "2026-08-29T20:00:00+08:00",
  "focus_fallback_used": false,
  "message": "scheduled upload verified"
}
```

- `work_id`/`url` may be empty only when the platform cannot expose it after bounded readback; Bilibili real acceptance requires numeric aid.
- Success is set only after deterministic platform result/readback. Exception paths never print a success line.

## Progress Ledger

| Task | Status | Completion evidence |
| --- | --- | --- |
| Task 1 | pending | — |
| Task 2 | pending | — |
| Task 3 | pending | — |
| Task 4 | pending | — |
| Task 5 | pending | — |
| Task 6 | pending | — |
| Task 7 | pending | — |
| Task 8 | pending | — |
| Task 9 | pending | — |

## Tasks

### Task 1: 启动门、Goal 和不可破坏基线

**Purpose:** 确认执行环境仍支持无监督工作，并固定脏树、浏览器和测试基线。
**Prerequisites:** 无。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** safe read-only，只有 Goal 创建会改变 Codex 任务状态。

**Required Skills:** 依次读取本文 Required Skills 的四个 `SKILL.md` 和存在的 Lessons。

- [ ] **Step 1.1: 刷新 OpenAI 合同并创建或恢复 Goal**
  - Run from: `/Users/yelin/Developer/agent-tools/social-auto-upload`
  - Action: 打开 Goal Contract 的四个官方 URL，记录检索时间；检查实时 permission profile 和 Goal schemas；`get_goal` 无目标时用本文 Goal 原文 `create_goal`，有目标时恢复而不重复创建。
  - Expected result: Goal active；未设置 token budget；没有字面 `/goal` 工具调用。
  - If it fails: 不开始代码；重新读取实时工具 schema 一次。仍无 Goal 工具时可以继续同一任务，但在 Ledger 记录“Goal tool unavailable”；不得伪造 Goal。
  - Evidence: 更新 Task 1 Ledger。

- [ ] **Step 1.2: 固定仓库和测试基线**
  - Commands:
    - `RTK_DISABLED=1 git status --short`
    - `codegraph status "/Users/yelin/Developer/agent-tools/social-auto-upload" --json`
    - `rtk .venv/bin/python -m unittest discover -s tests`
    - `rtk git diff --check`
  - Expected result: 现有脏文件仍在；CodeGraph 可用；132 tests 或更多全部 OK；diff check exit 0。
  - If it fails: 测试失败用 `rtk proxy .venv/bin/python -m unittest discover -s tests -v` 获取完整输出；只记录基线，不先改无关失败。若失败属于当前改动相关路径，Task 2 前修根因并留下测试证据。
  - Rollback: 无。

- [ ] **Step 1.3: 审计 9225 和保护页面 baseline**
  - Command: `python3 "/Users/yelin/.codex/skills/browser-fleet-manager/scripts/browser_fleet.py" audit`
  - Verify: 只接受 `SAU-自媒体运营-9225`/9225/running/ok/problems=[]/固定 Profile；任何锚点冲突立即停止浏览器操作，不自动修复。
  - Action: 通过 `http://127.0.0.1:9225/json/list` 只保存 page target IDs 到 `/private/tmp/sau-e2e-20260829/preexisting-page-ids.json`，不得保存 URL、标题、WebSocket URL。
  - Expected result: 当前约 44 IDs；文件只含 JSON 字符串数组。
  - If it fails: 精确 Auto-review 升级一次；失败后完成所有纯本地任务，但真实浏览器任务等待 live contract 恢复。

- [ ] **Task 1 acceptance**
  - Goal active or unavailable reason recorded；baseline tests green；9225 anchors healthy；protected page IDs saved；未修改代码。

### Task 2: 补齐现有 BrowserSession 的后台页和页面 ownership

**Purpose:** 在所有相关调用者共享的根路径解决抢焦点和标签页泄漏，不在三个 uploader 分别复制清理代码。
**Prerequisites:** Task 1 complete。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** reversible code mutation。

**Files:** `utils/browser_runtime.py`、`utils/direct_cdp.py`、`tests/test_browser_runtime_cdp.py`、`tests/test_direct_cdp.py`。

- [ ] **Step 2.1: 先写最小回归测试**
  - Add tests proving:
    1. CDP reused context records initial pages.
    2. `new_task_page` sends `Target.createTarget` with `background=True`.
    3. One CDP failure falls back to `context.new_page()` and sets the flag.
    4. `close(success=True)` closes all new pages and no initial page.
    5. `close(success=False)` leaves only the last new page and no initial page is closed.
    6. Existing exact direct-CDP target is never closed.
    7. Created direct-CDP target is background and closed on success or exception.
  - Command: `rtk .venv/bin/python -m unittest tests.test_browser_runtime_cdp tests.test_direct_cdp`
  - Expected result before implementation: new tests fail for missing behavior, existing tests remain green.
  - If it fails for fixture mistakes: correct mocks to match Patchright 1.58.2 API; do not weaken assertions.

- [ ] **Step 2.2: Implement BrowserSession contract**
  - Action: implement exactly the Interface Contract, preserve old `session.close()` callers by keeping `success=True` default, populate `initial_pages` and `connected_over_cdp` in every `open_browser_session` return.
  - Required local API facts already verified: `Browser.new_browser_cdp_session` and `BrowserContext.expect_page` exist.
  - Do not add a base uploader, context manager framework or dependency.
  - Verify command: `rtk .venv/bin/python -m unittest tests.test_browser_runtime_cdp`
  - Success means: all tests pass and every existing caller can still call `session.close()` without argument.
  - If background target event times out: close returned target ID when known, set fallback flag, create one normal page; no retry loop.

- [ ] **Step 2.3: Implement direct-CDP ownership**
  - Action: return `(target, created_by_call)`, pass `background=True`, and close only a created target in `evaluate_cdp` finally.
  - Verify command: `rtk .venv/bin/python -m unittest tests.test_direct_cdp`
  - Success means: same-site user tab regression remains green; no target leak in mocks.

- [ ] **Task 2 acceptance**
  - Run: `rtk .venv/bin/python -m unittest tests.test_browser_runtime_cdp tests.test_direct_cdp tests.test_youtube_schedule tests.test_sau_douyin_cli tests.test_bilibili_runtime`
  - Pass criteria: exit 0；no existing test disabled；raw diff touches only Step 2 files。

### Task 3: 扩展现有 selector/identity 为账号盘点和唯一路由

**Purpose:** 一个浏览器、多个浏览器都从同一 resolver 和 identity contract 进入，不复制端口解析或平台 ID 逻辑。
**Prerequisites:** Task 2 complete。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** reversible code mutation。

**Files:** `utils/browser_selector.py`、`utils/account_identity.py`、`sau_cli.py`、`uploader/bilibili_uploader/runtime.py`、对应 tests。

- [ ] **Step 3.1: Add pool and matching tests**
  - Cover comma-separated names/ports, order preservation, duplicate port removal, conflicting anchor rejection, runtime mutual exclusion, stable ID/handle/name exact matching, fuzzy/substring rejection.
  - Add `accounts scan` tests with mocked three platform identity readers: logged in, logged out, parser error; assert one item does not abort others.
  - Commands:
    - `rtk .venv/bin/python -m unittest tests.test_sau_browser_cli tests.test_account_identity`
  - Expected before implementation: new tests fail only for missing symbols/commands.

- [ ] **Step 3.2: Add read-only Bilibili identity**
  - Add `async get_bilibili_cdp_identity(cdp_url: str, target=None) -> AccountIdentity` by extracting the existing nav/DOM identity portion from `export_bilibili_cdp_account`.
  - It must not read all cookies, exchange TV tokens or write an account file.
  - `export_bilibili_cdp_account` must call the shared read-only identity logic, then perform cookie exchange and assert the exported MID equals the observed stable ID.
  - Logged-out nav returns `AccountIdentity(logged_in=False, stable_id=None)`; nav transport/parser exception raises `RuntimeError`.
  - Tests must prove cached visible DOM cannot override `isLogin=false`, and no secret appears.

- [ ] **Step 3.3: Add accounts scan and target router**
  - Implement the CLI contracts exactly.
  - Scan platforms sequentially and browsers sequentially; no `asyncio.gather` because visible shared contexts and tab ownership are not concurrency-safe.
  - Router uses the same scan readers and `identity_matches`; multiple targets without `--target-account` fail before upload; one unique match becomes the single existing `BrowserTarget` passed downstream.
  - Preserve current single `identity` stdout contract when only `--browser`/`--cdp-url` is used.
  - Commands:
    - `rtk .venv/bin/python -m unittest tests.test_sau_browser_cli tests.test_account_identity tests.test_bilibili_runtime tests.test_sau_bilibili_cli`
  - Expected result: all pass; no new dependency or second selector module.

- [ ] **Task 3 acceptance**
  - Run parser help and verify exact commands:
    - `.venv/bin/python sau_cli.py accounts scan --help`
    - `.venv/bin/python sau_cli.py bilibili upload-video --help`
  - Pass criteria: `--browsers`/`--target-account` visible where specified; legacy flags remain; invalid combinations exit 2 or controlled exit 1 without browser action.

### Task 4: 增加最小顺序 batch、端口锁和 task ID 防重复

**Purpose:** 让 Skill 可以把多个任务交给 SAU，同时防止同一浏览器竞争和超时重发。
**Prerequisites:** Task 3 complete。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** reversible code mutation and temporary local state。

**Files:** `utils/browser_runtime.py`、`sau_cli.py`、`tests/test_browser_runtime_cdp.py`、新建 `tests/test_sau_batch.py`。

- [ ] **Step 4.1: Write lock/receipt/batch tests**
  - Use `tempfile.TemporaryDirectory` and set `SAU_TASK_STATE_DIR` inside tests.
  - Cover live lock rejection, dead PID stale-lock one-time recovery, own-lock cleanup, task ID regex/path traversal rejection, argv hash conflict, complete duplicate skip, started/uncertain no rerun, sequential continuation after one failed child, nested batch rejection, no raw stderr secrets in result.
  - Command: `rtk .venv/bin/python -m unittest tests.test_browser_runtime_cdp tests.test_sau_batch`
  - Expected before implementation: missing-symbol failures only.

- [ ] **Step 4.2: Implement standard-library runtime state**
  - Implement Interface Contract using only `os`, `json`, `hashlib`, `tempfile`, `pathlib`, `contextlib`, `datetime`.
  - Atomic JSON write: `mkstemp` in state directory, `fchmod(0o600)`, JSON dump, flush, fsync, `os.replace`.
  - PID alive check may use `os.kill(pid, 0)`; `PermissionError` means alive; `ProcessLookupError` means dead.
  - Add one comment: `# ponytail: process-local file locks are enough for one Mac; use a lock service only if distributed workers are introduced.`

- [ ] **Step 4.3: Implement batch dispatcher**
  - Parse and validate manifest before executing any child.
  - Use current parser and `await dispatch(child_args)` in process; capture child stdout/stderr only long enough to produce a sanitized result. Never echo Cookie/Token/CSRF/Authorization values.
  - If a task argv has a browser port, hold `browser_task_lock(port)` around identity/routing/upload. For browser pools, acquire only the uniquely selected target before upload; scans lock one target at a time.
  - Do not parallelize.
  - Verify: `rtk .venv/bin/python -m unittest tests.test_sau_batch tests.test_sau_browser_cli`

- [ ] **Task 4 acceptance**
  - Create a temporary manifest containing two mocked/non-network identity tasks in a unit test; first fails, second succeeds; final summary reports both and process exits nonzero only when any item failed.
  - Replay identical complete task ID and prove dispatch mock call count does not increase.

### Task 5: 将三平台接入公共生命周期、结构化结果和双重身份闸门

**Purpose:** 公共能力必须真正被三个活跃平台消费；任务结果确定后才能清理页面。
**Prerequisites:** Tasks 2–4 complete。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** reversible code mutation。

**Files:** 三个平台 uploader/runtime、`sau_cli.py` 和对应 tests。

- [ ] **Step 5.1: YouTube wiring**
  - Replace task-owned `context.new_page()` with `session.new_task_page()` in `cookie_auth`、`get_youtube_account_identity`、`youtube_cookie_gen`、`YouTubeVideo.upload` where a `BrowserSession` exists.
  - Wrap each session in `success=False` plus `finally: await session.close(success=success)`; set success only after identity/readback/no-submit terminal result is known.
  - Remove early double `session.close()` calls.
  - Include `browser_name`、port、stable ID and `focus_fallback_used` in upload result without weakening existing schedule readback.
  - Test success closes all new pages; identity extraction failure keeps last; initial page untouched.

- [ ] **Step 5.2: Douyin wiring**
  - Change context identity helper to use the active `BrowserSession` for its task page and continue closing its temporary identity page when successful.
  - `DouYinVideo.upload` must use `session.new_task_page()` and a `try/finally` close contract.
  - After redirect to content manage, read a whitelisted deterministic result for the exact submitted title/marker: scheduled status/time when present, work href/ID when present. Return a dict; do not print full page text.
  - SMS verification becomes structured `interaction_required`; it must not enter retry loop or click publish.
  - Keep existing `locator.click(force=True)` final fallback because task completion is higher priority; do not replace with global JS click.

- [ ] **Step 5.3: Bilibili wiring**
  - Identity/credential page operations use session task pages and cleanup.
  - Before biliup subprocess: read 9225 identity, export credential, read credential identity, assert same stable ID, then immediately re-read 9225 identity and assert same again.
  - Convert naive CLI schedule to aware `Asia/Shanghai` before Unix timestamp; test expected epoch.
  - Add exact-title archive readback returning only `aid`、title、state、dtime、cover-present; count exact matches and reject more than one.
  - `upload_bilibili_video` returns structured result after bounded readback. Collection remains optional and must not block when not requested.

- [ ] **Step 5.4: CLI result and interaction behavior**
  - All three upload paths print JSON only after success. Error/interaction paths print sanitized JSON or stderr and nonzero exit; never print a submitted success line after exception.
  - `--target-account` must be rechecked inside platform uploader at final boundary, not only in CLI router.
  - Focused commands:
    - `rtk .venv/bin/python -m unittest tests.test_youtube_schedule tests.test_sau_douyin_cli tests.test_bilibili_runtime tests.test_sau_bilibili_cli tests.test_sau_browser_cli`

- [ ] **Task 5 acceptance**
  - Every platform has: identity mismatch block before final submit; success cleanup; failure cleanup; original page protection; structured result fixture.
  - No Browser Harness import or subprocess call in `sau_cli.py`、`utils`、three uploaders.

### Task 6: 全量自动化回归、CodeGraph 影响复核和安全审计

**Purpose:** 在连接真实账号和产生外部投稿前清除本地缺陷。
**Prerequisites:** Tasks 2–5 complete。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** safe tests and read-only audit；CodeGraph sync updates existing local index。

- [ ] **Step 6.1: Focused and full tests**
  - Commands:
    - `rtk .venv/bin/python -m unittest tests.test_browser_runtime_cdp tests.test_direct_cdp tests.test_account_identity tests.test_sau_batch tests.test_sau_browser_cli tests.test_sau_bilibili_cli tests.test_bilibili_runtime tests.test_sau_douyin_cli tests.test_youtube_schedule`
    - `rtk .venv/bin/python -m unittest discover -s tests`
    - `rtk .venv/bin/python -m compileall -q sau_cli.py uploader utils tests`
    - `rtk git diff --check`
  - Expected result: all exit 0；test count at least 132；no ResourceWarning/unawaited coroutine relevant to new code。
  - If same failure persists twice: raw `rtk proxy .venv/bin/python -m unittest MODULE -v` and CodeGraph callers/callees; fix shared root cause once.

- [ ] **Step 6.2: Security and scope audit**
  - Commands:
    - `RTK_DISABLED=1 git diff -- "sau_cli.py" "utils" "uploader/bilibili_uploader/runtime.py" "uploader/douyin_uploader/main.py" "uploader/youtube_uploader/main.py" "tests"`
    - `rtk rg -n "print\(.*(cookie|token|csrf|authorization)|logger.*(cookie|token|csrf|authorization)|T[B]D|TO[D]O|FIX[M]E|\.only\(|skip\(" "sau_cli.py" "utils" "uploader" "tests"`
  - Inspect raw diff because auth/cookies are security-sensitive.
  - Pass criteria: no secret values, no disabled tests, no placeholders, no dependency changes, no unrelated platform edits.

- [ ] **Step 6.3: Sync and query CodeGraph**
  - Commands:
    - `codegraph sync "/Users/yelin/Developer/agent-tools/social-auto-upload"`
    - `codegraph status "/Users/yelin/Developer/agent-tools/social-auto-upload" --json`
    - `codegraph impact "open_browser_session" --path "/Users/yelin/Developer/agent-tools/social-auto-upload" --json --depth 2`
    - `codegraph impact "resolve_browser_targets" --path "/Users/yelin/Developer/agent-tools/social-auto-upload" --json --depth 2`
  - Expected result: no mismatch/pending changes; high blast radius covered by full suite.

- [ ] **Task 6 acceptance**
  - Fresh full suite green；diff/scope/security clean；CodeGraph synced；Ledger lists exact test count and changed files。

### Task 7: 9225 无外部提交的 live 集成验收

**Purpose:** 在真实浏览器验证后台页、三平台账号矩阵、页面净零增长和路由，不发布新内容。
**Prerequisites:** Task 6 complete；9225 audit healthy。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** real logged-in browser read-only；task-created tabs may be closed under approved lifecycle。

- [ ] **Step 7.1: Snapshot current protected pages**
  - Save only current page target IDs as `/private/tmp/sau-e2e-20260829/task7-pages-before.json`.
  - Do not compare against Task 1 count as external user activity may add pages; Task 7 before/after within this task is authoritative.

- [ ] **Step 7.2: Run three-platform scan**
  - Command: `.venv/bin/python sau_cli.py accounts scan --browsers "9225" --platforms "douyin,youtube,bilibili"`
  - Expected:
    - browser name `SAU-自媒体运营-9225`, port 9225 for every item;
    - Bilibili `status=logged_in`, stable ID `526557505` at execution time;
    - YouTube/Douyin logged-in stable IDs match the preexisting account unless the live account genuinely changed;
    - `focus_fallback_used=false` for normal CDP background path.
  - If Bilibili reports `interaction_required`: do not use old credential file to bypass; retain one task page and finish other local tests. Because the author verified login before handoff, first inspect whether the error is parser/transport rather than asking user to login.
  - If status=`error`: capture sanitized traceback, fix extractor/transport, retry once.

- [ ] **Step 7.3: Verify cleanup and routing**
  - Snapshot page IDs immediately after scan.
  - Success condition: after IDs equal before IDs exactly; no preexisting ID disappeared and no task ID remains.
  - Run a routing-only identity command with `--browsers "9225" --target-account "526557505"` for Bilibili; it must select one target and leave page IDs unchanged after success.
  - Unit-test failure paths already prove retain-one; do not deliberately log out or corrupt the real profile.

- [ ] **Task 7 acceptance**
  - `accounts-scan.json` and before/after ID evidence saved without URLs/secrets；page delta zero；Bilibili correct UID；no external submission。

### Task 8: Bilibili 9225 一次真实定时投稿与 SAU 自读回

**Purpose:** 完成唯一尚未真实验收的平台闭环。
**Prerequisites:** Tasks 1–7 complete；当前时间早于 `2026-08-29 16:00 Asia/Shanghai`（biliup 要求延时大于四小时）；Bilibili UID 仍为 `526557505`；没有同标题投稿；full suite fresh green。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** 用户已明确授权的一次外部定时投稿。

**Fixed data:** account `sau9225`；browser `9225`；target account `526557505`；task ID `sau-bili-526557505-20260829-2000-v1`；video `/private/tmp/sau-e2e-20260829/test-video.mp4`；cover `/private/tmp/sau-e2e-20260829/bilibili-cover.png`；title `SAU REAL TEST 20260829 BILIBILI`；description `SAU-REAL-UPLOAD-TEST-20260829-2000 · DELETE AFTER TEST`；tags `SAU测试,自动化测试`；tid `249`；schedule `2026-08-29 20:00`。

- [ ] **Step 8.1: Time, media, identity and duplicate preflight**
  - Verify ffprobe duration 11.5–12.5 seconds, H.264 video stream, AAC audio stream; verify cover is a readable image.
  - Run Bilibili identity with browser 9225; require stable ID exactly `526557505`.
  - Call the new exact-title readback before upload. Zero matches is required. One match means a previous uncertain execution already submitted: do not run upload; validate it and treat as duplicate-safe recovered result. More than one match is failure evidence and no further submit.
  - Verify receipt: absent is normal; complete means use stored result; started/uncertain means read back first and never blindly run upload.

- [ ] **Step 8.2: Execute the one authorized upload**
  - Exact command:

```bash
.venv/bin/python sau_cli.py bilibili upload-video --account "sau9225" --file "/private/tmp/sau-e2e-20260829/test-video.mp4" --title "SAU REAL TEST 20260829 BILIBILI" --desc "SAU-REAL-UPLOAD-TEST-20260829-2000 · DELETE AFTER TEST" --tid 249 --tags "SAU测试,自动化测试" --thumbnail "/private/tmp/sau-e2e-20260829/bilibili-cover.png" --schedule "2026-08-29 20:00" --browser "9225" --target-account "526557505" --task-id "sau-bili-526557505-20260829-2000-v1"
```

  - Expected result: exit 0 and one sanitized JSON object; stable ID `526557505`; `submitted=true`; numeric aid; scheduled time `2026-08-29T20:00:00+08:00`; cover check true; exactly one title match.
  - If command times out or output connection drops: mark receipt uncertain, immediately run exact-title readback. If match exists, validate and finish; if no match exists, do not automatically resubmit in the same Goal turn. Recheck once after the existing bounded archive delay; only a proven pre-submit failure may use the same task ID retry path defined by code.
  - If Auto-review denies: do not use curl, browser JS, another binary or Browser Harness to bypass. Keep all local tasks complete and follow live Goal blocker rules.

- [ ] **Step 8.3: Read back and save evidence**
  - Use SAU runtime helper/CLI, not Browser Harness, to obtain exact-title matches.
  - Save `/private/tmp/sau-e2e-20260829/bilibili-final-evidence.json` containing only: browser name, port, stable ID, display name, title, marker, scheduled time, status/state, aid/bvid if available, cover-present boolean, submitted-once boolean, focus fallback flag.
  - Re-run exact-title count; require exactly one.
  - Snapshot pages; require every Step 8 task-created page closed after success and all Step 8 preexisting IDs preserved.
  - Do not delete the Bilibili投稿。

- [ ] **Task 8 acceptance**
  - Correct UID, one title match, numeric aid, correct dtime, cover present, one task receipt complete, no duplicate, no secret, no new persistent tab。

### Task 9: 最终验收、完整 diff 和 Goal completion

**Purpose:** 只有可重复公共能力和真实 Bilibili 结果都成立时才能交付。
**Prerequisites:** Tasks 1–8 complete。
**Working directory:** `/Users/yelin/Developer/agent-tools/social-auto-upload`
**Risk level:** safe read-only verification and Goal state update。

- [ ] **Step 9.1: Fresh Test Matrix**
  - Re-run every Test Matrix command below and record time、test count、exit code。
  - Any red required check means Task 9 remains pending；修根因后重新运行全部矩阵。

- [ ] **Step 9.2: Complete diff/scope/secrets review**
  - Commands:
    - `RTK_DISABLED=1 git status --short`
    - `RTK_DISABLED=1 git diff --stat`
    - `RTK_DISABLED=1 git diff`
    - `rtk git diff --check`
  - List every changed file and map it to File Map/Task。
  - Confirm original unrelated files remain；no branch/commit/push；no cookie/media/evidence in diff；no placeholder/debug/disabled tests。

- [ ] **Step 9.3: Verify requirement traceability and external state**
  - Every traceability row has passing evidence。
  - Existing YouTube ID `9_OuM_Vi_QE` and existing Douyin scheduled item were not resubmitted/deleted by this plan。
  - Bilibili exact title count is one；scheduled time/account/cover correct。
  - Future successful scan leaves zero net pages；failure unit tests leave one task page；preexisting page IDs protected。

- [ ] **Step 9.4: Complete Goal**
  - Update all Ledger rows with exact evidence。
  - Call live `update_goal(status="complete")` only now。
  - Final report in Chinese: outcome、changed files、tests/count、three platform identities、Bilibili aid/schedule、focus fallback flag、page cleanup result、residual fact that preexisting 44 pages were intentionally not closed。

## Test Matrix

| Layer | Requirement/risk | Preconditions | Exact command/procedure | Expected result | Failure evidence |
| --- | --- | --- | --- | --- | --- |
| Baseline | Preserve current work | `.venv` exists | `rtk .venv/bin/python -m unittest discover -s tests` | 132+ tests OK | raw `-v` output |
| Unit | Browser ownership/background | mocks | `rtk .venv/bin/python -m unittest tests.test_browser_runtime_cdp tests.test_direct_cdp` | background param、fallback、success/failure close all green | failing test name + traceback |
| Unit | Pool/account route | mocked fleet/identities | `rtk .venv/bin/python -m unittest tests.test_sau_browser_cli tests.test_account_identity` | one/zero/multiple paths deterministic | parser output + assertion |
| Unit | Lock/batch/idempotency | temp state dir | `rtk .venv/bin/python -m unittest tests.test_sau_batch` | sequential isolation、duplicate skip、uncertain no retry | receipt fixture and call count |
| Regression | Three platforms | mocked network/browser | `rtk .venv/bin/python -m unittest tests.test_youtube_schedule tests.test_sau_douyin_cli tests.test_bilibili_runtime tests.test_sau_bilibili_cli` | identity、schedule、cover、result、cleanup green | focused raw suite |
| Full | Whole repository | all unit changes done | `rtk .venv/bin/python -m unittest discover -s tests` | exit 0, count >=132 | raw full suite |
| Static | Syntax/import | source written | `rtk .venv/bin/python -m compileall -q sau_cli.py uploader utils tests` | exit 0 | compile error path |
| Scope | Patch integrity | dirty tree preserved | `rtk git diff --check` + raw diff | no whitespace error/unrelated edits | exact diff hunk |
| Security | Auth/secrets | raw inspection | secret scan in Task 6 | no values in output/diff/evidence | redacted filename/line only |
| Live integration | 9225 scan and pages | audit healthy | Task 7 commands | correct IDs, focus flag false, page delta zero | sanitized scan + ID arrays |
| E2E | Bilibili user outcome | correct UID/time/media | Task 8 exact command/readback | exactly one scheduled aid under UID 526557505 | sanitized evidence JSON |

## Failure Recovery and Autonomous Continuation

1. 每次自动续跑先调用 `get_goal`；重读本文、四个 Required Skills、Lessons 和 Progress Ledger。
2. 执行 `RTK_DISABLED=1 git status --short`，查看相关 raw diff；不得 reset/clean/checkout。
3. audit 9225；读取 `/private/tmp/social-auto-upload-task-state` 的固定 task receipt；读取 `/private/tmp/sau-e2e-20260829` 的脱敏证据；不得打印 Cookie 文件。
4. 从第一个未完成 Task 的第一个未完成 Step 开始。已经存在的文件/receipt/投稿先验证，禁止盲目重做。
5. 本地测试失败：第一次 raw traceback + CodeGraph callers/callees，修共享根因；第二次 raw 再验证；不做第三次相同尝试。
6. 9225 CDP PermissionError：使用精确 `require_escalated` 一次；Auto-review 拒绝后不得改用隐蔽网络/GUI/Browser Harness 绕过。
7. 页面后台创建失败：代码自动一次前台 fallback，并在结果标记；不得循环创建新页。
8. 登录过期：输出 `interaction_required`，不使用其他账号 Cookie、不猜扫码/验证码。保留最后一个任务页，其他本地任务继续。
9. Bilibili timeout/uncertain：先 exact-title readback；存在则恢复结果，不存在也不能盲重发。task receipt 防止重复。
10. Bilibili UID 与 `526557505` 不一致：硬阻止；这是错账号风险，不允许“任务优先”绕过。
11. 真实投稿时间已不足四小时：不得改成立即发布；记录时间前置条件失败并按实时 Goal blocker规则处理。
12. 任何不属于 File Map 的必要修改先证明是当前任务根因；否则跳过并记录，不扩大范围。

## Final Acceptance Gate

执行器必须逐项确认：

- 九个 Task 的 acceptance 全部通过并写入 Ledger。
- Test Matrix 全部 fresh green；不是引用旧结果。
- Bilibili UID、标题、aid、排期、封面、exactly-one 均有脱敏证据。
- `focus_fallback_used=false` 是正常 live 路径结果；若为 true，功能可交付但必须记录 Chrome 仍可能在兜底时抢一次焦点，不能伪称完全静默。
- 成功 live task 前后 page IDs 相等；原页面无丢失；失败路径 unit test 留最后一页。
- Batch replay 不重复调用 child；same task ID hash conflict 被拒绝。
- 无 Browser Harness 运行依赖、无新增依赖、无 secrets、无 placeholders、无 disabled tests、无生成垃圾进入 Git。
- 无 commit/push/branch/worktree/PR/release/deploy；无平台删除或第二次投稿。
- 没有待执行的人类审批动作。
- 只有此时才能 `update_goal(status="complete")`。
