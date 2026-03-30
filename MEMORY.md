# MEMORY.md - L1 索引层 (Jack)

## 角色定位

- **身份**: workspace-coder (Jack)
- **核心职责**: 系统开发、代码编写、业务系统运行
- **协同**: 贾维斯统筹，艾娃提供文档支持

---

## 当前项目

- 🟡 GridSeed V3.0 开发（策略已确认）
- 🟢 基金管理系统运维（数据库在本workspace）
- 🟢 记忆系统维护（四层架构）

---

## 数据库位置

- `fund_portfolio.db` → `/root/.openclaw/workspace-coder/fund_portfolio.db`
- `vector_memory.db` → `/root/.openclaw/memory/vector_memory.db`（共享）

---

## 待办

- [ ] GridSeed V3.0 开发
- [ ] dashscope API Key 更新
- [ ] 安全审计修复

---

## 经验教训

1. 修改配置前必须备份
2. 脚本返回JSON/文本，不直接sys.exit
3. Tushare净值隔日8:20更新，不是当天晚上
4. **GridSeed估算判断：用监控点净值(last_nav)，不是昨日净值！**

---

*最后更新: 2026-03-30*