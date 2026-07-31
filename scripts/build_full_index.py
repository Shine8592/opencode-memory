#!/usr/bin/env python3
"""
Build full semantic index from all memory sources
"""
import sys, json, os, hashlib
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from memory_config import (
    MEMORY_DIR, STM_DIR, HERMES_DIR, INDEX_PATH, METADATA_PATH,
    CORE_FILES, DAILY_DIR, ensure_dirs, write_index_safe
)

def extract_core_and_logs():
    """Extract text chunks from core files and logs"""
    chunks = []
    
    # Core memory files
    for filename in CORE_FILES:
        file_path = HERMES_DIR / filename
        if not file_path.exists():
            file_path = MEMORY_DIR / filename
        if not file_path.exists():
            continue
        try:
            content = file_path.read_text(encoding='utf-8')
            sections = content.split('\n## ')
            for i, section in enumerate(sections):
                section = section.strip()
                if len(section) > 50:
                    chunks.append({
                        'text': section[:2000],
                        'source': filename,
                        'type': 'core',
                        'id': f'{filename}:{i}'
                    })
        except Exception as e:
            print(f'  Error reading {file_path}: {e}')
    
    # Daily logs
    if DAILY_DIR.exists():
        for f in sorted(DAILY_DIR.glob('*.md')):
            try:
                content = f.read_text(encoding='utf-8')
                if content.strip():
                    chunks.append({
                        'text': content.strip()[:2000],
                        'source': f'daily/{f.name}',
                        'type': 'daily',
                        'id': f'daily/{f.name}:0'
                    })
            except Exception:
                pass
    
    return chunks

def build_index(chunks):
    """Build FAISS index from chunks"""
    if not chunks:
        print('No chunks to index')
        return
    
    import numpy as np
    import faiss
    from semantic_search import SemanticMemorySearch
    
    s = SemanticMemorySearch()
    s.load_model()
    
    texts = [c['text'] for c in chunks]
    embeddings = s.model.encode(texts, normalize_embeddings=True, batch_size=32)
    
    index = faiss.IndexFlatIP(384)
    index.add(embeddings)
    
    write_index_safe(index, INDEX_PATH)
    
    metadata = [{
        **c,
        'embedding_index': i,
        'hash': hashlib.md5(c['text'].encode()).hexdigest()[:12]
    } for i, c in enumerate(chunks)]
    
    METADATA_PATH.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Index built: {len(chunks)} entries')

def main():
    ensure_dirs()
    chunks = extract_core_and_logs()
    if chunks:
        build_index(chunks)
    else:
        print('No content to index')

if __name__ == '__main__':
    main()
