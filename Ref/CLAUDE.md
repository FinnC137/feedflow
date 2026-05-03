# Finn_ProSummary — Claude 上下文指令

## 项目目标

多源内容抓取 → Claude 整理/总结 → 推送 Flomo 信息流

## 当前架构状态

* **无 .py 脚本**：整条管线没有任何 Python 脚本，完全靠 Claude 实时读取本文件指令 + 调用 skill 编排执行

* 相当于"Claude 当人肉脚本引擎"，每次触发都由 Claude 临时组装命令链

* **已验证可行**：已成功运行多次（见 Files/ 目录下的归档），日常使用没有问题

* **局限性**：不可脱离 Claude 运行、每次执行路径可能有细微差异、无法被他人复用

* **下一步**：流程稳定后应固化为 .py 脚本 + 正式 skill，脱离暗号触发

## 设计原则

### 1. 轻依赖优先

> 选方案时，优先选"同等质量下依赖最少"的方案作为主路径。

每个信息源的主方案应追求：零 API Key > 单 API Key > 需账号登录 > 需特定生态绑定。
不牺牲结果质量的前提下，减少前置条件就是提升鲁棒性。

### 2. 降级链兜底

> 降级链不是主角，但必须在。它是保证任务一定能被完成的底层保障框架。

每个信息源 Scraper 内部自带降级策略：主方案失败 → 备选方案 → 最终兜底（粘贴长文）。
降级时允许体验降级（如需要手动操作），但必须保证任务能完成。

### 3. 未来演进方向

* **封装集成化**：从 CLAUDE.md 指令 → Python CLI 工具 → 可独立运行的软件

* **LLM 可切换**：总结模块抽象为 LLM 无关层，支持 Claude/DeepSeek/Kimi 等，脱离对单一模型的依赖

* **鲁棒性**：每步有输入输出持久化、错误重试、断点恢复

## 触发规则

* **固定前缀**：必须以 `Pro总结` 开头（防止误触发）

* 识别后自动执行：抓取内容 → 整理/总结 → POST Flomo

* ⚠️ 当前为暗号触发（临时方案），流程稳定后将迁移为正式 skill

### 三档触发词

| 档位    | 触发词            | 模糊匹配（宽松判定）                            | 说明             |
| ----- | -------------- | ------------------------------------- | -------------- |
| ⚡ 默认  | **`Pro总结`**    | `Pro总结` 后直接跟 URL/文本，无额外修饰词            | 观点小总结 + 完整脱水整理 |
| 📝 全文 | **`Pro总结·全文`** | `Pro总结` + 逐字稿 / 全文 / 完整 / 详细          | 保留原文全部内容的脱水逐字稿 |
| 💡 速览 | **`Pro总结·速览`** | `Pro总结` + 速览 / 精简 / 要点 / 快读 / 简要 / 概括 | 核心要点短摘要        |

**判定逻辑**：

1. 消息必须包含 `Pro总结` 前缀才触发（无前缀不触发）

2. 前缀后的修饰词做模糊意图匹配——不要求严格用 `·` 分隔，口语化表达也能命中

3. 无修饰词 → 默认档；出现全文/详细类词汇 → 全文档；出现精简/速览类词汇 → 速览档

### 输入类型判断

| 用户输入                             | 判定      | 主方案                           | 降级方案                                     |
| -------------------------------- | ------- | ----------------------------- | ---------------------------------------- |
| `Pro总结` + bilibili.com / BV号     | B站视频    | bilibili-cli 抓 CC 字幕          | yt-dlp 下载音频 → faster-whisper 本地转录 → 粘贴长文 |
| `Pro总结` + xiaoyuzhoufm.com       | 小宇宙播客   | xiaoyuzhou-transcribe 转录      | —                                        |
| `Pro总结` + youtube.com / youtu.be | YouTube | baoyu-youtube-transcript（零依赖） | NotebookLM → 粘贴长文                        |
| `Pro总结` + 其他 HTTP(S) 链接          | 网页正文    | WebFetch 抓取正文                 | 粘贴长文                                     |
| `Pro总结` + 大段文字（非 URL）            | 粘贴长文    | 直接处理，无需抓取                     | —                                        |

## 网络代理

* 境内网络环境需代理访问 `youtubei.googleapis.com`（InnerTube API）等被墙域名

* 代理地址：`http://127.0.0.1:7897`（Clash Verge）

* 所有涉及境外 API 的命令行工具（npx/bun、yt-dlp 等）执行时需设置环境变量：
  
  ```bash
  export HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897
  ```

