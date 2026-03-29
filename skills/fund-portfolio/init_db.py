#!/usr/bin/env python3
"""
基金持仓管理系统 - 数据库初始化

表结构:
- fund_holdings: 当前持仓
- fund_trades: 交易记录
- fund_nav_history: 净值历史
- daily_fund_snapshot: 每日快照
- dca_config: 定投配置
- closed_position_profit: 清仓盈亏
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'fund_portfolio.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. 当前持仓
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fund_holdings (
            fund_code TEXT PRIMARY KEY,
            fund_name TEXT,
            shares REAL NOT NULL DEFAULT 0,
            base_amount REAL NOT NULL DEFAULT 0,
            nav REAL,
            nav_date TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 2. 交易记录
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fund_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            trade_time TEXT,
            amount REAL,
            trade_type TEXT NOT NULL,
            fund_code TEXT NOT NULL,
            original_remark TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            confirm_date TEXT,
            is_qdii INTEGER DEFAULT 0,
            is_shares INTEGER DEFAULT 0
        )
    ''')
    
    # 3. 净值历史
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fund_nav_history (
            fund_code TEXT NOT NULL,
            nav_date TEXT NOT NULL,
            nav REAL NOT NULL,
            PRIMARY KEY (fund_code, nav_date)
        )
    ''')
    
    # 4. 每日快照
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_fund_snapshot (
            date TEXT NOT NULL,
            fund_code TEXT NOT NULL,
            fund_name TEXT,
            shares REAL,
            base_amount REAL,
            asset_value REAL,
            profit REAL,
            nav REAL,
            daily_profit REAL DEFAULT 0,
            PRIMARY KEY (date, fund_code)
        )
    ''')
    
    # 5. 定投配置
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dca_config (
            fund_code TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 1,
            weekday_1 INTEGER DEFAULT 0,
            weekday_2 INTEGER DEFAULT 0,
            weekday_3 INTEGER DEFAULT 0,
            weekday_4 INTEGER DEFAULT 0,
            weekday_5 INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 6. 清仓盈亏
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS closed_position_profit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fund_code TEXT NOT NULL,
            fund_name TEXT,
            close_date TEXT NOT NULL,
            total_profit REAL,
            base_amount REAL,
            close_amount REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ 数据库初始化完成: {DB_PATH}")

if __name__ == '__main__':
    init_db()