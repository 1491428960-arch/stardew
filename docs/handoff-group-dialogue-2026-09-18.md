# 群聊功能交接文档（2026-09-18）

> ⚠️ **本文已过时，请勿据此施工（2026-09-20 标注）**：本文写于群聊策略仍是 `turn_based`、长期记忆链路尚未打通之时，
> 其中“`multi_turn` 只是实验策略”“回放页固定读取 v3”“头像用符号”等结论均已被推翻或取代。
> 当前权威来源：`docs/active-work.md`（**最新条目在文件末尾**）与 `docs/handoff-group-dialogue-2026-09-20.md`。
> 本文保留仅作历史记录。

> 交给下一模型继续处理。本文只覆盖本轮线上群聊回放、自然接话流、角色化头像与气泡工作；当前 worktree 还有大量既有未提交改动，不能据此重置、清理或覆盖。

## 1. 开发现场与必读文件

- 真实 worktree：`E:\workspace\projects\stardew-ai-npc.worktrees\story-memory`
- 分支：`codex/story-memory`
- 先读：`E:\workspace\hub\AGENTS.md`、本 worktree 的 `AGENTS.md`
- 最新工作日志：`docs/active-work.md`（顶部最新）
- 本交接文档：`docs/handoff-group-dialogue-2026-09-18.md`
- Bridge 约定端口：`127.0.0.1:5678`
- Git 命令需要加：`git -c safe.directory=E:\workspace\projects\stardew-ai-npc.worktrees\story-memory ...`

当前工作树很脏，包含此前角色画像、Prompt、评测、SMAPI 和文档的大量改动。不要运行 `git reset --hard`、`git clean`、`git checkout --`，不要创建 Git commit，除非用户明确要求。

## 2. 用户目标

用户先发现群聊回放只有一个 NPC 发言，随后要求：

1. 群聊不能只是“每人整齐说一句”，应允许自然接话、插话、连续补充或有人不发言。
2. 每个 NPC 在回放中要有符合自身气质的头像和气泡，而不是所有人共用一套样式。
3. 页面要方便人工判断群聊是否真的成立。

## 3. 已完成

### 3.1 多人回应云端基线

旧回放使用 `turn_based`，按设计只调用 `activeSpeakerNpcId`，所以每个案例只有一个 NPC 回答。这不是数据丢失，而是策略含义如此。

已生成独立工件：

```text
artifacts/character-quality-eval/20260918-group-dialogue-cloud-v3-fanout-cases/
```

`summary.json` 已确认：`strategy=fanout`、`caseCount=6`、`successfulCases=6`、`providerCalls=14`、`provider=cloud`、`channel=remote`，并且 `allRemote`、`allCloud`、`allNoFallback`、`allNoProviderErrors`、`allParticipantsReplied`、`allSpeakersInRoster` 全部为真。

回放页现在固定读取 v3，而不是旧 v2：

```python
# bridge/src/stardew_ai_bridge/group_dialogue_review_page.py
_BATCH_NAME = "20260918-group-dialogue-cloud-v3-fanout-cases"
```

### 3.2 自然接话流

`fanout` 继续作为“每个参与者都回应”的协议基线，不要把它误称为自然流。`multi_turn` 已重新定义 Prompt：

- 名单内 NPC 都可以发言，但不要求每个人发言，也不要求一人恰好一句；
- 可以有人先接、另一个 NPC 插话；
- 允许同一 NPC 连续补一句或把话题递给指定参与者；
- 总回合数仍由 `turnCount` 上限限制；
- 每回合必须使用名单内 `speakerNpcId`，不能替别人代答；
- 不能添加名单外角色、把线上聊天写成线下见面，或修改关系/库存/日程；
- 仍要求结构化 JSON `{"turns":[...]}`。

实现位置：

- `bridge/src/stardew_ai_bridge/group_conversation.py`：`build_group_prompt()` 增加 `turn_count`，`multi_turn` 使用自然接话流规则，其他策略保留 active speaker 约束。
- `bridge/src/stardew_ai_bridge/group_dialogue_lab_page.py`：将 `multi_turn` 显示为“自然接话流（可插话）”，并更新页面说明。
- `bridge/tests/test_group_conversation.py`：新增回归，确认自然流不再携带“当前发言人只能说 Abigail”这类冲突约束。

### 3.3 角色化头像和气泡

实现位置：`bridge/src/stardew_ai_bridge/group_dialogue_review_page.py`。

当前是符号化头像，不是游戏原始肖像贴图。已配置：

| NPC | 图标 | 气质标签 |
|---|---|---|
| Abigail | `✦` | 好奇 · 直觉 |
| Alex | `★` | 直球 · 行动派 |
| Emily | `◇` | 温柔 · 灵感 |
| Elliott | `✒` | 铺陈 · 诗意 |
| Harvey | `✚` | 稳重 · 照料 |
| Sebastian | `◢` | 克制 · 短句 |
| Shane | `☕` | 疲惫 · 嘴硬 |
| Sophia | `✿` | 轻快 · 跳脱 |
| Wizard | `✧` | 神秘 · 判断 |

