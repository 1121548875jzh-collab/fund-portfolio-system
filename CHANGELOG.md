# Changelog

## [V3.3] - 2026-04-07

### Fixed
- **Historical Sync (P1)**: Modified `sync_trades.py` to automatically synchronize `total_cost` and `total_shares` from `fund_holdings` when a new fund joins GridSeed. This resolves data inconsistencies for newly added funds.
- **Holiday DCA Handling (P1)**: Rewrote `dca_runner.py` to incorporate A-share trading calendar validation via Tushare API.
- **Automatic Catch-up**: Implemented automatic DCA catch-up logic for holidays, ensuring missed investments during A-share market closures are executed on the first subsequent trading day.

## [V3.2] - 2026-04-02

### Added
- **Investment Strategy**: Integrated a standardized monitoring and execution rule based on **BIAS-250** and **Drawdown** (3-year rolling window).
- **Fund Profiling**: Added risk classification for 27 key funds (High, Medium, and Low volatility) in `config.py` with custom thresholds.
- **Strategy Monitor**: New `strategy_monitor.py` module for automated calculation of technical indicators and signal matching.
- **Enhanced Reporting**: Updated `send_email.py` and `daily_update.py` to include real-time investment recommendations ("補倉区", "大額区", etc.) in both email bodies and CSV attachments.

### Optimized
- **Decision Logic**: Implemented "Double Confirmation" logic (BIAS + Drawdown) to prevent premature capital depletion during extended market downturns.


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
