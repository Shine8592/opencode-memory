#!/usr/bin/env python3
"""
Auto index updater - rebuilds semantic index when memory files change
"""
import os, sys, json, hashlib
from pathlib import Path
from typing import Dict, List, Optional
import time

sys.path.insert(0, str(Path(__file__).parent))
from memory_config import MODEL_NAME, MEMORY_DIR
from semantic_search import SemanticMemorySearch

AUTO_UPDATE_FILE = MEMORY_DIR / ".last_index_update"
CHECK_INTERVAL = 300

class AutoIndexUpdater:
    def __init__(self):
        self.searcher = SemanticMemorySearch()
        self.last_update_file = AUTO_UPDATE_FILE
        
    def get_memory_files_mtime(self) -> Dict[str, float]:
        mtimes = {}
        from memory_config import HERMES_DIR, CORE_FILES, DAILY_DIR
        for filename in CORE_FILES:
            file_path = HERMES_DIR / filename
            if file_path.exists():
                mtimes[str(file_path)] = file_path.stat().st_mtime
        if DAILY_DIR.exists():
            for file_path in DAILY_DIR.glob("*.md"):
                mtimes[str(file_path)] = file_path.stat().st_mtime
        return mtimes
    
    def load_last_update(self) -> Optional[Dict[str, float]]:
        if not self.last_update_file.exists():
            return None
        try:
            with open(self.last_update_file, 'r') as f:
                return json.load(f)
        except Exception:
            return None
    
    def save_last_update(self, mtimes: Dict[str, float]):
        try:
            with open(self.last_update_file, 'w') as f:
                json.dump(mtimes, f, indent=2)
        except Exception:
            pass
    
    def needs_update(self) -> bool:
        current_mtimes = self.get_memory_files_mtime()
        last_mtimes = self.load_last_update()
        if last_mtimes is None:
            return True
        for file_path, current_mtime in current_mtimes.items():
            last_mtime = last_mtimes.get(file_path)
            if last_mtime is None or current_mtime > last_mtime:
                return True
        for file_path in last_mtimes:
            if file_path not in current_mtimes:
                return True
        return False
    
    def update_index(self) -> bool:
        start_time = time.time()
        try:
            success = self.searcher.build_index()
            if success:
                current_mtimes = self.get_memory_files_mtime()
                self.save_last_update(current_mtimes)
                elapsed = time.time() - start_time
                print(f"Index updated in {elapsed:.1f}s")
                return True
            return False
        except Exception as e:
            print(f"Update error: {e}")
            return False
    
    def check_and_update(self) -> bool:
        if self.needs_update():
            return self.update_index()
        else:
            print("Index is up to date")
            return True

def main():
    updater = AutoIndexUpdater()
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        updater.check_and_update()
    else:
        try:
            while True:
                updater.check_and_update()
                time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("Monitor stopped")

if __name__ == "__main__":
    main()