* 或在命令前直接注入：`HTTPS_PROXY=http://127.0.0.1:7897 npx -y bun ...`

* ⚠️ 仅境外 API 需要代理；bilibili-cli、Flomo Webhook 等国内服务不需要

## 凭证管理

* **统一凭证文件**：`Finn_ProSummary/secrets.json`

* 所有敏感信息（Flomo Webhook、B站 Cookie、未来的 LLM API Key）集中存放于此

* bilibili-cli 工具仍从 `~/.bilibili-cli/credential.json` 读取（工具自身约定），内容与 secrets.json 中的 bilibili 段保持同步

* ⚠️ secrets.json 不得提交到公开仓库

## Flomo 推送规范

* Webhook 地址见 `secrets.json` 中的 `flomo.webhook`（兼容旧路径 `.env` 中的 `FLOMO_WEBHOOK`）

* 必须用 Python `urllib` 发送（curl 中文编码会出错；urllib 内置零依赖，符合轻依赖优先原则）

### 整理模式（默认）格式

```
#Pro总结 《标题》
来源：油管 | 链接

📌 观点总结

（3-5 句话概括作者的核心观点和结论，让读者 10 秒内决定是否值得细看）

━━━━━━━━━━

（去除水分后的完整内容整理，保留原文的信息量和结构，
 重新组织为可读的书面文本，分段分节）
必要时用【小标题】标记段落主题
列表项用 ▪ 开头
```

### 逐字稿模式格式

```
#Pro总结 《标题》
来源：油管 | 链接

📝 逐字稿

（去掉时间戳，去掉口语重复和语气词，但保留原文全部信息和表达顺序，
 分段使其易读，不改变原文的结构和逻辑，不加小标题，不做归纳）
```

### 精简模式格式

```
#Pro总结 《标题》
来源：油管 | 链接

💡 速览

（短篇幅总结，根据原内容长度弹性调整，
 抓核心观点和关键信息，省略细节和论证过程）
```

### 通用规则

* 来源类型标注：B站 / 小宇宙 / 油管 / 网页 / 长文 / X
* 粘贴长文时：来源类型写"长文"，标题从内容中提炼，链接留空
* 来源信息单独一行，格式：`来源：类型 | URL`
* 全文使用纯文本排版，不使用 Markdown 语法（Flomo 不支持渲染）

### 排版约定

* **emoji**：仅用于段落标记（📌观点总结 / 📝逐字稿 / 💡速览），每篇不超过 5 个，不做句内装饰
* **强调/小标题**：用【】包裹，如【核心观点】【风险提示】
* **分隔线**：用 `━━━━━━━━━━`（Unicode 水平线），不用 `---` 或 `***`
* **列表**：用 `▪` 开头，不用 `-` 或 `*`

## 数据存储

* 所有中间产物（逐字稿、音频、srt 等）统一存放在：
  `Finn_ProSummary/Files/<时间戳>_<标题>/`

* 文件夹命名格式：`YYYYMMDD_HHMMSS_标题关键词`

* 示例：`20260427_115100_腰椎健康久坐时代/`

* 每个文件夹内包含：原始转录文件 + 最终推送到 Flomo 的文本副本（`flomo_output.md`）

## 信息源抓取方式

### B站 (bilibili.com)

**主方案：bilibili-cli**（轻依赖，Cookie 持久化）

```bash
"C:/Python314/Scripts/bili.exe" video <BV号> --subtitle
```

* 凭证存储：`~/.bilibili-cli/credential.json`（已配置，自动加载，无需每次登录）

* 认证降级链：已存凭证 → 自动读浏览器 Cookie → QR 码扫描

* 输出：纯文本字幕（`--subtitle`）或 SRT 格式（`-st --subtitle-format srt`）

* 限制：只能抓已有 CC 字幕的视频

**降级方案：yt-dlp 下载音频 + faster-whisper 本地转录**

* 视频无 CC 字幕时，bilibili-cli 无法抓取，走音频转录路径：
  
  1. `yt-dlp -x --audio-format mp3 -o "Finn_ProSummary/Files/<文件夹>/audio.mp3" "https://www.bilibili.com/video/<BV号>"`
  
  2. `C:/Python314/python.exe ~/.agents/skills/xiaoyuzhou-transcribe/scripts/xiaoyuzhou_transcribe.py "local" --audio-path "Finn_ProSummary/Files/<文件夹>/audio.mp3" --output-dir "Finn_ProSummary/Files/<文件夹>" --model base`

