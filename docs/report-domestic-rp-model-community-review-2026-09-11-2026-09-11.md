# 国内模型 RP 社区评价调查

日期：2026-09-11  
研究范围：MiniMax、Kimi、Qwen、GLM、DeepSeek 的角色扮演（RP）体验、长对话稳定性、社区口碑和接入风险。  
目标项目：`E:\workspace\projects\stardew-ai-npc.worktrees\story-memory`

## 结论

社区证据改变了上一轮“先试 MiniMax”的排序。对我们的 NPC 项目，当前更合理的候选顺序是：

1. DeepSeek 当前旗舰版：优先验证长对话和中文情绪表达；公开 RP 专项盲测中，DeepSeek V4 Pro 的 12 轮人工对话排名第一。
2. GLM 当前旗舰版：适合验证中文规则遵循和角色持续性；旧版 GLM 4.7 在长对话中处于国内模型前列，但 GLM 5.x 存在强制 reasoning、输出耗时和集成兼容问题。
3. Kimi 当前旗舰版：长对话表现不错，但公开测评中的 Kimi K2.5/K2.6 延迟明显偏高；Kimi K3 是更新版本，尚未被这套 RP 专项榜单覆盖。
4. MiniMax 当前文本旗舰版：首轮观感有竞争力，但旧版 MiniMax M2.7 从单轮人工排名第 4 降到 12 轮人工排名第 14，不宜直接当作长期 NPC 主模型。
5. Qwen 当前旗舰版：应该保留一次最新旗舰复测，但旧版 Qwen 3.5 Flash 在该 RP 专项评测中长对话和综合排名都偏后，与本项目此前 Qwen 低质量体验方向一致。

因此建议本项目第一批只测三家：DeepSeek、GLM、Kimi。MiniMax 作为第四个对照，Qwen 最新旗舰作为低成本和规则遵循对照，不再优先测试旧版或低配模型。

## 判断依据

### 1. 最相关的社区证据：RP-Bench

`RP-Bench` 是目前找到的最贴近本项目目标的公开社区评测。它不是普通通用能力榜单，而是把以下问题纳入测试：

- 是否尊重用户行动权，不替用户写动作；
- 是否保持角色卡和人物性格；
- 是否能在 50 轮前后的上下文中保持一致；
- 是否自然使用世界书和背景资料；
- 是否维持时间逻辑；
- 是否出现套话、重复描写、空洞文学腔；
- 是否能在 12 轮完整对话中保持叙事推进。

该项目同时提供单轮盲测和多轮盲测，方法文档明确说明：社区投票是自愿样本，单个模型-案例组合的票数有限，因此更适合判断方向，不适合作为绝对真理。

### 2. 国内模型在社区 RP 测试中的结果

以下数据来自 RP-Bench 仓库 2026-06-04 的公开结果快照。`MT ELO` 是完整 12 轮对话的人工盲测分数；`Composite` 融合多轮人工投票、LLM 评审、27 维单轮 rubric、缺陷检测和行为指标。延迟是该基准环境下的中位生成时间，不能直接等同于我们 Bridge 的实际延迟。

| 模型 | 单轮社区排名 | 12 轮社区排名 | 综合排名 | 观察到的信号 |
|---|---:|---:|---:|---|
| DeepSeek V4 Pro | 未覆盖 | **第 1**，MT ELO 1581.7 | 国内模型中第 1，综合第 6 | 长对话最强；适合优先验证关系承接和情绪连续性 |
| GLM 4.7 | 第 9 | 第 10，MT ELO 1506.6 | **综合第 5** | 综合质量不错，但测评中位延迟约 35.9 秒 |
| Kimi K2.5 | 未覆盖 | 第 9，MT ELO 1510.8 | 综合第 8 | 长对话不错，但测评中位延迟约 42.9 秒 |
| Kimi K2.6 | 未覆盖 | **第 8**，MT ELO 1517.7 | 综合第 14 | 长对话人工分数高，但中位延迟约 63.3 秒，且有截断风险信号 |
| MiniMax M2.7 | **第 4** | 第 14，MT ELO 1481.0 | 综合第 9 | 第一印象较强，长对话保持性明显下降 |
| DeepSeek V3.2 | 第 7 | 第 15，MT ELO 1458.5 | 综合第 7 | 成本和速度方向较好，但 RP 上限低于 V4 Pro |
| Qwen 3.5 Flash | 第 8 | **第 20**，MT ELO 1405.5 | **综合第 20** | 长对话最弱；与项目内部对 Qwen 低质量的观察一致 |
| GLM 5.1 | 未覆盖 | 第 17，MT ELO 1440.6 | 综合第 16 | 不能因为 GLM 4.7 表现好，就自动推断 GLM 5.x RP 更好 |

