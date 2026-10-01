# 星露谷：话题窗口对照为什么必然测不出差异（2026-10-01）

> **本报告已修订。** 初版的结论是「原因是采样底噪大于待测效应」。当天后续查明
> 真因是**评测路径根本没把窗口轮次的信号传给 prompt** —— 两臂的 prompt 逐字节
> 相同，null 是必然的。底噪确实存在（第四节，原封保留），但它不是这次 null 的
> 原因。两处修正都在下面写明，包括我自己走错的那一步。

## 一、结论

**K=1 / K=4 那次 198 轮、280 万 token 的对照，两臂的 prompt 逐字节相同。**

话题窗口按 `prompts.py:1792` 计算轮次：

```python
_window_signal = _first_value(values, "recentReplies", "recent_replies")
_turn_index = len(_window_signal) if isinstance(_window_signal, (list, tuple)) else 0
```

**只认 `recentReplies`**。而 `scripts/run_character_quality_eval.py` 的 `_build_context`
只发 `history`，签名里没有这个参数，payload 里也没有这个键 —— 于是评测路径
`_turn_index` 恒 0、`start = (0 × K) % 62 = 0`，**窗口永远停在池首，K 毫无作用**。

实测（零请求，`_k_input_delta.py`）：

| 状态 | K=1 vs K=4 的 prompt 差异 |
|---|---|
| 修复前 | **0 字符 / 0.00%，16 条消息逐字节完全相同** |
| 修复后 | 5–7 字符 / 0.01–0.08%，只动 1 条 system 消息 |

⇒ **「话题拓宽没有效果」不成立，「这个实验没有能力回答该问题」成立** —— 但理由
和初版写的不一样：不是被底噪淹没，是**自变量压根没送达**。

而且修复之后，效应量仍然只有**万分之几**：窗口只影响 12 个话题名，K=1 与 K=4
的差别约等于 3 个名字的差价，而整个 prompt 有 8,000+ 字符。**这个量级即便配上
完美指标和零噪音，也几乎不可能在合理样本量下测出来。** 所以第二节的结论
（先修测量再谈机制）依然成立，只是要修的东西换了。

## 二、真因：窗口轮次的信号源没接上

### 2.1 数据流

```
Mod 端 recentReplies（回看档案，≤ 40 条）
      ↓  prompts.py:1792
_turn_index  →  prompts.py:1796 _topic_window_for_turn(topics, _turn_index)
      ↓      start = (_turn_index × _TOPIC_WINDOW_STEP) % len(items)
窗口（12 条）
      ↓  prompts.py:1810
context["identity"]["voiceStyle"]["preferredTopics"]  →  模型
```

`_build_context` 断在第一步。它的签名是
`(builder, case, *, message, history, turn, intent)`，构造出的 payload 有
`npcId / displayName / sourceMods / recentFacts / message / intent / channel /
qualityContext / history / gameState`，**没有 `recentReplies`**，随后直接
`builder.build(payload)`（`scripts/run_character_quality_eval.py:357`）。

### 2.2 为什么注释里早就写了，却还是漏了

`prompts.py:1789-1791` 写着：

> 用跨窗口那一份（请求体的 `recentReplies`，Mod 端回看档案，最多 40 条）计
> 「已经聊过多少轮」：真机 `history` 只有 6 条，拿它当轮次信号会让窗口几乎不滑动。

**这句话正是为「让窗口滑起来」写的**，而评测脚本恰恰是那个「拿 `history` 当信号」
的调用方 —— 它连 `history` 都没能顶替成 `recentReplies`，因为只有在 payload 里
显式提供后者才生效。另有两个调用方（`bridge/tests/test_evidence_pool_width.py:102`、
`scripts/probes/verbatim_probe.py:241`）主动构造了它，评测主脚本却漏了。

### 2.3 修法与保守性

在 `_build_context` 里从 history 提取 assistant 项即可 —— `recentReplies` 的语义
就是「NPC 已经说过的回复」：

```python
recent_replies = [
    str(item["content"])
    for item in history_items
    if item.get("role") == "assistant" and item.get("content")
][-_RECENT_REPLIES_LIMIT:]
```

