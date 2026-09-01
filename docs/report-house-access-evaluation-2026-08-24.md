# NPC 房屋随时进入功能评估（2026-08-24）

## 结论

功能技术上可实现，但不建议直接安装或整体复制现成的“解锁所有门”Mod。当前最稳妥的方向是：在 Stardew AI NPC 内做一个可配置的“住宅门访问策略”，只放宽 NPC 住宅入口，保留商店、剧情场所、节日地图和特殊门的原版限制。

推荐实现顺序：

1. 先做只读识别和日志，确认门的 `LockedDoorWarp` 目标地点及 NPC 归属。
2. 通过 NPC／住宅白名单决定是否放宽时间和心级条件。
3. 遇到事件、节日、多人同步或无法确认归属的门时回退原版逻辑。
4. 先在快速测试 profile 验证，再同步完整 Stardrop profile。

## 现成 Mod 对比

### Stardew Hypnos

Nexus 页面明确提供“进入朋友或单身 NPC 房屋”的功能，并有 `MinimumRelationship`、`MinimumFriendshipHearts`、`KeepFriendDoorsOpen`、`NPCsByWarp` 等配置；它还扩展了 NPC 床铺使用。该 Mod 最后一次发布为 2020 年，版本为 1.1.1，目标年代早于当前 Stardew Valley 1.6 组合。来源：<https://www.nexusmods.com/stardewvalley/mods/5935>。

**可借鉴：** 按关系阶段、心级和住宅 warp 做白名单，而不是简单把所有门改成永久开放。

**不直接复用：** 版本过旧，且床铺和住宅访问耦合，会把本项目尚未决定的“是否允许进入卧室／睡 NPC 的床”一起带进来。

### Unlocked Doors

Nexus 页面描述为“多数锁门始终可打开”，包含所有房屋 24/7 和 Pierre 商店特殊时段解锁；它依赖 `bwdyworks`，页面显示为 2019 年旧版本。中文兼容性资料将 `bwdyworks` 与该 Mod 标为过时／非开源。来源：<https://www.nexusmods.com/stardewvalley/mods/4338>、<https://xinglugu.huijiwiki.com/wiki/%E6%A8%A1%E7%BB%84%C2%B7%E6%A8%A1%E7%BB%84%E5%85%BC%E5%AE%B9%E6%80%A7>。

**结论：** 不应作为本项目依赖，也不应照搬其全局解锁策略。

### Door Knock

这是较新的替代思路：不永久解锁，而是在门前敲门；Mod 根据室内 `Door NPC...` 和室外 `LockedDoorWarp ... [NPC] [friendship]` 解析房主，检查 NPC 是否在家，再让 NPC 开门。页面还说明它从门后方 tile 做简单房间检测，并处理多人房主、睡眠和 NPC 正在移动等情况。来源：<https://www.nexusmods.com/stardewvalley/mods/46880>。

**可借鉴：** 保留门的原版动作和地图数据，运行时解析门的归属；需要时再增加“敲门／允许进入”策略。

## 原版和 Mod 的门机制

Stardew Valley 的住宅外门通常在 `Buildings` 图层使用：

```text
Action LockedDoorWarp <toX> <toY> <toArea> <openTime> <closeTime> [NPC] [friendship]
```

官方 Modding Wiki 说明，将时间设为 `600 2600` 可以使门全天开放；最后两个参数还会叠加 NPC 和好感度限制。来源：<https://wiki.stardewvalley.net/Modding%3AMaps>。

本机 SVE 资源中已确认存在这些动作，例如 `Custom_SophiaHouse`、`Custom_ClaireHouse`、`Custom_AndyHouse`、`Custom_SusanHouse`、`Custom_JenkinsHouse` 等；证据来自：

`D:\sbeam\steamapps\common\Stardew Valley\Mods\Stardrop Installed Mods\Stardew Valley Expanded\[CP] Stardew Valley Expanded\assets\Maps\NewLocations\*.tmx`

这说明 SVE 的住宅入口不是固定的原版房屋列表，不能只维护一张 vanilla NPC 名单。

