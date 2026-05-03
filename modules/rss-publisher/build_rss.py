"""
RSS Publisher — 校验 + 生成
用法：
  python build_rss.py --validate articles.json   # 仅校验，返回错误 JSON
  python build_rss.py --build articles.json       # 校验通过后输出 rss.xml
"""

import json, sys, os, re
from datetime import datetime, timezone
from urllib.parse import quote, unquote
from email.utils import format_datetime
from pathlib import Path

CHANNEL_DEFAULTS = {
    "title": "FeedFlow News",
    "link": "https://example.github.io/project/",
    "description": "AI-powered RSS feed",
    "language": "zh-CN",
    "feed_url": "https://example.github.io/project/rss.xml",
}


# ── validation ──────────────────────────────────────────────

def validate(articles, channel=None):
    """返回 [{"level": "error"|"warn", "field": "...", "msg": "..."}]"""
    errors = []
    required = ["title", "link", "guid_path", "description", "content_html", "pubDate"]

    for i, a in enumerate(articles):
        idx = f"articles[{i}]"

        # 必填字段
        for f in required:
            if not a.get(f):
                errors.append({"level": "error", "field": f"{idx}.{f}", "msg": f"缺少必填字段 {f}"})

        # link ≠ guid（用 guid_path 推算完整 GUID URL 后比较）
        link = a.get("link", "")
        guid_path = a.get("guid_path", "")
        if link and guid_path:
            site = (channel or {}).get("link", CHANNEL_DEFAULTS["link"])
            full_guid = site.rstrip("/") + "/" + guid_path.lstrip("/")
            if link.rstrip("/") == full_guid.rstrip("/"):
                errors.append({"level": "error", "field": f"{idx}.link",
                               "msg": "link 和 guid 指向同一 URL，link 必须指向外部源", "fix": "将 link 改为原始外部源 URL"})

        # description 长度
        desc = a.get("description", "")
        if len(desc) > 150:
            errors.append({"level": "warn", "field": f"{idx}.description",
                           "msg": f"description 超过 150 字（当前 {len(desc)} 字）", "fix": "精简到 150 字以内"})

        # content_html 段落检查
        html = a.get("content_html", "")
        para_errors = check_paragraphs(html, idx)
        errors.extend(para_errors)

        # GUID 中文检查
        if guid_path:
            if re.search(r'[一-鿿]', guid_path):
                encoded = quote(guid_path, safe='/')
                errors.append({"level": "error", "field": f"{idx}.guid_path",
                               "msg": f"GUID 路径含中文字符，需 percent-encode", "fix": f"改为 {encoded}"})

    # pubDate 排序检查
    pubdates = []
    for a in articles:
        try:
            pubdates.append(datetime.strptime(a.get("pubDate", ""), "%a, %d %b %Y %H:%M:%S +0000"))
        except ValueError:
            pass
    if len(pubdates) == len(articles) and pubdates != sorted(pubdates, reverse=True):
        errors.append({"level": "warn", "field": "articles",
                       "msg": "articles 未按 pubDate 从新到旧排列", "fix": "按 pubDate 降序重新排列"})

    return errors


def check_paragraphs(html, idx):
    """检查 HTML 段落格式"""
    errors = []
    # 提取所有 <p>...</p> 内容
    paras = re.findall(r'<p>(.*?)</p>', html, re.DOTALL)
    for pi, p in enumerate(paras):
        text = p.strip()
        # 去掉 HTML 标签后统计纯文本字数
        clean = re.sub(r'<[^>]+>', '', text)
        if len(clean) > 150:
            errors.append({"level": "error", "field": f"{idx}.content_html.p[{pi}]",
                           "msg": f"段落过长（{len(clean)} 字），超过 150 字限制", "fix": "拆分为 2-3 句一个 <p>"})

    # 源码行长度检查
    for li, line in enumerate(html.split('\n')):
        if len(line) > 200:
            errors.append({"level": "warn", "field": f"{idx}.content_html",
                           "msg": f"源码第 {li+1} 行过长（{len(line)} 字符），影响可读性", "fix": "在标签处换行"})

    # 检查 CDATA 陷阱：内容中出现 ]]>
    if ']]>' in html:
        errors.append({"level": "error", "field": f"{idx}.content_html",
                       "msg": "HTML 内容包含 ]]>，会提前关闭 CDATA", "fix": "替换为 ]]]]><![CDATA[>"})

    return errors


# ── build ───────────────────────────────────────────────────

def build_rss(articles, channel=None):
    """校验通过后，生成完整 rss.xml 字符串"""
    ch = {**CHANNEL_DEFAULTS, **(channel or {})}

    # 自动修正：GUID encode
    for a in articles:
        gp = a.get("guid_path", "")
        if re.search(r'[一-鿿]', gp):
            a["guid_path"] = quote(gp, safe='/')

    # 自动修正：lastBuildDate
    now = datetime.now(timezone.utc)
    lbd = format_datetime(now, usegmt=True)

    items_xml = []
    for a in articles:
        site = ch["link"].rstrip("/")
        guid_url = site + "/" + a["guid_path"].lstrip("/")
        guid_url = quote(unquote(guid_url), safe='/:@')

        # 截断过长的 description
        desc = a["description"]
        if len(desc) > 150:
            desc = desc[:147] + "..."

        item = f"""  <item>
    <title>{escape_xml(a['title'])}</title>
    <link>{escape_xml(a['link'])}</link>
    <guid isPermaLink="true">{escape_xml(guid_url)}</guid>
    <description>{escape_xml(desc)}</description>
    <content:encoded><![CDATA[{a['content_html']}]]></content:encoded>
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


# ── CLI ─────────────────────────────────────────────────────

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
