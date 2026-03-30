#!/usr/bin/env python3
"""
GridSeed V3.0 - 策略核心

规则:
- 建仓阶段 (grid_base_nav=NULL):
  - L1-L4 (step 0-3): 跌3% → 加仓15%
  - L5-L6 (step 4-5): 跌5% → 加仓30%
  - 收益达15% → 卖出50%持仓，进入网格阶段

- 网格阶段 (grid_base_nav 有值):
  - 跌3% → 买入 100元
  - 每批次收益达10% → 卖出该批次份额

- 闲置唤醒:
  - 10个交易日无操作 → 提醒加仓 100元
  - 不增加 step
"""
import sqlite3
import tushare as ts
from datetime import datetime, timedelta
import os
import requests

TS_TOKEN = '7b81c3a430995f2912509eea6e5932513760cf170626110a440c497c'
FUND_DB = '/root/.openclaw/workspace-coder/skills/fund-portfolio/fund_portfolio.db'
GRID_DB = '/root/.openclaw/workspace-coder/skills/gridseed-v3/data/gridseed.db'

QDII_FUNDS = ['012062', '017641', '017437', '017091']

# 加仓比例
L1_L4_RATIO = 0.15  # 15%
L5_L6_RATIO = 0.30  # 30%

# 触发阈值
L1_L4_THRESHOLD = -0.03  # -3%
L5_L6_THRESHOLD = -0.05  # -5%
GRID_BUY_THRESHOLD = -0.03   # 网格买入 -3%
GRID_SELL_THRESHOLD = 0.10   # 网格卖出 +10%
ACCUM_SELL_THRESHOLD = 0.15  # 建仓期卖出 +15%
IDLE_TRADE_DAYS = 10         # 闲置交易日数

# 缓存交易日历
_trade_calendars = {}

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
            # 查找指定日期的净值
            trade_date_fmt = trade_date.replace('-', '')
            for _, row in df.iterrows():
                if row['nav_date'] == trade_date_fmt:
                    return float(row['unit_nav'])
            return None  # 指定日期净值未出
        
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
        # 从环境变量或配置文件获取 token 和 chat_id
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        
        if not token or not chat_id:
            # 尝试从配置文件读取
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
        data = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        resp = requests.post(url, data=data, timeout=10)
        if resp.status_code == 200:
            print(f"[Telegram] 发送成功")
            return True
        else:
            print(f"[Telegram] 发送失败: {resp.text}")
            return False
    except Exception as e:
        print(f"[Telegram] 发送异常: {e}")
        return False

