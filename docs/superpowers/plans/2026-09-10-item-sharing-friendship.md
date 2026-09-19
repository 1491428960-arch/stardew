# 物品分享与原版好感度实现计划

> **面向 AI 代理的工作者：** 在当前 `story-memory` 工作树内按任务顺序执行；保留全部既有未提交修改，不创建 Git commit，不启动 Stardew Valley/SMAPI。

**目标：** 将物品“分享”定义为一次明确的游戏内消耗行为，并让食物、矿石、宝石、晶球、文物和收藏品进入分享路径；成功分享后由游戏端安全地增加少量原版 friendship points，NPC 对白只描述物品互动，不自行决定消耗或修改好感度。

**架构：** C# 端在选中物品时完成受控分类，在分享确认后一次性扣除 1 个物品并尝试发放固定 `+5` friendship points；同一 NPC 同一游戏日最多发放一次分享奖励，Bridge 重试不会再次发放。Bridge 只接收游戏端已经确定的 `itemKind`、`consumesItem` 和 `friendshipAwarded` 上下文，并明确“消耗不等于食用”，模型不能改变游戏状态。

**技术栈：** .NET 6 / SMAPI C#、xUnit、Python 3.10+、Pydantic、现有 Bridge PromptBuilder。

---

### 任务 1：扩展物品分类与分享规则

**文件：**
- 修改：`smapi/ItemInteractionModels.cs`
- 测试：`smapi/tests/ItemInteractionRulesTests.cs`

- [ ] **步骤 1：编写失败测试**

新增行为测试，覆盖：

```csharp
Assert.Equal(ItemInteractionKind.Food, ItemInteractionRules.Classify("-7"));
Assert.Equal(ItemInteractionKind.Mineral, ItemInteractionRules.Classify("-12"));
Assert.Equal(ItemInteractionKind.Artifact, ItemInteractionRules.Classify("artifact"));
Assert.True(ItemInteractionRules.CanShare(ItemInteractionKind.Mineral));
Assert.True(ItemInteractionRules.CanShare(ItemInteractionKind.Artifact));
Assert.True(ItemInteractionRules.CreatePreview(
    new ItemSnapshot("-12", "石英", "矿石", 0, ItemInteractionKind.Mineral),
    ItemInteractionAction.Share).ConsumesItem);
Assert.False(ItemInteractionRules.CreatePreview(
    new ItemSnapshot("(BC)Bench", "长椅", "家具", 0, ItemInteractionKind.Other),
    ItemInteractionAction.Display).ConsumesItem);
```

保留旧构造函数调用兼容性，并增加测试证明 `Gift` 仍然需要显式确认。

- [ ] **步骤 2：运行测试确认红灯**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~ItemInteractionRulesTests
```

预期：新增断言因 `ItemInteractionKind`、分类规则和分享消耗规则尚不存在而失败；不得把编译环境错误当作功能失败。

- [ ] **步骤 3：编写最少实现代码**

增加受控的 `ItemInteractionKind` 和 `ItemSnapshot` 可选字段；把食品/饮料、矿石/宝石/晶球、文物/收藏品标记为可分享；分享预览固定 `ConsumesItem=true`，展示和待确认赠送不消耗。未知类别默认不可分享，避免误伤种子、工具、家具、任务道具等物品。

- [ ] **步骤 4：运行测试确认通过**

运行同一步骤 2 的命令，预期 `ItemInteractionRulesTests` 全部通过。

---

### 任务 2：增加一次性物品消耗与每日分享奖励账本

**文件：**
- 创建：`smapi/ShareFriendshipLedger.cs`
- 修改：`smapi/VanillaGiftHandler.cs`
- 修改：`smapi/ChatInputMenu.cs`
- 修改：`smapi/FaceToFaceConversationCoordinator.cs`
- 修改：`smapi/VisualTestHarness.cs`
- 测试：`smapi/tests/ShareFriendshipLedgerTests.cs`

- [ ] **步骤 1：编写失败测试**

新增纯规则测试：

```csharp
var ledger = new ShareFriendshipLedger();
Assert.True(ledger.TryClaim("Abigail", gameDay: 42));
Assert.False(ledger.TryClaim("Abigail", gameDay: 42));
Assert.True(ledger.TryClaim("Abigail", gameDay: 43));
Assert.True(ledger.TryClaim("Dwarf", gameDay: 42));
```

增加物品消耗契约：分享必须在本地确认物品仍存在且堆叠大于零后扣除一个；Bridge 请求失败、fallback 或重试不得再次扣除或再次领取好感奖励。展示和取消不消耗。

- [ ] **步骤 2：运行测试确认红灯**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~ShareFriendshipLedgerTests
```

预期：因账本类型和分享事务尚不存在而失败。

- [ ] **步骤 3：编写最少实现代码**

实现：

