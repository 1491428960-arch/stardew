# 星露谷：为什么话题窗口对照测不出差异（2026-10-01）

## 一、结论

**K=1 / K=4 那次 198 轮、280 万 token 的对照，没有测到任何信息。**

原因不是机制无效，而是**测量工具本身的底噪就比待测效应大**：

| 量 | 数值 |
|---|---|
| 同一 prompt 连发 5 次的逐次输出相似度（默认温度） | **0.222** |
| K=1 vs K=4 跨臂的逐轮输出相似度 | **0.203** |
| 差距 | **8.7%** |

跨臂差异**落在同 prompt 的噪音范围内**，所以「两臂指标几乎相同」是必然的：
两臂的 prompt 确实不同，但每次生成的随机性足以吞掉这点不同。

⇒ **「话题拓宽没有效果」这个结论不成立；「这个实验没有能力回答该问题」才成立。**
两者在报告里长得一模一样，但后者要求先修测量，而不是回头改机制。

## 二、噪音底噪实测（决定性证据）

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

### 为什么之前没发现

`scripts/analyze_ab_power.py` 其实早就写明了症结：

> σ 含**两种**波动：① 轮与轮之间的真实差异 ② **跑与跑之间的漂移**
> …… 2026-09-28 那次处理的效应量约 **+5.7 字**，而**对照组自己动了 −12.9 字**
> ⇒ 效应远小于噪音 ⇒ 负结果是**必然**，不是「改动没用」。

它建议改用配对设计消掉方差。但配对只能消掉**角色间差异**，消不掉**逐次采样漂移**——
实测证明后者才是主项：K 实验做了配对（n=196），reply 长度差异仍只有 +1.43 字
（t=+0.79，p=0.431），**配对几乎没有消掉方差**。

## 三、评测路径与线上口径不一致（本次已修）

### 3.1 实测的三条路径

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

### 3.2 但它不是 K 实验 null 的原因

`run_character_quality_eval.py:300-312` 只对 `deep-flirt-*`、`relationship-gate-*`
和 `adaptive+topic` 三类 case 设 `naturalMode=True`。
K 实验的 66 个 case 多数是 `*-daily` / `*-follow-up`，**走的是第 4 行（`c=F n=F`），
素材密度 6.1 / 条，比线上还高一倍**。

⇒ 路径差异真实存在、值得修，但它让 K 的改动**更显眼**而不是更隐形。
把 null 归因于路径是错的；**归因于底噪才对**。这是本次排查中我自己先走错、
又被数据纠正的一步，记在这里以免复现。

## 四、指标覆盖不足（未修）

即便有了完美指标，0.222 的底噪也会淹没 prompt 级效应 —— 所以这一项优先级**低于**降噪。
但它独立存在：

| 指标 | 现状 |
|---|---|
| `conversationLeadKind` | `None` 58.6% / 59.1%、`''` 22.2% / 24.2% ⇒ 仅 **19.2% / 16.6%** 的轮次带真实值（约 38 轮可用） |
| `mechanicalRestatementCount` | **两臂恒为 0** |
| `hasNewAnchor` | True 62/197 vs 56/197 —— 方向与预期相反，且它测的是 `conversationLead` 的锚点，**与话题窗口轮换无关** |
| 话题窗口轮换 | **没有任何直接指标** |

⇒ 现有评测量的是「对话引导」「机械复述」，而 K 改的是**话题窗口**。
**测的东西和改的东西不是一回事** —— 这是除底噪之外的第二个独立缺陷。

## 五、本次改动

### 5.1 `scripts/run_character_quality_eval.py` — 新增 `--compact-prompt`

compact 此前只能跟着 `--economical` 走，而后者会把 case 限到 3 个，**没法用来做正式对照**。
现在两者解耦，默认不变（`None` ⇒ 沿用历史行为），既有结果保持可比。

- CLI 注册：`--compact-prompt`（`action="store_true", default=None`）
- 预算传递：`compact_prompt=(default_budget.compact_prompt if args.compact_prompt is None else args.compact_prompt)`
- 测试：`test_compact_prompt_switch_is_independent_of_economical`（钉住互不牵连，
  且 `EvaluationBudget.economical().compact_prompt` 仍为 True、默认仍为 False）

### 5.2 `config.py` + `providers.py` — 采样温度可配（默认不发）

**这是本次唯一能直接改善可测性的改动。**

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

## 六、下一步的优先级

按「能不能真的改变结论」排序，不按工作量：

1. **多次采样取平均**（唯一真正降噪的手段）。同一 `(case, turn)` 跑 N 次取指标均值，
   方差按 1/N 降。先做**小样本标定**：取 5 个 case × 3 轮 × 3 次重复，
   量出「重复内方差」与「case 间方差」各占多少，再决定 N 与样本量。
2. **补话题窗口轮换的直接指标**（第四节）。在降噪之前做也可以，但单独做不会让
   K 类实验变得可判读。
3. **`temperature=0` 的残余噪音**需要确认是上游忽略还是中转站不透传 ——
   若上游支持更低温度档位，可再压一截。

**不建议**在没有 1 的情况下重跑任何 prompt 级 A/B：以 0.222 的底噪，
再跑一次 198 轮得到的仍然只会是「两臂差不多」。

## 附：可复现命令

```powershell
$wt = 'E:\workspace\projects\stardew-ai-npc.worktrees\story-memory'
$py = 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = "$wt;$wt\bridge\src;$wt\scripts"

# 噪音底噪（真发请求，10 次调用 ≈ $0.02）
& $py -B 'E:\workspace\.scratch\stardew-night\_noise_probe.py'

# 评测路径 vs 线上口径的素材密度（零请求）
& $py -B "$wt\scripts\run_character_quality_eval.py" --plan --compact-prompt

# 相关测试
& $py -B -m pytest "$wt\bridge\tests\test_providers.py" -q -p no:cacheprovider
& $py -B -m pytest "$wt\bridge\tests\test_run_character_quality_eval.py" -q -p no:cacheprovider
```

凭据：探针按池顺序从 `~/.dsh/.credentials.yaml` 读，**不读也不写 `.env.local`**
（那里的 key 额度已耗尽）。10-01 当时池 1 周剩 59.5%。
