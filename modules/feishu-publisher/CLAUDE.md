# feishu-publisher — 飞书 Wiki 发布模块

## 职责

将 FeedFlow 生成的 Markdown 文章发布到飞书 Wiki 页面，作为 RSS 之外的并行输出渠道。

## 架构

```
output/YYYY-MM-DD/文章.md
  │
  ├─→ rss-publisher/build_rss.py → rss.xml → GitHub Pages (现有)
  │
  └─→ feishu-publisher/deliver.py → 飞书 Wiki 页面 (新增)
       ├ _create_wiki_node()     → wiki +node-create (user 身份)
       ├ _md_to_blocks()         → Markdown → docx blocks
       └ _write_blocks()         → POST /docx/.../children (user 身份)
```

## 配置

`channel.json`：

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `parent_node_token` | 飞书 Wiki 父页面 token | `PsYTwWYQoiqQCAk43fZcGYaPnIF` |
| `lark_cli` | lark-cli.exe 路径 | Windows npm 全局路径 |
| `identity` | 操作身份（user/bot） | `user` |
| `chunk_size` | 单次写入最大 block 数 | `45` |

## 前置条件

- lark-cli 已安装并登录（`lark-cli auth login`）
- user 身份需拥有 `docx:document:write_only` scope
- 创建页面：需父页面可见权限
- 写入内容：需对文档有编辑权限

## 用法

```bash
# 命令行
python modules/feishu-publisher/deliver.py output/2026-05-05/LT视界.md

# 指定配置文件
python modules/feishu-publisher/deliver.py output/2026-05-05/LT视界.md --channel custom_channel.json
```

```python
# Python 调用
from modules.feishu_publisher.deliver import publish, load_config

config = load_config()
url = publish("output/2026-05-05/LT视界.md", config)
```

## Markdown → Blocks 转换规则

| Markdown | Feishu block_type | 备注 |
|----------|-------------------|------|
| `# ` | heading1 (3) | 页面标题 |
| `## ` | heading2 (4) | 分区标题 |
| `### ` | heading3 (5) | 子标题 |
| `#### ` | heading4 (6) | 小标题 |
| 纯文本 | text (2) | 含 **粗体** 和 [链接](url) |
| `> ` | text (2) | 引用降级为普通文本 |
| `---` | — | 跳过（API 不支持 divider） |

## 身份说明

| 身份 | 创建页面 | 写入 blocks | 说明 |
|------|----------|-------------|------|
| user (谢梦笙) | ✅ | ✅ | 需 `docx:document:write_only` scope |
| bot (BMO) | ❌ | ✅ (如有权限) | 需在空间添加为协作者 |

当前统一使用 user 身份完成全部操作。

## 故障排查

| 现象 | 原因 | 修复 |
|------|------|------|
| `1770032 forbidden` | 身份无文档编辑权限 | 确认 scope 或添加协作者 |
| `missing required scope: docx:document:write_only` | user 缺少 scope | `lark-cli auth login --scope "docx:document:write_only"` |
| `field validation failed` | 写入超过 50 blocks/批 | 减小 `chunk_size` |
| lark-cli 找不到 | 路径错误 | 检查 `channel.json` 中的 `lark_cli` 路径 |
