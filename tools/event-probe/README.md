# 事件探针（测试夹具）

**这不是产品代码。** 它的唯一用途是让「完成一个剧情事件 → 第二天早上 NPC 主动开口」这条链路可以在游戏里被验证。验证完请整个目录删掉，连同 `Mods\StardewAI.EventProbe\` 与 `data\scenarios\morning.json` 里那条 `event-after-probe` 预设。

## 为什么需要它

事件型预设要求玩家**刚完成一个剧情事件**，而原版事件全都带门槛：心级（`/f Shane 1000`）、时间窗（`/t 600 800`）、季节（`/z winter`）、前置事件（`/e 321777`）。在游戏里按需凑齐一条几乎不可能，尤其是事件已接近全完成的深度存档。

这个 mod 往 `Data/Events/Farm` 注入一条**没有任何前提条件**的事件：

```
9990001 → continue/-1000 -1000/message "[事件探针] 9990001 已触发"/pause 500/end
```

因为它挂在 `Data/Events/Farm` 且无前置，**第一次从农舍走进农场就会触发**；触发后由游戏写进 `player.eventsSeen`，此后不再出现——**这一点与真实事件完全相同**，而被测链路关心的正是这个写入，不是剧情内容。

三个参数都是为了不打扰其他事件：`continue`（无音乐）、`-1000 -1000`（viewport 不动，避免和原版农场事件抢镜头）、不写 `farmer x y`（不搬动玩家）。

事件 id `9990001` 是刻意挑的：原版用小数字（`13`、`20`、`92`）与不规则七位数（`3910674`），SVE/RomRas 占 `1000001`–`1000038`，9 开头这一段没人用。

## 构建与部署

```powershell
$gd = 'D:\sbeam\steamapps\common\Stardew Valley'
$w  = 'E:\workspace\projects\stardew-ai-npc.worktrees\story-memory'

# 1. 构建两个 mod
dotnet build "$w\smapi\StardewAI.NPC.csproj"        -p:GamePath=$gd -c Release
dotnet build "$w\tools\event-probe\EventProbe.csproj" -p:GamePath=$gd -c Release

# 2. 备份现有 DLL（可回退）
Copy-Item "$gd\Mods\StardewAI.NPC\StardewAI.NPC.dll" `
          "$gd\Mods\StardewAI.NPC\StardewAI.NPC.dll.bak" -Force

# 3. 部署
Copy-Item "$w\smapi\bin\Release\net6.0\StardewAI.NPC.dll" "$gd\Mods\StardewAI.NPC\" -Force
New-Item -ItemType Directory -Force -Path "$gd\Mods\StardewAI.EventProbe" | Out-Null
Copy-Item "$w\tools\event-probe\manifest.json"                 "$gd\Mods\StardewAI.EventProbe\" -Force
Copy-Item "$w\tools\event-probe\bin\Release\net6.0\StardewAI.EventProbe.dll" "$gd\Mods\StardewAI.EventProbe\" -Force
```

## 测试步骤

Bridge 必须在跑，且**输出要重定向到文件**，否则 `[morning]` 那行诊断看不到：

```powershell
Start-Process pwsh -ArgumentList '-NoProfile','-File',"$w\scripts\start_bridge.ps1" `
  -RedirectStandardOutput 'E:\workspace\.scratch\bridge.log' `
  -RedirectStandardError  'E:\workspace\.scratch\bridge.err.log' -WindowStyle Hidden
```

| 步 | 动作 | 预期 |
|---|---|---|
| 1 | 进入存档，**从农舍走到农场** | 弹出 `[事件探针] 9990001 已触发` |
| 2 | 正常玩，**睡一觉** | —— |
| 3 | 第二天早上 `DayStarted` 之后，看 `bridge.log` | `[morning] dayIndex=<N> recentEventIds=['9990001']` |
| 4 | 看游戏里刘易斯有没有主动发消息 | 开场白必须是「早啊。昨天你那边动静不小，我在镇上就瞧见了。都还顺利吧？」 |
| 5 | 跟他聊 2–3 轮 | 他**不该**描述具体发生了什么（他没进农场，只是路过）；**不该**说教 |
| 6 | 再睡一觉，看第三天 | **不该**再收到同一条（`firedScenarios` 去重） |

### 日志怎么读

`[morning]` 那行是这次测试的核心，三种形态含义完全不同：

| 日志 | 含义 |
|---|---|
| `recentEventIds=['9990001']` | **链路全通**。DLL 跨天差异算对了，也送到了 |
| `recentEventIds=[]` | DLL 送了，但**没算出新事件** —— 问题在 `RecentEventTracker` 或 `DayStarted` 时机 |
| `recentEventIds=<NOT-SENT>` | **DLL 根本没送这个字段** —— 问题在 `BridgeClient` 或序列化 |

⚠ `<NOT-SENT>` 在正常情况下**不应该出现**：C# 侧写的是
`RecentEventIds = recentEventIds ?? Array.Empty<string>()`，字段总是会被序列化。
它一出现，就说明接线断了。

## 撤掉

```powershell
Remove-Item -Recurse -Force "$gd\Mods\StardewAI.EventProbe"
# 恢复旧 DLL（或部署新的产品构建）
Move-Item "$gd\Mods\StardewAI.NPC\StardewAI.NPC.dll.bak" `
          "$gd\Mods\StardewAI.NPC\StardewAI.NPC.dll" -Force
```

同时删掉 `data/scenarios/morning.json` 里的 `event-after-probe` 预设，以及
`bridge/tests/test_morning_scenario.py` 里 `TestEventAfterRealData.PROBE_EVENT_IDS` 的豁免
（连同 `test_probe_ids_are_fixtures_only`）—— 那两处是**为这个夹具专门开的**，
留着就等于给「写错的 eventId」留了一条安静通过的通道。
