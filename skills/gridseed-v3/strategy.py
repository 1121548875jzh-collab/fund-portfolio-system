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
import sys
import requests
import math

# 添加父目录到路径，支持导入config
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import TS_TOKEN, FUND_DB, GRID_DB, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

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

def get_nav_df(pro, fund_code):
    """获取基金净值序列，按 Tushare 默认顺序返回。"""
    try:
        df = pro.fund_nav(ts_code=f'{fund_code}.OF')
        return df if not df.empty else None
    except:
        return None


def get_nav(pro, fund_code, trade_date=None):
    """获取净值，返回 (nav, nav_date)；若指定 trade_date 则只返回 nav"""
    df = get_nav_df(pro, fund_code)
    if df is None:
        return (None, None) if not trade_date else None

    if trade_date:
        trade_date_fmt = trade_date.replace('-', '')
        for _, row in df.iterrows():
            if row['nav_date'] == trade_date_fmt:
                return float(row['unit_nav'])
        return None

    return float(df.iloc[0]['unit_nav']), str(df.iloc[0]['nav_date'])

def calc_drawdown(current_nav, base_nav):
    """计算跌幅"""
    if not base_nav or base_nav == 0:
        return 0
    return (current_nav - base_nav) / base_nav

def get_phase(grid_base_nav, phase_col=None):
    """判断阶段，优先使用数据库 phase，没值则回退到根据 grid_base_nav 判断"""
    if phase_col:
        return phase_col
    return 'GRID' if grid_base_nav else 'ACCUMULATION'


def classify_strategy_action(strategy_action=None, trigger_reason=None, action_text=None):
    """优先使用结构化动作字段，兼容旧文本判断。"""
    if strategy_action:
        return strategy_action

    text = action_text or trigger_reason or ''
    if text == '进入网格':
        return 'ENTER_GRID'
    if '闲置唤醒' in text:
        return 'IDLE_WAKE'
    if '网格买入' in text:
        return 'GRID_BUY'
    if '网格卖出' in text:
        return 'GRID_SELL'
    if '建仓期卖出' in text or text == '赎回':
        return 'ACCUM_SELL'
    if '加仓' in text or '买入' in text:
        return 'ACCUM_BUY'
    return 'NONE'


def is_sell_action(strategy_action=None, trigger_reason=None, action_text=None):
    action = classify_strategy_action(strategy_action, trigger_reason, action_text)
    return action in ('ACCUM_SELL', 'GRID_SELL')


def is_buy_like_action(strategy_action=None, trigger_reason=None, action_text=None):
    action = classify_strategy_action(strategy_action, trigger_reason, action_text)
    return action in ('ACCUM_BUY', 'GRID_BUY', 'IDLE_WAKE')


def clip(value, min_value, max_value):
    """限制数值范围"""
    return max(min_value, min(value, max_value))


def round_to_step(value, step=10):
    """按固定步进取整，便于实际执行。"""
    return round(value / step) * step


def calc_mid_position_factor(nav_df, current_nav):
    """用近250个净值点估算当前所处区间位置。"""
    if nav_df is None or current_nav is None:
        return 1.0, None

    sample = nav_df.head(250)
    if sample.empty:
        return 1.0, None

    navs = [float(row['unit_nav']) for _, row in sample.iterrows() if row['unit_nav'] is not None]
    if not navs:
        return 1.0, None

    low = min(navs)
    high = max(navs)
    if high <= low:
        return 1.0, 0.5

    pos = (current_nav - low) / (high - low)
    pos = clip(pos, 0.0, 1.0)

    if pos <= 0.35:
        return 1.2, pos
    if pos <= 0.65:
        return 1.0, pos
    if pos <= 0.85:
        return 0.7, pos
    return 0.4, pos


