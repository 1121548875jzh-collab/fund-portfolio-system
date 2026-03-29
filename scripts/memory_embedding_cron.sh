#!/bin/bash
# 记忆向量化脚本 - workspace-coder

VECTOR_DB="/root/.openclaw/memory/vector_memory.db"
LOG_FILE="/root/.openclaw/workspace-coder/logs/memory_embedding.log"

mkdir -p "$(dirname $LOG_FILE)"

TOTAL=$(sqlite3 "$VECTOR_DB" "SELECT COUNT(*) FROM memories;" 2>/dev/null)
WITH_EMBED=$(sqlite3 "$VECTOR_DB" "SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL;" 2>/dev/null)

if [ -n "$TOTAL" ] && [ -n "$WITH_EMBED" ]; then
    COVERAGE=$((WITH_EMBED * 100 / TOTAL))
    echo "[$(date)] Vector status: $WITH_EMBED/$TOTAL (${COVERAGE}% coverage)" >> "$LOG_FILE"
else
    echo "[$(date)] Warning: Could not query vector database" >> "$LOG_FILE"
fi