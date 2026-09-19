# 正式环境部署清单（2026-09-20 拟）

> **本清单只描述步骤，未执行任何一步**（部署 DLL、改正式 Mods／存档都需要你点头）。
> 事实前提：正式 `Mods\StardewAI.NPC` 的最后修改时间是 **2026-08-23 02:55**，而当前构建产物 `smapi\bin\Debug\net6.0\StardewAI.NPC.dll` 是 **2026-09-20 00:50**——**正式环境落后近一个月**，
> 这一个月的改动包括：F9 线上群聊（策略／回合预算／两层记忆）、关系事件锁、事件对白素材链、房间门边界、物品分享语义等。

## 0. 先想清楚三件事

1. **存档会被写入**：新 DLL 会在正常对话／群聊后把故事状态（记忆、邀约、关系视角）写进**正式存档**。这与部署 DLL 本身不同——DLL 可回滚，**存档的写入不可逆**。建议部署前先复制一份存档。
2. **Bridge 必须同步**：新 DLL 依赖 Bridge 的新字段与默认值（如群聊 `memoryHighlights`、未指定 `turnCount` 时按人数给额度）。**Bridge 进程不重载，游戏就在跟旧代码说话。**
3. **跨度大，先小步验证**：一个月未部署，建议先在**测试存档**里过一遍 F8／F9，再换正式存档。

## 1. 前置检查（只读）

```powershell
cd E:\workspace\projects\stardew-ai-npc.worktrees\story-memory

# 1) 代码健康：一键验证（SMAPI + Bridge + compileall + diff-check）
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_project.ps1
#    期望：SMAPI 全绿；Bridge 若报 5 条失败，是另一条工作线的中间态（见 docs/diagnosis-*.md），不影响本线

# 2) 重载 Bridge，让它加载最新代码（当前 5678 可能仍是旧进程）
$c = Get-NetTCPConnection -LocalPort 5678 -State Listen -ErrorAction SilentlyContinue
if ($c) { Stop-Process -Id $c.OwningProcess -Force }
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_bridge.ps1   # 前台常驻，另开一个窗口
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5678/health             # 期望 {"status":"ok","provider":"cloud"}

# 3) 构建（不自动部署）
dotnet build smapi\StardewAI.NPC.csproj -p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" -p:EnableModDeploy=false -p:EnableModZip=false
```

## 2. 备份（可回滚的前提）

```powershell
$game = 'D:\sbeam\steamapps\common\Stardew Valley'
$stamp = Get-Date -Format 'yyyyMMdd-HHmm'
# 2a) 备份正式 Mod 目录
Copy-Item "$game\Mods\StardewAI.NPC" "$game\Mods\StardewAI.NPC.bak-$stamp" -Recurse
# 2b) 备份正式存档（换成你实际在玩的存档名）
$save = "$env:APPDATA\StardewValley\Saves\<你的存档名>"
Copy-Item $save "$save.bak-$stamp" -Recurse
```

## 3. 部署

```powershell
# 方式 A（推荐，可控）：手动复制构建输出
$game = 'D:\sbeam\steamapps\common\Stardew Valley'
$src  = 'smapi\bin\Debug\net6.0'
Copy-Item "$src\StardewAI.NPC.dll" "$game\Mods\StardewAI.NPC\" -Force
# 若 manifest.json / deps.json 有变化也一并复制（deps.json 与 DLL 同批构建）
Copy-Item "$src\StardewAI.NPC.deps.json" "$game\Mods\StardewAI.NPC\" -Force

# 方式 B：让 MSBuild 自动部署（会覆盖正式 Mod）
# dotnet build smapi\StardewAI.NPC.csproj -p:GamePath="$game" -p:EnableModDeploy=true -p:EnableModZip=false
```

**注意**：`config.json` **不要覆盖**（那是你的 F8/F9 键位、Bridge 地址、群聊策略等设置；新 DLL 会为缺失字段补默认值，例如 `GroupDialogueStrategy` 默认 `multi_turn`）。

## 4. 验证

1. 启动游戏，看 SMAPI 日志（`%APPDATA%\StardewValley\ErrorLogs\SMAPI-latest.txt`）：Mod 正常加载、无异常。
2. **F8 单 NPC 对话**：发一句，确认有回复、无 fallback。
3. **F9 群聊**：接受一张邀约或自由发起（选 2～3 人），发一句，确认**多人依次回应**（`multi_turn` 生效）而不是只有一人说一句。
4. 若要看机读证据：Bridge 侧日志与 `artifacts/` 下的新批次；游戏侧可对照 `SMAPI-latest.txt` 中 Mod 的日志行。
5. 想切回一人一轮：GMCM 里把 `GroupDialogueStrategy` 改成 `turn_based`。

## 5. 回滚

```powershell
$game = 'D:\sbeam\steamapps\common\Stardew Valley'
# 恢复 Mod（把 <stamp> 换成备份时的时间戳）
Remove-Item "$game\Mods\StardewAI.NPC" -Recurse -Force
Rename-Item "$game\Mods\StardewAI.NPC.bak-<stamp>" 'StardewAI.NPC'
# 存档回滚（会丢掉部署后写入的记忆/邀约，请先确认）
Remove-Item "$env:APPDATA\StardewValley\Saves\<你的存档名>" -Recurse -Force
Rename-Item "$env:APPDATA\StardewValley\Saves\<你的存档名>.bak-<stamp>" '<你的存档名>'
```

## 6. 部署后建议补的三件事

- 跑一次 `scripts/start_visual_test.ps1` 之外的真实场景（就是上面第 4 步）——**正式环境从未验证过**，FastTest 隔离 profile 只是替身。
- 记一笔到 `docs/active-work.md`（部署时间、DLL SHA256、验证结果）。
- 若发现回归：先看 `docs/handoff-group-dialogue-2026-09-20.md` 的「十条坑」，再用第 5 节回滚。
