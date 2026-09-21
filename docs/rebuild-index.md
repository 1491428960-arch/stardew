# 重建默认资料索引

默认索引 `data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json`
是 Bridge 在 Prompt 里读的**角色资料库**。它的构建链条有**两级产物**，改任一级的代码后
**都要连上游一起重生成**——因为**上游产物会把自己的 `warnings` 存进 JSON，下游直接继承**。

## 完整链条

```
游戏目录的原始素材（全程只读）
  ├─ artifacts/corpus/vanilla/                          ← 解包的 Characters/Dialogue
  ├─ <游戏>/Content (unpacked)/Data/Events/              ← 解包的 Data/Events
  ├─ <游戏>/Content (unpacked)/Data/                    ← 解包的 Data/ExtraDialogue（2026-09-23 新增）
  ├─ <游戏>/Mods/…/Stardew Valley Expanded/[CP] Stardew Valley Expanded
  └─ <游戏>/Mods/…/[CP] Romanceable Rasmodia
        ↓  scripts/export_dialogue_corpus.py
      artifacts/corpus/<批次>/vanilla-sve-rasmodia-dialogue-corpus.json      ← 一级产物（语料）
        ↓  scripts/build_profile_index.py
      data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json  ← 二级产物（索引）
```

## 命令（2026-09-23 实测通过）

```powershell
$py  = 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe'
$env:PYTHONPATH = 'bridge/src;scripts'
$game  = 'D:\sbeam\steamapps\common\Stardew Valley'
$batch = 'artifacts/corpus/20260923-extra-dialogue'      # 换批次名即可，旧产物不覆盖

# 1) 语料
& $py -B scripts/export_dialogue_corpus.py `
  --vanilla-root 'artifacts/corpus/vanilla' `
  --vanilla-events-root "$game\Content (unpacked)\Data\Events" `
  --vanilla-extra-dialogue-root "$game\Content (unpacked)\Data" `
  --mod-root "$game\Mods\Stardrop Installed Mods\Stardew Valley Expanded\[CP] Stardew Valley Expanded" `
  --mod-root "$game\Mods\Stardrop Installed Mods\[CP] Romanceable Rasmodia" `
  --locale zh-CN `
  --output "$batch/vanilla-sve-rasmodia-dialogue-corpus.json"

# 2) 索引
& $py -B scripts/build_profile_index.py `
  --persona-dir data/personas `
  --corpus "$batch/vanilla-sve-rasmodia-dialogue-corpus.json" `
  --vanilla-root 'artifacts/corpus/vanilla' `
  --vanilla-events-root "$game\Content (unpacked)\Data\Events" `
  --vanilla-extra-dialogue-root "$game\Content (unpacked)\Data" `
  --vanilla-locale zh-CN `
  --runtime-samples 'artifacts/corpus/runtime-dialogue-samples.sample.jsonl' `
  --output 'data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json'