上限 `_RECENT_REPLIES_LIMIT = 40`，与 `models.DialogueTestRequest.recent_replies`
的 `max_length=40` 同源，避免评测喂出线上不可能出现的超长窗口。

**天然的保守性**：评测里多数 `case.history` 不含 assistant 项 ⇒ `recent_replies`
为空 ⇒ 行为与改动前逐字节相同；只有多轮 case 走到第 2 轮起、
`conversation_history` 长出 assistant 项后窗口才真正开始滑动。既有结果的可比性
不受影响。

## 三、效应量：修好之后也只有 0.08%

窗口滑动的**结构**差异是真的：12 条窗口下，相邻轮交集 K=1 为 11 条（新进 1 条）、
K=4 为 8 条（新进 4 条）。44 个角色里 **42 个是宽池**（> 12 条），只有
**Alex（11 条）和 Leo（12 条）** 全池 passthrough、不受 K 影响。

但落到字符上就微不足道了 —— 12 条列表里换掉 1 条 vs 4 条 ≈ 3 个名字：

| history | K=1 字符 | K=4 字符 | 差异 | 占比 | 变化的消息 |
|---|---|---|---|---|---|
| 0 | 8,215 | 8,215 | 0 | 0.00% | 0/16 |
| 2 | 8,399 | 8,404 | 5 | 0.06% | 1/18 |
| 4 | 8,451 | 8,453 | 2 | 0.02% | 1/20 |
| 8 | 8,451 | 8,445 | 6 | 0.07% | 1/20 |
| 10 | 8,450 | 8,443 | 7 | 0.08% | 1/20 |

（`compactPrompt=true`，Sophia，12 条窗口）

⇒ **窗口轮换是个「结构性确定、内容上极小」的干预。** 想让它可测，要么放大它的
可见面（让窗口出现在更多卡片里、或让两臂差距更大），要么改用不依赖模型输出的
**直接指标**（窗口轮换本身是确定性的，可以直接断言，见第六节）。

## 四、采样底噪（保留：初版的决定性证据，但它不是本次 null 的原因）

用线上口径（`compactPrompt=true`）构造 Wizard 的真实 prompt（13 条消息 / 5,945 字符），
`moonshotai/Kimi-K2.5`、`max_tokens=400`，每个条件连发 5 次，两两比较：

| 条件 | 相似度中位数 | 均值 | 逐次完全相同 |
|---|---|---|---|
| **默认温度**（= 当前线上与评测的实际行为） | **0.222** | 0.223 | **0 对** |
| `temperature = 0` | 0.403 | 0.441 | **0 对** |

三点判读：

1. **默认温度下没有一次重复。** 同一 prompt 连发 5 次，10 个两两组合里**没有任何一对**
   输出相同。逐次观测**全部**是独立噪音。
2. **`temperature=0` 确实有效但不彻底**（+81%）。仍无一对相同，说明上游没有真正
   把温度归零（K2.5 一类推理模型常忽略该参数），或中转站未透传。
3. ⇒ **真正的降噪手段是多次采样取平均**，不是把这一项设成 0 就完事。
   方差按 1/N 下降，代价是 N 倍请求。

**⚠ 这段与第二节是两件独立的事。** 底噪让任何 prompt 级 A/B 都难以判读；而
`recentReplies` 缺失让这次特定的 A/B **根本没有自变量**。两者都真，但后者是
本次 null 的充分原因 —— 哪怕底噪为零，两臂 prompt 相同也测不出差异。

### 为什么之前没发现

`scripts/analyze_ab_power.py` 其实早就写明了症结：

> σ 含**两种**波动：① 轮与轮之间的真实差异 ② **跑与跑之间的漂移**
> …… 2026-09-28 那次处理的效应量约 **+5.7 字**，而**对照组自己动了 −12.9 字**
> ⇒ 效应远小于噪音 ⇒ 负结果是**必然**，不是「改动没用」。

它建议改用配对设计消掉方差。但配对只能消掉**角色间差异**，消不掉**逐次采样漂移**——
实测证明后者才是主项：K 实验做了配对（n=196），reply 长度差异仍只有 +1.43 字
（t=+0.79，p=0.431），**配对几乎没有消掉方差**。

## 五、评测口径不一致（本次已修；但归因更正）

