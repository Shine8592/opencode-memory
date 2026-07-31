#!/usr/bin/env python3
"""
MCP Server for opencode memory system.
Raw JSON-RPC over stdio - no mcp library dependency.
"""
import sys, json, time, os, traceback, contextlib
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True, write_through=True)

sys.path.insert(0, str(Path(__file__).parent))
from memory_config import (
    MODEL_NAME, MEMORY_DIR, INDEX_PATH, METADATA_PATH,
    STM_DIR, SCRIPTS_DIR, PROJECT_ROOT, ensure_dirs
)

# Lazy-load model on first use (cold start ~1s instead of ~10s)
searcher = None

def _clean_surrogates(text: str) -> str:
    """Remove lone UTF-16 surrogate characters that can't be encoded to UTF-8."""
    return text.encode("utf-8", errors="replace").decode("utf-8")

def _clean_obj(obj):
    """Recursively clean surrogates from all strings in a nested dict/list."""
    if isinstance(obj, str):
        return _clean_surrogates(obj)
    if isinstance(obj, dict):
        return {k: _clean_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_obj(v) for v in obj]
    return obj

def get_searcher():
    global searcher
    if searcher is None:
        from semantic_search import SemanticMemorySearch
        with contextlib.redirect_stdout(sys.stderr):
            searcher = SemanticMemorySearch()
            searcher.load_model()
    return searcher

def auto_commit(msg: str):
    try:
        from memory_git import commit as gc
        gc(msg)
    except:
        pass

TOOL_DEFS = [
    {
        "name": "memory_recall",
        "description": "Search saved memories by semantic similarity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "description": "Number of results", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "memory_remember",
        "description": "Save a new memory with automatic storage and Git commit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Memory content"},
                "tags": {"type": "string", "description": "Comma-separated tags", "default": ""}
            },
            "required": ["content"]
        }
    },
    {
        "name": "memory_forget",
        "description": "Delete memories matching a keyword",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Keyword to match"}
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "memory_status",
        "description": "View memory system status",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "memory_reindex",
        "description": "Rebuild vector index (runs in background by default)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "background": {"type": "boolean", "description": "Run in background", "default": True}
            }
        }
    },
    {
        "name": "memory_history",
        "description": "View memory change history",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of entries", "default": 10}
            }
        }
    },
    {
        "name": "memory_rollback",
        "description": "Rollback memory to a specific version",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hash": {"type": "string", "description": "commit hash"}
            },
            "required": ["hash"]
        }
    },
    {
        "name": "memory_sync",
        "description": "Initialize or sync memory Git repository",
        "inputSchema": {"type": "object", "properties": {}}
    },
]

TOOL_HANDLERS = {}

def tool(name):
    def deco(fn):
        TOOL_HANDLERS[name] = fn
        return fn
    return deco

# --- Tool implementations ---

_stm_cache = None
_stm_embed_cache = {}
_stm_embed_stale = True

def _load_stm_cache():
    global _stm_cache, _stm_embed_stale
    if _stm_cache is not None:
        return
    _stm_cache = []
    for f in STM_DIR.glob("*.json"):
        try:
            item = json.loads(f.read_text(encoding="utf-8"))
            txt = item.get("content", "") or ""
            _stm_cache.append((
                item.get("id", f.stem),
                txt,
                item.get("timestamp", ""),
                item.get("metadata", {}).get("tags", []),
            ))
        except:
            pass
    _stm_embed_stale = True

def _search_stm(query: str, s, top_k: int) -> list[dict]:
    """Search STM files using the loaded model for semantic matching."""
    global _stm_embed_cache, _stm_embed_stale
    _load_stm_cache()
    if not _stm_cache:
        return []
    query = _clean_surrogates(query)
    if not query.strip():
        return []
    if _stm_embed_stale or not _stm_embed_cache:
        texts = [_clean_surrogates(text[:512]) for _, text, _, _ in _stm_cache]
        valid = [(i, t) for i, t in enumerate(texts) if t.strip()]
        if not valid:
            return []
        valid_texts = [t for _, t in valid]
        valid_indices = [i for i, _ in valid]
        embeddings = s.model.encode(valid_texts, normalize_embeddings=True, batch_size=32)
        _stm_embed_cache = {}
        for j, idx in enumerate(valid_indices):
            _stm_embed_cache[_stm_cache[idx][0]] = embeddings[j]
        _stm_embed_stale = False
    qv = s.model.encode(query, normalize_embeddings=True)
    scored = []
    for sid, text, ts, tags in _stm_cache:
        tv = _stm_embed_cache.get(sid)
        if tv is None:
            clean_text = _clean_surrogates(text[:512])
            if not clean_text.strip():
                continue
            tv = s.model.encode(clean_text, normalize_embeddings=True)
            _stm_embed_cache[sid] = tv
        sim = float(qv @ tv)
        scored.append({"similarity": sim, "source": f"stm/{sid[:12]}", "text": text, "timestamp": ts})
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:top_k]

