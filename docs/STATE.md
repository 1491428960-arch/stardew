# 当前状态：prompt 指令体检（2026-09-28）

> **本文档的服务对象是「下一个开工会话的 agent」，不是人。**
> 只放**结论与证据强度**，不放推演过程 —— 过程在
> `docs/report-instruction-conflicts-2026-09-28.md`（归档）与 `docs/active-work.md`（流水）。
> 最后更新：2026-09-29 凌晨（本轮把「**一条长度约束要过五道闸**」固化成
> 可运行工具 `scripts/probe_length_constraint_decay.py`，**独立复现了核心结论「1/6」**，
> 并新增一个比值 **1 : 11.3**（按文本量）；台账盲区从四类扩到**六类**；
> 另核实了 `responseRules[0]` 实验的**真实落点**与**基线洁净性**）。
> ⚠ **需要用户拍板的事集中在 `docs/待决策.md`。**

---

## 一、30 秒速览

> **并行的另一条线（2026-09-30 夜，与本文档主题无关，仅作导航）**：
> NPC 话题素材扩充 —— `preferredTopics` 264 → **1336 条**（44 角色，平均 30.4），
> 并改了 `prompts.py` 一处：新增 `_topic_window_for_turn`，让进 prompt 的 12 条窗口**逐轮滑动**
> （池 ≤ 12 时返回全池，故落地时**零行为变化**）；另删了 `stage_policy.py` 里 Sebastian 模板
> 的一段重复硬编码（26 字），把他的素材从 9 条放到 43 条。全量 **4365 passed**，**已提交 `d14545a`**。
> 详情：`docs/active-work.md` 末尾「续：话题素材第 9 批 + 宽池扩库」与「续二：收口」；
> 完整报告在 hub：`E:\workspace\hub\docs\report-stardew-preferred-topics-expansion-2026-09-30.md`。
> ⚠ 这条线**不改变本文档的任何结论**，两者的测试基线各自独立验证过。

- **在做什么**：星露谷 NPC Bridge 的 prompt 指令体检 —— 找「同一约束被反复写、
  模型挑最松那条执行」的问题，并把结论固化成**可复跑的检查工具**。
- **结论**：真冲突**只有一处**（长度），**已修 + 已云端证明 + 已有守卫**。
  我一开始报的另外几处，**全部是我自己读错**（见 §三）。
- **本轮新增（06:00–06:52）**：
  - ✅ **处方 C**：评测产物现在同时记 `scrubbedReply` / `scrubChanged`。
  - ❌ **`responseRules[0]` 实验：负结果，已回滚**（见 §三）。
  - ⚠ **发现抽取器只覆盖 27%** ⇒ 放宽后 **69%** ⇒ **此前「0 缺口」是假的**（见 §二）。
  ⚠ 2026-09-28 晚又**有收紧**（排除指示词/动作短语类假阳性）⇒ 现为 **64%**，
  降的全是假阳性、真约束一条没丢（见 §四.7）。
  - ⚠ **`rasmodia.json` 一度被我误判为句数冲突、改了数据，被测试抓住后已回滚**
    （第 6 次同类误判，见 §三 —— 这次可查到证据：有测试钉住那个值）。
  - ✅ **新增 persona 静态扫描器**，把台账视野扩到**未启用配置**
    （`.tmp/length-probe/probe_persona_static_conflicts.py`）。
  - ⛔ **云端额度已满，10-01 才恢复** ⇒ 云端实验暂停（见 §七）。
- **后续新增（09-28 深夜 / 09-29 凌晨）**：
  - ⭐⭐ **核心是 §二 的「话语权」—— 字数话语权只有 1/6**。
    已用**第二条独立路径复现**（卡层并集去重 + 权威正则，同样是 **1 : 6.0**）；
    而按**文本量**算是 **1 : 11.3**（字数不仅卡少、篇幅也小得多）。
  - ⭐⭐ **一条长度约束要过「五道闸」**（这是对本问题最完整的描述）：
    ```
    ① 数据层  201 条 responseRules 里含长度词的只有 16 条（8%）
          ↓
    ② 到达率  写进数据 ≠ 进 prompt —— 只有 50%
          ↓
    ③ 卡层    字数 1 张 / 句数 6 张
          ↓
    ④ 文本量  399 / 4523 字符
          ↓
    ⑤ 输出侧  超 40 字上限 44%
    ```
    ⇒ **「44% 超标」不是模型不听话，是这条约束一路衰减到了尽头。**
    ⚠ 五道闸**量纲不同，不要相乘**。一条命令复现：
    `python scripts/probe_length_constraint_decay.py`
  - ⭐ **台账盲区已从「四类」扩到「六类」**（`docs/constraint-scope.md` 末节）：
    ①抽取漏抓 ②跨量算术 ③**评测集阶段没覆盖**（stranger/parent 各 0 个样本，
    ⚠ **「初识」= `stranger` 不是 `acquaintance`**）④验证工具自身失效
    ⑤**阶段对了话题不对**（acquaintance 有 12 个 case 但无一是邀约场景）
    ✅ **③ 与 ⑤ 已于 2026-09-30 修复**（`6768a28`）：stranger / parent 各 5 → **8**，
    acquaintance 补了邀约 2 个与边界 1 个；`DEFAULT_CASES` 57 → **66**，七阶段全覆盖。
    ⚠ 修复时发现③还有一层没记：**「边界 / 拒绝」在 stranger 与 acquaintance 也是 0**，
    而 stranger 的核心约束正是「不接邀约、不反问」—— 现已补上。
    ⑥**写进数据到不了 prompt**（到达率 50%，台账**结构上看不见**）。
  - ⚠ **我自己的系统性错误（两处，均已修正重跑）**：
    ① 4 个探针参数名写错 ⇒ **7 个阶段静默塌缩成同一个 prompt**；
    ② 探针用**汉化名**找**英文名** ⇒ 报出假「0 进」。
    ⇒ 共同形状：**静默失败**，都不报错。
  - ⚠ **`responseRules[0]` 实验的落点已核实**（`docs/responseRules0-experiment-site-*.md`）：
    是 **`data/personas/vanilla.json`**，**不是** `rasmodia.json`；
    其值为原值 `"先回答眼前的问题"`（**基线已三方比对确认干净**）。
