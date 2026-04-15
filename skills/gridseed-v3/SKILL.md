# GridSeed V3.0 - 网格定投策略系统

## 核心规则

### 阶段判断

```python
if grid_base_nav is None:
    phase = 'ACCUMULATION'  # 建仓阶段
else:
    phase = 'GRID'  # 网格阶段
```

### 建仓阶段规则

| step | 名称 | 触发条件 | 操作 |
|:---:|:---|:---|:---|
| 0 | L1 | 跌幅 ≥ 3% | 加仓 15% |
| 1 | L2 | 跌幅 ≥ 3% | 加仓 15% |
| 2 | L3 | 跌幅 ≥ 3% | 加仓 15% |
| 3 | L4 | 跌幅 ≥ 3% | 加仓 15% |
| 4 | L5 | 跌幅 ≥ 5% | 加仓 30% |
| 5 | L6 | 跌幅 ≥ 5% | 加仓 30% |
| 6 | — | — | 不再加仓 |

### 网格阶段规则

| 触发条件 | 操作 |
|:---|:---|
| 跌幅 ≥ 3% | 买入 100元 |
| 涨幅 ≥ 10% | 卖出 |

### 闲置唤醒规则

| 条件 | 操作 |
|:---|:---|
| 10 个交易日无操作 | 按动态金额提醒加仓 |

**平衡版金额公式**

```python
T = 3000
H = clip(sqrt(T / current_value), 0.4, 1.6)
r = (current_nav - last_nav) / last_nav
mid_pos = (current_nav - low_250) / (high_250 - low_250)

if r <= -0.03:
    P1 = 1.2
elif r <= 0.03:
    P1 = 1.0
elif r <= 0.06:
    P1 = 0.8
elif r <= 0.10:
    P1 = 0.6
else:
    P1 = 0.4

if mid_pos <= 0.35:
    P2 = 1.2
elif mid_pos <= 0.65:
    P2 = 1.0
elif mid_pos <= 0.85:
    P2 = 0.7
else:
    P2 = 0.4

idle_amount = clip(100 * H * P1 * P2, 20, 150)
idle_amount = round_to_step(idle_amount, 10)
```

**执行口径**
- 最终金额按 `10元` 步进取整，便于实际下单

**规则解释**
- 当前持仓越小，闲置唤醒金额越大
- 当前价格较上次监控点涨幅越高，闲置唤醒金额越小，但不再直接归零
- 若基金在近 250 个净值点区间仍处中位或低位，可保留小额或正常闲置唤醒
- 若基金在近 250 个净值点区间已偏高，则进一步缩量
- `GRID` 阶段不参与闲置唤醒
- 闲置唤醒不增加 `step`

---

## 实时估算判断（下午盘前）

### 数据来源

| 项目 | 来源 | 说明 |
|:---|:---|:---|
| 监控点净值 | `strategy_positions.last_nav` | 上次操作后的净值基准 |
| 估算净值 | 用户提供 | 支付宝/天天基金估算 |

### 计算公式

```python
涨跌幅 = (估算净值 - 监控点净值) / 监控点净值 × 100%
```

**⚠️ 重要：用监控点净值，不是昨日净值！**

### 判断流程

```
用户提供估算 → 对比监控点净值 → 计算涨跌幅 → 检查阈值 → 返回操作建议
```

### 触发条件

| 阶段 | 涨跌方向 | 阈值 | 操作 |
|:---|:---|:---|:---|
| 建仓L1-L4 | 跌 | ≥3% | 加仓15% |
| 建仓L5-L6 | 跌 | ≥5% | 加仓30% |
| 网格期 | 跌 | ≥3% | 买入100元 |
| 建仓期/网格期 | 涨 | ≥10% | 卖出 |

### 示例

```
基金: 015790 永赢高端装备
阶段: 建仓L1
监控点净值: 1.3398
估算净值: 1.4045

涨跌幅 = (1.4045 - 1.3398) / 1.3398 = +4.83%

判断: 涨幅<10%，不触发卖出
```

---

## 核心计算公式

### 跌幅计算

```python
drawdown = (current_nav - last_nav) / last_nav
```

- `current_nav`: 当前净值/估算净值
- `last_nav`: 监控点净值（最后操作时的净值）

### 加仓金额

```python
# L1-L4
add_amount = current_asset * 0.15

# L5-L6
add_amount = current_asset * 0.30

# 网格
add_amount = 100
```

---

## 状态更新

### 交易类型识别

通过 `trigger_reason` 字段区分：

| trigger_reason | 说明 | step 变化 |
|:---|:---|:---:|
| L1加仓/L2加仓/... | 建仓加仓 | +1 |
| 网格买入 | 网格阶段 | 不变 |
| 闲置唤醒 | 独立规则 | 不变 |

