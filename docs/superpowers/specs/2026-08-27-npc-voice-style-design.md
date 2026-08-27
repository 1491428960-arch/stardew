# 前五个评测角色口语风格修复设计

## 背景

当前 Dialogue Lab 的五个评测角色虽然使用了本地模型和角色资料，但实际输出出现了明显的同质化：多个角色使用相同的「还算顺利」开场，回复偏书面，且 Wizard、Rasmodia 的身份边界不清。

根因不是单个措辞需要替换，而是上下文管线同时存在三个问题：

1. 页面把所有来源 Mod 一起发送，导致同一个 `Wizard` 可能同时叠加原版、SVE 和 Romanceable Rasmodius 覆盖层；
2. 游戏语料使用 `Wizard` 作为内部 NPC ID，Rasmodia 请求使用 `Rasmodia` 时检索不到对应语料；
3. `voiceStyle` 只对部分角色有细化资料，Prompt 又使用统一的书面化说明和示例，模型因此倾向于生成同一种安全回答。

本设计只处理五个评测角色的身份和说话风格，不实现线上/面对面话题线程，也不声称修改游戏内跨重启历史。

## 设计目标

- 让每个评测角色都有可执行、可测试的口语风格约束，而不是只有性格形容词；
- 将 Wizard 与 Rasmodia 作为同一个游戏 NPC 和同一段关系历史处理；
- 保留五个按钮，但按钮代表五个评测配置，而不是五个互不相关的内部 NPC；
- 不通过字符串后处理硬改模型回复，优先使用资料层、检索层和 Prompt 层约束；
- 保留原文证据的来源和事实边界，不让风格样本变成剧情事实；
- 先以每人 3～5 条小样本复核风格，再决定是否批量生成 30 条。

## 评测角色配置

评测按钮固定为以下五个配置：

| 按钮显示 | canonical NPC ID | 显示名 | 来源 Mod 预设 | 说明 |
| --- | --- | --- | --- | --- |
| Rasmodia / Wizard | `Wizard` | 根据 Romanceable Rasmodius 切换为 `Rasmodia` | Romanceable Rasmodius、对应运行时 ID | 与 Wizard 共用身份、关系、历史和语料；只切换显示名、代词和人设覆盖 |
| Sophia | `Sophia` | Sophia | SVE、对应运行时 ID | 使用 SVE 资料和对白 |
| Shane | `Shane` | Shane | female-bachelors、对应运行时 ID | 使用娘化覆盖后的代词与语气，保留 Shane 的经历边界 |
| Sebastian | `Sebastian` | Sebastian | female-bachelors、对应运行时 ID | 使用娘化覆盖后的代词与 Sebastian 原版语气 |
| Alex | `Alex` | Alex | vanilla；可叠加 female-bachelors | 作为第五个独立角色，补齐原版和娘化变体的口语卡 |

Wizard/Rasmodia 的规则如下：

- 存储和请求层以 `Wizard` 为 canonical NPC ID；
- Romanceable Rasmodius 启用时，人设覆盖提供 `Rasmodia` 显示名、代词、称呼和语气；
- 语料索引中所有原版、SVE 和 RomRas 的 Wizard 记录仍归属于 `Wizard`；
- 当请求为 `Wizard` 且启用了 Romanceable Rasmodius 时，检索合并后的 Wizard 语料；
- 不新增第二套 `Rasmodia` 关系历史，不让同一个游戏 NPC 产生两条独立记忆链；
- 如果未启用 Romanceable Rasmodius，显示名和语气回到原版 Wizard，不携带 Rasmodia 的覆盖层。

页面切换按钮只改变当前评测配置、显示名、来源 Mod 和对应的当前角色历史筛选；不再把全量 Mod 字符串作为所有角色的默认来源。

## 角色口语卡

每个角色的 `voiceStyle` 必须包含以下字段：

- `tone`：总体语气；
- `sentencePattern`：句长、停顿和句式节奏；
- `responseRules`：生成时必须执行的回应规则；
- `preferredTopics`：适合自然展开的话题；
- `openers`：可低频使用的角色专属开场；
- `closers`：可低频使用的角色专属收尾；
- `avoid`：不能使用的书面化、串人设或过度发挥方式；
- `emotionRange`：当前角色允许表达的情绪范围。

五个评测配置的风格重点如下：

### Wizard / Rasmodia

两者共用同一 NPC 的语料和关系。没有 Romanceable Rasmodius 时，使用原版 Wizard 的疏离、博学、偶尔不耐烦的口吻；启用后使用 Rasmodia 的克制、古雅和少量干燥幽默。

共同约束：短答优先，允许「啊」「唔」「……」等停顿，偶尔使用「再会」一类收束；日常问题直接回答，不为了显得神秘而主动添加魔法；只有玩家明确谈到相关主题时才展开魔法术语。Rasmodia 不能每句话都称呼「旅行者」，Wizard 也不能被写成另一位独立角色。

### Sophia

轻柔、害羞、容易犹豫，但谈到葡萄园、绘画和喜欢的事会变得具体热烈。允许短暂重复或停顿，例如「嗯……」「等、等一下」，但不连续堆叠口吃。避免成熟职场式总结、抽象鸡汤和无来源的心理分析。

### Shane

