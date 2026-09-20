# 群聊功能交接（2026-09-20 更新版）

> 取代 `handoff-group-dialogue-2026-09-18.md`（那份写于策略仍是 `turn_based`、记忆链路尚未打通之前，结论已过时）。
> 本文覆盖「线上群聊」这条线的**当前真实状态**：策略、回合预算、两层记忆、F9 流程、验证工具与踩过的坑。

## 1. 开发现场与红线

- worktree：`E:\workspace\projects\stardew-ai-npc.worktrees\story-memory`（分支 `codex/story-memory`），**主库 main 只含文档提交，别在主库动工**
- 权威状态文档：`docs/active-work.md`，**最新条目在文件末尾**（历史条目顺序混杂，别只看开头）
- git 命令一律加 `-c safe.directory=<worktree 绝对路径>`；**禁止** `git config --global`
- 红线：不部署正式 DLL、不改正式存档/Mods、不清理 dirty worktree、不创建 commit（除非用户明确要求）、不输出任何 Key
- 游戏内验证需用户**逐次授权**（起的是真实游戏进程，走受控 `Mods-AI-FastTest` + 测试存档 `test_447101921`）
- 该工作树**可能有其他会话并行工作**（2026-09-19 起 UI/回放页由另一个会话负责，只改 `bridge/` 页面；SMAPI 侧归本线）

## 2. 当前行为（用户可感知的部分）

| 方面 | 现状 |
|---|---|
| 策略 | 默认 **`multi_turn`（自然接话流）**：一次请求里名单内多人可依次发言；GMCM 可切回 `turn_based`（一人一轮） |
| 回合预算 | **未显式指定时按在场人数给**（2 人→2、3 人→3，上限 4）；显式传 `turnCount` 时照用 |
| 记忆（内存层） | `BridgeClient.historyByNpc`，每人 6 条、重启即失；一次群聊**只占 1 条**合并记录，只记本人发言 |
| 记忆（存档层） | 只写 Bridge 挑出的 `memoryHighlights`（1～3 条重要事实/约定，闲聊不写），**在场每个 NPC 各一条** |
| F9 入口 | 多人对话中心：接受邀约卡 → 进群聊菜单；或自由发起 → 选 2～3 名已认识的 NPC → 进群聊菜单 |
| 频道 | 固定 `channel=remote`，不传送 NPC、不改日程、不写线下见面的措辞 |

**为什么策略默认值很关键**：2026-09-19 之前 `BridgeClient.SendGroupAsync()` 把策略**硬编码成 `turn_based`**，导致 09-18 以来十几批 `multi_turn` Prompt 调优（v4～v21）**从未进入游戏**，游戏里每次群聊只有一个人说一句。修复后真机验证 `turns=2`（两人各一句）、三人场 `turns=3`。

## 3. 关键文件

| 文件 | 作用 |
|---|---|
| `smapi/BridgeClient.cs` | 群聊请求构造（策略、turnCount 之外的全部字段）、响应校验（**响应策略必须等于请求策略**）、`RememberGroupTurn` 内存层记忆 |
| `smapi/ModConfig.cs` | `GroupDialogueStrategy`（默认 `multi_turn`，`Normalize()` 只接受 `multi_turn`/`turn_based`） |
| `smapi/ModEntry.cs` | 把策略注入 `BridgeClient`；F9 入口与 GMCM 下拉 |
| `smapi/GroupDialogueMenu.cs` | 群聊菜单；`ApplyMemoryHighlights()` 写存档记忆；`QueueResponseForVisualTest()` / `PressSendForVisualTest()` 供视觉测试走真实路径 |
| `smapi/GroupMemoryRules.cs` | 纯函数：在场每个参与者 × 每条 highlight（去重、去空白） |
| `smapi/GroupDialogueHubMenu.cs` / `GroupParticipantMenu.cs` | 邀约中心与选人菜单；两者的坐标常量与生产点击逻辑共用 |
| `bridge/src/.../group_conversation.py` | 群聊 Prompt 组装、`turn_budget()`、`parse_multi_turn_payload()`（回合 + memory 高亮） |
| `bridge/src/.../providers.py` | `_max_tokens_for()`：单 NPC 160、multi_turn 900 |
| `scripts/run_group_dialogue_cloud_batch.py` | 云端批次运行器（默认 dry-run，须 `--confirm-cloud`；`--turn-count` 可做回合预算单变量对照） |
| `scripts/start_visual_test.ps1` | 游戏内视觉验证入口（**必须 pwsh 7**） |