- **当前状态**：改动**已全部落盘**，全量 **4314 passed**，**没有半完成的改动**。
- **下一步**：① **当前无待拍板项**（2026-09-29 核对：`docs/待决策.md` 四项**均已定/已关闭** ——
  长度措辞 09-28 已选「乙·去字数」并落地、`responseRules[0]` 已定「等重做」、
  第一跑已执行完、群聊路径已关闭）。早先「四项决策待你拍板」的写法**已过时，勿再引用**；
  ② 等额度做 `responseRules[0]` 实验 —— **设计已改成抗漂移的交织式**（见 §六）。

---

## 二、已成立（可直接依赖，不必重验）

| 结论 | 证据强度 | 出处 |
|---|---|---|
| 长度收束**生效**：平均 70.5/49.5 字 → **38.8**，最长 135 → **61** | **云端实测** | 归档 §15 |
| 「重复」分两类：**同义重复**是有意的分层防御（有测试钉住）；**取值不同**才是真矛盾 | 3 处测试 + 1 张契约表 | 归档 §14 |
| `responseRules[1..3]` **进不了 prompt** ⇒ 只需改 `[0]` | 覆盖面已量化：进卡角色数 = **0** | 归档 §4 |
| 「英文残留 16.7%」是**评测口径**，不是出口缺陷 | `models.py:746-749` 分层是**故意**的 | 归档 §10.7 |
| ~~群聊**不经过** `stage_execution_card` ⇒ 单聊改动不影响群聊~~ **❌ 2026-09-28 晚更正**：**群聊确实包含该卡**。实测群聊 = **14 卡**（单聊 13 卡 **+ `voice_variation`**），且群聊的 `stage_execution_card.responseShape` 实测为「通常 2 句：先回答，再给一个具体细节或态度，不写总结」⇒ **单聊的长度改动同时影响群聊** | 直接 dump 群聊卡名列表，两处（单聊/群聊）对比 | active-work 续五 |
| 文学腔**按角色校准**：Elliott/Wizard 本来就被允许 | `styleCalibration` 带文学卡 | 归档 §10.6 |
| 阶段触发：`relationship` **覆盖** hearts；不设时 0=stranger、2/4=acquaintance、6/7=friend、**8+=close** | `probe_stage_matrix.py` 实测 | 归档 §10.1 |
| **`vanilla.json` 才是实际生效的 Wizard 定义**（不是 profile 声明的 `Romanceable Rasmodius`） | dump 出的 `voiceActions` 与 vanilla 逐字匹配 | active-work |
| **抽取器覆盖率 64%**（放宽后曾 69%，修正前 27%）⇒ 台账只能在**该覆盖范围内**声称完整 | `probe_extraction_blindspot.py` | constraint-scope §六 |
| **台账反常方向也验证过**：不只是「prompt 里的量都在台账」，也查了「台账里的条目是否真的存在」 | 2 条「找不到」经查是 `text` 存注释/格式差异，非遗漏 | `probe_ledger_reverse.py` |
| **判定引擎四条规则各自有正反案例**（不是只有总量冒烟） | 防止把 `!=` 写反后总量断言仍通过 | `constraint_scope._RULE_CASES` |
| **台账现在覆盖全部 7 个关系档**（stranger/acquaintance/friend/close/dating/married/parent） | 原先只有 4 档，补齐后立刻暴露一处缺口 | `check_prompt_consistency.STAGES` |
| **prompt 有 3 条真实路径，不是 1 条**：单聊普通（13 卡）/ 单聊 topic（15 卡）/ **群聊完整卡组（14 卡）** | 三者卡组**互不相同**；此前所有探针只用单聊 | `check_prompt_consistency.PATHS` |
| **单次云端评测检测不出小改动**：未改角色（对照组）的波动**大于**被测改动 | 33 轮共同轮次对照 | active-work |
| **出口清洗几乎不动文本**：33 轮里 `scrubChanged` 仅 **1** 轮 | 处方 C 后的产物 | active-work |
| **prompt 里没有第 9 个量**：全数量表述清点后，未覆盖项全是误报/非约束/已换说法 | `probe_quantity_inventory.py` | active-work |
| **stranger 阶段只有 Harvey/Sebastian 的 `responseShape` 没数字** | 是 per-character **风格化表达**（「短答」「半句」），且有全局兜底 ⇒ 不改 | `probe_stage_length_coverage.py` |
| ⭐⭐ **「43.8% 超 40 字」≠ 模型不照做 —— 但根本原因比「两个约束不自洽」更深**。分开算：字数违规 **43.8%**，**句数违规只有 18.5%**；**81.3% 的回复是 1–2 句**；**超字数那 2869 轮里 67.4% 句数合格**。**真正的机理**：整份 prompt 里 **「句数」出现在 6 张卡、「字数」只出现在 1 张卡**（`safety_rules`）⇒ 按已被证实的**「取最宽」**规律，**字数的话语权只有句数的 1/6，模型自然以句数为准** | 6550 轮分开统计 + `probe_length_directives.py` 清点 21 个组合 | active-work 续十七·续二十一 |
| ⭐ **辅证**：逐句统计 9777 句，**每句中位 18 字** —— 模型把「1–2 句、15–40 字」读成「**2 句、约 40 字**」，2×20=40 **恰好卡边界**，任何波动就超 ⇒ 43.8% 是**边界的必然**。而「≤2 句 + 每句≤20 字 + 总≤40 字」**现成就有 2003 轮做到**（可达性证据） | 同上 | active-work 续十九 |
| ⭐ **修法三条**（**改措辞**，不是重试/截断 —— 模型没做错）：**甲** 在其余 5 处句数旁**都补上字数**（同向，改 4~6 处）；**乙** 把唯一的 `15–40 字` **删掉**、只留句数（**最诚实**，且已验证**风险低**——见下条；因为 40 字在「2 句」前提下本身就偏紧）；**丙** 只改 `safety_rules` 一处 ❌ **等于没改** | `probe_length_directives.py` + `test_prompts.py:9249` 的实测结论 | active-work 续二十一 |
| ⭐ **「话语权」可用于排序，但⚠ 已被自己数据证伪一半**。扫全部量化约束：**字数只在 1 张卡（违规 43.8%）/ 句数在 6 张卡（守句数 81.3%）** ⇒ 两端吻合，但 **`追问数` 同样只在 1 张卡、违规率却仅 ~1%（被严守）** ⇒ **「卡数低 ⇒ 被无视」是错的**。⭐ **正确判据**：`f(模型自然倾向 vs 约束, 话语权)` —— **同向则自动遵守（与话语权无关）；冲突时话语权低才被无视**（字数是这种：模型倾向写满） | `probe_length_directives.py --all` + 按 intent 分组算违规率 | active-work 续二十三·续二十五 |
| ⭐⭐ **再往上一层：还有「写进数据但到不了 prompt」的损耗（09-28 深夜，续四十一）** —— **角色数据里的 `responseRules` 到达率只有 50%**：每个角色**写了 4 条、只有 2 条进 prompt**（**全卡扫描确认**，所以不是 `voiceActions` 单一通道的问题）。根因：`voice_actions[:3]` 截断，而 `signatureMoves` 为空时 `sentencePattern` 先占掉 2 槽。⇒ ⚠ **「写了规则」和「prompt 见到这条规则」是两件事**；**两层损耗叠加 ⇒ 长度约束的有效话语权比「1/6」还要低** | `scripts/probe_response_rules_reach.py` |
| ⭐⭐ **五道闸固化成工具，并独立复现了「1/6」（09-28 深夜，续四十三）**。`python scripts/probe_length_constraint_decay.py` 一次跑出：**① 数据层** 201 条 `responseRules` 里含长度词的只有 **16 条（8%）**；**② 到达率 50%**；**③ 卡层 字数 1 张 / 句数 6 张 = 1 : 6.0**（⚠ **与主结论「1/6」独立吻合，第二条验证路径**）；**④ 文本量 399 / 4523 字符 = 1 : 11.3**（⇒ 字数不仅卡少，**篇幅也小得多**）；**⑤ 输出侧 6550 轮超 40 字 44%**。⚠ **五道闸量纲不同，不要相乘** | `probe_length_constraint_decay.py` |
| ⭐ **按 intent 分组**：**topic 917 轮**超 40 字 **49.6%**、2+ 问号 **1.2%**；**chat 4010 轮**超 40 字 **52.5%**、2+ 问号 0.8%；`None` 1623 轮是**老 artifact 无 `intent` 字段**，中位 30 字、18.9% | 6550 轮 | active-work 续二十五 |
| ⚠ **元教训（本轮两次自我证伪）**：**结构性/代理指标只能排序，不能下结论** —— 必须**拆开算真实违规率**。长度那次是「把复合约束当单一约束」，话语权这次是「用卡数代替违规率」，**同一个形状** | 两次都是自己搭的验证拦住自己 | active-work 续十七·续二十五 |
| ⚠ **测约束前的三问（任何一问答不上就停手）**：① **作用范围**是什么（哪些阶段/路径/角色）？② 文本上**可操作的判据**是什么？③ 检测手段会不会**系统性偏移**？⇒ **`邀约` 已因此判定「现有 artifact 测不了」**（它只管初识阶段，而 artifact 以高阶段为主 —— **测的不是约束对象**）；`话题数`/`动作数`/`口语颗粒频率` 因**判据不可操作**同样暂不验 | 第三次同形状错误后总结 | active-work 续二十六 |
| ⭐ **约束的「作用范围」限定扫描**：**67.6% 的量化约束带限定词**（阶段/渠道/条件），其余看起来全局。⭐ **关键澄清**：「初识阶段不得邀约」**确实写了阶段限定** ⇒ **续二十六的失败不是约束的错，是我的验证方法不合格**（该改方法，不是改 prompt） | `scripts/probe_scope_qualifier.py`，只摊开不判定 | active-work 续二十七·续三十 |
| ⚠⚠ **评测集的结构性盲区（两份覆盖，别混，也别查错源头）**：**跑过的** artifact 里 **stranger 0 / parent 0 / acquaintance 仅 4**；**可跑的**（云端全部 suite 并集，**255 个 case**）里 **stranger / parent 也是 0**，而 acquaintance 有 **12** 个。⇒ **stranger / parent 两边都空 ⇒ 要加 case**；acquaintance 有 12 个 —— 但 ⚠ **跑全也未必够**（12 个里无一是邀约场景，见第 ⑤ 类盲区）。⚠ 第二列**不是** `data/personas/behavior-quality-scenarios.json`（那是**本地生成器**的输入），而是源码 `character_quality_eval.py` 的 `_BASE_CASES`。✅ **好消息：7 个阶段都已被支持，只需加数据**（但 `parent` 必须显式给 `childrenCount`） | `scripts/probe_untestable_scope.py`（**同时打印两列**）；方案见 `docs/draft-scenarios-stranger-parent-2026-09-28.md` | active-work 续三十二·续三十三 | ✅ **2026-09-30 已修复**（`6768a28`）：stranger / parent 各 5→**8**，acquaintance 补邀约 2 + 边界 1；`DEFAULT_CASES` 57→**66**。⚠ 本次新发现：**「边界 / 拒绝」在 stranger 与 acquaintance 也是 0**，而 stranger 的核心约束正是「不接邀约、不反问」—— 已补上。
| ⚠⚠ **探针自查：`ContextBuilder.build` 的参数名是 `friendshipHearts`，不是 `relationship`**。`build` 接受 `**values` ⇒ **拼错的参数名被静默忽略、永不报错**。今晚 4 个探针曾因此让 **7 个阶段塌缩成一个**；已修正并重跑，**核心结论（字数 1 张卡 / 句数 6 张卡）不变**，但若干细节数字已更新 | 输出内容自相矛盾（married 的卡里写着 `stage: stranger`）抓住的 | active-work 续三十 |
| ⭐ **验证长回复质量是否更差**：按字数分组看**质量扣分** `tags` —— **略超的（41–60 字）反而最差（0.81），极度超长的（>80）只有 0.66**；而 `warnings`/`retryCount` 单调递增 ⇒ **「超长本身不是质量差的标志」** ⇒ 删掉字数约束**风险低**（但好处未被证实，需 A/B） | 6550 轮分组，观察性非随机 | active-work 续二十二 |
| ⭐ **跨量盲区扫描（新工具）**：台账按**量**分桶，看不见**两个不同量之间是否自洽**。扫 21 个 prompt 组合后共 **8 对跨量共现** —— **只有 1 对是真的**（句数 + 字数），其余 7 对是提取器假阳性（**同一条被多种量重复命中** / **禁止项**被当成要求 / **描述性词语**被当成上限） | `scripts/probe_cross_quantity.py`，只摊开不判定 | active-work 续十八 |
| **重试不检查长度**：`retry_for_format_noise`（`guard.py:1208`）只查五类问题 —— 格式噪声 / 缺亲近信号 / 回显 prompt / 开头无锚 / 机械复述 ⇒ **超长回复直接放行**（36 条超长的 `retryCount` = 0） | 读源码 + artifact 的 `retryCount` 分布 | active-work 续九 |
| 超长**高度集中在浪漫 / 亲密类 case + Sophia**（94 条里她占 **58**）；且**不是**「玩家说得多所以回得多」（65% 的玩家输入是 10–30 字） | 同上 | active-work 续九 |
| **Sophia 特别话长 = 她的 persona 有更宽的长度约束** | ❌ **prompt 侧逐字相同**。同 hearts 下 dump 她与 Wizard 全部 13 卡，长度类表述**完全一致**（`1–2 句、15–40 字` / `最多两句` / `可用 1–2 句`）⇒ 是**模型行为**，不是指令差异 |
| **修长度有三条路，代价不同**：A 加进重试 = **每轮请求 +29%**（输入 token +18.2 M，因 prompt 单次 ~6354 token）；B 后处理截断 = **零请求但改文本**；C 维持现状 | 用 artifact 的 `requestCount`（均值 1.53）与 `usage` 实算 | active-work 续十 |
| ⭐ **方案 B（按句截断）实测不可靠**：切点 100% 干净（44/44 不以半句结尾），但**长度不可控** —— 同样「留 2 句」产出 **31 / 38 / 62 / 76 字**（中文长句可达 60+ 字）；且**会丢掉收货句**（161 字那条的真收尾在第 **7** 句）。⇒ B 不是零成本，要走得先设计**按字数累积截断** | 取 44 条 >80 字真实回复逐条切分对照 | active-work 续十二 |
| ⭐⭐ **事件门控的真闸门是 `style_samples` 漏了它**（2026-09-29，与上表各条正交）：`speech_evidence` 一直有 `_event_dialogue_is_completed`，**`style_samples` 没有** ⇒ 未完成事件的对白经 `styleSamples` 进 `style_evidence` 卡，初识阶段的 alex/shane/sebastian/sophia 甚至 wizard 都在漏。索引里 `styleSamples` 与 `speechEvidence` 是**同一批 11737 条**（分布逐项相同）⇒ 门控必须同源。修后 13 个空元组案例的 event_dialogue **3~6 条 → 0 条**、12 个案例 prompt 正文变化，`style_evidence` 卡**未消失**（日常对白补位）。⚠ **上一会话把根因判成 `run_character_quality_eval.py:243/:278` 是错的**：那个键的有无对 prompt 正文**零影响**（13/13 逐字相同），因为消费端读的是**值**不是「有没有键」 | `.scratch/probe-style-event-gate.py`（patch 出对照组）+ `probe-explicit-empty-event-state.py`，**均零请求** | active-work 09-29 续 |
| ⭐ **管道③ `voiceAnchors` 已修**（2026-09-29 续二，**不必重建索引**）：根因是锚点在构建期被裁掉了 `eventId`（`speech._voice_anchor_candidates` 只放 5 个字段）⇒ **不是漏门控，是信息不可用**。落地：构建期补字段 + `scripts/backfill_voice_anchor_event_ids.py` **离线回填**（237/237 命中，写新文件不覆盖）；`voice_card` 加 `completed_event_ids`，**无 id 就放行**（否则 34 个只有事件语料的角色被整批误杀）。探针：旧索引 60→60（向后兼容）、回填索引 60→**0**（门控生效）；新旧索引除锚点 `eventId` 外**逐字节一致**。另补一漏：`()` 与 `None` 在**全部检索入口**分开（上游不发 `completedEventIds` 时不再误开闸门）。⚠ 索引**已切换**（旧文件备份为 `…next-event-dialogue.pre-anchor-eventids.json`，两个启动脚本无需改） | `.scratch/probe-voice-card-gate.py` + `scripts/backfill_voice_anchor_event_ids.py`（零请求） | active-work 09-29 续三 |

