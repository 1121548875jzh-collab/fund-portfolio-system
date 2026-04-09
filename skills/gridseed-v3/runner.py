#!/usr/bin/env python3
"""
GridSeed V3.0 - 运行器

入口脚本，整合所有功能
"""
import sys
import os

# 添加路径
sys.path.insert(0, os.path.dirname(__file__))

from strategy import run_check
from sync_trades import sync_trades
from init_db import init_db
from check_consistency import main as run_consistency_check
from bootstrap_positions import bootstrap_all
from backfill_trade_semantics import main as run_backfill_trade_semantics

def main():
    if len(sys.argv) < 2:
        print("用法: python runner.py [check|sync|init|consistency|bootstrap|backfill-semantics]")
        return
    
    cmd = sys.argv[1]
    
    if cmd == 'check':
        run_check()
    elif cmd == 'sync':
        sync_trades()
    elif cmd == 'init':
        init_db()
    elif cmd == 'consistency':
        raise SystemExit(run_consistency_check())
    elif cmd == 'bootstrap':
        force = '--force' in sys.argv[2:]
        raise SystemExit(bootstrap_all(only_if_empty=not force))
    elif cmd == 'backfill-semantics':
        raise SystemExit(run_backfill_trade_semantics())
    else:
        print(f"未知命令: {cmd}")

if __name__ == '__main__':
    main()