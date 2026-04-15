#!/usr/bin/env python3
"""
GridSeed consistency checks.

Default mode is read-only.
Optional fix mode only repairs strategy cache fields (`total_cost`,
`total_shares`) for safe rows that have no pending trades and are not in a
GRID transition window.
"""
import os
import sys
import sqlite3
from datetime import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import FUND_DB, GRID_DB, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID  # noqa: E402

COST_EPSILON = 0.01
SHARES_EPSILON = 0.0001
PENDING_WARN_DAYS = 2
PENDING_ERROR_DAYS = 3


def send_telegram(message):
    """发送 Telegram 告警。"""
    try:
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            print('[WARN] telegram not configured, skip alert')
            return False
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={'chat_id': TELEGRAM_CHAT_ID, 'text': message},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as exc:
        print(f"[WARN] telegram alert failed: {exc}")
        return False


class Reporter:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []
        self.fixes = []

    def error(self, code, message):
        self.errors.append((code, message))

    def warn(self, code, message):
        self.warnings.append((code, message))

    def add_info(self, message):
        self.info.append(message)

    def add_fix(self, message):
        self.fixes.append(message)

    def print_report(self):
        print(f"=== Consistency Check {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
        print()

        for code, message in self.errors:
            print(f"[ERROR] {code} {message}")
        for code, message in self.warnings:
            print(f"[WARN]  {code} {message}")
        for message in self.fixes:
            print(f"[FIX]   {message}")
        for message in self.info:
            print(f"[INFO]  {message}")

        print()
        print(
            f"Summary: errors={len(self.errors)} warnings={len(self.warnings)} "
            f"fixes={len(self.fixes)} info={len(self.info)}"
        )

    def exit_code(self):
        return 1 if self.errors else 0

    def build_alert_message(self):
        if not self.errors and not self.warnings:
            return None

        lines = [
            f"GridSeed 巡检告警 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"errors={len(self.errors)} warnings={len(self.warnings)}",
        ]

        for code, message in self.errors[:10]:
            lines.append(f"ERROR {code}: {message}")
        for code, message in self.warnings[:10]:
            lines.append(f"WARN {code}: {message}")

        if len(self.errors) > 10 or len(self.warnings) > 10:
            lines.append('更多详情请查看 logs/gridseed_consistency.log')

        return '\n'.join(lines)


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def age_in_days(date_str):
    dt = parse_date(date_str)
    if not dt:
        return None
    return (datetime.now().date() - dt).days


def has_pending_trade(cursor, table, fund_code):
    status = 'PENDING' if table == 'fund_trades' else 'PENDING_NAV'
    cursor.execute(
        f"SELECT 1 FROM {table} WHERE fund_code = ? AND status = ? LIMIT 1",
        (fund_code, status),
    )
    return cursor.fetchone() is not None


def is_grid_transition(phase, grid_base_nav, last_action, last_date, last_strategy_action=None):
    if phase != 'GRID' or grid_base_nav is not None:
        return False
    last_dt = parse_date(last_date)
    if last_strategy_action == 'ENTER_GRID' and last_dt:
        return (datetime.now().date() - last_dt).days <= 1
    if last_action == '进入网格' and last_dt:
        return (datetime.now().date() - last_dt).days <= 1
    return False


def sync_safe_cache_rows(fund_conn, grid_conn, reporter):
    fund_cur = fund_conn.cursor()
    grid_cur = grid_conn.cursor()

    grid_cur.execute(
        "SELECT p.fund_code, p.fund_name, p.total_cost, p.total_shares, p.phase, p.grid_base_nav, p.last_action, p.last_date, "
        "(SELECT strategy_action FROM strategy_trades t WHERE t.fund_code = p.fund_code ORDER BY id DESC LIMIT 1) AS last_strategy_action "
        "FROM strategy_positions p ORDER BY p.fund_code"
    )
    positions = grid_cur.fetchall()

    fixed = 0
    skipped = 0
    for fund_code, fund_name, total_cost, total_shares, phase, grid_base_nav, last_action, last_date, last_strategy_action in positions:
        fund_cur.execute("SELECT base_amount, shares FROM fund_holdings WHERE fund_code = ?", (fund_code,))
        holding = fund_cur.fetchone()
        if not holding:
            skipped += 1
            continue

        base_amount, shares = holding
        total_cost = total_cost or 0.0
        total_shares = total_shares or 0.0
        base_amount = base_amount or 0.0
        shares = shares or 0.0

        mismatch = abs(base_amount - total_cost) > COST_EPSILON or abs(shares - total_shares) > SHARES_EPSILON
        if not mismatch:
            skipped += 1
            continue

        if has_pending_trade(fund_cur, 'fund_trades', fund_code):
            reporter.add_info(f"skip fix {fund_code}: fund_trades has pending records")
            skipped += 1
            continue

        if has_pending_trade(grid_cur, 'strategy_trades', fund_code):
            reporter.add_info(f"skip fix {fund_code}: strategy_trades has pending_nav records")
            skipped += 1
            continue

        if is_grid_transition(phase, grid_base_nav, last_action, last_date, last_strategy_action):
            reporter.add_info(f"skip fix {fund_code}: grid transition window")
            skipped += 1
            continue

        grid_cur.execute(
            "UPDATE strategy_positions SET total_cost = ?, total_shares = ?, updated_at = ? WHERE fund_code = ?",
            (base_amount, shares, datetime.now().strftime('%Y-%m-%d %H:%M'), fund_code),
        )
        reporter.add_fix(
            f"{fund_code} {fund_name}: synced cache cost {total_cost:.2f}->{base_amount:.2f}, "
            f"shares {total_shares:.6f}->{shares:.6f}"
        )
        fixed += 1

    grid_conn.commit()
    reporter.add_info(f"fix_mode=fixed {fixed} rows, skipped {skipped} rows")


def check_cost_and_shares(fund_conn, grid_conn, reporter):
    fund_cur = fund_conn.cursor()
    grid_cur = grid_conn.cursor()

    grid_cur.execute(
        "SELECT p.fund_code, p.fund_name, p.total_cost, p.total_shares, p.phase, p.grid_base_nav, p.last_action, p.last_date, "
        "(SELECT strategy_action FROM strategy_trades t WHERE t.fund_code = p.fund_code ORDER BY id DESC LIMIT 1) AS last_strategy_action "
        "FROM strategy_positions p ORDER BY p.fund_code"
    )
    positions = grid_cur.fetchall()
    reporter.add_info(f"tracked_funds={len(positions)}")

    for fund_code, fund_name, total_cost, total_shares, phase, grid_base_nav, last_action, last_date, last_strategy_action in positions:
        fund_cur.execute("SELECT base_amount, shares FROM fund_holdings WHERE fund_code = ?", (fund_code,))
        holding = fund_cur.fetchone()
        if not holding:
            reporter.warn(fund_code, f"{fund_name}: missing in fund_holdings")
            continue

        base_amount, shares = holding
        total_cost = total_cost or 0.0
        total_shares = total_shares or 0.0
        base_amount = base_amount or 0.0
        shares = shares or 0.0

        if abs(base_amount - total_cost) > COST_EPSILON:
            reporter.error(fund_code, f"{fund_name}: cost mismatch fund={base_amount:.2f} grid={total_cost:.2f}")
        if abs(shares - total_shares) > SHARES_EPSILON:
            reporter.error(fund_code, f"{fund_name}: shares mismatch fund={shares:.6f} grid={total_shares:.6f}")
        if base_amount > 0 and total_cost == 0:
            reporter.error(fund_code, f"{fund_name}: uninitialized total_cost with active holding")

        if phase == 'GRID' and grid_base_nav is None:
            if is_grid_transition(phase, grid_base_nav, last_action, last_date, last_strategy_action):
                reporter.add_info(f"{fund_code} pending grid_base_nav is tolerated during transition")
            else:
                reporter.error(fund_code, f"{fund_name}: phase=GRID but grid_base_nav is NULL")

        if phase == 'ACCUMULATION' and grid_base_nav is not None:
            reporter.warn(fund_code, f"{fund_name}: phase=ACCUMULATION but grid_base_nav={grid_base_nav}")


def check_pending_trades(fund_conn, grid_conn, reporter):
    fund_cur = fund_conn.cursor()
    grid_cur = grid_conn.cursor()

    fund_cur.execute("SELECT id, fund_code, trade_date, trade_type FROM fund_trades WHERE status = 'PENDING' ORDER BY trade_date")
    fund_pending = fund_cur.fetchall()
    reporter.add_info(f"fund_pending={len(fund_pending)}")

    for trade_id, fund_code, trade_date, trade_type in fund_pending:
        age = age_in_days(trade_date)
        if age is None:
            reporter.warn(fund_code, f"fund_trades id={trade_id}: invalid trade_date={trade_date}")
            continue
        if age >= PENDING_ERROR_DAYS:
            reporter.error(fund_code, f"fund_trades id={trade_id}: {trade_type} pending for {age} days")
        elif age >= PENDING_WARN_DAYS:
            reporter.warn(fund_code, f"fund_trades id={trade_id}: {trade_type} pending for {age} days")

    grid_cur.execute(
        "SELECT id, fund_code, trade_date, trade_type, trigger_reason FROM strategy_trades WHERE status = 'PENDING_NAV' ORDER BY trade_date"
    )
    grid_pending = grid_cur.fetchall()
    reporter.add_info(f"grid_pending_nav={len(grid_pending)}")

    for trade_id, fund_code, trade_date, trade_type, trigger_reason in grid_pending:
        age = age_in_days(trade_date)
        if age is None:
            reporter.warn(fund_code, f"strategy_trades id={trade_id}: invalid trade_date={trade_date}")
            continue
        if age >= PENDING_ERROR_DAYS:
            reporter.error(fund_code, f"strategy_trades id={trade_id}: {trigger_reason}/{trade_type} pending_nav for {age} days")
        elif age >= PENDING_WARN_DAYS:
            reporter.warn(fund_code, f"strategy_trades id={trade_id}: {trigger_reason}/{trade_type} pending_nav for {age} days")


def check_position_coverage(fund_conn, grid_conn, reporter):
    fund_cur = fund_conn.cursor()
    grid_cur = grid_conn.cursor()

    grid_cur.execute("SELECT fund_code FROM strategy_positions")
    tracked = {row[0] for row in grid_cur.fetchall()}

    fund_cur.execute("SELECT fund_code FROM fund_holdings WHERE shares > 0")
    active_holdings = [row[0] for row in fund_cur.fetchall()]
    tracked_active = sum(1 for fund_code in active_holdings if fund_code in tracked)
    reporter.add_info(f"active_holdings={len(active_holdings)} tracked_active_holdings={tracked_active}")


def main():
    fix_cost_cache = '--fix-cost-cache' in sys.argv[1:]
    reporter = Reporter()

    if not os.path.exists(FUND_DB):
        print(f"FUND_DB not found: {FUND_DB}")
        return 1
    if not os.path.exists(GRID_DB):
        print(f"GRID_DB not found: {GRID_DB}")
        return 1

    fund_conn = sqlite3.connect(FUND_DB)
    grid_conn = sqlite3.connect(GRID_DB)

    try:
        if fix_cost_cache:
            sync_safe_cache_rows(fund_conn, grid_conn, reporter)
        check_cost_and_shares(fund_conn, grid_conn, reporter)
        check_pending_trades(fund_conn, grid_conn, reporter)
        check_position_coverage(fund_conn, grid_conn, reporter)
        reporter.print_report()
        alert_message = reporter.build_alert_message()
        if alert_message:
            send_telegram(alert_message)
        return reporter.exit_code()
    finally:
        fund_conn.close()
        grid_conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
