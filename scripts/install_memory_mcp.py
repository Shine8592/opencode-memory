#!/usr/bin/env python3
"""
Memory MCP 通用安装器（阶段二-4）
================================
自动检测并配置主流 AI Coding Agent 的 MCP 设置，实现"装在哪个 Agent 都能用"。

用法:
    python install_memory_mcp.py              # 检测并列出所有 Agent
    python install_memory_mcp.py --all        # 安装到所有已检测到的 Agent
    python install_memory_mcp.py claude-code cursor   # 安装到指定 Agent
    python install_memory_mcp.py --uninstall --all    # 从所有 Agent 卸载
    python install_memory_mcp.py --model multilingual # 同时启用多语言模型

支持: opencode / claude-code / cursor / windsurf / codex / kiro / zed /
      continue / cline / roo-code / gemini-cli / vscode-copilot / trae
"""
import sys
import json
import os
import re
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
MCP_SERVER = SCRIPT_DIR / "mcp_server.py"
SERVER_NAME = "memory"

# 记忆系统需要的环境变量（留空表示由 Agent 的 cwd 决定项目根目录）
DEF_ENV = {}


# ---------------------------------------------------------------- 工具函数
def _py() -> str:
    """返回 python 可执行文件路径（优先当前解释器）"""
    return sys.executable or "python"


def _strip_jsonc(text: str) -> str:
    """去掉 JSONC 的注释和尾随逗号，使其可被 json.loads 解析"""
    # 去掉 /* */ 块注释
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    # 去掉 // 行注释（避免误伤 URL 中的 //）
    text = re.sub(r'(?<!:)//(?![^\n"]*").*?$', "", text, flags=re.M)
    # 去掉尾随逗号
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def _read_json(path: Path) -> dict:
    """读取 JSON/JSONC 配置，失败返回空 dict"""
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return json.loads(_strip_jsonc(raw))
    except Exception as e:
        print(f"    ⚠ 读取失败 {path}: {e}")
        return {}


