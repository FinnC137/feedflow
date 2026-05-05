# FeedFlow

通用多信源新闻采集 → AI 处理 → RSS 发布框架。

## 一句话

配置信源 → 每天 AI 自动抓取 → 按需处理（全文/摘要/轻简报）→ 输出 RSS Feed。

## 动机

从 LT_News 的实践进化而来。LT_News 是一个信源（YouTube LT视界）的单点方案，FeedFlow 是它的通用化——任何能抓取的内容源，都能接入同一管道输出 RSS。

## 现状

**AI 指令驱动**。由 Claude Code 读取 [CLAUDE.md](CLAUDE.md) 操作手册执行，流程稳定后固化为 Python CLI。

## 架构

```
sources.yaml ───────────────┐
                            ▼
CLAUDE.md (AI 操作手册) ──→ 遍历信源
  ├─ YouTube 家族   (RSS + baoyu-youtube-transcript)
  ├─ B站 家族       (bilibili-cli + whisper 降级)
  ├─ RSS 博客家族    (feedparser)
  └─ ... (可扩展)
        ▼
AI 处理（按 output_level 分叉）
  ├─ heavy   = 清洗后逐字稿
  ├─ default = 结构化摘要（同 LT_News）
  └─ light   = 精简摘要
        ▼
RSS 2.0 XML → 本地 / Cloudflare R2 / GitHub Pages
```

## 输出端

- RSS Feed（当前：本地 `output/` + `archive/feed.xml`）
- 按日存档（`output/YYYY-MM-DD/<source_name>.md`）

## 配置参考

### sources.yaml

```yaml
sources:
  - name: "LT视界"
    family: youtube
    channel_id: UCOsQMj_MZkQ5N7f1OOMB87Q
    output_level: default
    filter: international_only
```

`family` 决定采集方式，`output_level` 决定 AI 处理深度。

### secrets.json

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

### 代理

境外 API（YouTube、GitHub、R2 等）必须走 `http://172.22.240.1:7897`，境内服务（B站、Flomo）不需要。

## 待扩展

- **B站家族**：bilibili-cli 抓 CC 字幕，无字幕走 yt-dlp + faster-whisper。参考 `Ref/CLAUDE.md`
- **RSS 博客家族**：feedparser 解析，WebFetch 抓正文
- **播客家族**：RSS → 音频 → whisper 转录
- **RSS 发布端点**：Cloudflare R2 或 GitHub Pages（当前仅本地输出）
- **稳定后固化**：连续 N 次执行不调整流程时，开始写 `main.py`

## 相关项目

- `LT_News/` — 前身，单一信源（YT LT视界），并行运行中
- `Finn_ProSummary/` — 多源即时总结工具，设计理念参考来源
