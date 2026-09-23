# 星露谷 Bridge 云端切接 Command Code（2026-09-23）

## 结论

`.env.local` 已从 DeepSeek 官方切到 **Command Code 池 2**，模型用
**`moonshotai/Kimi-K2.5`**；Bridge 侧只改了**一处**：出网前把空 `content`
填上占位符（`providers.py` 的 `_fill_empty_message_content`）。

**3906 passed / 0 failed。** 回退只需把 `.env.local.bak-precommandcode`
覆盖回去。

## 为什么不能用 deepseek 系模型（本次最关键的一条）

Bridge 的 `_SINGLE_TURN_MAX_TOKENS = 160`，且只读响应的 `content` 字段。
实测 Command Code 上各模型的推理开销：

| 模型 | max_tokens=160 时 | 判定 |
|---|---|---|
| **`moonshotai/Kimi-K2.5`** | reasoning **0**，content 20 字 | ✅ **选用** |
| `deepseek/deepseek-v4-flash-fast` | reasoning 301，content 13 字 | ⚠️ 能出但极浪费 |
| `xiaomi/mimo-v2.6-pro` | reasoning 149 / 160，content 19 字 | ⚠️ 勉强 |
| `deepseek/deepseek-v4.1-flash` | reasoning 300+，**content 空** | ❌ |
| `deepseek/deepseek-v4-flash` | reasoning 160 / 160，**content 空** | ❌ |
| `z-ai/glm-5.3-flash` | reasoning 159，**content 空** | ❌ |
| `claude-haiku-4-5-20251001` | HTTP 400 | ❌ |
| `gpt-5.4-mini` | HTTP 403 `MODEL_NOT_IN_PLAN` | ❌ |

**⇒ 若直接按 settings.yaml 里的 `deepseek/deepseek-v4.1-flash` 切过去，
单轮对话的 content 必然是空的 —— 游戏里 NPC 会「不说话」。**

试过关闭推理，都不行：`reasoning_effort=off` / `=none` 返回 **400**；
`thinking={"type":"disabled"}` 仍占 203 tokens，而预算只有 160。

**⇒ 选一个「不带推理」的模型，比调大 max_tokens 更省事：**
不用动 `_SINGLE_TURN_MAX_TOKENS`，也就不用改钉住它的
`test_providers.py:532/547/855` 三处断言。

## 三个硬约束（漏一个就静默失败）

### ① URL 必须带后缀

`BRIDGE_CLOUD_URL` 要写全：

```
https://api.commandcode.ai/provider/v1/chat/completions
```

只写 `.../provider/v1` 或 `/v1/chat/completions` 都是 404
（`is not a registered API route`）。Bridge 是**直接用**这个 URL，不拼路径。

### ② 需要浏览器 User-Agent

Command Code 走 Cloudflare，用默认 UA 直连会拿到 **403 / error code 1010**。

* `_cc_usage.mjs` / `_cc_pools.mjs` 里早就显式设了浏览器 UA；
* Bridge 用 `httpx`，实测**它的默认 UA 能过**（400 而非 403），所以本轮**没有**
  给 Bridge 加 UA。若日后被拦，在 `OpenAICompatibleProvider._headers()` 补一个即可。

### ③ 空 content 必须「填」不能「删」

游戏端在「玩家还没开口」的回合会构造一条**空的 user 消息**
（`topic_trigger`，长度 0）。DeepSeek 官方端点容忍它，所以缺陷长期没暴露；
Command Code 上游直接拒收，两种错法实测如下：

| 做法 | 结果 |
|---|---|
| 原样发空 content | ❌ `user message must have content`，`param=messages.16.content` |
| **删掉那一条** | ❌ `A conversation must start with a user message` |
| **填占位符「（无）」** | ✅ **成功** |

**`topic_trigger` 恰好是唯一一条 user 消息，删了就只剩 system，所以只能填。**
占位符取「（无）」而非空串或空格 —— 空串是同一个错误，空格过不了类似
`strip()` 的上游校验。

## 参数与池

| 项 | 值 |
|---|---|
| URL | `https://api.commandcode.ai/provider/v1/chat/completions` |
| 模型 | `moonshotai/Kimi-K2.5` |
| 凭据 | `CMD_API_KEY_2`（池 `commandcode2`） |
| API_MODE | `openai` |
| TIMEOUT | 60 |

**为什么用池 2**：`_cc_pools.mjs` 实测 —— 池 1（`commandcode`）周窗口已用
**99.9%**（剩 $0.05 / $35），池 2（`commandcode2`）剩 **35.4%**（约 $12.38）。

