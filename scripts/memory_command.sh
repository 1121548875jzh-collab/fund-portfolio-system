#!/bin/bash
# /memory 命令接口 - 四层记忆管理

WORKSPACE="/root/.openclaw/workspace"
MANAGER="$WORKSPACE/scripts/memory_manager.py"

case "$1" in
    status)
        python3 "$MANAGER" status
        ;;
    
    write)
        # /memory write L2 GridSeed "策略优化完成"
        layer="$2"
        name="$3"
        content="$4"
        
        case "$layer" in
            L1)
                python3 "$MANAGER" write --layer L1 --content "$content" --section "$name"
                ;;
            L2)
                python3 "$MANAGER" write --layer L2 --project "$name" --content "$content"
                ;;
            L3)
                python3 "$MANAGER" write --layer L3 --category "$name" --content "$content"
                ;;
            L4)
                python3 "$MANAGER" write --layer L4 --content "$content"
                ;;
            *)
                echo "用法: /memory write L1|L2|L3|L4 [名称] [内容]"
                ;;
        esac
        ;;
    
    read)
        # /memory read L2 GridSeed
        layer="$2"
        name="$3"
        python3 "$MANAGER" read --layer "$layer" --name "$name"
        ;;
    
    search)
        # /memory search "基金策略"
        query="$2"
        limit="${3:-5}"
        python3 "$MANAGER" search --query "$query" --limit "$limit"
        ;;
    
    sync)
        # 全量同步
        python3 "$WORKSPACE/scripts/memory_sync_hook.py" --sync-all
        ;;
    
    clean)
        # 清理重复记忆
        python3 "$WORKSPACE/scripts/memory_cleanup.py" 2>/dev/null || echo "清理脚本未找到"
        ;;
    
    *)
        echo "📖 四层记忆管理系统"
        echo "━━━━━━━━━━━━━━━━━━━━"
        echo "命令:"
        echo "  /memory status         - 查看系统状态"
        echo "  /memory write L1-L4    - 写入记忆"
        echo "  /memory read L1-L4     - 读取记忆"
        echo "  /memory search [查询]  - 向量检索"
        echo "  /memory sync           - 全量同步向量库"
        echo "  /memory clean          - 清理重复记忆"
        echo ""
        echo "层级说明:"
        echo "  L1 索引: MEMORY.md (核心索引, <50行)"
        echo "  L2 项目: active-projects/*.md"
        echo "  L3 经验: tacit-knowledge/lessons-learned.md"
        echo "  L4 日志: YYYY-MM-DD.md"
        ;;
esac