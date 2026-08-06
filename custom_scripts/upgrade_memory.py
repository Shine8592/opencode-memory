#!/usr/bin/env python3
import sqlite3, pathlib, json, datetime, uuid, sys

# 统一遵循 universal-agent-memory 官方路径约定：~/.config/opencode/memory
DB_PATH = pathlib.Path('~/.config/opencode/memory/memory.db').expanduser()
MEMORY_MD = pathlib.Path('~/.config/opencode/memory/MEMORY.md').expanduser()

def calc_importance(item):
    score = 0.0
    meta = item.get('metadata') or {}
    access = meta.get('access_count', 0)
    score += min(access / 10, 0.3)
    try:
        ts = datetime.datetime.fromisoformat(item.get('timestamp'))
        age_h = (datetime.datetime.now() - ts).total_seconds() / 3600
        if age_h < 24:
            score += min(1.0 - age_h / 24, 0.3)
    except Exception:
        pass
    if meta.get('important'):
        score += 0.2
    if len(item.get('content', '')) > 100:
        score += 0.2
    return min(score, 1.0)

def promote(item):
    topic = item.get('metadata', {}).get('topic', 'General')
    header = f'## {topic}'
    text = MEMORY_MD.read_text(encoding='utf-8') if MEMORY_MD.exists() else ''
    if header not in text:
        text += f'\n{header}\n'
    summary = item.get('content', '')[:200].replace('\n', ' ')
    ts = datetime.datetime.now().isoformat(timespec='seconds')
    text += f"\n- {summary}  _(promoted on {ts})_\n"
    MEMORY_MD.write_text(text, encoding='utf-8')

def main():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute('SELECT id, source, timestamp, content, metadata FROM logs')
    rows = cur.fetchall()
    promoted = []
    for row in rows:
        log = {
            'id': row[0],
            'source': row[1],
            'timestamp': row[2],
            'content': row[3],
            'metadata': json.loads(row[4]) if row[4] else {}
        }
        imp = calc_importance(log)
        if imp >= 0.7:
            promote(log)
            cur.execute('UPDATE logs SET importance=? WHERE id=?', (imp, log['id']))
            promoted.append({'id': log['id'], 'summary': log['content'][:100]})
    conn.commit()
    conn.close()
    print('\u2705 Memory upgrade completed')
    if promoted:
        print('## Promotion Summary')
        for p in promoted:
            short_id = p['id'][:8]
            print(f"- [{short_id}] {p['summary']}")
    else:
        print('No items reached promotion threshold.')

if __name__ == '__main__':
    main()
