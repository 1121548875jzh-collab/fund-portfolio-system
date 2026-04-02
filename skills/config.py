#!/usr/bin/env python3
"""
基金系统统一配置

所有脚本从此文件导入配置，避免硬编码
"""
import os

# 基础路径（自动适配 Windows/Linux）
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

# 尝试加载 .env 文件（如果安装了 python-dotenv）
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, '.env'))
except ImportError:
    pass

# 数据库路径
FUND_DB = os.path.join(BASE_DIR, 'skills/fund-portfolio/fund_portfolio.db')
GRID_DB = os.path.join(BASE_DIR, 'skills/gridseed-v3/data/gridseed.db')

# Tushare Token (优先从环境变量读取，保留兜底硬编码)
TS_TOKEN = os.environ.get('TS_TOKEN', '7b81c3a430995f2912509eea6e5932513760cf170626110a440c497c')

# 邮件配置
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', '1121548875jzh@gmail.com')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', 'vfdoetqursseoase')
TO_EMAIL = os.environ.get('TO_EMAIL', '1121548875jzh@gmail.com')

# Telegram 配置
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8727468499:AAFPkdERWFuuWR1U1UbK4A9tVKT7F1_C6I4')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '6667291451')

# 基准日期
BASE_DATE = '2026-03-14'

# QDII基金列表
QDII_FUNDS = ['012062', '017641', '017437', '017091']

# 基金分类定义 (🔴高波动 / 🟡中波动 / 🟢低波动)
# 用于匹配不同的 BIAS & Drawdown 阈值
FUND_PROFILES = {
    # 🔴 高波动 (Volatility > 30%)
    '018957': 'high_volatility', '018463': 'high_volatility', '018125': 'high_volatility',
    '016874': 'high_volatility', '022287': 'high_volatility', '015790': 'high_volatility',
    '001665': 'high_volatility', '020629': 'high_volatility', '003625': 'high_volatility',
    
    # 🟡 中波动 (Volatility 20%-30%)
    '021909': 'medium_volatility', '012349': 'medium_volatility', '013180': 'medium_volatility',
    '002963': 'medium_volatility', '017437': 'medium_volatility', '011957': 'medium_volatility',
    '009982': 'medium_volatility', '007040': 'medium_volatility', '017091': 'medium_volatility',
    '019924': 'medium_volatility', '007882': 'medium_volatility',
    
    # 🟢 低波动 (Volatility < 20%)
    '004815': 'steady', '017641': 'steady', '016441': 'steady',
    '022431': 'steady', '003958': 'steady', '019261': 'steady', '023920': 'steady',
}

# 策略监控阈值 (BIAS & Drawdown)
# 键值：{等级: {阈值条件, 建议动作, 乘数}}
STRATEGY_THRESHOLDS = {
    'high_volatility': {
        'SELL_SIGNAL': {'bias': 0.25, 'action': '🔴 止盈区：停止定投，分批止盈计划', 'multiplier': 0},
        'BUY_L3': {'bias': -0.15, 'drawdown': 0.20, 'action': '🟡 补仓区：开启双倍定投', 'multiplier': 2.0},
        'BUY_L4': {'bias': -0.20, 'drawdown': 0.35, 'action': '🟠 大额区：投入预留资金 30%-50%', 'multiplier': 5.0},
        'BUY_L5': {'bias': -0.30, 'drawdown': 0.45, 'action': '🔴 梭哈区：重仓出击，全部打入', 'multiplier': 10.0},
    },
    'medium_volatility': {
        'SELL_SIGNAL': {'bias': 0.15, 'action': '🔴 止盈区：停止定投，分批止盈计划', 'multiplier': 0},
        'BUY_L3': {'bias': -0.08, 'drawdown': 0.10, 'action': '🟡 补仓区：开启双倍定投', 'multiplier': 2.0},
        'BUY_L4': {'bias': -0.15, 'drawdown': 0.20, 'action': '🟠 大额区：投入预留资金 30%-50%', 'multiplier': 5.0},
        'BUY_L5': {'bias': -0.20, 'drawdown': 0.30, 'action': '🔴 梭哈区：重仓出击', 'multiplier': 10.0},
    },
    'steady': {
        'SELL_SIGNAL': {'bias': 0.12, 'action': '🔴 止盈区：停止定投，分批止盈计划', 'multiplier': 0},
        'BUY_L3': {'bias': -0.05, 'drawdown': 0.08, 'action': '🟡 补仓区：开启双倍定投', 'multiplier': 2.0},
        'BUY_L4': {'bias': -0.10, 'drawdown': 0.12, 'action': '🟠 大额区：大额加仓建议', 'multiplier': 4.0},
        'BUY_L5': {'bias': -0.15, 'drawdown': 0.20, 'action': '🔴 梭哈区：极佳击球区', 'multiplier': 8.0},
    }
}