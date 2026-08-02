#!/usr/bin/env python3
"""
自动索引更新器
当记忆文件修改时自动重建语义索引
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
import time

sys.path.insert(0, str(Path(__file__).parent))

from memory_config import MODEL_NAME, MEMORY_DIR
from semantic_search import SemanticMemorySearch

AUTO_UPDATE_FILE = MEMORY_DIR / ".last_index_update"
CHECK_INTERVAL = 300

class AutoIndexUpdater:
    """自动索引更新器"""
    
    def __init__(self):
        self.searcher = SemanticMemorySearch()
        self.last_update_file = AUTO_UPDATE_FILE
        
    def get_memory_files_mtime(self) -> Dict[str, float]:
        """获取所有记忆文件的最后修改时间"""
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
        """加载上次更新的文件修改时间"""
        if not self.last_update_file.exists():
            return None
        
        try:
            with open(self.last_update_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠ 加载上次更新记录失败: {e}")
            return None
    
    def save_last_update(self, mtimes: Dict[str, float]):
        """保存当前文件修改时间"""
        try:
            with open(self.last_update_file, 'w', encoding='utf-8') as f:
                json.dump(mtimes, f, indent=2)
        except Exception as e:
            print(f"⚠ 保存更新记录失败: {e}")
    
    def needs_update(self) -> bool:
        """检查是否需要更新索引"""
        current_mtimes = self.get_memory_files_mtime()
        last_mtimes = self.load_last_update()
        
        if last_mtimes is None:
            print("ℹ 未找到上次更新记录，需要构建新索引")
            return True
        
        # 检查是否有文件被修改
        for file_path, current_mtime in current_mtimes.items():
            last_mtime = last_mtimes.get(file_path)
            if last_mtime is None:
                print(f"ℹ 新文件: {Path(file_path).name}")
                return True
            if current_mtime > last_mtime:
                print(f"ℹ 文件已修改: {Path(file_path).name}")
                return True
        
        # 检查是否有文件被删除
        for file_path in last_mtimes:
            if file_path not in current_mtimes:
                print(f"ℹ 文件已删除: {Path(file_path).name}")
                return True
        
        return False
    
    def update_index(self) -> bool:
        """更新索引"""
        print("\n🔄 开始自动更新索引...")
        print("=" * 60)
        
        start_time = time.time()
        
        try:
            # 构建新索引
            success = self.searcher.build_index()
            
            if success:
                # 保存更新记录
                current_mtimes = self.get_memory_files_mtime()
                self.save_last_update(current_mtimes)
                
                elapsed = time.time() - start_time
                print(f"\n✅ 索引更新完成! 耗时: {elapsed:.1f}s")
                print(f"   更新时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                return True
            else:
                print("\n❌ 索引更新失败!")
                return False
                
        except Exception as e:
            print(f"\n❌ 更新过程中出错: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def check_and_update(self) -> bool:
        """检查并更新索引"""
        print("\n🔍 检查索引状态...")
        print("=" * 60)
        
        if self.needs_update():
            return self.update_index()
        else:
            print("✅ 索引已是最新，无需更新")
            print(f"   最后更新时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_update_file.stat().st_mtime)) if self.last_update_file.exists() else '未知'}")
            return True

def main():
    """主函数"""
    print("🤖 自动索引更新器")
    print(f"   模型: {MODEL_NAME}")
    print(f"   检查间隔: {CHECK_INTERVAL}秒")
    
    updater = AutoIndexUpdater()
    
    # 检查命令行参数
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # 单次检查模式
        print("\n📋 单次检查模式")
        success = updater.check_and_update()
        sys.exit(0 if success else 1)
    
    else:
        # 持续监控模式
        print("\n📋 持续监控模式 (按Ctrl+C停止)")
        print("=" * 60)
        
        try:
            while True:
                success = updater.check_and_update()
                
                if not success:
                    print("\n⚠ 上次更新失败，将在下一轮重试")
                
                # 等待下次检查
                print(f"\n💤 等待 {CHECK_INTERVAL} 秒后再次检查...")
                print("   (按Ctrl+C停止监控)")
                time.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n\n👋 监控已停止")
            sys.exit(0)

if __name__ == "__main__":
    main()