### 5.1 实测的三条路径

同一请求，改 `compactPrompt` 与 `qualityContext.naturalMode`，
统计 11–12 条窗口话题素材在 prompt 里出现的次数：

| 组合 | 总字符 | 素材密度 | 承载卡 |
|---|---|---|---|
| `compact=F natural=T`（**评测现状**） | 6,118 | **1.2 / 条** | 仅 `persona_core` |
| `compact=T natural=T` | 5,774 | 1.2 / 条 | 仅 `persona_core` |
| `compact=T natural=F`（**线上口径**） | 6,745 | **3.1 / 条** | + `stage_execution_card`、`final_role_voice_contract` |
| `compact=F natural=F` | 9,860 | **6.1 / 条** | + `conversation_lead` |

两个开关各管一段，**互不替代**：

- **`naturalMode=True` 造成主要损失**：`stage_execution_card` 从 1,431 字压到 507 字，
  **素材命中归零**（`prompts.py:6886` 的 `if not compact and not natural_mode` 决定
  `stagePolicy` 是否进 prompt；`natural_adaptive_light` 另有一层砍卡）。
- **`compact=True` 砍掉 `conversation_lead`**（22 次素材命中）。

### 5.2 ⚠ 归因更正

初版这里写的是「路径差异让 K 的改动**更显眼**而不是更隐形，所以把 null 归因于
路径是错的」。**这句话是错的，本次撤回。**

`run_character_quality_eval.py:300-312` 确实只对 `deep-flirt-*`、`relationship-gate-*`
和 `adaptive+topic` 三类 case 设 `naturalMode=True`，K 实验的 66 个 case 多数是
`*-daily` / `*-follow-up`，走 `c=F n=F`、素材密度 6.1 / 条。**但素材密度高不等于
窗口在滑动** —— 窗口的轮次信号由 `recentReplies` 决定，与素材密度无关。
密度 6.1 只是把**同一个恒定窗口**渲染了更多遍。

⇒ 正确说法：**路径差异真实存在、值得修（已通过 `--compact-prompt` 修），但它和
本次 null 无关；null 的原因是 `recentReplies` 缺失（第二节）。** 两次归因我都走错
过，一并记在这里。

## 六、指标覆盖不足（未修）

即便把路径和信号源都修好，0.01–0.08% 的效应量配上 0.222 的底噪也测不出来。
独立存在的缺陷：

| 指标 | 现状 |
|---|---|
| `conversationLeadKind` | `None` 58.6% / 59.1%、`''` 22.2% / 24.2% ⇒ 仅 **19.2% / 16.6%** 的轮次带真实值（约 38 轮可用） |
| `mechanicalRestatementCount` | **两臂恒为 0** |
| `hasNewAnchor` | True 62/197 vs 56/197 —— 方向与预期相反，且它测的是 `conversationLead` 的锚点，**与话题窗口轮换无关** |
| 话题窗口轮换 | **没有任何直接指标** |

⚠ 需要说明 `topicMatches`（`character_quality_eval.py:4513`）**不是**窗口覆盖指标：
它是该 case 的 `expected` 词表在回复里的字面命中，属于**个案级**度量，
**不反映 12 条窗口自身轮换了多少**。拿它当窗口指标是误用。

## 七、本次改动

### 7.1 `scripts/run_character_quality_eval.py` — 接上 `recentReplies`（本次核心修复）

`:352` 处把 history 抽成 `history_items` 复用，新增 `recentReplies` 键与
`_RECENT_REPLIES_LIMIT = 40` 常量。

测试（`bridge/tests/test_run_character_quality_eval.py`）：

- `test_build_context_forwards_recent_replies_from_history` —— 只取 assistant 项
- `test_build_context_sends_empty_recent_replies_without_assistant_turns` —— 空列表
  而非缺键，让「这条路径接上了」在 payload 层可断言
- `test_recent_replies_are_capped_like_the_request_model` —— 40 条上限，且保留
  **最近** 40 条

### 7.2 `scripts/run_character_quality_eval.py` — 新增 `--compact-prompt`

compact 此前只能跟着 `--economical` 走，而后者会把 case 限到 3 个，**没法用来做正式对照**。
现在两者解耦，默认不变（`None` ⇒ 沿用历史行为），既有结果保持可比。

