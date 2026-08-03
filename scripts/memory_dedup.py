#!/usr/bin/env python3
"""
语义去重引擎 — 在索引入库前检查相似度，防止索引膨胀
"""
import sys, json, hashlib
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent))
from memory_config import METADATA_PATH, MODEL_NAME, MODEL_PATH

SIMILARITY_THRESHOLD = 0.85

class DedupEngine:
    def __init__(self):
        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            # 统一使用 memory_config 的 MODEL_PATH（多语言嵌入模型）
            cache = MODEL_PATH if MODEL_PATH.exists() else None
            self.model = SentenceTransformer(str(cache) if cache else MODEL_NAME)
        except Exception as e:
            print(f"  ⚠ 去重模型加载失败: {e}")

    def get_embedding(self, text: str):
        if not self.model:
            return None
        emb = self.model.encode([text], convert_to_numpy=True)
        return emb[0]

    def cosine_similarity(self, a, b):
        import numpy as np
        a = a / (np.linalg.norm(a) + 1e-10)
        b = b / (np.linalg.norm(b) + 1e-10)
        return float(np.dot(a, b))

    def is_duplicate(self, text: str, existing: List[Dict] = None) -> bool:
        if existing is None:
            existing = self._load_existing()
        if not existing:
            return False
        emb = self.get_embedding(text)
        if emb is None:
            return False
        for item in existing:
            existing_text = item.get("text", "")
            if not existing_text:
                continue
            if len(text) < 50 and text[:30] in existing_text:
                return True
            existing_emb = self.get_embedding(existing_text[:1000])
            if existing_emb is None:
                continue
            sim = self.cosine_similarity(emb, existing_emb)
            if sim >= SIMILARITY_THRESHOLD:
                return True
        return False

    def _load_existing(self) -> List[Dict]:
        if METADATA_PATH.exists():
            try:
                return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
            except:
                pass
        return []

    def dedup_chunks(self, chunks: List[Dict]) -> List[Dict]:
        existing = self._load_existing()
        keep = []
        skip = 0
        for c in chunks:
            text = c.get("text", "")
            if not text:
                continue
            key = text[:60]
            if any(key in e.get("text", "") for e in existing):
                skip += 1
                continue
            if not self.is_duplicate(text, existing):
                keep.append(c)
            else:
                skip += 1
                existing.append({"text": text})
        if skip:
            print(f"  🗑️ 去重过滤: {skip} 条 (阈值 {SIMILARITY_THRESHOLD})")
        return keep
