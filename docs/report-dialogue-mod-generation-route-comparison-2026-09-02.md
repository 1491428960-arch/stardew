# 参考对话 Mod 的生成方式与当前路线比较

日期：2026-09-02
研究问题：参考的 Stardew 对话 Mod 如何产出对白，当前项目采用的路线是否更合适。

## 结论

这里要先区分两类“对话 Mod”：

1. SVE、Romanceable Rasmodius 这类传统内容 Mod 不在运行时生成对白。作者预先写好带条件的文本，再由 Content Patcher、i18n 和游戏的关系/季节/事件/地点条件选择显示哪一句。
2. Chatty Valley、Pelican Town AI、ValleyTalk、CoboldAIValley 这类 AI 对话项目，通常是“角色资料 + 游戏状态 + 对话历史 + 模型”的运行时生成；区别主要在模型是随 Mod 内置、本地 Ollama/KoboldCPP，还是云端/可切换 Provider。

当前项目采用的是混合路线：关键原版对白和固定剧情仍交给游戏与 Mod 的条件文本；自由输入和“找话题”才交给 Bridge，通过结构化角色资料、原版/SVE/RomRas 语气证据、关系阶段、故事状态、行为示例和有限历史构造 Prompt，再调用本地或云端模型。

从工程方向看，这条路线比“裸模型 + 一张长角色卡”更适合我们的目标，也比现在就做 LoRA 更容易调试和回滚；但它还没有被当前质量结果证明已经优于参考 AI Mod。最近的 `topic-start-intimacy` 批次只有 `2/32` 案例、`35/96` 轮自动通过，说明“主动热情的亲密关系表达”仍是未解决问题。

## 参考项目怎样产出对白

### 传统内容 Mod：条件文本，不是 AI 生成

这类 Mod 的生产流程大致是：

```text
作者编写对白和 i18n 键
→ 按 NPC、心级、季节、星期、地点、事件等建立条件分支
→ Content Patcher/游戏读取当前条件
→ 直接显示匹配的固定短对白
```

优点是角色声音、剧情边界、中文长度和游戏节奏都可逐句控制；缺点是只能覆盖作者预先想到的输入，不能真正理解玩家任意提出的新话题。

### Chatty Valley：内置小模型与 LoRA

现有资料显示，Chatty Valley 随 Mod 搭载量化的 `LFM2.5-1.2B-Instruct` 和 LoRA，走本地离线推理。它把部署门槛、网络依赖和 API 成本压低，但小模型的自由对话质量和复杂多轮承接需要单独评测。

### Pelican Town AI：本地模型/外部 Provider 选择

Pelican Town AI 的公开说明列出 Ollama 模型选择，例如 `qwen3.5:4b`、`llama3.2:3b`、`qwen2.5:7b-instruct` 和 `phi3:mini`，同时支持其他本地或兼容接口。它的核心仍是运行时把游戏情境和角色信息交给模型，而不是把每条新对白预先写死。

### ValleyTalk 与 CoboldAIValley：后端可替换

ValleyTalk 是 Provider 可配置路线，可接 GPT、Claude、Gemini、Mistral、DeepSeek、VolcEngine、LlamaCpp 等；整体质量取决于角色上下文、关系状态、游戏信息、历史和模型的组合。CoboldAIValley 则偏向 KoboldCPP/LM Studio，并通过角色上下文和会话历史调用外部模型，作者曾比较 `Archaeo12B V2` 和 `ConvAI 9B`。

因此，参考 AI Mod 的共同点不是某一个“神奇模型”，而是把有限的角色上下文送进一个可生成模型；它们的差别更多在模型大小、运行位置、Prompt 详细程度和状态接入深度。

## 与当前路线的对照

| 路线 | 对白来源 | 灵活性 | 角色/剧情可控性 | 运行成本 | 适合本项目的部分 |
|---|---|---:|---:|---:|---|
| 传统条件对白 | 人工逐句编写 | 低 | 很高 | 几乎为零 | 原版寒暄、关键事件、固定关系节点 |
| 裸 AI 对话 Mod | 角色卡、状态、历史 | 高 | 中等或偏低 | 本地硬件或云端费用 | 快速验证自由输入，但容易通用聊天腔 |
| 内置小模型 + LoRA | 随 Mod 的模型和适配器 | 高 | 取决于训练数据 | 下载体积、内存、显存 | 离线和低延迟；需要稳定训练集 |
| 当前 Bridge 混合路线 | 条件原文 + 行为卡 + 状态 + 少量成对示例 + 模型 | 高 | 高，但实现复杂 | 本地或云端可选 | 原版保真与自由聊天并存 |

## 为什么当前路线更适合，但还不能宣布胜出

### 已有优势

- 原版、SVE 和 Romanceable Rasmodius 被当作有来源的语气/事实证据，不是把所有文本无条件塞进 Prompt。
- `ProfileIndexStore` 能按 NPC、来源 Mod、关系阶段、事件和当前话题筛选 `speechEvidence`、`styleSamples` 与 `behaviorExamples`。
- `PromptBuilder` 把角色基底、表达层、关系阶段、故事状态、渠道、有限历史和当前意图分层；Wizard/Rasmodia 继续使用 canonical `Wizard` 身份。
- 面对面流程保留原版寒暄，再提供继续聊天；AI 主要补足固定对白没有覆盖的自由输入。这样不会让模型取代所有原版内容。
- Provider 可在本地 `qwen3.5:9b`、低延迟 `qwen3.5:4b` 和云端 `qwen-plus-character` 之间做公平 A/B，便于区分模型能力和上下文工程问题。
- 改角色边界、证据筛选或行为示例只需重建索引/Prompt，不必立即重新训练模型；出问题时也更容易定位是哪一层导致的。