- `ShareFriendshipLedger` 按 `gameDay + npcId` 去重；NPC 名称大小写不敏感；跨游戏日自动开启新账本窗口。
- 分享流程先由 C# 校验并扣除一个物品，再调用原版 `Farmer.changeFriendship(5, npc)` 或当前引用版本的等价原版入口；不得直接让 Bridge 决定数值。
- 只有真正存在 friendship record 的 NPC 才发放奖励；发放失败时不重复扣除物品，并向 UI 写入可理解的本地提示。
- `ChatInputMenu` 保存一个由 `ModEntry` 生命周期共享的账本，通过 `FaceToFaceConversationCoordinator` 传入普通菜单；视觉测试菜单使用独立账本，不影响正式运行态。
- 赠送继续完全走现有 `VanillaGiftHandler.TryGive`，不套用分享奖励。

- [ ] **步骤 4：运行测试确认通过**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~ShareFriendshipLedgerTests
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~ItemInteractionRulesTests
```

预期：账本、消耗、展示和赠送边界全部通过。

---

### 任务 3：把确定后的物品语义传给 Bridge

**文件：**
- 修改：`smapi/ConversationModels.cs`
- 修改：`smapi/ItemInteractionModels.cs`
- 修改：`bridge/src/stardew_ai_bridge/models.py`
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
- 测试：`smapi/tests/BridgeClientTests.cs`
- 测试：`bridge/tests/test_chat_intents.py`
- 测试：`bridge/tests/test_prompts.py`

- [ ] **步骤 1：编写失败测试**

新增请求契约，要求 item context 可安全携带：

```json
{
  "itemKind": "mineral",
  "consumesItem": true,
  "friendshipAwarded": 5
}
```

同时测试 Prompt 明确要求：分享已由游戏端消耗物品，但“消耗”不等于 NPC 一定在吃；只有 Dwarf/Abigail 的受控彩蛋上下文允许口感/味道玩笑；模型不能声明自己修改了背包或好感度。

- [ ] **步骤 2：运行测试确认红灯**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
python -B -m pytest -q -p no:cacheprovider bridge/tests/test_chat_intents.py bridge/tests/test_prompts.py
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~BridgeClientTests
```

预期：新增字段尚未被模型和 Prompt 投影，相关断言失败。

- [ ] **步骤 3：编写最少实现代码**

在两端增加可选、白名单字段；Bridge 对未知字段继续严格拒绝，兼容旧 item payload；Prompt 只使用 C# 已确定的 item kind/action/consumption/award 状态，不计算原版喜好，不生成游戏状态副作用。

- [ ] **步骤 4：运行测试确认通过**

重复步骤 2 的命令，预期 Bridge item intent、Prompt 和 C# BridgeClient 契约全部通过。

---

### 任务 4：接入选择器和 UI 行为

**文件：**
- 修改：`smapi/InventoryItemPicker.cs`
- 修改：`smapi/ChatInputMenu.cs`
- 修改：`smapi/ModEntry.cs`
- 测试：`smapi/tests/ItemInteractionRulesTests.cs`

- [ ] **步骤 1：编写失败测试**

补充选择器规则测试：食品、饮料、矿石、宝石、晶球、文物可以点击“分享”；家具、工具、武器、服装、戒指、种子、肥料、鱼饵、炸弹、任务道具和未知类别的“分享”按钮不可用；展示按钮始终不消耗。

- [ ] **步骤 2：运行测试确认红灯**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~ItemInteractionRulesTests
```

- [ ] **步骤 3：编写最少实现代码**

选择器根据受控分类禁用不可分享物品；分享确认成功后立即完成一次扣除和一次奖励领取，再发 Bridge 请求。请求失败只显示“物品已分享，但暂时没有收到回复”，不得自动重放事务。分享对白使用“和你分享/拿来一起看看/让你感受一下”等中性语义，不强制写成吃东西。

- [ ] **步骤 4：运行测试确认通过**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~ItemInteractionRulesTests
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~FaceToFaceConversationCoordinatorTests
```

---

### 任务 5：全量离线验证并更新活动记录

**文件：**
- 修改：`docs/active-work.md`

- [ ] **步骤 1：运行 C# 全量测试**

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：全部测试通过。

- [ ] **步骤 2：运行 Bridge 全量测试和编译检查**

```powershell
$env:PYTHONPATH='bridge/src'
python -B -m pytest -q -p no:cacheprovider bridge/tests
py -3.10 -B -m compileall -q bridge/src scripts
git diff --check
```

- [ ] **步骤 3：更新活动记录并检查工作树**

在 `docs/active-work.md` 顶部追加本轮实际测试数字、修改范围和限制：没有启动游戏/SMAPI、没有发起云端请求、没有改正式 Mods/存档、没有提交；明确说明 friendship 需要用户在隔离测试存档中实机确认。

- [ ] **步骤 4：最终验收**

只报告新鲜命令输出支持的结论；不把单元测试、Bridge 健康检查或编译成功表述成游戏内物品扣除和好感度已经实机验证。

