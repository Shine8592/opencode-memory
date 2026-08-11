# Changelog

本文件记录 Universal Agent Memory 的版本迭代历史，遵循 **本地迭代 → 验证 → 发布 GitHub 最新 → 旧版本归档** 的开发原则。

## [v3.0.3] - 2026-08-11

> 修复迭代：MCP 实机全功能验证 + 三处健壮性修复 + 版本号统一

### 🐛 修复：`memory_remember` tags 参数类型兼容（实机测试发现）

**问题**：MCP 客户端（如 Claude Code）调用 `memory_remember` 时可能把 `tags` 作为**列表**传递（`["tag1","tag2"]`），而代码只处理**逗号分隔字符串**（`tags.split(",")`）→ 抛 `'list' object has no attribute 'split'`。

**修复**：`mcp_server.py` 的 `do_remember()` 现在同时兼容两种格式（`isinstance(tags_raw, list)` 分支）。

**验证**：通过 MCP JSON-RPC 实际调用，列表/字符串/无 tags/空内容/重复去重 5 种场景全部通过。

### 🔧 修复：嵌入模型缓存路径解析（Hermes 布局兼容）

**问题**：`_choose_default_model()` 只从 `get_opencode_global()/models` 找缓存，而真实 Hermes 部署中模型缓存位于其**同级** `~/.hermes/models` → 多语言模型永远检测不到、静默回退英文。

**修复**：`memory_config.py` 新增 `_model_cache_dir()`：仅当 `global_dir.name=="memory" and global_dir.parent.name==".hermes"` 时走同级 `models/`，其余布局保持 `global_dir/models`（对 `~/.config/opencode/memory` 无影响）。

> **教训沉淀**：判定 Hermes 布局必须以「父目录名 == .hermes」严格判定，不能只凭「当前目录名 == memory」——旧配置路径 `~/.config/opencode/memory` 也叫 memory。

### 🧹 重构：移除旧英文模型回退分支（评估 #2）

**问题**：`build_full_index.py` 保留 `semantic_model/` 旧英文模型回退分支，但该目录在部署环境中不存在（死代码），且静默降级英文比显式报错更危险。

**修复**：删除 legacy 回退，主模型不可用时改为显式 `raise RuntimeError`（提示重新下载）。

### 🔢 版本号统一

- `mcp_server.py` serverInfo `3.0.0` → `3.0.3`（原与 `memory_status` 标题不一致）
- `memory_status` 标题 `v3.0.1` → `v3.0.3`

### 🗂️ 涉及文件

- `scripts/mcp_server.py`
- `scripts/memory_config.py`
- `scripts/build_full_index.py`

---

## [v3.0.2] - 2026-08-07

> 三版本统一合并 + 索引自愈机制修复

### 🔀 三版本统一合并
将长期分叉的 **部署版 / 工作副本 / GitHub main** 三个版本合并对齐，保留每一侧的全部优势：

| 脚本 | 合并决策 | 亮点 |
|------|---------|------|
| `memory_config.py` | 真合并 | 吸收 GitHub 版模型智能选择 + Cross-encoder 重排 + Hermes 路径兜底；修正 Hermes 返回路径一致性 |
| `mcp_server.py` | 部署版 | 保留 v3.0.1 标题 + 同分按 ts 取最新排序修复 |
| `build_full_index.py` | 工作副本版 | 采用 `st_mtime` 时间戳 + 模型加载离线回退（先新模型后 legacy） |
| `plugin_bridge.py` | 部署版 | 复用 `hybrid_search.BM25Index` 单实现（消除双实现 IDF 漂移），移除无用 `semantic_ok` |
| `memory_git.py` | 部署版 | 完整 `.gitignore`（含向量索引）+ `rollback` returncode 校验 |
| `dual_memory_engine.py` | 部署版 | `evaluate_transfers` 优先已存重要性分数 + `user_marked` 提升 |
| 其余 9 个脚本 | 部署版精简 | 移除冗余 import（未用 `os`/`hashlib`/`faiss` 等），逻辑不变 |

> **教训沉淀**：合并前先做三版本 diff，识别"部署版独有修复"（须保留）与"GitHub 独有增强"，用语义判断而非"谁新谁旧"；`没在用 ≠ 没用`，删除前必须确认代码真实引用。

### 🔧 修复：索引自动更新机制（关键）

**问题**：FAISS 语义索引曾滞后 45 小时（会话期仅 08-05 构建，而 08-07 的新记忆全部未进索引）。虽靠 MCP 混合检索的 **STM 实时向量编码**兜底（实际使用不掉记忆），但索引自更新机制是坏的：

1. `auto_index_updater.py` 只检测 `CORE_FILES + daily/*.md`，**完全忽略 `stm/*.json`** → 新增/修改 STM 记忆时 `needs_update()` 永不返回 True
2. 即便触发重建，`semantic_search.build_index()` 也**不含 STM**（只建核心 + 日志），STM 记忆从不进 FAISS 索引
3. 无任何定时任务在运行

**修复**：
- `get_memory_files_mtime()` 纳入 `STM_DIR/*.json` 检测
- `update_index()` 改用 `build_full_index.extract_core_and_logs + build_index`（含 STM/short_term/scenarios/atoms 权威扫描）
- 新增定时维护（Windows）：
  - `Memory_Index_Rebuild`：每天 01:00 全量重建
  - `Memory_AutoUpdate`：每 30 分钟检测（有变化才重建，低负载）
  - wrapper 脚本 `run_index_rebuild.cmd` / `run_index_autoupdate.cmd` 已设 `MEMORY_PROJECT_ROOT`，避免 `cwd` 回退导致索引到空目录（返回 0 块）

**验证**：索引从 28 → **37 块**（26 核心 + 11 STM）；新增 STM 记忆后 `needs_update()` 正确返回 True；多个定时任务调度正常。

### 🗂️ 涉及文件

- `scripts/memory_config.py`
- `scripts/mcp_server.py`
- `scripts/build_full_index.py`
- `scripts/plugin_bridge.py`
- `scripts/memory_git.py`
- `scripts/dual_memory_engine.py`
- `scripts/auto_index_updater.py`
- `scripts/*.py`（统一精简导入）
- `scripts/install_memory_mcp.py` / `final_verify.py` / `hybrid_search.py` / `storage_tiers.py` 等

---

## [v3.0.1] - 2026-08-05

修复迭代：GBK/emoji 崩溃、MCP stdout 协议流污染、清理旧模型引用。

## [v3.0.0] - 更名独立

首个 v3.0 快照：更名 universal-agent-memory 后的完整实现（MCP 架构 + 混合检索 + 跨 Agent 安装）。