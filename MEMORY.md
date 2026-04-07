# MEMORY.md - 系统索引

> 更新: 2026-04-07 08:55 | **GridSeed V3.2**

## 角色定位

- **身份**: 开发经理·Jack
- **核心职责**: 系统开发、代码编写、业务系统跟踪
- **协同**: 贾维斯统筹，艾娃文档支持

---

## 系统架构

```
定时任务 (crontab)
├── 8:20 daily_update.py   # 净值更新+交易确认
├── 8:23 dca_runner.py     # 定投执行
├── 8:26 sync_trades.py    # GridSeed同步
├── 8:28 update_navs       # 补充净值+批次回填
├── 8:30 send_email.py     # 邮件报告
└── 8:35 strategy.py check # GridSeed提醒
```

---

## GridSeed V3.1 核心机制

### 盘中估值 vs 隔日确认

```
盘中操作（估算净值）
├── record_operation(nav=估算值)
├── is_confirmed = False
├── status = 'PENDING_NAV'
└── 不写入 grid_batches ❌

隔日确认（真实净值）
├── update_pending_navs()
├── 获取官方净值
├── status = 'CONFIRMED'
└── 回填 grid_batches ✅
```

### 闲置唤醒

```python
trigger_reason = '闲置唤醒'
new_step = step  # 不增加step
```

### 网格期处理

```python
if phase == 'GRID':
    trigger_reason = '网格买入/卖出'
    # 正确处理 grid_batches
```

---

## 配置管理

### skills/config.py

- 支持环境变量（.env）
- 自动适配Windows/Linux路径
- 统一Token/密码管理

### 数据库配置表

**dca_config** - 定投配置（12只，周640元）
**strategy_params** - 策略参数

---

## GridSeed 当前状态

| 阶段 | 数量 | 基金 |
|:---|:---:|:---|
| 网格期 | 2只 | 015790, 019924 |
| 建仓期 | 13只 | 其他 |

---

## V3.2 BIAS-Drawdown 技术指标

### 核心公式
```
BIAS-250 = (当前净值 - 250日均线) / 250日均线
Drawdown = (近3年最高净值 - 当前净值) / 近3年最高净值
```

### 策略阈值

| 波动类型 | 止盈 | 补仓 | 大额 | 梭哈 |
|:---|:---:|:---:|:---:|:---:|
| 🔴 高波动 | BIAS>25% | -15%/20%DD | -20%/35%DD | -30%/45%DD |
| 🟡 中波动 | BIAS>15% | -8%/10%DD | -15%/20%DD | -20%/30%DD |
| 🟢 低波动 | BIAS>12% | -5%/8%DD | -10%/12%DD | -15%/20%DD |

### 当前信号（2026-04-02）

| 信号 | 基金 |
|:---|:---|
| 🔴 止盈区 | 001665(+41%), 009982(+18%) |
| 🟠 大额区 | 012349(-16%/28%DD) |
| 🟡 补仓区 | 017437(-9%/16%DD) |

---

## 核心计算规则

### 估算判断
```
涨跌幅 = (估算净值 - 监控点净值) / 监控点净值
```

### 操作流程
```
操作日: last_date更新, last_nav=NULL, status=PENDING_NAV
隔日8:28: 补充净值, 回填grid_batches
```

---

## Git仓库

- **GitHub**: https://github.com/1121548875jzh-collab/fund-portfolio-system
- **规则**: 操作 → 写入数据库 → git commit → git push

---

## HTTP API

- **地址**: http://47.83.16.62:5000

---

## 已知问题

暂无（V3.3已修复历史问题）

---

## 经验教训

1. **净值确认：** 盘中估算→PENDING_NAV→隔日确认
2. **闲置唤醒：** 不增加step
3. **网格批次：** 只有确认净值才写入grid_batches
4. **配置统一：** config.py + 环境变量
5. **step更新：** 检查是否已存在，避免重复
6. **total_cost同步：** 新基金加入时必须同步已有持仓
7. **港股休市：** dca_runner需考虑港股休市日

---

*最后更新: 2026-04-07*