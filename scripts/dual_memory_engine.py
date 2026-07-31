#!/usr/bin/env python3
"""
Dual Memory Engine - Short-term + Long-term memory coordination
"""
import os, sys, json, hashlib, time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from memory_config import (
    MEMORY_DIR, STM_DIR, LTM_FILE, COORDINATOR_FILE,
    SCRIPTS_DIR, ensure_dirs
)

class ShortTermMemory:
    def __init__(self, max_age_hours: int = 24, max_items: int = 1000):
        self.max_age = timedelta(hours=max_age_hours)
        self.max_items = max_items
        self.stm_dir = STM_DIR
        self.stm_dir.mkdir(exist_ok=True)
        
    def add(self, content: str, metadata: Optional[Dict] = None) -> str:
        safe = content.encode("utf-8", errors="replace").decode("utf-8")
        item_id = hashlib.md5(f"{time.time()}_{safe}".encode()).hexdigest()[:12]
        item = {
            "id": item_id,
            "content": safe,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
            "access_count": 0,
            "importance_score": 0.0
        }
        file_path = self.stm_dir / f"{item_id}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(item, f, indent=2, ensure_ascii=False)
        self._cleanup()
        return item_id
    
    def get(self, item_id: str) -> Optional[Dict]:
        file_path = self.stm_dir / f"{item_id}.json"
        if not file_path.exists():
            return None
        with open(file_path, 'r', encoding='utf-8') as f:
            item = json.load(f)
        item["access_count"] = item.get("access_count", 0) + 1
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(item, f, indent=2, ensure_ascii=False)
        return item
    
    def query(self, keywords: List[str], limit: int = 10) -> List[Dict]:
        results = []
        cutoff = datetime.now() - self.max_age
        for file_path in self.stm_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    item = json.load(f)
                timestamp = datetime.fromisoformat(item["timestamp"])
                if timestamp < cutoff:
                    file_path.unlink()
                    continue
                content_lower = item["content"].lower()
                if any(kw.lower() in content_lower for kw in keywords):
                    results.append(item)
            except Exception:
                continue
        results.sort(key=lambda x: (x.get("access_count", 0), x["timestamp"]), reverse=True)
        return results[:limit]
    
    def _cleanup(self):
        items = []
        cutoff = datetime.now() - self.max_age
        for file_path in self.stm_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    item = json.load(f)
                timestamp = datetime.fromisoformat(item["timestamp"])
                if timestamp >= cutoff:
                    items.append((file_path, timestamp))
                else:
                    file_path.unlink()
            except Exception:
                file_path.unlink()
        if len(items) > self.max_items:
            items.sort(key=lambda x: x[1])
            for file_path, _ in items[:len(items) - self.max_items]:
                file_path.unlink()
    
    def get_all(self) -> List[Dict]:
        items = []
        cutoff = datetime.now() - self.max_age
        for file_path in self.stm_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    item = json.load(f)
                timestamp = datetime.fromisoformat(item["timestamp"])
                if timestamp >= cutoff:
                    items.append(item)
            except Exception:
                continue
        return items


