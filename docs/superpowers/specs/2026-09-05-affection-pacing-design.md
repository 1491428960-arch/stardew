# NPC 亲密表达节奏调节设计

## 目标

降低高好感 NPC 在普通对话中的情话密度和句式重复，优先解决 Rasmodia 连续使用强专属表达的问题，同时检查 Sophia、Shane、Sebastian、Alex 是否存在同类过量表达。调整只影响高好感主动亲密提示和质量评测，不改变角色资料、正式 Mods、存档或 `qwen3.5:9b` A/B 回退配置。

成功标准：

1. 普通行动、话题切换和收口先得到具体承接，不会被模型自动升级成表白。
2. 连续三轮中，强专属表达默认最多出现一轮；玩家明确索要情话、确认关系或表达强烈想念时允许单轮升档，下一轮回到具体行动或轻微温度。
3. `L0` 功能回应、`L1` 轻微温度、`L2` 直接亲密和 `L3` 强专属情话在 Prompt 与评测诊断中有清晰边界。
4. 每个目标角色都保留自己的亲密方式，不因统一限流变成冷淡或同一种模板。
5. 五角色、多个关系阶段、`face_to_face`/`remote`、正例和负例均有可重复的自动化验收样本；自动评分与人工判断继续分开记录。

## 背景与问题定位

现有 `affectionInitiative` 在 `dating`/`married` 阶段默认把 `personal_affection` 放在 `current_topic` 之前，并要求除收口、拒绝或状态需要停下外每轮先表达对玩家的偏爱、想念或靠近。普通 Prompt 的最终亲密默检还会要求每轮说明“为何是玩家”，compact Prompt 则直接把“因为是你”“舍不得”等作为推荐理由。现有 `variationRule` 主要约束亲近形状和开场变化，没有表达强度分档或短窗口预算。

这会造成两个相互叠加的问题：

- 模型把“回应当前动作”误解成“必须追加高强度关系确认”；
- “只有你”“舍不得”“时间留给你”“放下工作陪你”等同一语义族换词重复，虽然形状可能变化，实际情感强度仍然没有降下来。

## 设计方案

### 1. 阶段策略：增加亲密表达节奏卡

在 `stage_policy.py` 的 `affectionInitiative` 中增加结构化的 `pacing` 字段，由默认卡提供保守基线，再由角色或阶段覆盖必要差异：

- `defaultIntensity`：普通高好感轮次优先使用 `light`；
- `strongSignalWindow`：以最近三轮为默认观察窗口；
- `maxStrongSignals`：窗口内默认最多一轮强专属表达；
- `strongSignalKinds`：至少覆盖 `exclusive_share`、强 `player_directed_preference` 和强 `player_caused_anticipation`；
- `explicitRequestOverride`：玩家明确索要情话、表达想念或确认关系时只允许当前轮单次升档；
- `followUpAfterStrong`：强表达之后优先使用 `current_topic`、具体照顾、共同小行动或自然收口；
- `semanticCooldown`：把“只有你/只为你/舍不得/时间都给你”等同一语义族视为同类，避免换词绕过节奏限制。

这些是给模型的行为边界和给评测器的契约，不在运行时强行改写 NPC 文本，也不把三轮计数写入正式存档。历史中可获得的上一轮亲密诊断只用于提示“上一轮已使用强表达”时换档；缺少历史时按默认轻度策略生成。

关系阶段仍然决定是否允许主动亲密：`friend` 不新增强制爱意，`dating`/`married` 才使用节奏卡；`stranger`/`acquaintance`/非恋爱 NPC 不因本改动获得浪漫升级。

### 2. 角色差异化

统一节奏规则只提供上限，不统一表达内容。

| 角色 | 默认落点 | 强表达使用边界 |
| --- | --- | --- |
| Rasmodia/Wizard | 炉火、记录、灯光、茶、座位、安静相处和研究者式观察 | 最严格遵守三轮一强；普通研究或行动安排不自动变成“只有你”或“为你放下研究” |
| Sophia | 葡萄园、酒窖、品酒、绘画、害羞的分享和轻度调情 | 保留诗意和温柔，但强关系确认不连续出现；先接住酒/画/地点等具体对象 |
| Shane | 实际照顾、吃饭、休息、鸡舍和带边界的陪伴 | 低落、拒绝、疲惫和要空间时允许直接收口；不以“情话不足”为理由重试 |
| Sebastian | 音乐、耳机、摩托车、电脑、房间和并肩安静相处 | 拥抱只在明确请求时直接回应；强亲密动作和强情话都不连续堆叠 |
| Alex | 训练、比赛、农场活动、带笑打趣和实际邀约 | 保留自信热情，但减少连续外貌夸奖、口号式示爱和把普通陪伴写成热烈告白 |

### 3. Prompt 投影与指令优先级

在 `prompts.py` 中让完整 Prompt、compact Prompt 和最终默检共同使用节奏卡，优先级固定为：