def check_actions():
    """检查所有基金的策略动作"""
    if not os.path.exists(GRID_DB):
        print("GridSeed 数据库不存在")
        return []
    
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
    
    for fund_code, fund_name, step, last_nav, last_date, total_cost, total_shares, grid_base_nav in positions:
        # 获取当前净值
        current_nav, nav_date = get_nav(pro, fund_code)
        if not current_nav:
            continue
        
        # 计算跌幅和收益
        drawdown = calc_drawdown(current_nav, last_nav)
        phase = get_phase(grid_base_nav)
        
        # 计算当前市值和收益率
        if total_shares and total_shares > 0 and total_cost and total_cost > 0:
            current_value = total_shares * current_nav
            profit_ratio = (current_value - total_cost) / total_cost
        else:
            profit_ratio = 0
        
        if phase == 'ACCUMULATION':
            # === 建仓阶段 ===
            
            # 检查卖出条件：收益达15%
            if profit_ratio >= ACCUM_SELL_THRESHOLD:
                sell_shares = total_shares * 0.5  # 卖出50%
                sell_amount = sell_shares * current_nav
                actions.append({
                    'fund_code': fund_code,
                    'fund_name': fund_name,
                    'action': '建仓期卖出',
                    'amount': sell_amount,
                    'shares': sell_shares,
                    'profit_ratio': profit_ratio,
                    'step': step,
                    'phase': 'ACCUMULATION',
                    'trigger': '收益达15%'
                })
            
            # 检查加仓条件
            elif step < 4 and drawdown <= L1_L4_THRESHOLD:
                # L1-L4
                add_amount = total_shares * current_nav * L1_L4_RATIO
                actions.append({
                    'fund_code': fund_code,
                    'fund_name': fund_name,
                    'action': f'L{step+1}加仓',
                    'amount': add_amount,
                    'drawdown': drawdown,
                    'step': step,
                    'phase': 'ACCUMULATION'
                })
            elif step >= 4 and step < 6 and drawdown <= L5_L6_THRESHOLD:
                # L5-L6
                add_amount = total_shares * current_nav * L5_L6_RATIO
                actions.append({
                    'fund_code': fund_code,
                    'fund_name': fund_name,
                    'action': f'L{step+1}加仓',
                    'amount': add_amount,
                    'drawdown': drawdown,
                    'step': step,
                    'phase': 'ACCUMULATION'
                })
        else:
            # === 网格阶段 ===
            
            # 检查买入条件：跌3%
            if drawdown <= GRID_BUY_THRESHOLD:
                actions.append({
                    'fund_code': fund_code,
                    'fund_name': fund_name,
                    'action': '网格买入',
                    'amount': 100,
                    'drawdown': drawdown,
                    'step': step,
                    'phase': 'GRID'
                })
            
            # 检查卖出条件：查网格买入批次
            cursor.execute('''
                SELECT id, amount, shares, nav FROM grid_batches 
                WHERE fund_code = ? AND status = 'HELD'
                ORDER BY buy_date
            ''', (fund_code,))
            batches = cursor.fetchall()
            
            for batch_id, batch_amount, batch_shares, batch_nav in batches:
                # 该批次收益率
                batch_profit = (current_nav - batch_nav) / batch_nav
                if batch_profit >= GRID_SELL_THRESHOLD:
                    actions.append({
                        'fund_code': fund_code,
                        'fund_name': fund_name,
                        'action': '网格卖出',
                        'amount': batch_shares * current_nav,
                        'shares': batch_shares,
                        'batch_id': batch_id,
                        'profit_ratio': batch_profit,
                        'step': step,
                        'phase': 'GRID'
                    })
                    break  # 每次只建议卖出一批
        
        # 检查闲置（10个交易日）
        if last_date:
            idle_trade_days = count_trade_days(pro, last_date, today)
            if idle_trade_days >= IDLE_TRADE_DAYS:
                actions.append({
                    'fund_code': fund_code,
                    'fund_name': fund_name,
                    'action': '闲置唤醒',
                    'amount': 100,
                    'drawdown': drawdown,
                    'step': step,
                    'phase': phase,
                    'idle_days': idle_trade_days
                })
    
    conn.close()
    return actions

def run_check(send_msg=True):
    """运行检查并输出结果"""
    print(f"=== GridSeed V3.0 检查 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")
    
    actions = check_actions()
    
    if not actions:
        print("无操作建议")
        return []
    
    print(f"触发操作: {len(actions)} 只\n")
    
    # 分类统计
    buy_actions = [a for a in actions if '买入' in a['action'] or '加仓' in a['action'] or '唤醒' in a['action']]
    sell_actions = [a for a in actions if '卖出' in a['action']]
    
    # 构建消息
    msg_lines = [f"<b>GridSeed V3.0 操作建议</b>", f"<pre>"]
    
    for a in actions:
        if '卖出' in a['action']:
            profit_pct = a.get('profit_ratio', 0) * 100
            print(f"🔴 {a['fund_code']} {a['fund_name']}: {a['action']} {a['amount']:.0f}元 (收益{profit_pct:.1f}%)")
            msg_lines.append(f"🔴 {a['fund_code']} {a['action']} {a['amount']:.0f}元 (+{profit_pct:.1f}%)")
        elif '闲置唤醒' in a['action']:
            idle_days = a.get('idle_days', 0)
            drawdown_pct = abs(a.get('drawdown', 0)) * 100
            print(f"💤 {a['fund_code']} {a['fund_name']}: {a['action']} {a['amount']:.0f}元 (闲置{idle_days}交易日, 跌{drawdown_pct:.1f}%)")
            msg_lines.append(f"💤 {a['fund_code']} {a['action']} {a['amount']:.0f}元 ({idle_days}天)")
        else:
            drawdown_pct = abs(a.get('drawdown', 0)) * 100
            print(f"🟢 {a['fund_code']} {a['fund_name']}: {a['action']} {a['amount']:.0f}元 (跌{drawdown_pct:.1f}%)")
            msg_lines.append(f"🟢 {a['fund_code']} {a['action']} {a['amount']:.0f}元 (-{drawdown_pct:.1f}%)")
    
    msg_lines.append("</pre>")
    msg_lines.append(f"\n买入: {len(buy_actions)} | 卖出: {len(sell_actions)}")
    
    # 发送 Telegram
    if send_msg:
        message = '\n'.join(msg_lines)
        send_telegram(message)
    
    return actions

