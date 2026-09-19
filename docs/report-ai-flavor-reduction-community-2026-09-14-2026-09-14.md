# 降低角色对话 AI 味的社区方法复核

日期：2026-09-14
研究范围：社区角色卡/对话质量方法、DeepSeek 官方参数说明、当前
`deep-flirt` 批次和本项目 Prompt/Guard 代码。
排除项：本轮不改 Prompt、角色资料或 Guard，不生成新的云端结果，不把自动评分当成人工自然度。

说明：本文记录的是实施前的研究快照。随后已按文中的 P0 方案在同一
`story-memory` 工作树落地自然对白 Prompt、案例输入和 Guard 重试收敛；最新实现与验证结果以
`docs/active-work.md` 顶部记录为准。

## 结论

社区确实有一套比较一致的降 AI 味方法，但核心不是再加一句“像真人一点”，也不是把所有禁止项继续堆进 Prompt。最稳定的共识是：

1. **压缩规则层，减少模板泄漏。** 保留少量正向、可执行的角色行为，把机械复述、越权代替玩家、关系边界作为少数硬禁区；不要让多个 system card 同时要求“先回答、再加爱意、再推进、再收尾”。
2. **用少量、成对、彼此不同的示例教语气。** 示例要覆盖普通闲聊、暧昧推进、被放慢或拒绝三种状态，并刻意包含短句、停顿、答非全问和不完整收束；不要把同一套“动作＋解释＋邀约”复制给所有角色。
3. **给回复留出不完美和闲笔。** 角色不必每轮解释情绪、总结关系、提出新安排或留下问题；一轮只推进一个小变化，允许冷场、碎句、口是心非和轻微反弹。
4. **先治理上下文，再动采样参数。** 历史中的旧 AI 味回复会继续作为风格示范；应该用干净会话或从问题前回溯验证。DeepSeek 的 `temperature` 可以做单变量小 A/B，但 `frequency_penalty`/`presence_penalty` 在当前官方文档中已标为 deprecated，不能把它们当成解决方案。

当前项目的主要风险更像是 **Prompt 规则叠加 + few-shot/案例结构同形 + Guard 重试再次要求“补齐指标”**，而不是已经有证据证明“DeepSeek 天生只能写成这样”。因此优先级应是：先做离线 Prompt/Guard 结构收敛和 AI 味检测，再用同一模型的小批量复测；暂不换模型，也不直接对回复做字符串后处理。

## 判断依据

### 社区与官方来源事实

- SillyTavern 的 Character Design 文档把角色描述、首条消息和 Example Dialogue 分开：描述会持续注入，首条消息会显著影响长度和语气，示例对白用于展示“角色实际怎么说话”。文档还提醒，过长的角色定义会挤掉近期历史，示例最终会被上下文裁剪。可迁移结论是：短角色卡、少量角色专属示例和近期历史比继续堆长规则更重要。
- `foreverse-app/character-card-skills` 社区仓库的 `before-after.md` 将高风险模式归纳为引语点题、对仗翻转、生造概念词、金句癖、伪精确数字、说明书腔和“零闲笔”。其共同修法是删减、降密度、平铺事实、允许普通收束，而不是增加华丽形容词。
- 同仓库的 `chat-quality-doctor` 把 AI 味拆成小作文症、解说症、顺滑症和书面症：固定三段式、替用户解释情绪、角色永远服务式顺从、句子过于完整且没有停顿。它建议默认短回复、只写可观察动作、每轮最多推进一层、允许碎句和不完整回答，并提醒旧 AI 回复会污染后续 few-shot。
- Anthropic 的 Prompting Best Practices 不是 DeepSeek 专属规范，但明确建议指令清晰直接、解释目的、使用 3–5 个相关且有变化的 few-shot，并用结构区分规则、上下文和示例；它不支持把大量互相重叠的负向规则同时注入。
- DeepSeek 官方 API 文档说明 `temperature` 范围为 0–2，通用对话建议约 1.3、创作约 1.5；同时建议一次只改 `temperature` 或 `top_p`。当前文档将 `frequency_penalty` 和 `presence_penalty` 标为 deprecated，并说明非 thinking 模式下 `top_p` 可能被忽略或固定，因此这些参数不能直接当作“去 AI 味开关”。
- 生成研究和 KoboldAI 社区 issue 只能支持一个较弱的工程判断：重复和 bland 文本同时受解码、上下文和示例分布影响；全历史提高 repetition penalty 可能伤害长对话语义，不能不加验证地全局启用。