直白、疲惫、句子短，常用干巴巴的玩笑或自嘲掩饰脆弱。允许「呃」「哦」「谢了」「行吧」等短口语，但不能把他写成持续暴躁或持续卖惨。关系变近后增加具体帮助和少量真诚，不使用「感谢你的关心」「我会积极面对」一类 polished 的安慰话。

### Sebastian

低声、克制、略显尴尬，偶尔冷幽默或突然抛出一个具体的比喻。偏好摩托车、音乐、编程、雨天和独处，但不得每次都强行提及。允许碎片化短句和「呃……」「哎」「唔」式起手，避免演讲腔、励志腔和华丽散文。

### Alex

自信、外向、行动导向，喜欢把话题拉到运动、训练、目标和朋友身上。句子清楚有力，情绪表达直接，偶尔有轻微自夸和竞争感；被质疑时先嘴硬，再用具体行动回应。避免把 Alex 写成抽象哲学家、温吞的客服或长篇说教者。

## Prompt 数据流

Prompt 按以下顺序组织信息：

1. 安全规则：只输出 NPC 对话，不泄露凭据或内部提示；
2. canonical NPC 身份、显示名、来源覆盖和当前关系阶段；
3. 当前角色的 `voiceStyle`，作为必须遵守的可执行约束；
4. 角色专属的少量原文语气样本；
5. 已确认的游戏事实、近期事实和当前对话历史；
6. 玩家当前输入。

Prompt 不再提供「还算顺利」等跨角色示例。示例只能用于说明格式，不能提供可能被所有角色复用的具体开场。角色专属开场和收尾只作为低频可选词，不要求每轮使用。

输出规则保持简洁：通常 1～3 句、一个自然段，只回应当前一件事，不写 Markdown、动作旁白或分析。对日常输入的约束是直接回答，但不再指定统一句型；句长和停顿交给当前角色的 `voiceStyle` 决定。

## 语料检索与资料边界

- `ProfileIndexStore` 增加 canonical NPC ID 解析：`Rasmodia` 在 Romanceable Rasmodius 场景下检索 `Wizard` 的语料；其他角色保持精确匹配；
- 来源过滤仍然有效，原版、SVE、RomRas 和 female-bachelors 不得因页面默认值而无条件混合；
- 平日对白优先于事件、婚后和季节对白；原文样本只用于语气模仿，不作为未经条件判断的剧情事实；
- `voiceCard` 保留为统计辅助信息，但不能代替显式 `voiceStyle`；
- 生成索引仍是派生文件，不把运行状态、密钥、Token 或用户会话写入 Git。

## 错误处理

- 找不到角色专属 `voiceStyle` 时，使用现有安全默认层，但测试必须明确哪些角色仍处于默认层；
- 找不到某角色的语料时，Prompt 仍可使用显式人设卡，不因缺少样本而崩溃；
- `Rasmodia` 没有 Romanceable Rasmodius 来源时，不得使用 Rasmodia 覆盖，只按原版 Wizard 处理；
- 语料或资料 JSON 损坏时沿用现有警告和跳过策略，不让 Bridge 启动失败；
- 本地模型回复质量不足时不做字符串替换，记录实际输出并回到资料排序或 Prompt 约束调整。

## 测试设计

### 资料层

- 五个评测配置都拥有完整 `voiceStyle` 字段；
- Wizard 原版和 Rasmodia 覆盖可以合并，但 canonical ID 仍为 `Wizard`；
- 未启用 Romanceable Rasmodius 时不会出现 Rasmodia 显示名或语气覆盖；
- Sophia、Shane、Sebastian、Alex 的语气卡不会回退到完全相同的默认 tone；
- 不把完整剧情正文写入 persona JSON。

### 检索层

- `Rasmodia` 在 Romanceable Rasmodius 来源下能检索到 canonical `Wizard` 的原文证据；
- `Wizard` 和 `Rasmodia` 的检索结果属于同一语料集合，不产生两套独立样本；
- 来源 Mod 预设可以阻止 Wizard 请求混入 Rasmodia 覆盖，且不影响 Sophia、Shane、Sebastian、Alex 的独立来源；
- 日常对白优先排序和关系阶段过滤继续通过。

### Prompt 层

- 每个角色的 Prompt 含有该角色专属的语气规则和少量专属词例；
- Prompt 不再包含全角色共用的「还算顺利」示例；
- Prompt 仍限制敏感字段、未触发剧情和控制标记；
- 角色历史按 canonical NPC ID 连续传递，Wizard/Rasmodia 不因显示名变化而分裂。

### 本地模型小样本

每个评测配置先运行 3～5 条相同或相近的日常输入，至少覆盖：问近况、表达关心、主动找话题和一次追问。人工复核以下维度：

- 是否一眼能区分角色；
- 是否有符合角色的句长和停顿；
- 是否避免统一书面腔和重复开场；
- 是否只在有证据或玩家明确提及时谈魔法、事件或私人经历；
- Wizard/Rasmodia 切换是否仍保留同一人物和历史。

小样本通过后才批量生成每人 30 段。网页端用当前 Dialogue Lab 查看新结果；旧会话记录必须明确标记为旧结果，不能当作修复后的证据。

## 不在本次范围内

- 线上/面对面 `remote` / `face_to_face` 话题线程；
- 邀约待面对面承接；
- 游戏内 `BridgeClient.historyByNpc` 跨 SMAPI 或游戏重启持久化；
- 全部 95 个角色的完整口语卡；
- 模型微调、LoRA 或其他训练方案。

