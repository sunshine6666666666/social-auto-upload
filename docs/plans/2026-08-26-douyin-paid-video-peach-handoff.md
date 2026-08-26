# 抖音付费视频与 Peach 任务衔接：独立 Worktree 无监督实施计划

> 执行对象：能力较弱、无人工值守的代码模型
> 计划日期：2026-08-26（Asia/Shanghai）
> 源仓库：`/Users/yelin/Developer/agent-tools/social-auto-upload`
> 只读参考仓库：`/Users/yelin/Developer/linye-english-news-workflow`
> 真实测试浏览器：Browser Fleet 中的 `SAU-自媒体运营-9225`（CDP 端口 `9225`）
> 真实测试视频：`/Users/yelin/Desktop/自媒体测试/“疫苗制造商”英文怎么表达？_extended_video_2026-08-24T08-49-25-826Z.mp4`

## 1. 最终目标

在 **不触碰正在使用的 main 工作区** 的前提下，为 SAU 现有抖音上传链路增加以下最小闭环：

1. 接收并严格校验 Peach 抖音付费视频字段。
2. 在抖音创作者中心真实打开并设置付费视频相关控件。
3. 设置后从页面回读两次，只有两次结果均与请求完全一致才判定“配置完成”。
4. 保留现有账号核验、浏览器互斥锁、任务回执、后台标签页和成功关闭页面的机制，不重复实现。
5. 增加安全的 `--no-submit` 预提交模式：真实上传视频、真实设置并回读付费选项，但绝不点击最终发布按钮。
6. 使用端口 9225 和指定视频完成一次真实、高强度的预提交验收。
7. 同步更新本 Fork 的 `README.md`，不得把未完成、未验证或仅属于上游的能力写成已实现。

本计划 **不允许真实发布作品**，用户只授权了上传视频、打开和测试付费按钮。最终发布必须以后获得单独明确授权。

## 2. Ponytail 范围决定

只在原有抖音上传命令和 `DouYinVideo` 流程上加能力，不创建新的发布框架、插件系统、数据库、HTTP 服务、队列、锁系统或浏览器管理系统。

必须复用：

- `sau_cli.py` 中现有 `douyin upload-video` 命令、请求对象和调用链。
- `uploader/douyin_uploader/main.py` 中现有 `DouYinVideo.upload()`。
- `utils/browser_selector.py` 的浏览器名称/端口解析、注册表检查和按需启动。
- `utils/browser_runtime.py` 的任务锁、幂等任务和回执。
- `BrowserSession.new_task_page()` 的后台页面策略。
- `BrowserSession.close(success=True)` 的“成功全部关闭；失败只保留最后现场页”行为。
- 抖音现有的上传前、提交前两次账号核验。

计划内允许新增一个小型纯 Python 模块，集中处理付费字段解析和校验；这是非平凡的金钱/发布边界，必须有一个专门测试文件。不得增加第三方依赖。

## 3. 不可违反的安全边界

### 3.1 main 工作区是禁区

当前事实：

- main 工作区：`/Users/yelin/Developer/agent-tools/social-auto-upload`
- 当前分支：`main`
- 计划编写时 HEAD：`0b9e029cff2b94f23aef4b0f64beb1dc6a0425ad`
- 当前存在用户自有未提交改动：`M AGENTS.md`

除读取和创建 worktree 外，执行模型不得在这个目录进行任何开发操作。尤其禁止：

- 禁止 `git switch`、`git checkout`、`git merge`、`git rebase`、`git reset`。
- 禁止修改、暂存、还原、复制或提交 `AGENTS.md`。
- 禁止在 main 工作区运行会写入源码、依赖、缓存或测试产物的命令。
- 禁止把 worktree 的改动合并回 main。
- 禁止 commit、push、创建 PR、关闭 Issue；这些都不在本次授权内。

### 3.2 外部系统边界

