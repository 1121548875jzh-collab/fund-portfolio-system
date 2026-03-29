# fund-portfolio - 基金持仓管理系统

完整的基金持仓、盈亏计算、交易管理、定投自动化解决方案。

---

## 核心计算规则

### 1. 今日涨跌计算

```
今日涨跌 = 份额 × (今日净值 - 昨日净值)
```

**关键点**：
- 份额用快照中的份额
- 净值从 Tushare 获取
- QDII 基金的 T+1 延迟已在净值数据中体现，无需额外处理

### 2. QDII 基金处理

**T+1 延迟规则**：
- Tushare 返回的 QDII 净值比普通基金晚一天
- 例如：3/27 普通基金有 3/27 净值，QDII 只有 3/26 净值

**计算涨跌时**：
```python
if is_qdii:
    # 用 3/26 净值 - 3/25 净值
    daily = shares * (nav_26 - nav_25)
else:
    # 用 3/27 净值 - 3/26 净值
    daily = shares * (nav_27 - nav_26)
```

**Tushare 净值更新时间**：隔日早上 8:20 后

### 3. 报告日期规则

| 字段 | 规则 |
|:---|:---|
| 报告日期 | 净值日期，不是运行日期 |
| 昨日盈亏 | 从前一天快照读取"当日盈亏" |
| 今日涨跌 | 当天计算的涨跌 |

### 4. 份额计算

```
买入份额 = 买入金额 / 确认日净值
```

**确认规则**：
- 普通基金：T+1 确认，用 T 日净值
- QDII 基金：T+2 确认，用 T 日净值

### 5. 分红处理

```
当日涨跌 = 净值涨跌 + 分红金额
```

分红单独记录在 `fund_dividends` 表，计入当日收益。

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

## 定投配置（11只）

| 基金 | 名称 | 周一 | 周二 | 周三 | 周四 |
|:---|:---|:---:|:---:|:---:|:---:|
| 017437 | 华宝纳斯达克精选(QDII)C | 30 | - | 30 | - |
| 017091 | 景顺长城纳斯达克科技(QDII)A | 25 | - | 25 | - |
| 017641 | 摩根标普500人民币A | 25 | - | 25 | - |
| 002963 | 易方达黄金ETF联接C | - | 25 | - | 25 |
| 003958 | 安信量化沪深300增强C | - | 25 | - | 25 |
| 009982 | 万家创业板指数增强C | - | 30 | - | 30 |
| 012349 | 天弘恒生科技ETF联接C | - | 30 | - | 30 |
| 016441 | 华夏中证红利质量ETF联接C | - | 60 | - | - |
| 021909 | 鹏华上证科创板50增强ETF联接C | - | - | - | 50 |
| 022431 | 华夏中证A500ETF联接C | - | 30 | - | 30 |
| 023920 | 国泰富时中国A股自由现金流C | - | 50 | - | - |

**周定投**: 750元

---

## 数据表结构

| 表 | 作用 |
|:---|:---|
| fund_holdings | 当前持仓 |
| fund_trades | 交易记录 |
| fund_nav_history | 净值历史 |
| daily_fund_snapshot | 每日快照 |
| dca_config | 定投配置 |
| fund_dividends | 分红记录 |
| closed_position_profit | 清仓盈亏 |

---

## 邮件报告格式

### 正文内容

```
基金持仓报告 - YYYY-MM-DD

[汇总]
------------------------
持仓本金: X,XXX.XX 元
总资产: X,XXX.XX 元
累计盈亏: ±XXX.XX 元 (±X.XX%)
昨日盈亏: ±XXX.XX 元
今日涨跌: ±XXX.XX 元
基准盈亏: -389.14 元
清仓盈亏: ±XX.XX 元

[近一周涨跌]
------------------------
涨幅前3:
  CODE NAME +X.XX%
跌幅前3:
  CODE NAME -X.XX%

[定投统计（已确认）]
------------------------
本周定投: XXX.XX 元
本月定投: XXX.XX 元
```

### CSV 附件内容

- 汇总
- 持仓明细（含涨跌幅：昨日、近一周、近一月）
- 已确认交易（近7天）

---

## 常见问题

### Q: 为什么计算涨跌和实际有差异？

A: 可能原因：
1. 手续费扣除
2. 份额精度（小数点后两位）
3. 净值更新时间差

### Q: QDII 净值为什么显示昨天的？

A: Tushare 的 QDII 净值有 T+1 延迟，这是正常的。

### Q: 分红怎么处理？

A: 分红金额计入当日收益，单独记录在 fund_dividends 表。

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

# 发送邮件报告
python3 skills/fund-portfolio/fund_portfolio_email.py
```

---

## 相关文档

- **TECH_SPEC.md** - 完整技术规范
- **GridSeed/SKILL.md** - GridSeed 策略规则