---

## 三、否决清单（**别再查一遍**）

| 被排除的假设 | 排除依据 |
|---|---|
| 「复述玩家」被写了 11 处，是重复失控 | 真约束**只有 4 处**，其余 7 处说「不要复述**规则**」 |
| 逐字重复可以删，风险≈0 | **有测试钉住**（要求 `safety` 与 `guard` 两张卡**都**含那句）；删了全量立刻红 |
| `stage_execution_card` 有同卡内部矛盾 | 「表达预算」管**数量**，`initiative` 管**动机** —— 作用域不同 |
| 这是「结构性模式」，别处还有同类问题 | 扫七类量 × 四阶段，**除长度外没有第二处取值矛盾** |
| 文学腔来自素材传染 | 「疲惫是最好的枕头」在全部 `.tmp` 只出现一处 ⇒ 模型自发 |
| `npc_bubble_catalog['Elliott']['tone']` 影响 prompt | 只在 UI 页面模块使用，**不进 prompt** |
| 补跑云端评测能把 pass 率补成可比 | 基线目录**只留逐条 `result.json`、无汇总** ⇒ 口径不同 |
| **改 Wizard `responseRules[0]` 能改善「答题感」** | **实验为负结果**：未改的对照组波动**更大**（缺答 5→1、字数 −13），观察到的差异无法与噪音区分。**已回滚** |
| **「不得反问」与招牌动作「再反问一句」是冲突** | 反问是**阶段分级**的：stranger 禁 → acquaintance「只在玩家留下空间时问一个」→ friend 允许 → close「必要时提下一步」。且**没有 stranger 评测用例**，实测 51.2% 来自**允许反问的阶段** |
| **`responseRules[0]` 实验是「负结果」= 改动没用** | ❌ **是跑间漂移比效应大**。三个**未改**角色同期下降 **10~14 字**，唯一改了的只升 5.7 字 ⇒ 两批跑之间的系统性漂移**幅度远超被测量的效应** |
| **小改动也能靠跑一次 A/B 判断** | ❌ 条件内 σ ≈ **24 字** ⇒ 一次 12-case 跑（36 轮）只能测出 **≥ 17 字**的差异。5 字差异需 **约 430 轮/臂** |
| **配对设计能数量级提升效率** | ❌ 实测只降到 **2.6 倍**（配对差 σ = 21.4）—— σ 的大头是**同角色同 case 的重复跑波动**，不是「角色间差异」 |
| ~~**prompt 里写了长度上限 ⇒ 输出会守它**~~ **❌ 此判据已被推翻（同日续十七·续二十一）**：模型**确实在守「1–2 句」**（81.3% 是 1–2 句、句数违规仅 18.5%）。⚠ **根因更深**：**「字数」在全份 prompt 里只出现 1 次、「句数」出现 6 次** ⇒ 按「取最宽」规律，**字数的话语权只有 1/6，模型自然以句数为准** | 句数与字数分开统计（67.4% 超字数的轮句数合格）+ 21 组合清点 |
| **`--against-scope` 报 0 缺口 = 台账完整** | ❌ **是抽取器漏了**。放宽后 27% → 69%，立刻冒出新缺口 |
| **`affection_initiative` 同卡「1 句」vs「一两句」是冲突** | ❌ **正则假阳性**：「1 句」来自「同**一句**」「紧接的**一句**」（**指示词**）和「复述**一句**→回答**一句**」（**动作描述**），没有一处是句数上限。修正则后消失 |
| **`rasmodia.json` 的「1–3 句收束」vs「1–2 句」是冲突** | ❌ **我误判了，已回滚**。两者**不同粒度**：前者管**句式节奏**，后者管**日常寒暄这个场景**（更严）—— 方向一致的分层。且 `test_rasmodia_voice_style_captures_source_rhythm_and_register` **钉住了 `1–3 句`**，改了立刻红 |
| **括号动作（舞台指示）是守卫盲区** | ❌ **不是盲区，是历史数据**。44 条带括号的回复**全部来自 08-30~09-03 的老 artifact**，09-28 的跑里一条都没有；守卫正则（`guard.py:331`）对**句中**括号照样匹配（41/44 正是句中）；且当前 `warnings` 有 **156 次** `response_format_retry: stage_direction` ⇒ **守卫确实在抓** |
| **`retryCount = None` 表示「零次重试」** | ❌ **老 artifact 根本没这个字段**。按 `retryCount` 筛选前必须把 `None` 与 `0` 分开，否则会把「没有记录」读成「零次重试」 |