这里最值得注意的不是绝对名次，而是三组反差：

- MiniMax M2.7 单轮第 4、长对话第 14：说明文风和第一轮吸引力不等于长期 NPC 稳定性；
- Kimi K2.5/K2.6 长对话位于前十，但延迟很高：说明质量可以，但实时游戏体验可能不合格；
- Qwen 3.5 Flash 长对话第 20：与项目之前 `qwen-plus-character` 和本地 `qwen3.5:9b` 的低 RP 体验相互印证，但不能直接否定尚未覆盖的 Qwen 最新旗舰。

### 3. 社区工程反馈暴露出的 GLM 风险

RP-Bench 之外，公开的角色扮演和互动应用代码库里，GLM 5.3 出现了与我们 Bridge 直接相关的接入反馈：

- Marinara Engine 的公开 PR 记录了 GLM 5.3 在部分 OpenAI-compatible 路径上“不能关闭 reasoning”的 400 错误；
- De-Koi 的公开 PR 记录了 GLM 5.3 忽略关闭 reasoning、在较小输出预算内耗尽而没有给出最终 JSON 的问题，后续需要提高输出预算并增加定向重试；
- 这不是 RP 质量的直接证明，但说明 GLM 当前版本测试时必须把 reasoning 开关、流式收尾、输出预算和 JSON/文本边界作为独立兼容性检查。

这也解释了为什么“模型排行榜看起来不错”并不等于“可以直接放进当前 Bridge”：实时 NPC 需要短延迟、完整文本和稳定的非 fallback 返回。

### 4. 当前新版本的社区信号不能直接套用旧版排名

搜索到的近期生态信号显示，社区讨论已经转向 Kimi K3、Qwen3.8、GLM 5.3 等新版本；但本次 RP-Bench 的公开结果快照主要覆盖 Kimi K2.5/K2.6、Qwen 3.5 Flash、GLM 4.7/5.1、MiniMax M2.7 和 DeepSeek V3.2/V4 Pro。

因此：

- 不能把 K2.6 的 63 秒延迟直接当成 Kimi K3 的当前延迟；
- 不能把 Qwen 3.5 Flash 的第 20 名直接当成 Qwen3.8 最新旗舰的名次；
- 不能把 GLM 4.7 的表现直接外推到 GLM 5.3；
- 不能把 MiniMax M2.7 的单轮优势直接外推到当前文本旗舰。

这些新版本只能作为待实测候选，不能用宣传页、点赞量或模型总榜替代本项目的小批量质量验证。

## 建议

### 第一批测试顺序

建议按以下顺序接入国内官方 API，不使用新的未知中转站：

1. DeepSeek 当前旗舰版；
2. GLM 当前旗舰版；
3. Kimi 当前旗舰版；
4. MiniMax 当前文本旗舰版；
5. Qwen 当前旗舰版。

每家先做一个最小真实请求，要求记录：HTTP 状态、非空完整文本、实际 model/provider、fallback、延迟、usage、错误类型和重试次数。最小请求失败时不进行批量评测。

### 适合本项目的公平比较

每个模型使用独立工件目录，统一使用：

- 相同角色卡和原始对话证据；
- 相同关系阶段和游戏上下文；
- 相同 Prompt 和三轮案例；
- 5 个代表性案例、15 轮对话；
- `--provider cloud` 明确走真实云端；
- 不把健康检查、模型列表、Key 创建成功或本地 fallback 当作模型成功证据。

人工检查继续沿用本项目已有标准：

