# 质量评测查看器恢复设计

## 目标

让 `/test` 的历史质量评测页面完整显示每轮脱敏对话、评分和 Guard 重试原因，并明确当前案例目录与结果批次的覆盖关系，避免把旧版或其他套件结果误读为当前案例结果。

## 范围

- 保留现有 `/api/quality/results` 的脱敏结果结构，继续从历史工件读取 `turn.warnings`。
- 在历史 transcript 的每轮卡片中显示 Guard 重试警告，并与自动评分标签分开。
- 在批次摘要中显示结果批次、套件、结果条数与案例目录条数，明确未生成案例是覆盖缺口。
- 为上述行为增加离线回归测试，并用现有本地结果做 HTTP 和浏览器验证。

不在本次范围内：修改评分器或案例定义、生成新的 Gemini/DeepSeek 结果、安装依赖、启动游戏/SMAPI、创建提交。

## 数据流

`results.jsonl` → `quality_results._safe_turn` 保留脱敏 `warnings` → `/api/quality/results` → `dialogue_lab_page.renderCaseTranscript` 渲染每轮警告。

页面使用当前请求的 `suite` 读取案例目录，并将 `state.run.results` 与目录总数并列显示；缺少结果的案例继续显示“未生成”，但批次摘要明确覆盖差异。

## 验证

- 前端字符串回归：`renderCaseTranscript` 必须读取 `turn.warnings`，并生成 Guard 重试可读文本。
- 页面摘要回归：HTML 必须包含批次标识、结果数和案例目录覆盖提示。
- 定向 pytest：`bridge/tests/test_external_dialogue_lab.py bridge/tests/test_quality_results.py`。
- 运行中的 `5678`：`/health`、`/api/quality/results`、目标 `/test` HTTP 验证。
- 浏览器工作台检查目标案例的三轮对白、Guard 警告、评分和覆盖提示。