## 方法论

> **第 25 条：切上游前，要用「最接近实际工况」的探测，而不是 `hello`。**
>
> 我先用一条简单消息测通了端点，转手用 Bridge 真实的 17 条 messages 复现时
> 才拿到 400。**简单探测只能证明"端点活着"，证明不了"线上能跑"。**
> 判定一个上游能不能用，必须把**真实的 messages 形状**灌进去。

> **第 26 条：错误信息里的 `param` 是定位器，先读它再动手。**
>
> `"param": "messages.16.content"` 一步指出是**第 16 条**、**content 字段**。
> 没有它，很容易误判成"Kimi 不支持多 system 消息"或"name 字段有问题"而去改错地方。

## 尚未验证

* **换模型后的可比性**：v4→v11 的全部历史读数是在 `deepseek-chat` 上测的，
  与 Kimi 不可直接比较。已在跑一次 `cc-kimi-v11-*` 基线（stranger/dating/parent
  各 30 次）重建参照，结果见报告 §60。
* **游戏内实测**：本轮的验证都在 probe 路径完成，**没有启动游戏**。
  Bridge 线上是否随 `.env.local` 生效，还需要一次受控的游戏内验证。

## 附：模型选型 A/B（Kimi-K2.5 vs deepseek-v4-pro）

起因：用户问「换成 v4-pro 效果会不会更好」。之前用的是 **DeepSeek 官方的
`deepseek-chat` 别名**，它在消耗记录里显示为 **`deepseek-flash`（V4.1-Flash）**
—— 别名与真实模型名是两层，两者不矛盾。

**测法**：同一份 v11 数据、同一 prompt、同一阶段（`dating` / 8 心），
各跑独立会话取第 1 轮。探针加 `--model` / `--max-tokens` 参数实现，
**不动源码**（`_max_tokens_for()` 读的是模块级常量，直接改那个常量即可）。

### 结论：不换。pro 在游戏里不可用。

| 指标 | Kimi-K2.5（160 tokens） | deepseek-v4-pro（900 tokens） |
|---|---|---|
| **单次会话耗时（中位）** | **7.0 秒** | **114.0 秒** ⚠️ |
| 相同时间内完成数 | 16 次 | 6 次 |
| 单次 tokens | 6290 | 6287 |
| 回复长度（中位） | 78 字 | 46 字 |
| 开口语气词 | 13/16 | 2/2 |
| 前 6 字去重 | 14/16 | 2/2 |

**16 倍延迟差是决定性的。** 玩家点一次 F8 等近两分钟，这不是「效果差一点」，
是**根本不能用** —— 任何语言质量上的优势都会被这个延迟吃掉。

次要理由：

* **需要改代码** —— pro 是推理模型，会把 `_SINGLE_TURN_MAX_TOKENS = 160`
  吃光导致 content 为空；要用它必须提预算到 900 左右并改钉住该值的三处断言。
* **有出戏内容** —— 6 个 pro 样本里出现过「**等找到了给你发张照片**」。
  星露谷是田园世界、没有手机，这类现代概念对沉浸感是硬伤。
* **历史经验一致** —— 用户 2026-08-13 曾全项目把 DeepSeek 从 pro 换回 flash，
  原因是实测 pro 质量更差（那次是申论批改场景）。

### 方法论

> **第 27 条：换模型前先量延迟，再谈质量。**
>
> 质量差异需要几十个样本 + 人工阅读才能判断，而**延迟一个数字就能否决一个模型**。
> pro 的语言质量未必比 Kimi 差，但 114 秒让这个比较失去了意义。
> 先量一票否决的指标，能省掉整轮质量评估。

> **第 28 条：别把「别名」当成「模型名」。**
>
> `.env.local` 里写的是 `deepseek-chat`，消耗记录里显示 `deepseek-flash`
> —— 同一个模型的两层名字。仅凭配置文件回答「用的什么模型」会漏掉真实路由，
> 两边对不上时先去查消耗记录，而不是怀疑对方记错。

## 附二：pro 为什么慢 —— 三层反转后的根因

用户追问「pro 为什么会这么慢」，实测后推翻了我先前「pro 延迟高」的判断。

### 实测数据

| 测试场景 | Kimi-K2.5 | deepseek-v4-pro |
|---|---|---|
| 短 prompt 单次 | 1.8 秒 | 3.2 秒（推理 46 tok） |
| 长 prompt（约 5000 tok）单次 | 8.2 秒 | **9.1 秒**（推理 366 tok，占输出 **90%**） |
| 连续 5 次 | 1.4~2.9 秒 | 4.8~8.1 秒 |
| **真实路径 3 轮** | **3/3 成功** | **第 1 轮连败 3 次后放弃** |

