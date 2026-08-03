#!/usr/bin/env python3
"""
双记忆协同引擎 (Dual Memory Engine)
实现短期记忆与长期记忆的智能协同
"""

import os
import sys
import json
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta

import numpy as np

# Windows GBK 控制台下 emoji 打印会抛 UnicodeEncodeError，先重配置为 UTF-8
try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from memory_config import (
    MEMORY_DIR, STM_DIR, LTM_FILE, COORDINATOR_FILE,
    SCRIPTS_DIR, ensure_dirs
)

class ShortTermMemory:
    """短期记忆管理器"""
    
    def __init__(self, max_age_hours: int = 24, max_items: int = 1000):
        self.max_age = timedelta(hours=max_age_hours)
        self.max_items = max_items
        self.stm_dir = STM_DIR
        self.stm_dir.mkdir(exist_ok=True)
        
    def find_duplicate(self, content: str) -> Optional[str]:
        """查找内容完全相同的已存在记忆，返回其 id；无重复返回 None"""
        safe = content.encode("utf-8", errors="replace").decode("utf-8").strip()
        if not safe:
            return None
        for file_path in self.stm_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    item = json.load(f)
                if item.get("content", "").strip() == safe:
                    return item.get("id")
            except Exception:
                continue
        return None

    def find_similar(self, content: str, model=None, threshold: float = 0.9) -> Optional[tuple]:
        """
        语义去重（向后兼容封装）。实际逻辑统一由 find_semantic_duplicate 实现，
        避免两份重复的相似度计算代码。保留此方法供外部旧调用方使用。
        """
        return self.find_semantic_duplicate(content, threshold=threshold, model=model)

    def find_semantic_duplicate(self, content: str, threshold: float = 0.9,
                                model=None) -> Optional[tuple]:
        """语义去重（BUG修复版）：批量编码 + 复用全局 searcher 模型，而非逐条+二次加载。
        model: 可传入已加载的 SentenceTransformer 以复用（推荐）。
        返回 (id, similarity) 或 None。"""
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
        except ImportError:
            return None

        # 1. 优先复用全局 searcher 已加载的模型（避免二次 465MB 加载）
        try:
            import sys, importlib
            mcp_globals = sys.modules.get("__main__")
            if mcp_globals and hasattr(mcp_globals, "searcher") and mcp_globals.searcher:
                model = mcp_globals.searcher.model
        except Exception:
            pass

        # 2. 回退：按需加载（缓存在实例上，仅加载一次）
        if model is None:
            model = getattr(self, "_dup_model", None)
        if model is None:
            from memory_config import MODEL_PATH, MODEL_NAME
            cache = MODEL_PATH
            try:
                model = SentenceTransformer(str(cache) if cache.exists() else MODEL_NAME)
            except Exception:
                return None
            self._dup_model = model

        # 3. 收集现有 STM（一次 IO）
        existing = []
        for fp in self.stm_dir.glob("*.json"):
            try:
                item = json.load(open(fp, encoding="utf-8"))
                txt = (item.get("content", "") or "").strip()
                if txt:
                    existing.append((item.get("id", fp.stem), txt))
            except Exception:
                continue
        if not existing:
            return None

        # 4. 批量编码（一次模型调用，而非 N 次）
        try:
            qv = model.encode(content[:512], normalize_embeddings=True)
            texts = [t[:512] for _, t in existing]
            embs = model.encode(texts, normalize_embeddings=True, batch_size=32)
            sims = embs @ qv
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])
            if best_sim >= threshold:
                return (existing[best_idx][0], round(best_sim, 4))
        except Exception:
            pass
        return None

    def _calc_initial_importance(self, content: str, metadata: Optional[Dict]) -> float:
        """计算新记忆的初始重要性分数（0~1）"""
        score = 0.0
        # 长度适中加分
        length = len(content)
        if 50 <= length <= 1000:
            score += 0.3
        elif length > 1000:
            score += 0.2
        # 关键内容信号（踩坑/教训/重要决策等）
        important_keywords = ["坑", "教训", "错误", "解决", "关键", "重要", "决策", "注意", "必须", "协议",
                              "配置", "bug", "BUG", "Error", "失败", "约定", "架构", "pitfall"]
        if any(kw in content for kw in important_keywords):
            score += 0.3
        # 标签加分
        meta = metadata or {}
        tags = meta.get("tags", [])
        if isinstance(tags, (list, tuple)):
            if "pitfall" in tags or "lesson-learned" in tags:
                score += 0.2
            if "important" in tags:
                score += 0.2
        if meta.get("important"):
            score += 0.2
        if meta.get("user_marked"):
            score += 0.2
        return round(min(score, 1.0), 4)

    def _update_coordinator(self):
        """同步 coordinator 中的 STM 条数统计"""
        try:
            if COORDINATOR_FILE.exists():
                with open(COORDINATOR_FILE, 'r', encoding='utf-8') as f:
                    coord = json.load(f)
            else:
                coord = {"stats": {}}
            coord.setdefault("stats", {})["stm_count"] = len(list(self.stm_dir.glob("*.json")))
            with open(COORDINATOR_FILE, 'w', encoding='utf-8') as f:
                json.dump(coord, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _infer_type(self, content: str, metadata: Optional[Dict]) -> str:
        """推断记忆功能型分类：preference/decision/pitfall/fact/skill/event"""
        meta = metadata or {}
        # 1. 显式指定优先
        if meta.get("type"):
            return str(meta["type"]).strip().lower()
        tags = meta.get("tags", [])
        if isinstance(tags, (list, tuple)):
            tag_str = " ".join(tags).lower()
            if any(t in tag_str for t in ["pitfall", "lesson", "坑", "bug", "error"]):
                return "pitfall"
            if any(t in tag_str for t in ["decision", "架构", "决策"]):
                return "decision"
            if any(t in tag_str for t in ["preference", "偏好", "习惯"]):
                return "preference"
            if any(t in tag_str for t in ["skill", "技能", "命令"]):
                return "skill"
            if any(t in tag_str for t in ["event", "事件"]):
                return "event"
        # 2. 内容关键词推断
        c = content[:200].lower()
        if any(k in c for k in ["踩坑", "报错", "错误", "exception", "traceback", "failed", "教训"]):
            return "pitfall"
        if any(k in c for k in ["架构", "决策", "方案", "选型", "设计"]):
            return "decision"
        if any(k in c for k in ["配置", "安装", "setup", "config", "setting"]):
            return "config"
        if any(k in c for k in ["偏好", "习惯", "喜欢", "prefer"]):
            return "preference"
        if any(k in c for k in ["技能", "命令", "如何", "how to", "用法", "usage"]):
            return "skill"
        return "fact"

    def add(self, content: str, metadata: Optional[Dict] = None) -> str:
        """添加短期记忆（含去重 + 类型分类 + 初始重要性评分 + coordinator 同步）"""
        # Defensive: remove surrogate characters that could crash .encode() or json.dump
        safe = content.encode("utf-8", errors="replace").decode("utf-8")

        # 去重：内容完全相同的记忆不再重复保存
        dup_id = self.find_duplicate(safe)
        if dup_id:
            return dup_id

        item_id = hashlib.md5(f"{time.time()}_{safe}".encode()).hexdigest()[:12]

        item = {
            "id": item_id,
            "content": safe,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
            "mem_type": self._infer_type(safe, metadata),   # 记忆功能型分类
            "access_count": 0,
            "importance_score": self._calc_initial_importance(safe, metadata)
        }

        # 保存到文件
        file_path = self.stm_dir / f"{item_id}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(item, f, indent=2, ensure_ascii=False)

        # 清理过期项目（重要记忆先提升到 LTM）
        self._cleanup()

        # 同步 coordinator 统计
        self._update_coordinator()

        return item_id
    
    def get(self, item_id: str) -> Optional[Dict]:
        """获取短期记忆项"""
        file_path = self.stm_dir / f"{item_id}.json"
        if not file_path.exists():
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            item = json.load(f)
        
        # 更新访问计数
        item["access_count"] = item.get("access_count", 0) + 1
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(item, f, indent=2, ensure_ascii=False)
        
        return item
    
    def query(self, keywords: List[str], limit: int = 10) -> List[Dict]:
        """查询短期记忆"""
        results = []
        cutoff = datetime.now() - self.max_age
        
        for file_path in self.stm_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    item = json.load(f)
                
                # 检查是否过期
                timestamp = datetime.fromisoformat(item["timestamp"])
                if timestamp < cutoff:
                    file_path.unlink()
                    continue
                
                # 关键词匹配
                content_lower = item["content"].lower()
                if any(kw.lower() in content_lower for kw in keywords):
                    results.append(item)
                    
            except Exception:
                continue
        
        # 按访问次数和时效性排序
        results.sort(
            key=lambda x: (
                x.get("access_count", 0),
                x["timestamp"]
            ),
            reverse=True
        )
        
        return results[:limit]
    
    def _promote_to_ltm(self, item: Dict):
        """将值得长期保留的短期记忆提升到长期记忆文件 (MEMORY.md)
        P1-3 语义蒸馏（借鉴 Beads Compaction）：
        不再原文追加，而是先尝试用嵌入模型的 tokenizer 截取关键摘要，
        再以结构化格式写入 LTM，信息更精炼。"""
        try:
            ltm_dir = LTM_FILE.parent
            ltm_dir.mkdir(parents=True, exist_ok=True)

            content = item.get("content", "") or ""
            meta = item.get("metadata", {})
            tags = meta.get("tags", [])
            mtype = item.get("mem_type", "")
            ts = (item.get("timestamp", "") or "")[:16]

            # 语义蒸馏：超长内容截取首尾关键段（简单 extractive 摘要）
            MAX = 400
            if len(content) > MAX:
                head = content[:int(MAX * 0.7)].rsplit(" ", 1)[0]
                tail = content[-int(MAX * 0.3):].lstrip()
                distilled = head + " … " + tail
            else:
                distilled = content

            # 构建结构化 LTM 条目
            tag_str = f"[{', '.join(tags)}] " if isinstance(tags, list) and tags else ""
            type_str = f"({mtype})" if mtype else ""
            entry = (
                f"\n\n### {tag_str}{type_str} {ts}\n"
                f"{distilled}\n"
            )
            with open(LTM_FILE, 'a', encoding='utf-8') as f:
                f.write(entry)
            print(f"  ⬆ 已蒸馏提升 LTM: {content[:40]}...")
        except Exception as e:
            print(f"  ⚠ 提升 LTM 失败: {e}")

    def _should_promote(self, item: Dict) -> bool:
        """判断一条短期记忆是否值得在过期前提升到 LTM"""
        # 重要性分数高（如踩坑/重要决策等）
        if item.get("importance_score", 0) >= 0.6:
            return True
        # 用户显式标记
        meta = item.get("metadata", {})
        if meta.get("important") or meta.get("user_marked"):
            return True
        tags = meta.get("tags", [])
        if isinstance(tags, list) and ("pitfall" in tags or "lesson-learned" in tags):
            return True
        return False

    def _cleanup(self):
        """清理过期和超出限制的项目（重要记忆先提升到 LTM）"""
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
                    # 过期：值得保留的先提升到长期记忆，再删除
                    if self._should_promote(item):
                        self._promote_to_ltm(item)
                    file_path.unlink()

            except Exception:
                file_path.unlink()

        # 如果超出数量限制，删除最旧的项目（同样先评估提升）
        if len(items) > self.max_items:
            items.sort(key=lambda x: x[1])
            for file_path, _ in items[:len(items) - self.max_items]:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        item = json.load(f)
                    if self._should_promote(item):
                        self._promote_to_ltm(item)
                except Exception:
                    pass
                file_path.unlink()
    
    def get_all(self) -> List[Dict]:
        """获取所有短期记忆（用于协同分析）"""
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
    """长期记忆管理器"""
    
    def __init__(self, ltm_file: Path = LTM_FILE):
        self.ltm_file = ltm_file
        self.sections = self._load_sections()
    
    def _load_sections(self) -> List[Dict]:
        """加载长期记忆的各个章节"""
        sections = []
        
        if not self.ltm_file.exists():
            return sections
        
        with open(self.ltm_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 按 ## 分割章节
        parts = content.split("\n## ")
        
        for i, part in enumerate(parts):
            if not part.strip():
                continue
            
            if not part.startswith("#"):
                part = "## " + part
            
            # 提取标题
            lines = part.strip().split("\n")
            title = lines[0].replace("#", "").strip() if lines else f"章节 {i}"
            
            sections.append({
                "id": f"ltm_section_{i}",
                "title": title,
                "content": part.strip(),
                "last_accessed": None,
                "access_count": 0
            })
        
        return sections
    
    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """搜索长期记忆"""
        results = []
        query_lower = query.lower()
        
        for section in self.sections:
            # 计算相关性
            content_lower = section["content"].lower()
            
            # 简单的关键词匹配
            if query_lower in content_lower:
                # 计算匹配次数
                matches = content_lower.count(query_lower)
                
                # 考虑标题匹配
                title_bonus = 2.0 if query_lower in section["title"].lower() else 1.0
                
                # 计算相关性分数
                relevance = (matches * title_bonus) / len(section["content"]) * 1000
                
                results.append({
                    **section,
                    "relevance": min(relevance, 1.0),
                    "match_count": matches
                })
        
        # 按相关性排序
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:limit]
    
    def add_section(self, title: str, content: str) -> str:
        """添加新章节到长期记忆"""
        section_id = f"ltm_section_{len(self.sections)}"
        
        new_section = f"\n\n## {title}\n\n{content}"
        
        # 读取现有内容
        existing_content = ""
        if self.ltm_file.exists():
            with open(self.ltm_file, 'r', encoding='utf-8') as f:
                existing_content = f.read()
        
        # 添加新章节
        updated_content = existing_content + new_section
        
        # 保存
        with open(self.ltm_file, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        
        # 重新加载章节
        self.sections = self._load_sections()
        
        return section_id
    
    def get_important_concepts(self, limit: int = 10) -> List[str]:
        """提取重要概念"""
        concepts = []
        
        for section in self.sections:
            # 查找包含核心概念的句子
            lines = section["content"].split("\n")
            for line in lines:
                line = line.strip()
                if len(line) > 20 and len(line) < 200:
                    # 检查是否包含重要关键词
                    important_keywords = [
                        "原则", "规则", "核心", "重要", "关键",
                        "必须", "应该", "建议", "教训", "经验"
                    ]
                    
                    if any(kw in line for kw in important_keywords):
                        concepts.append(line[:100])
        
        return concepts[:limit]


class MemoryCoordinator:
    """记忆协同引擎 - 管理短期↔长期记忆的协同"""
    
    def __init__(self):
        self.stm = ShortTermMemory()
        self.ltm = LongTermMemory()
        self.coordinator_file = COORDINATOR_FILE
        self.load_state()
    
    def load_state(self):
        """加载协同状态（兼容新旧 coordinator 字段结构）"""
        defaults = {
            "total_transfers": 0,
            "last_coordination": None,
            "importance_threshold": 0.7,
            "transfer_threshold": 0.7,
        }
        if self.coordinator_file.exists():
            try:
                with open(self.coordinator_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                self.state = {**defaults, **loaded}
            except Exception:
                self.state = defaults
        else:
            self.state = defaults

    def save_state(self):
        """保存协同状态"""
        self.state["last_coordination"] = datetime.now().isoformat()

        with open(self.coordinator_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)
    
    def calculate_importance(self, item: Dict) -> float:
        """计算记忆项的重要性分数"""
        score = 0.0
        
        # 访问次数加成
        access_count = item.get("access_count", 0)
        score += min(access_count * 0.1, 0.3)
        
        # 时效性加成（最近访问更重要）
        try:
            timestamp = datetime.fromisoformat(item["timestamp"])
            age_hours = (datetime.now() - timestamp).total_seconds() / 3600
            recency_score = max(0, 1 - age_hours / 24)  # 24小时内线性衰减
            score += recency_score * 0.3
        except Exception:
            pass
        
        # 元数据加成
        metadata = item.get("metadata", {})
        if metadata.get("important", False):
            score += 0.2
        if metadata.get("user_marked", False):
            score += 0.2
        
        # 长度加成（适当长度的内容更有价值）
        content_length = len(item.get("content", ""))
        if 50 < content_length < 1000:
            score += 0.2
        
        return min(score, 1.0)
    
    def evaluate_transfers(self) -> List[Dict]:
        """评估需要转移的短期记忆项目"""
        stm_items = self.stm.get_all()
        transfers = []
        
        for item in stm_items:
            importance = self.calculate_importance(item)
            item["importance_score"] = importance
            
            # 如果超过重要性阈值，建议转移
            if importance >= self.state["importance_threshold"]:
                transfers.append(item)
        
        # 按重要性排序
        transfers.sort(key=lambda x: x["importance_score"], reverse=True)
        return transfers
    
    def transfer_to_ltm(self, item_id: str, ltm_title: Optional[str] = None) -> bool:
        """将短期记忆项目转移到长期记忆"""
        item = self.stm.get(item_id)
        if not item:
            return False
        
        # 计算重要性
        importance = self.calculate_importance(item)
        
        # 生成长期记忆标题
        if not ltm_title:
            content_preview = item["content"][:50]
            ltm_title = f"重要记忆: {content_preview}..."
        
        # 添加到长期记忆
        metadata = item.get("metadata", {})
        metadata.update({
            "source": "stm_transfer",
            "stm_id": item_id,
            "transfer_time": datetime.now().isoformat(),
            "importance_score": importance
        })
        
        ltm_content = f"{item['content']}\n\n[元数据: {json.dumps(metadata, ensure_ascii=False, indent=2)}]"
        
        section_id = self.ltm.add_section(ltm_title, ltm_content)
        
        # 更新状态
        self.state["total_transfers"] += 1
        self.save_state()
        
        print(f"✅ 已转移项目 {item_id} 到长期记忆 (章节: {section_id})")
        return True
    
    def auto_transfer(self, max_transfers: int = 5) -> int:
        """自动转移重要短期记忆到长期记忆"""
        transfers = self.evaluate_transfers()
        transferred = 0
        
        print(f"\n🔄 自动转移评估: 发现 {len(transfers)} 个重要项目")
        
        for item in transfers[:max_transfers]:
            if self.transfer_to_ltm(item["id"]):
                transferred += 1
        
        if transferred > 0:
            print(f"✅ 已完成 {transferred} 个项目转移")
        else:
            print("ℹ 没有需要转移的项目")
        
        return transferred
    
    def search_across_memories(self, query: str, stm_limit: int = 5, ltm_limit: int = 5) -> Dict[str, List]:
        """跨短期和长期记忆搜索"""
        print(f"\n🔍 跨记忆搜索: '{query}'")
        
        # 搜索短期记忆
        stm_results = self.stm.query(query.split(), limit=stm_limit)
        
        # 搜索长期记忆
        ltm_results = self.ltm.search(query, limit=ltm_limit)
        
        return {
            "short_term": stm_results,
            "long_term": ltm_results
        }
    
    def print_search_results(self, results: Dict[str, List]):
        """打印搜索结果"""
        stm_results = results["short_term"]
        ltm_results = results["long_term"]
        
        print(f"\n{'='*70}")
        print(f"📊 搜索结果")
        print(f"{'='*70}\n")
        
        # 短期记忆结果
        if stm_results:
            print(f"🟢 短期记忆 ({len(stm_results)} 个结果):")
            print("-" * 50)
            for i, item in enumerate(stm_results, 1):
                importance = item.get("importance_score", 0)
                access_count = item.get("access_count", 0)
                print(f"{i}. 📌 {item['content'][:100]}...")
                print(f"   ⚡ 重要性: {importance:.2f} | 访问: {access_count}")
                print()
        
        # 长期记忆结果
        if ltm_results:
            print(f"📚 长期记忆 ({len(ltm_results)} 个结果):")
            print("-" * 50)
            for i, section in enumerate(ltm_results, 1):
                print(f"{i}. 🏷️  {section['title']}")
                print(f"   相关性: {section['relevance']:.3f}")
                # 显示内容预览
                content_preview = section['content'][:200]
                print(f"   📄 {content_preview}...")
                print()
        
        if not stm_results and not ltm_results:
            print("❌ 未找到相关结果")
    
    def get_coordination_report(self) -> Dict:
        """获取协同报告"""
        stm_items = self.stm.get_all()
        
        return {
            "short_term_count": len(stm_items),
            "long_term_sections": len(self.ltm.sections),
            "total_transfers": self.state["total_transfers"],
            "threshold": self.state["importance_threshold"],
            "pending_transfers": len(self.evaluate_transfers()),
            "stm_items": stm_items
        }
    
    def print_status(self):
        """打印系统状态"""
        print("\n📊 双记忆协同引擎状态")
        print("=" * 50)
        
        report = self.get_coordination_report()
        
        print(f"短期记忆项目: {report['short_term_count']}")
        print(f"长期记忆章节: {report['long_term_sections']}")
        print(f"已完成转移: {report['total_transfers']}")
        print(f"待转移项目: {report['pending_transfers']}")
        print(f"重要性阈值: {report['threshold']}")
        print(f"\n最后协调时间: {self.state['last_coordination'] or '从未'}")


def main():
    """主函数 - 演示双记忆协同系统"""
    print("🚀 双记忆协同引擎 v1.0")
    print("=" * 60)
    
    coordinator = MemoryCoordinator()
    
    # 命令行接口
    if len(sys.argv) < 2:
        print("\n使用方法:")
        print("  添加短期记忆:")
        print(f"    python3 {SCRIPTS_DIR.name}/dual_memory_engine.py add \"内容\"")
        print("\n  跨记忆搜索:")
        print(f"    python3 {SCRIPTS_DIR.name}/dual_memory_engine.py search \"查询\"")
        print("\n  自动转移:")
        print(f"    python3 {SCRIPTS_DIR.name}/dual_memory_engine.py transfer")
        print("\n  系统状态:")
        print(f"    python3 {SCRIPTS_DIR.name}/dual_memory_engine.py status")
        print("\n  协调报告:")
        print(f"    python3 {SCRIPTS_DIR.name}/dual_memory_engine.py report")
        return
    
    command = sys.argv[1]
    
    if command == "add" and len(sys.argv) > 2:
        content = " ".join(sys.argv[2:])
        item_id = coordinator.stm.add(content)
        print(f"✅ 已添加短期记忆: {item_id[:8]}...")
    
    elif command == "search" and len(sys.argv) > 2:
        query = " ".join(sys.argv[2:])
        results = coordinator.search_across_memories(query)
        coordinator.print_search_results(results)
    
    elif command == "transfer":
        print("\n🔄 执行自动转移...")
        transferred = coordinator.auto_transfer()
        print(f"\n✅ 转移完成: {transferred} 个项目")
    
    elif command == "status":
        coordinator.print_status()
    
    elif command == "report":
        report = coordinator.get_coordination_report()
        print("\n📋 协同报告")
        print("=" * 50)
        for key, value in report.items():
            if key != "stm_items":
                print(f"{key}: {value}")
        
        if report["stm_items"]:
            print(f"\n短期记忆项目 ({len(report['stm_items'])}):")  
            for item in report["stm_items"][:5]:
                print(f"  - {item['content'][:60]}...")
    
    else:
        print("❌ 未知命令")


if __name__ == "__main__":
    main()
