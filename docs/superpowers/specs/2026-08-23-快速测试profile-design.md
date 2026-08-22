# AI NPC 快速测试 Profile 设计

日期：2026-08-23  
状态：已获用户批准，待实现

## 目标

提供一个可复现的一键快速测试入口，用于验证 `StardewAI.NPC` 的 F8 快捷键、GMCM 配置页、基础 NPC 对话和 Rasmodia 名称回退，不加载完整 SVE profile。

## 非目标

- 不修改现有 `AI-SVE-测试` profile。
- 不覆盖游戏目录下的正式 `Mods` 目录。
- 不修改 C 盘系统目录、注册表、Stardrop 全局配置或正式存档。
- 不替代最终的 SVE、男角色娘化和法师娘化兼容性回归。
- 不实现编译后 C# Mod 的进程内热重载。

## 方案

新增一个 PowerShell 启动器，使用 SMAPI 的 `--mods-path` 参数加载独立目录：

```text
D:\sbeam\steamapps\common\Stardew Valley\Mods-AI-FastTest\
├── StardewAI.NPC\
├── GenericModConfigMenu\
└── （可选）Romanceable Rasmodia 的内容包
```

启动器不依赖 Stardrop 当前选择状态。它从项目构建产物同步 `StardewAI.NPC`，从游戏正式 `Mods` 目录按明确目录名复制 GMCM，默认不复制其他 Mod。

## 用户入口

### 基础模式

```powershell
.\scripts\start_fast_test.ps1
```

用途：验证 Mod 能加载、F8 能响应、GMCM 配置页存在、基础 NPC 对话流程可进入。

### Rasmodia 模式

```powershell
.\scripts\start_fast_test.ps1 -IncludeRasmodia
```

用途：在基础模式上加入已存在的法师娘化内容包，验证 `Wizard` 内部 ID 与 `Rasmodia` 显示名的回退逻辑。

### 参数覆盖

启动器支持以下参数，避免把个人机器路径写死在代码中：

- `-GamePath`：覆盖星露谷安装目录。
- `-FastModsPath`：覆盖独立快速测试目录。
- `-SourceModsPath`：覆盖正式 Mod 源目录。
- `-ProjectRoot`：覆盖项目目录，默认由脚本位置推导。
- `-NoLaunch`：只执行同步和检查，不启动游戏。

脚本不接受任意递归删除参数，也不清空正式 Mod 目录。同步前只删除快速测试目录中由脚本管理的 `StardewAI.NPC`、GMCM 和本脚本标记的可选内容包。

## 同步流程

1. 解析并验证游戏目录、SMAPI 可执行文件、源 Mod 目录和项目构建产物。
2. 创建快速测试目录；目录不存在时才创建。
3. 删除快速测试目录中脚本管理的旧副本，不触碰其他目录。
4. 复制当前构建产物中的 `StardewAI.NPC`。
5. 复制正式 Mod 目录中明确匹配的 GMCM 目录。
6. `-IncludeRasmodia` 时复制明确匹配的法师娘化内容包；找不到时给出可读错误并停止启动。
7. 输出最终 Mod 清单和 DLL SHA-256。
8. 默认调用：

```powershell
StardewModdingAPI.exe --mods-path <FastModsPath>
```

## 安全边界

- 所有路径使用 `-LiteralPath` 和解析后的绝对路径。
- 只允许写入明确的 `FastModsPath`；若目标路径不是该参数指定的快速目录，脚本拒绝执行清理和复制。
- 不使用 `Remove-Item -Recurse` 清理游戏目录、正式 Mod 目录或用户配置目录。
- 启动器不会自动打开正式存档；首次使用应在游戏里新建或选择独立测试存档。
- 启动器只负责进程启动，不等待或强制结束游戏进程。

## 错误处理

- 游戏目录不存在：停止，并指出需要覆盖的参数。
- SMAPI 不存在：停止，不执行复制。
- `StardewAI.NPC.dll` 不存在：停止，不启动旧版本。
- GMCM 不存在：基础模式停止并提示安装；如果仅做代码加载测试，可通过显式参数跳过 GMCM 检查。
- Rasmodia 内容包不存在：只有 `-IncludeRasmodia` 模式停止，基础模式不受影响。
- 快速目录不是独立目录：停止，防止误操作正式 `Mods`。

## 测试设计

### 脚本离线测试

- 缺少游戏目录时返回非零退出码。
- 缺少构建 DLL 时返回非零退出码。
- 目标路径等于正式 `Mods` 目录时拒绝执行。
- `-NoLaunch` 模式只同步并输出清单，不创建游戏进程。
- 基础模式不复制 Rasmodia 内容包。
- `-IncludeRasmodia` 找不到内容包时返回非零退出码。

### 现有自动化测试

继续运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley"
```

### 游戏内烟测

在独立测试存档中：

1. 观察 SMAPI 顶部 `Mods go here` 是否指向快速目录。
2. 确认 `StardewAI.NPC` 和 GMCM 加载成功。
3. 打开 GMCM，确认 `DialogueKey`、`EnableDialogue`、`BridgeEndpoint` 和超时配置可见。
4. 按 F8，确认菜单出现并能发起对话。
5. `-IncludeRasmodia` 模式下确认日志不再出现“未找到 Rasmodia”，并能通过 `Wizard` 内部 ID 找到 NPC。

## 验收标准

- 一条命令即可启动最小 Mod 集合。
- 不加载完整 SVE 时，F8 与 GMCM 烟测可完成。
- 同步过程不会修改正式 `Mods`、现有 Stardrop profile 或正式存档。
- 缺少依赖或路径不安全时先报错，不启动游戏。
- 脚本离线测试和现有 C# 测试均通过。
- 完整 SVE profile 仍作为最终兼容性测试入口保留。

