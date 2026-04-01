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