### 当前批次的直接证据

工件：[20260914-deep-flirt-natural-v2/results.jsonl](../artifacts/character-quality-eval/20260914-deep-flirt-natural-v2/results.jsonl) 与同目录 `summary.json`。

- 实际返回 `4` 个案例、`12` 轮，`errors=0`；自动通过 `5/12` 轮、`1/4` 案例，质量重试 `21` 次，合计 `266195` tokens。
- 离线抽样中，`3/12` 轮有至少三个完整句末段落；其余多数仍是两段完整句子。`Sophia` 首轮约 `109` 字，明显呈“事实 → 内心解释 → 邀请陪伴”的小作文结构。
- `7/12` 轮出现“因为/所以/其实/只是/不过/才/正好”等解释或反转连接，虽然不是每次都违规，但会让对白变成说明式推进。
- `12/12` 轮没有动作括号、碎句或未完成语；几乎所有轮次都用完整句子承接，并在结尾给出“别急着走”“陪我一会儿”“你要是饿就一起”等条件邀约或安排。
- 机械整句复述字段为 `0`，说明当前 Guard 没有抓到“整段复制”；但每轮仍会高频回扣玩家锚点（星尘、位置、抱、牵手、鼓点），属于较轻的 topic echo，和用户感受到的“像在重复测试输入”不是同一个指标。
- 社区也有“最后一句完全重复”由 provider/stream 拼接引起的案例；当前工件没有显示这种完整尾句复制，所以这里先按 Prompt/案例结构造成的 topic echo 处理，不把两类问题混在一起。
- “顺滑症”明显：`12/12` 轮没有真实拒绝或摩擦，婚后案例基本直接接受靠近；Shane 只有“谁说我不累了”“我不躲”一类轻微反弹。

还要把“模型 AI 味”和“测试输入本身的评测腔”分开。当前 [deep_flirt_cases.py](../bridge/src/stardew_ai_bridge/deep_flirt_cases.py) 把每例固定成“首轮主动升温、第二轮明确同意、第三轮放慢或暂停”，并且每轮配置三个 `expected_terms`。玩家输入因此普遍是完整、长句、显式写出动作和边界的对白，例如“我也想听近一点。往旁边挪挪，给我留个位置，好吗？”和“抱一会儿就好……我还有点紧张，别急着往下走。”这会诱导模型逐项回显关键词，即使模型本身没有整句复述，也会产生“在完成测试清单”的感觉。后续评测应保留一套契约测试，同时增加更像真实聊天的自然输入对照；否则只改 NPC Prompt，无法消除案例设计带来的模板味。

当前 12 轮的输入 token 合计约 `264938`，单轮约 `6712–38432`；Sophia 第三轮约 `38432`，而同一案例的重试会继续叠加上下文。长 Prompt、多张质量卡和同轮重试共同挤压近期对话，是比“DeepSeek 单一模型缺陷”更值得先验证的工程嫌疑。

样本片段（脱敏结果原文）：

```text
Sophia t1：这杯是今年早收的那批……其实画那片葡萄园时，我一直想着你会不会喜欢这样的颜色……你要是还想听，我可以说说……不过得你愿意坐下来陪我一会儿。
Shane t3：好，就抱一下。你停在这儿也行，我不催你。等会儿把桶留在门口，今晚我去玛妮那边热口汤，你要是饿就一起。
Sebastian t1：软是因为把你常用的那个滤波器拧过了……你靠过来吧，耳机分你一边——别踩到线。
```

这些例子不是“模型完全失控”：它们能接住话题、能表达关系，也没有发生整句机械复制；问题在于每轮都过于完整、解释过满、收束过顺，并且容易把亲密动作写成下一项安排。

### 当前项目的代码映射

