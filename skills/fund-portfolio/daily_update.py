#!/usr/bin/env python3
"""
基金持仓管理系统 - 每日更新

功能:
1. 从 Tushare 获取最新净值
2. 确认 PENDING 交易
3. 生成每日快照
4. 发送邮件报告

执行时间: 8:20

计算规则:
- 普通基金: 当日涨跌 = 份额 × (今日净值 - 昨日净值)
- QDII基金: 净值有 T+1 延迟，Tushare 返回的最新净值是 T-1 的
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
    - 买入：份额 = 金额 / 交易日净值（T日买入用T日净值）
    - 卖出：金额 = 份额 × 交易日净值
    - 如果交易日净值还没出来，跳过等待下次确认
    """
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
        
        # ========== 核心：获取交易日净值 ==========
        # 规则：T日买入，用T日净值计算份额
        trade_date_fmt = trade_date.replace('-', '')  # 20260325
        
        # 先从净值历史表获取交易日净值
        nav = get_nav_by_date(conn, fund_code, trade_date_fmt)
        
        if not nav:
            # 历史表中没有，尝试从 Tushare 获取
            nav_tushare, nav_date_tushare = get_fund_nav(pro, fund_code)
            
            if not nav_tushare:
                print(f"  {fund_code}: 无法获取净值")
                continue
            
            # 先保存获取到的净值
            update_nav_history(conn, fund_code, nav_date_tushare, nav_tushare)
            
            # 检查 Tushare 返回的净值日期是否匹配交易日
            if nav_date_tushare != trade_date_fmt:
                # 净值日期不匹配，说明交易日净值还没出来
                print(f"  {fund_code}: 交易日{trade_date}净值未出（Tushare最新:{nav_date_tushare}），等待")
                continue
            
            nav = nav_tushare
        
        print(f"  {fund_code}: 使用交易日{trade_date}净值 {nav:.4f}")
        
        if trade_type == 'BUY':
            shares = amount / nav
            
            cursor.execute('SELECT shares, base_amount FROM fund_holdings WHERE fund_code = ?', (fund_code,))
            row = cursor.fetchone()
            
            if row and row[0]:
                new_shares = row[0] + shares
                new_base = row[1] + amount
                cursor.execute('''
                    UPDATE fund_holdings SET shares = ?, base_amount = ? WHERE fund_code = ?
                ''', (new_shares, new_base, fund_code))
            else:
                cursor.execute('''
                    INSERT INTO fund_holdings (fund_code, shares, base_amount)
                    VALUES (?, ?, ?)
                ''', (fund_code, shares, amount))
            
            print(f"  买入 {fund_code} {amount}元 → {shares:.2f}份 (净值{nav:.4f})")
            
        elif trade_type == 'SELL':
            cursor.execute('SELECT shares, base_amount FROM fund_holdings WHERE fund_code = ?', (fund_code,))
            row = cursor.fetchone()
            if row:
                sell_shares = amount if is_shares else amount / nav
                actual_amount = sell_shares * nav
                
                new_shares = row[0] - sell_shares
                new_base = row[1] * (1 - sell_shares / row[0])
                
                if new_shares <= 0.01:
                    cursor.execute('DELETE FROM fund_holdings WHERE fund_code = ?', (fund_code,))
                    print(f"  清仓 {fund_code} 卖出{actual_amount:.2f}元")
                else:
                    cursor.execute('''
                        UPDATE fund_holdings SET shares = ?, base_amount = ? WHERE fund_code = ?
                    ''', (new_shares, new_base, fund_code))
                    print(f"  卖出 {fund_code} {actual_amount:.2f}元")
        
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
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    print(f"\n=== 生成 {today} 快照 ===")
    
    # 先更新所有基金的净值历史
    for fund_code, fund_name, shares, base_amount in holdings:
        nav, nav_date = get_fund_nav(pro, fund_code)
        if nav and nav_date:
            update_nav_history(conn, fund_code, nav_date, nav)
    
    # 生成快照
    total_daily = 0
    
    for fund_code, fund_name, shares, base_amount in holdings:
        is_qdii = fund_code in QDII_FUNDS
        
        # 获取今日和昨日净值
        today_fmt = today.replace('-', '')
        yesterday_fmt = yesterday.replace('-', '')
        
        # 从净值历史获取
        nav_today = get_nav_by_date(conn, fund_code, today_fmt)
        nav_yesterday = get_nav_by_date(conn, fund_code, yesterday_fmt)
        
        # 如果没有今日净值，用昨日净值（QDII 可能出现这种情况）
        if not nav_today:
            nav_today = nav_yesterday
        
        if not nav_today:
            print(f"  {fund_code}: 无净值数据")
            continue
        
        # 计算资产和盈亏
        asset_value = shares * nav_today
        profit = asset_value - base_amount
        
        # 计算当日涨跌
        if nav_yesterday:
            daily_profit = shares * (nav_today - nav_yesterday)
        else:
            daily_profit = 0
        
        total_daily += daily_profit
        
        # 插入快照
        cursor.execute('''
            INSERT OR REPLACE INTO daily_fund_snapshot 
            (date, fund_code, fund_name, shares, base_amount, asset_value, profit, nav, daily_profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (today, fund_code, fund_name, shares, base_amount, asset_value, profit, nav_today, daily_profit))
        
        print(f"  {fund_code}: 净值{nav_today:.4f} 资产{asset_value:.2f} 盈亏{profit:+.2f} 当日{daily_profit:+.2f}")
    
    conn.commit()
    print(f"\n当日涨跌合计: {total_daily:+.2f}")

def main():
    print(f"=== 基金每日更新 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    
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