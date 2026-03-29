#!/usr/bin/env python3
"""
基金持仓邮件报告发送

执行时间: 8:30
"""
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

DB_PATH = '/root/.openclaw/workspace-coder/skills/fund-portfolio/fund_portfolio.db'

# 邮件配置
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = '1121548875jzh@gmail.com'
SMTP_PASSWORD = 'vfdoetqursseoase'

def generate_report():
    """生成持仓报告"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 获取所有持仓
    cursor.execute("""
        SELECT fund_code, fund_name, shares, base_amount, nav,
               ROUND(shares * nav, 2) as asset,
               ROUND(shares * nav - base_amount, 2) as profit
        FROM fund_holdings ORDER BY fund_code
    """)
    holdings = cursor.fetchall()
    
    # 计算汇总
    cursor.execute("""
        SELECT ROUND(SUM(base_amount), 2),
               ROUND(SUM(shares * nav), 2),
               ROUND(SUM(shares * nav - base_amount), 2)
        FROM fund_holdings
    """)
    total_base, total_asset, total_profit = cursor.fetchone()
    
    conn.close()
    
    # 生成报告
    report = f"""
基金持仓核对报告 - {datetime.now().strftime('%Y-%m-%d %H:%M')}
{'='*60}

【汇总】
总本金: {total_base:.2f} 元
总资产: {total_asset:.2f} 元
总盈亏: {total_profit:.2f} 元 ({total_profit/total_base*100:.2f}%)
基金数: {len(holdings)} 只

【持仓明细】
{'-'*60}
{'代码':<8} {'名称':<24} {'份额':>8} {'本金':>8} {'净值':>6} {'资产':>8} {'盈亏':>8}
{'-'*60}
"""
    
    for code, name, shares, base, nav, asset, profit in holdings:
        name_short = name[:22] if len(name) > 22 else name
        report += f"{code:<8} {name_short:<24} {shares:>8.2f} {base:>8.2f} {nav:>6.4f} {asset:>8.2f} {profit:>8.2f}\n"
    
    report += f"{'-'*60}\n"
    
    return report

def send_email(to_addr, subject, content):
    """发送邮件"""
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = to_addr
    msg['Subject'] = subject
    
    msg.attach(MIMEText(content, 'plain', 'utf-8'))
    
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [to_addr], msg.as_string())
    
    print(f"✅ 邮件已发送到 {to_addr}")

def main():
    report = generate_report()
    send_email('lihaiye@163.com', f'基金持仓核对报告 - {datetime.now().strftime("%Y-%m-%d")}', report)
    print("\n报告内容:")
    print(report)

if __name__ == '__main__':
    main()