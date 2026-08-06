---
name: semantic-memory-auto
description: |
  自动语义记忆检索。当用户问到涉及历史决策、配置偏好、项目进度等问题时，
  自动调用 semantic_search.py 搜索向量索引，将结果注入回答上下文。
  适用于 opencode / Claude Code 等项目。
---

# Semantic Memory Auto-Retrieval (for opencode)

## 触发条件

当用户的问题涉及以下内容时，**必须先执行语义检索**再回答：

1. **历史决策** — "为什么选择XX"、"我们之前讨论过…"
2. **用户配置** — "我的邮箱是"、"API配置"
3. **项目进度** — "项目进展"、"之前改了什么"
4. **用户偏好** — "我喜欢什么"
5. **已安装技能** — "我们有什么技能"
6. **技术方案** — "之前怎么解决的"

## 检索命令

优先使用 MCP 工具（已配置在 opencode.jsonc 中）：
- `memory_recall` — 语义搜索记忆
- `memory_remember` — 保存当前重要信息到短期记忆
- `memory_status` — 查看系统状态

备用 CLI（脚本全局安装，任意目录可用）：
```powershell
python ~\.config\opencode\memory\scripts\semantic_search.py search "用户问题"
```

中国大陆使用 HuggingFace 镜像：`$env:HF_ENDPOINT="https://hf-mirror.com"`

## 索引维护

| 动作 | 命令 |
|------|------|
| 状态检查 | `python ~\.config\opencode\memory\scripts\semantic_search.py status` |
| 全量重建 | `python ~\.config\opencode\memory\scripts\build_full_index.py` |

## 结果使用

检索结果的 Top 3-5 条直接引用到回答中，标注来源前缀。

| 评分 | 含义 | 应对 |
|------|------|------|
| 0.5+ | 强相关 | 直接引用 |
| 0.3-0.5 | 中等相关 | 选择性引用 |
| <0.3 | 弱相关 | 可选 |

## 不触发条件

- 简单问候（"你好"）
- 即时命令（"发邮件"）
- 用户明确要求不用查
