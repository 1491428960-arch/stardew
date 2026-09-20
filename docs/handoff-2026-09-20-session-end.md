# 交接：2026-09-20 会话结束（语义层排查 + UI 气泡）

> **新会话从这里开始。** 本文件是入口，不重复细节——细节在它指向的文档里。
> 上一段会话跑了约 200 轮，上下文已压缩过一次，因此做此交接。

## 一句话现状

**工作区干净、全部已提交并推送**（`codex/story-memory`）。
今天做完两件大事：**语义层「同概念多实现」排查（修了 12 处 P0）** 和 **F8/F9 气泡统一 + 装饰边框**（已部署到正式 Mods）。

## 当前基线（2026-09-20 19:30 实测）

| | |
|---|---|
| **SMAPI 测试** | **496 passed / 0 failed** |
| **Bridge 测试** | **2975 passed / 0 failed** |
| **构建** | 0 警告 0 错误 |
| **正式 Mods 部署** | DLL 721 KB，SHA256 `BF19FE47…`（含气泡全套效果，游戏内已验证加载） |
| **Bridge 进程** | `127.0.0.1:5678`，跑当前工作树代码 |

## 下一步：从这里接

**权威清单在 `docs/semantic-duplication-audit-2026-09-20.md`**（六路并行审计，64 个候选、48 个确认漂移，按 P0–P3 分级）。

**P0 已修 12 处**（群聊长期记忆从未生效、矿石对话 422、心数阈值漂移、`GetHashCode` 去重失效、群聊 warnings 超限 500、声线卡 key 读错、关系边形状、`recentFacts`/`relationshipWorld` 不进 prompt、parent 拆分……）。

**还没做的**：

| 批次 | 内容 | 备注 |
|---|---|---|
| **P0 剩 2 项** | ① **群聊完全没有回复质量门**（私聊有 `response_guard.check` + 安全兜底替换，群聊只有一句提示词）② **群聊开场对 `guard` 不可见**（`_is_topic_prompt` 只认 `topic_response_contract`/`topic_trigger`） | 都属**中风险**改动，改 prompt 结构 |
| **P1 约 20 条** | 静默不一致：收口判定（五处标记表）、NPC 收口回复（差集 9+7 条）、收口后重开、爱意落地、具体安排（三套判定共用一个 tag 名）、渠道越界、颗粒重复、阶段锁 vs 事件锁…… | **两处都跑、结论相反**——用户看不见，但**同时影响运行时行为与离线评测** |
| **P3** | 结构风险：视口取法（`Gameview` vs `uiViewport`，**有文档证据是没做完的统一**）、`ChatLayoutRules.VisibleMessages` 是死规则、亲吻双重门槛、F8 与交互键两套目标解析 | 当前无可见影响，会腐化 |

## 关键文档

| 用途 | 位置 |
|---|---|
| **本轮审计报告（下一步的依据）** | `docs/semantic-duplication-audit-2026-09-20.md` |
| 工作日志 | `docs/active-work.md`——**最新条目在文件末尾** |
| 待办 | `docs/next-steps-2026-09-20.md` |
| 群聊线现状与坑 | `docs/handoff-group-dialogue-2026-09-20.md` |
| 气泡边框实现说明 | `docs/handoff-npc-bubble-frame-2026-09-20.md` |
| 一键验证 | `pwsh -NoProfile -File scripts/verify_project.ps1` |
| 文档数字一致性 | `pwsh -NoProfile -File scripts/check_doc_consistency.ps1`——**改了测试数或时间戳后必须跑**，它专门抓「只改了三处、漏了第四处」这种漂移（本次交接就靠它抓出一处漏网的 07:26） |

## 运作规则（踩过坑，别重犯）

**构建与测试**（SYSTEM 账户下 ModBuildConfig 探不到游戏目录，**必须显式传 GamePath**）：

```powershell
dotnet build smapi\StardewAI.NPC.csproj -p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" -p:EnableModDeploy=false -p:EnableModZip=false
dotnet test  smapi\tests\StardewAI.NPC.Tests.csproj -p:GamePath="D:\sbeam\steamapps\common\Stardew Valley"
```

**Bridge 测试**（`py` launcher 找不到这个 Python，必须用完整路径）：

```powershell
$env:PYTHONPATH='bridge/src;scripts'; $env:PYTHONIOENCODING='utf-8'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest bridge/tests -q -p no:cacheprovider
```

**git**：所有命令加 `-c safe.directory=E:/workspace/projects/stardew-ai-npc.worktrees/story-memory`；
**push 必须走投递**（凭据窗在 Session 1）：

```powershell
pwsh -File E:\workspace\hub\scripts\invoke-in-session.ps1 -Command 'git -c safe.directory=... push' -WorkDir '<仓库>' -TimeoutSeconds 180
```

**重启 Bridge**：用 WMI 创建进程（**脱离 DSH 进程树**，否则被 job object 连带回收），并显式补齐环境变量（**WMI 不继承调用者环境**）——完整命令见 `docs/handoff-group-dialogue-2026-09-20.md` §5.1。

**部署 DLL 前先关游戏**（文件被加载会复制失败）；**先核对"游戏跑的到底是哪一版"**：比 `bin` 与 `Mods` 的**哈希**，并确认**源文件 mtime 早于 DLL mtime**（**只看时间戳会误判**，今天因此踩过四次）。

**红线**：不启动游戏（游戏内验证需用户逐次授权）；不改正式**存档**；不读写 Key/Token；不改全局设置。**创建 commit 与部署 DLL 已获用户长期授权。**

## 今天最重要的四条教训

1. **候选 ≠ 问题。** 表层扫描 604 处只有 2 处真问题；语义层 64 个候选里 48 个确认漂移。**核实语义是不可省的一步**。
2. **最值钱的线索是「同名 tag 给出不同结论」**——两处都跑、都写同一个诊断字段，却因规则表不同而结论相反。P1 大半由此找出。
3. **「两条路径各自演化」是本项目第一大技术债**：单轮 vs 多轮、私聊 vs 群聊、运行时 guard vs 离线评测、C# vs Python。**修一条路径时一定要问：另一条呢？**
4. **测试会固化 bug。** 既有测试里有一条把「两处不一致」本身写成了断言；另有 11 处喂的是跟着 bug 写的错误 key。**修完测试红了，先怀疑测试，别怀疑修复。**

另外两条操作教训：**改代码不要用正则做结构性删除**（删过头又删少，最终靠精确匹配）；**变异验证之后必须重新构建**（`dotnet test` 会把当时的源码构建进 `bin/`，恢复源码不会自动重建——今天因此把变异版部署出去过一次）。

## 用户可以怎么开场

> 接着 2026-09-20 的进度继续。先读 `docs/handoff-2026-09-20-session-end.md`，
> 然后按 `docs/semantic-duplication-audit-2026-09-20.md` 的清单往下修。