## 4. 验证工具

### 4.1 游戏内视觉 harness（场景由 `STARDEW_AI_NPC_VISUAL_ACTION` 决定）

| 场景 | 联网 | 覆盖 |
|---|---|---|
| `group-hub` | 否 | 多人对话中心与邀约卡渲染 |
| `group-message` | 否 | 模拟响应 → 会话 → 存档长期记忆写入 |
| `group-send` | 是 | 真实发一次群聊请求：内存层一条式记忆、参与者各自 gameState 转发 |
| `group-accept` | 否 | F9 全流程：点邀约卡"接受" → 群聊菜单 |
| `group-free` | 否 | F9 全流程：自由发起 → 选参与者（中途截图）→ 群聊菜单 |

用法：`pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_visual_test.ps1 -ActionId <场景> -ScenarioId <名> -OutputPath 'artifacts\visual-tests\<新目录>' -TimeoutSeconds 240`
产物：`<名>.png`（菜单截图）、`<名>.json`（manifest：回合数、记忆计数等）、`<名>-diagnostics.json`、`audio-mute.json`。
**每次必须换新 OutputPath**（脚本拒绝覆盖）。

**关于静音（跑之前该知道的事）**：harness 会**自动把本次运行静音**，但**启动瞬间仍可能漏出一声**。

- **怎么静的**：`VisualTestHarness.MuteAudio` 只改**本次进程的运行时音量**——把 `musicVolumeLevel` / `soundVolumeLevel` / `ambientVolumeLevel` / `footstepVolumeLevel` 四个字段清零，然后**必须调 `initializeVolumeLevels()`**（游戏把音量等级换算成分类音量缓存在那里，只改字段不调它，**正在播放的音乐仍按旧缓存音量出声**，实测如此），再反射调 `musicCategory` / `ambientCategory` / `soundCategory` / `footstepCategory` 四个分类的 `SetVolume(0)`。证据写在产物的 `audio-mute.json` 里。
- **不动全局设置**：改的是进程内 `Game1.options`，**不会写回你的游戏音量配置**。
- **为什么还可能有一声**：执行时机是尽量早的（Mod 加载时，早于 `GameLaunched`），因为**游戏在标题界面就会开始放音乐**；但**从进程启动到那一刻之间**仍有一个窗口，音乐可能已经起头。
- **想彻底消除**：需要在 **Core Audio 层面按进程静音**（例如对进程调用 `ISimpleAudioVolume`），**目前没做**——所以跑视觉测试时若听到一声，是预期内现象，不是 bug。

### 4.2 云端批次

```powershell
$env:PYTHONPATH='bridge/src;scripts'
& $py -B scripts/run_group_dialogue_cloud_batch.py --batch <新目录名> --confirm-cloud   # ⚠️ `py -3.10` 在本机不可用，改用绝对路径，见 .dsh/memory/commands.md 开头
# 只跑指定案例：--case <caseId>；覆盖回合预算：--turn-count 2|3|4
```
结果写 `artifacts/character-quality-eval/<批次名>/`，回放页会自动发现（`YYYYMMDD-group-dialogue-cloud-*`）。

## 5. 十个必须知道的坑

1. **改 Bridge 的 Python 代码必须重载 5678 进程**，否则游戏与探针都在连旧代码（2026-09-19 因此白验过一次）。
2. **游戏内验证跑在 Session 0**（DSH 是 Windows 服务），用户看不见窗口、但**能听见声音**；需要用户目视时要用计划任务投递到 Session 1。
3. **视觉 harness 会自动静音**，正确入口是 `Game1.options.*VolumeLevel = 0` **加**反射调用 `Game1.initializeVolumeLevels()`（只改字段或只调分类 `SetVolume` 都照样出声）。启动瞬间仍可能有一声（XACT 在 Mod 加载前已起标题音乐），用户已接受。
4. **自定义面板一律用 `drawTextureBox`**，不要用 `Game1.drawDialogueBox`——后者即使 `ignoreTitleSafe: true` 也会把框裁到 title-safe 区域。已踩三次（Hub、GroupDialogueMenu、GroupParticipantMenu）。
5. **菜单必须挂到 `Game1.activeClickableMenu`**，否则 `Rendered` 闸门静默 return、脚本超时；多步流程点击后要跟着更新 harness 的 `activeMenu`。
6. **中文 `Game1.smallFont` 没有 `✓` `□` `～` 字形**（会渲染成 `*`），UI 文案只用中文标点与 ASCII。
7. **测试数据写入 store 要晚于 `SaveLoaded`**：直接 `SaveGame.Load` 的路径下，存档状态会在菜单打开之后才灌进 store（harness 的订阅早于 ModEntry）；`group-accept` 用 `EnsureInvitationPresent()` 兜底。
8. **`turnCount` 不能想当然**：Bridge 默认已改为"按在场人数"，但任何显式传值都会覆盖它；2 人场在额度 2 下必然都开口，测不出修复效果，要用三人场。
9. **`gameState` 是逐参与者的**：`GroupDialogueMenu` 为每个参与者各自解析状态，解析不到时保持 null，**不拿别人的状态顶替**（例：FastTest profile 不含 SVE，SVE 角色解析不到 gameState——第 85 行那个 Sophia 的旧例即由此而来）。
10. **回应名单内的人要用"你"**：当面对话写第三人称名字很怪；`addressedTo` 必须与人称一致（对玩家说就留空数组）。

