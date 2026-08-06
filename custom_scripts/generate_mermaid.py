#!/usr/bin/env python3
import json, uuid, pathlib, sys

STM_DIR = pathlib.Path('~/.hermes/memory/stm').expanduser()
MERMAID_PATH = pathlib.Path('~/.hermes/memory/short_term/mermaid.md').expanduser()

def load_atoms():
    atoms = []
    if not STM_DIR.exists():
        return atoms
    for p in STM_DIR.glob('*.json'):
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        summary = data.get('summary') or data.get('content', '')[:30]
        atoms.append({'uid': str(uuid.uuid4())[:8], 'summary': summary})
    return atoms

def build_mermaid(atoms):
    lines = ['graph LR']
    prev = None
    for a in atoms:
        safe = a['summary'].replace('"', '\\"')
        node = f"{a['uid']}[\"{safe}\"]"
        lines.append(f"  {node}")
        if prev:
            lines.append(f"  {prev} --> {a['uid']}")
        prev = a['uid']
    return '\n'.join(lines)

atoms = load_atoms()
if not atoms:
    sys.stderr.write('No STM JSON files found.\n')
    sys.exit(1)
MERMAID_PATH.parent.mkdir(parents=True, exist_ok=True)
MERMAID_PATH.write_text(build_mermaid(atoms), encoding='utf-8')
print(f'✅ Mermaid 图已写入 {MERMAID_PATH}')