### ⚠ 元教训（比上面每一条都重要）

**我六次「看到矛盾」，六次都错，同源：只读「句子内容」，不读它的「作用域」。**

| 我说 | 实际 | 错在哪 |
|---|---|---|
| 「复述玩家」11 处 | 真约束 4 处 | 同词异义 |
| 逐字重复可删，风险≈0 | 有测试钉住，是有意设计 | 没跑测试就判性质 |
| 结构性根因、是模式 | 取值失控只有长度一处 | 把 1 个样本当模式 |
| 同卡内部矛盾 | 数量预算 vs 动机约束 | 没读那句的**标签** |
| 「不得反问」是冲突 | 阶段分级 + 无 stranger 用例 | **没读它挂在哪一阶段** |
| `rasmodia.json` 句数冲突 | **不同粒度**（句式节奏 vs 日常吹暄场景）+ 测试钉住 | **又没读粒度，且没先跑测试** |

**⇒ 判「两条约束是否打架」必须先确认三件事：**
① 它管哪个**量** ② 什么**条件**下生效 ③ 上面挂的什么**标签**。

**⇒ 后两次说明这条还不够狠，加一条可执行的检查顺序：**
**改任何「看起来矛盾」的值之前，先 `grep` 它有没有被测试断言。有 ⇒ 先假设它是有意设计。**
（`rasmodia.json` 那次，`assert "1–3 句"` 一秒就能查到；我没查就动了数据，全量立刻红。）