## 可选实现方案

| 方案 | 成本 | 对 SVE／自定义 NPC | 风险 | 结论 |
| --- | --- | --- | --- | --- |
| 直接安装 Unlocked Doors | 低 | 未知 | 旧版、全局解锁、依赖过时 | 不采用 |
| 复制 Hypnos 思路 | 中 | 需要维护 warp 与关系 | 旧代码、床铺功能耦合 | 只借鉴策略 |
| Content Patcher 改所有地图时间为 600/2600 | 中 | 需逐个补丁，SVE 更新易漏 | 与其他地图补丁覆盖顺序冲突 | 不作为主方案 |
| 本 Mod 运行时识别并放宽住宅门 | 中高 | 可解析 SVE 和自定义 NPC | Harmony／动作拦截需严格回退 | 推荐 |
| “敲门后临时放行” | 高 | 适配性好 | 需要 NPC 在家、路径和动画 | 第二阶段增强 |

## 主要风险

1. **剧情和进度绕过：** 商店、社区中心、节日场地和特殊门也可能使用 `LockedDoorWarp`；全局放行会让玩家提前进入商店或触发不该出现的剧情。
2. **地图补丁冲突：** SVE、Ridgeside Village、East Scarp 及其他内容包会编辑地图和门动作；硬编码坐标或 Content Patcher 覆盖容易被加载顺序和更新改坏。
3. **住宅归属不明确：** 一扇门可能属于多人、公共建筑或自定义 NPC，不能只按目标地图名判断。
4. **NPC 状态异常：** 允许进入不等于 NPC 在家；睡眠、移动、事件中和节日状态需要保留原版行为。
5. **事件／多人兼容：** 事件进行中、节日中、多人非主机玩家需要回退或由主机决定，避免传送不同步或把玩家带进事件锁定地图。
6. **玩法边界：** “能进屋”与“能进卧室／睡床／使用室内交互物”是三个不同权限，必须分开配置。

## 复合住宅与“提前进商店”风险（重点）

### 先区分三件事：进门、柜台、服务

原版把“建筑入口是否开放”和“店员是否在柜台、服务是否可用”分开处理。把 `LockedDoorWarp` 的时间改成全天，只能说明玩家可以进地图，不能保证商店界面一定打开；但它会制造一个稳定的提前进店机会：玩家可以在营业前进入室内，站在柜台附近等待店员到位，再尝试触发服务。

原版木匠店就是明确的边界案例：资料记录其建筑通常 9:00 开门，但玩家可以在 Robin 9:40 经过柜台时提前购物；晚上 20:00 Robin 回到柜台附近时也可能再次购物。也就是说，“提前开放建筑”并不是单纯的聊天便利，它可能改变商店服务的可达时间，形成卡点利用。来源：<https://stardewvalleywiki.com/Carpenter%27s_Shop>。

### 住宅与商店共用地图不是少数例外

原版地点名称本身不能用来判断“这是住宅还是商店”。例如：

| 地点 | 住宅居住者 | 同一地点的服务／商店 | 提前进门的主要风险 |
| --- | --- | --- | --- |
| `SeedShop` | Pierre、Caroline、Abigail | Pierre 商店、教堂 | 提前购买、触发教堂／家庭区域事件 |
| `ScienceHouse` | Robin、Demetrius、Maru、Sebastian | 木匠店 | 提前购物、施工相关交互 |
| `AnimalShop` | Marnie、Jas、Shane | Marnie 牧场商店 | 提前购买动物／用品、目录交互 |
| `FishShop` | Willy | 鱼店、船／姜岛相关交互 | 船和剧情入口的开放时机不一致 |
| `Saloon` | Gus | 酒馆商店 | 提前购买食物、酒馆事件入口 |
| `Hospital` | Harvey | 诊所 | 提前触发医疗服务或剧情 |
| `WizardHouse` | Wizard | 法师相关交互 | 特殊传送、剧情或祭坛交互 |
| `AdventureGuild` | Marlon、Gil | 公会商店 | 提前购买、战斗进度相关交互 |