class LongTermMemory:
    def __init__(self, ltm_file: Path = LTM_FILE):
        self.ltm_file = ltm_file
        self.sections = self._load_sections()
    
    def _load_sections(self) -> List[Dict]:
        sections = []
        if not self.ltm_file.exists():
            return sections
        with open(self.ltm_file, 'r', encoding='utf-8') as f:
            content = f.read()
        parts = content.split("\n## ")
        for i, part in enumerate(parts):
            if not part.strip():
                continue
            if not part.startswith("#"):
                part = "## " + part
            lines = part.strip().split("\n")
            title = lines[0].replace("#", "").strip() if lines else f"Section {i}"
            sections.append({
                "id": f"ltm_section_{i}",
                "title": title,
                "content": part.strip(),
                "last_accessed": None,
                "access_count": 0
            })
        return sections
    
    def search(self, query: str, limit: int = 5) -> List[Dict]:
        results = []
        query_lower = query.lower()
        for section in self.sections:
            content_lower = section["content"].lower()
            if query_lower in content_lower:
                matches = content_lower.count(query_lower)
                title_bonus = 2.0 if query_lower in section["title"].lower() else 1.0
                relevance = (matches * title_bonus) / len(section["content"]) * 1000
                results.append({**section, "relevance": min(relevance, 1.0), "match_count": matches})
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:limit]
    
    def add_section(self, title: str, content: str) -> str:
        section_id = f"ltm_section_{len(self.sections)}"
        new_section = f"\n\n## {title}\n\n{content}"
        existing_content = ""
        if self.ltm_file.exists():
            with open(self.ltm_file, 'r', encoding='utf-8') as f:
                existing_content = f.read()
        updated_content = existing_content + new_section
        with open(self.ltm_file, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        self.sections = self._load_sections()
        return section_id


class MemoryCoordinator:
    def __init__(self):
        self.stm = ShortTermMemory()
        self.ltm = LongTermMemory()
        self.coordinator_file = COORDINATOR_FILE
        self.load_state()
    
    def load_state(self):
        if self.coordinator_file.exists():
            with open(self.coordinator_file, 'r', encoding='utf-8') as f:
                self.state = json.load(f)
        else:
            self.state = {
                "total_transfers": 0,
                "last_coordination": None,
                "importance_threshold": 0.7
            }
    
    def save_state(self):
        self.state["last_coordination"] = datetime.now().isoformat()
        with open(self.coordinator_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)
    
    def calculate_importance(self, item: Dict) -> float:
        score = 0.0
        access_count = item.get("access_count", 0)
        score += min(access_count * 0.1, 0.3)
        try:
            timestamp = datetime.fromisoformat(item["timestamp"])
            age_hours = (datetime.now() - timestamp).total_seconds() / 3600
            recency_score = max(0, 1 - age_hours / 24)
            score += recency_score * 0.3
        except Exception:
            pass
        metadata = item.get("metadata", {})
        if metadata.get("important", False):
            score += 0.2
        if metadata.get("user_marked", False):
            score += 0.2
        content_length = len(item.get("content", ""))
        if 50 < content_length < 1000:
            score += 0.2
        return min(score, 1.0)
    
    def search_across_memories(self, query: str, stm_limit: int = 5, ltm_limit: int = 5) -> Dict[str, List]:
        stm_results = self.stm.query(query.split(), limit=stm_limit)
        ltm_results = self.ltm.search(query, limit=ltm_limit)
        return {"short_term": stm_results, "long_term": ltm_results}


def main():
    print("Dual Memory Engine v1.0")
    coordinator = MemoryCoordinator()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print(f"  python {SCRIPTS_DIR.name}/dual_memory_engine.py add \"content\"")
        print(f"  python {SCRIPTS_DIR.name}/dual_memory_engine.py search \"query\"")
        print(f"  python {SCRIPTS_DIR.name}/dual_memory_engine.py status")
        return
    
    command = sys.argv[1]
    
    if command == "add" and len(sys.argv) > 2:
        content = " ".join(sys.argv[2:])
        item_id = coordinator.stm.add(content)
        print(f"Added short-term memory: {item_id[:8]}...")
    
    elif command == "search" and len(sys.argv) > 2:
        query = " ".join(sys.argv[2:])
        results = coordinator.search_across_memories(query)
        print(f"\nSearch results for '{query}':")
        if results["short_term"]:
            print(f"\nShort-term ({len(results['short_term'])} results):")
            for item in results["short_term"]:
                print(f"  - {item['content'][:80]}...")
        if results["long_term"]:
            print(f"\nLong-term ({len(results['long_term'])} results):")
            for section in results["long_term"]:
                print(f"  - {section['title']}: {section['content'][:80]}...")
    
    elif command == "status":
        stm_items = coordinator.stm.get_all()
        print(f"\nSystem Status:")
        print(f"  Short-term memories: {len(stm_items)}")
        print(f"  Long-term sections: {len(coordinator.ltm.sections)}")
        print(f"  Total transfers: {coordinator.state['total_transfers']}")
    
    else:
        print("Unknown command")

if __name__ == "__main__":
    main()
