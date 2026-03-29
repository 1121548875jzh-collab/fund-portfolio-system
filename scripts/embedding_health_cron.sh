#!/bin/bash
# 嵌入健康检查脚本 - workspace-coder

VECTOR_DB="/root/.openclaw/memory/vector_memory.db"
LOG_FILE="/root/.openclaw/workspace-coder/logs/embedding_health.log"

mkdir -p "$(dirname $LOG_FILE)"

# 检查覆盖率
TOTAL=$(sqlite3 "$VECTOR_DB" "SELECT COUNT(*) FROM memories;" 2>/dev/null)
WITH_EMBED=$(sqlite3 "$VECTOR_DB" "SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL;" 2>/dev/null)

if [ -n "$TOTAL" ] && [ -n "$WITH_EMBED" ]; then
    COVERAGE=$((WITH_EMBED * 100 / TOTAL))
    
    if [ $COVERAGE -lt 50 ]; then
        echo "[$(date)] WARNING: Low coverage ${COVERAGE}% (${WITH_EMBED}/${TOTAL})" >> "$LOG_FILE"
    else
        echo "[$(date)] OK: ${COVERAGE}% coverage (${WITH_EMBED}/${TOTAL})" >> "$LOG_FILE"
    fi
else
    echo "[$(date)] ERROR: Could not query vector database" >> "$LOG_FILE"
fi