这些地点在本机已安装的 SVE 资源和原版地点数据中都能看到类似的复合用途；SVE 还增加了 `Custom_AndyHouse`、`Custom_ClaireHouse`、`Custom_SophiaHouse` 等自定义住宅，因此不能用“地图名包含 House”作为安全判断。原版地点数据的住宅／商店对应关系见：<https://wiki.stardewvalley.net/Modding:Location_data>。

### 节日和剧情会把风险放大

原版在大多数节日会统一锁住建筑和住宅；夜市等少数活动是例外。全局把门改为全天开放会绕过这层保护，玩家可能在节日地图、事件准备阶段或场景切换前进入不应访问的室内。SVE 的节日地图还会重复定义 `LockedDoorWarp`，所以只修普通地图并不能覆盖全部入口。商店开放时间和节日锁门规则见：<https://stardewvalleywiki.com/Shop_Schedules>。

### 当前 Mod 组合增加了“静态白名单失效”的可能

用户当前 Stardrop profile 中存在 `Shop Tile Framework`。这类框架允许内容包在地图 tile 上添加商店入口，商店不一定能从地点名或原版 NPC 名单推断出来；SVE、Ridgeside Village、East Scarp 也可能通过自定义地图和事件增加服务点。因此，运行时至少要检查：

- 目标地图是否存在 `Shop`、`Carpenter`、`AnimalShop`、`Hospital`、`Blacksmith`、`Boat`、`Wizard` 等服务动作；
- 目标门是否同时连接住宅 NPC 与服务 NPC；
- 当前是否处于节日、事件、婚礼／搬家或多人同步状态；
- 是否存在由 Shop Tile Framework 或其他框架注册的额外商店 tile。

### 推荐的安全分级

不建议做“所有房屋全天开放”开关，而应把门分成三类：

1. **纯住宅门：** 目标地点确认没有商店、服务动作或事件专用入口时，才允许按住宅策略放宽。
2. **复合住宅门：** `SeedShop`、`ScienceHouse`、`AnimalShop`、`FishShop`、`Saloon`、`Hospital`、`WizardHouse`、`AdventureGuild` 以及运行时检测到服务动作的自定义地点，保留原版外门时间；需要聊天时走 NPC 交互或独立聊天入口，不通过提前开门实现。
3. **未知／事件门：** 无法解析归属、处于节日或事件中的门，完全回退原版逻辑，并记录诊断日志。

这套分级能满足“和 NPC 随时聊天”的目标，同时不把“进入 NPC 家”误变成“提前营业”。如果未来确实要支持复合住宅，也应采用“NPC 在家时敲门、临时放行到公共区域”的模式，并让商店柜台、购买动作和剧情入口继续检查原版营业时间与事件条件。

## 建议的产品定义

第一版只做：

- 允许玩家随时进入“已确认属于 NPC 的住宅公共区域”；
- 保留卧室独立门的原版心级限制，后续再决定是否放宽；
- 不修改商店、公共设施、节日地图和事件专用入口；
- 对无法确认归属的门显示原版“门锁着”行为；
- GMCM 提供总开关、住宅模式（原版／朋友／所有 NPC）和事件／节日保护开关；
- 每次放行记录目标地图、门 tile、NPC 归属和原因，便于发现 SVE 或其他 Mod 的新房屋。

## 未解决问题

- Ridgeside Village 和 East Scarp 的部分地图资源不是纯文本 TMX，需在游戏内或通过运行时日志确认其门动作和住宅归属。
- 需要在独立存档中验证：住宅外门、室内卧室门、双 NPC 共用住宅、事件中和节日地图。
- 尚未决定第一版是否允许进入“NPC 不在家时的空屋”，建议允许进入但不自动召回 NPC。

## 允许提前进入后，剧情方案可能产生的二次问题

这里讨论的是“允许提前进入建筑，但仍使用原版事件检查；条件不满足时退出，再重新进入”的方案。它比直接改剧情数据安全，但仍有几个不能忽略的边界。