页面现在：

- 每条 NPC 消息有独立图标、主色、气泡底色、边框和圆角；
- speaker 行显示 NPC 名称和气质标签；
- `addressedTo` 非空时显示 `→ 目标`；
- 同一 NPC 连续回合隐藏重复头像和名称，视觉上合并为连续发言；
- 回放中提示当前 v3 是多人回应基线，实验台可切换自然接话流。

### 3.4 页面入口

- 实验台：`http://127.0.0.1:5678/test/group`
- 云端回放：`http://127.0.0.1:5678/test/group/review`
- 路由定义：`bridge/src/stardew_ai_bridge/app.py`

## 4. 已验证证据

最近一轮实际验证：

```text
py -3.10 -m pytest bridge/tests/test_group_conversation.py bridge/tests/test_external_dialogue_lab.py -q
128 passed

py -3.10 -B -m compileall -q bridge/src scripts
exit code 0

git diff --check
exit code 0
```

本地 API Fake 验证：`provider=fake`、`strategy=multi_turn`、3 个参与者、`turnCount=3`，结果为：

```text
strategy=multi_turn
providerCalls=1
turns=3
speakers=Abigail,Sebastian,Sophia
providerErrors=(empty)
```

浏览器人工验收曾实际看到 Shane 的 `☕`/蓝灰气泡/“疲惫 · 嘴硬”，Harvey 的 `✚`/青绿色气泡/“稳重 · 照料”，以及三人案例的三个独立气泡。

## 5. 尚未完成、不要误判

### 5.1 自然接话流还没有新的云端批次

本轮没有新发起云端请求。当前回放页展示的是已确认的 v3 `fanout` 云端基线；它证明多人气泡和协议，不证明 `multi_turn` 的真实云端自然程度。

若用户确认生成真实云端样本：

1. 必须使用新的独立目录，例如 `artifacts/character-quality-eval/20260918-group-dialogue-cloud-v4-natural-flow-cases/`；
2. 不覆盖 v3；
3. 小批次建议 4～6 个 2/3 人案例，`strategy=multi_turn`，`turnCount=3` 或 `4`；
4. 检查有人不发言、同一 NPC 连续回合、合理插话、`addressedTo` 承接、声线差异、无 fallback/ProviderError；
5. 真实云端验证前要先获得用户明确确认，因为会消耗 Token。

### 5.2 头像目前是符号，不是原始肖像

若要换游戏肖像，先查本地资源和授权边界，再加资源路径及加载失败回退；不要直接抓取或提交未经确认的外部图片。

### 5.3 群聊 Prompt 尚未逐 NPC 展开完整 persona

`build_group_prompt()` 当前 roster 主要传 `npcId` / `displayName`，而 `DialogueTestRequest` 仍带单个参与者的 `sourceMods`。如果云端自然流的角色差异不足，优先从现有 `ProfileIndexStore` / persona 层筛选简短声线锚点注入每个参与者，不要在群聊 Prompt 里手写一套新的画像。

注入时要保持 canonical NPC、source Mod、关系阶段、原文证据来源和线上/线下边界；不要把密钥或内部运行状态传给 Provider。

## 6. 推荐下一步

1. 先跑离线回归和 `GET /health`，确认承接环境没有漂移。
2. 检查 `multi_turn` 的实际 Prompt JSON，确认 `turn_count` 与解析上限一致。
3. 用户确认后，小批量生成 v4 自然流工件，不覆盖 v3。
4. 为 v4 增加独立回放入口或显式批次配置，不要静默替换基线。
5. 人工复核 Shane 的疲惫嘴硬、Sebastian 的克制短句、Sophia 的轻快跳拍、Elliott 的铺陈、Harvey 的照料和 Wizard 的判断口吻。
6. 只有自然流真实云端样本稳定后，才讨论接入游戏生产策略；本轮没有启动 Stardew/SMAPI，也没有部署 DLL。

## 7. 常用命令

```powershell
Set-Location E:\workspace\projects\stardew-ai-npc.worktrees\story-memory
$env:PYTHONPATH='bridge/src;scripts'

py -3.10 -m pytest bridge/tests/test_group_conversation.py bridge/tests/test_external_dialogue_lab.py -q
py -3.10 -B -m compileall -q bridge/src scripts
git -c safe.directory=E:\workspace\projects\stardew-ai-npc.worktrees\story-memory diff --check

powershell -ExecutionPolicy Bypass -File .\scripts\start_bridge.ps1
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5678/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5678/test/group/review
```

## 8. 红线

- 不启动 Stardew/SMAPI，除非用户明确要求并按项目既定 FastTest 流程执行。
- 不部署 DLL，不修改正式 Mods、存档或角色资料库。
- 不读写或输出 API Key、Token、Cookie、订阅认证字段。
- 云端请求需要用户明确确认，并使用新的独立工件目录。
- 不清理、重置或覆盖当前 dirty worktree。
- 不创建 Git commit，除非用户明确要求。
