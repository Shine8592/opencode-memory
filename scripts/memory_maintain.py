#!/usr/bin/env python3
"""
opencode 记忆维护 - 定时执行：
1. STM→LTM 自动转移
2. 清理过期STM
3. 增量索引更新
"""
import sys, json, time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from memory_config import MEMORY_DIR, STM_DIR, LTM_FILE, COORDINATOR_FILE

def maintain():
    # 1. 加载协调器状态
    if COORDINATOR_FILE.exists():
        coord = json.loads(COORDINATOR_FILE.read_text(encoding='utf-8'))
    else:
        print("❌ 协调器未初始化")
        return

    # 2. 清理过期STM
    cutoff = datetime.now().timestamp() - 24 * 3600
    cleaned = 0
    for f in STM_DIR.glob("*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                cleaned += 1
        except:
            pass
    if cleaned:
        print(f"   🧹 清理 {cleaned} 条过期短期记忆")
    
    # 3. 检查STM→LTM转移
    promoted = 0
    for f in sorted(STM_DIR.glob("*.json")):
        try:
            item = json.loads(f.read_text(encoding='utf-8'))
            score = item.get("importance_score", 0)
            if score >= coord.get("transfer_threshold", 0.7) and not item.get("promoted", False):
                # 添加到LTM
                content = f"### 记忆转移 ({item.get('timestamp','')})\n\n{item['content'][:500]}\n"
                with open(LTM_FILE, 'a', encoding='utf-8') as ltm:
                    ltm.write(f"\n{content}\n")
                item["promoted"] = True
                f.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding='utf-8')
                promoted += 1
        except:
            pass
    
    # 4. 更新状态
    coord["last_transfer"] = datetime.now().isoformat()
    coord["stats"]["stm_count"] = len(list(STM_DIR.glob("*.json")))
    coord["stats"]["promoted_count"] += promoted
    COORDINATOR_FILE.write_text(json.dumps(coord, indent=2, ensure_ascii=False), encoding='utf-8')
    
    print(f"   📊 STM: {coord['stats']['stm_count']}条 | 本次转移: {promoted}条 | 累计转移: {coord['stats']['promoted_count']}条")
    print("✅ 记忆维护完成")

if __name__ == "__main__":
    print(f"🔄 嘟嘟记忆维护 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    maintain()