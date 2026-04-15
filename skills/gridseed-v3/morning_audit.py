#!/usr/bin/env python3
"""每日巡检：先修安全缓存，再做一致性检查；仅异常时发提醒。"""
import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CHECK_SCRIPT = os.path.join(BASE_DIR, 'skills', 'gridseed-v3', 'check_consistency.py')


def run(cmd):
    return subprocess.run(cmd, cwd=BASE_DIR, text=True)


def main():
    # 先做安全级别的缓存对齐，避免已知的 strategy_positions 缓存滞后造成误报。
    fix = run(['python3', CHECK_SCRIPT, '--fix-cost-cache'])
    if fix.returncode != 0:
        return fix.returncode

    verify = run(['python3', CHECK_SCRIPT])
    return verify.returncode


if __name__ == '__main__':
    raise SystemExit(main())
