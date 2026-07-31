# OpenCode Memory System

基于 MCP 协议的 AI 记忆系统，支持语义向量检索、双记忆引擎、Git 版本管理。可接入任何支持 MCP 的 AI 客户端（OpenCode、HERMES、Claude Desktop、Cursor 等）。

## 功能特性

| 功能 | 说明 |
|------|------|
| 语义向量检索 | 基于 sentence-transformers + FAISS，支持中英文语义搜索 |
| 双记忆引擎 | 短期记忆（JSON 文件）+ 长期记忆（Markdown） |
| Git 版本管理 | 记忆自动 commit，支持回滚 |
| 自动编码识别 | UTF-8 优先，自动回退系统编码，兼容 Windows 中文环境 |
| 代理字符防护 | 递归清洗 UTF-16 代理字符，防止编码崩溃 |
| MCP 标准协议 | JSON-RPC over stdio，任何 MCP 客户端可直接调用 |

## 提供的 MCP 工具

| 工具名 | 说明 |
|--------|------|
| `memory_remember` | 保存记忆（自动存储 + Git commit） |
| `memory_recall` | 语义搜索记忆（合并 FAISS 索引 + 实时文件搜索） |
| `memory_forget` | 按关键词删除记忆 |
| `memory_status` | 查看系统状态（索引、模型、记忆数量） |
| `memory_reindex` | 重建向量索引（支持后台运行） |
| `memory_history` | 查看 Git 变更历史 |
| `memory_rollback` | 回滚到指定版本 |
| `memory_sync` | 初始化/同步 Git 仓库 |

## 快速安装

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 下载模型（首次运行自动下载）

```bash
python scripts/semantic_search.py --download
```

### 3. 配置 MCP 客户端

#### OpenCode (`~/.config/opencode/opencode.jsonc`)

```json
{
  "mcp": {
    "memory": {
      "type": "local",
      "command": ["python", "-u", "scripts/mcp_server.py"],
      "enabled": true
    }
  }
}
```

#### HERMES (`~/.hermes/config.yaml`)

```yaml
mcp_servers:
  memory:
    type: stdio
    command: ["python", "-u", "/path/to/scripts/mcp_server.py"]
```

#### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "memory": {
      "command": "python",
      "args": ["-u", "/path/to/scripts/mcp_server.py"]
    }
  }
}
```

## 目录结构

```
opencode-memory/
├── scripts/                    # MCP Server 核心脚本
│   ├── mcp_server.py          # MCP Server 主入口（JSON-RPC over stdio）
│   ├── semantic_search.py     # 语义向量检索（sentence-transformers + FAISS）
│   ├── dual_memory_engine.py  # 双记忆协同引擎
│   ├── build_full_index.py    # 向量索引构建工具
│   ├── memory_config.py       # 路径配置（自动适配系统）
│   ├── memory_git.py          # Git 自动版本管理
│   ├── storage_tiers.py       # 三层存储（热/温/冷）
│   ├── memory_maintain.py     # 记忆维护工具
│   ├── memory_dedup.py        # 记忆去重
│   ├── auto_index_updater.py  # 自动索引更新
│   ├── plugin_bridge.py       # 插件桥接（BM25 混合检索）
│   └── init_dual_memory.py    # 双记忆引擎初始化
├── plugins/
│   └── memory-plugin/
│       └── index.ts           # OpenCode 插件（可选）
├── skills/
│   └── memory-system/
│       └── SKILL.md           # AI 技能文档
├── requirements.txt           # Python 依赖
├── .gitignore
└── README.md
```

## 工作原理

### 编码处理流程

```
客户端发送 UTF-8 字节
        ↓
┌─────────────────────────────────────┐
│  _detect_decode() 自动识别编码       │
│  ① 先试 UTF-8（MCP 标准协议）        │
│  ② 失败→试系统编码（cp936/cp1252）   │
│  ③ 再失败→UTF-8 + 替换非法字符       │
└─────────────────────────────────────┘
        ↓
┌─────────────────────────────────────┐
│  _clean_surrogates() 移除代理字符    │
│  _clean_obj() 递归清洗整个响应       │
└─────────────────────────────────────┘
        ↓
  存储为 UTF-8 JSON 文件
```

### 记忆检索流程

```
memory_recall("查询")
        ↓
   ┌────┴────┐
   ↓         ↓
FAISS 索引  STM 文件实时编码
(预构建)    (即时搜索)
   ↓         ↓
   └────┬────┘
        ↓
   合并去重 + 按相似度排序
        ↓
   返回 Top-K 结果
```

## 依赖

- Python 3.10+
- sentence-transformers（语义编码）
- faiss-cpu（向量索引）
- numpy

## 许可证

MIT License
