#!/usr/bin/env python3
"""
基金持仓管理系统 - 每日更新

功能:
1. 从 Tushare 获取最新净值
2. 确认 PENDING 交易
3. 生成每日快照

执行时间: 8:20

计算规则:
- 买入：金额 → 份额（用交易日净值）
- 卖出：份额 → 金额（用交易日净值）
- QDII基金: T+2确认
"""
import sqlite3
import tushare as ts
from datetime import datetime, timedelta
import os
import sys

# 添加父目录到路径，支持导入config
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import TS_TOKEN, FUND_DB
import strategy_monitor

def get_qdii_funds(conn):
    """从数据库获取QDII基金列表"""
    cursor = conn.cursor()
    cursor.execute("SELECT fund_code FROM dca_config WHERE is_qdii = 1")
    return [row[0] for row in cursor.fetchall()]

def get_fund_nav(pro, fund_code):
    """从 Tushare 获取基金净值"""
    try:
        df = pro.fund_nav(ts_code=f'{fund_code}.OF')
        if df.empty:
            return None, None
        
        nav = float(df.iloc[0]['unit_nav'])
        nav_date = str(df.iloc[0]['nav_date'])
        return nav, nav_date
    except Exception as e:
        print(f"  获取净值失败 {fund_code}: {e}")
        return None, None

def get_nav_by_date(conn, fund_code, nav_date):
    """获取指定日期的净值"""
    cursor = conn.cursor()
    cursor.execute('SELECT nav FROM fund_nav_history WHERE fund_code = ? AND nav_date = ?', (fund_code, nav_date))
    row = cursor.fetchone()
    return row[0] if row else None

def update_nav_history(conn, fund_code, nav_date, nav):
    """更新净值历史"""
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO fund_nav_history (fund_code, nav_date, nav)
        VALUES (?, ?, ?)
    ''', (fund_code, nav_date, nav))
    conn.commit()

def confirm_pending_trades(conn, pro):
    """
    确认 PENDING 交易
    
    份额计算规则：
    - 买入：份额 = 金额 / 交易日净值
    - 卖出：金额 = 份额 × 交易日净值
    - 清仓时记录盈亏到 closed_position_profit
    """
    cursor = conn.cursor()
    
    # 从数据库获取QDII列表
    qdii_funds = get_qdii_funds(conn)
    
    cursor.execute('''
        SELECT id, fund_code, amount, trade_type, trade_date, is_shares
        FROM fund_trades WHERE status = 'PENDING'
    ''')
    pending = cursor.fetchall()
    
    if not pending:
        print("无待确认交易")
        return
    
    print(f"\n=== 确认 {len(pending)} 笔交易 ===")
    
    for trade_id, fund_code, amount, trade_type, trade_date, is_shares in pending:
        # 判断是否QDII
        is_qdii = fund_code in qdii_funds
        
        # T+1 确认规则（QDII是T+2）
        trade_dt = datetime.strptime(trade_date, '%Y-%m-%d')
        if is_qdii:
            confirm_date = (trade_dt + timedelta(days=2)).strftime('%Y-%m-%d')
        else:
            confirm_date = (trade_dt + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # 检查是否到确认日期
        today = datetime.now().strftime('%Y-%m-%d')
        if confirm_date > today:
            print(f"  {fund_code}: 等待确认日期 {confirm_date}")
            continue
        
        # 获取交易日净值
        trade_date_fmt = trade_date.replace('-', '')
        nav = get_nav_by_date(conn, fund_code, trade_date_fmt)
        
        if not nav:
            nav_tushare, nav_date_tushare = get_fund_nav(pro, fund_code)
            
            if not nav_tushare:
                print(f"  {fund_code}: 无法获取净值")
                continue
            
            update_nav_history(conn, fund_code, nav_date_tushare, nav_tushare)
            
            if nav_date_tushare != trade_date_fmt:
                print(f"  {fund_code}: 交易日{trade_date}净值未出，等待")
                continue
            
            nav = nav_tushare
        
        print(f"  {fund_code}: 净值 {nav:.4f}")
        
        if trade_type == 'BUY':
            shares = amount / nav
            
            cursor.execute('SELECT shares, base_amount, fund_name FROM fund_holdings WHERE fund_code = ?', (fund_code,))
            row = cursor.fetchone()
            
            if row and row[0]:
                new_shares = row[0] + shares
                new_base = row[1] + amount
                cursor.execute('UPDATE fund_holdings SET shares = ?, base_amount = ?, nav = ?, nav_date = ?, updated_at = CURRENT_TIMESTAMP WHERE fund_code = ?',
                    (new_shares, new_base, nav, trade_date_fmt, fund_code))
                fund_name = row[2]
            else:
                cursor.execute('SELECT fund_name FROM fund_holdings WHERE fund_code = ?', (fund_code,))
                fund_name_row = cursor.fetchone()
                fund_name = fund_name_row[0] if fund_name_row else fund_code
                cursor.execute('INSERT INTO fund_holdings (fund_code, fund_name, shares, base_amount, nav, nav_date) VALUES (?, ?, ?, ?, ?, ?)',
                    (fund_code, fund_name, shares, amount, nav, trade_date_fmt))
            
            print(f"  ✅ 买入 {fund_code} {amount}元 → {shares:.2f}份")
            
        elif trade_type == 'SELL':
            cursor.execute('SELECT shares, base_amount, fund_name FROM fund_holdings WHERE fund_code = ?', (fund_code,))
            row = cursor.fetchone()
            
            if row:
                old_shares, old_base, fund_name = row
                sell_shares = amount if is_shares else amount / nav
                actual_amount = sell_shares * nav
                
                new_shares = old_shares - sell_shares
                new_base = old_base * (1 - sell_shares / old_shares) if old_shares > 0 else 0
                
                if new_shares <= 0.01:
                    # 清仓：记录盈亏
                    profit = actual_amount - old_base
                    
                    cursor.execute('''
                        INSERT INTO closed_position_profit (fund_code, fund_name, close_date, total_profit, base_amount, close_amount)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (fund_code, fund_name, trade_date, profit, old_base, actual_amount))
                    
                    cursor.execute('DELETE FROM fund_holdings WHERE fund_code = ?', (fund_code,))
                    print(f"  ✅ 清仓 {fund_code} {sell_shares:.2f}份 → {actual_amount:.2f}元，盈亏: {profit:+.2f}元")
                else:
                    cursor.execute('UPDATE fund_holdings SET shares = ?, base_amount = ?, nav = ?, nav_date = ?, updated_at = CURRENT_TIMESTAMP WHERE fund_code = ?',
                        (new_shares, new_base, nav, trade_date_fmt, fund_code))
                    print(f"  ✅ 卖出 {fund_code} {sell_shares:.2f}份 → {actual_amount:.2f}元")
        
        cursor.execute('UPDATE fund_trades SET status = ?, confirm_date = ? WHERE id = ?',
            ('CONFIRMED', confirm_date, trade_id))
    
    conn.commit()

