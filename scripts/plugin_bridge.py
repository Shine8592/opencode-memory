#!/usr/bin/env python3
"""
JSON CLI bridge for opencode plugin -> memory system.
Supports single-shot CLI mode and persistent daemon mode.
Daemon mode keeps the embedding model loaded across calls.
"""
import sys, json, os, traceback, io, contextlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

@contextlib.contextmanager
def _silent():
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    try:
        yield
    finally:
        sys.stdout, sys.stderr = old_out, old_err

_searcher_cache = None
_BM25_CACHE = None

def _get_searcher():
    global _searcher_cache
    if _searcher_cache is None:
        with _silent():
            from semantic_search import SemanticMemorySearch
            _searcher_cache = SemanticMemorySearch()
            _searcher_cache.load_model()
    return _searcher_cache

def _bm25_tokenize(text: str) -> list:
    import re
    return re.findall(r'\w+', text.lower())

def _bm25_build_index():
    global _BM25_CACHE
    if _BM25_CACHE is not None:
        return
    from memory_config import STM_DIR, METADATA_PATH
    docs = []
    for f in STM_DIR.glob("*.json"):
        try:
            item = json.loads(f.read_text(encoding="utf-8"))
            txt = item.get("content", "") or ""
            docs.append({"text": txt, "source": f"stm/{item.get('id', f.stem)}", "type": "stm"})
        except Exception:
            pass
    if METADATA_PATH.exists():
        for entry in json.loads(METADATA_PATH.read_text(encoding="utf-8")):
            txt = entry.get("text", "") or ""
            docs.append({"text": txt, "source": entry.get("source", "index"), "type": "indexed"})
    if not docs:
        _BM25_CACHE = []
        return
    N = len(docs)
    tokenized = [_bm25_tokenize(d["text"]) for d in docs]
    df = {}
    for tokens in tokenized:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1
    avgdl = sum(len(t) for t in tokenized) / N if N else 1
    k1, b = 1.5, 0.75
    for i, d in enumerate(docs):
        tokens = tokenized[i]
        dl = len(tokens)
        score_map = {}
        for t in tokens:
            tf = tokens.count(t)
            idf = ((N - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5) + 1.0)
            bm25 = idf * ((tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl)))
            score_map[t] = score_map.get(t, 0) + bm25
        d["_bm25_tokens"] = tokens
        d["_bm25_scores"] = score_map
    _BM25_CACHE = docs

def _bm25_search(query: str, top_k: int = 5) -> list:
    _bm25_build_index()
    if not _BM25_CACHE:
        return []
    q_tokens = _bm25_tokenize(query)
    if not q_tokens:
        return []
    scored = []
    for d in _BM25_CACHE:
        score = sum(d["_bm25_scores"].get(t, 0) for t in set(q_tokens))
        if score > 0:
            scored.append((score, d))
    scored.sort(key=lambda x: -x[0])
    results = []
    for score, d in scored[:top_k]:
        results.append({
            "text": d["text"][:500],
            "source": d["source"],
            "similarity": min(score / 10.0, 1.0),
            "type": d["type"] + "_bm25",
            "id": d["source"],
        })
    return results

def cmd_recall(args: dict) -> dict:
    from memory_config import INDEX_PATH
    query = args.get("query", "")
    top_k = min(args.get("top_k", 5), 20)
    if not query:
        return {"ok": False, "error": "查询内容为空"}
    # Try semantic search first
    semantic_ok = False
    if INDEX_PATH.exists():
        try:
            with _silent():
                searcher = _get_searcher()
                ok = searcher.load_index()
                if ok:
                    results = searcher.search(query, top_k=top_k)
                    if results:
                        semantic_ok = True
                        final = []
                        for r in results:
                            final.append({
                                "text": r.get("text", "")[:500],
                                "source": r.get("source", ""),
                                "similarity": r.get("similarity", 0),
                                "type": r.get("type", ""),
                                "id": r.get("id", ""),
                            })
                        return {"ok": True, "results": final, "method": "semantic"}
        except Exception:
            pass
    # Fall back to BM25 keyword search
    try:
        results = _bm25_search(query, top_k=top_k)
        if results:
            return {"ok": True, "results": results, "method": "bm25"}
        return {"ok": True, "results": [], "method": "bm25", "note": "语义搜索不可用，BM25 也未找到匹配"}
    except Exception as e:
        return {"ok": False, "error": f"搜索失败（语义+BM25均不可用）: {e}"}

