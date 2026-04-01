# Changelog

## [V3.1] - 2026-04-01

### Added
- **Security**: Added support for `.env` and `os.environ` variables in `config.py`. Sensitive credentials (Tushare Token, SMTP, Telegram) are now de-coupled from the code.
- **Manual Control**: Enhanced `strategy.py record` command with optional `reason` parameter (e.g., "闲置唤醒") to bypass automated step increments.

### Fixed
- **Grid Loop Closure (P0)**: Fixed critical bug where grid buy/sell batches were not being recorded when using estimated NAVs during intra-day manual operations.
- **Data Integrity**: Modified `record_operation` to defer `grid_batches` updates until real NAV is confirmed by `update_pending_navs` the following morning.
- **Type Stability**: Fixed `TypeError` in `record_operation` when no NAV was provided and fallback returned a tuple.
- **Phase Logic**: Fixed `sync_trades.py` to prioritize `GRID` phase logic (grid buying/selling) over accumulation step increments when a fund has an established grid base.
- **Idle Wake-up**: Automated `step` preservation for "Idle Wake-up" actions, preventing manual database corrections after each wake-up.

### Optimized
- **Execution Flow**: Separation of *Intra-day Estimation* and *Next-day Confirmation* ensures 100% precision in cost basis and profit tracking.
- **Configuration**: Centralized path management with OS-agnostic auto-detection.
