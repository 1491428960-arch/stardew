# 重建默认资料索引

默认索引 `data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json`
是 Bridge 在 Prompt 里读的**角色资料库**。它的构建链条有**两级产物**，改任一级的代码后
**都要连上游一起重生成**——因为**上游产物会把自己的 `warnings` 存进 JSON，下游直接继承**。

## 完整链条

```
游戏目录的原始素材（全程只读）
  ├─ artifacts/corpus/vanilla/                          ← 解包的 Characters/Dialogue
  ├─ <游戏>/Content (unpacked)/Data/Events/              ← 解包的 Data/Events
  ├─ <游戏>/Mods/…/Stardew Valley Expanded/[CP] Stardew Valley Expanded
  └─ <游戏>/Mods/…/[CP] Romanceable Rasmodia
        ↓  scripts/export_dialogue_corpus.py
      artifacts/corpus/<批次>/vanilla-sve-rasmodia-dialogue-corpus.json      ← 一级产物（语料）
        ↓  scripts/build_profile_index.py
      data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json  ← 二级产物（索引）
```

## 命令（2026-09-20 实测通过）

```powershell
$py  = 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe'
$env:PYTHONPATH = 'bridge/src;scripts'
$game  = 'D:\sbeam\steamapps\common\Stardew Valley'
$batch = 'artifacts/corpus/20260920-xnb-collapsed'      # 换批次名即可，旧产物不覆盖

# 1) 语料
& $py -B scripts/export_dialogue_corpus.py `
  --vanilla-root 'artifacts/corpus/vanilla' `
  --vanilla-events-root "$game\Content (unpacked)\Data\Events" `
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
  --vanilla-locale zh-CN `
  --runtime-samples 'artifacts/corpus/runtime-dialogue-samples.sample.jsonl' `
  --output 'data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json'
```

## 验收判据（对得上才算成功）

| | 期望值 |
|---|---|
| 语料 `records` | **13935** |
| 语料按来源 | `FlashShifter.StardewValleyExpandedCP` **6666**、`Nom0ri.RomRas` **2176**、`vanilla` **5093** |
| 索引 `profiles` | **137** |
| 索引 `styleSamples` / `speechEvidence` | **10084** / **10084** |
| 索引 `knowledgeFacts` | **43** |

**按来源对不上，就是 mod 传错了。** 2026-09-20 踩过这个坑：`[CP] Romanceable Rasmodius SVE`
的 UniqueID 是 `Parrot.RomRas`（只出 1263 条），而旧语料要的是 `Nom0ri.RomRas`（2176 条），
对应目录是 `[CP] Romanceable Rasmodia`——**早期报告里写的路径已经过时**。
一律用各目录 `manifest.json` 的 `UniqueID` 核对（`Nom0ri.RomRas` / `Parrot.RomRas` /
`Dacar.SeasRomRasmodia` 三个都装在本机），不要照抄文档里的目录名。

## 两个坑

1. **`warnings` 会被下游继承。** 语料 JSON 里存着自己的 `warnings`，索引构建会照单全收。
   所以修好产生警告的代码（例如 `corpus.py::_warn_for_unpacked_sources`）**还必须重生成语料**，
   否则索引里的旧警告一条都不会少——这正是 2026-09-20 那次"改了代码但数字没变"的原因。
2. **路径含 `[` `]` 时必须用 `-LiteralPath`。** PowerShell 默认把方括号当通配符，
   `Test-Path '…\[CP] X'` 会**假报"不存在"**，`Get-ChildItem -Filter *.xnb` 也会数成 0 个。

## 替换默认索引前的安全检查

```powershell
# 当前默认与 v3 备份是否相同（相同则可随时回退）
(Get-FileHash 'data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json').Hash -eq `
(Get-FileHash 'data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue-v3.json').Hash
```

替换后**必须确认 `profiles` / `styleSamples` / `knowledgeFacts` 与替换前一致**——
2026-09-20 那次替换前实测三者分别为 `137` / `10084` / `43`，与旧索引逐项相同，
只有 `warnings` 从 `67` 降到 `10`，因此替换是零内容变更。

## 重新加载

索引是 Bridge **启动时**读入的，改文件后**必须重启 Bridge** 才会生效（旧进程内存里仍是旧索引）。
