"""
RSS Publisher — 校验 + 渲染 + 生成

AI 只填 sections 纯文本数组，HTML 和 XML 由本脚本生成。

用法：
  python build_rss.py --validate articles.json    # 校验，返回错误 JSON
  python build_rss.py --build articles.json        # 校验 → 渲染 → 输出 rss.xml
"""

import json, sys, os, re
from datetime import datetime, timezone
from urllib.parse import quote, unquote
from email.utils import format_datetime

CHANNEL_DEFAULTS = {
    "title": "FeedFlow News",
    "link": "https://example.github.io/project/",
    "description": "AI-powered RSS feed",
    "language": "zh-CN",
    "feed_url": "https://example.github.io/project/rss.xml",
}


# ── HTML 渲染 ────────────────────────────────────────────────

def render_article_html(article: dict) -> str:
    """从 sections 结构化数据生成完整的 content:encoded HTML"""
    parts = []

    # 标题
    parts.append(f"<h1>{escape_xml(article['title'])}</h1>")

    # 来源行
    source_label = article.get("source_label", "")
    source_url = article.get("source_url", "")
    if source_label and source_url:
        parts.append(f"<p>来源：{escape_xml(source_label)} | {escape_xml(source_url)}</p>")
    elif source_label:
        parts.append(f"<p>来源：{escape_xml(source_label)}</p>")
    elif source_url:
        parts.append(f"<p>来源：{escape_xml(source_url)}</p>")

    parts.append("<hr>")

    # 段落区
    for sec in article.get("sections", []):
        heading = sec.get("heading", "")
        if heading:
            parts.append(f"<h2>{escape_xml(heading)}</h2>")
        for para in sec.get("paragraphs", []):
            para = para.strip()
            if para:
                parts.append(f"<p>{escape_xml(para)}</p>")

    parts.append("<hr>")
    return "\n".join(parts)


# ── 校验 ──────────────────────────────────────────────────────

def validate(articles, channel=None):
    """返回 [{"level": "error"|"warn", "field": "...", "msg": "..."}]"""
    errors = []
    required = ["title", "link", "guid_path", "description", "pubDate"]

    for i, a in enumerate(articles):
        idx = f"articles[{i}]"

        # 必填字段
        for f in required:
            if not a.get(f):
                errors.append({"level": "error", "field": f"{idx}.{f}",
                               "msg": f"缺少必填字段 {f}"})

        # sections 必填
        sections = a.get("sections", [])
        if not sections:
            errors.append({"level": "error", "field": f"{idx}.sections",
                           "msg": "缺少 sections 字段，至少需要 1 个 section"})

        # 校验 sections 结构
        for si, sec in enumerate(sections):
            sidx = f"{idx}.sections[{si}]"
            if not sec.get("heading"):
                errors.append({"level": "error", "field": f"{sidx}.heading",
                               "msg": "heading 为空，每节必须有标题"})
            paras = sec.get("paragraphs", [])
            if not paras:
                errors.append({"level": "warn", "field": f"{sidx}.paragraphs",
                               "msg": "paragraphs 为空"})
            for pi, p in enumerate(paras):
                if len(p) > 150:
                    errors.append({"level": "error", "field": f"{sidx}.paragraphs[{pi}]",
                                   "msg": f"段落过长（{len(p)} 字），超过 150 字限制",
                                   "fix": "拆分为 2-3 句一个段落"})

        # link ≠ guid
        link = a.get("link", "")
        guid_path = a.get("guid_path", "")
        if link and guid_path:
            site = (channel or {}).get("link", CHANNEL_DEFAULTS["link"])
            full_guid = site.rstrip("/") + "/" + guid_path.lstrip("/")
            if link.rstrip("/") == full_guid.rstrip("/"):
                errors.append({"level": "error", "field": f"{idx}.link",
                               "msg": "link 和 guid 指向同一 URL",
                               "fix": "link 改为原始外部源 URL"})

        # description 长度
        desc = a.get("description", "")
        if len(desc) > 150:
            errors.append({"level": "warn", "field": f"{idx}.description",
                           "msg": f"description 超过 150 字（当前 {len(desc)} 字）",
                           "fix": "精简到 150 字以内"})

        # GUID 中文检查
        if guid_path and re.search(r'[一-鿿]', guid_path):
            encoded = quote(guid_path, safe='/')
            errors.append({"level": "error", "field": f"{idx}.guid_path",
                           "msg": "GUID 路径含中文字符，需 percent-encode",
                           "fix": f"改为 {encoded}"})

    # pubDate 排序检查
    pubdates = []
    for a in articles:
        try:
            pubdates.append(datetime.strptime(a.get("pubDate", ""),
                            "%a, %d %b %Y %H:%M:%S +0000"))
        except ValueError:
            pass
    if len(pubdates) == len(articles) and pubdates != sorted(pubdates, reverse=True):
        errors.append({"level": "warn", "field": "articles",
                       "msg": "articles 未按 pubDate 降序排列",
                       "fix": "按 pubDate 降序重新排列"})

    return errors