```

### `--vanilla-extra-dialogue-root` 是什么（2026-09-23 加）

指向**已解包的 `Content (unpacked)/Data`**。它同时打开**两条入口**：

| | 入口 | 判据 | 本轮条数 |
|---|---|---|---|
| **A** | vanilla `Data/ExtraDialogue.<locale>.json` | 键的**第一段**是 NPC 名（`Birdie0` / `Morris_Greeting`） | **+63** 条样本 |
| **B** | CP mod 的 `Data/ExtraDialogue` Target | 键的**任意段**是 NPC 名（SVE 把角色名写在尾部：`SummitEvent_Dialogue3_Sophia`） | **+17** 条样本 |

- **NPC 名单**取自同目录树的 `Data/Characters.json` ∪ `Strings/NPCNames.<locale>.json`
  （它补上了 `Data/Characters.json` 没有的 `ProfessorSnail`）∪ CP 里 `Target: Data/Characters`
  的 Entries 键（SVE 原创角色 Sophia / Victor / Olivia / Claire / Lance / Apples / Scarlett 只在这里）。
  **名单读不到就一条都不收**并出警告 —— 没有名单就无法区分"角色键"与"场景键"。
- **不收无主键的场景键**（`PurchasedItem_*` 34 / `SummitEvent_*` 31 / `Mines_*` 7 / `NewChild_*` 4 …
  共 91 条）：说话人由运行时上下文决定（谁在跟你说话、谁是你的配偶），猜错比漏收更坏。
- 语料里的来源标为 `evidenceKind = extra_dialogue`（**场景台词**），与日常对白 `dialogue`、
  事件脚本 `event_dialogue` 三分开 —— 日后要按来源筛（例如"低关系阶段说了婚后的话"）就看这个字段。
- **键名里写着 `Gift` / `Festival` 的照样收**：`Data/ExtraDialogue` 的条目按定义就是"某个情境下
  说的话"，键名说的是**什么时候说**，不是"这不是他平时的口吻"。该豁免**只对这一个来源开口**，
  其它来源的 `*Gift*` / `*Festival*` 键仍被排除（那些大量是模板化台词）。

## 验收判据（对得上才算成功）

| | 期望值（2026-09-23） | 上一版 |
|---|---|---|
| 语料 `records` | **14063** | 13935 |
| 语料按来源 | `FlashShifter.StardewValleyExpandedCP` **6683**、`Nom0ri.RomRas` **2231**、`vanilla` **5149** | 6666 / 2176 / 5093 |
| 索引 `profiles` | **139** | 137 |
| 索引 `styleSamples` / `speechEvidence` | **10213** / **10213** | 10084 / 10084 |
| 索引 `knowledgeFacts` | **49** | 48 |
| 索引 `warnings` | **10** | 10 |

**数字为什么变 —— 下次重建前先读这段，否则会把正常漂移误判成"重建失败"**：

| 项 | 条数（样本） | 口径 |
|---|---|---|
| 方案 A（vanilla 表） | +63 | 代码改动，**可复现** |
| 方案 B（CP 的 ExtraDialogue） | +17 | 代码改动，**可复现** |
| `Birdie_NoGift` + `Robin_*_Festival` | +3 | 窄豁免（只对 `extra_dialogue` 放开礼物类/节日类键名判据） |
| `data/compatibility/ESR.json` / `CFDE.json` / `SVE.json` | **+47** | ⚠ **不是代码改动**：这些 mod 文件是 **2026-09-21 10:15~10:22** 才装入的，而旧语料生成于 09-20 08:44 |
| `data/compatibility/Juna.json` | **−1** | ⚠ **不是代码改动**：mod 更新后该条变成未解析的 `{{i18n:…}}`，被清洗规则丢弃 |

**所以：mod 一更新，`records` / `styleSamples` 就会漂。**对不上时先按上表归因，
再决定是"重建失败"还是"素材变了"。**别把本表当永久基线照抄。**

**按来源对不上，就是 mod 传错了。** 2026-09-20 踩过这个坑：`[CP] Romanceable Rasmodius SVE`
的 UniqueID 是 `Parrot.RomRas`（只出 1263 条），而旧语料要的是 `Nom0ri.RomRas`（2176 条），
对应目录是 `[CP] Romanceable Rasmodia`——**早期报告里写的路径已经过时**。
一律用各目录 `manifest.json` 的 `UniqueID` 核对（`Nom0ri.RomRas` / `Parrot.RomRas` /
`Dacar.SeasRomRasmodia` 三个都装在本机），不要照抄文档里的目录名。

## 三个坑

1. **`warnings` 会被下游继承。** 语料 JSON 里存着自己的 `warnings`，索引构建会照单全收。
   所以修好产生警告的代码（例如 `corpus.py::_warn_for_unpacked_sources`）**还必须重生成语料**，
   否则索引里的旧警告一条都不会少——这正是 2026-09-20 那次"改了代码但数字没变"的原因。
2. **路径含 `[` `]` 时必须用 `-LiteralPath`。** PowerShell 默认把方括号当通配符，
   `Test-Path '…\[CP] X'` 会**假报"不存在"**，`Get-ChildItem -Filter *.xnb` 也会数成 0 个。
3. **⭐ personas 被并行线改动时，素材级逐条对照会错位。**
   2026-09-23 实测：跑"素材字面 vs 原话"的逐条回测时，另一条线正在改
   `data/personas/sve.json`，于是同一个 `sve.json / Sophia / 1` 在前后两次采样里
   **指的是两条不同的素材**，被误当成"索引变化让最佳匹配换了人"，白追了一轮。
   **做法**：要么在两次采样之间锁定一份 personas 副本，要么只信"同一时刻跑两次"的口径
   （`.tmp/facet-coverage/a2_backtest.py` 就是后者）。

## 替换默认索引前的安全检查

```powershell
# 当前默认与 v3 备份是否相同（相同则可随时回退）
(Get-FileHash 'data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json').Hash -eq `
(Get-FileHash 'data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue-v3.json').Hash
```

替换后**必须确认 `profiles` / `styleSamples` / `knowledgeFacts` 与替换前一致**——
2026-09-20 那次替换前实测三者分别为 `137` / `10084` / `43`，与旧索引逐项相同，
只有 `warnings` 从 `67` 降到 `10`，因此替换是零内容变更。
（2026-09-23 补上 ExtraDialogue 入口后，这三个数是 **139 / 10213 / 49** —— 见上面的验收表。）

## 重新加载

索引是 Bridge **启动时**读入的，改文件后**必须重启 Bridge** 才会生效（旧进程内存里仍是旧索引）。