@tool("memory_recall")
def do_recall(args):
    query = _clean_surrogates(str(args.get("query", "")))
    if not query.strip():
        return "Empty search query"
    top_k = min(args.get("top_k", 5), 20)
    s = get_searcher()
    if s is None:
        return "Search engine failed to load"
    faiss_results = []
    if INDEX_PATH.exists():
        if not s.index:
            with contextlib.redirect_stdout(sys.stderr):
                ok = s.load_index()
        if s.index:
            with contextlib.redirect_stdout(sys.stderr):
                faiss_results = s.search(query, top_k=top_k)
    with contextlib.redirect_stdout(sys.stderr):
        stm_results = _search_stm(query, s, top_k)
    seen = set()
    merged = []
    for r in faiss_results + stm_results:
        text_key = r.get("text", "")[:100]
        if text_key in seen:
            continue
        seen.add(text_key)
        merged.append(r)
    merged.sort(key=lambda x: x.get("similarity", 0), reverse=True)
    merged = merged[:top_k]
    if not merged:
        return f"No results for '{query}'"
    lines = [f"Results for '{query}' (top {len(merged)}):", ""]
    for r in merged:
        sim = r.get("similarity", 0)
        src = r.get("source", "?")
        text = _clean_surrogates(r.get("text", "")[:200].replace("\n", " "))
        lines.append(f"[{sim:.3f}] [{src}] {text}")
    return "\n".join(lines)

@tool("memory_remember")
def do_remember(args):
    global _stm_cache, _stm_embed_stale
    content = _clean_surrogates(args["content"])
    tags = args.get("tags", "")
    # 容错：tags 兼容 str（逗号分隔）与 list 两种格式
    if isinstance(tags, list):
        tag_list = [str(t).strip() for t in tags if str(t).strip()]
    elif isinstance(tags, str) and tags.strip():
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    else:
        tag_list = []
    from dual_memory_engine import ShortTermMemory
    stm = ShortTermMemory()
    meta = {}
    if tag_list:
        meta["tags"] = [_clean_surrogates(t) for t in tag_list]
    content = _clean_surrogates(content)
    meta_clean = {}
    if tag_list:
        meta_clean["tags"] = [_clean_surrogates(t) for t in tag_list]
    item_id = stm.add(content, metadata=meta_clean)
    _stm_cache = None
    _stm_embed_stale = True
    safe_msg = _clean_surrogates(content[:50]).replace("\n", " ")
    auto_commit(f"New memory: {safe_msg}")
    return f"Saved memory: {item_id[:12]}"

@tool("memory_forget")
def do_forget(args):
    global _stm_cache, _stm_embed_stale
    keyword = args["keyword"].lower()
    removed = 0
    for f in STM_DIR.glob("*.json"):
        try:
            item = json.loads(f.read_text(encoding="utf-8"))
            if keyword in item.get("content", "").lower():
                f.unlink()
                removed += 1
        except:
            pass
    meta_path = METADATA_PATH
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        filtered = [m for m in meta if keyword not in m.get("text", "").lower()]
        if len(filtered) < len(meta):
            meta_path.write_text(json.dumps(filtered, indent=2, ensure_ascii=False), encoding="utf-8")
            removed += len(meta) - len(filtered)
    if removed:
        _stm_cache = None
        _stm_embed_stale = True
        auto_commit(f"Deleted {removed} memories (keyword: {keyword})")
    return f"Deleted {removed} memories"

