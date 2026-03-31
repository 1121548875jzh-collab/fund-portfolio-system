#!/usr/bin/env python3
"""
基金系统配置数据库初始化

将写死的配置改为数据库驱动：
- 定投配置
- GridSeed策略参数
- 基金类型标记（QDII等）
"""
import sqlite3

FUND_DB = '/root/.openclaw/workspace-coder/skills/fund-portfolio/fund_portfolio.db'
GRID_DB = '/root/.openclaw/workspace-coder/skills/gridseed-v3/data/gridseed.db'

def load_initial_data():
    """加载初始配置数据"""
    
    fund_conn = sqlite3.connect(FUND_DB)
    fund_cursor = fund_conn.cursor()
    
    # 定投配置（从代码迁移）
    dca_data = [
        ('017437', '华宝纳斯达克精选(QDII)C', 1, 30, 0, 30, 0, 0, 0, 0, 1),
        ('017091', '景顺长城纳斯达克科技(QDII)A', 1, 25, 0, 25, 0, 0, 0, 0, 1),
        ('017641', '摩根标普500人民币A', 1, 25, 0, 25, 0, 0, 0, 0, 1),
        ('002963', '易方达黄金ETF联接C', 1, 0, 25, 0, 25, 0, 0, 0, 0, 0),
        ('003958', '安信量化沪深300增强C', 1, 0, 25, 0, 25, 0, 0, 0, 0, 0),
        ('009982', '万家创业板指数增强C', 1, 0, 30, 0, 30, 0, 0, 0, 0, 0),
        ('012349', '天弘恒生科技ETF联接C', 1, 0, 30, 0, 30, 0, 0, 0, 0, 0),
        ('016441', '华夏中证红利质量ETF联接', 1, 0, 60, 0, 0, 0, 0, 0, 0, 0),
        ('022431', '华夏中证A500ETF联接C', 1, 0, 30, 0, 30, 0, 0, 0, 0, 0),
        ('023920', '国泰富时中国A股自由现金流C', 1, 0, 50, 0, 0, 0, 0, 0, 0, 0),
        ('021909', '中欧红利优享C', 1, 0, 0, 0, 50, 0, 0, 0, 0, 0),
        ('019261', '富国恒生港股通高股息低波动C', 1, 40, 0, 0, 0, 0, 0, 0, 0, 0),
    ]
    
    for row in dca_data:
        fund_cursor.execute('''
            INSERT OR REPLACE INTO dca_config 
            (fund_code, fund_name, enabled, weekday_1, weekday_2, weekday_3, weekday_4, weekday_5, monthly_day, monthly_amount, is_qdii)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', row)
    
    # 基金类型表
    fund_cursor.execute('''
        CREATE TABLE IF NOT EXISTS fund_types (
            fund_code TEXT PRIMARY KEY,
            fund_name TEXT,
            fund_type TEXT,
            confirm_days INTEGER DEFAULT 1,
            risk_level TEXT,
            notes TEXT
        )
    ''')
    
    fund_types_data = [
        ('017437', '华宝纳斯达克精选(QDII)C', 'QDII', 2, '高', '纳斯达克'),
        ('017091', '景顺长城纳斯达克科技(QDII)A', 'QDII', 2, '高', '纳斯达克科技'),
        ('017641', '摩根标普500人民币A', 'QDII', 2, '高', '标普500'),
        ('002963', '易方达黄金ETF联接C', 'ETF联接', 1, '中', '黄金'),
    ]
    
    for row in fund_types_data:
        fund_cursor.execute('''
            INSERT OR IGNORE INTO fund_types (fund_code, fund_name, fund_type, confirm_days, risk_level, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', row)
    
    fund_conn.commit()
    fund_conn.close()
    
    # GridSeed策略参数
    grid_conn = sqlite3.connect(GRID_DB)
    grid_cursor = grid_conn.cursor()
    
    grid_cursor.execute('''
        CREATE TABLE IF NOT EXISTS strategy_params (
            param_name TEXT PRIMARY KEY,
            param_value REAL,
            description TEXT
        )
    ''')
    
    default_params = [
        ('l1_l4_ratio', 0.15, 'L1-L4加仓比例15%'),
        ('l5_l6_ratio', 0.30, 'L5-L6加仓比例30%'),
        ('l1_l4_threshold', -0.03, 'L1-L4跌幅阈值-3%'),
        ('l5_l6_threshold', -0.05, 'L5-L6跌幅阈值-5%'),
        ('grid_buy_threshold', -0.03, '网格买入阈值-3%'),
        ('grid_sell_threshold', 0.10, '网格卖出阈值+10%'),
        ('accum_sell_threshold', 0.15, '建仓期卖出阈值+15%'),
        ('idle_trade_days', 10, '闲置唤醒交易日数'),
        ('grid_buy_amount', 100, '网格买入金额'),
        ('idle_wake_amount', 100, '闲置唤醒加仓金额'),
    ]
    
    for name, value, desc in default_params:
        grid_cursor.execute('''
            INSERT OR IGNORE INTO strategy_params (param_name, param_value, description)
            VALUES (?, ?, ?)
        ''', (name, value, desc))
    
    grid_conn.commit()
    grid_conn.close()
    
    print("✅ 配置数据加载完成")

if __name__ == '__main__':
    load_initial_data()
    
    # 显示结果
    fund_conn = sqlite3.connect(FUND_DB)
    print("\n定投配置表:")
    for row in fund_conn.execute("SELECT fund_code, fund_name, weekday_1, weekday_2, weekday_3, weekday_4 FROM dca_config LIMIT 5"):
        print(f"  {row}")
    
    grid_conn = sqlite3.connect(GRID_DB)
    print("\n策略参数表:")
    for row in grid_conn.execute("SELECT * FROM strategy_params"):
        print(f"  {row}")
    
    fund_conn.close()
    grid_conn.close()