### 更新规则

```python
if 'L' in trigger_reason and '加仓' in trigger_reason:
    new_step = old_step + 1
elif trigger_reason in ['网格买入', '闲置唤醒']:
    new_step = old_step
```

---

## 监控基金 (15只)

| 基金代码 | 基金名称 |
|:---|:---|
| 007882 | 易方达沪深300非银行金融ETF联接C |
| 007040 | 新疆前海联合泳隆灵活配置混合 |
| 001665 | 平安鑫安混合C |
| 020629 | 汇添富上证科创板芯片ETF联接C |
| 018463 | 德邦稳盈增长灵活配置C |
| 003625 | 创金合信资源主题精选股票C |
| 015790 | 永赢高端装备智选混合发起C |
| 011957 | 鹏华新能源精选混合C |
| 009982 | 万家创业板指数增强C |
| 018125 | 永赢先进制造智选混合发起C |
| 018957 | 中航机遇领航混合型 |
| 019924 | 华泰柏瑞中证2000指数增强C |
| 019261 | 富国恒生港股通高股息低波动C |
| 021909 | 鹏华上证科创板50增强ETF联接C |
| 022287 | 长城医药产业精选混合C |
| 016874 | 广发远见智选混合C |
| 022287 | 长城医药产业精选混合C |

---

## 主账同步规则

- `strategy_trades / strategy_positions` 是策略账，负责阶段、step、监控点与策略动作。
- `fund_trades / fund_holdings` 是基金主账，负责最终持仓、成本和报表展示。
- 策略交易一旦 `CONFIRMED`，必须同步写入基金主账；只写策略账、不写主账，视为异常。
- 买入通常按金额驱动；卖出若用户下达的是份额，则按份额驱动，正式净值出来后仅回算金额。
- 用户提供平台实际份额、收益或成本时，以用户实际值为准，可直接修正主账与策略账。
- 每日 9:00 必跑巡检：先对齐安全缓存，再检查持仓分叉、长时间 pending、GRID 状态异常；出现 `error/warn` 即提醒。
- `daily_fund_snapshot` 是展示快照，不作为手工修正后的唯一真值；真实口径以 `fund_holdings / fund_trades` 为准。

## 数据库设计

### strategy_positions

| 字段 | 说明 |
|:---|:---|
| fund_code | 基金代码 |
| fund_name | 基金名称 |
| phase | ACCUMULATION/GRID |
| step | 加仓次数 (0-6) |
| total_cost | 总成本 |
| total_shares | 总份额 |
| last_nav | 基准净值 |
| last_date | 最后操作日期 |
| grid_base_nav | 网格基准净值 |

### strategy_trades

| 字段 | 说明 |
|:---|:---|
| fund_code | 基金代码 |
| trade_date | 交易日期 |
| trade_type | BUY/SELL |
| amount | 金额 |
| nav | 净值 |
| shares | 份额 |
| trigger_reason | 触发原因 |
| status | PENDING/CONFIRMED |

---

## 定时任务

| 时间 | 任务 | 说明 |
|:---|:---|:---|
| 8:26 | sync_trades.py | 同步基金系统交易 |
| 8:28 | strategy.py update_navs | 补充手动操作净值 |
| 8:35 | strategy.py check | 检查操作建议 |
| 9:00 | morning_audit.py | 先做安全缓存对齐，再做一致性巡检，异常时 Telegram 提醒 |

---

## 手动操作流程

当你手动执行买入/卖出后，告诉我操作详情，我会更新监督点：

**你说**: "007882 买了 100 元" 或 "020629 卖了 500 元"

**我执行**:
1. 更新 `last_date` → 操作日期（立即）
2. 记录交易，状态 `PENDING_NAV`
3. 第二天 8:28 补充 `last_nav`（净值出来后）

**关键点**:
- 监督点（`last_date`）立即更新
- 监督净值（`last_nav`）隔日更新
- 买入通常按金额驱动；若卖出是按份额下达，则确认时保持份额不变，仅按正式净值回算金额
- 不干扰基金系统的正常流程

---

## 使用方式

```bash
# 检查操作建议
python3 skills/gridseed-v3/strategy.py check

# 记录手动操作
python3 skills/gridseed-v3/strategy.py record 007882 BUY 100
python3 skills/gridseed-v3/strategy.py record 020629 SELL 500

# 补充待处理净值
python3 skills/gridseed-v3/strategy.py update_navs

# 同步基金系统交易
python3 skills/gridseed-v3/sync_trades.py
```

---

## 相关文档

- **fund-portfolio/SKILL.md** - 基金系统核心规则
- **fund-portfolio/TECH_SPEC.md** - 技术规范