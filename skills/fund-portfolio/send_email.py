#!/usr/bin/env python3
"""
基金持仓邮件报告发送

执行时间: 8:30

数据来源: fund_holdings表（实时准确）
QDII基金列表: 从数据库读取
"""
import sqlite3
import smtplib
import csv
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta

DB_PATH = '/root/.openclaw/workspace-coder/skills/fund-portfolio/fund_portfolio.db'

SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = '1121548875jzh@gmail.com'
SMTP_PASSWORD = 'vfdoetqursseoase'
TO_EMAIL = '1121548875jzh@gmail.com'

BASE_DATE = '2026-03-14'

def get_qdii_funds(conn):
    """从数据库获取QDII基金列表"""
    cursor = conn.cursor()
    cursor.execute("SELECT fund_code FROM dca_config WHERE is_qdii = 1")
    return [row[0] for row in cursor.fetchall()]

def get_report_date(cursor):
    """获取报告日期"""
    cursor.execute("SELECT MAX(nav_date) FROM fund_nav_history")
    return cursor.fetchone()[0]

def get_nav_dates(cursor, report_date, qdii_funds):
    """获取各类基金的净值日期"""
    normal_today = report_date
    
    qdii_placeholder = ','.join(["'{}'".format(f) for f in qdii_funds]) if qdii_funds else "''"
    
    cursor.execute(f"""
        SELECT MAX(nav_date) FROM fund_nav_history 
        WHERE fund_code NOT IN ({qdii_placeholder}) AND nav_date < ?
    """, (normal_today,))
    normal_prev = cursor.fetchone()[0]
    
    cursor.execute(f"""
        SELECT MAX(nav_date) FROM fund_nav_history 
        WHERE fund_code IN ({qdii_placeholder})
    """)
    qdii_today = cursor.fetchone()[0]
    
    cursor.execute(f"""
        SELECT MAX(nav_date) FROM fund_nav_history 
        WHERE fund_code IN ({qdii_placeholder}) AND nav_date < ?
    """, (qdii_today,))
    qdii_prev = cursor.fetchone()[0]
    
    return normal_today, normal_prev, qdii_today, qdii_prev

def get_summary(cursor, normal_today, normal_prev, qdii_today, qdii_prev, qdii_funds):
    """获取汇总数据"""
    cursor.execute("""
        SELECT ROUND(SUM(base_amount), 2), ROUND(SUM(shares * nav), 2), ROUND(SUM(shares * nav - base_amount), 2)
        FROM fund_holdings
    """)
    total_base, total_asset, total_profit = cursor.fetchone()
    
    today_profit = 0
    qdii_placeholder = ','.join(["'{}'".format(f) for f in qdii_funds]) if qdii_funds else "''"
    
    cursor.execute(f"""
        SELECT ROUND(SUM(h.shares * (n1.nav - n2.nav)), 2)
        FROM fund_holdings h
        JOIN fund_nav_history n1 ON h.fund_code = n1.fund_code AND n1.nav_date = ?
        JOIN fund_nav_history n2 ON h.fund_code = n2.fund_code AND n2.nav_date = ?
        WHERE h.fund_code NOT IN ({qdii_placeholder})
    """, (normal_today, normal_prev))
    normal_today_profit = cursor.fetchone()[0] or 0
    today_profit += normal_today_profit
    
    cursor.execute(f"""
        SELECT ROUND(SUM(h.shares * (n1.nav - n2.nav)), 2)
        FROM fund_holdings h
        JOIN fund_nav_history n1 ON h.fund_code = n1.fund_code AND n1.nav_date = ?
        JOIN fund_nav_history n2 ON h.fund_code = n2.fund_code AND n2.nav_date = ?
        WHERE h.fund_code IN ({qdii_placeholder})
    """, (qdii_today, qdii_prev))
    qdii_today_profit = cursor.fetchone()[0] or 0
    today_profit += qdii_today_profit
    
    report_date_fmt = normal_today[:4] + '-' + normal_today[4:6] + '-' + normal_today[6:8]
    cursor.execute("SELECT ROUND(SUM(daily_profit), 2) FROM daily_fund_snapshot WHERE date = date(?, '-1 day')", (report_date_fmt,))
    prev_profit = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT ROUND(SUM(asset_value - base_amount), 2) FROM daily_fund_snapshot WHERE date = ?", (BASE_DATE,))
    base_profit = cursor.fetchone()[0] or -389.14
    
    cursor.execute("SELECT ROUND(SUM(total_profit), 2) FROM closed_position_profit")
    closed_profit = cursor.fetchone()[0] or -93.69
    
    profit_pct = total_profit / total_base * 100 if total_base else 0
    
    return {
        'total_base': total_base, 'total_asset': total_asset, 'total_profit': total_profit,
        'profit_pct': profit_pct, 'prev_profit': prev_profit, 'today_profit': today_profit,
        'base_profit': base_profit, 'closed_profit': closed_profit
    }

