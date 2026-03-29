# fund-portfolio - 基金持仓管理系统

完整的基金持仓、盈亏计算、交易管理、定投自动化解决方案。

---

## 核心规则

### 1. 今日涨跌计算

```
今日涨跌 = 份额 × (最新净值 - 第二新净值)
```

**统一逻辑：** 所有基金（包括QDII）都用最新净值减第二新净值

### 2. 报告日期规则

| 字段 | 规则 |
|:---|:---|
| 报告日期 | 净值最新日期，不是运行日期 |
| 昨日盈亏 | 从前一天报告读取"今日涨跌" |
| 今日涨跌 | 当天计算的涨跌 |

### 3. 净值字段

```
使用 unit_nav（单位净值）
不用 adj_nav（复权净值）
```

### 4. T+1 确认规则

- 今天买入 → 明天确认
- 确认时 Tushare 已有交易日净值（隔日早上更新）

### 5. Tushare 净值更新时间

```
隔日早上 8:20 后更新
```

---

## 定时任务

| 时间 | 任务 | 脚本 |
|:---|:---|:---|
| 8:20 | 净值更新+快照 | daily_update.py |
| 8:23 | 定投执行 | dca_runner.py |
| 8:25 | 交易确认 | fund_trade.py confirm |
| 8:26 | GridSeed同步 | sync_trades.py |
| 8:30 | 邮件报告 | fund_portfolio_email.py |
| 8:35 | GridSeed提醒 | daily_reminder.sh |

---

## 定投配置（12只）

| 基金 | 周一 | 周二 | 周三 | 周四 |
|:---|:---:|:---:|:---:|:---:|
| 017437 | 30 | - | 30 | - |
| 017091 | 25 | - | 25 | - |
| 017641 | 25 | - | 25 | - |
| 002963 | - | 25 | - | 25 |
| 003958 | - | 25 | - | 25 |
| 009982 | - | 30 | - | 30 |
| 012349 | - | 30 | - | 30 |
| 016441 | - | 60 | - | - |
| 021909 | - | - | - | 50 |
| 022431 | - | 30 | - | 30 |
| 023920 | - | 50 | - | - |

**周定投**: 750元

---

## 数据表职责

| 表 | 作用 |
|:---|:---|
| fund_holdings | 当前持仓 |
| fund_trades | 交易记录 |
| fund_nav_history | 净值历史 |
| daily_fund_snapshot | 每日快照 |
| dca_config | 定投配置 |
| closed_position_profit | 清仓盈亏 |

---

## 使用方式

```bash
# 初始化数据库
python3 skills/fund-portfolio/init_db.py

# 定投执行
python3 skills/fund-portfolio/dca_runner.py

# 净值更新+快照
python3 skills/fund-portfolio/daily_update.py

# GridSeed 同步
python3 skills/gridseed-v3/sync_trades.py

# GridSeed 检查
python3 skills/gridseed-v3/runner.py check
```

---

## 相关文档

- **TECH_SPEC.md** - 完整技术规范（必读）