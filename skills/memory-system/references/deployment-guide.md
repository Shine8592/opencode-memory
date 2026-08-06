# Universal Agent Memory — 部署与维护参考

## 一键部署（公开仓库）
```bash
git clone https://github.com/Shine8592/universal-agent-memory.git
cd universal-agent-memory
chmod +x install.sh && ./install.sh
```

## 手动部署步骤
```bash
# 1. 安装依赖
pip install sentence-transformers faiss-cpu numpy

# 2. 部署脚本（全局脚本目录，遵循 universal-agent-memory 官方约定）
mkdir -p ~/.config/opencode/memory/scripts ~/.config/opencode/memory/{stm,archive}
cp scripts/*.py ~/.config/opencode/memory/scripts/
chmod +x ~/.config/opencode/memory/scripts/*.py

# 3. 部署技能
cp -r skills/* ~/.config/opencode/memory/skills/

# 4. 放入核心记忆文件（用户自行提供）
# 需要: SOUL.md, IDENTITY.md, USER.md, MEMORY.md, TOOLS.md

# 5. 初始化双记忆引擎
python3 ~/.config/opencode/memory/scripts/init_dual_memory.py

# 6. 构建向量索引
cd ~/.config/opencode/memory && python3 ~/.config/opencode/memory/scripts/build_full_index.py
```

## Cron 部署（使用 Hermes cronjob 工具）

```python
# 1. 每日备份
cronjob action=create name="嘟嘟每日备份" \
  schedule="0 2 * * *" \
  prompt="执行嘟嘟每日自动备份到GitHub。进入目录 /root/dudu-backup，git add -A，git commit，git push"

# 2. 向量索引重建
cronjob action=create name="向量索引每日重建" \
  schedule="0 3 * * *" \
  prompt="执行嘟嘟向量记忆索引自动重建。运行命令: python3 ~/.config/opencode/memory/scripts/build_full_index.py"

# 3. 记忆维护
cronjob action=create name="记忆维护自动转移" \
  schedule="0 */6 * * *" \
  prompt="执行嘟嘟记忆维护。运行命令: python3 ~/.config/opencode/memory/scripts/memory_maintain.py"
```

## 日常维护命令速查

| 操作 | 命令 |
|------|------|
| 查看索引状态 | `python3 ~/.config/opencode/memory/scripts/semantic_search.py status` |
| 语义搜索 | `python3 ~/.config/opencode/memory/scripts/semantic_search.py search "你的问题"` |
| 重建索引（含会话） | `python3 ~/.config/opencode/memory/scripts/build_full_index.py` |
| 记忆维护（清理+转移） | `python3 ~/.config/opencode/memory/scripts/memory_maintain.py` |
| 查看Cron任务列表 | `cronjob action=list` |

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: No module named 'sentence_transformers'` | 依赖未安装 | `pip install sentence-transformers` |
| Faiss索引为空（0 chunks） | 核心记忆文件未放入 `~/.config/opencode/memory/` | 放入 SOUL.md, MEMORY.md 等文件 |
| 搜索结果不相关 | 索引太旧或会话数据未包含 | 运行 `build_full_index.py` 重建 |
| STM为空 | 刚部署或已过期清理 | 正常，新会话会自动产生STM条目 |