def calc_idle_wake_amount(current_value, price_change, mid_position_factor, base_amount):
    """闲置唤醒平衡版：仓位、短期涨跌、中期位置共同决定金额。"""
    target_value = 3000.0
    safe_value = max(current_value or 0, 1.0)
    h_factor = clip((target_value / safe_value) ** 0.5, 0.4, 1.6)

    if price_change <= -0.03:
        short_factor = 1.2
    elif price_change <= 0.03:
        short_factor = 1.0
    elif price_change <= 0.06:
        short_factor = 0.8
    elif price_change <= 0.10:
        short_factor = 0.6
    else:
        short_factor = 0.4

    amount = clip(base_amount * h_factor * short_factor * mid_position_factor, 20, 150)
    amount = clip(round_to_step(amount, 10), 20, 150)
    return float(amount), h_factor, short_factor


def send_telegram(message):
    """发送 Telegram 消息"""
    try:
        token = TELEGRAM_TOKEN
        chat_id = TELEGRAM_CHAT_ID

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


def sync_trade_to_fund_db(fund_code, trade_date, trade_type, amount, shares, nav, strategy_action, trigger_reason, status='CONFIRMED'):
    """将策略已确认交易同步到基金主账，避免两套账分叉。"""
    if not os.path.exists(FUND_DB):
        return False, '基金数据库不存在'

    fund_conn = sqlite3.connect(FUND_DB)
    fund_cursor = fund_conn.cursor()

    # 同交易日、同方向、同来源已存在则不重复写入
    fund_cursor.execute(
        """
        SELECT id FROM fund_trades
        WHERE fund_code = ? AND trade_date = ? AND trade_type = ? AND trade_source = 'STRATEGY'
          AND strategy_action = ?
        ORDER BY id DESC LIMIT 1
        """,
        (fund_code, trade_date, trade_type, strategy_action)
    )
    if fund_cursor.fetchone():
        fund_conn.close()
        return True, 'fund_trades 已存在'

    is_shares = 1 if trade_type == 'SELL' and shares else 0
    trade_amount = shares if is_shares else amount
    original_remark = f'{trigger_reason} 同步入主账'
    confirm_date = trade_date if status == 'CONFIRMED' else None

    fund_cursor.execute(
        """
        INSERT INTO fund_trades (
            trade_date, amount, trade_type, fund_code, status,
            confirm_date, is_qdii, is_shares, trade_source, strategy_action, original_remark
        ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, 'STRATEGY', ?, ?)
        """,
        (trade_date, trade_amount, trade_type, fund_code, status, confirm_date, is_shares, strategy_action, original_remark)
    )

    if status == 'CONFIRMED' and nav:
        fund_cursor.execute(
            "SELECT shares, base_amount, fund_name FROM fund_holdings WHERE fund_code = ?",
            (fund_code,)
        )
        holding = fund_cursor.fetchone()

        if trade_type == 'BUY':
            buy_shares = shares if shares else amount / nav
            if holding:
                old_shares, old_base, _ = holding
                new_shares = (old_shares or 0) + buy_shares
                new_base = (old_base or 0) + amount
                fund_cursor.execute(
                    "UPDATE fund_holdings SET shares = ?, base_amount = ?, nav = ?, nav_date = ?, updated_at = CURRENT_TIMESTAMP WHERE fund_code = ?",
                    (new_shares, new_base, nav, trade_date.replace('-', ''), fund_code)
                )
        elif trade_type == 'SELL' and holding:
            old_shares, old_base, _ = holding
            sell_shares = shares if shares else amount / nav
            actual_amount = sell_shares * nav
            new_shares = (old_shares or 0) - sell_shares
            new_base = (old_base or 0) * (1 - sell_shares / old_shares) if old_shares and old_shares > 0 else 0
            if new_shares <= 0.01:
                fund_cursor.execute("DELETE FROM fund_holdings WHERE fund_code = ?", (fund_code,))
            else:
                fund_cursor.execute(
                    "UPDATE fund_holdings SET shares = ?, base_amount = ?, nav = ?, nav_date = ?, updated_at = CURRENT_TIMESTAMP WHERE fund_code = ?",
                    (new_shares, new_base, nav, trade_date.replace('-', ''), fund_code)
                )

    fund_conn.commit()
    fund_conn.close()
    return True, '同步成功'

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
        SELECT fund_code, fund_name, step, last_nav, last_date, total_cost, total_shares, grid_base_nav, phase
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

    for fund_code, fund_name, step, last_nav, last_date, total_cost, total_shares, grid_base_nav, phase_col in positions:
        nav_df = get_nav_df(pro, fund_code)
        if nav_df is None:
            continue
        current_nav = float(nav_df.iloc[0]['unit_nav'])
        nav_date = str(nav_df.iloc[0]['nav_date'])

        drawdown = calc_drawdown(current_nav, last_nav)
        phase = get_phase(grid_base_nav, phase_col)

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
                    'action': '建仓期卖出', 'strategy_action': 'ACCUM_SELL', 'amount': sell_amount,
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
                    'action': f'L{step+1}加仓', 'strategy_action': 'ACCUM_BUY', 'amount': add_amount,
                    'drawdown': drawdown, 'step': step, 'phase': 'ACCUMULATION'
                })
        else:
            # 网格阶段
            if not grid_base_nav:
                # 基准净值待定，跳过本轮监控
                continue

            if drawdown <= grid_buy_threshold:
                actions.append({
                    'fund_code': fund_code, 'fund_name': fund_name,
                    'action': '网格买入', 'strategy_action': 'GRID_BUY', 'amount': grid_buy_amount,
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
                        'action': '网格卖出', 'strategy_action': 'GRID_SELL', 'amount': batch_shares * current_nav,
                        'shares': batch_shares, 'batch_id': batch_id,
                        'profit_ratio': batch_profit, 'step': step, 'phase': 'GRID'
                    })
                    break

        # 闲置唤醒（网格期不触发）
        if phase != 'GRID' and last_date:
            idle_days = count_trade_days(pro, last_date, today)
            if idle_days >= idle_trade_days:
                base_idle_amount = float(params.get('idle_wake_amount', 100))
                mid_factor, mid_pos = calc_mid_position_factor(nav_df, current_nav)
                idle_amount, h_factor, short_factor = calc_idle_wake_amount(current_value, drawdown, mid_factor, base_idle_amount)
                if idle_amount > 0:
                    actions.append({
                        'fund_code': fund_code, 'fund_name': fund_name,
                        'action': '闲置唤醒', 'strategy_action': 'IDLE_WAKE', 'amount': idle_amount,
                        'drawdown': drawdown, 'step': step, 'phase': phase,
                        'idle_days': idle_days, 'h_factor': h_factor,
                        'short_factor': short_factor, 'mid_factor': mid_factor, 'mid_pos': mid_pos
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
        action = a.get('action', '')
        action_type = classify_strategy_action(a.get('strategy_action'), action_text=action)

        if action_type in ('ACCUM_SELL', 'GRID_SELL'):
            profit_pct = a.get('profit_ratio', 0) * 100
            print(f"🔴 {a['fund_code']} {a['fund_name']}: {action} {a['amount']:.0f}元 (收益{profit_pct:.1f}%)")
            msg_lines.append(f"🔴 {a['fund_code']} {action} {a['amount']:.0f}元 (+{profit_pct:.1f}%)")
        elif action_type in ('IDLE_WAKE',):
            idle_days = a.get('idle_days', 0)
            print(f"💤 {a['fund_code']} {a['fund_name']}: {action} {a['amount']:.0f}元 (闲置{idle_days}交易日)")
            msg_lines.append(f"💤 {a['fund_code']} {action} {a['amount']:.0f}元 ({idle_days}天)")
        else:
            drawdown_pct = abs(a.get('drawdown', 0)) * 100
            print(f"🟢 {a['fund_code']} {a['fund_name']}: {action} {a['amount']:.0f}元 (跌{drawdown_pct:.1f}%)")
            msg_lines.append(f"🟢 {a['fund_code']} {action} {a['amount']:.0f}元 (-{drawdown_pct:.1f}%)")

    msg_lines.append("</pre>")

    buy_actions = [a for a in actions if is_buy_like_action(a.get('strategy_action'), action_text=a.get('action'))]
    sell_actions = [a for a in actions if is_sell_action(a.get('strategy_action'), action_text=a.get('action'))]
    msg_lines.append(f"\n买入: {len(buy_actions)} | 卖出: {len(sell_actions)}")

    if send_msg:
        send_telegram('\n'.join(msg_lines))

    return actions

def record_operation(fund_code, trade_type, amount, trade_date=None, shares=None, nav=None, trigger_reason_override=None):
    """记录手动操作"""
    if trade_date is None:
        trade_date = datetime.now().strftime('%Y-%m-%d')

    if not os.path.exists(GRID_DB):
        return False, "GridSeed 数据库不存在"

    pro = ts.pro_api(TS_TOKEN)
    conn = sqlite3.connect(GRID_DB)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT fund_name, step, total_cost, total_shares, grid_base_nav, phase FROM strategy_positions WHERE fund_code = ?",
        (fund_code,)
    )
    pos = cursor.fetchone()

    if not pos:
        conn.close()
        return False, f"基金 {fund_code} 不在监控列表中"

    fund_name, step, total_cost, total_shares, grid_base_nav, phase_col = pos
    phase = get_phase(grid_base_nav, phase_col)

    is_confirmed = False

    if not nav:
        nav_result = get_nav(pro, fund_code, trade_date)
        if nav_result is not None:
            nav = nav_result
            is_confirmed = True
        else:
            fallback = get_nav(pro, fund_code)
            if fallback:
                nav = fallback[0]
            else:
                nav = None
            is_confirmed = False
    else:
        # 如果手动传递了 nav，则认为是估算净值（暂不计为确认态，防止写入错误单价）
        is_confirmed = False

    if not shares and nav:
        shares = amount / nav

    trade_source = 'STRATEGY'
    strategy_action = 'NONE'
    step_label = None

    if trade_type == 'BUY':
        if phase == 'ACCUMULATION':
            trigger_reason = trigger_reason_override or f'L{step+1}加仓'
            if '唤醒' in trigger_reason:
                trade_source = 'IDLE_WAKE'
                strategy_action = 'IDLE_WAKE'
                new_step = step
            else:
                strategy_action = 'ACCUM_BUY'
                new_step = step + 1
                step_label = f'L{new_step}'
        else:
            trigger_reason = trigger_reason_override or '网格买入'
            trade_source = 'GRID'
            strategy_action = 'GRID_BUY'
            new_step = step
            # 网格买入：仅当确认为真实净值时，此时才写入 grid_batches 表
            if is_confirmed and shares and nav:
                cursor.execute('''
                    INSERT INTO grid_batches (fund_code, buy_date, amount, shares, nav, status)
                    VALUES (?, ?, ?, ?, ?, 'HELD')
                ''', (fund_code, trade_date, amount, shares, nav))
    else:
        if phase == 'ACCUMULATION':
            trigger_reason = trigger_reason_override or '建仓期卖出'
            strategy_action = 'ACCUM_SELL'
            cursor.execute("UPDATE strategy_positions SET grid_base_nav = ? WHERE fund_code = ?", (nav, fund_code))
        else:
            trigger_reason = trigger_reason_override or '网格卖出'
            trade_source = 'GRID'
            strategy_action = 'GRID_SELL'
            # 网格卖出：同理，确认为真实净值时才更新
            if is_confirmed and shares and nav:
                cursor.execute('''
                    UPDATE grid_batches
                    SET status = 'SOLD', sell_date = ?, sell_nav = ?, profit = ?
                    WHERE fund_code = ? AND status = 'HELD'
                    ORDER BY buy_date LIMIT 1
                ''', (trade_date, nav, shares * nav - amount, fund_code))
        new_step = step

    if trigger_reason == '进入网格':
        trade_source = 'STRATEGY'
        strategy_action = 'ENTER_GRID'

    cursor.execute(
        "UPDATE strategy_positions SET last_date = ?, last_action = ?, last_amount = ?, step = ?, updated_at = ? WHERE fund_code = ?",
        (trade_date, trigger_reason, amount, new_step, datetime.now().strftime('%Y-%m-%d %H:%M'), fund_code)
    )

    status = 'CONFIRMED' if is_confirmed else 'PENDING_NAV'
    cursor.execute(
        "INSERT INTO strategy_trades (fund_code, trade_date, trade_type, amount, shares, nav, trigger_reason, status, trade_source, strategy_action, step_label) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (fund_code, trade_date, trade_type, amount, shares, nav, trigger_reason, status, trade_source, strategy_action, step_label)
    )

    if status == 'CONFIRMED':
        sync_trade_to_fund_db(
            fund_code, trade_date, trade_type, amount, shares, nav,
            strategy_action, trigger_reason, status='CONFIRMED'
        )

    # 如果是进入网格模式，更新grid_base_nav
    if trigger_reason in ['进入网格', '赎回'] or '建仓期卖出' in trigger_reason:
        # 核心逻辑：若净值尚未确认，则 grid_base_nav 设为 NULL，正式进入 GRID 阶段
        target_nav = nav if is_confirmed else None
        cursor.execute("UPDATE strategy_positions SET grid_base_nav = ?, phase = 'GRID' WHERE fund_code = ?", (target_nav, fund_code))

    conn.commit()
    conn.close()

    return True, f"{fund_code} {fund_name}: {trigger_reason} {amount}元，状态: {status}，监督点更新"

def update_pending_navs():
    """更新待补充净值的交易记录"""
    if not os.path.exists(GRID_DB):
        return 0, []

    pro = ts.pro_api(TS_TOKEN)
    conn = sqlite3.connect(GRID_DB)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, fund_code, trade_date, trade_type, amount, shares, trigger_reason, strategy_action FROM strategy_trades WHERE status = 'PENDING_NAV'"
    )
    pending = cursor.fetchall()

    if not pending:
        conn.close()
        return 0, []

    updated = 0
    failed = []

    for trade_id, fund_code, trade_date, trade_type, amount, shares, trigger_reason, strategy_action in pending:
        nav = get_nav(pro, fund_code, trade_date)

        if not nav:
            failed.append({'fund_code': fund_code, 'trade_date': trade_date, 'reason': '净值未出'})
            continue

        resolved_action = classify_strategy_action(strategy_action, trigger_reason)

        # 买入默认由金额反推份额；卖出若用户先给了份额，则确认时保持份额不变，只回算金额。
        if trade_type == 'SELL' and shares:
            confirmed_shares = shares
            confirmed_amount = confirmed_shares * nav
        else:
            confirmed_shares = amount / nav
            confirmed_amount = amount

        cursor.execute(
            "UPDATE strategy_trades SET nav = ?, shares = ?, amount = ?, status = 'CONFIRMED' WHERE id = ?",
            (nav, confirmed_shares, confirmed_amount, trade_id)
        )
        cursor.execute("UPDATE strategy_positions SET last_nav = ? WHERE fund_code = ?", (nav, fund_code))

        if resolved_action in ('ENTER_GRID', 'ACCUM_SELL'):
            cursor.execute("UPDATE strategy_positions SET grid_base_nav = ?, phase = 'GRID' WHERE fund_code = ?", (nav, fund_code))

        if resolved_action == 'GRID_BUY':
            cursor.execute('''
                INSERT INTO grid_batches (fund_code, buy_date, amount, shares, nav, status)
                VALUES (?, ?, ?, ?, ?, 'HELD')
            ''', (fund_code, trade_date, confirmed_amount, confirmed_shares, nav))
        elif resolved_action == 'GRID_SELL':
            cursor.execute('''
                UPDATE grid_batches 
                SET status = 'SOLD', sell_date = ?, sell_nav = ?, profit = ?
                WHERE fund_code = ? AND status = 'HELD'
                ORDER BY buy_date LIMIT 1
            ''', (trade_date, nav, confirmed_shares * nav - confirmed_amount, fund_code))

        sync_trade_to_fund_db(
            fund_code, trade_date, trade_type, confirmed_amount, confirmed_shares, nav,
            resolved_action, trigger_reason, status='CONFIRMED'
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
            fund_code = sys.argv[2]
            trade_type = sys.argv[3]
            amount = float(sys.argv[4])
            trigger_reason_override = sys.argv[5] if len(sys.argv) >= 6 else None
            success, msg = record_operation(fund_code, trade_type, amount, trigger_reason_override=trigger_reason_override)
            print(msg)
        else:
            print("用法: python strategy.py [check|check_silent|update_navs|record <code> <BUY|SELL> <amount> [reason]]")
    else:
        run_check()