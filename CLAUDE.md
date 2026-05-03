# FeedFlow — AI 操作手册

## 项目定位

FeedFlow 是一个**通用信源 → RSS 发布框架**。解决"多个不同规律的内容源，统一采集、统一处理、统一分发"的问题。

当前阶段：**AI 指令驱动**，不依赖 Python 脚本。Claude 读这份手册，按每日清单执行。

设计原则（继承自 ProSummary）：

1. **轻依赖优先**：同等质量下，选依赖最少的方案做主路径
2. **降级链兜底**：主方案失败→备选→兜底，保证任务能完成
3. **渐进固化**：先用 CLAUDE.md 指令驱动跑通，稳定后再固化为 Python CLI
4. **凭证统一**：所有敏感信息集中在 `secrets.json`

## 信源家族

| 家族         | 采集方式                                       | 依赖                    |
| ---------- | ------------------------------------------ | --------------------- |
| `youtube`  | YouTube RSS → baoyu-youtube-transcript 抓转录 | 代理                    |
| `bilibili` | bilibili-cli 抓 CC 字幕 / yt-dlp + whisper 降级 | bilibili-cli + Cookie |
| `rss`      | feedparser 解析 RSS/Atom → 正文抓取              | feedparser            |
| `podcast`  | 播客 RSS → 下载音频 → whisper 转录                 | 待实现                   |

## 输出级别

| 级别        | 产出                  | 长度参考       |
| --------- | ------------------- | ---------- |
| `heavy`   | 清洗后的完整逐字稿（去语气词/时间戳） | 保留原文全部信息   |
| `default` | 结构化摘要（分组+小标题+关键数据）  | 150-300字/条 |
| `light`   | 精简摘要（核心要点 3-5 句话）   | ~100字/条    |

---

# 每日执行清单

> 以下为每天 7:10 CST 的固定作业。读完 `sources.yaml`，对每个有 `family` 的信源逐条执行。

## 一、准备

```bash
export https_proxy=http://172.22.240.1:7897
DATE=$(TZ='Asia/Shanghai' date +%Y-%m-%d)
OUTDIR="x:/Desktop/Hermes_workspace/FeedFlow/output/$DATE"
mkdir -p "$OUTDIR"
```

## 二、YouTube 家族

### 2.1 检查是否有新视频

```bash
CHANNEL_ID="<取 sources.yaml 中的 channel_id>"
RSS_URL="https://www.youtube.com/feeds/videos.xml?channel_id=${CHANNEL_ID}"
curl -s --proxy http://172.22.240.1:7897 "$RSS_URL" -o "$OUTDIR/rss_raw.xml"
```

打开 `$OUTDIR/rss_raw.xml`，读取 `<entry>` 中第一个 `<published>` 的日期。

- 日期 = 今天 CST → 继续
- 日期 ≠ 今天 → 终止此信源，跳到下一个

### 2.2 抓取转录

主方案（baoyu-youtube-transcript）：

```bash
npx -y bun ~/.agents/skills/baoyu-youtube-transcript/scripts/main.ts \
  '<从 entry/link 取的 video_url>' \
  --languages zh-CN,zh,en --no-timestamps \
  --output-dir "$OUTDIR"
```

如果报 "No transcript found"，看报错里提示的可用语言码，换成对应码重试。

读取输出文件 `$OUTDIR/transcript.md`（或 skill 实际输出的路径），以此为原始文本。

备选（yt-dlp 字幕下载）：

```bash
yt-dlp --write-auto-sub --sub-lang zh-Hans,zh --convert-subs srt --skip-download \
  -o "$OUTDIR/%(title)s" "<video_url>"
```

兜底（音频 + faster-whisper）：

```bash
yt-dlp -x --audio-format mp3 --audio-quality 64K \
  -o "$OUTDIR/audio.%(ext)s" "<video_url>"
C:/Python314/python.exe ~/.agents/skills/xiaoyuzhou-transcribe/scripts/xiaoyuzhou_transcribe.py \
  "local" --audio-path "$OUTDIR/audio.mp3" --output-dir "$OUTDIR" --model base
```

## 三、AI 处理

读取采集到的原始文本，按 `sources.yaml` 中该信源的 `output_level` 执行处理。