### 当前短板

- 原版单句对白主要教会模型“这个角色谈什么、用哪些词”，不能单独教会“玩家说什么时如何回应”。这正是成对 `playerInput → npcReply` 行为示例的价值。
- 近期主动亲密批次显示，模型可以提出摩托车、葡萄酒、散步、星象等角色化话题，却经常停留在事务邀约或礼貌反问，缺少稳定的主动亲热信号。
- `topicEvidence` 和关键词评分是机械质量信号，不能完全判断一句话是否真的像 Shane、Sebastian 或 Alex；必须保留人工抽查。
- 云端质量批次输入 Token 较多，长期全量运行成本高于固定对白；本地模型则承担延迟、显存和回复稳定性成本。

## 建议路线

建议继续采用“传统条件对白兜底 + 结构化 RAG/Prompt 生成自由对话”的混合方案，执行顺序如下：

1. 保留原版/SVE/事件对白作为固定内容，尤其是关键剧情、关系门槛、明确拒绝和重要场景。
2. 继续完善当前的行为示例层。每个主要角色先维护少量人工审核的成对示例，覆盖直接回答、被关心、暧昧接近、具体邀约、拒绝越界、承接上一轮和自然收口，并精确标注关系阶段与渠道。
3. 为高亲密阶段单独定义“主动表达强度”而不是只写 `direct`：先从角色化日常切入，再给一个清楚但不强迫的偏爱/想念/靠近信号；远程场景仍只能提出待确认的安排。
4. 用同一套固定案例比较 `qwen3.5:9b`、`qwen3.5:4b` 和 `qwen-plus-character`，先看角色辨识度、自然中文、阶段/渠道边界、历史承接和主动性，不按回复长度选模型。
5. 只有当结构化检索、行为示例和 Prompt 已稳定而模型仍反复出现同类问题时，才评估小规模 LoRA/QLoRA；不把未经审核的云端回复直接写回角色资料。

## 来源

- [社区 AI 对话 Mod 评价与模型路线报告](report-社区AI对话Mod评价与模型路线-2026-08-26.md)：Chatty Valley、Pelican Town AI、ValleyTalk、CoboldAIValley 和 `stardew-llm-dialog` 的模型/后端路线及限制。
- [社区角色模仿方法与当前项目落地方案](report-社区角色模仿方法与当前项目落地方案-2026-08-27.md)：角色卡、成对示例、条件 Lore、历史后短指令和干净评测会话的工程依据。
- [中文 API 与原版对白定制路线](report-中文API与原版对白定制路线-2026-08-30.md)：RAG/Prompt、教师模型候选样本和 LoRA/QLoRA 的分层路线。
- [SillyTavern Character Design](https://docs.sillytavern.app/usage/core-concepts/characterdesign/)：角色资料、第一条消息与示例对白的分工。
- [SillyTavern Prompts](https://docs.sillytavern.app/usage/prompts/) 与 [World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)：历史、生成位置和条件 Lore 的上下文组织。
- [Stardew Valley Wiki Modding:Dialogue](https://stardewvalleywiki.com/Modding:Dialogue)：Stardew 对白的 key、关系/事件和运行时条件结构。
- [Chatty Valley Nexus](https://www.nexusmods.com/stardewvalley/mods/49886) 与 [GitHub](https://github.com/edbuildingstuff/chatty-valley)：内置 `LFM2.5-1.2B-Instruct`、LoRA 和本地推理说明。
- [Pelican Town AI Nexus](https://www.nexusmods.com/stardewvalley/mods/46853)：Ollama/模型选择与作者性能说明。
- [ValleyTalk GitHub](https://github.com/dandm1/ValleyTalk)：可配置 Provider 与上下文路线。
- [CoboldAIValley Nexus](https://www.nexusmods.com/stardewvalley/mods/34214)：KoboldCPP/LM Studio 与角色模型测试说明。
- 当前项目：[README.md](../README.md)、[profile_index.py](../bridge/src/stardew_ai_bridge/profile_index.py)、[prompts.py](../bridge/src/stardew_ai_bridge/prompts.py)、[providers.py](../bridge/src/stardew_ai_bridge/providers.py)。

## 证据

- 当前项目 README 明确描述了“原版寒暄 → 继续聊聊”、NPC 主动找话题、连续对话和 Provider 路由；当前实现不是纯替换原版对白。
- 当前 `profile_index.py` 已有按话题、关系阶段、来源和行为维度选择示例/证据的实现；`prompts.py` 将行为示例以成对 user/assistant 消息和短执行卡投影到模型上下文。
- 最近 `topic-start-intimacy` 云端批次实际为 `32/32` 案例、`96/96` 轮、`0` 错误、`0` fallback，自动通过 `2/32` 案例和 `35/96` 轮；这证明链路正常，但也证明主动亲密质量尚未达标。
- 当前批次使用 `qwen-plus-character`，输入 `462158`、输出 `1875`、合计 `464033` Token；该数字来自本地脱敏 `summary.json`，不代表固定的未来成本。

## 限制

- 社区 Mod 页面和作者 README 说明的是实现/使用方式，不是统一硬件、统一 Prompt 和统一案例下的第三方质量实验。
- 本报告没有反编译或逐行审计每个第三方 Mod 的完整运行时代码；对其内部 Prompt 细节只采用公开 README、Mod 页面和已有报告记录的部分。
- 传统 Mod 的原文、Content Patcher 包和翻译文本仍需遵守各自的授权与再分发边界；本项目只把它们作为本地开发时的有来源证据使用。
- 当前项目的云端批次自动评分不能代替人工判断，尤其不能单凭关键词命中宣布“像本人”或“足够热情”。