def cmd_remember(args: dict) -> dict:
    from dual_memory_engine import ShortTermMemory
    from memory_git import commit as git_commit
    content = args.get("content", "")
    tags = args.get("tags", "")
    meta = {}
    if tags:
        meta["tags"] = [t.strip() for t in tags.split(",")]
    stm = ShortTermMemory()
    item_id = stm.add(content, metadata=meta)
    try:
        git_commit(f"plugin auto-save: {content[:50]}...")
    except Exception:
        pass
    return {"ok": True, "id": item_id}

def cmd_recent(args: dict) -> dict:
    from memory_config import STM_DIR
    limit = args.get("limit", 10)
    tag_filter = args.get("tag", "")
    items = []
    for f in sorted(STM_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit * 3]:
        try:
            item = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if tag_filter:
            meta = item.get("metadata", {})
            tags = meta.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]
            if tag_filter not in tags:
                continue
        items.append(item)
        if len(items) >= limit:
            break
    return {"ok": True, "items": items[:limit]}

def cmd_pitfalls(args: dict) -> dict:
    return cmd_recent({"tag": "pitfall", "limit": args.get("limit", 10)})

def cmd_score_all(args: dict) -> dict:
    from memory_config import STM_DIR
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    updated = 0
    for f in STM_DIR.glob("*.json"):
        try:
            item = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        ts_str = item.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            ts = now
        age_hours = (now - ts).total_seconds() / 3600
        access = item.get("access_count", 0)
        item["importance_score"] = _calc_importance(age_hours, access)
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(item, fh, indent=2, ensure_ascii=False)
        updated += 1
    return {"ok": True, "updated": updated}

def _calc_importance(age_hours: float, access_count: int = 0) -> float:
    decay = 2.718 ** (-0.01 * age_hours)  # Ebbinghaus: lambda=0.01
    access_bonus = min(access_count * 0.1, 0.3)
    score = decay * 0.7 + access_bonus * 0.3
    return round(max(0.0, min(1.0, score)), 4)

def cmd_tidy(args: dict) -> dict:
    from memory_config import STM_DIR
    from datetime import datetime, timezone
    threshold = args.get("threshold", 0.05)
    max_age_days = args.get("max_age_days", 90)
    now = datetime.now(timezone.utc)
    removed = 0
    for f in STM_DIR.glob("*.json"):
        try:
            item = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            f.unlink()
            removed += 1
            continue
        ts_str = item.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            ts = now
        age_days = (now - ts).total_seconds() / 86400
        score = item.get("importance_score", 0)
        if score < threshold and age_days > 7:
            f.unlink()
            removed += 1
            continue
        if age_days > max_age_days and score < 0.3:
            f.unlink()
            removed += 1
    return {"ok": True, "removed": removed}

def cmd_forget(args: dict) -> dict:
    from memory_config import STM_DIR, METADATA_PATH
    keyword = args.get("keyword", "").lower()
    removed = 0
    for f in STM_DIR.glob("*.json"):
        try:
            item = json.loads(f.read_text(encoding="utf-8"))
            if keyword in item.get("content", "").lower():
                f.unlink()
                removed += 1
        except Exception:
            pass
    if METADATA_PATH.exists():
        meta = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        filtered = [m for m in meta if keyword not in m.get("text", "").lower()]
        if len(filtered) < len(meta):
            METADATA_PATH.write_text(json.dumps(filtered, indent=2, ensure_ascii=False), encoding="utf-8")
            removed += len(meta) - len(filtered)
    return {"ok": True, "removed": removed}

