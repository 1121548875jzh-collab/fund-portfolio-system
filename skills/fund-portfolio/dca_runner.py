#!/usr/bin/env python3
"""
基金持仓管理系统 - 定投执行

执行时间: 8:23

规则: 从数据库读取定投配置
- dca_config表：周定投金额
- is_qdii字段：标记QDII基金
"""
import sqlite3
from datetime import datetime
import os

DB_PATH = '/root/.openclaw/workspace-coder/skills/fund-portfolio/fund_portfolio.db'

def get_dca_config(conn):
    """从数据库读取定投配置"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fund_code, fund_name, weekday_1, weekday_2, weekday_3, weekday_4, weekday_5, 
               monthly_day, monthly_amount, is_qdii
        FROM dca_config WHERE enabled = 1
    """)
    return cursor.fetchall()

def run_dca():
    """执行定投"""
    today = datetime.now()
    weekday = today.weekday()  # 0=周一, 1=周二, ...
    day = today.day
    
    print(f"=== 定投执行 {today.strftime('%Y-%m-%d %A')} ===")
    
    if not os.path.exists(DB_PATH):
        print("数据库不存在")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 从数据库读取配置
    config = get_dca_config(conn)
    
    if not config:
        print("无定投配置")
        conn.close()
        return
    
    trades_created = 0
    weekday_name = ['周一', '周二', '周三', '周四', '周五'][weekday]
    
    # 周定投
    print(f"\n周定投 ({weekday_name}):")
    for fund_code, fund_name, w1, w2, w3, w4, w5, monthly_day, monthly_amount, is_qdii in config:
        # 获取当天的定投金额
        amounts = [w1, w2, w3, w4, w5]
        amount = amounts[weekday] if weekday < 5 else 0
        
        if amount > 0:
            cursor.execute('''
                INSERT INTO fund_trades (trade_date, trade_type, amount, fund_code, status, is_qdii)
                VALUES (?, 'BUY', ?, ?, 'PENDING', ?)
            ''', (today.strftime('%Y-%m-%d'), amount, fund_code, is_qdii))
            
            print(f"  {fund_code} {fund_name}: {amount}元")
            trades_created += 1
    
    # 月定投（指定日期）
    print(f"\n月定投检查:")
    for fund_code, fund_name, w1, w2, w3, w4, w5, monthly_day, monthly_amount, is_qdii in config:
        if monthly_day > 0 and day == monthly_day and monthly_amount > 0:
            cursor.execute('''
                INSERT INTO fund_trades (trade_date, trade_type, amount, fund_code, status, is_qdii)
                VALUES (?, 'BUY', ?, ?, 'PENDING', ?)
            ''', (today.strftime('%Y-%m-%d'), monthly_amount, fund_code, is_qdii))
            
            print(f"  {fund_code} {fund_name}: {monthly_amount}元 (月定投{monthly_day}号)")
            trades_created += 1
    
    if trades_created == 0:
        print("  今日无定投")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ 创建 {trades_created} 笔定投交易")

if __name__ == '__main__':
    run_dca()