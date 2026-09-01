# 游戏内中文输入法兼容实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:executing-plans` 逐任务实现此计划；每个步骤完成后更新复选框并保留实际测试输出。

**目标：** 保留 Stardew 原生 `TextBox`，修复聊天菜单的焦点/订阅生命周期，使常用中文 IME 已提交字符、退格、光标和连续发送稳定工作。

**架构：** 将 `Game1.keyboardDispatcher.Subscriber` 的占用封装为可单测的 `KeyboardSubscriberLease<T>`；`ChatInputMenu` 在 `SelectMe()` 前获取 lease，关闭/暂停/恢复时通过 lease 幂等操作。继续使用 vanilla 的 `KeyboardDispatcher`，不拼接按键，也不引入 Windows 原生 IME hook。

**技术栈：** C# / .NET 6、xUnit、Stardew Valley 1.6.15.24356、MonoGame 3.8、SMAPI 4.5.2。

---

### 任务 1：确认测试项目的 ModBuild 部署目标已隔离

**文件：**
- 无文件修改；验证现有项目属性和命令行参数

- [x] **步骤 1：编写失败前的基线命令**

运行：

```powershell
$env:OS='Windows_NT'
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

记录当前是否出现 `manifest.json` 或 `DeployModTask` 错误；该步骤只确认现状，不改源文件。

- [x] **步骤 2：确认无需删除测试项目自己的 ModBuildConfig 包引用**

基线已经证明测试项目保留现有包引用也不会触发部署错误；不修改 `smapi/tests/StardewAI.NPC.Tests.csproj`，统一使用 `-p:EnableModDeploy=false -p:EnableModZip=false`。

- [x] **步骤 3：运行完整 C# 测试确认部署目标不再介入**

运行：

```powershell
$env:OS='Windows_NT'
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

实际：主项目和测试项目均显示 `EnableModDeploy: false, EnableModZip: false`，C# 测试 134/134 通过，没有缺失 `manifest.json`。

- [x] **步骤 4：记录无文件改动**

本任务没有源文件改动，不创建空提交；后续测试命令沿用上述两个 `EnableMod*` 参数。

### 任务 2：为键盘订阅 lease 编写失败测试

**文件：**
- 创建：`smapi/tests/KeyboardSubscriberLeaseTests.cs`
- 创建：`smapi/KeyboardSubscriberLease.cs`

- [x] **步骤 1：先只写测试**

测试必须覆盖以下具体行为，测试先引用尚不存在的 `KeyboardSubscriberLease<T>`：

```csharp
[Fact]
public void AcquireStoresPreviousSubscriberBeforeReplacingIt()
{
    var previous = new object();
    var input = new object();
    object? current = previous;
    var lease = new KeyboardSubscriberLease<object>(
        () => current,
        value => current = value);

    lease.Acquire(input);
    Assert.Same(input, current);
    lease.Release();

    Assert.Same(previous, current);
}

[Fact]
public void ReleaseRestoresPreviousSubscriberOnlyWhenLeaseStillOwnsHost()
{
    var previous = new object();
    var input = new object();
    object? current = previous;
    var lease = new KeyboardSubscriberLease<object>(() => current, value => current = value);

    lease.Acquire(input);
    lease.Release();

    Assert.Same(previous, current);
}

[Fact]
public void ReleaseDoesNotOverwriteAThirdPartySubscriber()
{
    var previous = new object();
    var input = new object();
    var thirdParty = new object();
    object? current = previous;
    var lease = new KeyboardSubscriberLease<object>(() => current, value => current = value);

    lease.Acquire(input);
    current = thirdParty;
    lease.Release();

    Assert.Same(thirdParty, current);
}

[Fact]
public void SuspendResumeAndReleaseAreIdempotent()
{
    var previous = new object();
    var input = new object();
    object? current = previous;
    var lease = new KeyboardSubscriberLease<object>(() => current, value => current = value);
    lease.Acquire(input);

    lease.Suspend();
    lease.Suspend();
    Assert.Null(current);
    lease.Resume();
    lease.Resume();
    Assert.Same(input, current);
    lease.Release();
    lease.Release();
    Assert.Same(previous, current);
}
```

- [x] **步骤 2：运行测试确认正确失败**

运行：

