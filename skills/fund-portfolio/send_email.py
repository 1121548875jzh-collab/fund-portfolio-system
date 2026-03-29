#!/usr/bin/env python3
"""
基金持仓邮件报告发送

执行时间: 8:30

邮件模板格式参照 SKILL.md
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

# 邮件配置
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = '1121548875jzh@gmail.com'
SMTP_PASSWORD = 'vfdoetqursseoase'
TO_EMAIL = '1121548875jzh@gmail.com'

QDII_FUNDS = ['012062', '017641', '017437', '017091']

def get_nav_date():
    """获取报告净值日期（最新净值日期）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(nav_date) FROM fund_nav_history")
    nav_date = cursor.fetchone()[0]
    conn.close()
    return nav_date

def get_summary(cursor, nav_date, prev_date):
    """获取汇总数据"""
    # 持仓汇总
    cursor.execute("""
        SELECT ROUND(SUM(base_amount), 2),
               ROUND(SUM(shares * nav), 2),
               ROUND(SUM(shares * nav - base_amount), 2)
        FROM fund_holdings
    """)
    total_base, total_asset, total_profit = cursor.fetchone()
    
    # 昨日盈亏
    cursor.execute("""
        SELECT ROUND(SUM(daily_profit), 2) FROM daily_fund_snapshot 
        WHERE date = ?
    """, (prev_date,))
    prev_profit = cursor.fetchone()[0] or 0
    
    # 今日涨跌（从最新快照获取）
    cursor.execute("""
        SELECT ROUND(SUM(daily_profit), 2) FROM daily_fund_snapshot 
        WHERE date = ?
    """, (nav_date,))
    today_profit = cursor.fetchone()[0] or 0
    
    # 清仓盈亏
    cursor.execute("SELECT ROUND(SUM(total_profit), 2) FROM closed_position_profit")
    closed_profit = cursor.fetchone()[0] or 0
    
    return {
        'total_base': total_base,
        'total_asset': total_asset,
        'total_profit': total_profit,
        'profit_pct': total_profit / total_base * 100 if total_base else 0,
        'prev_profit': prev_profit,
        'today_profit': today_profit,
        'closed_profit': closed_profit
    }

def get_weekly_change(cursor, nav_date):
    """获取近一周涨跌"""
    cursor.execute("""
        SELECT fund_code, fund_name, 
               ROUND((nav - prev_nav) / prev_nav * 100, 2) as change_pct
        FROM (
            SELECT h.fund_code, h.fund_name, h.nav,
                   (SELECT nav FROM fund_nav_history n2 
                    WHERE n2.fund_code = h.fund_code 
                    AND n2.nav_date < h.nav_date 
                    ORDER BY n2.nav_date DESC LIMIT 1) as prev_nav
            FROM fund_holdings h
        )
        WHERE prev_nav > 0
        ORDER BY change_pct DESC
    """)
    return cursor.fetchall()

def get_dca_stats(cursor, nav_date):
    """获取定投统计"""
    # 本周定投（周一到今天）
    cursor.execute("""
        SELECT ROUND(SUM(amount), 2) FROM fund_trades 
        WHERE status = 'CONFIRMED' 
        AND trade_date >= date(?, 'weekday 0', '-6 days')
    """, (nav_date[:4] + '-' + nav_date[4:6] + '-' + nav_date[6:8],))
    weekly_dca = cursor.fetchone()[0] or 0
    
    # 本月定投
    cursor.execute("""
        SELECT ROUND(SUM(amount), 2) FROM fund_trades 
        WHERE status = 'CONFIRMED' 
        AND trade_date LIKE ?
    """, (nav_date[:6] + '%',))
    monthly_dca = cursor.fetchone()[0] or 0
    
    return weekly_dca, monthly_dca

def get_holdings_detail(cursor):
    """获取持仓明细"""
    cursor.execute("""
        SELECT fund_code, fund_name, ROUND(shares, 2), base_amount, nav,
               ROUND(shares * nav, 2) as asset,
               ROUND(shares * nav - base_amount, 2) as profit,
               ROUND((shares * nav - base_amount) / base_amount * 100, 2) as profit_pct
        FROM fund_holdings ORDER BY fund_code
    """)
    return cursor.fetchall()

def get_recent_trades(cursor, days=7):
    """获取近N天交易"""
    cursor.execute("""
        SELECT trade_date, fund_code, trade_type, amount, status
        FROM fund_trades 
        WHERE trade_date >= date('now', ?)
        ORDER BY trade_date DESC
    """, (f'-{days} days',))
    return cursor.fetchall()

