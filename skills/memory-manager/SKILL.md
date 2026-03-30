# memory-manager - 记忆力管理命令

记忆力管理、去重清理、健康检查、备份恢复、上下文压缩提示。

**命令**: `/memory`

---

## 功能

| 子命令 | 功能 |
|:---|:---|
| `/memory` | 显示记忆系统状态 + 上下文压缩建议 |
| `/memory stats` | 详细统计（总数、嵌入覆盖、日期分布） |
| `/memory clean` | 清除重复记忆（保留最早的） + 建议压缩 |
| `/memory backup` | 手动备份向量库 |
| `/memory health` | 综合健康检查报告 |
| `/memory report` | 生成 JSON 报告文件 |
| `/memory compact` | 记忆力管理 + 返回压缩建议 |

---

## 使用方式

```bash
# 一站式管理（推荐）
/memory compact

# 清除重复 + 建议
/memory clean

# 仅查看状态
/memory
```

---

## 执行流程

当收到 `/memory` 或 `/memory compact`：

1. **执行记忆力管理** - 调用 memory_hooks.py
2. **返回结果** - 显示记忆统计、健康状态
3. **建议压缩** - 提示发送 `/compact` 压缩上下文

**注意**: `/compact` 是 Gateway 命令，需用户手动发送。Agent 无法直接触发。

---

## 技术实现

### 记忆系统脚本

位置: `/root/.openclaw/workspace/scripts/memory_hooks.py`

功能:
- `stats` - 记忆统计
- `duplicates` - 查找重复
- `clean` - 清理重复（`--force` 执行）
- `backup` - 备份数据库
- `health` - 健康检查
- `report` - JSON 报告

### 向量库

位置: `/root/.openclaw/memory/vector_memory.db`

表: `memories`

### 备份目录

位置: `/root/.openclaw/workspace/memory/backups/`

保留最近 7 个备份（自动清理）

---

## Agent 执行流程

当收到 `/memory` 命令时:

1. 解析子命令
2. 执行对应脚本
3. 返回结果给用户

```python
# 执行示例
import subprocess
result = subprocess.run([
    "python3", 
    "/root/.openclaw/workspace/scripts/memory_hooks.py",
    "stats"
], capture_output=True, text=True)
print(result.stdout)
```

---

## 定时维护

已在 cron 中配置:
- 每日备份（凌晨 3:00）
- 每周清理（周日 4:00）

---

## 多机器人同步

此 Skill 已同步到:
- workspace (贾维斯)
- workspace-coder (Jack)
- workspace-eva (艾娃)
- workspace-financial-elder (金融老登)

---

## 注意事项

- 清理重复需要先备份
- 嵌入覆盖率应保持 > 50%
- 备份文件自动压缩（gzip）