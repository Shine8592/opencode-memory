#!/usr/bin/env python3
import json, sqlite3, pathlib, datetime, sys, uuid

# This script is intended to be called after each assistant turn (post-process).
# It receives a JSON payload on stdin with the keys:
#   "role": "assistant" | "user"
#   "content": "..."
#   "metadata": {optional extra info}
# It will insert a log record into the universal-agent-memory SQLite DB.

# 统一遵循 universal-agent-memory 官方路径约定：~/.config/opencode/memory
DB_PATH = pathlib.Path('~/.config/opencode/memory/memory.db').expanduser()

def insert_log(entry):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO logs (id, source, timestamp, content, metadata) VALUES (?,?,?,?,?)",
        (
            str(uuid.uuid4()),
            entry.get('role', 'assistant'),
            datetime.datetime.now().isoformat(),
            entry.get('content', ''),
            json.dumps(entry.get('metadata', {}))
        )
    )
    conn.commit()
    conn.close()

if __name__ == '__main__':
    try:
        data = json.load(sys.stdin)
    except Exception as e:
        sys.stderr.write(f'Failed to parse JSON input: {e}\n')
        sys.exit(1)
    insert_log(data)
    print('✅ Log inserted via post_process script')
