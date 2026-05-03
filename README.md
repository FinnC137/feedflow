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

## 相关项目

- `LT_News/` — 前身，单一信源（YT LT视界），并行运行中
- `Finn_ProSummary/` — 多源即时总结工具，设计理念参考来源
