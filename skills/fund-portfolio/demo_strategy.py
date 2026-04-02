#!/usr/bin/env python3
"""
BIAS & Drawdown 机制运行演示脚本 (Mock 演示)
"""
import pandas as pd
import numpy as np

# 模拟导入 config (直接硬编码演示版)
STRATEGY_THRESHOLDS = {
    'high_volatility': {
        'SELL_SIGNAL': {'bias': 0.25, 'action': '🔴 止盈区', 'multiplier': 0},
        'BUY_L3': {'bias': -0.15, 'drawdown': 0.20, 'action': '🟡 补仓区', 'multiplier': 2.0},
        'BUY_L4': {'bias': -0.20, 'drawdown': 0.35, 'action': '🟠 大额区', 'multiplier': 5.0},
        'BUY_L5': {'bias': -0.30, 'drawdown': 0.45, 'action': '🔴 梭哈区', 'multiplier': 10.0},
    },
    'steady': {
        'SELL_SIGNAL': {'bias': 0.12, 'action': '🔴 止盈区', 'multiplier': 0},
        'BUY_L3': {'bias': -0.05, 'drawdown': 0.08, 'action': '🟡 补仓区', 'multiplier': 2.0},
        'BUY_L4': {'bias': -0.10, 'drawdown': 0.12, 'action': '🟠 大额区', 'multiplier': 4.0},
        'BUY_L5': {'bias': -0.15, 'drawdown': 0.20, 'action': '🔴 梭哈区', 'multiplier': 8.0},
    }
}

def simulate_metrics(case_name, current_nav, ma250, max_nav):
    bias_250 = (current_nav - ma250) / ma250
    drawdown = (max_nav - current_nav) / max_nav
    return {
        'case': case_name,
        'nav': current_nav,
        'bias_250': bias_250,
        'drawdown': drawdown
    }

def match_signal(profile, metrics):
    thresholds = STRATEGY_THRESHOLDS[profile]
    bias = metrics['bias_250']
    dd = metrics['drawdown']
    
    if bias > thresholds['SELL_SIGNAL']['bias']:
        return thresholds['SELL_SIGNAL']
    if bias < thresholds['BUY_L5']['bias'] and dd > thresholds['BUY_L5']['drawdown']:
        return thresholds['BUY_L5']
    if bias < thresholds['BUY_L4']['bias'] and dd > thresholds['BUY_L4']['drawdown']:
        return thresholds['BUY_L4']
    if bias < thresholds['BUY_L3']['bias'] and dd > thresholds['BUY_L3']['drawdown']:
        return thresholds['BUY_L3']
    return {'action': '🟢 观望/标准定投', 'multiplier': 1.0}

# 准备演示案例
cases = [
    # 🔴 高波动标的 (例如 AI 应用)
    ("AI表现强劲 (高位)", 1.5, 1.1, 1.5, 'high_volatility'),
    ("AI技术性调回调 (补仓)", 1.2, 1.5, 1.7, 'high_volatility'),
    ("AI恐慌阴跌 (大额)", 0.8, 1.2, 1.7, 'high_volatility'),
    
    # 🟢 稳健标的 (例如 红利/A500)
    ("红利高位止盈", 1.2, 1.05, 1.25, 'steady'),
    ("红利正常回调", 1.0, 1.08, 1.15, 'steady'),
    ("红利黄金坑", 0.9, 1.05, 1.15, 'steady'),
]

print("=== 基金策略监控机制运行逻辑演示 ===\n")
print(f"{'案例名称':<18} | {'BIAS-250':<10} | {'回撤度':<10} | {'操作信号'}")
print("-" * 75)

for name, nav, ma, mx, profile in cases:
    m = simulate_metrics(name, nav, ma, mx)
    sig = match_signal(profile, m)
    
    color = "🔴" if "高波动" in profile else "🟢"
    print(f"{name:<20} | {m['bias_250']:>9.2%} | {m['drawdown']:>9.2%} | {sig['action']} (x{sig['multiplier']})")

print("\n[运行原理说明]")
print("1. 均值回归: 当 BIAS < 阈值，说明价格显著低于年均成本，反弹概率大。")
print("2. 风险确认: 只有当回撤度 (Drawdown) 同步满足深度时，才触发加大幅度补仓，避免在阴跌初期过早耗尽资金。")
print("3. 个性化配置: 同样的回撤 20%，对稳健基金是'重仓'级别信号，对高波动基金可能仅是'定投加倍'。")
