"""deliver.py — 将 Markdown 文章发布到飞书 Wiki。

用法：
  python modules/feishu-publisher/deliver.py <markdown_path> [--channel channel.json]

流程：
  1. 按信源创建/复用子目录页（镜像 output/ 层级）
  2. 在信源页下创建 wiki 子页面（标题：短名_主题_时间戳）
  3. 将 Markdown 转为飞书 docx blocks（支持 heading / 粗体 / 链接）
  4. 分批写入 blocks 到文档
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

CST = timezone(timedelta(hours=8))


# ── 默认配置 ──────────────────────────────────
DEFAULT_CONFIG: dict[str, Any] = {
    "parent_node_token": "PsYTwWYQoiqQCAk43fZcGYaPnIF",
    "lark_cli": (
        "C:/Users/Administrator/AppData/Roaming/npm/"
        "node_modules/@larksuite/cli/bin/lark-cli.exe"
    ),
    "identity": "user",
    "chunk_size": 45,
    "source_parents": {},  # source_name → feishu node_token
}


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """加载 channel.json 配置，合并默认值。"""
    if config_path is None:
        module_dir = Path(__file__).resolve().parent
        config_path = str(module_dir / "channel.json")

    config = dict(DEFAULT_CONFIG)
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            # 确保 source_parents 不被覆盖
            if "source_parents" in loaded:
                config["source_parents"] = loaded.pop("source_parents")
            config.update(loaded)
            if "source_parents" not in config:
                config["source_parents"] = {}
    return config


def _save_source_parent(config_path: str, config: dict, source_name: str,
                        node_token: str) -> None:
    """持久化 source → parent node_token 映射到 channel.json。"""
    module_dir = Path(__file__).resolve().parent
    cp = config_path or str(module_dir / "channel.json")

    existing: dict = {}
    if os.path.exists(cp):
        with open(cp, "r", encoding="utf-8") as f:
            existing = json.load(f)

    if "source_parents" not in existing:
        existing["source_parents"] = {}
    existing["source_parents"][source_name] = node_token

    with open(cp, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


def _load_short_names() -> dict[str, str]:
    """从 sources_cache.json 加载 source_name → short_name 映射。"""
    module_dir = Path(__file__).resolve().parent
    cache_path = str(module_dir / "sources_cache.json")
    mapping: dict[str, str] = {}
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            sources = json.load(f)
        for s in sources:
            name = s.get("name", "")
            short = s.get("short_name", "") or name
            # 截取前4个中文字符作为兜底缩写
            if not short and name:
                short = name[:4] if len(name) >= 4 else name
            if name:
                mapping[name] = short
    return mapping


def publish(md_path: str, config: dict[str, Any] | None = None) -> str | None:
    """发布一篇 Markdown 文章到飞书 Wiki。返回飞书页面 URL，失败返回 None。"""
    if config is None:
        config = load_config()

    # 0. 解析信源名称（从路径 output/DATE/source_name/ 提取）
    source_name = _extract_source_name(md_path)

    # 1. 读取 Markdown
    if not os.path.exists(md_path):
        print(f"[ERROR] 文件不存在: {md_path}", file=sys.stderr)
        return None
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    # 2. 生成标题（短名_主题_时间戳）
    short_names = _load_short_names()
    short_name = short_names.get(source_name, source_name[:4] if len(source_name) >= 4 else source_name)
    title = _make_title(md_text, short_name)

    # 3. 获取或创建信源级父页面
    source_parent = _get_or_create_source_parent(
        source_name, config, Path(md_path).resolve()
    )
    if not source_parent:
        print(f"[ERROR] 无法获取信源父页面: {source_name}", file=sys.stderr)
        return None

    # 4. 在信源父页面下创建 wiki 子页面
    node_info = _create_wiki_node(title, source_parent, config)
    if not node_info:
        return None

    obj_token = node_info["obj_token"]
    node_token = node_info["node_token"]
    url = f"https://www.feishu.cn/wiki/{node_token}"
    print(f"[INFO] 页面已创建: {url}")

    # 5. Markdown → Feishu blocks
    blocks = _md_to_blocks(md_text)
    print(f"[INFO] {len(blocks)} 个 blocks")

    # 6. 写入 blocks
    ok = _write_blocks(obj_token, blocks, config)
    if ok:
        print(f"[OK] 发布成功: {url}")
        return url
    else:
        print(f"[WARN] 内容写入失败，页面为空: {url}", file=sys.stderr)
        return url


def _extract_source_name(md_path: str) -> str:
    """从路径 output/DATE/source_name/xxx.md 提取信源名称。"""
    parts = Path(md_path).parts
    # 找到 "output" 后的第二级目录（DATE 后的 source_name）
    for i, p in enumerate(parts):
        if p == "output" and i + 2 < len(parts):
            return parts[i + 2]
    # Fallback：用父目录名
    return Path(md_path).parent.name


# ── 标题生成 ──────────────────────────────────


def _make_title(md_text: str, short_name: str) -> str:
    """生成标题：短名_主题_YYYYMMDD_HHMM。主题从 H1 或首个 ## 提取。"""
    topic = ""
    for line in md_text.split("\n"):
        stripped = line.strip()
        # H1（如果有的话）
        if stripped.startswith("# ") and not stripped.startswith("## "):
            raw = stripped[2:]
            for sep in (" — ", "_"):
                if raw.startswith(short_name + sep):
                    raw = raw[len(short_name) + len(sep):]
                    break
            raw = re.sub(r'\s*[—\-_]\s*\d{8}[_\-]\d{4}.*$', '', raw)
            topic = raw.strip()
            break

    # H1 已去掉时，用首个 ## 小标题作为主题
    if not topic:
        for line in md_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("## "):
                topic = stripped[3:].strip()
                break

    if not topic:
        topic = "未命名"

    ts = datetime.now(CST).strftime("%Y%m%d_%H%M")
    return f"{short_name}_{topic}_{ts}"


