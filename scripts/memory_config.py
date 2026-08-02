import os
from pathlib import Path

def get_opencode_global() -> Path:
    """全局记忆系统根目录（跨 Agent 通用，不依赖 opencode 专属路径）。"""
    # 优先用户自定义，其次默认
    env = os.environ.get("MEMORY_GLOBAL_DIR")
    if env:
        return Path(env).resolve()
    return Path.home() / ".config" / "opencode" / "memory"

def get_project_root() -> Path:
    """项目根目录：优先 MEMORY_PROJECT_ROOT（跨 Agent 通用），兼容 OPENCODE_PROJECT_ROOT。"""
    env = os.environ.get("MEMORY_PROJECT_ROOT") or os.environ.get("OPENCODE_PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()

def get_memory_dir() -> Path:
    """项目级记忆存储目录（兼容旧路径 .opencode/memory，支持 MEMORY_STORE 覆盖）。"""
    env = os.environ.get("MEMORY_STORE")
    if env:
        return Path(env).resolve()
    return get_project_root() / ".opencode" / "memory"

def get_scripts_dir() -> Path:
    return get_opencode_global() / "scripts"

def get_hermes_dir() -> Path:
    """记忆核心文件目录（.opencode/）"""
    return get_project_root() / ".opencode"

MEMORY_DIR = get_memory_dir()
HERMES_DIR = get_hermes_dir()
SCRIPTS_DIR = get_scripts_dir()

INDEX_PATH = MEMORY_DIR / "semantic_index.faiss"
METADATA_PATH = MEMORY_DIR / "semantic_metadata.json"

# 嵌入模型：支持 MEMORY_MODEL_NAME 覆盖，智能默认：优先多语言（已下载），否则回退旧模型
_ML_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"   # 优先：中英文效果均佳
_EN_MODEL  = "all-MiniLM-L6-v2"                        # 回退：仅英文，但已下载

def _choose_default_model() -> str:
    """自动选最佳已缓存模型：有多语言缓存用多语言，否则回退旧英文模型（已下载不阻塞）"""
    global_dir = get_opencode_global()
    # 新缓存路径（models/）是否有多语言模型
    ml_cache = global_dir / "models" / _ML_MODEL.replace("/", "_").replace(":", "_")
    if ml_cache.exists():
        return _ML_MODEL
    # 旧路径（semantic_model/）是否有英文模型
    legacy = global_dir / "semantic_model"
    if legacy.exists():
        return _EN_MODEL
    # 均未下载 → 默认多语言（首次 recall 时按需下载）
    return _ML_MODEL

DEFAULT_MODEL = _ML_MODEL
MODEL_NAME = os.environ.get("MEMORY_MODEL_NAME", _choose_default_model())

def get_model_path() -> Path:
    """模型本地缓存目录（按模型名区分，避免混用）"""
    safe = MODEL_NAME.replace("/", "_").replace(":", "_")
    return get_opencode_global() / "models" / safe

MODEL_PATH = get_model_path()

# Cross-encoder 重排模型（v3.0 P0-2）：RRF 融合后做精排，可用 MEMORY_RERANKER 覆盖
# 设为 "off" 可完全禁用重排（纯 RRF）
RERANKER_NAME = os.environ.get("MEMORY_RERANKER", "cross-encoder/ms-marco-MiniLM-L-6-v2")
RERANK_ENABLED = RERANKER_NAME.strip().lower() not in ("off", "none", "disabled", "0", "false")

def get_reranker_path() -> Path:
    """重排模型本地缓存目录（按模型名区分）"""
    safe = RERANKER_NAME.replace("/", "_").replace(":", "_")
    return get_opencode_global() / "models" / safe

RERANKER_PATH = get_reranker_path()

STM_DIR = MEMORY_DIR / "stm"
LTM_FILE = HERMES_DIR / "MEMORY.md"
COORDINATOR_FILE = MEMORY_DIR / "memory_coordinator.json"
ARCHIVE_DIR = MEMORY_DIR / "archive"
DAILY_DIR = MEMORY_DIR / "daily"
DIFF_LOG_PATH = MEMORY_DIR / "memory_diff.jsonl"   # 审计日志（阶段三-8）

MAX_CHUNK_CHARS = 1200

CORE_FILES = ["SOUL.md", "USER.md", "MEMORY.md", "AGENTS.md"]
PROJECT_ROOT = get_project_root()

def ensure_dirs():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    STM_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)


# Faiss 原生 C++ I/O 不支持中文路径，用序列化绕开
_faiss = None
_np = None

def _load_faiss():
    global _faiss, _np
    if _faiss is None:
        import faiss
        import numpy as np
        _faiss = faiss
        _np = np

def write_index_safe(index, path: Path):
    _load_faiss()
    buf = _faiss.serialize_index(index)
    path.write_bytes(buf.tobytes())

def read_index_safe(path: Path):
    _load_faiss()
    buf = _np.frombuffer(path.read_bytes(), dtype=_np.uint8)
    return _faiss.deserialize_index(buf)
