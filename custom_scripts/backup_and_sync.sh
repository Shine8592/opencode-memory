#!/usr/bin/env bash
# Backup SQLite memory DB, email it, and push to remote GitHub repo.

# ---- Configuration ----
# 记忆存储路径统一遵循 universal-agent-memory 官方约定：
#   全局脚本目录    ~/.config/opencode/memory/scripts
#   记忆存储目录    ~/.config/opencode/memory/
DB_PATH="$HOME/.config/opencode/memory/memory.db"
BACKUP_ROOT="$HOME/universal_agent_memory_backup"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
ARCHIVE_NAME="memory_backup_${TIMESTAMP}.tar.gz"
ARCHIVE_PATH="$BACKUP_ROOT/$ARCHIVE_NAME"

# Email settings (Himalaya)
RECIPIENT="${BACKUP_EMAIL:-your-email@example.com}"
EMAIL_SUBJECT="Universal Agent Memory Backup ${TIMESTAMP}"
EMAIL_BODY="Attached is the SQLite memory backup for ${TIMESTAMP}."

# GitHub settings（备份仓独立于主仓）
GIT_REPO="${BACKUP_REPO:-https://github.com/Shine8592/universal-agent-memory-backup.git}"
GIT_BRANCH="main"
GITHUB_TOKEN="<GITHUB_TOKEN>"

# ---- Ensure backup directory exists ----
mkdir -p "$BACKUP_ROOT"

# ---- Create tar.gz archive of the SQLite DB ----
if [ -f "$DB_PATH" ]; then
  tar -czf "$ARCHIVE_PATH" -C "$(dirname "$DB_PATH")" "$(basename "$DB_PATH")"
  echo "✅ Created archive $ARCHIVE_PATH"
else
  echo "⚠️ SQLite DB not found at $DB_PATH"
  exit 1
fi

# ---- Send email via Himalaya (if available) ----
if command -v himalaya >/dev/null 2>&1; then
  himalaya send -t "$RECIPIENT" -s "$EMAIL_SUBJECT" -b "$EMAIL_BODY" -a "$ARCHIVE_PATH" > /dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "✅ Email sent to $RECIPIENT"
  else
    echo "⚠️ Failed to send email via Himalaya"
  fi
else
  echo "⚠️ Himalaya CLI not installed, skipping email step"
fi

# ---- Git push backup to remote repository ----
cd "$BACKUP_ROOT" || { echo "⚠️ Cannot cd to $BACKUP_ROOT"; exit 1; }
# Initialize repo if not already a git repo
if [ ! -d ".git" ]; then
  git init
  git remote add origin "$GIT_REPO"
fi
# Configure git to use token for authentication
git config user.name "UniversalAgentMemoryBackupBot"
git config user.email "bot@universal-agent-memory.local"
# Add archive and commit
git add "$ARCHIVE_NAME"
git commit -m "Backup $TIMESTAMP"
# Push using token
GIT_ASKPASS=$(mktemp)
cat > "$GIT_ASKPASS" <<EOF
#!/usr/bin/env bash
exec echo "$GITHUB_TOKEN"
EOF
chmod +x "$GIT_ASKPASS"
GIT_ASKPASS="$GIT_ASKPASS" git push -u origin "$GIT_BRANCH" --force-with-lease
rm -f "$GIT_ASKPASS"
if [ $? -eq 0 ]; then
  echo "✅ Backup pushed to GitHub repository"
else
  echo "⚠️ Failed to push backup to GitHub"
fi
