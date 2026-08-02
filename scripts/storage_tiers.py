#!/usr/bin/env python3
"""
热、温、冷三层存储实现
智能记忆系统的核心存储架构
"""

import os
import sys
import json
import time
import shutil
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path

# LRU缓存实现
class LRUCache:
    """简单的LRU缓存实现"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache: Dict[str, Any] = {}
        self.access_time: Dict[str, float] = {}
        self.priority: Dict[str, float] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存项"""
        if key in self.cache:
            self.access_time[key] = time.time()
            return self.cache[key]
        return None
    
    def put(self, key: str, value: Any, priority: float = 1.0):
        """存储缓存项"""
        if len(self.cache) >= self.max_size and key not in self.cache:
            self._evict()
        
        self.cache[key] = value
        self.access_time[key] = time.time()
        self.priority[key] = priority
    
    def _evict(self):
        """淘汰最不常用的项"""
        # 考虑优先级和访问时间
        scores = {}
        current_time = time.time()
        
        for key in self.cache:
            age = current_time - self.access_time[key]
            # 分数 = 优先级 / (1 + 年龄)
            scores[key] = self.priority[key] / (1 + age / 3600)  # 按小时计算
        
        # 删除分数最低的
        if scores:
            key_to_remove = min(scores, key=scores.get)
            del self.cache[key_to_remove]
            del self.access_time[key_to_remove]
            del self.priority[key_to_remove]
    
    def remove(self, key: str):
        """移除指定项"""
        self.cache.pop(key, None)
        self.access_time.pop(key, None)
        self.priority.pop(key, None)
    
    def get_cold_items(self, days: int = 7) -> List[Any]:
        """获取长时间未访问的项"""
        cutoff = time.time() - (days * 24 * 3600)
        cold_items = []
        
        for key in list(self.cache.keys()):
            if self.access_time[key] < cutoff:
                cold_items.append(self._make_cache_item(key))
        
        return cold_items
    
    def _make_cache_item(self, key: str) -> Any:
        """创建缓存项对象"""
        return {
            'key': key,
            'value': self.cache[key],
            'priority': self.priority[key],
            'access_time': self.access_time[key]
        }


class HotStorage:
    """热存储层 - 内存缓存"""
    
    def __init__(self, max_size: int = 1000):
        self.cache = LRUCache(max_size)
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0
        }
    
    def get(self, key: str) -> Optional[Any]:
        """从热存储获取数据"""
        value = self.cache.get(key)
        if value is not None:
            self.stats['hits'] += 1
        else:
            self.stats['misses'] += 1
        return value
    
    def put(self, key: str, value: Any, priority: float = 1.0):
        """存储到热层"""
        self.cache.put(key, value, priority)
    
    def remove(self, key: str):
        """从热存储移除"""
        self.cache.remove(key)
    
    def auto_demote(self, warm_storage) -> int:
        """自动降级到温存储"""
        cold_items = self.cache.get_cold_items(days=7)
        demoted_count = 0
        
        for item in cold_items:
            warm_storage.store(item['key'], item['value'], {
                'source': 'hot',
                'demoted_at': datetime.now().isoformat(),
                'original_priority': item['priority']
            })
            self.remove(item['key'])
            demoted_count += 1
            self.stats['evictions'] += 1
        
        return demoted_count
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        total = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total * 100) if total > 0 else 0
        
        return {
            'tier': 'hot',
            'size': len(self.cache.cache),
            'max_size': self.cache.max_size,
            'hit_rate': f"{hit_rate:.1f}%",
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'evictions': self.stats['evictions']
        }


