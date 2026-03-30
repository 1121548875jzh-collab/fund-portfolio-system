#!/usr/bin/env python3
"""
基金数据库 HTTP API

提供实时查询接口
"""
from flask import Flask, jsonify, request
import sqlite3
import os

app = Flask(__name__)

FUND_DB = '/root/.openclaw/workspace-coder/skills/fund-portfolio/fund_portfolio.db'
GRID_DB = '/root/.openclaw/workspace-coder/skills/gridseed-v3/data/gridseed.db'

@app.route('/holdings', methods=['GET'])
def get_holdings():
    """获取当前持仓"""
    conn = sqlite3.connect(FUND_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT fund_code, fund_name, shares, base_amount, nav, nav_date
        FROM fund_holdings ORDER BY fund_code
    ''')
    
    rows = cursor.fetchall()
    result = [dict(row) for row in rows]
    conn.close()
    
    return jsonify({
        'success': True,
        'data': result,
        'count': len(result)
    })

@app.route('/nav_history/<fund_code>', methods=['GET'])
def get_nav_history(fund_code):
    """获取净值历史"""
    days = request.args.get('days', 30, type=int)
    
    conn = sqlite3.connect(FUND_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT nav_date, nav FROM fund_nav_history
        WHERE fund_code = ?
        ORDER BY nav_date DESC LIMIT ?
    ''', (fund_code, days))
    
    rows = cursor.fetchall()
    result = [dict(row) for row in rows]
    conn.close()
    
    return jsonify({
        'success': True,
        'fund_code': fund_code,
        'data': result
    })

@app.route('/trades', methods=['GET'])
def get_trades():
    """获取最近交易"""
    days = request.args.get('days', 7, type=int)
    
    conn = sqlite3.connect(FUND_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT trade_date, fund_code, trade_type, amount, status, confirm_date
        FROM fund_trades
        WHERE trade_date >= date('now', ?)
        ORDER BY trade_date DESC
    ''', (f'-{days} days',))
    
    rows = cursor.fetchall()
    result = [dict(row) for row in rows]
    conn.close()
    
    return jsonify({
        'success': True,
        'data': result
    })

@app.route('/gridseed/positions', methods=['GET'])
def get_gridseed_positions():
    """获取GridSeed策略持仓"""
    conn = sqlite3.connect(GRID_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT fund_code, fund_name, phase, step, last_nav, last_date, last_action,
               total_cost, total_shares, grid_base_nav
        FROM strategy_positions ORDER BY fund_code
    ''')
    
    rows = cursor.fetchall()
    result = [dict(row) for row in rows]
    conn.close()
    
    return jsonify({
        'success': True,
        'data': result
    })

@app.route('/snapshot', methods=['GET'])
def get_snapshot():
    """获取最新快照"""
    conn = sqlite3.connect(FUND_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取最新日期
    cursor.execute('SELECT MAX(date) FROM daily_fund_snapshot')
    latest_date = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT date, fund_code, fund_name, shares, base_amount, asset_value, profit, nav, daily_profit
        FROM daily_fund_snapshot
        WHERE date = ?
        ORDER BY fund_code
    ''', (latest_date,))
    
    rows = cursor.fetchall()
    result = [dict(row) for row in rows]
    conn.close()
    
    return jsonify({
        'success': True,
        'date': latest_date,
        'data': result
    })

@app.route('/summary', methods=['GET'])
def get_summary():
    """获取汇总数据"""
    conn = sqlite3.connect(FUND_DB)
    cursor = conn.cursor()
    
    # 持仓汇总
    cursor.execute('''
        SELECT ROUND(SUM(base_amount), 2) as total_base,
               ROUND(SUM(shares * nav), 2) as total_asset,
               ROUND(SUM(shares * nav - base_amount), 2) as total_profit
        FROM fund_holdings
    ''')
    base, asset, profit = cursor.fetchone()
    
    # 最新快照日期的当日涨跌
    cursor.execute('SELECT MAX(date) FROM daily_fund_snapshot')
    latest_date = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT ROUND(SUM(daily_profit), 2)
        FROM daily_fund_snapshot WHERE date = ?
    ''', (latest_date,))
    daily = cursor.fetchone()[0] or 0
    
    conn.close()
    
    profit_pct = profit / base * 100 if base else 0
    
    return jsonify({
        'success': True,
        'data': {
            'total_base': base,
            'total_asset': asset,
            'total_profit': profit,
            'profit_pct': round(profit_pct, 2),
            'daily_profit': daily,
            'latest_date': latest_date
        }
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)