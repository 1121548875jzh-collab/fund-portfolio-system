#!/usr/bin/env python3
"""
GridSeed V3.0 - 策略核心

规则:
- 建仓阶段 (grid_base_nav=NULL):
  - L1-L4 (step 0-3): 跌3% → 加仓15%
  - L5-L6 (step 4-5): 跌5% → 加仓30%
  - step=6: 不再加仓

- 网格阶段 (grid_base_nav 有值):
  - 跌3% → 买入 100元
  - 涨10% → 卖出

- 闲置唤醒:
  - 10个交易日无操作 → 提醒加仓 100元
  - 不增加 step
"""
import sqlite3
import tushare as ts
from datetime import datetime, timedelta
import os

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
GRID_THRESHOLD = -0.03   # 网格 -3%
IDLE_DAYS = 10           # 闲置天数

def get_nav(pro, fund_code):
    """获取最新净值"""
    try:
        df = pro.fund_nav(ts_code=f'{fund_code}.OF')
        if df.empty:
            return None, None
        return float(df.iloc[0]['unit_nav']), str(df.iloc[0]['nav_date'])
    except:
        return None, None

def calc_drawdown(current_nav, base_nav):
    """计算跌幅"""
    if not base_nav or base_nav == 0:
        return 0
    return (current_nav - base_nav) / base_nav

def get_phase(grid_base_nav):
    """判断阶段"""
    return 'GRID' if grid_base_nav else 'ACCUMULATION'

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
        
        # 计算跌幅
        drawdown = calc_drawdown(current_nav, last_nav)
        phase = get_phase(grid_base_nav)
        
        if phase == 'ACCUMULATION':
            # 建仓阶段
            if step < 4 and drawdown <= L1_L4_THRESHOLD:
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
            # 网格阶段
            if drawdown <= GRID_THRESHOLD:
                actions.append({
                    'fund_code': fund_code,
                    'fund_name': fund_name,
                    'action': '网格买入',
                    'amount': 100,
                    'drawdown': drawdown,
                    'step': step,
                    'phase': 'GRID'
                })
        
        # 检查闲置
        if last_date:
            last_dt = datetime.strptime(last_date, '%Y-%m-%d')
            idle_days = (datetime.now() - last_dt).days
            if idle_days >= IDLE_DAYS:
                actions.append({
                    'fund_code': fund_code,
                    'fund_name': fund_name,
                    'action': '闲置唤醒',
                    'amount': 100,
                    'drawdown': drawdown,
                    'step': step,
                    'phase': phase,
                    'idle_days': idle_days
                })
    
    conn.close()
    return actions

def run_check():
    """运行检查并输出结果"""
    print(f"=== GridSeed V3.0 检查 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")
    
    actions = check_actions()
    
    if not actions:
        print("无操作建议")
        return
    
    print(f"触发操作: {len(actions)} 只\n")
    
    for a in actions:
        print(f"{a['fund_code']} {a['fund_name']}: {a['action']} {a['amount']:.0f}元 (跌{abs(a['drawdown'])*100:.1f}%)")

if __name__ == '__main__':
    run_check()