@tool("memory_status")
def do_status(args):
    ensure_dirs()
    lines = ["OpenCode Memory System", f"   Project: {PROJECT_ROOT}", f"   Storage: {MEMORY_DIR}", ""]
    lines.append(f"   Vector index: {'Exists' if INDEX_PATH.exists() else 'Not built'}")
    if METADATA_PATH.exists():
        meta = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        lines.append(f"   Index entries: {len(meta)}")
    else:
        lines.append("   Index entries: 0")
    stm_count = len(list(STM_DIR.glob("*.json")))
    lines.append(f"   Short-term memories: {stm_count}")
    lines.append(f"   Model: {MODEL_NAME}")
    return "\n".join(lines)

@tool("memory_reindex")
def do_reindex(args):
    background = args.get("background", True)
    if background:
        import subprocess
        subprocess.Popen(
            [sys.executable, str(SCRIPTS_DIR / "build_full_index.py")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return "Index rebuild started in background"
    # 本地版 build_full_index 接口：extract_session_text + extract_from_statedb + build_index
    from build_full_index import extract_session_text, extract_from_statedb, build_index as do_build
    ensure_dirs()
    chunks = extract_session_text()
    chunks.extend(extract_from_statedb(max_sessions=50))
    MAX_CHUNKS = 500
    if len(chunks) > MAX_CHUNKS:
        chunks.sort(key=lambda c: str(c.get("timestamp", "")), reverse=True)
        chunks = chunks[:MAX_CHUNKS]
    if not chunks:
        return "No indexable content found"
    do_build(chunks)
    return f"Index rebuilt: {len(chunks)} entries"

@tool("memory_history")
def do_history(args):
    from memory_git import log as git_log, status as git_status
    limit = args.get("limit", 10)
    st = git_status()
    if not st.get("initialized"):
        return "Memory Git repo not initialized. Run memory_sync first."
    entries = git_log(limit=limit)
    lines = [f"Memory history ({st.get('commits', 0)} commits):", ""]
    for e in entries:
        lines.append(f"  {e['hash']}  {e['message']}  ({e.get('date','')})")
    return "\n".join(lines)

@tool("memory_rollback")
def do_rollback(args):
    from memory_git import rollback as git_rollback
    h = args.get("hash", "")
    if not h:
        return "Rollback failed: missing 'hash' parameter (commit hash)"
    ok = git_rollback(h)
    return f"Rolled back to {h}" if ok else "Rollback failed"

@tool("memory_sync")
def do_sync(args):
    from memory_git import init as git_init, commit as git_commit
    git_init()
    git_commit("Manual sync")
    return "Memory Git repo synced"

# --- JSON-RPC handler ---

def handle_message(msg: dict) -> dict | None:
    method = msg.get("method", "")
    msg_id = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"experimental": {}, "tools": {"listChanged": False}},
                "serverInfo": {"name": "opencode-memory", "version": "1.0.0"}
            }
        }
    elif method == "notifications/initialized":
        return None
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOL_DEFS}}
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        try:
            if name in TOOL_HANDLERS:
                text = TOOL_HANDLERS[name](args)
            else:
                text = f"Unknown tool: {name}"
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": text}]}
            }
        except Exception as e:
            traceback.print_exc()
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32603, "message": str(e)}
            }
    elif msg_id:
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }
    return None

def _detect_decode(data: bytes) -> str:
    """Auto-detect encoding: try UTF-8 first (MCP/JSON standard), fallback to system encoding."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    import locale
    fallback = locale.getpreferredencoding(False)
    try:
        return data.decode(fallback, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")

def main():
    stdin_bin = sys.stdin.buffer
    stdout_bin = sys.stdout.buffer

    while True:
        try:
            raw_line = stdin_bin.readline()
        except (EOFError, ConnectionError):
            break
        if not raw_line:
            break
        line = raw_line.strip()
        if not line:
            continue
        try:
            msg = json.loads(_detect_decode(line))
            resp = handle_message(msg)
            if resp is not None:
                resp = _clean_obj(resp)
                raw = json.dumps(resp, ensure_ascii=False) + "\n"
                stdout_bin.write(raw.encode("utf-8", errors="replace"))
                stdout_bin.flush()
        except json.JSONDecodeError:
            continue
        except SystemExit:
            break
        except:
            pass

if __name__ == "__main__":
    main()
