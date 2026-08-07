#!/usr/bin/env python3
"""
Git 自动版本管理 — 记忆目录变更自动 commit，可 rollback
"""
import subprocess
from datetime import datetime

from memory_config import MEMORY_DIR

GIT_DIR = MEMORY_DIR / ".git"

def _run_git(*args, cwd=None) -> str:
    if cwd is None:
        cwd = MEMORY_DIR
    try:
        r = subprocess.run(
            ["git"] + list(args),
            capture_output=True, timeout=30,
            cwd=str(cwd), encoding="utf-8", errors="replace"
        )
        return r.stdout.strip()
    except Exception:
        return ""

def init():
    if not GIT_DIR.exists():
        _run_git("init")
        _run_git("config", "user.name", "universal-agent-memory")
        _run_git("config", "user.email", "memory@universal-agent-memory.local")
        gitignore = MEMORY_DIR / ".gitignore"
        if not gitignore.exists():
            # 统一忽略规则：模型缓存目录 + 二进制向量索引 + Python 缓存
            gitignore.write_text(
                "models/\nsemantic_model/\nsemantic_index.faiss\n*.pyc\n__pycache__/\n",
                encoding="utf-8",
            )
        _run_git("add", "-A")
        _run_git("commit", "-m", "🎬 记忆仓库初始化", "--allow-empty")
        print(f"  📦 记忆 Git 仓库已初始化: {MEMORY_DIR}")

def commit(message: str = ""):
    if not GIT_DIR.exists():
        init()
    _run_git("add", "-A")
    status = _run_git("status", "--porcelain")
    if not status:
        return
    msg = message or f"🔄 记忆更新 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    _run_git("commit", "-m", msg)

def log(limit: int = 10) -> list:
    if not GIT_DIR.exists():
        return []
    out = _run_git("log", f"--max-count={limit}", "--oneline", "--pretty=format:%h|%s|%ar")
    lines = []
    for line in out.split("\n"):
        if "|" in line:
            parts = line.split("|", 2)
            lines.append({"hash": parts[0], "message": parts[1], "date": parts[2] if len(parts) > 2 else ""})
    return lines

def rollback(hash: str):
    if not GIT_DIR.exists():
        return False
    try:
        r = subprocess.run(
            ["git", "restore", "--source", hash, "--", "."],
            capture_output=True, timeout=30,
            cwd=str(MEMORY_DIR), encoding="utf-8", errors="replace"
        )
        if r.returncode != 0:
            return False
    except Exception:
        return False
    commit(f"⏪ 回滚到 {hash}")
    return True

def status() -> dict:
    if not GIT_DIR.exists():
        return {"initialized": False}
    commit_count = _run_git("rev-list", "--count", "HEAD")
    return {
        "initialized": True,
        "commits": int(commit_count) if commit_count.isdigit() else 0,
        "has_changes": bool(_run_git("status", "--porcelain"))
    }