- [prompts.py](../bridge/src/stardew_ai_bridge/prompts.py) 的基础对白契约要求中文 `1–3` 句、通常 `15–80` 字，明确追问时可接近 `120` 字；这本身是合理的上限，但和 deep-flirt 的明确追问、关系亲密卡、连续对话卡叠加后，会把“完整回答”推成稳定的小作文长度。
- 同文件的表达变化卡要求口语颗粒最多一次、不能固定句首、不能机械拼接；连续对话卡又要求承接一个对象并“只新增一个小进展”；关系卡在部分路径中要求首轮必须出现可感知爱意、不能只给功能性邀约。每条单独看都合理，叠加后会让模型像在逐项验收。
- [guard.py](../bridge/src/stardew_ai_bridge/guard.py) 已有机械复述、机械 conversation lead、机械 affection shape、主动亲密和未来安排检查。当前批次 `21` 次重试说明 Guard 并非只做离线诊断；重试提示继续要求补齐“主动性/对话推进/关系信号”，可能把原本自然但克制的回答再次规范化。
- 现有角色辨识和阶段设计文档已经提出“短角色卡、单动作预算、语气词可选、只推进一个小变化”。因此下一步不应再新建一套检测器或继续扩大规则，而应把这些已有原则合并成一张短的自然对白契约，并让 Guard 主要报告问题、只对明确硬错误重试。

## 建议

### P0：离线 Prompt/Guard 收敛，不发起云端请求

1. 为普通 chat/deep-flirt 建一张短的正向 `natural_voice_contract`：先接住一个具体点，补一处角色细节，最多推进一个小变化，自然收口即可。硬禁区只保留机械复述、代替玩家行动、关系/成人边界越界。
2. 将多张重叠的“不要……”卡做成 A/B 开关，保留旧卡作为基线；离线 Fake provider 比较 Prompt 长度、重复约束数量、输出结构评分和 Guard 重试触发，不改历史工件。
3. 将 `missing_proactive_affection` 与“AI 味”分离：有些普通轮次或玩家要求放慢的轮次应该允许克制、停顿或不继续升温，不能为了让自动分数好看而强迫每轮补个人爱意。
4. 增加离线结构检测：三段式（动作/解释/邀约）、解释型连接词密度、固定条件邀约收尾、玩家锚点过度回扣、跨轮同形开场、完整句比例。检测结果用于诊断和抽样，不直接改写模型文本。

### P1：小批量真实验证

1. 用同一 DeepSeek、同一案例、同一上下文，各跑短批次 A（现有 Prompt）和 B（收敛 Prompt），每组只看 2–3 个角色、2–3 轮；不启动新的大批次。
2. 先固定采样参数；若仍需要调解码，只做一个变量的 `temperature=1.2` 或 `1.3` 对照，观察自然度、重复、Guard 重试和角色事实保持。不要同时改 `top_p`，不要依赖已 deprecated 的 frequency/presence penalty。
3. 人工盲看每组至少一轮普通闲聊、一轮暧昧推进、一轮被放慢/暂停。评分分开记录：自然中文、角色辨识、上下文承接、边界尊重、AI 味；自动通过率只作为辅助指标。

### 不建议

- 不要继续增加“更自然”“更像真人”“不要 AI 味”这类抽象提示。
- 不要把所有角色都改成碎片化短句；Shane 的干涩、Elliott 的完整表达、Wizard 的克制可以不同。
- 不要用字符串后处理强行删掉“其实/不过/你”；这会破坏角色语气，也会掩盖 Prompt 和 Guard 的根因。
- 不要用全历史 `no_repeat_ngram` 或高 repetition penalty 代替语料和上下文治理；聊天中可能误伤固定称呼和 Stardew 专有词。

## 来源

### 外部来源