# ── 生成 RSS ──────────────────────────────────────────────────

def build_rss(articles, channel=None):
    """校验通过后，渲染 HTML 并生成完整 rss.xml 字符串"""
    ch = {**CHANNEL_DEFAULTS, **(channel or {})}

    # 自动修正：GUID encode
    for a in articles:
        gp = a.get("guid_path", "")
        if re.search(r'[一-鿿]', gp):
            a["guid_path"] = quote(gp, safe='/')

    now = datetime.now(timezone.utc)
    lbd = format_datetime(now, usegmt=True)

    items_xml = []
    for a in articles:
        site = ch["link"].rstrip("/")
        guid_url = site + "/" + a["guid_path"].lstrip("/")
        guid_url = quote(unquote(guid_url), safe='/:@')

        desc = a["description"]
        if len(desc) > 150:
            desc = desc[:147] + "..."

        content_html = render_article_html(a)

        # CDATA 安全检查
        if ']]>' in content_html:
            content_html = content_html.replace(']]>', ']]]]><![CDATA[>')

        item = f"""  <item>
    <title>{escape_xml(a['title'])}</title>
    <link>{escape_xml(a['link'])}</link>
    <guid isPermaLink="true">{escape_xml(guid_url)}</guid>
    <description>{escape_xml(desc)}</description>
    <content:encoded><![CDATA[{content_html}]]></content:encoded>
    <pubDate>{a['pubDate']}</pubDate>
  </item>"""
        items_xml.append(item)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
  <title>{escape_xml(ch['title'])}</title>
  <link>{escape_xml(ch['link'])}</link>
  <description>{escape_xml(ch['description'])}</description>
  <language>{escape_xml(ch['language'])}</language>
  <atom:link href="{escape_xml(ch['feed_url'])}" rel="self" type="application/rss+xml"/>
  <lastBuildDate>{lbd}</lastBuildDate>
{chr(10).join(items_xml)}
</channel>
</rss>"""


def escape_xml(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ── CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--validate", action="store_true")
    p.add_argument("--build", action="store_true")
    p.add_argument("input", help="articles.json 路径")
    p.add_argument("--channel", help="channel.json 路径（可选）")
    p.add_argument("--output", default="rss.xml", help="输出 RSS 文件路径")
    args = p.parse_args()

    with open(args.input, encoding="utf-8") as f:
        articles = json.load(f)

    channel = None
    if args.channel and os.path.exists(args.channel):
        with open(args.channel, encoding="utf-8") as f:
            channel = json.load(f)

    if args.validate:
        errs = validate(articles, channel)
        print(json.dumps({"valid": len([e for e in errs if e["level"] == "error"]) == 0,
                          "errors": errs}, ensure_ascii=False, indent=2))
        sys.exit(0 if len([e for e in errs if e["level"] == "error"]) == 0 else 1)

    if args.build:
        errs = validate(articles, channel)
        fatals = [e for e in errs if e["level"] == "error"]
        if fatals:
            print(json.dumps({"valid": False, "errors": fatals}, ensure_ascii=False, indent=2))
            sys.exit(1)
        xml = build_rss(articles, channel)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(xml)
        warns = [e for e in errs if e["level"] == "warn"]
        print(json.dumps({"valid": True, "warnings": warns, "output": args.output},
                         ensure_ascii=False, indent=2))
