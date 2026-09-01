# 社区AI对话Mod评价与模型路线

日期：2026-08-26
研究问题：社区AI对话Mod评价与模型路线

## 结论

社区对 Stardew Valley AI 对话 Mod 的评价是“有吸引力，但成败主要取决于角色一致性和上下文工程”，而不是单纯追求更大的模型。正面反馈集中在：能自由输入、能结合天气/季节/关系/事件、对话不重复；负面反馈集中在：像通用聊天机器人、越聊越重复、感情阶段判断错误，以及破坏原版手写对白的节奏。

现成 Mod 大致分成三条模型路线：

1. **内置小模型**：Chatty Valley 随 Mod 搭载 Liquid AI 的 `LFM2.5-1.2B-Instruct` 量化模型和 LoRA，约 700 MB 模型文件，完全离线运行，目标是低门槛和低延迟。
2. **本地模型可切换**：Pelican Town AI 默认推荐 Ollama 的 `qwen3.5:4b`，同时支持 `llama3.2:3b`、`qwen2.5:7b-instruct`、`phi3:mini`，也可接 OpenAI 兼容端点或云端模型。
3. **后端无关/云端优先**：ValleyTalk 支持 GPT、Claude、Gemini、Mistral、DeepSeek、VolcEngine、LlamaCpp 等；较早的 `stardew-llm-dialog` 默认使用 OpenAI `gpt-3.5-turbo`。CoboldAIValley 则以 KoboldCPP/LM Studio 为后端，作者实测更偏好带角色上下文的 `Archaeo12B V2`，其次是 `ConvAI 9B`。

对本项目的直接结论：暂不因为“别人用了 1.2B”就降低目标。我们已经有原版、SVE 和 RomRas 的可追溯语料，Rasmodia 的角色一致性更可能受检索、关系阶段、记忆压缩和提示词约束影响。建议继续以本机 `Qwen3.5 9B Q4` 作为质量候选、`Qwen3.5 4B Q4` 作为低延迟候选，并在同一套角色测试集上比较；先把“像 Rasmodia”做对，再考虑 LoRA 微调。

## 判断依据

### 来源事实

- Chatty Valley 的 Mod 页面明确写明使用 `LFM2.5-1.2B-Instruct`，模型随 Mod 提供，约 820 MB 安装体积、约 1 GB 额外内存，并通过本地推理实现离线聊天。
- Pelican Town AI 的页面明确列出 Ollama 模型选择，并给出作者在 RTX 4090 上使用 `qwen3.5:4b` 的自测：每轮约 300–900 ms、首 token 约 250 ms、约 3.5 GB VRAM。该数字是作者自测，不能直接当成本机 RTX 3070 Laptop 的保证。
- Pelican Town AI 还特别提醒：`Qwen3` thinking/`DeepSeek-R1` 在 OpenAI 兼容接口下可能出现空回复，建议使用 Ollama 原生 `/api/chat` 并显式传 `think:false`。这与我们当前 Bridge 只发送 `model` 和 `messages` 的实现存在直接风险。
- ValleyTalk 的 README 是“provider-configurable”路线，不绑定单一模型；它把人物性格、关系、游戏状态、事件、玩家历史和季节/时间上下文组合进请求。
- CoboldAIValley 的作者说明后端可用 LM Studio/KoboldCPP，并以 `Archaeo12B V2`、`ConvAI 9B` 做过角色对话测试；其效果依赖额外的角色上下文和会话历史。

### 社区反馈

- Reddit 的 ValleyTalk 讨论中，有玩家认为 Claude 回复“出乎意料地符合角色且不重复”；也有玩家认为 Google 模型让 NPC 变得重复、出戏，并错误假设十心角色存在恋爱关系。
- 另一条关于 NPC AI 对话的讨论批评通用 AI 回复“木讷、不自然、缺少个性意识”，并认为原版精心编写的对白具有 AI 难以替代的意图；也有人因为原版配偶对白重复，愿意接受 AI 作为补充。

以上两类反馈并不矛盾：玩家评价的是“模型 + 角色卡 + 检索 + 记忆 + 游戏状态 + UI”的整体，而不是裸模型分数。我的推断是，针对 Rasmodia，增加可验证的原文证据和阶段门控，通常比从 4B 直接换到更大但无上下文的通用模型更划算。

### 本项目代码观察

- `bridge/src/stardew_ai_bridge/providers.py` 的 `OpenAICompatibleProvider` 目前只发送 `model`、`messages`，没有 `think:false` 或原生 Ollama 路径。
- 当前项目语料管线已包含原版、SVE 和 RomRas；此前盘点得到 7,108 条风格/对白样本，Wizard/Rasmodia 证据按来源层分层保存。该数据适合做检索增强和评测，不等于已经完成模型微调。

## 来源

