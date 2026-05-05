"""load_sources.py — 从飞书多维表格加载信源配置。

用法：
  python modules/feishu-publisher/load_sources.py [--output cache.json]

流程：
  1. 调 lark-cli 拉取表格记录
  2. 转为 sources.yaml 兼容格式
  3. 写入本地缓存（API 失败时降级读取）
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# ── 配置 ──────────────────────────────────────
BASE_TOKEN = "BYTgbNqVnaeQKSsS6lJcMrjqnTf"
TABLE_ID = "tblhebgW3SLqmInU"
LARK_CLI = (
    "C:/Users/Administrator/AppData/Roaming/npm/"
    "node_modules/@larksuite/cli/bin/lark-cli.exe"
)

# URL → family 自动推断规则
FAMILY_RULES = [
    (lambda u: "youtube.com" in u or "youtu.be" in u, "youtube"),
    (lambda u: "bilibili.com" in u or u.startswith("BV"), "bilibili"),
    (lambda u: u.startswith("http"), "rss"),
]


def _infer_family(url: str) -> str:
    """从 URL/ID 格式自动推断信源家族。"""
    for check, family in FAMILY_RULES:
        if check(url):
            return family
    return "rss"  # 默认当作 RSS


def _run_lark(args: list[str], stdin_data: str | None = None) -> dict | None:
    """调用 lark-cli，返回解析后的 JSON。"""
    try:
        result = subprocess.run(
            [LARK_CLI] + args,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
        )
        stdout = result.stdout.strip()
        if not stdout:
            return None
        return json.loads(stdout)
    except Exception as e:
        print(f"[WARN] lark-cli 调用失败: {e}", file=sys.stderr)
        return None


def load_sources(output_path: str | None = None) -> list[dict[str, Any]]:
    """从飞书表格加载 active 信源列表。失败时降级读本地缓存。"""
    if output_path is None:
        module_dir = Path(__file__).resolve().parent
        output_path = str(module_dir / "sources_cache.json")

    # 1. 尝试从飞书拉取
    result = _run_lark([
        "base", "+record-list",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--format", "json",
        "--limit", "200",
        "--as", "user",
    ])

    if result and result.get("ok"):
        sources = _parse_response(result.get("data", {}))
        active_sources = [s for s in sources if s.get("status") == "active"]

        if active_sources:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(active_sources, f, ensure_ascii=False, indent=2)
            print(f"[OK] 从飞书加载了 {len(active_sources)} 个信源 → {output_path}")
            return active_sources

    # 2. 降级：读本地缓存
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        print(f"[WARN] 飞书拉取失败，降级使用本地缓存 ({len(cached)} 个信源)")
        return cached

    print("[ERROR] 飞书拉取失败且无本地缓存", file=sys.stderr)
    return []


def _parse_response(data: dict) -> list[dict[str, Any]]:
    """解析飞书 +record-list 返回的位置数组格式。

    API 返回格式：
      { "data": [[val, val, ...], ...],
        "fields": ["信源名称", "总结强度", ...],
        "record_id_list": ["rec...", ...] }
    """
    rows = data.get("data", [])
    field_names = data.get("fields", [])
    record_ids = data.get("record_id_list", [])

    # 构建 field_name → index 映射
    name_to_idx = {name: i for i, name in enumerate(field_names)}

    sources = []
    for i, row in enumerate(rows):
        # 跳过全 null 的空行（默认表带的占位行）
        if all(v is None for v in row):
            continue

        url = _row_val(row, name_to_idx, "URL/ID", "")
        # 显式类型优先，否则从 URL 推断
        explicit_type = _row_val(row, name_to_idx, "信源类型", "")
        short = _row_val(row, name_to_idx, "short_name", "")
        name = _row_val(row, name_to_idx, "信源名称", "")
        source = {
            "name": name,
            "short_name": short or name[:4] if len(name) >= 4 else name,
            "family": explicit_type or _infer_family(url),
            "url": url,
            "output_level": _row_val(row, name_to_idx, "总结强度", "default"),
            "filter_prompt": _row_val(row, name_to_idx, "特殊要求", ""),
            "status": _row_val(row, name_to_idx, "状态", "active"),
            "last_push": _row_val(row, name_to_idx, "最后推送", ""),
            "record_id": record_ids[i] if i < len(record_ids) else "",
        }
        if source["name"] and source["url"]:
            sources.append(source)
    return sources


def _row_val(row: list, name_to_idx: dict, field_name: str, default: Any) -> Any:
    """从位置数组中提取字段值。单选字段返回列表的第一个元素。"""
    idx = name_to_idx.get(field_name)
    if idx is None or idx >= len(row):
        return default
    val = row[idx]
    if val is None:
        return default
    if isinstance(val, list):
        return val[0] if val else default
    return val


def update_last_push(source_name: str, timestamp: str) -> bool:
    """更新指定信源的最后推送时间。"""
    # 直接拉 API 获取 record_id
    result = _run_lark([
        "base", "+record-list",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--format", "json",
        "--limit", "200",
        "--as", "user",
    ])
    if not result or not result.get("ok"):
        return False

    data = result.get("data", {})
    rows = data.get("data", [])
    field_names = data.get("fields", [])
    record_ids = data.get("record_id_list", [])
    name_idx = field_names.index("信源名称") if "信源名称" in field_names else -1

    for i, row in enumerate(rows):
        if name_idx >= 0 and i < len(record_ids):
            if row[name_idx] == source_name:
                update = _run_lark([
                    "base", "+record-upsert",
                    "--base-token", BASE_TOKEN,
                    "--table-id", TABLE_ID,
                    "--record-id", record_ids[i],
                    "--json", json.dumps({"最后推送": timestamp}),
                    "--as", "user",
                ])
                return update is not None and update.get("ok")
    return False


def _resolve_youtube_channel_url(name: str) -> str | None:
    """通过 YouTube 搜索，从频道名称反查频道首页 URL。"""
    import shutil

    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        print("[WARN] yt-dlp 未安装，无法自动搜索频道", file=sys.stderr)
        return None

    try:
        result = subprocess.run(
            [ytdlp, "--flat-playlist", "--print", "%(channel_id)s|%(uploader_id)s",
             f"ytsearch5:{name}"],
            capture_output=True, text=True, timeout=30, encoding="utf-8",
            env={**os.environ, "https_proxy": "http://172.22.240.1:7897"},
        )
        lines = [l.strip() for l in result.stdout.split("\n") if l.strip() and "|" in l]
        if not lines:
            return None

        # 提取出现最多的 channel_id 和对应的 uploader_id
        from collections import Counter
        pairs = [line.split("|", 1) for line in lines]
        cid_counts = Counter(p[0] for p in pairs)
        best_cid = cid_counts.most_common(1)[0][0]

        # 找到对应的 uploader_id
        uploader_id = ""
        for cid, uid in pairs:
            if cid == best_cid and uid and uid != "NA":
                uploader_id = uid
                break

        if uploader_id:
            url = f"https://www.youtube.com/@{uploader_id}/videos"
        else:
            url = f"https://www.youtube.com/channel/{best_cid}"

        print(f"[INFO] YouTube 搜索 '{name}' → {url}")
        return url
    except Exception as e:
        print(f"[WARN] YouTube 搜索失败: {e}", file=sys.stderr)
        return None


def _derive_short_name(name: str) -> str:
    """从完整信源名推导缩略名。取前 2-4 个中文字符作为辨识名。"""
    # 去掉常见后缀
    for suffix in ["啥书都读", "讲故事", "视界", "频道", "Channel", "Official"]:
        if name.endswith(suffix):
            short = name[:len(name) - len(suffix)]
            if short:
                return short
    # 兜底：前 4 个字符
    return name[:4] if len(name) >= 4 else name


def resolve_and_fill() -> list[dict]:
    """扫描 Feishu 表中缺失 url/short_name 的信源，自动补齐。"""
    result = _run_lark([
        "base", "+record-list",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--format", "json",
        "--limit", "200",
        "--as", "user",
    ])

    if not result or not result.get("ok"):
        print("[ERROR] 无法读取飞书表格", file=sys.stderr)
        return []

    data = result.get("data", {})
    rows = data.get("data", [])
    field_names = data.get("fields", [])
    record_ids = data.get("record_id_list", [])
    name_to_idx = {name: i for i, name in enumerate(field_names)}

    resolved = []
    for i, row in enumerate(rows):
        if all(v is None for v in row):
            continue
        if i >= len(record_ids):
            continue

        name = _row_val(row, name_to_idx, "信源名称", "")
        family = _row_val(row, name_to_idx, "信源类型", "")
        url = _row_val(row, name_to_idx, "URL/ID", "")
        short = _row_val(row, name_to_idx, "short_name", "")

        if not name:
            continue

        patches = {}
        needs_update = False

        # 自动补齐 YouTube 频道首页 URL
        if (not url or url.strip() == "") and family == "youtube":
            print(f"[INFO] 信源 '{name}' 缺少频道 URL，自动搜索...")
            channel_url = _resolve_youtube_channel_url(name)
            if channel_url:
                patches["URL/ID"] = channel_url
                needs_update = True

        # 自动补齐 short_name
        if not short or short.strip() == "":
            derived = _derive_short_name(name)
            patches["short_name"] = derived
            print(f"[INFO] 信源 '{name}' 缺少缩略名，自动推导: {derived}")
            needs_update = True

        if needs_update:
            update = _run_lark([
                "base", "+record-upsert",
                "--base-token", BASE_TOKEN,
                "--table-id", TABLE_ID,
                "--record-id", record_ids[i],
                "--json", json.dumps(patches, ensure_ascii=False),
                "--as", "user",
            ])
            if update and update.get("ok"):
                print(f"[OK] '{name}' 已补齐: {patches}")
                resolved.append({"name": name, "patches": patches})
            else:
                print(f"[WARN] '{name}' 补齐失败", file=sys.stderr)

    return resolved


def _find_first_empty_record_id() -> str | None:
    """查找第一条全空行的 record_id，用于填充最小空位。"""
    result = _run_lark([
        "base", "+record-list",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--format", "json",
        "--limit", "200",
        "--as", "user",
    ])
    if not result or not result.get("ok"):
        return None

    data = result.get("data", {})
    rows = data.get("data", [])
    record_ids = data.get("record_id_list", [])

    for i, row in enumerate(rows):
        if all(v is None for v in row) and i < len(record_ids):
            return record_ids[i]
    return None


def add_or_update_source(
    name: str,
    url: str,
    family: str = "",
    short_name: str = "",
    output_level: str = "default",
    filter_prompt: str = "",
    status: str = "active",
) -> bool:
    """添加或更新信源记录。优先填充最小空位行，无空位则追加新行。"""
    # 先尝试查找已有记录（按名称匹配）
    result = _run_lark([
        "base", "+record-list",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--format", "json",
        "--limit", "200",
        "--as", "user",
    ])

    existing_id: str | None = None
    if result and result.get("ok"):
        data = result.get("data", {})
        rows = data.get("data", [])
        field_names = data.get("fields", [])
        record_ids = data.get("record_id_list", [])
        name_idx = field_names.index("信源名称") if "信源名称" in field_names else -1

        for i, row in enumerate(rows):
            if name_idx >= 0 and i < len(record_ids):
                if row[name_idx] == name:
                    existing_id = record_ids[i]
                    break

    # 无已有记录时，尝试找最小空位
    if not existing_id:
        existing_id = _find_first_empty_record_id()

    # 推断 family
    if not family:
        family = _infer_family(url)

    record_data = json.dumps({
        "信源名称": name,
        "short_name": short_name or name,
        "URL/ID": url,
        "信源类型": family,
        "总结强度": output_level,
        "特殊要求": filter_prompt,
        "状态": status,
    }, ensure_ascii=False)

    upsert_args = [
        "base", "+record-upsert",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--json", record_data,
        "--as", "user",
    ]
    if existing_id:
        upsert_args.extend(["--record-id", existing_id])

    update = _run_lark(upsert_args)
    ok = update is not None and update.get("ok")
    if ok:
        slot = f"空位 {existing_id}" if existing_id and not result else "新行"
        print(f"[OK] 信源 '{name}' 已写入 ({slot})")
    return ok


# ── CLI ────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="从飞书多维表格加载/管理信源配置"
    )
    sub = parser.add_subparsers(dest="action")

    # load（默认）
    load_p = sub.add_parser("load", help="加载 active 信源列表")
    load_p.add_argument("--output", default=None,
                        help="缓存输出路径")

    # add
    add_p = sub.add_parser("add", help="添加或更新信源")
    add_p.add_argument("--name", required=True, help="信源名称")
    add_p.add_argument("--url", required=True, help="URL 或 Channel ID")
    add_p.add_argument("--short-name", default="", help="简短辨识名（标题用）")
    add_p.add_argument("--family", default="", help="信源类型（空则自动推断）")
    add_p.add_argument("--level", default="default", help="总结强度")
    add_p.add_argument("--filter", default="", help="特殊要求")
    add_p.add_argument("--status", default="active", help="状态")

    # resolve
    sub.add_parser("resolve", help="自动补齐缺失的 YouTube ID 和缩略名")

    # update-push
    push_p = sub.add_parser("update-push", help="回写最后推送时间")
    push_p.add_argument("--name", required=True, help="信源名称")
    push_p.add_argument("--time", default=None, help="时间戳（默认当前 CST）")

    args = parser.parse_args()

    if args.action == "add":
        ok = add_or_update_source(
            name=args.name, url=args.url, family=args.family,
            short_name=getattr(args, 'short_name', '') or '',
            output_level=args.level, filter_prompt=args.filter,
            status=args.status,
        )
        sys.exit(0 if ok else 1)
    elif args.action == "resolve":
        resolved = resolve_and_fill()
        if resolved:
            # 刷新缓存
            load_sources()
        sys.exit(0 if resolved else 1)
    elif args.action == "update-push":
        from datetime import datetime, timezone, timedelta
        ts = args.time
        if not ts:
            ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
        ok = update_last_push(args.name, ts)
        sys.exit(0 if ok else 1)
    else:
        # 默认 load
        output = args.output if hasattr(args, 'output') else None
        sources = load_sources(output)
        if sources:
            print(json.dumps(sources, ensure_ascii=False, indent=2))
        else:
            sys.exit(1)