## 6. 未完成 / 待用户拍板

- **正式环境部署**：DLL 装进正式 Mods、用正式存档跑一遍群聊——至今只验过 FastTest 隔离 profile
- **参与覆盖的真实稳定性**：真实云端 multi_turn 偶尔仍只回 1 个回合（Emily 整场不开口），Prompt 层面的兜底已在，但未达稳定
- **`group-send` 的三人名单已换成游戏内存在的角色**（Abigail／Emily／**Sebastian**）。原先第三位是 SVE 的 Sophia，而 FastTest profile 未装 SVE，`Game1.getCharacterFromName("Sophia")` 解析不到 gameState，`groupRequestStateCount` 会停在 **2**。**换人后应期待 `groupRequestStateCount=3`**（三人各自带状态）；历史基线目录 `artifacts/visual-tests/group-send-trio/` 是旧名单（含 Sophia）的结果，**不要拿它对照新值**。此改动**已就绪但尚未真机确认**。
- **群聊 Prompt 与私聊 Prompt 的同源维护**：群聊现在复用单 NPC 的完整角色卡（`build_group_messages`），私聊每加一张卡都要确认群聊跟着生效

## 7. 2026-09-20 通宵会话对这条线的改动

这一夜（00:07→06:00）本线（SMAPI 侧与群聊链路）改了 **4 个生产文件**，每个都有测试与实测证据。
细节见 `docs/active-work.md` 的相关条目与 `docs/overnight-report-2026-09-20.md` 的逐项表。

| 文件 | 改了什么 | 为什么 | 验证 |
|---|---|---|---|
| `smapi/GroupDialogueSessionRules.cs` | `addressedTo` 归一化 | 大小写／空白写法不同会导致发言人识别失败 | SMAPI 测试 + 新增回归用例 |
| `smapi/GroupInvitationRules.cs` | `BuildPairKey` 改成 `Trim().ToLowerInvariant()` + `Distinct(Ordinal)` + `OrderBy`；`BuildDuplicateKey` 也归一化模板 ID | 去重键大小写不一致会让同一对 NPC 重复入队 | `GroupInvitationCaseInsensitiveDedupTests`（3 条新用例） |
| `smapi/ConversationStateRules.cs` | `Truncate` 不再切断 UTF-16 代理对 | 截断会把 emoji／罕见汉字切成半个字符，产生乱码 | 新增代理对边界用例 |
| `bridge/src/stardew_ai_bridge/group_dialogue_review_page.py` | 修阻塞性 import（别名改从 `npc_bubble_catalog` 导入） | **它会让 Bridge 重启直接起不来**（`app` 无法导入） | `verify_project.ps1` + Bridge 全量 |

**两条要注意的边界**：

1. **`group-send` 的三人名单已换成游戏内存在的角色**（原含 Sophia，而 FastTest 存档未装 SVE）——**待真机确认** `groupRequestStateCount=3`。
2. **运行中的 Bridge（5678）仍是旧代码**（PID 57768，启动于 09-19 22:53）：上面第 4 条的修复**要重启进程才生效**；重启命令见 `.dsh/memory/commands.md`。

**当前测试基线**（2026-09-20 04:47 实测）：SMAPI **469 passed**、Bridge **2723 passed / 5 failed**——那 5 条属气泡元素线的重构中间态，不是本线回归。
**权威值以 `.dsh/memory/current-state.md` 为准**（它带取数时间戳）。