- [SillyTavern：Character Design](https://docs.sillytavern.app/usage/core-concepts/characterdesign/)：角色描述、首条消息、Example Dialogue 和上下文预算的职责区别。
- [foreverse-app/character-card-skills](https://github.com/foreverse-app/character-card-skills)：社区角色卡与 AI 味诊断项目。
- [Before/After 手术记录](https://raw.githubusercontent.com/foreverse-app/character-card-skills/main/docs/before-after.md)：引语点题、对仗翻转、金句癖、说明书腔和零闲笔等模式。
- [chat-quality-doctor](https://raw.githubusercontent.com/foreverse-app/character-card-skills/main/skills/chat-quality-doctor/SKILL.md)：小作文症、解说症、顺滑症、书面症及修复建议。
- [Anthropic：Be clear and direct](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/be-clear-and-direct)：清晰指令、少量多样 few-shot 和结构分隔建议；这是可迁移方法，不是 DeepSeek 专属结论。
- [DeepSeek：Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion) 与 [Parameter settings](https://api-docs.deepseek.com/quick_start/parameter_settings)：`temperature`、`top_p` 和已 deprecated 惩罚参数的说明。
- [Hugging Face：Text generation](https://huggingface.co/docs/transformers/main/en/main_classes/text_generation)：重复惩罚和 no-repeat n-gram 的解码层说明；不代表 DeepSeek API 一定支持这些参数。
- [KoboldAI issue #93](https://github.com/KoboldAI/KoboldAI-Client/issues/93)：长对话全局 repetition penalty 可能带来无关词的社区反馈。
- [SillyTavern issue #2960](https://github.com/SillyTavern/SillyTavern/issues/2960)：社区将“最后一句完全重复”作为可能的 provider/stream 拼接问题单独排查；这里只用于区分诊断类别。
- [The Curious Case of Neural Text Degeneration](https://arxiv.org/abs/1904.09751)：把退化归因到解码与概率分布的研究背景。

### 本地来源

- [deep-flirt 案例定义](../bridge/src/stardew_ai_bridge/deep_flirt_cases.py)：8 个角色、每例 3 轮的输入结构和关系边界。
- [Prompt 构建](../bridge/src/stardew_ai_bridge/prompts.py)：基础回复契约、连续对话卡、表达变化卡和关系亲密卡。
- [Guard](../bridge/src/stardew_ai_bridge/guard.py)：机械复述、conversation lead、主动亲密、未来安排和重试链路。
- [当前结果工件](../artifacts/character-quality-eval/20260914-deep-flirt-natural-v2/summary.json)：案例/轮次完成数、重试数和自动评分。
- [角色语气设计](../docs/superpowers/specs/2026-08-27-npc-voice-style-design.md)：短角色卡、示例和来源隔离的既有设计。
- [高阶段语气变化](../docs/superpowers/specs/2026-09-01-dialogue-lab-high-stage-voice-variation-design.md)：口语颗粒可选、避免固定开场的既有设计。
- [角色辨识度计划](../docs/superpowers/plans/2026-09-07-character-voice-distinctiveness.md)：单动作预算和避免统一模板的既有计划。

Guard 重试提示也应作为独立变量审计：详细诊断码留在结果数据和查看器，发送给模型的重试内容只保留一两句正向任务（直接回答当前对象、补一个角色化个人理由、只输出自然的 1–3 句对白）。这是建议，不是本轮已实施的修改。

## 证据与复查记录

- 外部五个网页来源在 2026-09-14 以 `Invoke-WebRequest` 取得 HTTP `200`；本报告依据页面正文和原始 Markdown，不依据搜索摘要。
- 当前结果使用 Python 3.10 只读解析 `20260914-deep-flirt-natural-v2/results.jsonl` 和 `summary.json`，未读取或输出 `.env.local`、API key、完整 Prompt 或请求头。
- 本轮没有发起 DeepSeek、Gemini 或其他云端模型请求，没有启动游戏、SMAPI 或 Bridge 测试服务，没有修改源代码、测试、角色资料、历史结果或正式 Mods。

## 限制

- 社区角色卡指南和 `chat-quality-doctor` 是经验性资料，不是统一模型、统一数据集和盲评条件下的因果实验；它们只能提供方向。
- Anthropic、Hugging Face 和 KoboldAI 的结论不能直接外推为 DeepSeek 的确定行为；参数效果必须用同一项目的小批量 A/B 验证。
- 当前样本只有 4 个案例、12 轮，且是自动生成结果；“AI 味”仍需要人工盲评确认，不能用 `5/12` 自动通过率代替。
- 本报告提出的是离线优先的方案，没有在本轮实施 Prompt/Guard 修改；任何落地改动都应先新增失败测试，再做最小修改和小批量复测。