class WarmStorage:
    """温存储层 - 磁盘存储"""

    def __init__(self, storage_path: str = None):
        if storage_path is None:
            from memory_config import MEMORY_DIR
            storage_path = str(MEMORY_DIR / "warm")
        self.storage_path = Path(storage_path)
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.index_file = self.storage_path / "index.json"
        self.index = self._load_index()
        self.stats = {
            'stores': 0,
            'retrieves': 0,
            'archives': 0
        }
    
    def _load_index(self) -> Dict:
        """加载索引"""
        if self.index_file.exists():
            with open(self.index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _save_index(self):
        """保存索引"""
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, indent=2, ensure_ascii=False)
    
    def _compress(self, data: Any) -> bytes:
        """简单压缩（实际应用中应使用lz4等）"""
        json_str = json.dumps(data, ensure_ascii=False)
        return json_str.encode('utf-8')
    
    def _decompress(self, data: bytes) -> Any:
        """解压缩"""
        json_str = data.decode('utf-8')
        return json.loads(json_str)
    
    def store(self, key: str, value: Any, metadata: Dict = None):
        """存储到温层"""
        # 使用简单压缩
        compressed = self._compress(value)
        
        # 存储文件
        file_path = self.storage_path / f"{key}.dat"
        with open(file_path, 'wb') as f:
            f.write(compressed)
        
        # 更新索引
        self.index[key] = {
            'file': str(file_path),
            'size': len(compressed),
            'stored_at': datetime.now().isoformat(),
            'metadata': metadata or {},
            'access_count': 0
        }
        self._save_index()
        self.stats['stores'] += 1
    
    def retrieve(self, key: str) -> Optional[Any]:
        """从温层检索"""
        if key not in self.index:
            return None
        
        try:
            file_path = Path(self.index[key]['file'])
            if not file_path.exists():
                return None
            
            with open(file_path, 'rb') as f:
                compressed = f.read()
            
            value = self._decompress(compressed)
            
            # 更新访问统计
            self.index[key]['access_count'] += 1
            self.index[key]['last_accessed'] = datetime.now().isoformat()
            self._save_index()
            
            self.stats['retrieves'] += 1
            return value
        except Exception:
            return None
    
    def delete(self, key: str):
        """删除温层数据"""
        if key in self.index:
            file_path = Path(self.index[key]['file'])
            if file_path.exists():
                file_path.unlink()
            del self.index[key]
            self._save_index()
    
    def get_old_items(self, days: int = 30) -> List[Dict]:
        """获取长时间未访问的项"""
        cutoff = datetime.now() - timedelta(days=days)
        old_items = []
        
        for key, info in self.index.items():
            last_access = info.get('last_accessed', info['stored_at'])
            access_time = datetime.fromisoformat(last_access)
            
            if access_time < cutoff:
                old_items.append({
                    'key': key,
                    'info': info
                })
        
        return old_items
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        total_size = sum(info['size'] for info in self.index.values())
        
        return {
            'tier': 'warm',
            'items': len(self.index),
            'total_size_mb': f"{total_size / 1024 / 1024:.2f}",
            'stores': self.stats['stores'],
            'retrieves': self.stats['retrieves'],
            'archives': self.stats['archives']
        }