1. 先回答玩家当前输入和场景；
2. 根据当前角色选择一个具体的 `L0`/`L1` 落点；
3. 只有有自然理由或玩家明确索要时才使用 `L2`；
4. 检查最近历史和当前输入，默认避免 `L3`；
5. 若上一轮已经是 `L3`，本轮回到具体行动、轻微温度、角色自我分享或收口；
6. 玩家明确结束、拒绝、需要空间或准备休息时，允许只回答并自然结束。

“个人亲近”与“强专属情话”不再等价：`因为是你`、`舍不得`等只能作为可选的高强度表达，不能继续写成每轮最低要求。`companionship`、`specific_plan`、角色化小动作可以独立构成自然的低强度温度，但不能被错误评分为强专属情话。

compact Prompt 只保留短版节奏要求和上一轮强表达提示，避免扩大 Token；完整 Prompt 保留结构化字段和角色化解释。历史字段缺失、格式异常或不是同一 NPC/关系阶段时，安全回退到默认 `light`，不阻断对白。

### 4. 质量诊断与评分

在 `behavior_quality.py` 与 `character_quality_eval.py` 增加不改写回复的节奏诊断：

- 识别回复的 `affectionIntensity`（`none`/`light`/`direct`/`strong`）和 `affectionSemanticFamily`；
- 对“只有你/只为你/舍不得/把时间都给你”等强语义族做有限、可解释的匹配；
- 统计三轮窗口内强表达次数、相邻强表达、强表达后的具体承接和玩家明确索要覆盖；
- 产生 `strong_affection_over_budget`、`repeated_strong_affection_family`、`strong_affection_without_prompt` 等诊断标签；
- 保留现有 `affectionShape`、`mechanical_affection_shape`、`missing_personal_affection` 和 exact/semantic evidence 字段，不把低强度陪伴误判成强情话，也不因为节奏诊断失败而重写或丢弃原始回复。

质量评分只在适用的高好感 `chat` 案例中启用；`conversation_exit`、Shane 的 `guarded_exit_allowed`、明确的同意/索要情话和阶段升级都应跳过不适用的惩罚。自动评分标记用于筛选人工样本，不单独决定 Gemini 是否可以替换千问。

### 5. 测试与评测数据

测试分为四层：

1. 阶段策略与 Prompt 契约：所有五角色的 dating/married 节奏字段、compact 投影、历史强表达后的下一轮提示、明确索要情话的例外、远程/当面边界。
2. 诊断器单元测试：强表达分档、同义族归一、三轮预算、低强度具体陪伴、普通事务安排、玩家明确索要、低落收口和非恋爱阶段负例。
3. 离线多轮质量测试：每个目标角色至少覆盖普通动作、兴趣/工作、轻度亲近、明确索要、拒绝/低落或收口、远程与当面中的适用组合；至少包含三轮连续样本，用于检查密度和重复。
4. Gemini 隔离验收：先运行小批次验证评分契约，再运行完整分层批次。每批写入新的 `artifacts/character-quality-eval/` 目录，只保存脱敏结果，不覆盖既有 v12/v13/v14 工件，不写入角色资料库。

重点人工验收问题：

- Ras 三轮中是否从“连续专属表白”变成“具体行动 + 偶尔明确情话”；
- Sophia 是否仍然柔和、感性且有轻度调情，而不是只剩事务回答；
- Shane 是否能在低落和拒绝时停下来；
- Sebastian 是否通过音乐/耳机/房间等具体形状表达亲近，并保留拥抱边界；
- Alex 是否仍然自信、热情、带行动感，而不是只减少所有情绪；
- 五角色是否都能在玩家明确索要时正常升档；
- 远程回复是否没有写成已经见面。

## 风险与回滚

- 风险：预算提示过强可能让角色突然变冷。缓解方式是只限制 `L3` 和同义重复，保留 `L1`/`L2` 及角色化具体行动，并用五角色对照样本检查。
- 风险：中文语义匹配过宽可能把普通“陪你”“给你留一杯”误判成强情话。缓解方式是强表达使用低歧义短语和组合条件，继续保留事务负例。
- 风险：历史字段不完整导致错误惩罚。缓解方式是缺历史安全回退默认轻度，不把缺失当作强表达。
- 回滚：本轮只修改工作树中的 Bridge 策略、Prompt、诊断、评测与测试；删除或恢复本轮新增字段和测试即可，不触碰正式 Mods、存档、API Key、旧工件和千问回退文件。

## 验证命令

在实现阶段按 TDD 运行：

```powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_stage_policy.py bridge/tests/test_prompts.py bridge/tests/test_behavior_quality.py bridge/tests/test_character_quality_eval.py -q
py -3.10 -m pytest bridge/tests -q
py -3.10 -m compileall -q bridge/src scripts
git diff --check
```

云端验收使用新目录和明确预算，先小批次再完整批次；报告必须同时列出返回率、Provider error/fallback、重试、Token、单轮自动通过、完整案例通过和人工观察，不把“请求成功”当作角色质量达标。
