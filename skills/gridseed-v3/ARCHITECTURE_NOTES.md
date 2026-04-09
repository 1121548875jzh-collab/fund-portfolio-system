# GridSeed / Fund Portfolio Architecture Notes

## Goals

- Preserve the existing snapshot-based main flow.
- Keep strategy experimentation isolated from the main portfolio system.
- Reduce drift between the main ledger and strategy state.

## Source of Truth

### Main ledger (`fund_portfolio.db`)

These fields are treated as the real portfolio truth:

- `fund_holdings.base_amount`: real accumulated principal
- `fund_holdings.shares`: real holding shares
- `fund_holdings.nav`: latest display NAV
- `fund_holdings.nav_date`: NAV date
- `fund_trades`: all pending/confirmed trade records
- `fund_nav_history`: historical NAV source

### Strategy ledger (`gridseed.db`)

These fields are strategy state, not portfolio truth:

- `strategy_positions.phase`
- `strategy_positions.step`
- `strategy_positions.last_nav`
- `strategy_positions.last_date`
- `strategy_positions.last_action`
- `strategy_positions.grid_base_nav`
- `strategy_trades`: strategy-side action history
- `grid_batches`: grid batch lifecycle

## Cached Fields To Watch

These fields currently duplicate main-ledger information and must stay aligned:

- `strategy_positions.total_cost`
- `strategy_positions.total_shares`

Current policy:
- keep them for compatibility
- validate them daily
- initialize them from `fund_holdings` when a fund first enters GridSeed

## Snapshot Rule

Do not break the existing daily snapshot logic.

Target model:

```text
previous-day snapshot = daily baseline
confirmed trades today = daily delta
strategy state = phase/step/grid state cache
```

That means:
- snapshot generation stays unchanged
- daily calculations can still use yesterday's snapshot as baseline
- GridSeed should consume baseline + confirmed deltas, instead of inventing a second portfolio truth

## New Fund Initialization Rule

When a fund first enters GridSeed monitoring:

1. create `strategy_positions`
2. read `fund_holdings.base_amount` and `fund_holdings.shares`
3. initialize `total_cost` / `total_shares`
4. set strategy-only fields (`phase`, `step`, `last_nav`, `grid_base_nav`) explicitly
5. record the initialization action in `strategy_trades` if needed

Never leave a monitored fund with:
- `fund_holdings.base_amount > 0`
- but `strategy_positions.total_cost = 0`

Available tools:
- `python3 skills/gridseed-v3/runner.py bootstrap`
  - initialize only empty strategy cache rows
- `python3 skills/gridseed-v3/runner.py bootstrap --force`
  - resync all monitored funds from `fund_holdings`

## Safety Rules

- consistency checks must be read-only by default
- auto-fix must be explicit and narrow in scope
- do not let strategy changes rewrite snapshot history
- treat `trigger_reason` as display/audit text, not the only business truth

Current repair mode:
- `python3 skills/gridseed-v3/check_consistency.py --fix-cost-cache`
- scope: only safe cache sync for `total_cost` / `total_shares`
- excludes rows with pending trades or GRID transition state

## Field Role Matrix

### Main truth fields (do not redefine in strategy logic)

- `fund_holdings.fund_code`
- `fund_holdings.fund_name`
- `fund_holdings.shares`
- `fund_holdings.base_amount`
- `fund_holdings.nav`
- `fund_holdings.nav_date`
- `fund_trades.trade_type`
- `fund_trades.amount`
- `fund_trades.status`
- `fund_trades.is_shares`

Rule:
- these are the main-ledger truth
- strategy code can read them, but should not invent a conflicting version

### Strategy state fields (owned by GridSeed)

- `strategy_positions.phase`
- `strategy_positions.step`
- `strategy_positions.last_nav`
- `strategy_positions.last_date`
- `strategy_positions.last_action`
- `strategy_positions.last_amount`
- `strategy_positions.grid_base_nav`
- `grid_batches.*`
- `strategy_trades.trigger_reason`
- `strategy_trades.status`

Rule:
- these belong to strategy behavior and can be updated by GridSeed flows
- they should not be used as the only source of portfolio truth

### Compatibility cache fields (candidate downgrade fields)

- `strategy_positions.total_cost`
- `strategy_positions.total_shares`
- `strategy_positions.grid_shares`
- `strategy_positions.grid_cost`
- `strategy_positions.grid_profit`

Current policy:
- keep for compatibility
- validate daily
- allow explicit safe repair only
- avoid using them as the first truth source when a main-ledger equivalent exists

Future direction:
- `total_cost` / `total_shares`: remain cache or derived values, not independent truth
- `grid_shares` / `grid_cost` / `grid_profit`: evaluate whether they should stay as summary cache only

### Display / audit text fields

- `strategy_positions.last_action`
- `strategy_trades.trigger_reason`
- `fund_trades.original_remark`

Rule:
- keep for readability and audit trail
- do not make them the only business discriminator if a structured field can replace them later

## Historical Semantics Backfill

Available tool:
- `python3 skills/gridseed-v3/runner.py backfill-semantics`
  - preview only, does not write
- `python3 skills/gridseed-v3/backfill_trade_semantics.py --apply`
  - applies only high-confidence mappings to empty semantic fields

Current high-confidence mappings:
- fund trades: `补投`, `月定投...`, `卖出一半份额，进入GRID`
- strategy trades: `建仓`, `Lx加仓`, `闲置唤醒`, `网格买入`, `网格卖出`, `进入网格`, `减仓进入网格`, `赎回`, `建仓期卖出`

Policy:
- only fill empty semantic fields
- do not overwrite existing structured values
- skip ambiguous free text
