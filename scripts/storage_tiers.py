#!/usr/bin/env python3
"""
Three-tier storage system: Hot / Warm / Cold
"""
import os, sys, json, time
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from memory_config import MEMORY_DIR, STM_DIR, ensure_dirs

HOT_DIR = MEMORY_DIR / "hot"
WARM_DIR = MEMORY_DIR / "warm"
COLD_DIR = MEMORY_DIR / "cold"

class StorageTierManager:
    def __init__(self):
        ensure_dirs()
        HOT_DIR.mkdir(exist_ok=True)
        WARM_DIR.mkdir(exist_ok=True)
        COLD_DIR.mkdir(exist_ok=True)
    
    def classify(self, item: dict) -> str:
        score = 0.0
        access_count = item.get("access_count", 0)
        score += min(access_count * 0.1, 0.3)
        try:
            ts = datetime.fromisoformat(item.get("timestamp", ""))
            age_hours = (datetime.now() - ts).total_seconds() / 3600
            score += max(0, 1 - age_hours / 24) * 0.3
        except Exception:
            pass
        if item.get("metadata", {}).get("important"):
            score += 0.2
        content_len = len(item.get("content", ""))
        if 50 < content_len < 1000:
            score += 0.2
        if score >= 0.7:
            return "hot"
        elif score >= 0.3:
            return "warm"
        else:
            return "cold"
    
    def route(self, item: dict) -> str:
        tier = self.classify(item)
        item_id = item.get("id", "unknown")
        if tier == "hot":
            dest = HOT_DIR / f"{item_id}.json"
        elif tier == "warm":
            dest = WARM_DIR / f"{item_id}.json"
        else:
            dest = COLD_DIR / f"{item_id}.json"
        with open(dest, 'w', encoding='utf-8') as f:
            json.dump(item, f, indent=2, ensure_ascii=False)
        return tier
    
    def get_stats(self) -> dict:
        return {
            "hot": len(list(HOT_DIR.glob("*.json"))),
            "warm": len(list(WARM_DIR.glob("*.json"))),
            "cold": len(list(COLD_DIR.glob("*.json")))
        }

if __name__ == "__main__":
    mgr = StorageTierManager()
    stats = mgr.get_stats()
    print(f"Storage tiers: {stats}")