def cmd_status(args: dict) -> dict:
    from memory_config import MEMORY_DIR, INDEX_PATH, METADATA_PATH, STM_DIR, MODEL_NAME, PROJECT_ROOT
    stm_count = len(list(STM_DIR.glob("*.json")))
    meta_count = 0
    if METADATA_PATH.exists():
        meta = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        meta_count = len(meta)
    return {
        "ok": True,
        "project_root": str(PROJECT_ROOT),
        "memory_dir": str(MEMORY_DIR),
        "index_exists": INDEX_PATH.exists(),
        "indexed_chunks": meta_count,
        "stm_count": stm_count,
        "model": MODEL_NAME,
    }

def cmd_reindex(args: dict) -> dict:
    background = args.get("background", False)
    if background:
        import subprocess
        subprocess.Popen(
            [sys.executable, str(Path(__file__).parent / "build_full_index.py")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return {"ok": True, "note": "索引重建已在后台启动"}
    from build_full_index import extract_core_and_logs, build_index as do_build
    from memory_config import ensure_dirs
    ensure_dirs()
    with _silent():
        chunks = extract_core_and_logs()
        MAX_CHUNKS = 500
        if len(chunks) > MAX_CHUNKS:
            chunks.sort(key=lambda c: c.get("timestamp", ""), reverse=True)
            chunks = chunks[:MAX_CHUNKS]
        if not chunks:
            return {"ok": False, "error": "没有找到可索引的内容"}
        do_build(chunks)
    return {"ok": True, "indexed": len(chunks)}

def cmd_history(args: dict) -> dict:
    from memory_git import log as git_log
    limit = args.get("limit", 10)
    with _silent():
        entries = git_log(limit=limit)
    return {"ok": True, "entries": entries}

CMDS = {
    "recall": cmd_recall,
    "remember": cmd_remember,
    "recent": cmd_recent,
    "pitfalls": cmd_pitfalls,
    "score": cmd_score_all,
    "tidy": cmd_tidy,
    "forget": cmd_forget,
    "status": cmd_status,
    "reindex": cmd_reindex,
    "history": cmd_history,
}

def handle_request(raw: str) -> str:
    try:
        req = json.loads(raw)
    except json.JSONDecodeError:
        return json.dumps({"ok": False, "error": "JSON 解析失败"})
    cmd = req.get("cmd", "")
    args = req.get("args", {})
    handler = CMDS.get(cmd)
    if not handler:
        return json.dumps({"ok": False, "error": f"未知命令: {cmd}"})
    try:
        result = handler(args)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

if __name__ == "__main__":
    # Daemon mode: reads JSON lines from stdin, writes JSON to stdout
    if len(sys.argv) >= 2 and sys.argv[1] == "daemon":
        sys.stdin.reconfigure(encoding="utf-8")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            response = handle_request(line)
            sys.stdout.buffer.write(response.encode("utf-8", errors="replace") + b"\n")
            sys.stdout.buffer.flush()
    else:
        # Single-shot mode
        if len(sys.argv) < 2:
            print(json.dumps({"ok": False, "error": "需要命令参数"}))
            sys.exit(1)
        cmd = sys.argv[1]
        args = {}
        if len(sys.argv) >= 3:
            try:
                args = json.loads(sys.argv[2])
            except json.JSONDecodeError:
                args = {}
        handler = CMDS.get(cmd)
        if not handler:
            print(json.dumps({"ok": False, "error": f"未知命令: {cmd}"}))
            sys.exit(1)
        try:
            result = handler(args)
            sys.stdout.buffer.write(
                json.dumps(result, ensure_ascii=False, default=str).encode("utf-8", errors="replace") + b"\n"
            )
            sys.stdout.buffer.flush()
        except Exception as e:
            sys.stdout.buffer.write(
                json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False).encode("utf-8", errors="replace") + b"\n"
            )
            sys.stdout.buffer.flush()
            sys.exit(1)
