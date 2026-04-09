#!/usr/bin/env python3
"""
Bootstrap GridSeed position state from the main portfolio ledger.

This keeps strategy_positions.total_cost / total_shares aligned with
fund_holdings when a monitored fund is first initialized or needs repair.
"""
import os
import sys
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import FUND_DB, GRID_DB  # noqa: E402


def bootstrap_position(fund_cursor, grid_cursor, fund_code, only_if_empty=True):
    fund_cursor.execute(
        "SELECT fund_name, base_amount, shares, nav_date FROM fund_holdings WHERE fund_code = ?",
        (fund_code,),
    )
    holding = fund_cursor.fetchone()
    if not holding:
        return False, f"{fund_code}: missing in fund_holdings"

    fund_name, base_amount, shares, nav_date = holding
    base_amount = base_amount or 0.0
    shares = shares or 0.0

    grid_cursor.execute(
        "SELECT fund_name, total_cost, total_shares FROM strategy_positions WHERE fund_code = ?",
        (fund_code,),
    )
    pos = grid_cursor.fetchone()
    if not pos:
        return False, f"{fund_code}: missing in strategy_positions"

    _, total_cost, total_shares = pos
    total_cost = total_cost or 0.0
    total_shares = total_shares or 0.0

    if only_if_empty and not (total_cost == 0 and total_shares == 0):
        return False, f"{fund_code}: skipped, already initialized"

    grid_cursor.execute(
        """
        UPDATE strategy_positions
        SET fund_name = ?,
            total_cost = ?,
            total_shares = ?,
            updated_at = ?
        WHERE fund_code = ?
        """,
        (fund_name, base_amount, shares, datetime.now().strftime('%Y-%m-%d %H:%M'), fund_code),
    )
    return True, f"{fund_code}: bootstrap cost={base_amount:.2f} shares={shares:.6f}"


def bootstrap_all(only_if_empty=True):
    if not os.path.exists(FUND_DB) or not os.path.exists(GRID_DB):
        print("数据库不存在")
        return 1

    fund_conn = sqlite3.connect(FUND_DB)
    grid_conn = sqlite3.connect(GRID_DB)
    fund_cursor = fund_conn.cursor()
    grid_cursor = grid_conn.cursor()

    grid_cursor.execute("SELECT fund_code FROM strategy_positions ORDER BY fund_code")
    fund_codes = [row[0] for row in grid_cursor.fetchall()]

    updated = 0
    skipped = 0
    failed = 0
    for fund_code in fund_codes:
        ok, message = bootstrap_position(fund_cursor, grid_cursor, fund_code, only_if_empty=only_if_empty)
        print(message)
        if ok:
            updated += 1
        elif 'skipped' in message:
            skipped += 1
        else:
            failed += 1

    grid_conn.commit()
    fund_conn.close()
    grid_conn.close()

    print()
    print(f"Summary: updated={updated} skipped={skipped} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    force = '--force' in sys.argv
    raise SystemExit(bootstrap_all(only_if_empty=not force))
