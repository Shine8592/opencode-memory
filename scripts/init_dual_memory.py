#!/usr/bin/env python3
"""Initialize opencode dual memory engine - STM + auto-transfer config"""
import json, time, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from memory_config import MEMORY_DIR, STM_DIR, COORDINATOR_FILE, ensure_dirs

# Create STM directory
STM_DIR.mkdir(parents=True, exist_ok=True)

# Create coordinator config
coordinator = {
    "auto_transfer_enabled": True,
    "stm_max_items": 1000,
    "stm_max_age_hours": 24,
    "transfer_threshold": 0.7,
    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "last_transfer": None,
    "stats": {"stm_count": 0, "ltm_sections": 0, "promoted_count": 0}
}
with open(COORDINATOR_FILE, 'w') as f:
    json.dump(coordinator, f, indent=2, ensure_ascii=False)

# Create archive directory
(MEMORY_DIR / "archive").mkdir(exist_ok=True)

print("Dual memory engine initialized")
print(f"  STM dir: {STM_DIR}")
print(f"  Coordinator: {COORDINATOR_FILE}")
print(f"  Auto-transfer: {'enabled' if coordinator['auto_transfer_enabled'] else 'disabled'}")
print(f"  Transfer threshold: {coordinator['transfer_threshold']}")
print(f"  Max items: {coordinator['stm_max_items']}")
print(f"  Window: {coordinator['stm_max_age_hours']}h")
