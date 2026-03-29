#!/bin/bash
# 记忆清理脚本 - workspace-coder

LOG_DIR="/root/.openclaw/workspace-coder/logs"
MEMORY_DIR="/root/.openclaw/workspace-coder/memory"
MAX_DAYS=30

mkdir -p "$LOG_DIR"

find "$LOG_DIR" -name "*.log" -mtime +$MAX_DAYS -delete 2>/dev/null
find "$MEMORY_DIR" -name "*.bak" -mtime +$MAX_DAYS -delete 2>/dev/null

echo "[$(date)] Memory cleanup completed for workspace-coder"