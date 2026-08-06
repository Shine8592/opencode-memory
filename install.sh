#!/bin/bash
# universal-agent-memory 安装脚本
set -e

MCP_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "========================================"
echo "  universal-agent-memory 安装"
echo "========================================"

# 1. Python 依赖
echo ""
echo "[1/4] 安装 Python 依赖..."
pip install sentence-transformers faiss-cpu numpy mcp 2>&1 | tail -1

# 2. MCP Server 注册
echo ""
echo "[2/4] 注册 MCP Server..."
CONFIG_DIR="${HOME}/.config/opencode"
CONFIG_FILE="${CONFIG_DIR}/opencode.jsonc"
mkdir -p "$CONFIG_DIR"

if [ -f "$CONFIG_FILE" ] && grep -q '"memory"' "$CONFIG_FILE" 2>/dev/null; then
  echo "  MCP 'memory' 已注册，跳过"
else
  # 尝试插入到 mcp 块中
  if grep -q '"mcp"' "$CONFIG_FILE" 2>/dev/null; then
    # 在第一个 "mcp": { 之后插入
    sed -i 's/"mcp": {/"mcp": {\n    "memory": {\n      "type": "local",\n      "command": ["python", "'"$MCP_DIR"'\/scripts\/mcp_server.py"],\n      "enabled": true\n    },/' "$CONFIG_FILE"
  else
    # 追加到文件末尾
    cat >> "$CONFIG_FILE" << EOF

"mcp": {
  "memory": {
    "type": "local",
    "command": ["python", "$MCP_DIR/scripts/mcp_server.py"],
    "enabled": true
  }
}
EOF
  fi
  echo "  MCP Server 已注册到 $CONFIG_FILE"
fi

# 3. Plugin 安装
echo ""
echo "[3/4] 安装 Plugin..."
PLUGIN_DIR=".opencode/plugins/memory-plugin"
mkdir -p "$PLUGIN_DIR"
cp "$MCP_DIR/plugin/src/index.ts" "$PLUGIN_DIR/index.ts"

# 创建 .opencode/package.json
if [ ! -f ".opencode/package.json" ]; then
  echo '{ "dependencies": { "@opencode-ai/plugin": "latest" } }' > .opencode/package.json
fi

# 设置环境变量（写入 .bashrc/.zshrc）
SHELL_RC="${HOME}/.bashrc"
if [ -f "${HOME}/.zshrc" ]; then
  SHELL_RC="${HOME}/.zshrc"
fi
if ! grep -q "MEMORY_MCP_HOME" "$SHELL_RC" 2>/dev/null; then
  echo "" >> "$SHELL_RC"
  echo "# universal-agent-memory" >> "$SHELL_RC"
  echo "export MEMORY_MCP_HOME=\"$MCP_DIR\"" >> "$SHELL_RC"
  echo "  ！已添加 export MEMORY_MCP_HOME 到 $SHELL_RC"
  echo "    执行 source $SHELL_RC 或重启终端生效"
fi
echo "  Plugin 已安装到 $PLUGIN_DIR"

# 4. 构建初始索引
echo ""
echo "[4/4] 构建初始向量索引..."
python "$MCP_DIR/scripts/build_full_index.py" 2>/dev/null && echo "  索引构建完成" || echo "  跳过索引构建（可稍后手动运行）"

echo ""
echo "========================================"
echo "  安装完成！请重启 opencode 加载插件。"
echo "========================================"