- NPC 是否保持对玩家忠诚；
- 是否能主动提及玩家与其他人交往并表达不安或吃醋；
- 是否替其他 NPC 发言；
- 是否编造未来日期、预约、排期或改变 NPC 日程的承诺；
- 女性化男性恋爱角色的 canonical `npcId` 和 `she/her/her`；
- 关系修复、线上线下承接和亲吻触发是否越界；
- 角色是否有个人特色，而不是统一的书面腔。

### 当前决策

在真实请求之前，不修改 Bridge 默认 Provider，不覆盖当前本地配置，不改变现有角色资料和 SMAPI 代码。研究结果只调整候选排序：

- **优先质量**：DeepSeek 最新旗舰、GLM 最新旗舰、Kimi 最新旗舰；
- **优先低延迟**：先测 DeepSeek 的非 reasoning/快速版本，再观察质量损失；
- **优先中文情绪表现**：Kimi 和 MiniMax 必须做人工三轮连续对话；
- **优先规则稳定性**：GLM 和 Qwen 需要重点测不替 NPC 发言、无排期承诺和 canonical 身份字段；
- **离线回退**：继续保留本地 Qwen，但不将其当作高质量 RP 主模型。

## 来源

1. [RP-Bench README](https://github.com/LeviTheWeasel/rp-benchmark)：角色扮演质量基准的评测目标、公开榜单和社区盲测说明。
2. [RP-Bench Methodology](https://github.com/LeviTheWeasel/rp-benchmark/blob/main/docs/METHODOLOGY.md)：人工投票、12 轮多轮会话、27 维 rubric、缺陷检测和样本限制。
3. [RP-Bench composite leaderboard JSON](https://raw.githubusercontent.com/LeviTheWeasel/rp-benchmark/main/results/composite_leaderboard.json)：本报告表格使用的原始模型数据。
4. [RP-Bench live arena stats](https://arena.l3vi4th4n.ai/api/stats)：访问时的公开统计摘要：总投票约 5,228、单轮约 2,013、多轮约 3,192、投票者约 547；网站前端结果页与 API 统计存在不同步，故以仓库快照作为可复查排名来源。
5. [Marinara Engine: GLM 5.3 reasoning compatibility PR](https://github.com/Pasta-Devs/Marinara-Engine/pull/5766)：GLM 5.3 在部分 OpenAI-compatible provider 上不能关闭 reasoning 的集成反馈。
6. [De-Koi: retry GLM 5.3 story builder output](https://github.com/The-Koi-Pond/De-Koi/pull/1283)：GLM 5.3 忽略关闭 reasoning、输出预算耗尽和定向重试的公开工程反馈。
7. [近期 Hugging Face 生态趋势汇总](https://github.com/stevenko2002/agents-radar/issues/1159)：只用于确认 Qwen3.8、GLM 5.3 等新版本已经进入社区讨论；该来源是自动汇总，不作为 RP 质量证据。

## 证据与复查记录

- 访问日期：2026-09-11。
- 通过 PowerShell `Invoke-WebRequest` 读取公开 GitHub Raw、GitHub API 和 RP-Bench 统计接口。
- RP-Bench `composite_leaderboard.json` 最近一次相关提交为 2026-06-04，提交信息为新增 644 条多轮投票；因此本报告明确把它当作方向性社区证据，而不是当前最新版本的完整排名。
- 本次只做网络资料研究和报告落盘，没有调用任何模型 API，没有读取或输出项目 Key，没有启动 Bridge、游戏或 SMAPI，没有修改代码。
- 项目内部已有的 Qwen 低质量观察来自历史评测，不代替本次社区数据；两者只作为相互印证，不构成严格同条件 A/B。

## 限制

- RP-Bench 的投票者是自选择社区样本，且部分模型的单轮 Engagement 是代理估计，不应与真实人工投票混为一谈。
- 公开榜单没有覆盖我们当前可能使用的 Kimi K3、Qwen3.8、GLM 5.3、MiniMax 最新文本版本，因此最终决策仍需在同一 Bridge Prompt 和相同案例上实测。
- 公开评测的语言、角色卡、采样参数和上下文长度与 Stardew NPC 场景不完全相同。
- 社区工程 PR 能证明接入风险或具体故障，但不能单独证明某模型的 RP 质量。
- 本次没有验证任何国内 API 的实际账号、余额、地区、配额或延迟；这些必须通过最小真实请求确认。
