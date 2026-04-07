#!/usr/bin/env python3
"""
基金持仓管理系统 - 定投执行

执行时间: 8:23

规则: 从数据库读取定投配置
- dca_config表：周定投金额
- is_qdii字段：标记QDII基金

节假日逻辑:
- A股非交易日：跳过所有定投（渠道关闭）
- 节后第一个交易日：自动补投假期中被跳过的工作日定投
- 补投只补 A 股节假日（非周末），避免重复
"""
import sqlite3
import tushare as ts
from datetime import datetime, timedelta
import os
import sys

# 添加父目录到路径，支持导入config
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import FUND_DB, TS_TOKEN

def get_dca_config(conn):
    """从数据库读取定投配置"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fund_code, fund_name, weekday_1, weekday_2, weekday_3, weekday_4, weekday_5, 
               monthly_day, monthly_amount, is_qdii
        FROM dca_config WHERE enabled = 1
    """)
    return cursor.fetchall()

def is_a_share_trade_day(pro, date):
    """判断指定日期是否为 A 股交易日"""
    try:
        date_str = date.strftime('%Y%m%d')
        df = pro.trade_cal(exchange='SSE', start_date=date_str, end_date=date_str)
        if not df.empty:
            return df.iloc[0]['is_open'] == 1
    except Exception as e:
        print(f"  ⚠️ 交易日历查询失败: {e}，默认执行")
    return True  # 查询失败时默认执行，避免漏单

def get_missed_holiday_weekdays(pro, today):
    """
    获取节后需要补投的工作日列表
    
    回溯逻辑：从昨天开始往前查，找到连续的 A 股非交易日中属于工作日（周一~周五）的日期。
    一旦遇到正常交易日，停止回溯。
    
    返回: [(weekday_index, date_str), ...] 例如 [(0, '2026-04-06'), (3, '2026-04-03')]
    """
    try:
        # 向前查找最多 14 天的交易日历
        start = (today - timedelta(days=14)).strftime('%Y%m%d')
        end = (today - timedelta(days=1)).strftime('%Y%m%d')
        
        df = pro.trade_cal(exchange='SSE', start_date=start, end_date=end)
        if df.empty:
            return []
        
        # 按日期降序排列（从昨天往前查）
        df = df.sort_values('cal_date', ascending=False)
        
        missed = []
        for _, row in df.iterrows():
            cal_date = datetime.strptime(row['cal_date'], '%Y%m%d')
            
            if row['is_open'] == 1:
                # 遇到正常交易日，停止回溯
                break
            
            # 非交易日 + 不是周末 = 节假日工作日，需要补投
            if cal_date.weekday() < 5:
                missed.append((cal_date.weekday(), cal_date.strftime('%Y-%m-%d')))
        
        return missed
    except Exception as e:
        print(f"  ⚠️ 节假日回溯查询失败: {e}")
        return []

def create_weekday_trades(cursor, config, weekday, trade_date, is_qdii_filter=None, label=""):
    """
    为指定星期几创建定投交易
    
    Args:
        cursor: 数据库游标
        config: 定投配置列表
        weekday: 星期几 (0=周一 ... 4=周五)
        trade_date: 交易日期字符串
        is_qdii_filter: None=所有, 0=仅非QDII, 1=仅QDII
        label: 日志标签 (如 "补周一")
    
    Returns:
        创建的交易笔数
    """
    count = 0
    for fund_code, fund_name, w1, w2, w3, w4, w5, monthly_day, monthly_amount, is_qdii in config:
        # 如果有 QDII 过滤条件
        if is_qdii_filter is not None and is_qdii != is_qdii_filter:
            continue
        
        amounts = [w1, w2, w3, w4, w5]
        amount = amounts[weekday] if weekday < 5 else 0
        
        if amount > 0:
            cursor.execute('''
                INSERT INTO fund_trades (trade_date, trade_type, amount, fund_code, status, is_qdii)
                VALUES (?, 'BUY', ?, ?, 'PENDING', ?)
            ''', (trade_date, amount, fund_code, is_qdii))
            
            suffix = f" ({label})" if label else ""
            print(f"  {fund_code} {fund_name}: {amount}元{suffix}")
            count += 1
    return count

def run_dca():
    """执行定投"""
    today = datetime.now()
    weekday = today.weekday()  # 0=周一, 1=周二, ...
    day = today.day
    
    print(f"=== 定投执行 {today.strftime('%Y-%m-%d %A')} ===")
    
    # 周末直接跳过
    if weekday >= 5:
        print("周末，跳过定投")
        return
    
    if not os.path.exists(FUND_DB):
        print("数据库不存在")
        return
    
    # 检查 A 股交易日
    pro = ts.pro_api(TS_TOKEN)
    if not is_a_share_trade_day(pro, today):
        print(f"今日 {today.strftime('%Y-%m-%d')} 非A股交易日，跳过定投")
        return
    
    conn = sqlite3.connect(FUND_DB)
    cursor = conn.cursor()
    
    # 从数据库读取配置
    config = get_dca_config(conn)
    
    if not config:
        print("无定投配置")
        conn.close()
        return
    
    trades_created = 0
    weekday_names = ['周一', '周二', '周三', '周四', '周五']
    
    # ===== 节后补投 =====
    missed_days = get_missed_holiday_weekdays(pro, today)
    if missed_days:
        print(f"\n📥 节后补投 (补 {len(missed_days)} 天):")
        for missed_wd, missed_date in missed_days:
            wd_name = weekday_names[missed_wd]
            count = create_weekday_trades(
                cursor, config, missed_wd, today.strftime('%Y-%m-%d'),
                label=f"补{wd_name} {missed_date}"
            )
            trades_created += count
    
    # ===== 当日周定投 =====
    weekday_name = weekday_names[weekday]
    print(f"\n周定投 ({weekday_name}):")
    count = create_weekday_trades(
        cursor, config, weekday, today.strftime('%Y-%m-%d')
    )
    trades_created += count
    
    # ===== 月定投（指定日期）=====
    print(f"\n月定投检查:")
    for fund_code, fund_name, w1, w2, w3, w4, w5, monthly_day, monthly_amount, is_qdii in config:
        if monthly_day > 0 and day == monthly_day and monthly_amount > 0:
            cursor.execute('''
                INSERT INTO fund_trades (trade_date, trade_type, amount, fund_code, status, is_qdii)
                VALUES (?, 'BUY', ?, ?, 'PENDING', ?)
            ''', (today.strftime('%Y-%m-%d'), monthly_amount, fund_code, is_qdii))
            
            print(f"  {fund_code} {fund_name}: {monthly_amount}元 (月定投{monthly_day}号)")
            trades_created += 1
    
    if trades_created == 0:
        print("  今日无定投")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ 创建 {trades_created} 笔定投交易")

if __name__ == '__main__':
    run_dca()