### heavy（清洗逐字稿）

```
以下是一段视频的原始逐字稿转录。请清洗它：

- 去除口语重复、语气词（"这个""那个""就是说"等）
- 去除时间戳
- 保留全部信息和表达顺序
- 分段使其易读
- 不要添加原文没有的观点或总结
- 不要加小标题

原始文本：
---
<粘贴原始转录>
---
```

### default（结构化摘要）

```
以下是一段时政类视频的逐字稿。请生成结构化摘要：

- 按新闻主题分组，每组用【主题】标记
- 过滤国内相关新闻，只保留国际/跨国内容
- 保留关键数据、因果关系、观点分析
- 每条 150-300 字
- 每 2-3 个句子换行分段，禁止连续超过 150 字不换行
- 不使用 Markdown 语法

原始文本：
---
<粘贴原始转录>
---
```

### light（精简摘要）

```
以下是视频逐字稿。请生成精简摘要：

- 提取 3-5 句核心要点
- 保留关键信息和结论
- 省略细节和论证过程

原始文本：
---
<粘贴原始转录>
---
```

处理结果写入 `$OUTDIR/<source_name>.md`。

## 四、RSS 发布

参见 `modules/rss-publisher/CLAUDE.md`（自包含模块，可复制到其他项目复用）。

本项目参数：

- FEED_PATH: `rss.xml`
- SITE_URL: `https://finnc137.github.io/feedflow/`
- FEED_URL: `https://finnc137.github.io/feedflow/rss.xml`
- CHANNEL_TITLE: `FeedFlow 新闻聚合`
- CHANNEL_DESC: `多信源 AI 处理新闻摘要`
- OUTPUT_DIR: `output/`

### 快速检查清单

- [ ] `lastBuildDate` 已更新为当前 UTC 时间
- [ ] item 按 `pubDate` 从新到旧排列
- [ ] 每个 `<guid>` 中 URL 已 percent-encode（无中文字符）
- [ ] 每个 `<link>` 指向外部源，`<guid>` 指向 `.md` 永久链接，两者不同
- [ ] `<description>` 纯文本 ≤150 字，`<content:encoded>` 用 CDATA 包裹 HTML 全文
- [ ] W3C 验证通过（validity=true, 0 errors）
- [ ] 只保留最近 20 条 item

### 发布命令

```bash
cd x:/Desktop/Hermes_workspace/FeedFlow && git add rss.xml && git commit -m "Daily: ${DATE}" && git push
```

验证：`https://finnc137.github.io/feedflow/rss.xml`

## 五、收尾

1. 确认 `$OUTDIR/` 下有当天所有处理结果
2. 删除 `$OUTDIR/rss_raw.xml`（临时文件）
3. 运行日志追加到 `output/cron-${DATE}.log`

---

# 配置参考

## sources.yaml

路径：`sources.yaml`

```yaml
sources:
  - name: "LT视界"
    family: youtube
    channel_id: UCOsQMj_MZkQ5N7f1OOMB87Q
    output_level: default
    filter: international_only
```

`family` 决定采集方式，`output_level` 决定 AI 处理深度。

## secrets.json

参考 `secrets.example.json`。所有敏感信息集中存放：

```json
{
  "bilibili_cookie": "",
  "flomo_webhook": "",
  "r2": {
    "account_id": "",
    "access_key_id": "",
    "access_key_secret": "",
    "bucket_name": "feedflow"
  },
  "llm": {
    "provider": "opencode-go",
    "api_key": "",
    "model": "deepseek-v4-flash"
  }
}
```

## 代理

境外 API（YouTube、GitHub、R2 等）必须走：

```
http://172.22.240.1:7897
```

境内服务（B站、Flomo）不需要。

---

# 待扩展

- **B站家族**：bilibili-cli 抓 CC 字幕，无字幕走 yt-dlp + faster-whisper。参考 `Ref/CLAUDE.md`
- **RSS 博客家族**：feedparser 解析，WebFetch 抓正文
- **播客家族**：RSS → 音频 → whisper 转录
- **RSS 发布端点**：Cloudflare R2 或 GitHub Pages（当前仅本地输出）
- **稳定后固化**：连续 N 次执行不调整流程时，开始写 `main.py`
