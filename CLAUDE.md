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

> 以下为每天 7:10 CST 的固定作业。信源配置从飞书多维表格拉取。

## 零、加载信源配置

```bash
PYTHONIOENCODING=utf-8 python modules/feishu-publisher/load_sources.py
```

输出 `modules/feishu-publisher/sources_cache.json`。后续步骤以缓存文件中的 active 信源为准。

**配置入口**：飞书多维表格 → [FeedFlow 信源配置](https://www.feishu.cn/wiki/XV0Swj7Xxi66oKktt8Lcqs6tnud)

| 列      | 说明                                 |
| ------ | ---------------------------------- |
| 信源名称   | 如 "LT视界"                           |
| URL/ID | YouTube channel_id 或 RSS URL       |
| 信源类型   | youtube / bilibili / rss / podcast |
| 总结强度   | light / default / heavy            |
| 特殊要求   | 自由文本，如 "过滤国内新闻，只保留国际/跨国内容"         |
| 状态     | active / paused                    |
| 最后推送   | pipeline 自动回写                      |

## 一、准备

```bash
export https_proxy=http://172.22.240.1:7897   # 境外服务必须走代理，境内（B站/Flomo）不需要
DATE=$(TZ='Asia/Shanghai' date +%Y-%m-%d)
OUTBASE="x:/Desktop/Hermes_workspace/FeedFlow/output/$DATE"
mkdir -p "$OUTBASE"
```

每个信源使用独立子目录：`$OUTBASE/<信源名称>/`。处理前按需创建 `SOURCEDIR`。

## 二、YouTube 家族

### 2.1 检查是否有新视频

```bash
SOURCE_NAME="<取 sources_cache.json 中的 name>"
CHANNEL_URL="<取 sources_cache.json 中的 url，如 https://www.youtube.com/@weizhichao/videos>"
SOURCEDIR="$OUTBASE/$SOURCE_NAME"
mkdir -p "$SOURCEDIR"

# 用 yt-dlp 拉取频道最新视频（比 RSS 更可靠）
yt-dlp --flat-playlist --print "%(id)s|%(title)s|%(upload_date)s" \
  "$CHANNEL_URL" 2>/dev/null | head -1 > "$SOURCEDIR/latest.txt"
```

读取 `$SOURCEDIR/latest.txt`，格式 `video_id|title|YYYYMMDD`。

- 日期 = 今天 CST → 继续
- 日期 ≠ 今天 → 终止此信源，跳到下一个

### 2.2 抓取转录

主方案（baoyu-youtube-transcript）：

```bash
VIDEO_URL="https://www.youtube.com/watch?v=<video_id>"
npx -y bun ~/.agents/skills/baoyu-youtube-transcript/scripts/main.ts \
  "$VIDEO_URL" \
  --languages zh-CN,zh,en --no-timestamps \
  --output-dir "$SOURCEDIR"
```

如果报 "No transcript found"，看报错里提示的可用语言码，换成对应码重试。

读取输出文件 `$SOURCEDIR/transcript.md`（或 skill 实际输出的路径），以此为原始文本。

备选（yt-dlp 字幕下载）：

```bash
yt-dlp --write-auto-sub --sub-lang zh-Hans,zh --convert-subs srt --skip-download \
  -o "$SOURCEDIR/%(title)s" "<video_url>"
```

兜底（音频 + faster-whisper）：

```bash
yt-dlp -x --audio-format mp3 --audio-quality 64K \
  -o "$SOURCEDIR/audio.%(ext)s" "<video_url>"
C:/Python314/python.exe ~/.agents/skills/xiaoyuzhou-transcribe/scripts/xiaoyuzhou_transcribe.py \
  "local" --audio-path "$SOURCEDIR/audio.mp3" --output-dir "$SOURCEDIR" --model base
```

## 三、AI 处理

读取采集到的原始文本，按 `sources_cache.json` 中该信源的 `output_level` 执行处理。

**输出文件命名**：`$SOURCEDIR/<short_name>.md`

**H1 规范**：只写主题（如 `# 意志力的经济学解释`），不要拼入 short_name 或时间戳——飞书标题由 deliver.py 自动组装为 `short_name_主题_YYYYMMDD_HHMM`。

**页首元数据**：每篇文章正文前必须有一行小字元数据（用 `>` 引用块），记录本次 AI 处理的耗时和 token 消耗：

```
> 采集耗时：<audio download/transcript fetch 时长> | AI 处理耗时 ~Xs | 预估 token：输入 ~N / 输出 ~N
```

此元数据行始终放在 H1 之后、正文之前。预估方式：1 个中文字符 ≈ 1 token，英文按 1 token/词估算。

### heavy（清洗逐字稿）

**必须严格使用此 prompt，禁止输出摘要——heavy 的唯一产出是清洗脱水后的完整逐字稿。**

```
以下是一段视频的原始逐字稿转录。请清洗脱水：

- 去除开场寒暄和结尾求赞求关注（"大家好我是xxx""请点赞转发关注"等）
- 去除口语重复、语气词（"这个""那个""就是说""然后"等冗余连接词）
- 去除时间戳
- 保留全部实质信息和论证逻辑，不压缩不精简
- 分段使其易读，按主题转换自然分段
- 不要添加原文没有的观点或总结
- 不要加小标题

原始文本：
---
<粘贴原始转录>
---
```

### default（结构化摘要）

**将信源的 `filter_prompt` 填入下方过滤规则行。无 filter_prompt 时省略该行。**

```
以下是一段视频的逐字稿。请生成结构化摘要：

- 按主题分组，每组用【主题】标记
- <如有 filter_prompt，在此写入过滤规则，如"过滤国内新闻，只保留国际/跨国内容">
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

处理结果写入 `$SOURCEDIR/<short_name>.md`，H1 只写主题，飞书标题由 deliver.py 自动组装。

## 四、RSS 发布

**硬性规则：禁止直接编辑 rss.xml。RSS 输出必须通过 `build_rss.py` 生成。AI 只产出 `articles.json`，XML 由 Python 脚本负责。**

参见 `modules/rss-publisher/CLAUDE.md`（含完整校验规则清单）。`channel.json` 已配好。

### 4.1 生成 articles.json

处理完所有信源后，将当天文章汇总为 `articles.json`，格式：

```json
[
  {
    "title": "source_name — 2026-05-03",
    "link": "https://www.youtube.com/watch?v=xxx",
    "guid_path": "output/2026-05-03/文章名/文章名.md",
    "description": "纯文本摘要，≤150字",
    "content_html": "<h1>标题</h1><p>段落1内容。</p><p>段落2内容。</p>",
    "pubDate": "Sun, 03 May 2026 09:00:00 +0000"
  }
]
```

字段说明：

- `link`：指向原始外部源（YouTube 视频页等），**不是** GitHub Pages 的 .md 链接
- `guid_path`：文章 .md 文件相对于仓库根的路径，含中文需 percent-encode
- `content_html`：每 2-3 句一个 `<p>`，每个 `<p>` 内纯文本 ≤150 字，开闭标签前后必须有换行
- `pubDate`：RFC 822 UTC 格式，用 `date -u +"%a, %d %b %Y %H:%M:%S +0000"` 生成

可与前一日 articles.json 合并后按 pubDate 降序排列。

### 4.2 校验循环

```bash
python modules/rss-publisher/build_rss.py --validate articles.json --channel modules/rss-publisher/channel.json
```

输出为 JSON，包含 `valid` 和 `errors` 两个字段。`level: error` 的项会阻断生成，必须全部修完。

逐个阅读错误，按 `fix` 提示修改 `articles.json`，重新运行校验。**循环直到 `"valid": true`。**

常见错误速查：
| 报错 | 原因 | 修法 |
|------|------|------|
| 段落过长（>150 字） | 一个 `<p>` 塞太多句 | 拆成 2-3 句一个 `<p>` |
| link 和 guid 指向同一 URL | link 写成了 .md 链接 | link 改为 YouTube 等外部源 |
| GUID 路径含中文字符 | guid_path 未 encode | 按 fix 提示的 encoded 值替换 |

### 4.3 生成 rss.xml

```bash
python modules/rss-publisher/build_rss.py --build articles.json --channel modules/rss-publisher/channel.json --output rss.xml
```

`--build` 内部会先跑一遍校验，有 error 级别问题时拒绝生成。

### 4.4 发布

```bash
cd x:/Desktop/Hermes_workspace/FeedFlow && git add rss.xml output/ && git commit -m "Daily: ${DATE}" && git -c http.proxy=http://172.22.240.1:7897 push
```

验证：`https://finnc137.github.io/feedflow/rss.xml`

## 五、飞书发布

RSS 推送完成后，同步推送到飞书 Wiki 作为并行输出渠道。

参见 `modules/feishu-publisher/CLAUDE.md`（含完整配置说明和故障排查）。

### 5.1 推送文章

```bash
PYTHONIOENCODING=utf-8 python modules/feishu-publisher/deliver.py "output/${DATE}/<source_name>/<source_name>.md"
```

按当天处理结果逐篇推送。

### 5.2 回写最后推送时间

```bash
PYTHONIOENCODING=utf-8 python -c "
import sys; sys.path.insert(0, '.')
import importlib
m = importlib.import_module('modules.feishu-publisher.load_sources')
m.update_last_push('<信源名称>', '$(TZ=Asia/Shanghai date +\"%Y-%m-%d %H:%M\")')
"
```

### 5.2 前置条件

- `lark-cli` 已安装并登录
- user 身份已有 `docx:document:write_only` scope
- 目标父页面存在且可访问

### 5.3 配置

`modules/feishu-publisher/channel.json`：

| 字段                  | 说明                      |
| ------------------- | ----------------------- |
| `parent_node_token` | 飞书 Wiki 父页面 token       |
| `lark_cli`          | lark-cli.exe 路径         |
| `identity`          | 操作身份（默认 `user`）         |
| `chunk_size`        | 单次写入最大 block 数（默认 `45`） |

## 六、收尾

1. 确认 `$OUTBASE/` 下每个信源子目录都有处理结果
2. 删除各子目录下的 `latest.txt` 等临时文件
3. 运行日志追加到 `output/cron-${DATE}.log`