# ── 信源级父页面管理 ──────────────────────────


def _get_or_create_source_parent(
    source_name: str,
    config: dict[str, Any],
    md_path: Path,
) -> str | None:
    """获取或创建信源级父页面，返回其 node_token。"""
    # 1. 检查缓存
    source_parents = config.get("source_parents", {})
    if source_name in source_parents:
        return source_parents[source_name]

    # 2. 检查是否已存在同名子页面
    root_parent = config["parent_node_token"]
    existing = _find_child_by_title(root_parent, source_name, config)
    if existing:
        source_parents[source_name] = existing
        config["source_parents"] = source_parents
        # 持久化
        module_dir = Path(__file__).resolve().parent
        _save_source_parent(str(module_dir / "channel.json"), config,
                           source_name, existing)
        print(f"[INFO] 复用已有信源页: {source_name} → {existing}")
        return existing

    # 3. 创建新的信源父页面
    print(f"[INFO] 创建信源父页面: {source_name}")
    result = _run_lark([
        "wiki", "+node-create",
        "--title", source_name,
        "--parent-node-token", root_parent,
        "--as", config.get("identity", "user"),
    ], config)

    if result and result.get("ok"):
        node_token = result["data"]["node_token"]
        source_parents[source_name] = node_token
        config["source_parents"] = source_parents
        module_dir = Path(__file__).resolve().parent
        _save_source_parent(str(module_dir / "channel.json"), config,
                           source_name, node_token)
        print(f"[OK] 信源父页面已创建: {source_name} → {node_token}")
        return node_token

    print(f"[ERROR] 创建信源父页面失败: {result}", file=sys.stderr)
    return None


def _find_child_by_title(
    parent_token: str,
    title: str,
    config: dict[str, Any],
) -> str | None:
    """在父页面下查找指定标题的子页面，返回 node_token。"""
    result = _run_lark([
        "api", "GET",
        f"/open-apis/wiki/v2/spaces/get_node?token={parent_token}",
        "--as", config.get("identity", "user"),
    ], config)

    if not result or result.get("code") != 0:
        return None

    data = result.get("data", {})
    node = data.get("node", data)

    # 查直接子节点（API 返回的 children 可能为空，需另查）
    children_result = _run_lark([
        "api", "GET",
        f"/open-apis/wiki/v2/spaces/{node.get('space_id','')}/nodes/{parent_token}/children",
        "--as", config.get("identity", "user"),
    ], config)

    if children_result and children_result.get("code") == 0:
        for child in children_result.get("data", {}).get("children", []):
            if child.get("title") == title:
                return child.get("node_token")

    return None


# ── 飞书 Wiki 操作 ────────────────────────────


