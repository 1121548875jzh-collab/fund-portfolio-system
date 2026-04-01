#!/usr/bin/env python3
"""
GridSeed V3.0 - 策略核心

规则: 从数据库读取策略参数
- strategy_params表：阈值、比例等参数
"""
import sqlite3
import tushare as ts
from datetime import datetime, timedelta
import os
import requests

TS_TOKEN = '7b81c3a430995f2912509eea6e5932513760cf170626110a440c497c'
FUND_DB = '/root/.openclaw/workspace-coder/skills/fund-portfolio/fund_portfolio.db'
GRID_DB = '/root/.openclaw/workspace-coder/skills/gridseed-v3/data/gridseed.db'

# 缓存交易日历
_trade_calendars = {}
_strategy_params = None

def get_strategy_params():
    """从数据库读取策略参数"""
    global _strategy_params
    if _strategy_params is not None:
        return _strategy_params
    
    conn = sqlite3.connect(GRID_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT param_name, param_value FROM strategy_params")
    params = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    
    _strategy_params = params
    return params

def get_param(name, default=None):
    """获取单个参数"""
    params = get_strategy_params()
    return params.get(name, default)

def get_qdii_funds():
    """从数据库获取QDII基金列表"""
    conn = sqlite3.connect(FUND_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT fund_code FROM dca_config WHERE is_qdii = 1")
    return [row[0] for row in cursor.fetchall()]

def get_trade_calendar(pro, year):
    """获取某年的交易日历"""
    if year in _trade_calendars:
        return _trade_calendars[year]
    
    try:
        df = pro.trade_cal(exchange='SSE', start_date=f'{year}0101', end_date=f'{year}1231')
        trade_dates = set(df[df['is_open'] == 1]['cal_date'].tolist())
        _trade_calendars[year] = trade_dates
        return trade_dates
    except:
        return set()

def count_trade_days(pro, start_date, end_date):
    """计算两个日期之间的交易日数"""
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    years = set([start_dt.year, end_dt.year])
    all_trade_dates = set()
    
    for year in years:
        all_trade_dates.update(get_trade_calendar(pro, year))
    
    count = 0
    current = start_dt
    while current <= end_dt:
        if current.strftime('%Y%m%d') in all_trade_dates:
            count += 1
        current += timedelta(days=1)
    
    return count

def get_nav(pro, fund_code, trade_date=None):
    """获取净值，返回 (nav, nav_date)；若指定 trade_date 则只返回 nav"""
    try:
        df = pro.fund_nav(ts_code=f'{fund_code}.OF')
        if df.empty:
            return (None, None) if not trade_date else None
        
        if trade_date:
            trade_date_fmt = trade_date.replace('-', '')
            for _, row in df.iterrows():
                if row['nav_date'] == trade_date_fmt:
                    return float(row['unit_nav'])
            return None
        
        return float(df.iloc[0]['unit_nav']), str(df.iloc[0]['nav_date'])
    except:
        return (None, None) if not trade_date else None

def calc_drawdown(current_nav, base_nav):
    """计算跌幅"""
    if not base_nav or base_nav == 0:
        return 0
    return (current_nav - base_nav) / base_nav

def get_phase(grid_base_nav):
    """判断阶段"""
    return 'GRID' if grid_base_nav else 'ACCUMULATION'

def send_telegram(message):
    """发送 Telegram 消息"""
    try:
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        
        if not token or not chat_id:
            config_path = '/root/.openclaw/workspace-coder/telegram_config.txt'
            if os.path.exists(config_path):
                with open(config_path) as f:
                    for line in f:
                        if '=' in line:
                            key, value = line.strip().split('=', 1)
                            if key == 'token':
                                token = value
                            elif key == 'chat_id':
                                chat_id = value
        
        if not token or not chat_id:
            print(f"[Telegram] 未配置，消息: {message[:50]}...")
            return False
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
        resp = requests.post(url, data=data, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[Telegram] 发送异常: {e}")
        return False

def check_actions():
    """检查所有基金的策略动作"""
    if not os.path.exists(GRID_DB):
        print("GridSeed 数据库不存在")
        return []
    
    params = get_strategy_params()
    pro = ts.pro_api(TS_TOKEN)
    conn = sqlite3.connect(GRID_DB)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT fund_code, fund_name, step, last_nav, last_date, total_cost, total_shares, grid_base_nav
        FROM strategy_positions
    ''')
    positions = cursor.fetchall()
    
    actions = []
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 从数据库读取阈值
    l1_l4_threshold = params.get('l1_l4_threshold', -0.03)
    l5_l6_threshold = params.get('l5_l6_threshold', -0.05)
    l1_l4_ratio = params.get('l1_l4_ratio', 0.15)
    l5_l6_ratio = params.get('l5_l6_ratio', 0.30)
    grid_buy_threshold = params.get('grid_buy_threshold', -0.03)
    grid_sell_threshold = params.get('grid_sell_threshold', 0.10)
    accum_sell_threshold = params.get('accum_sell_threshold', 0.15)
    idle_trade_days = int(params.get('idle_trade_days', 10))
    grid_buy_amount = params.get('grid_buy_amount', 100)
    
    for fund_code, fund_name, step, last_nav, last_date, total_cost, total_shares, grid_base_nav in positions:
        current_nav, nav_date = get_nav(pro, fund_code)
        if not current_nav:
            continue
        
        drawdown = calc_drawdown(current_nav, last_nav)
        phase = get_phase(grid_base_nav)
        
        if total_shares and total_shares > 0 and total_cost and total_cost > 0:
            current_value = total_shares * current_nav
            profit_ratio = (current_value - total_cost) / total_cost
        else:
            profit_ratio = 0
        
        if phase == 'ACCUMULATION':
            # 建仓期卖出
            if profit_ratio >= accum_sell_threshold:
                sell_shares = total_shares * 0.5
                sell_amount = sell_shares * current_nav
                actions.append({
                    'fund_code': fund_code, 'fund_name': fund_name,
                    'action': '建仓期卖出', 'amount': sell_amount,
                    'shares': sell_shares, 'profit_ratio': profit_ratio,
                    'step': step, 'phase': 'ACCUMULATION', 'trigger': '收益达15%'
                })
            
            # 加仓
            elif step < 4 and drawdown <= l1_l4_threshold:
                add_amount = total_shares * current_nav * l1_l4_ratio
                actions.append({
                    'fund_code': fund_code, 'fund_name': fund_name,
                    'action': f'L{step+1}加仓', 'amount': add_amount,
                    'drawdown': drawdown, 'step': step, 'phase': 'ACCUMULATION'
                })
            elif step >= 4 and step < 6 and drawdown <= l5_l6_threshold:
                add_amount = total_shares * current_nav * l5_l6_ratio
                actions.append({
                    'fund_code': fund_code, 'fund_name': fund_name,
                    'action': f'L{step+1}加仓', 'amount': add_amount,
                    'drawdown': drawdown, 'step': step, 'phase': 'ACCUMULATION'
                })
        else:
            # 网格阶段
            if drawdown <= grid_buy_threshold:
                actions.append({
                    'fund_code': fund_code, 'fund_name': fund_name,
                    'action': '网格买入', 'amount': grid_buy_amount,
                    'drawdown': drawdown, 'step': step, 'phase': 'GRID'
                })
            
            # 网格卖出
            cursor.execute('''
                SELECT id, amount, shares, nav FROM grid_batches 
                WHERE fund_code = ? AND status = 'HELD' ORDER BY buy_date
            ''', (fund_code,))
            batches = cursor.fetchall()
            
            for batch_id, batch_amount, batch_shares, batch_nav in batches:
                batch_profit = (current_nav - batch_nav) / batch_nav
                if batch_profit >= grid_sell_threshold:
                    actions.append({
                        'fund_code': fund_code, 'fund_name': fund_name,
                        'action': '网格卖出', 'amount': batch_shares * current_nav,
                        'shares': batch_shares, 'batch_id': batch_id,
                        'profit_ratio': batch_profit, 'step': step, 'phase': 'GRID'
                    })
                    break
        
        # 闲置唤醒
        if last_date:
            idle_days = count_trade_days(pro, last_date, today)
            if idle_days >= idle_trade_days:
                idle_amount = params.get('idle_wake_amount', 100)
                actions.append({
                    'fund_code': fund_code, 'fund_name': fund_name,
                    'action': '闲置唤醒', 'amount': idle_amount,
                    'drawdown': drawdown, 'step': step, 'phase': phase,
                    'idle_days': idle_days
                })
    
    conn.close()
    return actions

def run_check(send_msg=True):
    """运行检查并输出结果"""
    print(f"=== GridSeed V3.0 检查 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")
    
    actions = check_actions()
    
    if not actions:
        print("无操作建议")
        # 即使无操作也发送提醒
        if send_msg:
            msg = f"<b>GridSeed V3.0 检查</b>\n<code>\n✅ 无操作建议\n\n所有基金涨跌幅正常\n闲置提醒: 无\n</code>"
            send_telegram(msg)
        return []
    
    print(f"触发操作: {len(actions)} 只\n")
    
    msg_lines = ["<b>GridSeed V3.0 操作建议</b>", "<pre>"]
    
    for a in actions:
        if '卖出' in a['action']:
            profit_pct = a.get('profit_ratio', 0) * 100
            print(f"🔴 {a['fund_code']} {a['fund_name']}: {a['action']} {a['amount']:.0f}元 (收益{profit_pct:.1f}%)")
            msg_lines.append(f"🔴 {a['fund_code']} {a['action']} {a['amount']:.0f}元 (+{profit_pct:.1f}%)")
        elif '闲置唤醒' in a['action']:
            idle_days = a.get('idle_days', 0)
            drawdown_pct = abs(a.get('drawdown', 0)) * 100
            print(f"💤 {a['fund_code']} {a['fund_name']}: {a['action']} {a['amount']:.0f}元 (闲置{idle_days}交易日)")
            msg_lines.append(f"💤 {a['fund_code']} {a['action']} {a['amount']:.0f}元 ({idle_days}天)")
        else:
            drawdown_pct = abs(a.get('drawdown', 0)) * 100
            print(f"🟢 {a['fund_code']} {a['fund_name']}: {a['action']} {a['amount']:.0f}元 (跌{drawdown_pct:.1f}%)")
            msg_lines.append(f"🟢 {a['fund_code']} {a['action']} {a['amount']:.0f}元 (-{drawdown_pct:.1f}%)")
    
    msg_lines.append("</pre>")
    
    buy_actions = [a for a in actions if '买入' in a['action'] or '加仓' in a['action'] or '唤醒' in a['action']]
    sell_actions = [a for a in actions if '卖出' in a['action']]
    msg_lines.append(f"\n买入: {len(buy_actions)} | 卖出: {len(sell_actions)}")
    
    if send_msg:
        send_telegram('\n'.join(msg_lines))
    
    return actions

def record_operation(fund_code, trade_type, amount, trade_date=None, shares=None, nav=None):
    """记录手动操作"""
    if trade_date is None:
        trade_date = datetime.now().strftime('%Y-%m-%d')
    
    if not os.path.exists(GRID_DB):
        return False, "GridSeed 数据库不存在"
    
    pro = ts.pro_api(TS_TOKEN)
    conn = sqlite3.connect(GRID_DB)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT fund_name, step, total_cost, total_shares, grid_base_nav FROM strategy_positions WHERE fund_code = ?",
        (fund_code,)
    )
    pos = cursor.fetchone()
    
    if not pos:
        conn.close()
        return False, f"基金 {fund_code} 不在监控列表中"
    
    fund_name, step, total_cost, total_shares, grid_base_nav = pos
    phase = get_phase(grid_base_nav)
    
    if not nav:
        nav = get_nav(pro, fund_code, trade_date)
        if not nav:
            nav = get_nav(pro, fund_code)
    
    if not shares and nav:
        shares = amount / nav
    
    if trade_type == 'BUY':
        if phase == 'ACCUMULATION':
            trigger_reason = f'L{step+1}加仓'
            new_step = step + 1
        else:
            trigger_reason = '网格买入'
            new_step = step
    else:
        if phase == 'ACCUMULATION':
            trigger_reason = '建仓期卖出'
            cursor.execute("UPDATE strategy_positions SET grid_base_nav = ? WHERE fund_code = ?", (nav, fund_code))
        else:
            trigger_reason = '网格卖出'
        new_step = step
    
    cursor.execute(
        "UPDATE strategy_positions SET last_date = ?, last_action = ?, last_amount = ?, step = ?, updated_at = ? WHERE fund_code = ?",
        (trade_date, trigger_reason, amount, new_step, datetime.now().strftime('%Y-%m-%d %H:%M'), fund_code)
    )
    
    status = 'CONFIRMED' if nav else 'PENDING_NAV'
    cursor.execute(
        "INSERT INTO strategy_trades (fund_code, trade_date, trade_type, amount, shares, nav, trigger_reason, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (fund_code, trade_date, trade_type, amount, shares, nav, trigger_reason, status)
    )
    
    conn.commit()
    conn.close()
    
    return True, f"{fund_code} {fund_name}: {trigger_reason} {amount}元，监督点更新至 {trade_date}"

def update_pending_navs():
    """更新待补充净值的交易记录"""
    if not os.path.exists(GRID_DB):
        return 0, []
    
    pro = ts.pro_api(TS_TOKEN)
    conn = sqlite3.connect(GRID_DB)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id, fund_code, trade_date, trade_type, amount, trigger_reason FROM strategy_trades WHERE status = 'PENDING_NAV'"
    )
    pending = cursor.fetchall()
    
    if not pending:
        conn.close()
        return 0, []
    
    updated = 0
    failed = []
    
    for trade_id, fund_code, trade_date, trade_type, amount, trigger_reason in pending:
        nav = get_nav(pro, fund_code, trade_date)
        
        if not nav:
            failed.append({'fund_code': fund_code, 'trade_date': trade_date, 'reason': '净值未出'})
            continue
        
        shares = amount / nav
        
        cursor.execute("UPDATE strategy_trades SET nav = ?, shares = ?, status = 'CONFIRMED' WHERE id = ?", (nav, shares, trade_id))
        cursor.execute("UPDATE strategy_positions SET last_nav = ? WHERE fund_code = ?", (nav, fund_code))
        
        # 如果是进入网格模式，更新grid_base_nav
        if trigger_reason in ['进入网格', '赎回'] or '建仓期卖出' in trigger_reason:
            cursor.execute("UPDATE strategy_positions SET grid_base_nav = ?, phase = 'GRID' WHERE fund_code = ?", (nav, fund_code))
        
        updated += 1
    
    conn.commit()
    conn.close()
    
    return updated, failed

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'check':
            run_check()
        elif cmd == 'check_silent':
            run_check(send_msg=False)
        elif cmd == 'update_navs':
            updated, failed = update_pending_navs()
            print(f"更新净值: {updated} 笔")
            if failed:
                print(f"待处理: {len(failed)} 笔")
        elif cmd == 'record' and len(sys.argv) >= 5:
            fund_code = sys.argv[2]
            trade_type = sys.argv[3]
            amount = float(sys.argv[4])
            success, msg = record_operation(fund_code, trade_type, amount)
            print(msg)
        else:
            print("用法: python strategy.py [check|check_silent|update_navs|record <code> <BUY|SELL> <amount>]")
    else:
        run_check()