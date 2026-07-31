#!/usr/bin/env python3
"""
Memory maintenance - STM cleanup, STM->LTM transfer
"""
import sys, json, time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from memory_config import MEMORY_DIR, STM_DIR, LTM_FILE, COORDINATOR_FILE

def maintain():
    if COORDINATOR_FILE.exists():
        coord = json.loads(COORDINATOR_FILE.read_text())
    else:
        print("Coordinator not initialized")
        return

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
        print(f"  Cleaned {cleaned} expired short-term memories")
    
    promoted = 0
    for f in sorted(STM_DIR.glob("*.json")):
        try:
            item = json.loads(f.read_text())
            score = item.get("importance_score", 0)
            if score >= coord.get("transfer_threshold", 0.7) and not item.get("promoted", False):
                content = f"### Memory transfer ({item.get('timestamp','')})\n\n{item['content'][:500]}\n"
                with open(LTM_FILE, 'a') as ltm:
                    ltm.write(f"\n{content}\n")
                item["promoted"] = True
                f.write_text(json.dumps(item, ensure_ascii=False, indent=2))
                promoted += 1
        except:
            pass
    
    coord["last_transfer"] = datetime.now().isoformat()
    coord["stats"]["stm_count"] = len(list(STM_DIR.glob("*.json")))
    coord["stats"]["promoted_count"] += promoted
    COORDINATOR_FILE.write_text(json.dumps(coord, indent=2, ensure_ascii=False))
    
    print(f"  STM: {coord['stats']['stm_count']} | promoted: {promoted} | total: {coord['stats']['promoted_count']}")
    print("Memory maintenance complete")

if __name__ == "__main__":
    print(f"Memory maintenance - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    maintain()