**⇒ 第二条元教训：工具报「没问题」时，先问工具看得见多少。**
抽取器 27% 覆盖时也报「0 缺口」；把覆盖提到 69%，缺口立刻出现 5 组。

---

## 四、陷阱清单（看着像问题，其实不是）

1. **stranger 有 3 种句数**（`1–2 句` / `最多两句` / `最多 1 句`）—— **方向一致且层层更严**。
2. **「整条 15–40 字」vs「每句十来个字、最多二十出头」** —— `2×20 = 40`，**正好吻合**。
3. **`persona_core` 与 `voice_execution_card` 有同一句** —— `voiceActions` 被双投影，**有意的**。
   ⚠ 但记台账时**两张卡都要记**，否则报缺口。
4. **`guard._allowed_english`(147) 与 `reply_scrub._KEEP_LATIN`(11) 名单不同** ——
   **方向相反，刻意不接同源**。
5. **「十来个字」会先被「字数」正则命中** ⇒ `CARD_QUANTITY_OVERRIDES` 的字数侧与句数侧**都要改**。
6. **`rasmodia.json` 有 `Wizard` 与 `Rasmodia` 两个键** —— 同一个人的别名，内容逐字相同，**不是重复错误**。
7. **「同一句」「紧接的一句」「复述一句→回答一句」被正则当成句数上限** ——
   前两个是**指示词**、第三个是**动作描述**。同时 `(?<!同)(?<!的)` 排除不会误伤真约束
   （真约束都写「补第 2 句」「最多两句」这类）。⚠ 代价是覆盖率 69% → 64%，**降的全是假阳性**。