def generate_report():
    """生成完整报告"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    nav_date = get_nav_date()
    nav_date_fmt = f"{nav_date[:4]}-{nav_date[4:6]}-{nav_date[6:8]}"
    
    # 计算前一日净值日期
    prev_date = (datetime.strptime(nav_date_fmt, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y%m%d')
    
    summary = get_summary(cursor, nav_date, prev_date)
    weekly_changes = get_weekly_change(cursor, nav_date)
    weekly_dca, monthly_dca = get_dca_stats(cursor, nav_date)
    holdings = get_holdings_detail(cursor)
    trades = get_recent_trades(cursor)
    
    conn.close()
    
    # 生成正文
    report = f"""基金持仓报告 - {nav_date_fmt}

[汇总]
------------------------
持仓本金: {summary['total_base']:,.2f} 元
总资产: {summary['total_asset']:,.2f} 元
累计盈亏: {summary['total_profit']:+,.2f} 元 ({summary['profit_pct']:+.2f}%)
昨日盈亏: {summary['prev_profit']:+,.2f} 元
今日涨跌: {summary['today_profit']:+,.2f} 元
清仓盈亏: {summary['closed_profit']:+,.2f} 元

[近一周涨跌]
------------------------
涨幅前3:
"""
    
    # 涨幅前3
    top_gains = [c for c in weekly_changes if c[2] > 0][:3]
    for code, name, pct in top_gains:
        report += f"  {code} {name[:12]} {pct:+.2f}%\n"
    
    report += "跌幅前3:\n"
    
    # 跌幅前3
    top_losses = [c for c in weekly_changes if c[2] < 0][-3:]
    for code, name, pct in top_losses:
        report += f"  {code} {name[:12]} {pct:+.2f}%\n"
    
    report += f"""
[定投统计（已确认）]
------------------------
本周定投: {weekly_dca:,.2f} 元
本月定投: {monthly_dca:,.2f} 元

[持仓明细]
------------------------
代码     名称                     份额       本金      净值     资产      盈亏
------------------------
"""
    
    for code, name, shares, base, nav, asset, profit, pct in holdings:
        name_short = name[:16] if len(name) > 16 else name
        report += f"{code:<8} {name_short:<16} {shares:>8.2f} {base:>8.2f} {nav:>6.4f} {asset:>8.2f} {profit:>+8.2f}\n"
    
    # 生成CSV附件内容
    csv_content = io.StringIO()
    writer = csv.writer(csv_content)
    
    # 汇总
    writer.writerow(['汇总'])
    writer.writerow(['持仓本金', summary['total_base']])
    writer.writerow(['总资产', summary['total_asset']])
    writer.writerow(['累计盈亏', summary['total_profit']])
    writer.writerow(['昨日盈亏', summary['prev_profit']])
    writer.writerow(['今日涨跌', summary['today_profit']])
    writer.writerow(['清仓盈亏', summary['closed_profit']])
    writer.writerow([])
    
    # 持仓明细
    writer.writerow(['持仓明细'])
    writer.writerow(['代码', '名称', '份额', '本金', '净值', '资产', '盈亏', '盈亏%'])
    for row in holdings:
        writer.writerow(row)
    writer.writerow([])
    
    # 近期交易
    writer.writerow(['已确认交易（近7天）'])
    writer.writerow(['交易日期', '基金代码', '类型', '金额', '状态'])
    for row in trades:
        writer.writerow(row)
    
    return report, csv_content.getvalue(), nav_date_fmt

def send_email(subject, content, csv_content, date_str):
    """发送邮件"""
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = TO_EMAIL
    msg['Subject'] = subject
    
    msg.attach(MIMEText(content, 'plain', 'utf-8'))
    
    # 添加CSV附件
    attachment = MIMEBase('text', 'csv')
    attachment.set_payload(csv_content.encode('utf-8-sig'))
    encoders.encode_base64(attachment)
    attachment.add_header('Content-Disposition', 'attachment', 
                          filename=f'fund_report_{date_str}.csv')
    msg.attach(attachment)
    
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [TO_EMAIL], msg.as_string())
    
    print(f"✅ 邮件已发送到 {TO_EMAIL}")

def main():
    content, csv_content, date_str = generate_report()
    send_email(f'基金持仓报告 - {date_str}', content, csv_content, date_str)
    print("\n报告内容:")
    print(content)

if __name__ == '__main__':
    main()