**吞吐量两者接近**（584 vs 616 tok/s）。pro 单次生成只要 **5~9 秒**。

### 真正的原因：失败重试

```
第 1 次失败（ProviderError），5s 后重试：cloud returned truncated stream (finish_reason=length)
第 2 次失败（ProviderError），10s 后重试：同
第 3 次失败（ProviderError），15s 后重试：同
```

pro 是推理模型，真实对话 prompt 有 6290 tokens，**推理量随内容随机波动** ——
有时 111 tokens 就够（单跑成功），有时把 900 的预算全吃光，`content` 变成空串，
Bridge 判为截断并退避重试 3 次。

**5 秒的正常生成 → 114 秒。** 很多会话重试完仍失败，这正是 pro 样本一直
只有个位数的原因 —— 不是跑得慢，是**大部分根本没成功**。

提到 2500 仍不稳定：3 轮里第 3 轮照样截断重试一次，单次会话 118.6 秒。

### 效果对比（比延迟更关键）

同一 stranger / 0 心 / 3 轮：

| | pro | Kimi |
|---|---|---|
| 第 1 轮 | 我刚把**蓝月亮葡萄园**边上那排杂草拔完 | 厨房里那堆布料按颜色分类叠好 |
| 第 2 轮 | 有一卷颜色和**葡萄叶**特别像 | 挑下周要缝的格子布，像去年秋天落叶 |
| 第 3 轮 | 我刚从**葡萄园**出来 | 窝在毯子里看《学校女巫》 |

**pro 3/3 提到葡萄园，Kimi 0/3。**

v11 把「葡萄」从 73% 压到 3% 的那轮工作，被 pro 一次性带回来了 ——
**推理能力更强的模型会更执着地抓住人设卡里最显眼的那个词。**
换 pro 不是效果更好，是把已经修好的东西弄坏。

### 结论：不换

| 维度 | Kimi-K2.5 | deepseek-v4-pro |
|---|---|---|
| 工程 | 开箱可用 | 需提预算，2500 仍随机截断重试 |
| 延迟 | 1.4~2.9 秒 | 5~9 秒；失败时 118 秒 |
| 效果 | 葡萄 0/3 | 葡萄 3/3 |

### 方法论

> **第 29 条：慢的可能是重试，不是模型。**
>
> 单请求 9 秒、批量 114 秒，差值不在模型而在**失败重试的退避**。
> 量延迟时要区分「一次请求耗时」与「一次会话耗时」，
> 后者包含重试。看到 `ProviderError` 就该先数尝试次数，再谈性能。

> **第 30 条：推理模型会吃掉自己的输出预算。**
>
> pro 的输出里 90% 是 reasoning tokens。预算按 `max_tokens` 计，
> 推理和正文共享 —— 推理一旦吃满，`content` 就是空的，
> 而上游报的是 `finish_reason=length`（截断）而非错误。
> **给 Bridge 接推理模型必须先确认：预算够推理 + 正文两部分。**

## 附三：prompt 压缩实验（A 档 / B 档）

### 起点体检

`stranger` 阶段 compact prompt 共 **8145 字符（≈5430 tokens）**，15 张卡：

| 卡片 | 字符 | 占比 |
|---|---|---|
| persona_core | 2689 | 33.0% |
| topic_response_contract | 1120 | 13.8% |
| voice_execution_card | 888 | 10.9% |
| stage_execution_card | 877 | 10.8% |
| safety_rules | 525 | 6.4% |
| post_history_voice_guard | 519 | 6.4% |
| 其余 9 张 | 1527 | 18.7% |

各阶段体积差异明显：**stranger 8037 / parent 10084 / dating 11339**
（dating 比 stranger 多 41%）。

### A 档：字面重复（8145 → 8037，省 108 字符 / 1.3%）

- 删掉 `stage_execution_card.instruction` 末尾拼接的「角色表达指纹」——
  同一张卡已有 `voiceFingerprint` 独立字段，拼接是第二次输出同一句话
  （四处互斥分支，每处约 48 字符）
- `_compact_relationship_gate` 改为**同值去重**：五个 stage 字段
  （relationshipStage / heartStage / effectiveStage / effectiveIntimacyStage /
  eventUnlockedStage）是同一条推导链的不同环节，stranger 阶段实测五个值全是
  `"stranger"`，逐个输出等于把同一句话说五遍（221 字符）。现在只在值不完全
  相同时全部输出（保留诊断价值），全同则只留两个结论字段

