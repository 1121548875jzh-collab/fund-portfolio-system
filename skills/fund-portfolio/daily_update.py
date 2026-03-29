#!/usr/bin/env python3
"""
基金持仓管理系统 - 每日更新

功能:
1. 从 Tushare 获取最新净值
2. 确认 PENDING 交易
3. 生成每日快照
4. 发送邮件报告

执行时间: 8:20
"""
import sqlite3
import tushare as ts
from datetime import datetime, timedelta
import os

TS_TOKEN = '7b81c3a430995f2912509eea6e5932513760cf170626110a440c497c'
DB_PATH = '/root/.openclaw/workspace-coder/skills/fund-portfolio/fund_portfolio.db'
QDII_FUNDS = ['012062', '017641', '017437', '017091']

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

def update_nav_history(conn, fund_code, nav_date, nav):
    """更新净值历史"""
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO fund_nav_history (fund_code, nav_date, nav)
        VALUES (?, ?, ?)
    ''', (fund_code, nav_date, nav))
    conn.commit()

def confirm_pending_trades(conn, pro):
    """确认 PENDING 交易"""
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, fund_code, amount, trade_type, trade_date, is_qdii, is_shares
        FROM fund_trades WHERE status = 'PENDING'
    ''')
    pending = cursor.fetchall()
    
    if not pending:
        print("无待确认交易")
        return
    
    print(f"\n=== 确认 {len(pending)} 笔交易 ===")
    
    for trade_id, fund_code, amount, trade_type, trade_date, is_qdii, is_shares in pending:
        # T+1 确认规则
        trade_dt = datetime.strptime(trade_date, '%Y-%m-%d')
        if is_qdii:
            confirm_date = (trade_dt + timedelta(days=2)).strftime('%Y-%m-%d')
            nav_date = trade_date  # QDII用T日净值
        else:
            confirm_date = (trade_dt + timedelta(days=1)).strftime('%Y-%m-%d')
            nav_date = trade_date
        
        # 检查是否到确认日期
        today = datetime.now().strftime('%Y-%m-%d')
        if confirm_date > today:
            print(f"  {fund_code}: 等待确认日期 {confirm_date}")
            continue
        
        # 获取净值
        nav, actual_nav_date = get_fund_nav(pro, fund_code)
        if not nav:
            print(f"  {fund_code}: 无法获取净值")
            continue
        
        # 更新净值历史
        update_nav_history(conn, fund_code, actual_nav_date, nav)
        
        if trade_type == 'BUY':
            shares = amount / nav
            
            # 更新持仓
            cursor.execute('SELECT shares, base_amount FROM fund_holdings WHERE fund_code = ?', (fund_code,))
            row = cursor.fetchone()
            
            if row and row[0]:
                new_shares = row[0] + shares
                new_base = row[1] + amount
                cursor.execute('''
                    UPDATE fund_holdings 
                    SET shares = ?, base_amount = ?, nav = ?, nav_date = ?
                    WHERE fund_code = ?
                ''', (new_shares, new_base, nav, actual_nav_date, fund_code))
            else:
                cursor.execute('''
                    INSERT INTO fund_holdings (fund_code, shares, base_amount, nav, nav_date)
                    VALUES (?, ?, ?, ?, ?)
                ''', (fund_code, shares, amount, nav, actual_nav_date))
            
            print(f"  买入 {fund_code} {amount}元 → {shares:.2f}份 (净值{nav:.4f})")
            
        elif trade_type == 'SELL':
            # 卖出处理
            cursor.execute('SELECT shares, base_amount FROM fund_holdings WHERE fund_code = ?', (fund_code,))
            row = cursor.fetchone()
            if row:
                sell_shares = amount if is_shares else amount / nav
                actual_amount = sell_shares * nav
                
                new_shares = row[0] - sell_shares
                new_base = row[1] * (1 - sell_shares / row[0])
                
                if new_shares <= 0.01:  # 清仓
                    cursor.execute('DELETE FROM fund_holdings WHERE fund_code = ?', (fund_code,))
                    print(f"  清仓 {fund_code} 卖出{actual_amount:.2f}元")
                else:
                    cursor.execute('''
                        UPDATE fund_holdings 
                        SET shares = ?, base_amount = ?
                        WHERE fund_code = ?
                    ''', (new_shares, new_base, fund_code))
                    print(f"  卖出 {fund_code} {actual_amount:.2f}元")
        
        # 更新交易状态
        cursor.execute('''
            UPDATE fund_trades SET status = 'CONFIRMED', confirm_date = ? WHERE id = ?
        ''', (confirm_date, trade_id))
    
    conn.commit()

def generate_snapshot(conn, pro):
    """生成每日快照"""
    cursor = conn.cursor()
    
    # 获取所有持仓
    cursor.execute('SELECT fund_code, fund_name, shares, base_amount FROM fund_holdings')
    holdings = cursor.fetchall()
    
    if not holdings:
        print("无持仓")
        return
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    print(f"\n=== 生成 {today} 快照 ===")
    
    for fund_code, fund_name, shares, base_amount in holdings:
        # 获取最新净值
        nav, nav_date = get_fund_nav(pro, fund_code)
        if not nav:
            continue
        
        # 更新净值历史
        update_nav_history(conn, fund_code, nav_date, nav)
        
        # 计算资产和盈亏
        asset_value = shares * nav
        profit = asset_value - base_amount
        
        # 计算当日涨跌 (需要前一日净值)
        cursor.execute('''
            SELECT nav FROM fund_nav_history 
            WHERE fund_code = ? AND nav_date < ?
            ORDER BY nav_date DESC LIMIT 1
        ''', (fund_code, nav_date))
        prev_nav_row = cursor.fetchone()
        prev_nav = prev_nav_row[0] if prev_nav_row else nav
        
        daily_profit = shares * (nav - prev_nav)
        
        # 插入快照
        cursor.execute('''
            INSERT OR REPLACE INTO daily_fund_snapshot 
            (date, fund_code, fund_name, shares, base_amount, asset_value, profit, nav, daily_profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (today, fund_code, fund_name, shares, base_amount, asset_value, profit, nav, daily_profit))
        
        print(f"  {fund_code}: 净值{nav:.4f} 资产{asset_value:.2f} 盈亏{profit:+.2f} 当日{daily_profit:+.2f}")
    
    conn.commit()

def main():
    print(f"=== 基金每日更新 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    
    # 初始化数据库
    if not os.path.exists(DB_PATH):
        print("数据库不存在，请先运行 init_db.py")
        return
    
    conn = sqlite3.connect(DB_PATH)
    pro = ts.pro_api(TS_TOKEN)
    
    try:
        # 1. 确认交易
        confirm_pending_trades(conn, pro)
        
        # 2. 生成快照
        generate_snapshot(conn, pro)
        
    finally:
        conn.close()

if __name__ == '__main__':
    main()