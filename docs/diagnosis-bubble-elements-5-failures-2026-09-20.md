# 诊断：气泡元素线的 5 条失败（2026-09-20 00:45 由通宵会话记录）

> 背景：这条线不是本线（本线做群聊/SMAPI）。夜里跑 Bridge 全量时发现它处于中间态，
> 其中 **1 个 import 错误已被本线修复**（见下"已修"），剩下 5 条是实质工作未完成，
> 需要原作者的设计意图，本线不代改。本文只做诊断，不改任何相关文件。

## 已修（本线改动，一行）

`group_dialogue_review_page.py` 第 7 行把 `NPC_BUBBLE_ALIASES` 从 `npc_bubble_elements` 导入，
而该常量实际定义在 `npc_bubble_catalog.py`。后果是整个 `app` 无法导入 → **Bridge 一旦重启就起不来**
（运行中的 5678 是旧代码，掩盖了这个问题）。已改为从定义处导入，现在 `app` 可正常导入。

## 未修的 5 条失败

| 测试 | 断言要点 |
|---|---|
| `test_npc_bubble_objects.py::test_prop_atlas_covers_exact_specification` | `set(OBJECT_SVGS) == set(spec["objectLibrary"])`：规格里有 76 个物件（`pearl`/`wave`/`saw`/`dice`/`blueprint`…），`npc_bubble_objects.OBJECT_SVGS` 少了大量条目 |
| `test_npc_bubble_elements.py::test_added_characters_follow_the_authoritative_catalog` | 遍历 `ALL_SPEC["npcs"]` 逐个取 `_elements()[npc]`，在 `KeyError: 'Lewis'` 处中断——实现里还没有 Lewis 等角色 |
| `test_npc_bubble_elements.py::test_all_friendship_characters_and_aliases_resolve_to_one_definition` | 好友度名单里的角色与别名要能解析到同一份定义 |
| `test_npc_bubble_frame_materials.py::test_aliases_resolve_styles_glyphs_ornaments_in_browser_javascript` | 别名在浏览器 JS 里也要解析到同一套样式/图案 |
| `test_external_dialogue_lab.py::test_group_dialogue_review_character_frames_use_the_single_element_library` | 回放页要用**单一**元素库（不能存在两份定义） |

## 共同根因

**规格数据领先于实现**：

- 权威规格 `docs/npc-bubble-elements-all-2026-09-19.json` 已经是 **46 个角色 + 76 件物件**的完整规模
- 而实现侧 `npc_bubble_elements.py` / `npc_bubble_objects.py` 仍是**旧的较小规模**（缺 Lewis 等角色、缺大量物件）
- 于是"规格 vs 实现"的相等/包含断言全部失败

这不是 bug，是**重构进行到一半**：先写全规格与测试（红灯），再补实现（绿）。

## 建议的下一步（供原作者判断）—— 已用只读检查缩小范围

**先排除一种可能**：`scripts/build_npc_bubble_elements.py --check` 实测**通过**：

```
好感度名单 47 条 → 独立角色 46 个（登记覆盖 47 条）
  别名复用 4 个，归并组 1 个
审计通过：色相相差 <6° 的角色，底色亮度都拉开了 ≥6 ✅
check-exit=0
```

即**规格 JSON 本身自洽、不需要重建**（`--check` 模式是只读的，审计通过后直接返回，不写任何文件）。

**同时确认了缺失的是哪一步**：该生成器只写规格
（`docs/npc-bubble-elements-all-2026-09-19.json`：**46 角色 / 96 物件 / 19 材质**），
**并不生成实现模块**。所以缺的是「规格 → 实现模块」这一步：需要把 46 个角色的元素定义与 96 件物件
补进 `npc_bubble_elements.py`（`NPC_BUBBLE_ELEMENTS`）与 `npc_bubble_objects.py`（`OBJECT_SVGS`）——
手工补齐，或新增一个把规格同步到实现模块的脚本，然后跑那 5 条测试确认转绿。

顺带一提：别名解析涉及两处，`npc_bubble_catalog.NPC_BUBBLE_ALIASES`（Python 侧）与回放页模板注入的
`NPC_ALIASES`（浏览器侧，见 `group_dialogue_review_page.py` 的 `aliases_json`），两处都要覆盖新角色。

本线**没有执行任何写入操作**（没有重跑生成器、没有改实现模块、没有动该线的测试）。

## 复现命令

```powershell
$env:PYTHONPATH='bridge/src;scripts'
& $py -B -m pytest bridge/tests/test_npc_bubble_elements.py bridge/tests/test_npc_bubble_objects.py `
  bridge/tests/test_npc_bubble_frame_materials.py bridge/tests/test_external_dialogue_lab.py -q -p no:cacheprovider
```