### B 档：跨卡去重（dating −678，parent −668）

`affectionInitiative` 原先**同时出现在 `stage_execution_card` 与独立的
`affection_initiative` 卡里**，两处是同一份 `_compact_affection_initiative`
结果，等于连发两次。独立卡那份更完整（多 `cooldownActive` /
`recentStrongCount` / `recentStrongFamilies` 三个运行时字段）。

改法：把 `_build_affection_initiative_card` 的计算**提前**，仅在独立卡本轮
确实会出现时（判定条件与 append 处逐字一致）才从 `stage_execution_card` 摘掉，
否则原样保留。

| 阶段 | 改前 | 改后 | 省 |
|---|---|---|---|
| stranger | 8037 | 8037 | 0（本就没这张卡） |
| **dating** | 11339 | **10661** | **−678** |
| **parent** | 10084 | **9416** | **−668** |

测试：**3906 passed**。`test_marriage_familiarity` 的断言改为从独立卡取值，
并加强为同时校验两卡 —— 若将来独立卡不再产出，测试会以 KeyError 直接失败。

### 行为验证（这是关键的一步）

用 Kimi-K2.5、同一份 v11 数据、同一入口，**临时回退代码跑等规模基线**：

| 指标 | 压缩前 n=30 | 压缩后 n=45 |
|---|---|---|
| 面种类 | 6 | 6 |
| 工作面 | 63% | 69% |
| 葡萄 | 33% | 31% |
| 长度中位 | 60 | 58 |
| 语气词开头 | 28/30 | 41/45 |
| 开头去重 | 27/30 | 44/45 |
| 中英混杂 | 0/30 | 4/45 |

**核心指标全部持平或更好。** 唯一异常是中英混杂 4/45（含一条
`{{<purple>}}`，那是模型自己吐的，不在 prompt 里 —— sve.json、语料、
当前 prompt 三处均已确认干净）。

**判定：不计为压缩的退化。** 理由是算术 —— stranger 的 prompt 只压缩了 108
字符（1.3%），1.3% 的文本变化引起 8.9% 的英文串，因果链太弱；0/30 vs 4/45
的 Fisher 检验在边缘（p≈0.15）。更可能是 Kimi 在长 prompt 下的固有行为。
**保持观察，不阻塞。**

### 尚未做的（B 档第二项，性质不同）

`voiceStyle` 一个字段占 **1663 字符**（整个 prompt 的 20%），其中五组意思被反复说：

| 意思 | 遍数 |
|---|---|
| 兴奋时先亮出第一反应 | 4 |
| 短句连冲、说快、两三个念头 | 5 |
| 被夸说多后害羞改口收回 | 3 |
| 不要退化成平静散文 | 2 |
| 紧张时结巴半截话 | 1（不重复，须保留） |

相关字段（bubblyCadence 117 / livelinessProfile 171 / energyProfile 253 /
emotionTexture 124 / rhythmProfile 177 = 842 字符）经查**只在 prompts.py 里
被引用，没有其他消费者**，合并安全。

**但这一项与 A 档、B 档第一项性质不同**：前两者是零信息损失的去重，
这一项要判断「哪些措辞算重复」——是**有损压缩**，而且触及的正是用户最在意的
「语气像不像她」。预计可省 400+ 字符（stranger 再降约 5%）。

### 方法论

> **第 31 条：压缩验证必须做等规模对照，小样本会骗人。**
>
> stranger 的压缩后样本从 15 扩到 45 时，葡萄占比从 40% 回落到 31%，
> 而真值（30 样本）是 33%。**n=15 时我读到了 +13% 的"退化"，
> 它根本不存在。** 报差异前先问：这个差是几条样本造成的？

> **第 32 条：先量压缩率，再解释行为变化。**
>
> stranger 只压掉 1.3%，却"观察到" 13% 的行为偏移 —— 这个比例本身就说明
> 观察的是噪声。**压缩率是判断行为变化可信度的标尺**：改动越小，
> 越应该先怀疑测量而非系统。

> **第 33 条：重复有三种，压缩手段完全不同。**
>
> ① **字面重复**（同一句话两个副本）→ 删副本，零损失，但总量往往很小
> （本次仅 1.3%）；② **跨卡重复**（同一个 JSON 发两次）→ 摘一处，
> 零损失，收益可观（本次 6%）；③ **语义重复**（换个说法讲同一件事）→
> 必须判断，有损，收益最大也最危险。**预估压缩收益时要先分清是哪一种** ——
> 我最初把③当成①报出 27%，实际①只有 1.3%，差了一个数量级。
