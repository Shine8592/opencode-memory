#!/usr/bin/env bash
# Backup the Hermes SQLite memory database daily
DB_PATH="$HOME/.hermes/memory/memory.db"
BACKUP_DIR="$HOME/sqlite_backups"
mkdir -p "$BACKUP_DIR"
DATE=$(date +%F)
BACKUP_FILE="$BACKUP_DIR/memory_${DATE}.sql"
sqlite3 "$DB_PATH" .dump > "$BACKUP_FILE"
if [ $? -eq 0 ]; then
  echo "✅ SQLite backup created at $BACKUP_FILE"
else
  echo "❌ Failed to backup SQLite database"
fi
