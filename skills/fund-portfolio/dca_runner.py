#!/usr/bin/env python3
"""
基金持仓管理系统 - 定投执行

执行时间: 8:23

规则:
- 周一: 017437(30), 017091(25), 017641(25)
- 周二: 002963(25), 003958(25), 009982(30), 012349(30), 016441(60), 022431(30), 023920(50)
- 周三: 017437(30), 017091(25), 017641(25)
- 周四: 002963(25), 003958(25), 009982(30), 012349(30), 021909(50), 022431(30)
- 25号: 月定投 (QDII基金)
"""
import sqlite3
from datetime import datetime
import os

DB_PATH = '/root/.openclaw/workspace-coder/skills/fund-portfolio/fund_portfolio.db'

# 定投配置
DCA_CONFIG = {
    # 周一定投 (周一=0)
    0: [
        ('017437', '华宝纳斯达克精选(QDII)C', 30),
        ('017091', '景顺长城纳斯达克科技(QDII)A', 25),
        ('017641', '摩根标普500人民币A', 25),
    ],
    # 周二定投
    1: [
        ('002963', '易方达黄金ETF联接C', 25),
        ('003958', '安信量化沪深300增强C', 25),
        ('009982', '万家创业板指数增强C', 30),
        ('012349', '天弘恒生科技ETF联接C', 30),
        ('016441', '华夏中证红利质量ETF联接', 60),
        ('022431', '华夏中证A500ETF联接C', 30),
        ('023920', '国泰富时中国A股自由现金流C', 50),
    ],
    # 周三定投
    2: [
        ('017437', '华宝纳斯达克精选(QDII)C', 30),
        ('017091', '景顺长城纳斯达克科技(QDII)A', 25),
        ('017641', '摩根标普500人民币A', 25),
    ],
    # 周四定投
    3: [
        ('002963', '易方达黄金ETF联接C', 25),
        ('003958', '安信量化沪深300增强C', 25),
        ('009982', '万家创业板指数增强C', 30),
        ('012349', '天弘恒生科技ETF联接C', 30),
        ('021909', '中欧红利优享C', 50),
        ('022431', '华夏中证A500ETF联接C', 30),
    ],
}

# 月定投 (25号)
MONTHLY_DCA = [
    ('017437', '华宝纳斯达克精选(QDII)C', 30),
    ('017091', '景顺长城纳斯达克科技(QDII)A', 25),
    ('017641', '摩根标普500人民币A', 25),
]

def run_dca():
    """执行定投"""
    today = datetime.now()
    weekday = today.weekday()
    day = today.day
    
    print(f"=== 定投执行 {today.strftime('%Y-%m-%d %A')} ===")
    
    # 初始化数据库
    if not os.path.exists(DB_PATH):
        print("数据库不存在")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 加载定投配置
    cursor.execute("SELECT fund_code, weekday_1, weekday_2, weekday_3, weekday_4, weekday_5 FROM dca_config WHERE enabled = 1")
    db_config = {row[0]: row[1:] for row in cursor.fetchall()}
    
    trades_created = 0
    
    # 周定投
    if weekday in DCA_CONFIG:
        print(f"\n周定投 ({['周一','周二','周三','周四','周五'][weekday]}):")
        for fund_code, fund_name, amount in DCA_CONFIG[weekday]:
            # 检查数据库配置
            if fund_code in db_config:
                db_amount = db_config[fund_code][weekday]
                if db_amount and db_amount > 0:
                    amount = db_amount
            
            # 创建交易记录
            cursor.execute('''
                INSERT INTO fund_trades (trade_date, trade_type, amount, fund_code, status, is_qdii)
                VALUES (?, 'BUY', ?, ?, 'PENDING', ?)
            ''', (today.strftime('%Y-%m-%d'), amount, fund_code, 1 if fund_code in ['017437', '017091', '017641'] else 0))
            
            print(f"  {fund_code} {fund_name}: {amount}元")
            trades_created += 1
    
    # 月定投 (25号)
    if day == 25:
        print(f"\n月定投 (25号):")
        for fund_code, fund_name, amount in MONTHLY_DCA:
            cursor.execute('''
                INSERT INTO fund_trades (trade_date, trade_type, amount, fund_code, status, is_qdii)
                VALUES (?, 'BUY', ?, ?, 'PENDING', 1)
            ''', (today.strftime('%Y-%m-%d'), amount, fund_code))
            print(f"  {fund_code} {fund_name}: {amount}元")
            trades_created += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ 创建 {trades_created} 笔定投交易")

if __name__ == '__main__':
    run_dca()