8. **prompt 有三条路径，探针只用过一条** —— 单聊普通 13 卡 / 单聊 topic **15 卡** /
   **群聊完整卡组 14 卡**。`voice_variation` 整张卡、`affection_*` 两张卡此前**从未被扫过**。
   ⚠ **最容易漏整张卡的地方就是这里**：`compact=False` 才是群聊，
   而 `topic` 要**手动注入** `context["interaction"]`（`ContextBuilder` 自己不设这个键）。
7. **取值必须归一化成「数值 + 单位」再比较** —— 同一段里「**用一句**」与「**一句**」是两个不同
   match 但同指取值 `1`。不归一化，静态扫描在 50 个 persona 上报 **20 处假冲突**。
   已加 `check_prompt_consistency.normalize_value()`。
8. **「补一句」不是长度约束，「补第 2 句」才是** —— 前者是**动作**，后者才定上限。
   正则里 `补` 必须后接「第」。
9. **`rasmodia.json` 的 `sentencePattern` 与 `responseRules` 同量多值是合法的** ——
   前者管**句式节奏**、后者管**日常寒暄这个场景**（更严）⇒ 分层防御。
   ⚠ **不要改它**：`test_rasmodia_voice_style_captures_source_rhythm_and_register` 钉住了 `1–3 句`。

---

## 五、改动清单（已落盘，**未提交**）

