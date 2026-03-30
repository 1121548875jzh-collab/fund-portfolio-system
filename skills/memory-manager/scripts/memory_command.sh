#!/bin/bash
# memory_command.sh - /memory 命令入口
# 由 Agent 调用，执行记忆力管理

set -e

SCRIPTS_DIR="/root/.openclaw/workspace/scripts"
PYTHON_HOOKS="$SCRIPTS_DIR/memory_hooks.py"
BASH_HOOKS="$SCRIPTS_DIR/memory_hooks.sh"

# 子命令处理
cmd="${1:-status}"

case "$cmd" in
    status|stats)
        python3 "$PYTHON_HOOKS" stats
        ;;
    
    duplicates)
        python3 "$PYTHON_HOOKS" duplicates
        ;;
    
    clean)
        # 先备份，再清理
        echo "📦 先备份..."
        python3 "$PYTHON_HOOKS" backup
        echo ""
        echo "🧹 清理重复记忆..."
        python3 "$PYTHON_HOOKS" clean --force
        ;;
    
    backup)
        python3 "$PYTHON_HOOKS" backup
        ;;
    
    health)
        python3 "$PYTHON_HOOKS" health
        ;;
    
    report)
        python3 "$PYTHON_HOOKS" report
        ;;
    
    maintain)
        "$BASH_HOOKS" maintain
        ;;
    
    verify)
        "$BASH_HOOKS" verify
        ;;
    
    recover)
        "$BASH_HOOKS" recover
        ;;
    
    compact)
        # 记忆力管理 + 压缩建议
        echo "=== 记忆力管理 ==="
        python3 "$PYTHON_HOOKS" stats
        echo ""
        echo "=== 健康检查 ==="
        python3 "$PYTHON_HOOKS" health | head -20
        echo ""
        echo "=== 上下文压缩 ==="
        echo "💡 请发送 /compact 命令来压缩当前会话上下文"
        echo "   这会总结旧对话，释放 token 空间"
        ;;
    
    *)
        echo "用法: /memory <command>"
        echo ""
        echo "命令:"
        echo "  status   - 显示记忆系统状态"
        echo "  stats    - 详细统计"
        echo "  clean    - 清除重复记忆"
        echo "  backup   - 手动备份"
        echo "  health   - 健康检查"
        echo "  report   - JSON 报告"
        echo "  maintain - 完整维护"
        echo "  compact  - 上下文压缩提示"
        ;;
esac