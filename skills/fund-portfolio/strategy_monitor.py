#!/usr/bin/env python3
"""
基金投资建议生成器 - 基于 BIAS-250 和 3年回撤 (Drawdown)
核心指标：
- BIAS-250: (当前净值 - 250日均线) / 250日均线
- Drawdown: (近3年最高净值 - 当前净值) / 近3年最高净值
"""
import sqlite3
import pandas as pd
import tushare as ts
from datetime import datetime, timedelta
import os
import sys

# 路径适配
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import TS_TOKEN, FUND_DB, FUND_PROFILES, STRATEGY_THRESHOLDS

def get_history_nav(fund_code, days=1100):
    """
    获取基金历史净值，优先从数据库获取，不足则补充分支
    3年约 750 交易日，取 1100 自然日作为保险范围
    """
    conn = sqlite3.connect(FUND_DB)
    # 尝试从数据库读取
    query = f"SELECT nav_date, nav FROM fund_nav_history WHERE fund_code = ? ORDER BY nav_date DESC LIMIT {days}"
    df_local = pd.read_sql_query(query, conn, params=(fund_code,))
    conn.close()
    
    # 如果本地数据不足以计算 250日均线 (至少需要 250条) 或 3年回撤
    # 理论上 3年交易日约为 750 天
    if len(df_local) < 750:
        print(f"  {fund_code}: 本地数据量({len(df_local)})不足，尝试从 Tushare 补全...")
        pro = ts.pro_api(TS_TOKEN)
        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
            df_remote = pro.fund_nav(ts_code=f'{fund_code}.OF', start_date=start_date, end_date=end_date)
            if not df_remote.empty:
                df_remote = df_remote[['nav_date', 'unit_nav']].rename(columns={'unit_nav': 'nav'})
                return df_remote.sort_values('nav_date', ascending=False)
        except Exception as e:
            print(f"  获取远程数据失败: {e}")
    
    return df_local

def calculate_metrics(df):
    """计算核心指标"""
    if df.empty or len(df) < 2:
        return None
    
    # 确保按时间升序排列用于计算
    df = df.sort_values('nav_date', ascending=True).reset_index(drop=True)
    
    current_nav = df.iloc[-1]['nav']
    
    # 1. BIAS-250 (计算 250 天移动平均)
    if len(df) >= 250:
        ma250 = df['nav'].tail(250).mean()
        bias_250 = (current_nav - ma250) / ma250
    else:
        # 数据不足 250 天时，使用全量均值作为参考（弱参考）
        ma_all = df['nav'].mean()
        bias_250 = (current_nav - ma_all) / ma_all
        
    # 2. Drawdown (近 3 年，即全量 df 的最高点)
    # 因为 get_history_nav 已经限制了 1100 天（约 3 年交易日）
    max_nav = df['nav'].max()
    drawdown = (max_nav - current_nav) / max_nav
    
    return {
        'current_nav': current_nav,
        'bias_250': bias_250,
        'drawdown': drawdown,
        'nav_date': df.iloc[-1]['nav_date']
    }

def get_strategy_signal(fund_code, metrics):
    """根据阈值匹配信号"""
    profile = FUND_PROFILES.get(fund_code, 'medium_volatility')
    thresholds = STRATEGY_THRESHOLDS.get(profile)
    
    bias = metrics['bias_250']
    dd = metrics['drawdown']
    
    # 默认状态
    signal = {
        'level': '二级：观望区',
        'action': '维持标准定投',
        'multiplier': 1.0
    }
    
    # 依次判断，由重到轻
    # 这里的逻辑采用“或”与“且”的结合，优先匹配最极端的区间
    
    # 止盈判断 (L1)
    if bias > thresholds['SELL_SIGNAL']['bias']:
        return {
            'level': '一级：贪婪区',
            'action': thresholds['SELL_SIGNAL']['action'],
            'multiplier': thresholds['SELL_SIGNAL']['multiplier']
        }
    
    # 梭哈/极佳区 (L5)
    if bias < thresholds['BUY_L5']['bias'] and dd > thresholds['BUY_L5']['drawdown']:
        return {
            'level': '五级：梭哈区',
            'action': thresholds['BUY_L5']['action'],
            'multiplier': thresholds['BUY_L5']['multiplier']
        }
        
    # 大额区 (L4)
    if bias < thresholds['BUY_L4']['bias'] and dd > thresholds['BUY_L4']['drawdown']:
        return {
            'level': '四级：大额区',
            'action': thresholds['BUY_L4']['action'],
            'multiplier': thresholds['BUY_L4']['multiplier']
        }

    # 补仓区 (L3)
    if bias < thresholds['BUY_L3']['bias'] and dd > thresholds['BUY_L3']['drawdown']:
        return {
            'level': '三级：补仓区',
            'action': thresholds['BUY_L3']['action'],
            'multiplier': thresholds['BUY_L3']['multiplier']
        }
        
    return signal

def monitor_fund(fund_code):
    """监控单只基金并返回结果"""
    df = get_history_nav(fund_code)
    metrics = calculate_metrics(df)
    if not metrics:
        return None
    
    signal = get_strategy_signal(fund_code, metrics)
    metrics.update(signal)
    return metrics

def init_stats_table():
    """初始化技术指标存储表"""
    conn = sqlite3.connect(FUND_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fund_technical_stats (
            fund_code TEXT,
            nav_date TEXT,
            bias_250 REAL,
            drawdown REAL,
            signal_level TEXT,
            suggested_action TEXT,
            multiplier REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (fund_code, nav_date)
        )
    ''')
    conn.commit()
    conn.close()

def save_stats(fund_code, metrics):
    """保存计算结果"""
    init_stats_table()
    conn = sqlite3.connect(FUND_DB)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO fund_technical_stats 
        (fund_code, nav_date, bias_250, drawdown, signal_level, suggested_action, multiplier)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (fund_code, metrics['nav_date'], metrics['bias_250'], metrics['drawdown'], 
          metrics['level'], metrics['action'], metrics['multiplier']))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    # 测试代码
    test_code = '001665'
    res = monitor_fund(test_code)
    if res:
        print(f"监控结果 [{test_code}]:")
        print(f"  BIAS-250: {res['bias_250']:.2%}")
        print(f"  Drawdown: {res['drawdown']:.2%}")
        print(f"  Signal: {res['level']} -> {res['action']}")
        save_stats(test_code, res)