- 英语工作流仓库 `/Users/yelin/Developer/linye-english-news-workflow` 永远只读，不得修改、提交或推送。
- 旧目录 `/Users/yelin/Developer/agent-tools/express` 不作为事实依据。
- 不得 claim、complete、fail 或更新 Peach staging 的真实任务。
- 不得点击抖音最终“发布”按钮，不得创建任何实际作品或定时作品。
- 不得操作个人 Chrome；只允许使用 Browser Fleet 登记的 `SAU-自媒体运营-9225`。
- 不得输出或落盘 Cookie、Token、手机号、完整账号 ID、二维码、页面原始 HTML 或未脱敏截图。
- 测试视频只可作为运行时输入，不得复制进仓库或提交。

### 3.3 权限与审批规则

执行模型启动后先检查自己的真实工具、沙箱和审批制度。计划编写时环境与执行时 OMI API 环境可能不同，不得假设权限相同。

官方说明：沙箱限制与命令审批是两个独立层次；命令越过当前沙箱边界时仍可能需要审批。参考：

- [Codex sandboxing](https://learn.chatgpt.com/docs/sandboxing)（2026-08-26 查阅）
- [Auto-review](https://learn.chatgpt.com/docs/sandboxing/auto-review)（2026-08-26 查阅）
- [Agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security)（2026-08-26 查阅）
- [Git worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)（2026-08-26 查阅）

允许的写入范围仅限：

- 新 worktree：`/Users/yelin/Developer/agent-tools/social-auto-upload-douyin-paid`
- `/tmp` 或系统临时目录中的脱敏测试产物

如果创建上述 worktree 需要审批，只能发起一次 **目标明确、范围精确** 的审批。若被拒绝或运行环境根本不允许创建 worktree，立即停止，报告 `BLOCKED_WORKTREE_PERMISSION`；绝不退而求其次在 main 工作区开发。

若运行环境暴露 Goal API，先读取其真实 schema，再创建目标；不得凭空使用 `/goal` 文本命令。目标内容应为：“在独立 worktree 中实现并验证 SAU 抖音付费视频预提交闭环，main 工作区保持不变”。只有所有验收门槛通过后才能标记 complete；权限不足只在重复确认确实无法继续后标记 blocked。

## 4. 启动时必须先做的环境核验

以下命令必须逐条执行。路径必须用双引号。普通命令优先使用 `rtk`；涉及完整状态、差异或安全判断时使用原始输出。

```bash
cd "/Users/yelin/Developer/agent-tools/social-auto-upload"
RTK_DISABLED=1 git status --short --branch
RTK_DISABLED=1 git rev-parse HEAD
RTK_DISABLED=1 git worktree list --porcelain
test ! -e "/Users/yelin/Developer/agent-tools/social-auto-upload-douyin-paid"
test -f "/Users/yelin/Desktop/自媒体测试/“疫苗制造商”英文怎么表达？_extended_video_2026-08-24T08-49-25-826Z.mp4"
ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 "/Users/yelin/Desktop/自媒体测试/“疫苗制造商”英文怎么表达？_extended_video_2026-08-24T08-49-25-826Z.mp4"
```

预期：

- 分支是 `main`。
- `AGENTS.md` 的用户改动仍存在，绝不修改。
- 指定 worktree 路径不存在。
- 测试视频约 48.5 秒、约 9.8 MB；允许实际数据有极小显示差异。

如果 HEAD 已变化，不要失败；记录新的 `MAIN_HEAD_BEFORE`，后续以它作为“不改变 main”的基准。如果 worktree 路径已经存在，先检查它是否正是本计划的分支和干净目录；不满足则停止并报告冲突，禁止删除未知目录。

## 5. 独立 Worktree 的唯一创建方式

在 main 工作区只执行下面这一条创建命令：

```bash
git worktree add -b codex/douyin-paid-video-peach-handoff "/Users/yelin/Developer/agent-tools/social-auto-upload-douyin-paid" main
```

如果分支已存在但 worktree 不存在，先只读核对该分支是否由本任务创建并指向当前 main。无法证明则停止，不能强删或复用未知分支。

创建后立刻执行：

```bash
cd "/Users/yelin/Developer/agent-tools/social-auto-upload-douyin-paid"
RTK_DISABLED=1 git status --short --branch
RTK_DISABLED=1 git rev-parse --show-toplevel
RTK_DISABLED=1 git branch --show-current
```

必须同时满足：

- 顶层目录是新 worktree 路径。
- 分支是 `codex/douyin-paid-video-peach-handoff`。
- worktree 初始干净。

从这一刻开始，所有修改、安装、测试、CodeGraph 操作都在新 worktree 中完成。

## 6. 已知代码与业务契约

### 6.1 SAU 当前代码落点

- `sau_cli.py`
  - `DouyinVideoUploadRequest`：抖音 CLI 到上传器的请求载体。
  - `upload_video()`：检查环境并构造 `DouYinVideo`。
  - `douyin upload-video` 参数定义与 dispatch：目前没有付费参数，也没有抖音 `--no-submit`。
- `uploader/douyin_uploader/main.py`
  - `DouYinVideo`：上传任务对象。
  - `DouYinVideo.upload()`：上传、标题/标签、商品、封面、声明、合集、定时、最终账号核验、发布和结果等待。
  - 商品链接/商品标题属于购物车能力，**不是付费视频**，严禁借用。
- `utils/browser_selector.py`：浏览器名称、端口、CDP URL、注册表和自动启动。
- `utils/browser_runtime.py`：浏览器任务互斥、任务幂等和回执。
- `tests/test_sau_douyin_cli.py`：抖音 CLI 和上传流程现有测试。
- `tests/test_sau_browser_cli.py`：浏览器路由和账号识别测试。
- `tests/test_sau_batch.py`：锁、幂等和批处理测试。
- `README.md`：本 Fork 的真实能力说明，任何行为变更必须同步更新。

### 6.2 Peach 抖音付费字段

只读参考仓库中，抖音目标位于：

```text
publishTargets[].platform == "douyin"
publishTargets[].accountKey
publishTargets[].platformAccountId
publishTargets[].accountDisplayName
publishTargets[].settings.douyin.paidVideo
```

`paidVideo` 的字段为：

```text
enabled
saleModeText
priceModeText
priceYuan
productTitle
coverModeText
coverAssetRef
trialEnabled
trialStartSec
trialEndSec
marketingManaged
subtitleModeText
agreementConfirmed
collectionId
```

严格规则：

- `enabled`：布尔值。
- `saleModeText`：只允许 `单点售卖`、`组合售卖`。
- `priceModeText`：只允许 `付费视频`、`付费视频（会员免费看）`、`会员视频`。
- `priceYuan`：1–1000 元，最多两位小数；内部使用 `decimal.Decimal`，不得使用浮点比较金额。
- `productTitle`：去除首尾空白后非空，最多 28 个 Unicode 字符。
- `coverModeText`：只允许 `当前封面`、`更改封面`。
- `coverModeText == "更改封面"` 时 `coverAssetRef` 必须指向存在的本地图片；使用当前封面时必须为 `null` 或空值。
- `trialEnabled == true` 时：`trialStartSec >= 0`、`trialEndSec > trialStartSec`、时长至少 10 秒、`trialEndSec <= 视频总时长 / 2`。
- `marketingManaged`：布尔值。
- `subtitleModeText`：第一版只允许已核实的 `使用成片内已有双语字幕`，不要猜测其他文案。
- `agreementConfirmed`：付费开启时必须为 `true`，否则在打开浏览器前失败。
- `collectionId`：第一版必须为 `null`；付费视频与合集同时请求时立即失败，不做猜测。
- `enabled == false` 时不操作任何付费 UI；仍可校验字段类型，但不能凭默认值偷偷开启。
- 任何未知枚举、缺失必填字段或回读不一致，都必须 fail closed，不能继续最终提交。

### 6.3 账号安全

- 必须沿用现有 `--target-account` 和现有两次账号核验。
- Peach 的 `platformAccountId` 若被提供，必须作为目标账号 ID 传入并与 9225 当前抖音稳定 ID 精确比较。
- 零命中、多命中、账号 ID 不一致或中途切换均阻止任务。
- 日志和最终报告只输出 `logged_in=true/false`、`has_stable_id=true/false`、`account_match=true/false`，不得输出完整 ID。

### 6.4 已知外部限制

Peach 当前平台级回执不能完整表达“同一平台多个账号部分成功”。本计划只要求 SAU 输出逐账号结构化结果并阻止错账号；不得声称 SAU 单仓库已经修复 Peach UI/后端的部分成功状态。需要以后修改 Peach 时再单独立项。

## 7. 文件级最小改动清单

预计只改以下文件：

1. `uploader/douyin_uploader/paid_video.py`（新增）
   - 一个 `@dataclass(frozen=True, slots=True)` 的 `DouyinPaidVideoSettings`。
   - 使用标准库 `json`、`decimal.Decimal`、`pathlib.Path` 完成解析、严格校验和规范化快照。
   - 一个从 Peach 单个 `publishTarget` 提取付费配置和目标账号的纯函数。
2. `uploader/douyin_uploader/main.py`
   - 给 `DouYinVideo` 增加可选付费配置和 `submit: bool = True`。
   - 在现有上传链路中增加“设置付费 UI → 回读两次 → 比较”的最小步骤。
   - `submit=False` 时在最终账号核验后返回 `prepared`，不点击发布。
3. `sau_cli.py`
   - 给 `douyin upload-video` 增加 `--paid-target-config <JSON文件>` 和 `--no-submit`。
   - 读取 JSON，调用纯解析器，传入现有请求和上传器。
   - `--no-submit` 与 `--schedule` 互斥，避免产生含糊的定时预览行为。
4. `tests/test_sau_douyin_paid_video.py`（新增）
   - 一个小型、集中测试文件覆盖金钱、账号、UI 回读和 no-submit 安全边界。
5. `README.md`
   - 写清楚新参数、Peach JSON 形状、严格校验、账号阻断、no-submit 行为和当前限制。

如实现能在更少文件内保持职责清楚，可以减少文件；不得增加上述清单以外的生产模块，除非现有真实结构证明不可行，并在最终报告逐项说明原因。

## 8. 十步执行计划

### 步骤 1：建立隔离环境并记录基线

1. 按第 4、5 节创建 worktree。
2. 在新 worktree 中读取完整 `AGENTS.md`。
3. 运行 CodeGraph：先 `status`，必要时 `sync`；再查询 `DouYinVideo.upload`、`DouyinVideoUploadRequest`、浏览器锁和账号识别的 callers/callees/impact。CodeGraph 已存在时优先使用，不要先广泛翻文件。
4. 只读取第 6.1 节列出的相关代码和测试。
5. 建立新 worktree 自己的虚拟环境，不得链接或修改 main 的 `.venv`：

```bash
cd "/Users/yelin/Developer/agent-tools/social-auto-upload-douyin-paid"
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -e .
rtk .venv/bin/python -m unittest discover -s tests
```

基线必须全绿。若基线失败，原样保存失败摘要并判断是否与环境安装有关；不得在不知道原因时改业务代码“修测试”。

### 步骤 2：先写严格的纯字段解析器

在 `uploader/douyin_uploader/paid_video.py` 实现：

- `DouyinPaidVideoSettings.from_dict(data, video_duration_sec, base_dir=None)`。
- `DouyinPaidVideoSettings.to_snapshot()`：输出只含规范化、可安全比较的字段；金额以固定十进制字符串表达。
- `parse_peach_douyin_target(target, video_duration_sec, base_dir=None)`：
  - 要求 `platform == "douyin"`。
  - 读取 `platformAccountId`。
  - 精确读取 `settings.douyin.paidVideo`，不模糊猜字段。
  - 返回目标账号 ID 与设置对象。

先写测试再完成实现，至少覆盖：合法配置、未知枚举、浮点陷阱、价格上下界、标题长度、试看不足 10 秒、超过视频一半、未同意协议、付费与合集冲突、更换封面但资源不存在、错误平台、缺失账号 ID。

### 步骤 3：用真实页面发现控件，不靠猜测写选择器

先核对 Browser Fleet，不要把“在线状态”写回任何永久账本。使用 browser-fleet-manager 的只读审计确认：

- 名称为 `SAU-自媒体运营-9225`。
- 端口为 `9225`。
- Profile 位于 Browser Fleet 登记目录。
- 该端口身份锚点与名称、Profile 一致。

若浏览器停止，使用 Browser Fleet 的启动能力启动它；不得自行拼 Chrome 命令，不得创建新 Profile。

使用 Browser Harness 时必须遵守：

1. 通过 stdin/管道传脚本，当前 CLI 不支持 `-c`。
2. 第一次调用只能 `new_tab(url)` 或 `goto_url(url)` 后打印 `page_info()`。
3. 若 `page_info()` 返回 `domain_skill_files`，必须先逐个完整读取，再做下一步。
4. 正式技能目录：`/Users/yelin/Developer/agent-tools/browser-harness/agent-workspace/domain-skills/`。
5. 使用 `BU_NAME=SAU-自媒体运营-9225`、`BU_CDP_URL=http://127.0.0.1:9225`；不得连接个人浏览器。

先运行 SAU 脱敏身份命令，要求：退出码 0、已登录、有稳定 ID、目标账号精确匹配。不得在报告中打印 ID。

然后用指定视频进入抖音发布页，停留在最终提交之前，观察并记录以下控件的真实可访问名称、角色、层级和状态：

- 付费视频入口/开关。
- 售卖方式。
- 价格模式与金额。
- 商品标题。
- 当前封面/更改封面。
- 试看开关和起止时间。
- 平台营销管理开关。
- 字幕模式。
- 付费协议勾选框。

选择器优先级：稳定的 role/label/文本与弹窗作用域 > 稳定 data 属性 > 最小 CSS。禁止使用屏幕坐标、深层 `nth-child`、随机 class 或依赖当前标签页序号。只记录过滤后的控件信息；原始 DOM/截图只能放 `/tmp`，任务结束删除临时证据。

发现阶段不得点击最终发布。发现后清理本任务新开的标签页，保留浏览器原有标签页。

### 步骤 4：把配置贯穿现有 CLI 与请求对象

给现有命令增加：

```text
--paid-target-config /absolute/path/to/peach-douyin-target.json
--no-submit
```

契约：

- JSON 文件必须是 Peach 的单个 `publishTarget`，不能同时塞整个 job，也不能接受多种含糊形状。
- 解析后自动把 `platformAccountId` 作为最终目标账号；如果用户同时给 `--target-account`，两者必须完全相等，否则在浏览器启动前失败。
- `--no-submit` 将 `submit=False` 贯穿 `DouyinVideoUploadRequest`、`upload_video()` 和 `DouYinVideo`。
- `--no-submit` 与 `--schedule` 互斥，在 argparse 层给出清晰错误。
- 没有 `--paid-target-config` 时，原有免费发布行为完全不变。

不得新增第二套抖音命令或通用配置框架。

### 步骤 5：在原上传流程中设置并回读付费 UI

在 `DouYinVideo.upload()` 中选择已有且最接近最终提交的位置插入：

```text
上传视频并等待就绪
→ 填写标题/标签/现有选项
→ 设置付费视频 UI
→ 第一次回读
→ 等待约 1 秒让前端状态稳定
→ 第二次回读
→ 两次均与请求快照完全一致
→ 现有最终账号核验
→ submit=True 才允许点击发布；submit=False 返回 prepared
```

实现要求：

- 新增一个设置方法和一个回读方法即可，不创建页面对象框架。
- 所有付费控件都限定在付费区域或弹窗内，避免点到同名文字。
- 开关必须先读取当前状态，只在目标状态不同的时候点击，保证可重试。
- 文本框清空后填值，再读取实际值。
- 金额比较用规范化十进制字符串。
- 任何控件缺失、不可用、页面文案不在允许集合、第一次或第二次回读不一致，都抛出清晰异常，以 `blocked Douyin paid video:` 开头。
- 失败路径沿用现有页面保留策略：只保留最后一个现场页，其余关闭。
- 成功或 `prepared` 路径关闭本任务创建的所有页面，不动既有页面。
- 不得用 Browser Harness 代替 SAU 的生产上传逻辑；Browser Harness 只用于发现和交叉验证。

### 步骤 6：实现安全的 no-submit 结果

`submit=False` 时必须满足：

- 视频已经上传到发布表单。
- 付费配置已设置并稳定回读两次。
- 最终账号核验已经通过。
- 从未查找或点击最终发布按钮。
- 返回结构化结果：

```json
{
  "status": "prepared",
  "submitted": false,
  "account_match": true,
  "paid_video": {
    "requested": {},
    "observed": {},
    "verified": true
  }
}
```

真实结果可以保留现有公共字段，但不得包含完整账号 ID、Cookie、CDP 页面内容或本地 Profile 数据。

### 步骤 7：完成最小自动化测试集

在 `tests/test_sau_douyin_paid_video.py` 集中覆盖：

1. 第 2 步全部纯校验分支。
2. CLI 正确解析并传递 `--paid-target-config` 与 `--no-submit`。
3. config 账号与 `--target-account` 不一致时在浏览器调用前失败。
4. 不提供付费配置时旧行为不变。
5. 付费 UI 设置按实际状态幂等操作。
6. 两次回读完全一致时通过。
7. 任一次回读不一致时阻止。
8. `submit=False` 时发布按钮 mock 的点击次数严格为 0。
9. `submit=True` 但回读失败时发布按钮点击次数严格为 0。
10. `submit=True`、回读和账号复核均成功时才允许进入原有发布点击分支。
11. 成功/准备态关闭任务页；失败只保留最后现场页。
12. 账号 ID、Cookie 不出现在日志和结构化结果中。

运行：

```bash
rtk .venv/bin/python -m unittest tests.test_sau_douyin_paid_video
rtk .venv/bin/python -m unittest tests.test_sau_douyin_cli
rtk .venv/bin/python -m unittest tests.test_sau_browser_cli
rtk .venv/bin/python -m unittest tests.test_sau_batch
rtk .venv/bin/python -m unittest discover -s tests
```

同一失败用 RTK 输出排查两次仍不清楚，必须用 `rtk proxy ... -v` 或 `RTK_DISABLED=1` 重跑关键测试，不得盲改。

### 步骤 8：更新 README，但不扩大承诺

README 必须增加：

- `--paid-target-config` 的精确 JSON 示例，账号 ID 使用 `<DOUYIN_STABLE_ID>` 占位，禁止真实值。
- 字段允许值与严格校验规则。
- `--no-submit` 的含义和示例。
- 发布前两次账号核验、付费设置两次回读和 fail-closed 行为。
- Browser Fleet 名称/端口/CDP URL 均可通过现有浏览器选择器解析；示例使用 9225，但不硬编码为唯一端口。
- 当前限制：Peach 多账号部分成功状态仍需 Peach 上游配合；第一版字幕枚举仅支持已验证值；付费视频不支持合集。

不得写“已支持最终真实发布”，除非本计划允许并完成最终发布；本计划明确不允许，因此 README 只能说明生产代码具备提交路径、真实验收完成到预提交阶段。

### 步骤 9：使用 9225 做真实高强度预提交测试

先在 `/tmp` 创建一次性 JSON，不得放入仓库。内容使用下列值，其中 `platformAccountId` 必须由运行时已核验的 9225 当前抖音稳定 ID 注入；不得打印该值：

```json
{
  "platform": "douyin",
  "accountKey": "sau-9225-paid-test",
  "platformAccountId": "<运行时注入，不得记录>",
  "accountDisplayName": "SAU 9225 付费测试",
  "settings": {
    "douyin": {
      "paidVideo": {
        "enabled": true,
        "saleModeText": "单点售卖",
        "priceModeText": "付费视频",
        "priceYuan": "1.00",
        "productTitle": "SAU付费功能测试",
        "coverModeText": "当前封面",
        "coverAssetRef": null,
        "trialEnabled": true,
        "trialStartSec": 0,
        "trialEndSec": 15,
        "marketingManaged": false,
        "subtitleModeText": "使用成片内已有双语字幕",
        "agreementConfirmed": true,
        "collectionId": null
      }
    }
  }
}
```

运行现有 `sau` 命令的实际参数名必须以 `--help` 为准；核心等价命令为：

```bash
cd "/Users/yelin/Developer/agent-tools/social-auto-upload-douyin-paid"
.venv/bin/python sau_cli.py douyin upload-video \
  --browser 9225 \
  --file "/Users/yelin/Desktop/自媒体测试/“疫苗制造商”英文怎么表达？_extended_video_2026-08-24T08-49-25-826Z.mp4" \
  --title "SAU付费功能预提交测试-20260826" \
  --description "SAU 自动化付费配置预提交验收；不会点击最终发布。" \
  --paid-target-config "/tmp/sau-douyin-paid-target-20260826.json" \
  --no-submit
```

如果实际 CLI 的浏览器/文件参数名不同，只可根据 `--help` 做等价替换，不可改测试语义。

真实测试成功必须同时满足：

- 只连接 Browser Fleet 的 9225。
- 账号在上传前和结束前均精确匹配。
- 指定视频上传成功并进入可配置状态。
- 所有付费控件被真实设置。
- 两次回读与请求快照完全一致。
- 结果为 `status=prepared`、`submitted=false`、`verified=true`。
- 最终发布按钮点击次数为 0；抖音内容管理中没有新增作品或定时作品。
- 本任务创建的标签页全部关闭，原有标签页数量和内容未被清理。
- Browser Fleet 注册信息未记录瞬时在线状态。

再做两类负向真实测试，均必须在上传/提交前安全失败：

1. 将 `priceYuan` 改为 `0.99`：应在打开浏览器前失败。
2. 将 `platformAccountId` 改为明显不存在的测试值：应在上传前因账号不匹配失败，不得打印实际账号 ID。

负向测试结束后删除 `/tmp` 配置和临时证据；不关闭 9225 浏览器本身，除非它是本任务启动且 Browser Fleet 明确要求恢复原状态。

### 步骤 10：最终审计、验收和交接

在新 worktree 执行：

```bash
cd "/Users/yelin/Developer/agent-tools/social-auto-upload-douyin-paid"
rtk .venv/bin/python -m unittest discover -s tests
RTK_DISABLED=1 git status --short --branch
RTK_DISABLED=1 git diff --check
RTK_DISABLED=1 git diff --stat
RTK_DISABLED=1 git diff -- README.md sau_cli.py uploader/douyin_uploader/main.py uploader/douyin_uploader/paid_video.py tests/test_sau_douyin_paid_video.py
```

检查：

- 没有 `conf.py`、Cookie、数据库、日志、视频、截图、二维码、`.venv`、`/tmp` 文件进入 Git diff。
- 没有修改英语工作流仓库。
- 没有新增依赖。
- 所有变更均服务于当前需求。
- README 与实际代码、测试完全一致。
- 不存在 `TODO`、`TBD`、占位实现、跳过测试或伪造成功。

最后回到 main 工作区做只读核验：

```bash
cd "/Users/yelin/Developer/agent-tools/social-auto-upload"
RTK_DISABLED=1 git rev-parse HEAD
RTK_DISABLED=1 git status --short --branch
```

必须证明：

- main HEAD 等于启动时记录的 `MAIN_HEAD_BEFORE`，除非用户在执行期间自行更新；若发生外部更新，只报告事实，不覆盖。
- 用户原有 `AGENTS.md` 改动仍原样存在。
- main 没有本任务产生的业务代码、依赖或缓存改动。

不得 commit、push、merge 或删除 worktree。最终把 worktree 路径、分支名、测试摘要、真实预提交摘要、未解决限制和建议的人工 review 文件列表交给用户。

## 9. 验收矩阵

| 验收项 | 必须结果 | 失败处理 |
|---|---|---|
| main 隔离 | HEAD/用户改动不被本任务改变 | 立即停止，报告污染路径，不做 reset |
| 单元测试 | 全部通过 | 定位根因；禁止跳过或删测试 |
| 字段校验 | 非法金额/枚举/试看/协议/合集均在浏览器前失败 | 修纯解析器 |
| 账号安全 | 9225 实际账号与目标精确一致 | 阻止上传/提交，脱敏报告 |
| UI 设置 | 所有付费控件可被稳定定位和设置 | 保留最后现场页，禁止提交 |
| UI 回读 | 连续两次等于请求快照 | fail closed，禁止提交 |
| no-submit | prepared 且发布按钮从未点击 | 视为最高优先级安全缺陷 |
| 页面生命周期 | 成功全关任务页；失败仅留最后现场页 | 修复并重新真实测试 |
| README | 与实现、测试、限制一致 | 不得交付 |
| Peach 多账号状态 | 明确标为外部限制，不伪称已解决 | 文档纠正，不扩建本任务 |

## 10. 无监督失败策略

执行模型不得因普通实现选择向离线用户提问。按以下规则自主处理：

- 页面文案或 DOM 与预期不同：使用 Browser Harness 重新读取可访问树，选择语义最稳定的真实定位方式；不得猜坐标。
- 一个控件无法稳定回读：本次能力不得宣称完成；保留最后现场页，输出 `BLOCKED_UI_READBACK_<FIELD>`。
- 9225 未登录或账号不匹配：输出 `BLOCKED_ACCOUNT_9225`，不扫码、不短信登录、不换账号、不使用 9226 代替。
- 抖音平台没有向该账号开放付费功能：输出 `BLOCKED_PLATFORM_CAPABILITY`，附脱敏的可见文案摘要；不得绕过资格限制。
- 视频被平台拒绝：输出 `BLOCKED_TEST_MEDIA`，保留现场；不得自行寻找、下载或上传其他视频。
- 权限不足以创建 worktree：输出 `BLOCKED_WORKTREE_PERMISSION`；绝不在 main 开发。
- Peach 多账号平台回执无法表达部分成功：记录为 `UPSTREAM_DEPENDENCY_PEACH_MULTI_ACCOUNT_RECEIPT`，不修改只读仓库。
- 只有实现、自动化测试和真实 no-submit 验收全部通过，才可报告完成。

## 11. 最终报告固定格式

```text
状态：COMPLETE / BLOCKED_<REASON>
worktree：/Users/yelin/Developer/agent-tools/social-auto-upload-douyin-paid
分支：codex/douyin-paid-video-peach-handoff
main 是否保持不变：是/否（不得隐瞒）
改动文件：逐项列出
自动化测试：命令、通过数、失败数
真实浏览器：SAU-自媒体运营-9225；账号匹配 true/false（不得输出 ID）
真实预提交：prepared true/false；submitted 必须为 false；付费回读 verified true/false
最终发布按钮点击次数：必须为 0
页面清理：成功任务页已关闭 true/false；既有页面未改变 true/false
README 同步：是/否
未解决限制：只列真实存在的外部依赖或阻塞
需要用户下一步：人工 review；如认可，再单独授权 commit/merge/push 或最终真实发布
```

完成本计划不等于获得提交、合并、推送或真实发布授权。