| 文件 | 改动 |
|---|---|
| `prompts.py:6427` | 长度 `1–3 句、15–80 字` → `1–2 句、15–40 字` |
| `prompts.py:7742` | 主动搭话路径 `1–3 句` → `1–2 句` |
| `stage_policy.py:1720/1727/1734/1741` | 四个 `responseShape` `2–3 句` → `1–2 句` |
| `reply_scrub.py` | 新增 `_LATIN_AT_HEAD` + `_drop_latin_at_head`；`_KEEP_LATIN` 扩到 11 词；两处 `.casefold()` |
| `npc_names.py` | 仅注释（该文件 **`??` 未跟踪**） |
| `bridge/tests/test_reply_scrub.py` | +8 条用例 |
| `bridge/tests/test_prompts.py` | 新增 `test_length_directives_never_widen_across_cards`；唤醒 2 条死断言 |
| `scripts/check_prompt_consistency.py` | **新建**；**本轮**放宽抽取正则 + `_MAX_FRAGMENT` 120→300 + `normalize_value()` + `STAGES` **4→7 档** + `PATHS` **3 条真实路径** + 句数正则排除指示词/动作短语 |
| `scripts/health_check.py` | **新建**：一键体检（台账缺口 / 台账自测 / 抽取覆盖率 / 台账反向验证 / persona 静态扫描 / **输出侧遵守率** / 全量测试），**零请求**。加 `--fast` 跳过全量测试。⚠ 它覆盖**两条正交的线**，别把前几项全绿读成「输出也没问题」 |
| `scripts/probe_length_compliance.py` | **新建**：**输出侧遵守率** —— 扫全部 artifact，报超 40/80 字比例与按角色分解。**报告项，不是通过项** |
| `scripts/analyze_ab_power.py` | **新建**：用实测方差算实验**样本量 / 最小可检测效应**。⚠ 取「最近 N 个」按 **mtime** 排序（artifact 命名不统一） |
| `docs/改动对照表-2026-09-28.md` | **新建**：精确到文件行与前后值的改动对照（含**已回滚**的两项与原因），供审计与回滚判断 |
| `scripts/constraint_scope.py` | **新建**；**本轮加 `particle_frequency` 量、4 条量名覆盖、7 条台账条目** |
| `scripts/run_character_quality_eval.py` | **处方 C**：产物记 `scrubbedReply` + `scrubChanged` |
| `docs/STATE.md`、`docs/constraint-scope.md` | 状态入口 / 台账人读视图 |
| `AGENTS.md` | 三条约定：先读 STATE.md、文档分工、判冲突前先确认作用域 |
| `prompts.py`（安全卡） | 长度 `1–2 句、15–40 字` → `1–2 句`（**乙·去字数**，2026-09-28 用户拍板） |
| `bridge/tests/test_prompts.py` | 对应断言由钉 `15–40 字` 改为钉句数 |
| `bridge/src/stardew_ai_bridge/models.py` | `ProviderResult` 加 `retry_improved`（重试是否被采纳；**未塞进 `warnings`**） |
| `bridge/src/stardew_ai_bridge/guard.py` | 重试比较处设置 `retry_improved`，经 `_best_retry_result` 传递 |
| `scripts/run_character_quality_eval.py` | 产物记 `retryImproved`；`summary.json` 加 `truncated`/`truncatedReason`；**加 `--plan` 跑前闸门**（三问 + 预算预估，零请求，复用真实选例逻辑） |
| `bridge/src/stardew_ai_bridge/character_quality_eval.py` | **补 stranger/parent 两档 10 个 case**（`default` 47→57，两档各 0→5）+ 对应 `_FOLLOW_UP_TURNS` | ⇒ **2026-09-30 再补 9 个**（stranger 邀约 3 / acquaintance 邀约 2 / acquaintance 边界 1 / parent 3，57→66）
| `bridge/tests/test_event_gate_case_data.py` | 修正 `empty_chain` 代理指标（「该角色有门」→「该案例的阶段在门表里」） |
| `bridge/tests/test_run_character_quality_eval.py` | +1 条 `truncated` 用例 |
| `bridge/tests/test_guard_retry_edges.py` | +4 条 `retry_improved` 断言（TDD 先红后绿） |
| `docs/eval-runbook-2026-09-28.md` | **新建**：跑法三档规范（L0/L1/L2）+ 跑前闸门 + 成本护栏 |

> `data/personas/rasmodia.json` **曾改后已回滚**（误判，见 §三），**当前无改动**。

**备份**（都在各自源文件旁边）：
`prompts.py-bak-20260928-lengthfix`、`reply_scrub.py-bak-20260928-headlatin`、
`stage_policy.py-bak-20260928-stage-len`、`test_prompts.py-bak-20260928-lengthfix`、
`data/personas/vanilla.json-bak-20260928-responseRules0`（已还原）、
`data/personas/rasmodia.json-bak-20260928-sentence-count`（已还原，仅作记录）

---

## 六、下一步（按价值排序）

1. ~~**台账的「范围盲区」**~~ ✅ **已做**（2026-09-28 早）：
   - persona 静态扫描器 `scripts/probe_persona_static_conflicts.py` —— 视野扩到**未启用配置**；
   - `STAGES` 从 4 档补到 **7 档**（原缺 acquaintance / dating / parent）⇒ 补齐后
     **立刻暴露一处看不见的缺口**（`stage_execution_card × topic_count`，实为量名误判，
     已归 `action_count`）；
   - 全 prompt 数量清点 `scripts/probe_quantity_inventory.py` ⇒ **确认没有第 9 个量**。
   ⚠ **仍未做**：静态扫描只**摊开取值、不判冲突** —— 真冲突与分层防御在取值这一层
   长得完全一样，区别只在**粒度**与**测试是否钉住**，所以判断仍须人做。
   ✅ **补充（09-28 晚）**：台账的盲区已**汇总成四类**并写进
   `docs/constraint-scope.md` 末节「完整性声明」——抽取端 / 跨量算术 /
   **评测集覆盖** / **验证工具自身**。最后一类是本轮新发现且最根本。
