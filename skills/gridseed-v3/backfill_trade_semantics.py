#!/usr/bin/env python3
"""Backfill structured trade semantics for historical records.

Safe defaults:
- only fills rows where semantic fields are empty
- only applies high-confidence mappings
- supports preview mode by default
"""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import FUND_DB, GRID_DB  # noqa: E402


def classify_fund_trade(text):
    text = (text or '').strip()
    if not text:
        return None
    if '补投' in text:
        return ('CATCH_UP', 'NONE', None)
    if '月定投' in text:
        return ('DCA', 'NONE', None)
    if text == '卖出一半份额，进入GRID':
        return ('STRATEGY', 'ENTER_GRID', None)
    return None


def classify_strategy_trade(text):
    text = (text or '').strip()
    if not text:
        return None
    if text in ('建仓', '初始建仓'):
        return ('STRATEGY', 'ACCUM_BUY', 'L1')
    if text == '闲置唤醒':
        return ('IDLE_WAKE', 'IDLE_WAKE', None)
    if text == '网格买入':
        return ('GRID', 'GRID_BUY', None)
    if text == '网格卖出':
        return ('GRID', 'GRID_SELL', None)
    if text in ('进入网格', '减仓进入网格', '赎回'):
        return ('STRATEGY', 'ENTER_GRID', None)
    if text == '建仓期卖出':
        return ('STRATEGY', 'ACCUM_SELL', None)
    if text.startswith('L') and text.endswith('加仓'):
        step_label = text.split('加仓')[0]
        return ('STRATEGY', 'ACCUM_BUY', step_label)
    return None


def backfill_table(conn, table, text_col, classifier, preview=True):
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, {text_col}, trade_source, strategy_action, step_label FROM {table} "
        "WHERE COALESCE(trade_source, '') = '' OR COALESCE(strategy_action, '') = '' OR COALESCE(step_label, '') = '' "
        f"ORDER BY id"
    )
    rows = cur.fetchall()

    matched = 0
    updated = 0
    skipped = 0

    for row_id, text, trade_source, strategy_action, step_label in rows:
        classified = classifier(text)
        if not classified:
            skipped += 1
            continue

        matched += 1
        new_source, new_action, new_step = classified
        final_source = trade_source or new_source
        final_action = strategy_action or new_action
        final_step = step_label or new_step

        if preview:
            print(f"[PREVIEW] {table} id={row_id} text={text!r} -> source={final_source}, action={final_action}, step={final_step}")
            continue

        cur.execute(
            f"UPDATE {table} SET trade_source = ?, strategy_action = ?, step_label = ? WHERE id = ?",
            (final_source, final_action, final_step, row_id),
        )
        updated += 1

    if not preview:
        conn.commit()

    return matched, updated, skipped


def main():
    apply_changes = '--apply' in sys.argv[1:]
    preview = not apply_changes

    fund_conn = sqlite3.connect(FUND_DB)
    grid_conn = sqlite3.connect(GRID_DB)
    try:
        print('=== Backfill Trade Semantics ===')
        matched, updated, skipped = backfill_table(
            fund_conn, 'fund_trades', 'original_remark', classify_fund_trade, preview=preview
        )
        print(f'fund_trades: matched={matched} updated={updated} skipped={skipped}')

        matched, updated, skipped = backfill_table(
            grid_conn, 'strategy_trades', 'trigger_reason', classify_strategy_trade, preview=preview
        )
        print(f'strategy_trades: matched={matched} updated={updated} skipped={skipped}')
        return 0
    finally:
        fund_conn.close()
        grid_conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
