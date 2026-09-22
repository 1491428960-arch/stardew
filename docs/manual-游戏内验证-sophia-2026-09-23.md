# 游戏内验证操作手册 · Sophia「找话题」换面（2026-09-23 01:0x 编写）

> 结论先行：**可以验**。静态分析下来只缺一样东西 —— SVE 本体（受控目录里没有），
> 而 SMAPI 与 ContentPatcher 版本都够。下面是全部前置事实与逐步操作。
>
> ⚠ 本手册是「**怎么做**」，**不是「已授权」**。起游戏仍需你逐次点头（`AGENTS.md` 红线 1）。

## 1. 现在有什么、缺什么（全部实测）

| 项 | 状态 |
|---|---|
| SMAPI | **4.5.2**（`StardewModdingAPI.exe` 文件版本）≥ SVE 要求的 `MinimumApiVersion: 4.1.7` ✅ |
| ContentPatcher | **2.7.3**（真实 dll，706 KB）—— 由 `-IncludeRasmodia` 带进受控目录 ✅ |
| 受控目录 `Mods-AI-FastTest` | `StardewAI.NPC` / `GenericModConfigMenu` / `[CP] Romanceable Rasmodia` / `ContentPatcher` / `CrossModCompatibilityTokens` —— **不含 SVE** ❌ |
| SVE 本体 | `Mods\Stardrop Installed Mods\Stardew Valley Expanded\` 下三件套 |
| 游戏进程 | 未运行 |
| Bridge `:5678` | pid **127092**，含本轮全部改动 ✅ |

**SVE 的依赖（关键，决定了要不要搬一堆前置）**：

| 依赖 | 必需？ | 在哪 |
|---|---|---|
| `FlashShifter.SVE-FTM` | **`IsRequired: true`** | **三件套里的 `[FTM] Stardew Valley Expanded`** ✅ |
| `FlashShifter.SVECode` | **`IsRequired: true`** | **三件套里的 `Stardew Valley Expanded Code`** ✅ |
| `MoreFish` | `IsRequired: false` | 可选，**没有也能加载** |
| `Tanpoponoko.SeasonalOutfits` | `IsRequired: false` | 同上 |
| `Rose.craftables` | `IsRequired: false` | 同上 |

⇒ **两个必需依赖都在三件套内部**，三个可选依赖不装也照样加载。
（我一开始用正则扫 `manifest.json` 找这三个前置，**被骗了** —— 依赖声明的写法与
"我提供"完全一样，扫出来全是假匹配。后来读 SVE 的 `manifest.json` 原文才看清
`IsRequired: false`。）

**体积**：`[CP]` 123.1 MB / 2099 文件、`[FTM]` 0.8 MB / 3 文件、`Code` 0.2 MB / 6 文件
⇒ 约 **124 MB**，拷贝约 1~2 分钟。

## 2. 操作步骤

### 步骤 1 · 同步受控 Mods（**不带** `-Launch`）

```powershell
cd E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory
pwsh -NoProfile -File scripts\start_fast_test.ps1 -IncludeRasmodia
```

`-IncludeRasmodia` 必须带 —— 否则 ContentPatcher 会被清掉而**不补**，SVE 直接加载失败
（脚本的受管白名单是 `StardewAI.NPC` / `GenericModConfigMenu` / `[CP] Romanceable Rasmodia`
/ `ContentPatcher` / `CrossModCompatibilityTokens` 五个名字，先删后拷）。

### 步骤 2 · 把 SVE 三件套拷进受控目录

```powershell
$src = 'D:\sbeam\steamapps\common\Stardew Valley\Mods\Stardrop Installed Mods\Stardew Valley Expanded'
$dst = 'D:\sbeam\steamapps\common\Stardew Valley\Mods-AI-FastTest'
robocopy $src $dst /E /NFL /NDL /NJH /NJS /NP
```

⚠ 只**读**正式 `Mods`，只**写**受控 `Mods-AI-FastTest` —— 不碰正式存档、不改角色资料库。

⚠ 白名单只有那 5 个名字，所以 SVE 放进去**下次同步也不会被删**；但如果你重跑步骤 1
且想回到"干净状态"，手动删掉这三个目录即可（见 §5 回滚）。

### 步骤 3 · 起游戏（**必须投递到 Session 1**）

DSH 以 SYSTEM 跑在 Session 0，直接起游戏**你看不见**：

```powershell
pwsh -File E:\workspace\hub\scripts\invoke-in-session.ps1 `
     -Command 'pwsh -NoProfile -File scripts\start_fast_test.ps1 -IncludeRasmodia -Launch' `
     -WorkDir 'E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory' `
     -TimeoutSeconds 120
```

前提：**你已经登录桌面**（没有 Session 1 就没有落点，脚本会明确抛错）。
SMAPI 会用 `--mods-path` 指向受控目录，**不加载正式 Mods 集合**。

### 步骤 4 · 进游戏

1. **选独立测试存档**（脚本不做存档隔离，这一步归你 —— 别选正式档）
2. 走到 Sophia 面前
3. 反复点「**找话题**」（这条路径不打字，正是本次改动的目标路径）

## 3. 要看什么

| 观察点 | 期望 | 依据 |
|---|---|---|
| 连说 2~3 轮同一件事后，她是否**换面** | 折算已就位 ⇒ 第 2~3 轮就该出禁令 | 报告 §1.1 / §7.1 |
| 换面时她是否**真的避开**被禁的面 | **强引导、不是硬开关** —— 允许偶尔半遵守（真机第 8 轮就是） | 报告 §7.3 |
| 话题是否还"总围着酿酒/创作" | 工作面占比目标 **< 40%**（真机 8 轮已从 58% 降到 37.5%） | 报告 §7.2 |
| **文艺腔是否退** | 本轮改动**不直接**管语气 —— 它改的是"换不换面" | —— |

**看的时候顺手记下**：她说的话如果判不出面（像真机第 4 轮那样），把原话抄给 Bridge 侧，
那正是词表下一批的输入（缝纫那批 §8 就是这么来的）。

## 4. Bridge 侧现状（验证时会用到）

| 实例 | pid | 代码 |
|---|---|---|
| `:5678`（游戏端） | 127092 | **含本轮全部改动** ✅ |
| `:5680`（预览） | 136388 | 已重载，同样含改动 ✅ |

两者都是**独立进程**，不随 DSH 会话结束而消失。

## 5. 回滚

| 要回滚什么 | 怎么做 |
|---|---|
| 受控目录里的 SVE | 删掉 `[CP] Stardew Valley Expanded` / `[FTM] Stardew Valley Expanded` / `Stardew Valley Expanded Code` 三个目录 |
| 整个受控目录 | 重跑步骤 1（会把 5 个受管目录重建），再删 SVE 三个 |
| 游戏 | 直接退出 |
| Bridge | 本手册没动代码；桥跑的是已提交的 `89a10ac` |

## 6. 红线（照抄 `AGENTS.md`，未变）

1. 起游戏 / SMAPI **需逐次授权**；本手册只是把操作备好。
2. 不部署 DLL 到正式 `Mods`、不修改正式存档或角色资料库。
3. 云端生成请求仍需事先确认。
4. 不 `git config --global`；git 命令一律 `git -c safe.directory=<目录>`。
