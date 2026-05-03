# RSS Publisher — AI 操作模块

> 自包含的 RSS 2.0 发布模块。本文件可被任何 AI 读取并执行，不依赖 Python 脚本。
> 复用方式：复制整个 `modules/rss-publisher/` 目录到新项目，修改 `<channel>` 元信息。

## 输入约定

调用方（项目 CLAUDE.md）应提供以下信息：

| 参数 | 说明 | 示例 |
|------|------|------|
| `FEED_PATH` | RSS 文件在仓库中的路径 | `rss.xml` |
| `SITE_URL` | GitHub Pages 站点根 URL | `https://xxx.github.io/project/` |
| `FEED_URL` | RSS 文件的完整 URL | `https://xxx.github.io/project/rss.xml` |
| `CHANNEL_TITLE` | feed 标题 | `FeedFlow 新闻聚合` |
| `CHANNEL_DESC` | feed 描述 | `多信源 AI 处理新闻摘要` |
| `OUTPUT_DIR` | 文章输出目录（相对于仓库根） | `output/` |

每篇文章（item）的数据结构：

```python
{
    "title": "source_name — 2026-05-03",        # 标题
    "link": "https://www.youtube.com/watch?v=xxx",  # 原始外部源 URL
    "guid_path": "output/2026-05-03/文章名.md",     # 相对于仓库根的路径
    "description": "纯文本摘要，≤150字",              # 纯文本，无 HTML
    "content_html": "<h1>...</h1><p>...</p>",        # HTML 全文
    "pubDate": "Sun, 03 May 2026 09:00:00 +0000",   # RFC 822 UTC 格式
}
```

## 生成清单（逐条执行，不可跳过）

### 第 1 步：读取现有 feed

如果 `rss.xml` 已存在且有内容，解析出所有现有 `<item>`。如果不存在，从模板创建空 feed。

### 第 2 步：插入新 item（按时间排序）

**关键**：不是 append 到末尾。必须按 `<pubDate>` 从新到旧插入到正确位置。

用 Python 伪代码：
```python
from datetime import datetime
from email.utils import parsedate_to_datetime

def sort_items(items):
    return sorted(items, key=lambda i: parsedate_to_datetime(i['pubDate']), reverse=True)
```

### 第 3 步：生成 GUID

**关键**：`<guid>` 是永久标识，值必须是纯 ASCII URL。中文路径必须 percent-encode。

```python
from urllib.parse import quote

guid_url = f"{SITE_URL}{article['guid_path']}"
guid_url = quote(guid_url, safe='/:@')  # 编码中文，保留 URL 结构字符
```

错误示例：`https://xxx.github.io/output/2026-05-03/LT视界.md`（含中文，违反 RSS 2.0 规范）
正确示例：`https://xxx.github.io/output/2026-05-03/LT%E8%A7%86%E7%95%8C.md`

### 第 4 步：生成 `<item>` XML

**关键规则**（违反将导致 RSS 阅读器不显示文章）：

1. **`<link>` ≠ `<guid>`**：`<link>` 指向原始外部源（YouTube URL、博客 URL 等），`<guid>` 指向 GitHub Pages 上的 `.md` 永久链接。两者绝不能相同。
2. **`<description>`**：纯文本，≤ 150 字，不含 HTML 标签。
3. **`<content:encoded>`**：HTML 全文，必须用 `<![CDATA[...]]>` 包裹。
4. **CDATA 陷阱**：如果 HTML 内容中出现 `]]>`（极罕见），需替换为 `]]]]><![CDATA[>`。

模板：
```xml
<item>
  <title>{{title}}</title>
  <link>{{原始外部源 URL}}</link>
  <guid isPermaLink="true">{{URL-encoded GUID}}</guid>
  <description>{{纯文本摘要}}</description>
  <content:encoded><![CDATA[{{HTML 全文}}]]></content:encoded>
  <pubDate>{{pubDate}}</pubDate>
</item>
```

### 第 5 步：更新 lastBuildDate

**每次修改 feed 必须更新**。取当前 UTC 时间，格式为 RFC 822：

```bash
date -u +"%a, %d %b %Y %H:%M:%S +0000"
```

### 第 6 步：裁剪到 20 条

只保留最近 20 条 item，多余的整段删除（从 `<item>` 到 `</item>`）。

### 第 7 步：组装完整 XML

必须声明的命名空间：`xmlns:atom` 和 `xmlns:content`。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
  <title>{{CHANNEL_TITLE}}</title>
  <link>{{SITE_URL}}</link>
  <description>{{CHANNEL_DESC}}</description>
  <language>zh-CN</language>
  <atom:link href="{{FEED_URL}}" rel="self" type="application/rss+xml"/>
  <lastBuildDate>{{当前 UTC RFC 822 时间}}</lastBuildDate>
  {{按 pubDate 从新到旧排列的所有 item}}
</channel>
</rss>
```

### 第 8 步：写入文件

直接覆盖仓库根目录的 `rss.xml`。

## 验证

用 W3C Feed Validator API 校验（无需浏览器）：

```bash
curl -s "https://validator.w3.org/feed/check.cgi?url=$(python -c 'import urllib.parse; print(urllib.parse.quote("FEED_URL", safe=""))')&output=soap12" | grep -E "validity|errorcount|warningcount"
```

期望输出：
```
<m:validity>true</m:validity>
<m:errorcount>0</m:errorcount>
<m:warningcount>0</m:warningcount>
```

如果不是这个结果，检查 `<m:errorlist>` 中的具体错误信息。

## 常见错误排查

| 症状 | 可能原因 | 修复 |
|------|----------|------|
| Folo 看不到新文章 | `<link>` 和 `<guid>` 相同 | `<link>` 改指向外部源 |
| W3C 报 "IRI found where URL expected" | GUID 含中文 | `urllib.parse.quote()` |
| 文章顺序错乱 | 新 item 直接 append 没按 pubDate 排序 | 按 pubDate 从新到旧插入 |
| 阅读器不刷新 | `<lastBuildDate>` 没更新 | 每次修改必须更新 |
| Folo 显示旧内容 | Folo 用 GUID 去重，相同 GUID 视为同一篇 | 内容有实质修改时 GUID 末尾加 `-v2` |

## 集成方式

项目 CLAUDE.md 中只需一行引用 + 参数表：

```markdown
## RSS 发布

参见 `modules/rss-publisher/CLAUDE.md`

本项目参数：
- FEED_PATH: rss.xml
- SITE_URL: https://finnc137.github.io/feedflow/
- FEED_URL: https://finnc137.github.io/feedflow/rss.xml
- CHANNEL_TITLE: FeedFlow 新闻聚合
- CHANNEL_DESC: 多信源 AI 处理新闻摘要
- OUTPUT_DIR: output/
```