def _write_json(path: Path, data: dict) -> bool:
    """写入 JSON 配置（自动备份原文件）"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True
    except Exception as e:
        print(f"    ✗ 写入失败 {path}: {e}")
        return False


# ---------------------------------------------------- 各 Agent 的配置写入器
def _std_mcp_servers(cfg: dict, uninstall: bool) -> dict:
    """标准 mcpServers 格式（Claude Code / Cursor / Windsurf / Codex / Kiro 等）"""
    servers = cfg.setdefault("mcpServers", {})
    if uninstall:
        servers.pop(SERVER_NAME, None)
    else:
        entry = {
            "command": _py(),
            "args": ["-u", str(MCP_SERVER)],
        }
        if DEF_ENV:
            entry["env"] = dict(DEF_ENV)
        servers[SERVER_NAME] = entry
    return cfg


def _opencode_mcp(cfg: dict, uninstall: bool) -> dict:
    """opencode 专用格式：mcp.<name>.{type,command,enabled}"""
    mcp = cfg.setdefault("mcp", {})
    if uninstall:
        mcp.pop(SERVER_NAME, None)
    else:
        entry = {
            "type": "local",
            "command": [_py(), "-u", str(MCP_SERVER)],
            "enabled": True,
        }
        if DEF_ENV:
            entry["environment"] = dict(DEF_ENV)
        mcp[SERVER_NAME] = entry
    return cfg


def _zed_mcp(cfg: dict, uninstall: bool) -> dict:
    """Zed 格式：context_servers.<name>.{command:{path,args}}"""
    servers = cfg.setdefault("context_servers", {})
    if uninstall:
        servers.pop(SERVER_NAME, None)
    else:
        servers[SERVER_NAME] = {
            "command": {"path": _py(), "args": ["-u", str(MCP_SERVER)]},
            "settings": {},
        }
    return cfg


def _continue_mcp(cfg: dict, uninstall: bool) -> dict:
    """Continue 格式：experimental.modelContextProtocolServers = [ {transport:{...}} ]"""
    exp = cfg.setdefault("experimental", {})
    servers = exp.setdefault("modelContextProtocolServers", [])
    servers[:] = [
        s
        for s in servers
        if not (
            isinstance(s, dict)
            and str(s.get("transport", {}).get("args", "")).find("mcp_server.py") >= 0
        )
    ]
    if not uninstall:
        servers.append(
            {
                "transport": {
                    "type": "stdio",
                    "command": _py(),
                    "args": ["-u", str(MCP_SERVER)],
                }
            }
        )
    return cfg


# --------------------------------------------------------------- Agent 定义
HOME = Path.home()

AGENTS = {
    "opencode": {
        "label": "opencode",
        "paths": [
            HOME / ".config" / "opencode" / "opencode.jsonc",
            HOME / ".config" / "opencode" / "opencode.json",
        ],
        "writer": _opencode_mcp,
        "detect": [HOME / ".config" / "opencode"],
    },
    "claude-code": {
        "label": "Claude Code",
        "paths": [HOME / ".claude.json", HOME / ".claude" / "settings.json"],
        "writer": _std_mcp_servers,
        "detect": [HOME / ".claude", HOME / ".claude.json"],
    },
    "cursor": {
        "label": "Cursor",
        "paths": [HOME / ".cursor" / "mcp.json"],
        "writer": _std_mcp_servers,
        "detect": [HOME / ".cursor"],
    },
    "windsurf": {
        "label": "Windsurf",
        "paths": [HOME / ".codeium" / "windsurf" / "mcp_config.json"],
        "writer": _std_mcp_servers,
        "detect": [HOME / ".codeium"],
    },
    "codex": {
        "label": "Codex CLI",
        "paths": [HOME / ".codex" / "config.json"],
        "writer": _std_mcp_servers,
        "detect": [HOME / ".codex"],
    },
    "kiro": {
        "label": "Kiro",
        "paths": [HOME / ".kiro" / "settings" / "mcp.json"],
        "writer": _std_mcp_servers,
        "detect": [HOME / ".kiro"],
    },
    "zed": {
        "label": "Zed",
        "paths": [
            HOME / ".config" / "zed" / "settings.json",
            HOME / "AppData" / "Roaming" / "Zed" / "settings.json",
        ],
        "writer": _zed_mcp,
        "detect": [
            HOME / ".config" / "zed",
            HOME / "AppData" / "Roaming" / "Zed",
        ],
    },
    "continue": {
        "label": "Continue",
        "paths": [HOME / ".continue" / "config.json"],
        "writer": _continue_mcp,
        "detect": [HOME / ".continue"],
    },
    "cline": {
        "label": "Cline (VSCode)",
        "paths": [
            HOME
            / "AppData"
            / "Roaming"
            / "Code"
            / "User"
            / "globalStorage"
            / "saoudrizwan.claude-dev"
            / "settings"
            / "cline_mcp_settings.json",
            HOME
            / ".config"
            / "Code"
            / "User"
            / "globalStorage"
            / "saoudrizwan.claude-dev"
            / "settings"
            / "cline_mcp_settings.json",
            HOME
            / "Library"
            / "Application Support"
            / "Code"
            / "User"
            / "globalStorage"
            / "saoudrizwan.claude-dev"
            / "settings"
            / "cline_mcp_settings.json",
        ],
        "writer": _std_mcp_servers,
        "detect": [
            HOME / "AppData" / "Roaming" / "Code" / "User" / "globalStorage",
            HOME / ".config" / "Code" / "User" / "globalStorage",
        ],
    },
    "roo-code": {
        "label": "Roo Code (VSCode)",
        "paths": [
            HOME
            / "AppData"
            / "Roaming"
            / "Code"
            / "User"
            / "globalStorage"
            / "rooveterinaryinc.roo-cline"
            / "settings"
            / "mcp_settings.json",
            HOME
            / ".config"
            / "Code"
            / "User"
            / "globalStorage"
            / "rooveterinaryinc.roo-cline"
            / "settings"
            / "mcp_settings.json",
        ],
        "writer": _std_mcp_servers,
        "detect": [
            HOME / "AppData" / "Roaming" / "Code" / "User" / "globalStorage",
            HOME / ".config" / "Code" / "User" / "globalStorage",
        ],
    },
    "gemini-cli": {
        "label": "Gemini CLI",
        "paths": [HOME / ".gemini" / "settings.json"],
        "writer": _std_mcp_servers,
        "detect": [HOME / ".gemini"],
    },
    "vscode-copilot": {
        "label": "VS Code Copilot",
        "paths": [
            HOME / "AppData" / "Roaming" / "Code" / "User" / "mcp.json",
            HOME / ".config" / "Code" / "User" / "mcp.json",
        ],
        "writer": _std_mcp_servers,
        "detect": [
            HOME / "AppData" / "Roaming" / "Code" / "User",
            HOME / ".config" / "Code" / "User",
        ],
    },
    "trae": {
        "label": "Trae",
        "paths": [
            HOME / ".trae" / "mcp.json",
            HOME / "AppData" / "Roaming" / "Trae" / "User" / "mcp.json",
        ],
        "writer": _std_mcp_servers,
        "detect": [HOME / ".trae", HOME / "AppData" / "Roaming" / "Trae"],
    },
}


def detect(key: str) -> bool:
    """判断该 Agent 是否已安装（检查特征目录/文件是否存在）"""
    info = AGENTS[key]
    for p in info.get("detect", []):
        if p.exists():
            return True
    for p in info["paths"]:
        if p.exists():
            return True
    return False


def target_path(key: str) -> Path:
    """选择要写入的配置文件：优先已存在的，否则用第一个可创建的父目录"""
    info = AGENTS[key]
    for p in info["paths"]:
        if p.exists():
            return p
    for p in info["paths"]:
        if p.parent.exists() or p.parent.parent.exists():
            return p
    return info["paths"][0]


def install_one(key: str, uninstall: bool = False) -> bool:
    info = AGENTS[key]
    path = target_path(key)
    action = "卸载" if uninstall else "安装"
    print(f"  → {info['label']}: {path}")
    cfg = _read_json(path)
    cfg = info["writer"](cfg, uninstall)
    if _write_json(path, cfg):
        print(f"    ✓ {action}成功")
        return True
    return False


def main():
    args = [a for a in sys.argv[1:]]
    uninstall = "--uninstall" in args
    do_all = "--all" in args
    use_multilingual = "--model" in args and "multilingual" in args
    targets = [a for a in args if not a.startswith("--") and a in AGENTS]

    print("=" * 68)
    print("Memory MCP 通用安装器")
    print("=" * 68)
    print(f"MCP Server: {MCP_SERVER}")
    print(f"Python:     {_py()}")

    if not MCP_SERVER.exists():
        print(f"\n✗ 找不到 mcp_server.py，请确认路径: {MCP_SERVER}")
        return 1

    # 检测阶段
    print("\n检测到的 Agent:")
    detected = []
    for key in AGENTS:
        ok = detect(key)
        mark = "✓" if ok else " "
        print(f"  [{mark}] {key:<16} {AGENTS[key]['label']}")
        if ok:
            detected.append(key)

    if not targets and not do_all:
        print(f"\n共检测到 {len(detected)} 个 Agent。")
        print("\n用法:")
        print("  python install_memory_mcp.py --all              # 安装到全部")
        print("  python install_memory_mcp.py claude-code cursor # 安装到指定")
        print("  python install_memory_mcp.py --uninstall --all  # 全部卸载")
        return 0

    todo = detected if do_all else targets
    if not todo:
        print("\n没有可操作的目标 Agent。")
        return 1

    print(f"\n开始{'卸载' if uninstall else '安装'} ({len(todo)} 个):")
    ok_count = 0
    for key in todo:
        if install_one(key, uninstall):
            ok_count += 1

    # 可选：写入多语言模型环境变量提示
    if use_multilingual and not uninstall:
        print("\n多语言模型启用方式（任选其一）:")
        print("  临时: set MEMORY_MODEL_NAME=paraphrase-multilingual-MiniLM-L12-v2")
        print("  永久: setx MEMORY_MODEL_NAME paraphrase-multilingual-MiniLM-L12-v2")

    print("\n" + "=" * 68)
    print(f"完成: {ok_count}/{len(todo)} 个 Agent {'卸载' if uninstall else '配置'}成功")
    print("原配置已备份为 *.bak")
    if not uninstall:
        print("\n重启对应 Agent 后即可使用 memory_* 工具")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