### 1. 门禁原本可能就是剧情的隐含时间门

事件数据通常同时包含地点、时间、季节、天气、好感度、邮件和事件历史等前置条件；事件引擎并不会自动把商店营业时间当成所有剧情的额外条件。若某个住宅／商店事件允许在 6:00～12:00 进入触发，而原版外门 9:00 才开，放宽门禁后就可能把剧情提前三小时启动。事件一旦真正开始，重新进入不能把它退回“未发生”状态。

这不只影响商店住宅。纯住宅同样可能承载心事件、婚后事件和 Mod 自定义事件，因此“没有商店动作”只能排除提前营业风险，不能单独证明全天开门安全。

因此，“重新进入可以补触发”只适用于**第一次进入时条件不满足且事件没有启动**的情况，不能作为提前启动事件的补救机制。事件前置条件和事件历史机制见：<https://wiki.stardewvalley.net/Modding:Event_data>。

### 2. `firstVisit` 和地点进入触发器可能被提前消耗

原版和内容包可以用首次进入地点生成的 `firstVisit_<location>` 主题，也可以用 `LocationChanged` 触发动作执行逻辑。早进一次再退出，可能改变当天或后续对白上下文；若内容包把首次进入当作剧情条件，第二次进入就不再等价于第一次。`Data/TriggerActions` 默认只执行一次，但也允许内容包设置为可重复，因此重复进出可能暴露重复奖励、重复提示或重复状态更新问题。相关机制见：<https://wiki.stardewvalley.net/Modding:Dialogue>、<https://wiki.stardewvalley.net/Modding:Trigger_actions>。

### 3. NPC 日程与事件演员状态可能暂时不一致

开门只改变玩家能否通过入口，不会自动改变 NPC 日程。玩家可能在一个 NPC 尚未按日程抵达的时间进入空屋，或者 NPC 正在从商店柜台切换到住宅活动。大多数原版事件会自己加载所需演员，但自定义事件可能假设 NPC 已经在地图内；这会造成事件不触发、角色站位不对或入口对白不符合时间的表现。

### 4. “重新进入”会增加事件检查次数，但不应改变事件顺序

正常情况下，事件历史会阻止同一事件重复播放；不过内容包可以定义可重复事件，或在进入地点时执行一次性／可重复触发动作。多次进出同一栋复合建筑，可能让这类 Mod 逻辑比作者预期更频繁地运行。项目不能用“重进一定安全”来替代事件去重。

### 5. 多人模式需要单独处理

单人存档通常只涉及本地玩家；多人模式下，农场工进入地点时会从主机获取真实地点，非主机玩家的影子地点与主机状态可能不一致。若门禁放行只在客户端判断，可能出现一人能进、一人被挡，或事件／NPC 状态不同步。多人机制与地点同步说明见：<https://wiki.stardewvalley.net/Modding:Modder_Guide/Game_Fundamentals>。

### 风险结论

“提前进入、条件不满足就退出、满足后再进入”本身是可行的，但它不能保证所有剧情都无副作用。第一版必须额外保证：

- 事件实际启动前，不修改 `eventSeen`、邮件、任务和好感度状态；
- 对包含 `firstVisit`、`LocationChanged` 或自定义触发动作的地点，默认保留原版门禁，除非确认其只涉及住宅对白；
- 保留原版事件的时间条件，不能用“重新进入”覆盖事件时段；
- 未知内容包、节日、多人模式和事件进行中全部回退原版门禁；
- 对商店／服务地点只开放 AI 聊天，不开放提前柜台交互。
- 对纯住宅也要先确认没有会被原版门禁隐含保护的事件时段；否则采用聊天入口，不直接放开物理门。

## 按当前偏好重新定义目标

用户可以接受剧情提前发生，因此目标不应是“恢复原版事件时间”，而应定义为：