def generate_snapshot(conn, pro):
    """生成每日快照"""
    cursor = conn.cursor()
    
    qdii_funds = get_qdii_funds(conn)
    
    cursor.execute('SELECT fund_code, fund_name, shares, base_amount FROM fund_holdings')
    holdings = cursor.fetchall()
    
    if not holdings:
        print("无持仓")
        return
    
    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    print(f"\n=== 生成 {today} 快照 ===")
    
    # 更新净值历史
    for fund_code, fund_name, shares, base_amount in holdings:
        nav, nav_date = get_fund_nav(pro, fund_code)
        if nav and nav_date:
            update_nav_history(conn, fund_code, nav_date, nav)
    
    total_daily = 0
    
    for fund_code, fund_name, shares, base_amount in holdings:
        is_qdii = fund_code in qdii_funds
        
        today_fmt = today.replace('-', '')
        yesterday_fmt = yesterday.replace('-', '')
        
        nav_today = get_nav_by_date(conn, fund_code, today_fmt)
        nav_yesterday = get_nav_by_date(conn, fund_code, yesterday_fmt)
        
        if not nav_today:
            nav_today = nav_yesterday
        
        if not nav_today:
            print(f"  {fund_code}: 无净值数据")
            continue
        
        asset_value = shares * nav_today
        profit = asset_value - base_amount
        daily_profit = shares * (nav_today - nav_yesterday) if nav_yesterday else 0
        
        total_daily += daily_profit
        
        cursor.execute('''
            INSERT OR REPLACE INTO daily_fund_snapshot 
            (date, fund_code, fund_name, shares, base_amount, asset_value, profit, nav, daily_profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (today, fund_code, fund_name, shares, base_amount, asset_value, profit, nav_today, daily_profit))
        
        # 同步更新 fund_holdings 表的展示用净值
        cursor.execute('''
            UPDATE fund_holdings SET nav = ?, nav_date = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE fund_code = ?
        ''', (nav_today, today_fmt, fund_code))
        
        print(f"  {fund_code}: 净值{nav_today:.4f} 资产{asset_value:.2f} 盈亏{profit:+.2f}")
    
    conn.commit()

    # --- 新增：BIAS & Drawdown 策略监控 ---
    print("\n=== 更新技术指标监控 ===")
    for fund_code, fund_name, shares, base_amount in holdings:
        try:
            res = strategy_monitor.monitor_fund(fund_code)
            if res:
                strategy_monitor.save_stats(fund_code, res)
                print(f"  {fund_code}: BIAS-250:{res['bias_250']:.2%} Drawdown:{res['drawdown']:.2%} -> {res['level']}")
        except Exception as e:
            print(f"  {fund_code}: 计算策略信号识别失败: {e}")
    # -----------------------------------

    print(f"\n当日涨跌合计: {total_daily:+.2f}")

def main():
    print(f"=== 基金每日更新 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    
    if not os.path.exists(FUND_DB):
        print("数据库不存在")
        return
    
    conn = sqlite3.connect(FUND_DB)
    pro = ts.pro_api(TS_TOKEN)
    
    try:
        confirm_pending_trades(conn, pro)
        generate_snapshot(conn, pro)
    finally:
        conn.close()

if __name__ == '__main__':
    main()