import sqlite3
import os

def check_db(db_path):
    if not os.path.exists(db_path):
        print(f"File not found: {db_path}")
        return
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    print(f"\n--- {db_path} ---")
    print(f"Tables: {tables}")
    for t in tables:
        cursor.execute(f"PRAGMA table_info({t})")
        cols = [c[1] for c in cursor.fetchall()]
        print(f"  {t}: {cols}")
    conn.close()

check_db('d:/workspace/fund-portfolio-system/skills/fund-portfolio/fund_portfolio.db')
check_db('d:/workspace/fund-portfolio-system/skills/gridseed-v3/data/gridseed.db')
