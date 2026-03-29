#!/usr/bin/env python3
"""
GridSeed V3.0 - 运行器

入口脚本，整合所有功能
"""
import sys
import os

# 添加路径
sys.path.insert(0, os.path.dirname(__file__))

from strategy import check_actions, run_check
from sync_trades import sync_trades
from init_db import init_db

def main():
    if len(sys.argv) < 2:
        print("用法: python runner.py [check|sync|init]")
        return
    
    cmd = sys.argv[1]
    
    if cmd == 'check':
        run_check()
    elif cmd == 'sync':
        sync_trades()
    elif cmd == 'init':
        init_db()
    else:
        print(f"未知命令: {cmd}")

if __name__ == '__main__':
    main()