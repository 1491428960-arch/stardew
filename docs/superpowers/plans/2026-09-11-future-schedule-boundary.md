# 未来安排判定边界收窄实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans`（内联执行）逐任务实现，并保留文档中的复选框。

**目标：** 允许 NPC 推迟自己的记录、研究和普通事务，同时继续拦截面向玩家或共同活动的未来社交承诺。

**架构：** 保留现有质量评分器的 `future_schedule_commitment` 标签，但让它只覆盖固定时长、见面/预约/陪伴/共同活动和自动履约等社交安排。关系 Prompt 改为禁止社交排期，而不是禁止所有“明天/晚点”等相对时间词；普通自我事务延期与自然收尾明确放行。

**技术栈：** Python、pytest、Bridge PromptBuilder、现有正则评分器。

---

### 任务 1：补充未来安排边界回归测试

**文件：**
- 修改：`bridge/tests/test_character_quality_eval.py`
- 修改：`bridge/tests/test_prompts.py`

- [x] **步骤 1：添加应放行与应拦截的最小案例**

增加以下行为断言：

```python
assert "future_schedule_commitment" not in score_for("记录可以搁到明天。")
assert "future_schedule_commitment" not in score_for("这份笔记明天再看。")
assert "future_schedule_commitment" in score_for("明天来找你。")
assert "future_schedule_commitment" in score_for("给你留出两小时。")
assert "future_schedule_commitment" in score_for("行，聊完就去房间，给我十分钟。")
```

Prompt 回归同时要求关系卡包含“允许 NPC 自己的事务延期/自然收尾”，并继续包含禁止社交排期、固定陪伴时间和自动履约的约束。

- [x] **步骤 2：运行定向测试确认红灯**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_character_quality_eval.py bridge/tests/test_prompts.py
```

预期：新增测试至少因 `明天来找你` 未被识别或 Prompt 尚未提供新边界而失败；失败原因应来自行为缺口，不是导入错误。

### 任务 2：收窄评分器和关系 Prompt

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py`
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`

- [x] **步骤 1：扩展社交承诺匹配而不拦截自我事务延期**

保持“给玩家固定时长”和“聊完后安排下一动作”的现有拦截，并补充“明天来找你/联系你/陪你”等面向玩家的动作；不要添加仅由“明天/晚点/下次”触发的全局匹配。

- [x] **步骤 2：修改关系卡和最终覆盖卡的语义约束**

将绝对禁止未来时间词改为：禁止涉及玩家、共同活动、见面、预约、固定时长或自动履约的社交安排；允许 NPC 对自己的记录、笔记、研究、工作、整理和普通事务延期，也允许自然对话收尾。

### 任务 3：分层验证并记录结果

**文件：**
- 修改：`docs/active-work.md`

- [x] **步骤 1：运行定向回归**

确认边界测试和 Prompt 测试全部通过。

- [x] **步骤 2：运行 Bridge 全量与静态检查**

运行 Bridge 全量 pytest、`compileall` 和 `git diff --check`；不启动游戏、不发起云端请求。

- [x] **步骤 3：更新活动记录**

记录实际测试数量、失败/通过结果、未进行云端与游戏验证的边界；不创建 Git commit。

### 任务 4：统一运行时 Guard 与质量评分器的未来安排判定

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/guard.py`
- 修改：`bridge/tests/test_guard.py`
- 修改：`docs/active-work.md`

- [x] **步骤 1：用 Guard 边界回归复现分裂行为**

确认独立 Guard 正则会误拦“明天安排记录/给自己留出两小时整理记录”，并漏拦“明天来找你”；实际红灯为 `3 failed, 4 passed`。

- [x] **步骤 2：复用评分器统一判定并收窄重试提示**

让最终角色契约 Guard 复用 `_has_future_schedule_commitment`，并让重试提示允许 NPC 延期自己的普通事务，只要求重写面向玩家或共同活动的社交安排。

- [x] **步骤 3：完成运行时与本地服务验证**

定向 Guard/评分器/Prompt 回归 `444 passed`，Bridge 全量 `1364 passed`，`compileall` 与 `git diff --check` 通过；重载后 5678 监听 PID 和父进程命令行均指向当前工作树，`/health=200/ok/cloud`，案例接口 `200/8`。不发起云端请求、不启动游戏、不创建提交。
