#!/usr/bin/env python3
"""初始化 opencode 双记忆引擎 - 初始化STM + 配置自动转移"""
import json, time, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from memory_config import MEMORY_DIR, STM_DIR, COORDINATOR_FILE, ensure_dirs

# 创建STM目录
STM_DIR.mkdir(parents=True, exist_ok=True)

# 创建协调器配置
coordinator = {
    "auto_transfer_enabled": True,
    "stm_max_items": 1000,
    "stm_max_age_hours": 24,
    "transfer_threshold": 0.7,
    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "last_transfer": None,
    "stats": {"stm_count": 0, "ltm_sections": 0, "promoted_count": 0}
}
with open(COORDINATOR_FILE, 'w', encoding='utf-8') as f:
    json.dump(coordinator, f, indent=2, ensure_ascii=False)

# 创建archive目录
(MEMORY_DIR / "archive").mkdir(exist_ok=True)

print("✅ 双记忆引擎初始化完成")
print(f"   STM目录: {STM_DIR}")
print(f"   协调器: {COORDINATOR_FILE}")
print(f"   自动转移: {'已启用' if coordinator['auto_transfer_enabled'] else '未启用'}")
print(f"   转移阈值: {coordinator['transfer_threshold']}")
print(f"   最大条数: {coordinator['stm_max_items']}")
print(f"   窗口时间: {coordinator['stm_max_age_hours']}h")