* 复用已有的 faster-whisper 能力（xiaoyuzhou-transcribe skill），无需额外依赖

### 小宇宙 (xiaoyuzhoufm.com)

```bash
C:/Python314/python.exe ~/.agents/skills/xiaoyuzhou-transcribe/scripts/xiaoyuzhou_transcribe.py "<URL>" --output-dir "Finn_ProSummary/Files" --model base
```

* 输出 `.mp3` + `.srt` + `.txt` 三件套

* 质量优先用 `--model base`

### YouTube (youtube.com / youtu.be)

```bash
HTTPS_PROXY=http://127.0.0.1:7897 npx -y bun ~/.agents/skills/baoyu-youtube-transcript/scripts/main.ts '<YouTube URL>' --languages zh,en --no-timestamps --output-dir "Finn_ProSummary/Files"
```

* 主方案：baoyu-youtube-transcript skill（InnerTube API 直抓，零 API Key，零登录）

* 自带降级：InnerTube 被拦 → 换客户端身份重试 → yt-dlp fallback

* 有缓存，同一视频再跑不重新请求

* 输出：`transcript.md`（含 frontmatter 元数据）+ `meta.json` + 缓存文件

* ⚠️ 注意 URL 必须用单引号包裹（zsh `?` 通配符问题）

**降级方案 B：yt-dlp 下载音频 + faster-whisper 本地转录**

* InnerTube API 被墙或限流时走此路径：
  
  1. `HTTPS_PROXY=http://127.0.0.1:7897 yt-dlp -x --audio-format mp3 --audio-quality 64K -o "Finn_ProSummary/Files/<文件夹>/audio.%(ext)s" "<YouTube URL>"`
  
  2. `C:/Python314/python.exe ~/.agents/skills/xiaoyuzhou-transcribe/scripts/xiaoyuzhou_transcribe.py "local" --audio-path "Finn_ProSummary/Files/<文件夹>/audio.mp3" --output-dir "Finn_ProSummary/Files/<文件夹>" --model base`

* 复用 xiaoyuzhou-transcribe skill 的 faster-whisper 能力，无需额外依赖

**降级兜底 C：NotebookLM `source_add` → `notebook_query`**（需 Google 账号 + Gemini Pro）

### 网页正文 (一般 HTTP/HTTPS 链接)

**主方案：WebFetch**（内置工具，零依赖）

* 使用 WebFetch 抓取目标 URL，自动将 HTML 转为 Markdown 正文

* 调用方式：`WebFetch(url=目标URL, prompt="提取正文内容，忽略导航栏、广告、页脚等无关元素")`

* 输出即为可直接处理的 Markdown 文本，无需额外解析

**降级方案：粘贴长文**

* 页面需要登录、JS 重度渲染（SPA）、或反爬拦截导致抓取失败时

* 提示用户手动复制正文粘贴，走"粘贴长文"通道

### 粘贴长文

* 无需抓取，用户直接粘贴的文本即为原始内容

* 直接进入处理环节

### X (Twitter)

* 🔲 待研究

## 待完成事项（按优先级）

1. [x] ~~**网页正文抓取**~~ — WebFetch 内置工具，零依赖，降级走粘贴长文

2. [x] ~~**YouTube 字幕提取**~~ — 已切换为 baoyu-youtube-transcript（零依赖），NotebookLM 降级为兜底

3. [x] ~~**B站轻依赖方案**~~ — bilibili-cli 主方案（Cookie 持久化，无需 QR 码），无字幕视频降级为 yt-dlp + faster-whisper 本地转录

4. [x] **迁移为正式 skill** — 脱离暗号触发，实现框架级自动识别和调度

5. [ ] **X/Twitter 支持** — 反爬严格，需研究可行方案

## 当前运行模式：指令驱动（有意为之）

当前阶段**刻意不写 .py 脚本**，由 Claude 实时读取本文件指令 + 调度 skill 执行。
这不是偷懒，而是一种有意的设计：

* **原型验证期**：流程还在迭代，每次跑都可能调整信息源、输出格式、降级策略

* **脚本过早固化 = 过早优化**：写成 .py 反而增加修改成本

* **当前目标**：先把各信息源跑通、把体验打磨到满意，再固化

* **固化信号**：连续 N 次执行都不需要改流程时，说明可以固化了

固化路线：CLAUDE.md 指令 → Python CLI 工具 → 正式 skill → 可独立运行的软件

## 编码规范

* 脚本语言：Python

* 注释用中文，变量名用英文

* 实现功能前先讨论方案，得到确认后再动手