def get_holdings_detail(cursor, normal_today, normal_prev, qdii_today, qdii_prev, qdii_funds):
    """获取持仓明细"""
    nav_dt = datetime.strptime(normal_today, '%Y%m%d')
    week_ago = (nav_dt - timedelta(days=7)).strftime('%Y%m%d')
    month_ago = (nav_dt - timedelta(days=30)).strftime('%Y%m%d')
    
    result = []
    total_base = total_asset = total_profit = total_today = 0
    
    cursor.execute("""
        SELECT fund_code, fund_name, nav, shares, base_amount,
               ROUND(shares * nav, 2) as asset, ROUND(shares * nav - base_amount, 2) as profit
        FROM fund_holdings ORDER BY profit ASC
    """)
    holdings = cursor.fetchall()
    
    for code, name, nav, shares, base, asset, profit in holdings:
        is_qdii = code in qdii_funds
        
        today_nav_date = qdii_today if is_qdii else normal_today
        prev_nav_date = qdii_prev if is_qdii else normal_prev
        
        cursor.execute("SELECT nav FROM fund_nav_history WHERE fund_code = ? AND nav_date = ?", (code, today_nav_date))
        today_nav_row = cursor.fetchone()
        today_nav = today_nav_row[0] if today_nav_row else nav
        
        cursor.execute("SELECT nav FROM fund_nav_history WHERE fund_code = ? AND nav_date = ?", (code, prev_nav_date))
        prev_nav_row = cursor.fetchone()
        prev_nav = prev_nav_row[0] if prev_nav_row else today_nav
        
        cursor.execute("SELECT nav FROM fund_nav_history WHERE fund_code = ? AND nav_date = ?", (code, week_ago))
        week_nav_row = cursor.fetchone()
        week_nav = week_nav_row[0] if week_nav_row else today_nav
        
        cursor.execute("SELECT nav FROM fund_nav_history WHERE fund_code = ? AND nav_date = ?", (code, month_ago))
        month_nav_row = cursor.fetchone()
        month_nav = month_nav_row[0] if month_nav_row else today_nav
        
        today_profit = shares * (today_nav - prev_nav)
        daily_pct = (today_nav - prev_nav) / prev_nav * 100 if prev_nav else 0
        week_pct = (today_nav - week_nav) / week_nav * 100 if week_nav else 0
        month_pct = (today_nav - month_nav) / month_nav * 100 if month_nav else 0
        
        result.append({
            'code': code, 'name': name, 'nav': today_nav, 'shares': shares,
            'base': base, 'asset': asset, 'profit': profit,
            'today_profit': today_profit, 'daily_pct': daily_pct,
            'week_pct': week_pct, 'month_pct': month_pct
        })
        
        total_base += base or 0
        total_asset += asset or 0
        total_profit += profit or 0
        total_today += today_profit
    
    return result, total_base, total_asset, total_profit, total_today

def generate_report():
    """生成完整报告"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    qdii_funds = get_qdii_funds(conn)
    report_date = get_report_date(cursor)
    normal_today, normal_prev, qdii_today, qdii_prev = get_nav_dates(cursor, report_date, qdii_funds)
    summary = get_summary(cursor, normal_today, normal_prev, qdii_today, qdii_prev, qdii_funds)
    holdings, total_base, total_asset, total_profit, total_today = get_holdings_detail(cursor, normal_today, normal_prev, qdii_today, qdii_prev, qdii_funds)
    
    conn.close()
    
    date_str = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:8]}"
    
    csv_content = io.StringIO()
    writer = csv.writer(csv_content)
    
    writer.writerow([f'基金持仓报告 - {date_str}'])
    writer.writerow([])
    writer.writerow(['[汇总]'])
    writer.writerow(['持仓本金', summary['total_base']])
    writer.writerow(['总资产', summary['total_asset']])
    writer.writerow(['累计盈亏', summary['total_profit']])
    writer.writerow(['盈亏比例', f"{summary['profit_pct']:.2f}%"])
    writer.writerow(['昨日盈亏', summary['prev_profit']])
    writer.writerow(['今日涨跌', summary['today_profit']])
    writer.writerow([f'基准盈亏({BASE_DATE})', summary['base_profit']])
    writer.writerow(['清仓盈亏', summary['closed_profit']])
    writer.writerow([])
    
    writer.writerow(['[持仓明细]'])
    writer.writerow(['代码', '名称', '净值', '份额', '本金', '资产', '盈亏', '当日盈亏', '昨日涨跌', '近一周涨跌', '近一月涨跌'])
    
    for h in holdings:
        writer.writerow([
            h['code'], h['name'], h['nav'], round(h['shares'], 2), h['base'],
            h['asset'], h['profit'], f"{h['today_profit']:+.2f}",
            f"{h['daily_pct']:+.2f}%", f"{h['week_pct']:+.2f}%", f"{h['month_pct']:+.2f}%"
        ])
    
    writer.writerow(['合计', '', '', '', round(total_base, 2), round(total_asset, 2), round(total_profit, 2), f"{total_today:+.2f}", '', '', ''])
    
    return csv_content.getvalue(), date_str

def send_email(subject, csv_content, date_str):
    """发送邮件"""
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = TO_EMAIL
    msg['Subject'] = subject
    
    msg.attach(MIMEText(csv_content, 'plain', 'utf-8'))
    
    attachment = MIMEBase('text', 'csv')
    attachment.set_payload(csv_content.encode('utf-8-sig'))
    encoders.encode_base64(attachment)
    attachment.add_header('Content-Disposition', 'attachment', filename=f'fund_report_{date_str}.csv')
    msg.attach(attachment)
    
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [TO_EMAIL], msg.as_string())
    
    print(f"✅ 邮件已发送到 {TO_EMAIL}")

def main():
    csv_content, date_str = generate_report()
    send_email(f'基金持仓报告 - {date_str}', csv_content, date_str)

if __name__ == '__main__':
    main()