class ColdStorage:
    """冷存储层 - 归档存储"""

    def __init__(self, archive_path: str = None):
        if archive_path is None:
            from memory_config import MEMORY_DIR
            archive_path = str(MEMORY_DIR / "cold")
        self.archive_path = Path(archive_path)
        self.archive_path.mkdir(parents=True, exist_ok=True)
        self.manifest_file = self.archive_path / "manifest.json"
        self.manifest = self._load_manifest()
        self.stats = {
            'archives': 0,
            'restores': 0
        }
    
    def _load_manifest(self) -> Dict:
        """加载清单"""
        if self.manifest_file.exists():
            with open(self.manifest_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _save_manifest(self):
        """保存清单"""
        with open(self.manifest_file, 'w', encoding='utf-8') as f:
            json.dump(self.manifest, f, indent=2, ensure_ascii=False)
    
    def _compress(self, data: Any) -> bytes:
        """高压缩率压缩"""
        json_str = json.dumps(data, ensure_ascii=False)
        return json_str.encode('utf-8')
    
    def archive(self, key: str, value: Any, metadata: Dict = None) -> str:
        """归档到冷存储"""
        # 使用高压缩
        compressed = self._compress(value)
        
        # 创建归档文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"{timestamp}_{key}.arc"
        archive_path = self.archive_path / archive_name
        
        # 写入归档
        with open(archive_path, 'wb') as f:
            f.write(compressed)
        
        # 更新清单
        self.manifest[key] = {
            'archive': archive_name,
            'size': len(compressed),
            'archived_at': datetime.now().isoformat(),
            'metadata': metadata or {},
            'checksum': hashlib.md5(compressed).hexdigest()
        }
        self._save_manifest()
        self.stats['archives'] += 1
        
        return archive_name
    
    def restore(self, key: str) -> Optional[Any]:
        """从冷存储恢复"""
        if key not in self.manifest:
            return None
        
        try:
            archive_info = self.manifest[key]
            archive_path = self.archive_path / archive_info['archive']
            
            if not archive_path.exists():
                return None
            
            with open(archive_path, 'rb') as f:
                compressed = f.read()
            
            # 验证完整性
            if hashlib.md5(compressed).hexdigest() != archive_info['checksum']:
                print(f"⚠️ 校验失败: {key}")
                return None
            
            value = json.loads(compressed.decode('utf-8'))
            self.stats['restores'] += 1
            
            return value
        except Exception as e:
            print(f"❌ 恢复失败 {key}: {e}")
            return None
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        total_size = sum(info['size'] for info in self.manifest.values())
        
        return {
            'tier': 'cold',
            'archives': len(self.manifest),
            'total_size_mb': f"{total_size / 1024 / 1024:.2f}",
            'archives_count': self.stats['archives'],
            'restores_count': self.stats['restores']
        }


class StorageOrchestrator:
    """存储编排器 - 管理三层存储"""

    def __init__(self):
        from memory_config import MEMORY_DIR
        self.hot = HotStorage(max_size=1000)
        self.warm = WarmStorage(str(MEMORY_DIR / "warm"))
        self.cold = ColdStorage(str(MEMORY_DIR / "cold"))
    
    def get(self, key: str) -> Optional[Any]:
        """获取数据（自动分层）"""
        # 优先查询热存储
        value = self.hot.get(key)
        if value is not None:
            return value
        
        # 热存储未命中，查询温存储
        value = self.warm.retrieve(key)
        if value is not None:
            # 提升到热存储
            self.hot.put(key, value, priority=0.8)
            return value
        
        # 温存储未命中，查询冷存储
        value = self.cold.restore(key)
        if value is not None:
            # 提升到温存储
            self.warm.store(key, value, {'source': 'cold_restore'})
            return value
        
        return None
    
    def put(self, key: str, value: Any, importance: float = 0.5):
        """存储数据（智能分层）"""
        # 根据重要性决定存储层级
        if importance >= 0.8:
            # 高重要性 -> 热存储
            self.hot.put(key, value, priority=importance)
        elif importance >= 0.4:
            # 中重要性 -> 温存储
            self.warm.store(key, value, {
                'importance': importance,
                'stored_at': datetime.now().isoformat()
            })
        else:
            # 低重要性 -> 直接归档
            self.cold.archive(key, value, {
                'importance': importance,
                'archived_at': datetime.now().isoformat()
            })
    
    def auto_tier_management(self):
        """自动分层管理"""
        # 热 -> 温
        demoted = self.hot.auto_demote(self.warm)
        print(f"  🔻 热→温: {demoted} 项")
        
        # 温 -> 冷
        old_items = self.warm.get_old_items(days=30)
        for item in old_items:
            value = self.warm.retrieve(item['key'])
            if value:
                self.cold.archive(item['key'], value, item['info'])
                self.warm.delete(item['key'])
        print(f"  🔻 温→冷: {len(old_items)} 项")
    
    def get_stats(self) -> Dict:
        """获取完整统计信息"""
        return {
            'hot': self.hot.get_stats(),
            'warm': self.warm.get_stats(),
            'cold': self.cold.get_stats()
        }
    
    def print_stats(self):
        """打印统计信息"""
        stats = self.get_stats()
        
        print("\n📊 存储层级统计")
        print("=" * 50)
        
        for tier, info in stats.items():
            print(f"\n🔥 {tier.upper()} 存储层:")
            for key, value in info.items():
                print(f"   {key}: {value}")


def demo():
    """演示三层存储系统"""
    print("\n" + "="*70)
    print("🚀 三层存储系统演示")
    print("="*70)
    
    # 创建存储编排器
    storage = StorageOrchestrator()
    
    # 演示1: 存储不同类型的数据
    print("\n📝 演示1: 存储不同类型的数据")
    print("-" * 50)
    
    test_data = [
        ("session_001", {"user": "owner", "action": "login", "time": "2026-04-24"}, 0.9),
        ("dream_001", {"content": "梦见飞翔", "emotion": "joy"}, 0.7),
        ("temp_session", {"temp": True, "expires": "1h"}, 0.3),
        ("historical_event", {"event": "project_start", "year": 2024}, 0.1),
        ("important_principle", {"principle": "代码需要测试"}, 0.95),
    ]
    
    for key, value, importance in test_data:
        storage.put(key, value, importance)
        tier = "热" if importance >= 0.8 else ("温" if importance >= 0.4 else "冷")
        print(f"  ✅ 存储 {key} -> {tier}层 (重要性: {importance})")
    
    # 演示2: 查询热数据
    print("\n🔍 演示2: 查询热数据 (毫秒级响应)")
    print("-" * 50)
    
    start = time.time()
    result = storage.get("important_principle")
    elapsed = (time.time() - start) * 1000
    
    print(f"  ⚡ 查询 important_principle: {elapsed:.2f}ms")
    print(f"  📄 结果: {result}")
    
    # 演示3: 查询温数据
    print("\n🔍 演示3: 查询温数据 (秒级响应)")
    print("-" * 50)
    
    start = time.time()
    result = storage.get("dream_001")
    elapsed = (time.time() - start) * 1000
    
    print(f"  🕐 查询 dream_001: {elapsed:.2f}ms")
    print(f"  📄 结果: {result}")
    
    # 演示4: 自动分层管理
    print("\n🔄 演示4: 自动分层管理")
    print("-" * 50)
    
    print("  执行自动分层...")
    storage.auto_tier_management()
    
    # 演示5: 统计信息
    print("\n📊 演示5: 存储统计")
    print("-" * 50)
    storage.print_stats()
    
    print("\n" + "="*70)
    print("✅ 演示完成!")
    print("="*70 + "\n")


if __name__ == "__main__":
    demo()
