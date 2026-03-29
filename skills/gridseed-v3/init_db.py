#!/usr/bin/env python3
"""
GridSeed V3.0 - 数据库初始化

表结构:
- strategy_positions: 策略持仓
- strategy_trades: 策略交易记录
"""
import sqlite3
import os

DB_PATH = '/root/.openclaw/workspace-coder/skills/gridseed-v3/data/gridseed.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 策略持仓
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS strategy_positions (
            fund_code TEXT PRIMARY KEY,
            fund_name TEXT,
            phase TEXT DEFAULT 'ACCUMULATION',
            step INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0,
            total_shares REAL DEFAULT 0,
            last_nav REAL,
            last_date TEXT,
            last_action TEXT,
            last_amount REAL DEFAULT 0,
            grid_base_nav REAL,
            grid_shares REAL DEFAULT 0,
            grid_cost REAL DEFAULT 0,
            grid_profit REAL DEFAULT 0,
            min_amount REAL DEFAULT 1500.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 策略交易
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS strategy_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fund_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            trade_type TEXT NOT NULL,
            amount REAL,
            nav REAL,
            shares REAL,
            trigger_reason TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ GridSeed 数据库初始化完成: {DB_PATH}")

if __name__ == '__main__':
    init_db()