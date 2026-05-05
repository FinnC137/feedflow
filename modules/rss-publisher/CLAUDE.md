# RSS Publisher — 模块文档

> 自包含的 RSS 2.0 发布模块。AI 产出文章数据 → Python 校验 → 纠错循环 → 生成 XML。
> 复用方式：复制整个 `modules/rss-publisher/` 目录到新项目，修改 `channel.json`。

## 工作流

```
AI 处理信源 → 生成 articles.json
     ↓
python build_rss.py --validate articles.json --channel channel.json
     ↓
┌─ 有 error → AI 读 errors JSON，修 articles.json，回到上一步
│
└─ 全部通过 → python build_rss.py --build articles.json  → rss.xml
```

**核心原则**：硬性规则由 Python 强校验，AI 无法绕过。AI 只需应对校验报错，修到通过为止。

## 文件清单

| 文件                          | 用途          |
| --------------------------- | ----------- |
| `build_rss.py`              | 校验 + 生成脚本   |
| `channel.json`              | 频道元信息，按项目修改 |
| `CLAUDE.md`                 | 本文件，AI 参考   |
| `examples/articles.json`    | 正确格式样例      |
| `examples/feed.example.xml` | 正确输出样例      |

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

### content_html 格式要求

**这是最容易出错的环节**。AI 处理生成的 HTML 全文必须满足：

1. **分段**：每个 `<p>` 只放 2-3 个句子，禁止连续超过 150 字不换行不拆段
2. **换行**：`<p>` 开始标签后、`</p>` 结束标签前必须有换行，源码中不得出现 200+ 字符的单行
3. **标点**：使用中文全角标点（，。、；：？！）

正确格式：

```html
<h2>【小标题】</h2>
<p>
第一段 2-3 句话，约 80-150 字。
第二句内容在这里。
</p>
<p>
第二段内容，也是 2-3 句话。
每个自然段独立一个 p 标签。
</p>
```

错误格式（另一个 AI 常犯）：

```html
<h2>【小标题】</h2>
<p>第一段内容。第二句。第三句。第四句。第五句。第六句。第七句。全部挤在一个 p 里，一个 section 只给一个 p，导致阅读器里看起来是一堵文字墙。</p>
<h2>【下一标题】</h2>
<p>又是一大段全部挤在一起不分段的文字。</p>
```

## AI 操作步骤

### 1. 生成 articles.json

处理完所有信源后，将文章数据汇总为 `articles.json`（格式见上方数据结构）。若已有现有文章，合并后按 pubDate 降序排列。

`pubDate` 用 RFC 822 UTC 格式：

```bash
date -u +"%a, %d %b %Y %H:%M:%S +0000"
```

### 2. 校验循环

```bash
python modules/rss-publisher/build_rss.py --validate articles.json --channel modules/rss-publisher/channel.json
```

输出示例：

```json
{
  "valid": false,
  "errors": [
    {
      "level": "error",
      "field": "articles[1].content_html.p[2]",
      "msg": "段落过长（179 字），超过 150 字限制",
      "fix": "拆分为 2-3 句一个 <p>"
    }
  ]
}
```

逐个阅读 `errors` 数组，按 `fix` 提示修改 `articles.json`，重新运行校验。循环直到 `"valid": true`。

### 3. 生成 rss.xml

```bash
python modules/rss-publisher/build_rss.py --build articles.json --channel modules/rss-publisher/channel.json --output rss.xml
```

### 4. W3C 最终验证

```bash
export https_proxy=http://172.22.240.1:7897
curl -s "https://validator.w3.org/feed/check.cgi?url=$(python -c 'import urllib.parse; print(urllib.parse.quote("FEED_URL", safe=""))')&output=soap12" | grep -E "validity|errorcount"
```

期望：`<m:validity>true</m:validity>` `<m:errorcount>0</m:errorcount>`

### 5. 推送

```bash
cd <项目根目录> && git add rss.xml output/ && git commit -m "Daily: ${DATE}" && git push
```

## 校验规则清单

以下规则由 Python 自动执行，`level: error` 会阻断生成：

| 规则                 | level | 说明                                                    |
| ------------------ | ----- | ----------------------------------------------------- |
| 必填字段               | error | title/link/guid_path/description/content_html/pubDate |
| link ≠ guid        | error | link 指外部源，guid 指 .md 永久链接                             |
| GUID 含中文           | error | 自动 percent-encode                                     |
| 段落 ≤150 字          | error | `<p>` 内纯文本超过则阻断                                       |
| HTML 含 `]]>`       | error | 会提前关闭 CDATA                                           |
| 单行 >200 字符         | warn  | 影响源码可读性                                               |
| description >150 字 | warn  | 自动截断                                                  |
| pubDate 排序         | warn  | 自动按降序重排                                               |
| lastBuildDate      | 自动    | 始终设为当前 UTC 时间                                         |
| 保留 20 条            | 自动    | 多余的自动裁剪                                               |

## 常见错误排查

| 症状                                   | 可能原因                   | 修复               |
| ------------------------------------ | ---------------------- | ---------------- |
| Folo 看不到新文章                          | `<link>` 和 `<guid>` 相同 | `<link>` 改指向外部源  |
| W3C 报 "IRI found where URL expected" | GUID 含中文               | Python 已自动处理     |
| 校验报段落过长                              | 一个 `<p>` 塞太多句子         | 拆分 2-3 句一个 `<p>` |
| Folo 显示旧内容                           | Folo 用 GUID 去重         | GUID 末尾加 `-v2`   |

## 集成方式

项目 CLAUDE.md 中引用：

```markdown
## RSS 发布

参见 `modules/rss-publisher/CLAUDE.md`，channel.json 已配好。
```