1. **允许事件提前启动；**
2. **不因本 Mod 额外消费事件、邮件、任务或 `firstVisit` 状态；**
3. **不改变事件原本的前置条件和先后依赖；**
4. **事件启动后仍由原版／内容包自己的脚本完成；**
5. **无法识别的自定义事件只记录，不主动重排或补发。**

需要明确边界：Stardew 本身就存在有年份、婚姻、社区升级或其他事件互斥条件的剧情，Mod 也可能定义一次性或可重复事件。因此我们可以保证“门禁 Mod 不新增漏剧情”，但不能承诺“所有原版和所有 Mod 剧情在任何条件下都永远不会错过”。例如事件数据支持 `SawEvent` 前置和事件 ID 历史，某些事件本来就会因前置事件或状态改变而不再适用。相关机制见：<https://wiki.stardewvalley.net/Modding:Event_data>。

最小保护层应是只读和审计：进入建筑时不写事件状态；若事件实际开始，记录事件 ID、地点、游戏时间和来源；若没有事件，不写任何“已访问／已完成”标记。这样可以接受提前剧情，同时把“因本 Mod 漏剧情”的范围压缩到可诊断、可回滚的程度。

## 当前实现状态（2026-08-24）

已在 `codex/story-memory` 隔离工作树中完成第一段可回滚实现：

- `DoorActionParser` 只解析 `LockedDoorWarp`，不改地图文件；它目前是规则/调试工具，生产门禁路径直接使用 Harmony 已解析的参数，避免重复解析；
- `HouseDoorTargetRules` 只有在 NPC 的 `getHome()` 与目标地点匹配时，才把门标为住宅；
- `HouseAccessRules` 将纯住宅、复合建筑、未知地点、节日、事件和多人状态分开决策；
- 复合建筑识别除原版地点类型/名单外，还扫描目标地图的 `Action`/`TouchAction`。已知的 `Shop`、`Store`、`Vendor`、`Buy`、`Purchase`、`Trade`、`Boat`、`Theater`、`Bookseller`、`IceCream`、`Mermaid` 类动作会被视为服务入口；无法识别的自定义动作会进入保守的“未知服务”分支，而不是按纯住宅放行。结果按地点缓存，以覆盖 `Shop Tile Framework` 等在普通 `GameLocation` 上注册商店的情况；
- `HouseAccessController` 在原版 `GameLocation.lockedDoorWarp` 的单次调用上做 Harmony 前置拦截。允许时只把本次调用的时间门和 NPC/心级门槛改为全天，不写 `eventsSeen`、邮件、任务、好感度或地图资源；无法识别或发生异常时原样执行原版方法；
- `EventAuditObserver` 与 `EventAuditSnapshotReader` 在玩家换图时只读记录事件 ID，不修改 `eventsSeen` 等原版状态；审计字段 `ModWouldMutateGameState=false` 只表示本 Mod 没有直接写入，原版地点进入流程仍可能按自身规则更新 `firstVisit`、`eventsSeen` 或剧情状态；
- GMCM 新增 `EnableHouseAccess` 和 `AllowMixedBuildingAccess`，两项默认关闭。第一项只放宽已确认住宅外门，第二项显式允许复合住宅／商店建筑，默认保持关闭；节日、事件进行中和多人模式始终回退原版。

本轮验证：C# 全量 `107` 项通过，Bridge 全量 `73` 项通过（保留 1 条既有 Starlette/httpx 弃用警告），Mod 隔离构建 `0` 警告、`0` 错误。由于现有 `StardewModdingAPI` 进程占用工作树默认 `obj` 输出，本轮使用 `E:\workspace\hub\.stardew-ai-verify` 隔离输出完成构建；随后执行 `start_fast_test.ps1 -IncludeRasmodia -NoLaunch`，快速 profile DLL SHA-256 为 `76AB4CB55BAC0E009D9D67C0AA2D5B8BA6E730F7C4639D92FD98FB6B7389B734`，与验证构建一致。尚未启动游戏存档，因此 Harmony 在真实门前的行为仍需游戏内冒烟测试确认；Stardrop 完整 profile 仍未修改。
