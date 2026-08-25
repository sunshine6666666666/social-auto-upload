# Social Auto Upload（本地 Fork）

这是基于上游 [`dreammis/social-auto-upload`](https://github.com/dreammis/social-auto-upload) 持续维护的本地 Fork。当前主线是 Python CLI `sau`：使用浏览器自动化或本地账号文件，把视频、图文发布到多个内容平台。

本 README 只描述当前工作区真实存在的能力。上游文档、旧 Web 页面和历史示例可能与本 Fork 不完全一致。

## 现在能做什么

| 平台 | 登录检查 | 账号身份读取 | 视频 | 图文 | 定时发布 | 本 Fork 的重点能力 |
| --- | --- | --- | --- | --- | --- | --- |
| 抖音 | ✅ | ✅ | ✅ | ✅ | ✅ | 双比例封面、商品、合集、自主声明、短信验证拦截、发布前账号复核 |
| Bilibili | ✅ | ✅ | ✅ | — | ✅ | CDP 登录态转换为 biliup 凭证、封面、合集、充电专属、投稿读回 |
| YouTube | ✅ | ✅ | ✅ | — | ✅ | Studio 原生预约、封面、播放列表、可见性、发布前账号复核、结果读回 |
| 小红书 | ✅ | — | ✅ | ✅ | ✅ | 视频可用 `--no-submit` 做发布前冒烟测试 |
| 快手 | ✅ | — | ✅ | ✅ | ✅ | 传统账号文件与浏览器自动化流程 |
| 视频号 | ✅ | — | ✅ | — | ✅ | 双比例封面、分类、短标题、草稿 |
| 百家号 | 历史代码 | — | 历史代码 | — | 未纳入本轮审计 | 尚未接入统一 CLI |
| TikTok | 历史代码 | — | 历史代码 | — | 未纳入本轮审计 | 尚未接入统一 CLI |

抖音、Bilibili、YouTube 是当前“受管浏览器 + 账号校验 + 防错发”闭环最完整的三个平台。其他平台仍保留原有 uploader 和 CLI 能力，但没有多浏览器账号路由。

## 本 Fork 新增的公共能力

### 1. 指定受管浏览器或 CDP 端口

三种输入最终都会解析为本机 CDP 地址，端口没有硬编码在仓库中：

```bash
# 受管浏览器端口
sau youtube identity --account sau9225 --browser 9225

# 受管浏览器名称
sau bilibili identity --account sau9225 --browser "SAU-自媒体运营-9225"

# 完整的本机 CDP URL
sau douyin identity --account sau9225 --cdp-url http://127.0.0.1:9225
```

也可以使用环境变量：

```bash
export SAU_BROWSER=9225
# 或者
export SAU_CDP_URL=http://127.0.0.1:9225
```

规则：

- `--browser`、`--browsers`、`--cdp-url` 互斥。
- `--browser` 支持登记名称或端口，并通过本机 `browser-fleet-manager` 校验名称、端口、健康状态和锚点。
- 已登记但离线的名称、端口或本机 CDP URL 会按需启动对应浏览器；任务结束不会停止它。未登记端口、冲突锚点和远程 CDP URL 都会拒绝。
- 登记表只保存长期身份锚点；在线/离线状态由实时进程、端口、Profile 和 CDP 检查推导。
- `--cdp-url` 只接受 `localhost`、`127.0.0.1` 或 `::1`，不连接远程浏览器。
- `--headless`/`--headed` 只决定 SAU 自己启动的浏览器；连接现有 CDP 浏览器时，浏览器是否可见由那个浏览器本身决定。

### 2. 查看当前到底登录了谁

抖音、YouTube、Bilibili 都有 `identity` 命令，输出 JSON，不输出 Cookie、Token 或 CSRF：

```bash
sau douyin identity --account sau9225 --browser 9225
sau youtube identity --account sau9225 --browser 9225
sau bilibili identity --account sau9225 --browser 9225
```

稳定账号字段分别是：

- 抖音：页面可见抖音号或平台稳定 ID。
- YouTube：`UC...` Channel ID。
- Bilibili：数字 MID/UID。

可以要求账号必须匹配：

```bash
sau bilibili identity \
  --account sau9225 \
  --browser 9225 \
  --target-account 526557505
```

`--target-account` 只做精确匹配：稳定 ID、handle 或完整昵称。不会用模糊相似度猜账号。

### 3. 一次盘点多个浏览器

```bash
sau accounts scan \
  --browsers "9225,热点监控-9224" \
  --platforms "douyin,youtube,bilibili"
```

输出是浏览器 × 平台矩阵，每项会明确区分：

- `logged_in`：读取到登录态和稳定 ID。
- `interaction_required`：需要登录或重新登录。
- `error`：读取过程失败，不能误报成“未登录”。

扫描按顺序执行。一个平台读取失败不会阻止其他平台继续盘点。

### 4. 多浏览器按账号自动路由

抖音、YouTube、Bilibili 的视频上传可以给出多个候选浏览器：

```bash
sau youtube upload-video \
  --account sau \
  --file videos/demo.mp4 \
  --title "示例视频" \
  --browsers "9225,9226" \
  --target-account UCxxxxxxxxxxxxxxxxxxxxxx
```

SAU 会读取候选浏览器的账号身份：

- 唯一命中：使用该浏览器。
- 零命中：阻止发布。
- 多重命中：阻止发布，避免随机选错。
- 多浏览器但没有 `--target-account`：阻止发布。

### 5. 发布前双重账号校验

抖音和 YouTube 会在准备阶段读取稳定 ID，并在最终点击发布/预约前再次读取；ID 变化立即阻止。

Bilibili 会核对：

1. CDP 浏览器当前账号；
2. 转换后的 biliup 凭证 MID；
3. 提交前再次读取的浏览器账号。

这套校验的原则是：宁可失败，也不要发错账号。

### 6. 后台标签页与确定性回收

抖音、YouTube、Bilibili 通过公共 `BrowserSession` 连接现有 CDP 浏览器时，SAU 优先使用 `Target.createTarget(background=true)` 创建后台任务页。

- 后台创建失败时，只兜底一次普通前台页，并在结果中返回 `focus_fallback_used=true`。
- 成功任务关闭自己新建的页面。
- 失败任务只保留最后一个自己新建的现场页，方便排查。
- 执行前已经存在的页面不会被 SAU 页面生命周期逻辑关闭。
- Direct CDP fallback 只复用完全相同 URL 的页面；否则创建并回收自己的后台 target。
- CDP 会话结束只断开 SAU 连接，不调用会关闭长期 Chrome 的 `browser.close()`；SAU 自己启动的临时浏览器仍会正常关闭。

正常路径不会主动抢系统鼠标，但不能承诺浏览器永远不获得焦点：前台 fallback 或平台自身行为仍可能让 Chrome 到前台。

### 7. 浏览器端口互斥

每条通过 CLI 执行的 CDP 任务都会按实际解析出的端口加进程锁。名称、数字端口和完整 CDP URL 都会归一到同一个端口，因此不能同时操作同一个浏览器。

锁文件位于：

```text
/private/tmp/social-auto-upload-task-state/browser-PORT.lock
```

进程正常结束会释放锁；确认原 PID 已不存在时，SAU 可以回收 stale lock。不会自动停止或删除 Chrome。

### 8. Task ID 防重复

抖音、YouTube、Bilibili 的视频上传支持 `--task-id`：

```bash
sau bilibili upload-video \
  --account sau9225 \
  --file videos/demo.mp4 \
  --title "唯一测试标题" \
  --desc "测试说明" \
  --tid 249 \
  --browser 9225 \
  --target-account 526557505 \
  --task-id bili-demo-001
```

规则：

- Task ID 只能使用字母、数字、点、下划线、短横线，长度 1–128。
- 同一 Task ID + 同一参数成功后再次执行，不会再次投稿。
- 同一 Task ID 的并发启动只有一个调用能取得执行权，其余调用按 `uncertain` 阻止。
- 同一 Task ID 换了参数会被拒绝。
- `started` 或 `uncertain` 结果不会自动重试，避免超时后重复投稿。
- 失败结果也不会在批量任务中自动重试。
- 成功 receipt 保留平台返回的脱敏结构化结果，例如账号稳定 ID、端口、定时时间和作品 ID/URL。

脱敏 receipt 与锁放在同一个临时目录，不保存 Cookie、Token 或 CSRF。

### 9. Issue #9/#10 相关行为

- YouTube Studio 预约优先点击原生 `#done-button`，兼容中文“预定”；禁用按钮不会被点击。找不到最终按钮时返回 `interaction_required`、`recoverable=true` 以及可提取的草稿 ID/URL，并保留最后现场页；带 `--task-id` 的失败 receipt 不会自动重传。
- 抖音本地 CDP 上传的主视频超过 50 MiB 时，首次上传和失败重试都通过现有 `DOM.setFileInputFiles` helper 交给同机 Chrome；小文件和非 CDP 路径保持普通文件输入。

### 10. 顺序批量任务

批量清单是一个 JSON 文件，`argv` 不包含开头的 `sau`：

```json
{
  "tasks": [
    {
      "id": "scan-youtube-9225",
      "argv": [
        "youtube",
        "identity",
        "--account",
        "sau9225",
        "--browser",
        "9225"
      ]
    },
    {
      "id": "scan-bilibili-9225",
      "argv": [
        "bilibili",
        "identity",
        "--account",
        "sau9225",
        "--browser",
        "9225"
      ]
    }
  ]
}
```

执行：

```bash
sau batch --file tasks.json
```

批量任务故意串行，不做并行队列。单项失败会被记录，后续项继续执行，最后返回汇总 JSON 和非零退出码。

## 安装

要求 Python 3.10–3.12，推荐 3.11 和 `uv`：

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e .
patchright install chromium
cp conf.example.py conf.py
sau --help
```

传统依赖安装和 Web 兼容路径仍保留，但当前 CLI 主线以 `pyproject.toml`、Patchright 和 `sau` 为准。

常用配置在 `conf.py`：

- `LOCAL_CHROME_PATH`
- `LOCAL_CHROME_HEADLESS`
- `DEBUG_MODE`
- `YT_PROXY`：YouTube 需要显式代理时设置。
- `YT_MAX_DURATION_SECONDS`：YouTube 上传时长预检，默认 900 秒。

不要提交 `conf.py`、`cookies/`、`db/`、二维码、冒烟截图、视频、日志、本地代码索引或任何账号凭证。

## 三个平台的常用命令

### 抖音

```bash
sau douyin check --account sau9225 --browser 9225
sau douyin identity --account sau9225 --browser 9225

sau douyin upload-video \
  --account sau9225 \
  --file videos/demo.mp4 \
  --title "示例标题" \
  --desc "示例简介" \
  --tags "英语,听力" \
  --thumbnail-landscape covers/landscape.png \
  --thumbnail-portrait covers/portrait.png \
  --declaration "内容由AI生成" \
  --schedule "2030-01-01 20:00" \
  --browser 9225 \
  --target-account 202851389 \
  --task-id douyin-demo-001
```

抖音额外支持商品链接、商品标题、合集和图文 BGM。遇到短信验证码挑战会停止自动发布，不读取或猜测验证码。

### Bilibili

```bash
sau bilibili check --account sau9225 --browser 9225
sau bilibili identity --account sau9225 --browser 9225

sau bilibili upload-video \
  --account sau9225 \
  --file videos/demo.mp4 \
  --title "示例标题" \
  --desc "示例简介" \
  --tid 249 \
  --tags "英语,听力" \
  --thumbnail covers/bilibili.png \
  --schedule "2030-01-01 20:00" \
  --browser 9225 \
  --target-account 526557505 \
  --task-id bilibili-demo-001
```

CDP 模式会把当前 Bilibili Web 登录态转换为 biliup 可用的 Bilibili 专用凭证文件，然后校验 MID。首次使用可能需要联网准备 biliup。提交前会检查创作中心近期稿件中的完全同名标题；提交后读回 aid、排期和封面状态。

### YouTube

```bash
sau youtube check --account sau9225 --browser 9225
sau youtube identity --account sau9225 --browser 9225

sau youtube upload-video \
  --account sau9225 \
  --file videos/demo.mp4 \
  --title "Example title" \
  --desc "Example description" \
  --tags "English,listening" \
  --thumbnail covers/youtube.png \
  --playlist "Listening Series" \
  --schedule "2030-01-01 20:00" \
  --timezone Asia/Shanghai \
  --browser 9225 \
  --target-account UCxxxxxxxxxxxxxxxxxxxxxx \
  --task-id youtube-demo-001
```

YouTube 预约发布会读回 Video ID、预约时间、可见性和处理失败标记。找不到最终 Publish/Schedule 按钮会直接报错，不再把“等待手工点击”误报成成功。

只准备到最终页面而不点击发布：

```bash
sau youtube upload-video \
  --account sau9225 \
  --file videos/demo.mp4 \
  --title "Smoke test" \
  --no-submit \
  --browser 9225
```

## 传统平台命令

```bash
sau kuaishou login --account creator
sau kuaishou upload-video --account creator --file videos/demo.mp4 --title "标题"
sau kuaishou upload-note --account creator --images videos/1.png videos/2.png --title "标题"

sau xiaohongshu login --account creator
sau xiaohongshu upload-video --account creator --file videos/demo.mp4 --title "标题" --no-submit
sau xiaohongshu upload-note --account creator --images videos/1.png videos/2.png --title "标题"

sau tencent login --account creator
sau tencent upload-video --account creator --file videos/demo.mp4 --title "标题" --draft
```

这些平台仍支持各自的 `--schedule` 和 uploader 参数，但暂时没有稳定账号 ID 读取、账号池唯一路由和视频发布前双重身份闸门。

## 重要边界

- `--account` 是 SAU 本地账号别名，不一定等于平台昵称或账号 ID。
- 连接共享 CDP Profile 时，抖音和 YouTube 直接复用该 Profile，不把整个共享上下文导出到单个平台 cookie 文件。
- Bilibili 是例外：为了调用 biliup，会生成只供 Bilibili 使用的凭证文件，存放在 `cookies/bilibili_ACCOUNT.json`。
- 多浏览器账号路由、`identity` 和 `--target-account` 目前只承诺抖音、YouTube、Bilibili 视频链路。
- `--task-id` 目前只用于抖音、YouTube、Bilibili 视频上传。
- YouTube 自定义封面和播放列表属于尽力处理项；平台 UI 不可用时会给出 warning。最终发布按钮不是尽力项，缺失时硬失败。
- 抖音日期控件依赖当前平台 UI，建议使用近期、合理范围内的预约时间。
- 浏览器自动化依赖平台页面结构，平台改版后可能需要更新 selector；先运行 `identity` 或 `--no-submit` 再做真实投稿。
- Web/Flask/Vue 代码仍在仓库中，但不是当前主线，不能假设与 CLI 完全同步。
- SAU 不依赖 Browser Harness 才能完成账号读取或发布；Browser Harness 可以作为人工排障工具，但不属于运行时依赖。

## 测试与审计

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m compileall -q sau_cli.py uploader utils tests
git diff --check
```

测试默认 mock 浏览器、文件系统和网络，不会真实投稿。真实平台验收必须使用唯一标题、明确账号 ID、未来预约时间和唯一 Task ID；发生超时或结果不确定时先到平台后台读回，禁止盲目重发。

2026-08-25 本轮审计结果：165 项单元/回归测试通过，语法编译与 `git diff --check` 通过；本轮 README 审计没有再次执行真实投稿。

## 代码结构

```text
sau_cli.py                         CLI 参数、路由、批量和结果编排
utils/browser_selector.py          浏览器名称/端口/CDP URL 解析
utils/browser_runtime.py           CDP 会话、后台页、页面回收、端口锁、Task receipt
utils/account_identity.py          三平台统一账号身份合同
utils/direct_cdp.py                Patchright 连接失败时的最小 CDP fallback
uploader/douyin_uploader/          抖音登录、身份、视频和图文
uploader/bilibili_uploader/        Bilibili 凭证转换、biliup 和投稿读回
uploader/youtube_uploader/         YouTube Studio 上传、预约和读回
tests/                             unittest 回归测试
sau_frontend/                      历史 Vue 管理界面
```

更多安装细节见 [`docs/install.md`](docs/install.md)，参数最终以 `sau PLATFORM ACTION --help` 和当前源码为准。

## 上游与致谢

本 Fork 基于 `dreammis/social-auto-upload`，保留并持续选择性吸收上游平台能力。Bilibili 上传底层使用 [`biliup`](https://github.com/biliup/biliup)。
