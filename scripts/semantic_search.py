#!/usr/bin/env python3
"""
Semantic Memory Search with Sentence Transformers
Uses pre-trained embeddings for high-quality semantic search
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Optional
import time

import numpy as np

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("Error: faiss not installed. pip install faiss-cpu")
    sys.exit(1)

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("Error: sentence-transformers not installed. pip install sentence-transformers")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))
from memory_config import (
    MODEL_NAME, MEMORY_DIR, HERMES_DIR, INDEX_PATH, METADATA_PATH,
    MODEL_PATH, DAILY_DIR, CORE_FILES, ensure_dirs, SCRIPTS_DIR,
    PROJECT_ROOT, write_index_safe, read_index_safe
)

class SemanticMemorySearch:
    """Semantic memory search system"""
    
    def __init__(self):
        self.model = None
        self.index = None
        self.metadata = []
        self.dimension = 384  # all-MiniLM-L6-v2 output dimension
        
    def load_model(self):
        """Load sentence transformer model from local cache only"""
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        start_time = time.time()
        
        if MODEL_PATH.exists():
            self.model = SentenceTransformer(str(MODEL_PATH))
        else:
            self.model = SentenceTransformer(MODEL_NAME)
            MODEL_PATH.mkdir(parents=True, exist_ok=True)
            self.model.save(str(MODEL_PATH))
        
        elapsed = time.time() - start_time
        print(f"Model loaded ({elapsed:.1f}s) dim={self.dimension}")
    
    def load_text_chunks(self) -> List[Dict]:
        """Load text chunks from memory files"""
        chunks = []
        
        for filename in CORE_FILES:
            file_path = HERMES_DIR / filename
            if not file_path.exists():
                file_path = PROJECT_ROOT / filename
            if not file_path.exists():
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                sections = content.split("\n## ")
                for i, section in enumerate(sections):
                    if not section.strip():
                        continue
                    
                    if not section.startswith("#"):
                        section = "## " + section
                    
                    section = section.strip()
                    if len(section) > 2000:
                        section = section[:2000] + "..."
                    
                    if len(section) > 50:
                        chunks.append({
                            "id": f"{filename}:{i}",
                            "text": section,
                            "source": filename,
                            "type": "core_memory",
                            "chunk_index": i
                        })
            except Exception as e:
                print(f"  Error reading {file_path}: {e}")
        
        if DAILY_DIR.exists():
            for file_path in sorted(DAILY_DIR.glob("*.md")):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    if content.strip() and len(content) > 50:
                        chunks.append({
                            "id": f"daily/{file_path.name}:0",
                            "text": content.strip(),
                            "source": f"daily/{file_path.name}",
                            "type": "daily_log"
                        })
                except Exception as e:
                    print(f"  Error reading {file_path}: {e}")
        
        return chunks
    
    def build_index(self):
        """Build semantic search index"""
        print("Building Semantic Memory Index")
        
        ensure_dirs()
        
        if not self.model:
            self.load_model()
        
        chunks = self.load_text_chunks()
        print(f"Found {len(chunks)} chunks to index")
        
        if not chunks:
            print("No chunks found to index")
            return False
        
        print("Generating embeddings...")
        start_time = time.time()
        
        texts = [chunk["text"] for chunk in chunks]
        batch_size = 32
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            batch_embeddings = self.model.encode(batch, show_progress_bar=False, convert_to_numpy=True)
            all_embeddings.append(batch_embeddings)
        
        embeddings = np.vstack(all_embeddings)
        elapsed = time.time() - start_time
        
        print(f"Embeddings generated in {elapsed:.1f}s")
        
        faiss.normalize_L2(embeddings)
        
        index = faiss.IndexFlatIP(self.dimension)
        index.add(embeddings)
        
        write_index_safe(index, INDEX_PATH)
        
        metadata = []
        for i, chunk in enumerate(chunks):
            metadata.append({
                **chunk,
                "embedding_index": i,
                "hash": hashlib.md5(chunk["text"].encode()).hexdigest()[:12]
            })
        
        with open(METADATA_PATH, 'w') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        print(f"Index built: {len(metadata)} chunks")
        self.index = index
        self.metadata = metadata
        return True
    
    def load_index(self):
        """Load existing index"""
        if not INDEX_PATH.exists():
            return False
        
        if not METADATA_PATH.exists():
            return False
        
        if not self.model:
            self.load_model()
        
        self.index = read_index_safe(INDEX_PATH)
        
        with open(METADATA_PATH, 'r') as f:
            self.metadata = json.load(f)
        
        print(f"Index loaded: {len(self.metadata)} chunks")
        return True
    
    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search for similar chunks"""
        
        if not self.index:
            if not self.load_index():
                return []
        
        if not isinstance(query, str):
            query = str(query) if query is not None else ""
        query = query.encode("utf-8", errors="replace").decode("utf-8")
        if not query.strip():
            return []
        
        query_embedding = self.model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_embedding)
        
        actual_k = min(top_k, len(self.metadata))
        scores, indices = self.index.search(query_embedding, actual_k)

        results = []
        for i, (idx, score) in enumerate(zip(indices[0], scores[0])):
            if idx < len(self.metadata) and score > -1e10:
                results.append({
                    **self.metadata[idx],
                    "similarity": float(score),
                    "rank": i + 1
                })

        return results

def main():
    """Main CLI interface"""
    print(f"Semantic Memory Search System")
    print(f"   Model: {MODEL_NAME}")
    print(f"   Memory dir: {MEMORY_DIR}\n")
    
    searcher = SemanticMemorySearch()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print(f"  python {SCRIPTS_DIR.name}/semantic_search.py build        # Build search index")
        print(f"  python {SCRIPTS_DIR.name}/semantic_search.py search <q>   # Search")
        print(f"  python {SCRIPTS_DIR.name}/semantic_search.py status        # Check status")
        return
    
    command = sys.argv[1]
    
    if command == "build":
        success = searcher.build_index()
        sys.exit(0 if success else 1)
    
    elif command == "search":
        if len(sys.argv) < 3:
            print("Please provide a search query")
            return
        
        query = " ".join(sys.argv[2:])
        print(f"\nSemantic Search: '{query}'")
        
        results = searcher.search(query, top_k=5)
        if not results:
            print("No results found.")
        else:
            for r in results:
                print(f"  [{r['similarity']:.3f}] {r['source']}: {r['text'][:100]}...")
    
    elif command == "status":
        print(f"\nSystem Status")
        print(f"   Memory dir: {MEMORY_DIR}")
        print(f"   Model: {MODEL_NAME}")
        print(f"   Model cache: {'Exists' if MODEL_PATH.exists() else 'Not found'}")
        print(f"   Index: {'Exists' if INDEX_PATH.exists() else 'Not built'}")
        print(f"   Metadata: {'Exists' if METADATA_PATH.exists() else 'Not found'}")
        
        if METADATA_PATH.exists():
            with open(METADATA_PATH, 'r') as f:
                metadata = json.load(f)
            print(f"   Indexed chunks: {len(metadata)}")
    
    else:
        print(f"Unknown command: {command}")

if __name__ == "__main__":
    main()