```powershell
$env:OS='Windows_NT'
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~KeyboardSubscriberLeaseTests -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：编译失败，原因是 `KeyboardSubscriberLease<T>` 尚未定义；若出现项目部署错误，先完成任务 1。

- [x] **步骤 3：实现最小 lease**

在 `smapi/KeyboardSubscriberLease.cs` 实现公开、无游戏依赖的泛型类：保存 getter/setter、`Acquire(T subscriber)`、`Suspend()`、`Resume()`、`Release()`；`Release()` 只在当前值仍等于已获取的 subscriber 时恢复 previous，重复调用不写入状态。

- [x] **步骤 4：运行测试确认通过**

重复步骤 2 命令，预期该测试类全部 PASS，输出中无 ModBuild 部署错误。

- [x] **步骤 5：提交 lease**

```powershell
git add smapi/KeyboardSubscriberLease.cs smapi/tests/KeyboardSubscriberLeaseTests.cs
git commit -m "feat(输入): 添加键盘订阅生命周期 lease"
```

### 任务 3：接入 ChatInputMenu 并修复焦点回归

**文件：**
- 修改：`smapi/ChatInputMenu.cs`
- 修改：`smapi/tests/KeyboardSubscriberLeaseTests.cs`

- [x] **步骤 1：用 lease RED→GREEN 测试覆盖菜单生命周期契约**

任务 2 的 4 个 fake getter/setter 测试已经覆盖：获取前保存 previous、第三方接管不被覆盖、Suspend/Resume 幂等、Release 幂等；不再添加无法实例化完整 `Game1` 的伪集成测试。

- [x] **步骤 2：运行测试确认新契约已因缺少 lease 失败**

实际：lease 测试在生产类型创建前因 `KeyboardSubscriberLease<>` 未定义而编译失败，随后最小实现使 4/4 通过。

- [x] **步骤 3：修改 ChatInputMenu 的订阅顺序和更新循环**

具体改动：

1. 用 `KeyboardSubscriberLease<IKeyboardSubscriber>` 替换 `previousKeyboardSubscriber` 字段。
2. 构造 `TextBox` 后先创建 lease，再调用 `Acquire(inputBox)`，最后调用 `inputBox.SelectMe()`；旧 subscriber 必须在任何 `SelectMe()` 前保存。
3. 从 `update(GameTime)` 删除 `inputBox.Update()`，保留 `base.update(time)`；输入框选择只在 `receiveLeftClick`、`ResumeInput` 和构造时发生。
4. `CleanupKeyboardSubscriber()` 改为 lease 的 `Release()`。
5. `SuspendInput()`/`ResumeInput()` 改为 lease 的 `Suspend()`/`Resume()`，并在恢复时调用 `inputBox.SelectMe()`。
6. 保留 Enter、Escape、退格和 `RecieveTextInput` 的 vanilla 链路，不添加按键拼接代码。

- [x] **步骤 4：运行 C# 测试和全量测试**

先运行筛选测试，再运行：

```powershell
$env:OS='Windows_NT'
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：新测试与既有 C# 测试全部 PASS。

- [x] **步骤 5：构建并记录 DLL SHA256**

运行：

```powershell
$env:OS='Windows_NT'
dotnet build smapi/StardewAI.NPC.csproj --no-restore -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
Get-FileHash smapi/bin/Debug/net6.0/StardewAI.NPC.dll -Algorithm SHA256
```

预期：构建成功，并保存源码 DLL 哈希用于部署核对。

- [ ] **步骤 6：进行真实游戏输入法回归**

使用 `scripts/start_ai_npc_test.ps1 -Launch` 启动 FastTest，记录 SMAPI 版本和实际 DLL 哈希；在游戏内依次验证：

1. 微软拼音输入“中文测试”，选择候选词后发送；
2. 鼠标移出输入框到对话区后继续输入；
3. 退格、中文标点、Enter 发送、连续两次发送；
4. 打开/关闭物品选择器后继续输入；
5. 关闭菜单后检查 SMAPI 日志无残留输入订阅异常。

单独记录“字符提交成功”和“预编辑候选窗位置”两个结果；MonoGame 3.8 不绘制 SDL 预编辑串，不能把候选窗问题误报为字符提交失败。

- [ ] **步骤 7：提交接线改动**

```powershell
git add smapi/ChatInputMenu.cs smapi/tests/KeyboardSubscriberLeaseTests.cs
git commit -m "fix(输入): 修复聊天菜单中文输入焦点生命周期"
```

## 完成门禁

- C# 新测试先 RED 后 GREEN；
- 全量 C# 测试无部署目标错误；
- 实际 FastTest profile 中的 DLL SHA256 与构建输出一致；
- SMAPI 日志确认加载该 DLL；
- 游戏内中文提交、鼠标移出后输入、连续发送和物品菜单恢复均通过；
- 不声称 MonoGame 3.8 支持自绘拼音预编辑串。
