#!/usr/bin/env python3
"""
同步脚本：将 fund_holdings 中的 nav 和 nav_date 更新为 fund_nav_history 中的最新值
"""
import sqlite3
import os
import sys

# 添加父目录到路径，支持导入config
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import FUND_DB

def sync_nav():
    if not os.path.exists(FUND_DB):
        print(f"数据库不存在: {FUND_DB}")
        return

    conn = sqlite3.connect(FUND_DB)
    cursor = conn.cursor()

    print("=== 开始同步 fund_holdings 中的净值 ===")

    # 获取所有持仓
    cursor.execute("SELECT fund_code, fund_name, nav, nav_date FROM fund_holdings")
    holdings = cursor.fetchall()

    for fund_code, fund_name, old_nav, old_date in holdings:
        # 获取该基金在历史表中的最新净值
        cursor.execute('''
            SELECT nav, nav_date FROM fund_nav_history 
            WHERE fund_code = ? 
            ORDER BY nav_date DESC LIMIT 1
        ''', (fund_code,))
        latest = cursor.fetchone()

        if latest:
            new_nav, new_date = latest
            if old_nav != new_nav or old_date != new_date:
                cursor.execute('''
                    UPDATE fund_holdings 
                    SET nav = ?, nav_date = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE fund_code = ?
                ''', (new_nav, new_date, fund_code))
                print(f"  ✅ 更新 {fund_code} ({fund_name}): {old_nav} ({old_date}) -> {new_nav} ({new_date})")
            else:
                print(f"  - {fund_code} ({fund_name}): 已是最新 {new_nav}")
        else:
            print(f"  ⚠️ {fund_code} ({fund_name}): 历史表中未找到净值数据")

    conn.commit()
    conn.close()
    print("=== 同步完成 ===")

if __name__ == '__main__':
    sync_nav()