def _run_lark(
    args: list[str],
    config: dict[str, Any],
    stdin_data: str | None = None,
) -> dict | None:
    """调用 lark-cli，返回解析后的 JSON。"""
    try:
        cmd = [config["lark_cli"]] + args
        result = subprocess.run(
            cmd,
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


def _create_wiki_node(
    title: str,
    parent_token: str,
    config: dict[str, Any],
) -> dict | None:
    """在指定父页面下创建 wiki 子页面。"""
    identity = config.get("identity", "user")
    result = _run_lark([
        "wiki", "+node-create",
        "--title", title,
        "--parent-node-token", parent_token,
        "--as", identity,
    ], config)

    if result and result.get("ok"):
        return result.get("data")

    print(f"[ERROR] 创建 wiki 页面失败: {result}", file=sys.stderr)
    return None


def _write_blocks(
    obj_token: str,
    blocks: list[dict],
    config: dict[str, Any],
) -> bool:
    """分批写入 docx blocks。"""
    chunk_size = config.get("chunk_size", 45)
    identity = config.get("identity", "user")
    total_batches = (len(blocks) + chunk_size - 1) // chunk_size
    all_ok = True

    for start in range(0, len(blocks), chunk_size):
        chunk = blocks[start : start + chunk_size]
        payload = json.dumps(
            {"children": chunk, "index": 0}, ensure_ascii=False
        )

        result = _run_lark([
            "api", "POST",
            f"/open-apis/docx/v1/documents/{obj_token}"
            f"/blocks/{obj_token}/children",
            "--data", "-",
            "--as", identity,
        ], config, stdin_data=payload)

        batch_num = start // chunk_size + 1
        if result and result.get("code") == 0:
            print(f"  [OK] batch {batch_num}/{total_batches}")
        else:
            code = result.get("code") if result else "?"
            msg = result.get("msg") if result else "no response"
            print(f"  [FAIL] batch {batch_num}: [{code}] {msg}", file=sys.stderr)
            all_ok = False

    return all_ok


# ── Markdown → Feishu Blocks ──────────────────


def _md_to_blocks(md_text: str) -> list[dict]:
    """将 Markdown 文本转为飞书 docx blocks。

    支持：h1-h4 / **粗体** / [链接](url) / 引用
    """
    blocks: list[dict] = []
    for line in md_text.strip().split("\n"):
        stripped = line.strip()
        if not stripped or stripped == "---":
            continue

        # H1 仅用于标题提取，不渲染到飞书（避免与页面标题重复）
        if stripped.startswith("# ") and not stripped.startswith("## "):
            continue

        if stripped.startswith("> "):
            elements = _parse_inline(stripped[2:])
            blocks.append({
                "block_type": 2,
                "text": {
                    "elements": elements,
                    "style": {"align": 1, "folded": False},
                },
            })
        elif stripped.startswith("###### "):
            blocks.append(_heading_block(6, stripped[7:]))
        elif stripped.startswith("##### "):
            blocks.append(_heading_block(6, stripped[6:]))
        elif stripped.startswith("#### "):
            blocks.append(_heading_block(6, stripped[5:]))
        elif stripped.startswith("### "):
            blocks.append(_heading_block(5, stripped[4:]))
        elif stripped.startswith("## "):
            blocks.append(_heading_block(4, stripped[3:]))
        else:
            elements = _parse_inline(stripped)
            blocks.append({
                "block_type": 2,
                "text": {
                    "elements": elements,
                    "style": {"align": 1, "folded": False},
                },
            })

    return blocks


def _heading_block(block_type: int, content: str) -> dict:
    """构建 heading block。"""
    key = {
        3: "heading1", 4: "heading2", 5: "heading3", 6: "heading4",
    }[block_type]
    return {
        "block_type": block_type,
        key: {
            "elements": [{
                "text_run": {
                    "content": content,
                    "text_element_style": {"bold": False},
                }
            }],
            "style": {},
        },
    }


def _parse_inline(text: str) -> list[dict]:
    """解析单行文本中的 **粗体** 和 [链接](url) 语法。"""
    elements: list[dict] = []
    pos = 0

    while pos < len(text):
        bold_match = re.search(r"\*\*(.+?)\*\*", text[pos:])
        link_match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", text[pos:])

        next_bold = bold_match.start() + pos if bold_match else float("inf")
        next_link = link_match.start() + pos if link_match else float("inf")

        if next_bold == float("inf") and next_link == float("inf"):
            elements.append(
                _text_element(text[pos:], bold=False)
            )
            break

        if next_bold < next_link and bold_match:
            _append_text_before(elements, text, pos, bold_match.start())
            elements.append(
                _text_element(bold_match.group(1), bold=True)
            )
            pos += bold_match.end()
        elif link_match:
            _append_text_before(elements, text, pos, link_match.start())
            elements.append(
                _text_element(
                    link_match.group(1),
                    bold=False,
                    link_url=link_match.group(2),
                )
            )
            pos += link_match.end()

    return elements


def _text_element(
    content: str,
    bold: bool = False,
    link_url: str | None = None,
) -> dict:
    """构建一个 text_run element。"""
    style: dict[str, Any] = {"bold": bold}
    if link_url:
        style["link"] = {"url": link_url}
    return {
        "text_run": {
            "content": content,
            "text_element_style": style,
        }
    }


def _append_text_before(
    elements: list[dict],
    text: str,
    pos: int,
    match_start: int,
) -> None:
    """在匹配标记之前添加一段纯文本。"""
    before = text[pos : pos + match_start]
    if before:
        elements.append(_text_element(before, bold=False))


# ── CLI 入口 ──────────────────────────────────


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="将 Markdown 文章发布到飞书 Wiki"
    )
    parser.add_argument("markdown", help="Markdown 文件路径")
    parser.add_argument(
        "--channel",
        default=None,
        help="channel.json 配置文件路径（默认同目录下的 channel.json）",
    )
    args = parser.parse_args()

    config = load_config(args.channel)
    url = publish(args.markdown, config)
    if url:
        print(f"\n[URL] {url}")
    else:
        sys.exit(1)
