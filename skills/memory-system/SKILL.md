---
name: memory-system
description: |
  Memory architecture system - semantic vector search (Faiss + sentence-transformers),
  dual memory engine (STM <-> LTM), three-tier storage (hot/warm/cold).
  For opencode persistent memory, cross-session recall, semantic search.
tags: [memory, semantic-search, vector-db, faiss, dual-memory, storage-tiers, persistence]
---

# Memory System for opencode

## Overview

Semantic vector memory system based on SuperMemo-Du architecture, designed for opencode.

| System | Function | Technology |
|--------|----------|------------|
| **Semantic Vector Search** | Semantic recall (not keyword) | sentence-transformers + Faiss |
| **Dual Memory Engine** | STM <-> LTM auto-transfer | JSON + importance scoring |
| **Three-Tier Storage** | Hot/Warm/Cold tiering | LRU cache + disk + archive |

## Storage Structure

```
project_root/
└── .opencode/
    ├── MEMORY.md           # Long-term memory file
    ├── SOUL.md              # Core personality
    ├── USER.md               # User profile
    └── AGENTS.md             # Agent config
    └── memory/
        ├── semantic_index.faiss   # Faiss vector index
        ├── semantic_metadata.json # Index metadata
        ├── stm/                   # Short-term memory (JSON)
        ├── daily/                 # Daily logs
        ├── archive/               # Cold storage
        ├── warm/                  # Warm storage
        └── cold/                  # Cold storage
```
> Memory system code installed globally at `~/.config/opencode/memory/scripts/`

## 1. Semantic Vector Search

### Architecture

```
User Query -> SentenceTransformer (all-MiniLM-L6-v2, 384-dim)
                |
         Faiss Flat Index
                |
       Top-K Cosine Similarity
                |
       Return {id, content, score, metadata}
```

### Commands

| Operation | Command |
|-----------|----------|
| Build index | `python ~/.config/opencode/memory/scripts/semantic_search.py build` |
| Search | `python ~/.config/opencode/memory/scripts/semantic_search.py search "query"` |
| Status | `python ~/.config/opencode/memory/scripts/semantic_search.py status` |
| Full rebuild | `python ~/.config/opencode/memory/scripts/build_full_index.py` |

## 2. Dual Memory Engine

### Short-Term Memory (STM)
- 24-hour window
- Raw session records
- JSON format
- Max 1000 items

### Long-Term Memory (LTM)
- Permanent storage
- Distilled key information
- MEMORY.md structured storage

### STM -> LTM Transfer
When importance score >= 0.7, auto-transfer:
1. Summary (first 200 chars)
2. Append to LTM section
3. STM marked as "promoted"

## 3. Usage

### MCP Tools (preferred)
MCP server configured in `opencode.jsonc`, provides:
- `memory_recall` - Semantic search
- `memory_remember` - Save memory
- `memory_forget` - Delete memory
- `memory_status` - System status
- `memory_reindex` - Rebuild index
- `memory_history` - Version history
- `memory_rollback` - Rollback version
- `memory_sync` - Sync Git repo

### CLI
```bash
# Semantic search
python ~/.config/opencode/memory/scripts/semantic_search.py search "query"

# Rebuild index (with dedup)
python ~/.config/opencode/memory/scripts/build_full_index.py
```

### Initialization
```bash
pip install sentence-transformers faiss-cpu numpy
python ~/.config/opencode/memory/scripts/build_full_index.py
```

## Dependencies
```bash
pip install sentence-transformers faiss-cpu numpy
# China mainland: $env:HF_ENDPOINT="https://hf-mirror.com"
```
Model ~80MB, auto-downloads on first run.