2. ~~**全 prompt 约束清点**~~ ✅ **已做**（同日）：结论见上，无新量。
3. ~~**给用户的可读报告**~~ ✅ **已做**（同日）：`docs/人读版-改动说明-2026-09-28.md`
   （含「今日总账」十项）；另加 `docs/改动对照表-2026-09-28.md`（精确到文件行的前后值，
   含**已回滚**的两项），供审计与回滚。
4. ~~**覆盖三条 prompt 路径**~~ ✅ **已做**（同日续）：
   `PATHS` = 单聊普通 13 卡 / 单聊 topic **15 卡** / **群聊完整卡组 14 卡**。
   接入后立刻暴露 **8 组**未登记条目（`voice_variation` **整张卡**此前从未被扫过）。
   补齐后 **3 条路径 × 7 档缺口 0**。
   ⚠ 复现要点：`topic` 必须**手动注入** `context["interaction"] = {"intent": "topic"}` ——
   `ContextBuilder` 自己**不设**这个键，用参数传进去会被静默忽略。
5. ~~**验证闭环**~~ ✅ **已做**（同日续）：
   - **反向验证** `probe_ledger_reverse.py` —— 「台账里的条目是否真的存在」，
     此前只验证过反方向。2 条「找不到」经查是 `text` 存注释 / 格式差异，**不是遗漏**；
   - **判定引擎规则级案例** `constraint_scope._RULE_CASES`（6 条，正反双向）——
     此前只有总量冒烟，规则写反了也可能通过；
   - **一键体检** `scripts/health_check.py` —— **接手先跑这个**。
6. ~~**第四个数据源**~~ ✅ **已查**（同日续）：`data/scenarios/morning.json`
   163 条预设 / 839 个进 prompt 的片段 ⇒ **不引入新的量约束**
   （164 处「N 句」几乎全在描述**玩家输入**「玩家这一轮只给了一句很短的应声」）。
7. **云端实验** —— ⛔ **等 10-01 额度恢复**。
   ⚠ 在那之前**不要**再用「静态检查」的名义继续挖台账 —— 那条线**已做尽**。
8. ⭐ **【新线，同日晚上】「执行侧」：模型到底照不照做** ——
   与 §一~§五 的全部工作**正交**，此前**完全没测过**。
   - **已完成（零请求）**：遵守率量化（`scripts/probe_length_compliance.py`）、
     五类重试判据的触发画像（22.5% 的轮已在重试）、分级重试成本曲线、
     方案 B 的实测缺陷、括号动作的归因。
   - **待用户拍板**：四条路 —— **A1** 全量重试（阈值 40，**+29% 请求**，重试变常态）/
     **A2 分级重试（阈值 60~70，+2~6%）** / **B** 后处理截断（零请求，但长度不可控且可能丢收尾）/
     **C** 维持现状。
   - **待云端验证**：修完之后遵守率能改善多少（要先固定 case 集合，否则不可比）。
   - **⚠ 别重查**：括号动作**不是**盲区（§三）、Sophia 话长**不是** prompt 差异（§二）。
   **五条**边界写在 §七 之后 / 见 `改动对照表` §五。继续挖只会产出噪音。
   ⚠ 第 5 条是 **2026-09-28 晚新增**的「**评测集阶段覆盖**」：
   `artifacts/` 里 **stranger / parent 两个阶段 0 个 case**，
   而「**初识**」阶段的约束 ⇒ ⚠ **「初识」= `stranger`（不是 acquaintance，实测）**
   ⇒ **完全没样本**（台账里 2 条，`cond: stage=stranger`）。
   ⚠ 第二列是**云端全部 suite 的并集（255 个）**，**不是**那个本地生成器的 JSON
   —— 我查错过一次。**stranger / parent 在 255 个里也是 0** ⇒ 要**加 case**；
   而 acquaintance 有 12 个（只跑了 4 个）⇒ 但 ⚠ **跑全也未必够**：
   那 12 个里**没有一个是邀约场景** ⇒ 见第 ⑤ 类盲区。
   ✅ 7 个阶段**都已被支持**，只需加数据（`parent` 必须给 `childrenCount`）。
   它现在是 `health_check.py` 的**第 7 项**，每次体检都会显示。

---

## 七、环境与纪律

- **现场**：`E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory`（`codex/story-memory`）。
- **全量测试 PYTHONPATH 需三者**：
  `<worktree>;<worktree>/bridge/src;<worktree>/scripts`。基线 **4314 passed**。
- Python：`C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe`；设 `PYTHONIOENCODING=utf-8`。
- **云端评测**必须 `--economical`（= compact Prompt，与游戏同路径）；产物落
  `artifacts/character-quality-eval/<ts>/`。
- ⛔ **云端额度已满**：CommandCode 池 3 周额度用尽，
  `HTTP 429 ... resets at 2026-10-01T10:32:50.601Z` ⇒ **10-01 前云端评测不可用**。
  复现方式：用 `.env.local` 的 `BRIDGE_CLOUD_URL` + key，**必须带浏览器 UA**，直接 POST。
  云请求累计 **429**。
- ⚠ **`--max-requests` 会给评测引入截断**：两次跑覆盖的 case 数可能不同，
  **必须只比「共同轮次」**（见 `.tmp/length-probe/compare_response_rules0.py`）。
- **红线**：不提交 git；不启动游戏/SMAPI；不碰真实存档。
  （⚠ 角色数据修改**已获用户授权**，但推广到其他角色前需实验验证。）
- git 一律用 `git -c safe.directory=*`，**绝不** `git config --global`。
