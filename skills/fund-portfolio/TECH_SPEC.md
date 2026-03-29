# 基金持仓管理系统 - 技术规范

## 一、系统架构

```
+-------------------------------------------------------------+
|                    基金持仓管理系统                          |
+-------------------------------------------------------------+
|  定时任务                                                    |
|  |-- 8:20  daily_update.py    净值更新+快照生成             |
|  |-- 8:23  dca_runner.py      定投执行                      |
|  |-- 8:25  fund_trade.py      交易确认                      |
|  |-- 8:26  sync_trades.py     GridSeed同步                  |
|  |-- 8:30  fund_portfolio_email.py  邮件报告               |
|  +-- 8:35  daily_reminder.sh  GridSeed提醒                  |
+-------------------------------------------------------------+
```

## 二、计算公式

### 1. 当日涨跌

```python
# 普通基金
daily_profit = shares * (nav_today - nav_yesterday)

# QDII 基金 (T+1 延迟已在净值中体现)
daily_profit = shares * (nav_today - nav_yesterday)
```

### 2. 累计盈亏

```python
total_profit = total_asset - total_base
```

### 3. 盈亏比例

```python
profit_pct = total_profit / total_base * 100
```

### 4. 份额计算

```python
shares = amount / nav  # 买入金额 / 确认日净值
```

---

## 三、QDII 基金处理

### QDII 基金列表

```python
QDII_FUNDS = ['012062', '017641', '017437', '017091']
```

### T+1 延迟说明

| 基金类型 | Tushare 净值日期 | 计算涨跌 |
|:---|:---|:---|
| 普通基金 | 当天 | (当天净值 - 昨天净值) |
| QDII基金 | 昨天净值 | (昨天净值 - 前天净值) |

**示例** (3/27 报告):
- 普通基金: `shares * (nav_27 - nav_26)`
- QDII基金: `shares * (nav_26 - nav_25)`

---

## 四、数据库设计

### fund_holdings (当前持仓)

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| fund_code | TEXT | 基金代码 (主键) |
| fund_name | TEXT | 基金名称 |
| shares | REAL | 份额 |
| base_amount | REAL | 本金 |
| nav | REAL | 最新净值 |
| nav_date | TEXT | 净值日期 |

### fund_trades (交易记录)

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| id | INTEGER | 主键 |
| trade_date | TEXT | 交易日期 |
| trade_type | TEXT | BUY/SELL |
| amount | REAL | 金额 |
| fund_code | TEXT | 基金代码 |
| status | TEXT | PENDING/CONFIRMED |
| is_qdii | INTEGER | 是否QDII |
| confirm_date | TEXT | 确认日期 |

### fund_nav_history (净值历史)

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| fund_code | TEXT | 基金代码 |
| nav_date | TEXT | 净值日期 (YYYYMMDD) |
| nav | REAL | 净值 |

### daily_fund_snapshot (每日快照)

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| date | TEXT | 快照日期 |
| fund_code | TEXT | 基金代码 |
| fund_name | TEXT | 基金名称 |
| shares | REAL | 份额 |
| base_amount | REAL | 本金 |
| asset_value | REAL | 资产 |
| profit | REAL | 累计盈亏 |
| nav | REAL | 净值 |
| daily_profit | REAL | 当日盈亏 |

### fund_dividends (分红记录)

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| id | INTEGER | 主键 |
| fund_code | TEXT | 基金代码 |
| dividend_date | TEXT | 分红日期 |
| amount | REAL | 分红金额 |

---

## 五、API 集成

### Tushare

```python
TS_TOKEN = 'your_token'
pro = ts.pro_api(TS_TOKEN)

# 获取净值
df = pro.fund_nav(ts_code='000001.OF')

# 返回字段
# nav_date: 净值日期 (YYYYMMDD)
# unit_nav: 单位净值
```

### Tushare 净值更新时间

- **实际更新时间**: 隔日早上 8:20 后
- **不是**: 当天晚上

---

## 六、邮件格式

### 正文

```
基金持仓报告 - YYYY-MM-DD

[汇总]
持仓本金: X,XXX.XX 元
总资产: X,XXX.XX 元
累计盈亏: ±XXX.XX 元 (±X.XX%)
昨日盈亏: ±XXX.XX 元
今日涨跌: ±XXX.XX 元
基准盈亏(3/14): -389.14 元
清仓盈亏: ±XX.XX 元

[近一周涨跌]
涨幅前3: ...
跌幅前3: ...

[定投统计（已确认）]
本周定投: XXX.XX 元
本月定投: XXX.XX 元
```

### CSV 附件

```csv
[汇总]
持仓本金,XXX
总资产,XXX
...

[持仓明细]
代码,名称,净值,份额,本金,资产,盈亏,当日盈亏,昨日涨跌,近一周涨跌,近一月涨跌
...

[已确认交易（近7天）]
确认日期,代码,操作,数量
...
```

---

## 七、错误处理

### sync_trades.py

```python
# 计算前验证
if nav is None:
    failed.append({'fund_code': code, 'reason': '无法获取净值'})
    continue

# 汇总报告
print(f"✅ 同步成功: X 笔")
if failed:
    print(f"❌ 同步失败: Y 笔")
    for f in failed:
        print(f"  {f['fund_code']}: {f['reason']}")
```

### daily_update.py

```python
# 事务处理
try:
    # 操作
    conn.commit()
except Exception as e:
    conn.rollback()
    print(f"错误: {e}")
finally:
    conn.close()
```

---

## 八、常见问题排查

### Q: 涨跌计算和实际不一致

1. 检查份额是否正确
2. 检查净值日期是否匹配
3. QDII 是否用了正确的净值
4. 是否有分红

### Q: 快照数据缺失

1. 检查定时任务是否执行
2. 检查日志文件
3. 验证 Tushare API 是否正常

### Q: 份额不对

1. 检查交易记录是否确认
2. 验证确认时用的净值
3. 检查是否有遗漏的交易