def record_operation(fund_code, trade_type, amount, trade_date=None, shares=None, nav=None):
    """
    记录手动操作，更新监督点
    
    参数:
        fund_code: 基金代码
        trade_type: 'BUY' 或 'SELL'
        amount: 金额
        trade_date: 交易日期（默认今天）
        shares: 份额（卖出时必填）
        nav: 净值（可选，会自动获取）
    
    返回:
        (success, message)
    """
    if trade_date is None:
        trade_date = datetime.now().strftime('%Y-%m-%d')
    
    if not os.path.exists(GRID_DB):
        return False, "GridSeed 数据库不存在"
    
    pro = ts.pro_api(TS_TOKEN)
    conn = sqlite3.connect(GRID_DB)
    cursor = conn.cursor()
    
    # 检查基金是否存在
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
    
    # 获取净值
    if not nav:
        nav = get_nav(pro, fund_code, trade_date)
        if not nav:
            nav = get_nav(pro, fund_code)  # 尝试获取最新净值
    
    # 计算份额
    if not shares and nav:
        shares = amount / nav
    
    # 确定操作类型和状态变化
    if trade_type == 'BUY':
        if phase == 'ACCUMULATION':
            trigger_reason = f'L{step+1}加仓'
            new_step = step + 1
        else:
            trigger_reason = '网格买入'
            new_step = step
    else:
        # 卖出
        if phase == 'ACCUMULATION':
            # 建仓期卖出，进入网格阶段
            trigger_reason = '建仓期卖出'
            # 设置 grid_base_nav 为卖出时净值
            cursor.execute(
                "UPDATE strategy_positions SET grid_base_nav = ? WHERE fund_code = ?",
                (nav, fund_code)
            )
        else:
            trigger_reason = '网格卖出'
        new_step = step
    
    # 更新持仓
    cursor.execute(
        "UPDATE strategy_positions SET last_date = ?, last_action = ?, last_amount = ?, step = ?, updated_at = ? WHERE fund_code = ?",
        (trade_date, trigger_reason, amount, new_step, datetime.now().strftime('%Y-%m-%d %H:%M'), fund_code)
    )
    
    # 记录交易
    status = 'CONFIRMED' if nav else 'PENDING_NAV'
    cursor.execute(
        "INSERT INTO strategy_trades (fund_code, trade_date, trade_type, amount, shares, nav, trigger_reason, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (fund_code, trade_date, trade_type, amount, shares, nav, trigger_reason, status)
    )
    
    conn.commit()
    conn.close()
    
    return True, f"{fund_code} {fund_name}: {trigger_reason} {amount}元，监督点更新至 {trade_date}"

def update_pending_navs():
    """
    更新待补充净值的交易记录
    
    隔日 8:20 后调用，净值出来后补充 last_nav 和交易记录的净值/份额
    """
    if not os.path.exists(GRID_DB):
        return 0, []
    
    pro = ts.pro_api(TS_TOKEN)
    conn = sqlite3.connect(GRID_DB)
    cursor = conn.cursor()
    
    # 获取待补充净值的交易
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
        # 获取交易日净值
        nav = get_nav(pro, fund_code, trade_date)
        
        if not nav:
            failed.append({'fund_code': fund_code, 'trade_date': trade_date, 'reason': '净值未出'})
            continue
        
        shares = amount / nav
        
        # 更新交易记录
        cursor.execute(
            "UPDATE strategy_trades SET nav = ?, shares = ?, status = 'CONFIRMED' WHERE id = ?",
            (nav, shares, trade_id)
        )
        
        # 更新持仓的 last_nav
        cursor.execute(
            "UPDATE strategy_positions SET last_nav = ? WHERE fund_code = ?",
            (nav, fund_code)
        )
        
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
            # python strategy.py record 007882 BUY 100
            fund_code = sys.argv[2]
            trade_type = sys.argv[3]
            amount = float(sys.argv[4])
            success, msg = record_operation(fund_code, trade_type, amount)
            print(msg)
        else:
            print("用法: python strategy.py [check|check_silent|update_navs|record <code> <BUY|SELL> <amount>]")
    else:
        run_check()