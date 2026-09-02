# “找话题”连续性与主动亲密优化执行计划

> 按 `executing-plans` 顺序执行；每个阶段先用测试锁定行为，再实现、回归和记录证据。

## 目标

在保留现有 `topic-start-intimacy` 独立套件和旧批次的前提下，修复三轮语义错位：第一轮由 NPC 主动找话题，第二、三轮改为普通 `chat` 并保留真实玩家输入；将 `topicSeed`、`topicKeywords`、`continuationMode` 投影到评测 Prompt；增加话题承接、突然换题和主动亲密缺失的可解释诊断；生成独立新批次供网页读取。

## 阶段 1：失败测试与案例模型

- 为 `CharacterQualityTurn` 增加可选的当前轮 `intent`，旧案例缺省为 `chat`。
- 为 `CharacterQualityCase` 增加 `topic_seed`、`topic_keywords`、`continuation_mode`，目录导出使用 camelCase。
- 测试 `topic-start-intimacy` 的 32 例：首轮 `topic` + 空输入，后两轮 `chat` + 非空输入；目标案例有话题种子和关键词，对照为 `none` 强度。
- 先运行定向测试，确认红灯来自缺少字段/语义，而不是导入或路径问题。

## 阶段 2：评测请求、Prompt 与评分

- 评测器每轮使用 `turn.intent`，仅 `topic` 轮清空消息；后续轮将真实玩家输入写进 `DialogueTestRequest`、上下文和 Prompt。
- 质量上下文携带受限的话题种子、关键词和连续模式；首轮 Prompt 给出具体开题契约，后续 Prompt 给出连续承接契约。
- 评分按当前轮识别话题证据和历史锚点；目标案例主动亲密要求不能被普通 `specific_plan` 单独满足；记录 `unrelated_topic_shift` 等诊断标签。
- 运行定向 Python 测试、Fake Provider 三轮小批次和结果脱敏检查。

## 阶段 3：接口与全量回归

- `/api/quality/cases?suite=topic-start-intimacy` 返回新字段，默认套件契约不变；未知套件仍返回 400。
- 运行 Bridge 全量测试、内存 `compileall`、`git diff --check`。
- 重启当前 `story-memory` Bridge，使用 `/health`、案例 API 和结果 API 核对实际加载代码；不启动游戏、不部署 DLL、不改正式存档。

## 阶段 4：独立新云端批次与验收

- 使用当前 `next-proactive-affection` 索引和已配置云端 Provider，输出到新的 `20260902-topic-start-continuity-cloud` 目录，不覆盖 `20260902-topic-start-intimacy-cloud`。
- 校验 32 例、96 轮、请求语义统计、错误/fallback、Token、哈希和敏感字段扫描。
- 网页按最新批次加载对应套件；人工抽查五个主要角色的 anchored/pressure/对照及 remote/face_to_face，记录“像角色的热情”与未解决问题。

## 停止条件

只有代码回归、实际 Bridge 加载、新工件结构和网页 API 核对均完成后，才汇报本轮完成；云端输出质量不足时如实保留失败诊断，不把自动通过率当作角色质量达标。