- [Chatty Valley Nexus 页面](https://www.nexusmods.com/stardewvalley/mods/49886)：内置 `LFM2.5-1.2B-Instruct`、离线运行、安装体积和内存说明。
- [Chatty Valley GitHub](https://github.com/edbuildingstuff/chatty-valley)：本地 1.2B 微调模型、GGUF/llama.cpp/LoRA 技术标记。
- [Pelican Town AI Nexus 页面](https://www.nexusmods.com/stardewvalley/mods/46853)：Ollama 模型清单、作者自测性能、thinking 模式兼容性提醒。
- [ValleyTalk GitHub](https://github.com/dandm1/ValleyTalk)：多 provider 支持和上下文架构说明。
- [CoboldAIValley Nexus 页面](https://www.nexusmods.com/stardewvalley/mods/34214)：LM Studio/KoboldCPP 后端与 `Archaeo12B V2`/`ConvAI 9B` 作者测试。
- [ValleyTalk Reddit 讨论](https://www.reddit.com/r/StardewValley/comments/1hmww5g/valleytalk/)：Claude 正面反馈、Google 模型重复/出戏反馈。
- [NPC AI 对话 Reddit 讨论](https://www.reddit.com/r/StardewValleyMods/comments/1hrd2m3/hello_anyone_to_talk_to_the_npc/)：对木讷、缺少角色意图的批评及对原版重复对白的反向需求。
- [stardew-llm-dialog GitHub](https://github.com/trbarron/stardew-llm-dialog)：较早的 OpenAI `gpt-3.5-turbo` 默认路线。
- 项目代码：`bridge/src/stardew_ai_bridge/providers.py`、`bridge/src/stardew_ai_bridge/config.py`、`docs/` 语料与评测文档。

## 证据

本次检索得到的可复核要点：

| Mod/项目 | 模型或后端 | 运行方式 | 证据性质 |
|---|---|---|---|
| Chatty Valley | `LFM2.5-1.2B-Instruct` + LoRA | 模型随 Mod，离线 | Mod 作者说明 + GitHub |
| Pelican Town AI | `qwen3.5:4b` 默认；另有 `llama3.2:3b`、`qwen2.5:7b-instruct` 等 | Ollama、llama.cpp、OpenAI 兼容、云端 | Mod 作者说明和作者自测 |
| ValleyTalk | GPT/Claude/Gemini/Mistral/DeepSeek/VolcEngine/LlamaCpp 等 | Provider 可配置 | README |
| CoboldAIValley | `Archaeo12B V2` 首选、`ConvAI 9B` 次选（作者测试） | KoboldCPP/LM Studio | Mod 作者说明 |
| stardew-llm-dialog | `gpt-3.5-turbo` 默认 | OpenAI API | GitHub README |

本机可执行的下一步评测应固定提示、固定角色证据和固定上下文，仅替换模型；至少覆盖：初识/高好感/Roommate（等同 married）、同日再次交互、SVE 事件、拒绝越界恋爱假设、连续 6 轮不重复、中文输入和空响应恢复。这样才能把“模型差异”与“上下文工程差异”分离。

## 建议

1. **保持现有模型路线**：在本机先比较 `Qwen3.5 9B Q4` 与 `Qwen3.5 4B Q4`，不先做微调，也不直接照搬 Chatty Valley 的 1.2B。9B 追求角色稳定，4B 作为响应速度和显存的兜底。
2. **先修 Bridge 的 thinking 兼容**：补测试后增加 Ollama 原生 `/api/chat` 或可配置的 `think:false`；继续保留 OpenAI 兼容端点给其他后端。没有这一步，Qwen3/DeepSeek 类模型的空回复会被误判为模型质量问题。
3. **建立 Rasmodia 专项评测**：对每个模型跑同一组 12–20 条用例，记录角色一致性、事实引用、阶段边界、重复率、延迟、显存和失败恢复；测试集结果落盘，不凭单轮截图选型。
4. **把“原版意图”设为硬约束**：AI 只补充原版没有覆盖的自由输入，不改写关键剧情、关系门槛和明确的角色立场；对玩家反馈中最常见的“十心自动暧昧”和“通用助手口吻”加负向测试。
5. **暂缓微调**：只有在 9B/4B + 检索 + 状态提示仍无法稳定通过 Rasmodia 测试时，才用已清洗、带来源标签的 Rasmodia 语料做小规模 LoRA；先核查原版/SVE 文本的再分发和训练许可。

## 限制

- Nexus 页面主要是 Mod 作者的功能与性能说明，不是统一硬件、统一提示词下的第三方基准；Pelican Town AI 的 4090 数据不能外推到本机 RTX 3070 Laptop。
- Reddit 反馈是少量、主观、可能受模型配置影响的个案，适合发现风险模式，不适合推断全体玩家比例。
- Mod、模型和 provider 配置会更新；报告记录的是 2026-08-26 可访问页面内容。
- 本报告没有在本机下载或运行任何模型，也没有把云端 API 作为测试前提；因此尚未给出本机实测质量/速度排名。