- CLI 注册：`--compact-prompt`（`action="store_true", default=None`）
- 预算传递：`compact_prompt=(default_budget.compact_prompt if args.compact_prompt is None else args.compact_prompt)`
- 测试：`test_compact_prompt_switch_is_independent_of_economical`（钉住互不牵连，
  且 `EvaluationBudget.economical().compact_prompt` 仍为 True、默认仍为 False）

### 7.3 `config.py` + `providers.py` — 采样温度可配（默认不发）

- `ProviderSettings.temperature: float | None = None`；环境变量 `BRIDGE_{LOCAL,CLOUD}_TEMPERATURE`
- `providers.py` 两个 payload 各自支持：OpenAI 兼容走顶层 `temperature`，
  Ollama 风格走 `options.temperature`
- **`None` ⇒ 键根本不存在**，与加这个字段之前逐字节一致，不影响任何既有 A/B 的可比性

⚠ **踩到的坑**：不能复用现成的 `_env_float` —— 它是
`parsed if parsed > 0 else default`，会把 `temperature = 0`
（这里**最**有意义的取值）静默丢成默认值，配置看起来设了、实际等于没设。
为此单写了 `_env_optional_float`，允许 0，拒绝越界（[0, 2]）与非法输入。

测试：`test_temperature_is_only_sent_when_configured`
（不设 ⇒ 无键；0.0 与 None 必须可区分，因为 0.0 是 falsy）。

## 八、下一步的优先级

按「能不能真的改变结论」排序，不按工作量：

1. **补话题窗口轮换的直接指标**（第六节）。窗口滑动是**确定性**的：给定
   `len(recentReplies)` 与 `_TOPIC_WINDOW_STEP`，`start` 唯一确定。所以可以
   零请求断言「第 N 轮应该看到哪 12 条」「相邻轮新进几条」。
   **这是本次唯一能立刻拿到的可测性提升**，且不受底噪影响。
2. **多次采样取平均**（唯一真正降噪的手段）。同一 `(case, turn)` 跑 N 次取指标均值，
   方差按 1/N 降。先做**小样本标定**：取 5 个 case × 3 轮 × 3 次重复，
   量出「重复内方差」与「case 间方差」各占多少，再决定 N 与样本量。
3. **`temperature=0` 的残余噪音**需要确认是上游忽略还是中转站不透传 ——
   若上游支持更低温度档位，可再压一截。
4. **放大 K 的可见面**（产品决策，非测量问题）。若希望 K 真的影响输出，得让它
   出现在更多卡片或更靠前的指令位；维持现状则应把它当**低风险微调**接受，
   不追求 A/B 级别的证据。

**不建议**在没有 1 或 2 的情况下重跑 prompt 级 A/B：以 0.01–0.08% 的效应量配
0.222 的底噪，再跑一次 198 轮得到的仍然只会是「两臂差不多」。

## 附：可复现命令

```powershell
$wt = 'E:\workspace\projects\stardew-ai-npc.worktrees\story-memory'
$py = 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = "$wt;$wt\bridge\src;$wt\scripts;$wt\bridge\tests"

# 【新增】K=1 与 K=4 的输入差异（零请求，第二节与第三节的全部数字）
& $py -B 'E:\workspace\.scratch\stardew-night\_k_input_delta.py'
#   → 结果落盘 _k_input_delta_result.txt

# 噪音底噪（真发请求，10 次调用 ≈ $0.02）
& $py -B 'E:\workspace\.scratch\stardew-night\_noise_probe.py'

# 评测路径 vs 线上口径的素材密度（零请求）
& $py -B "$wt\scripts\run_character_quality_eval.py" --plan --compact-prompt

# 相关测试
& $py -B -m pytest "$wt\bridge\tests\test_run_character_quality_eval.py" -q -p no:cacheprovider
& $py -B -m pytest "$wt\bridge\tests\test_providers.py" -q -p no:cacheprovider
```

凭据：探针按池顺序从 `~/.dsh/.credentials.yaml` 读，**不读也不写 `.env.local`**
（那里的 key 额度已耗尽）。10-01 当时池 1 周剩 59.5%。
