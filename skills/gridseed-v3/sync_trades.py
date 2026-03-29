#!/usr/bin/env python3
"""
GridSeed V3.0 - 交易同步

从基金系统同步已确认的交易到 GridSeed

执行时间: 8:26
"""
import sqlite3
import tushare as ts
from datetime import datetime
import os

TS_TOKEN = '7b81c3a430995f2912509eea6e5932513760cf170626110a440c497c'
FUND_DB = '/root/.openclaw/workspace-coder/skills/fund-portfolio/fund_portfolio.db'
GRID_DB = '/root/.openclaw/workspace-coder/skills/gridseed-v3/data/gridseed.db'

QDII_FUNDS = ['012062', '017641', '017437', '017091']

def get_nav(pro, fund_code, trade_date):
    """获取交易日净值"""
    try:
        df = pro.fund_nav(ts_code=f'{fund_code}.OF')
        if df.empty:
            return None
        
        trade_date_fmt = trade_date.replace('-', '')
        for _, row in df.iterrows():
            if row['nav_date'] == trade_date_fmt:
                return float(row['unit_nav'])
        
        return float(df.iloc[0]['unit_nav'])
    except:
        return None

def is_grid_phase(grid_base_nav):
    return grid_base_nav is not None

def sync_trades():
    """同步交易"""
    print(f"=== GridSeed 同步 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")
    
    if not os.path.exists(FUND_DB) or not os.path.exists(GRID_DB):
        print("数据库不存在")
        return 0, []
    
    fund_conn = sqlite3.connect(FUND_DB)
    grid_conn = sqlite3.connect(GRID_DB)
    pro = ts.pro_api(TS_TOKEN)
    
    fund_cursor = fund_conn.cursor()
    grid_cursor = grid_conn.cursor()
    
    # 获取 GridSeed 监控的基金
    grid_cursor.execute("SELECT fund_code FROM strategy_positions")
    tracking = [row[0] for row in grid_cursor.fetchall()]
    
    if not tracking:
        print("无监控基金")
        fund_conn.close()
        grid_conn.close()
        return 0, []
    
    print(f"同步 {len(tracking)} 只基金\n")
    
    synced = 0
    failed = []
    
    for fund_code in tracking:
        # 获取 GridSeed 最后确认日期
        grid_cursor.execute(
            "SELECT MAX(trade_date) FROM strategy_trades WHERE fund_code = ? AND status = 'CONFIRMED'",
            (fund_code,)
        )
        last_sync = grid_cursor.fetchone()[0]
        
        # 获取基金系统新确认的交易
        if last_sync:
            fund_cursor.execute(
                "SELECT trade_date, trade_type, amount, confirm_date FROM fund_trades WHERE fund_code = ? AND status = 'CONFIRMED' AND trade_date > ? ORDER BY trade_date",
                (fund_code, last_sync)
            )
        else:
            fund_cursor.execute(
                "SELECT trade_date, trade_type, amount, confirm_date FROM fund_trades WHERE fund_code = ? AND status = 'CONFIRMED' ORDER BY trade_date",
                (fund_code,)
            )
        
        trades = fund_cursor.fetchall()
        
        for trade_date, trade_type, amount, confirm_date in trades:
            nav = get_nav(pro, fund_code, trade_date)
            if not nav:
                failed.append({'fund_code': fund_code, 'trade_date': trade_date, 'reason': '无法获取净值'})
                continue
            
            shares = amount / nav
            
            # 获取当前持仓
            grid_cursor.execute(
                "SELECT total_cost, total_shares, step, grid_base_nav FROM strategy_positions WHERE fund_code = ?",
                (fund_code,)
            )
            pos = grid_cursor.fetchone()
            
            if not pos:
                failed.append({'fund_code': fund_code, 'trade_date': trade_date, 'reason': '找不到持仓记录'})
                continue
            
            old_cost, old_shares, step, grid_base_nav = pos
            is_grid = is_grid_phase(grid_base_nav)
            
            if trade_type == 'BUY':
                new_cost = old_cost + amount
                new_shares = old_shares + shares
                
                # 判断动作类型
                trigger_reason = f'L{step+1}加仓'
                new_step = step + 1
                
                # 更新持仓
                grid_cursor.execute(
                    "UPDATE strategy_positions SET total_cost = ?, total_shares = ?, last_nav = ?, last_date = ?, last_action = ?, last_amount = ?, step = ?, updated_at = ? WHERE fund_code = ?",
                    (new_cost, new_shares, nav, trade_date, trigger_reason, amount, new_step, datetime.now().strftime('%Y-%m-%d %H:%M'), fund_code)
                )
                
                grid_cursor.execute(
                    "INSERT INTO strategy_trades (fund_code, trade_date, trade_type, amount, nav, shares, trigger_reason, status) VALUES (?, ?, 'BUY', ?, ?, ?, ?, 'CONFIRMED')",
                    (fund_code, trade_date, amount, nav, shares, trigger_reason)
                )
                
                print(f"  {fund_code}: {trigger_reason} {amount}元")
                synced += 1
            
            elif trade_type == 'SELL':
                new_cost = old_cost * (1 - shares / old_shares)
                new_shares = old_shares - shares
                
                grid_cursor.execute(
                    "UPDATE strategy_positions SET total_cost = ?, total_shares = ?, last_nav = ?, last_date = ?, last_action = ?, last_amount = ?, updated_at = ? WHERE fund_code = ?",
                    (new_cost, new_shares, nav, trade_date, 'SELL', amount, datetime.now().strftime('%Y-%m-%d %H:%M'), fund_code)
                )
                
                grid_cursor.execute(
                    "INSERT INTO strategy_trades (fund_code, trade_date, trade_type, amount, nav, shares, trigger_reason, status) VALUES (?, ?, 'SELL', ?, ?, ?, '卖出', 'CONFIRMED')",
                    (fund_code, trade_date, amount, nav, shares)
                )
                
                print(f"  {fund_code}: 卖出 {amount}元")
                synced += 1
    
    grid_conn.commit()
    fund_conn.close()
    grid_conn.close()
    
    print(f"\n✅ 同步成功: {synced} 笔")
    if failed:
        print(f"❌ 同步失败: {len(failed)} 笔")
        for f in failed:
            print(f"  {f['fund_code']} {f['trade_date']}: {f['reason']}")
    
    return synced, failed

if __name__ == '__main__':
    sync_trades()