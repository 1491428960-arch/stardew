# 恋爱阶段主动亲密表达实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 逐任务实现；用 `update_plan` 跟踪整体状态，并保留本文件中的复选框。

**目标：** 为 dating/married NPC 增加结构化主动亲密行为卡、已审核角色示例、可诊断的评测元数据和 Dialogue Lab 展示，同时保留 Shane 的拒绝/收口与远程边界。

**架构：** `stage_policy` 只声明当前阶段和角色允许的主动动作；`PromptBuilder` 将其压缩成最终生成前的 `affection_initiative` 行为卡，不改写模型文本。质量评测在案例/轮次上声明期待并用独立纯函数检测亲密信号、过度升级和角色化收口，结果层只做脱敏透传，网页显示标签但仍以完整 transcript 为主。

**技术栈：** Python 3、pytest、Pydantic/FastAPI、静态 HTML/JavaScript、JSON 派生 profile index；不切换 Provider，不启动游戏，不写正式存档。

---

## 文件范围与职责

- 修改 `bridge/src/stardew_ai_bridge/stage_policy.py`：增加 dating/married 的 `affectionInitiative` 结构和五个角色覆盖。
- 修改 `bridge/src/stardew_ai_bridge/prompts.py`：压缩并注入 `affection_initiative` 行为卡，更新 light/direct/explicit 的正向约束和边界。
- 修改 `bridge/src/stardew_ai_bridge/character_quality_eval.py`：为轮次增加主动性期待/类型，扩展目录和结果诊断。
- 修改 `bridge/src/stardew_ai_bridge/behavior_quality.py`：校验/诊断主动行为字段，保持纯函数不改写回复。
- 修改 `bridge/src/stardew_ai_bridge/quality_results.py`：安全保留主动性元数据和标签。
- 修改 `bridge/src/stardew_ai_bridge/dialogue_lab_page.py`：列表和详情显示主动性期待、动作类型与诊断标签。
- 修改 `bridge/src/stardew_ai_bridge/profile_index.py`、`scripts/generate_behavior_examples.py`：保留并检索已审核高阶段示例，禁止未审核样本进入 few-shot。
- 修改 `data/personas/behavior-examples.json`、`data/personas/behavior-quality-scenarios.json`：将五个角色的 dating/married 示例标为 `human_approved`，补齐主动日常/收口覆盖。
- 修改 `scripts/run_character_quality_eval.py`：将主动性元数据传入上下文，并记录每轮检测结果。
- 修改 `bridge/tests/test_stage_policy.py`、`test_prompts.py`、`test_character_quality_eval.py`、`test_behavior_quality.py`、`test_quality_results.py`、`test_profile_index.py`、`test_external_dialogue_lab.py`：覆盖红绿循环、过滤、脱敏和展示契约。

### 任务 1：先写主动性失败测试

**完成标准：** 新测试在未实现结构化字段、行为卡和诊断前按预期失败；失败原因必须是缺少目标行为，而不是导入或测试拼写错误。

- [x] **步骤 1：** 在阶段策略测试中断言 dating/married 返回 `affectionInitiative`，友情阶段不启用 proactive；断言五个角色的 `allowedKinds` 有差异，Shane 包含 `guarded_care` 与 `conversation_exit`。
- [x] **步骤 2：** 在 Prompt 测试中断言 `affection_initiative` 位于历史/质量边界之后、玩家输入之前；断言 proactive 不要求玩家先说情话、remote 不得写成已见面、explicit 仍要求玩家主动且同意、明确结束时不得调情。
- [x] **步骤 3：** 在评测测试中增加 `CharacterQualityTurn` 主动性元数据、四个被动日常/笨拙表达案例和 Shane 允许收口案例的断言；在纯函数测试中断言命中信号、缺失主动、generic romance、wrong-stage/remote 边界标签。
- [x] **步骤 4：** 在 profile、结果脱敏和网页测试中分别断言 `human_approved` 示例按角色/阶段/渠道命中，主动性字段被安全保留，HTML/JS 含中文标签而不透传秘密或完整 prompt。
- [x] **步骤 5：** 运行定向测试：

  ```powershell
  python -m pytest bridge/tests/test_stage_policy.py bridge/tests/test_prompts.py bridge/tests/test_character_quality_eval.py bridge/tests/test_behavior_quality.py bridge/tests/test_quality_results.py bridge/tests/test_profile_index.py bridge/tests/test_external_dialogue_lab.py -q
  ```

  **预期：** 新增断言出现可解释的 FAIL，主要报错为 `affectionInitiative`、`affection_initiative` 或主动性字段不存在。

### 任务 2：实现阶段策略与 Prompt 行为卡

**完成标准：** dating/married 只有在关系已成立时提供主动亲密结构；生成卡最多指导一个动作，保留角色差异、同意、渠道和结束边界。

- [x] **步骤 1：** 将阶段策略类型放宽为可嵌套对象；新增结构字段：`initiativeMode`、`allowedIntensities`、`allowedKinds`、`maxActions`、`channelRules`。dating 使用 `proactive`，married 使用更自然的 `proactive`；Shane 覆盖为 `guarded` 并保留实际关心和退出能力。
- [x] **步骤 2：** 为 Wizard、Sophia、Shane、Sebastian、Alex 填写互不相同的主动动作/话题覆盖；stranger/acquaintance/friend/close/parent 不添加恋爱主动结构。
- [x] **步骤 3：** 更新 `_compact_stage_policy` 并增加 `_build_affection_initiative_card`，只保留短字段和一段执行指令；卡明确“先答当前话题，再最多一步”“proactive 不必等待情话”“explicit 不凭空主动露骨”“remote 只允许待确认安排”“玩家拒绝/结束或状态差可收口”。
- [x] **步骤 4：** 在 quality context 中安全传递 `initiativeExpectation`/`initiativeKind`，把 light 文案改为允许关系成立时主动接近一步，保留 direct/explicit 的同意与角色边界。
- [x] **步骤 5：** 运行任务 1 的定向测试并确认全部通过，再检查既有 prompt 顺序测试未回归。

### 任务 3：实现评测元数据与主动性诊断

**完成标准：** 评测记录每轮期待、类型、是否检测到主动信号及标签；诊断只读回复，不修改回复文本。

- [x] **步骤 1：** 在 `CharacterQualityTurn` 增加 `initiative_expectation` 和 `initiative_kind` 默认值，并限定 `none`、`responsive`、`proactive`、`guarded` 与五类动作。
- [x] **步骤 2：** 为 #24 和新增四个主要角色日常/笨拙表达案例设置 `responsive`/`proactive` 元数据；为 Shane 低落轮次设置 `guarded` + `conversation_exit`，确保允许收口不被算作缺少主动。
- [x] **步骤 3：** 添加纯函数 `diagnose_affection_initiative(case, turn, reply)`：从当前轮文本识别回接情感、轻微回撩、具体安排、实际关心和收口信号；根据 stage/intensity/channel/expectation 生成 `initiativeDetected` 与 `initiativeTags`，不按单个“陪/喜欢”词直接判定成人升级。
- [x] **步骤 4：** 在 `quality_case_catalog`、`run_evaluation` 和各轮 `turn_records` 中记录 camelCase 字段；主动性标签仅作为诊断，不改变 `reply`。
- [x] **步骤 5：** 用 Fake Provider 跑新增最小评测，验证 JSONL/summary 的字段和 Shane 收口路径，再运行 `test_character_quality_eval.py` 与 `test_run_character_quality_eval.py`。

### 任务 4：数据管线、脱敏结果与网页展示

**完成标准：** 10 个现有恋爱/婚后示例成为已审核 few-shot，profile index 可按阶段/渠道检索；浏览器可见主动性信息，秘密和未审核文本仍被过滤。

- [x] **步骤 1：** 将五个角色 dating/married 示例的 `sourceType` 改为 `human_approved`，补充审核所需的行为函数/渠道/阶段字段；不把模型生成工件直接写回资料库。
- [x] **步骤 2：** 扩展 `behavior-quality-scenarios.json`，为被动日常主动表达和 Shane 收口提供可审核场景；更新 CLI 默认字段复制，保持 approve id 才能产生 approved 工件。
- [x] **步骤 3：** 扩展 `ProfileIndexStore._BEHAVIOR_FIELDS` 和选择逻辑，验证人审示例可在 dating/married + remote/face_to_face 场景返回，缺失时返回空并继续基础策略。
- [x] **步骤 4：** 在 `quality_results.py` 只保留受限长度的主动性字段/标签；在 Dialogue Lab 列表、详情和 transcript 诊断区显示“主动回撩/具体邀约/克制接住/允许收口”等标签。
- [x] **步骤 5：** 重建派生 profile index 到独立生成文件，检查 JSON、schema、案例数量和五角色高阶段示例，不覆盖历史评测工件。

### 任务 5：完整验证与工作记录

**完成标准：** 代码、数据和网页契约均通过自动验证；外部云端质量评测与游戏实机验证明确分开，不在本任务中宣称已完成。

- [x] **步骤 1：** 运行定向 Bridge 测试、Bridge 全量测试、Python 语法检查、`git diff --check`。
- [x] **步骤 2：** 通过当前 5678 Bridge 的 Fake Provider 做一次独立小批次，确认 `/health`、`/api/quality/cases`、`/api/quality/results` 读取当前 worktree；若不发起云端请求则明确记录未做真实质量批次。
- [x] **步骤 3：** 逐项核对规格：关系阶段结构、角色差异、主动性诊断、remote/face_to_face、Shane 收口、human_approved、网页标签和持久化边界。
- [x] **步骤 4：** 更新 `docs/active-work.md`，写入真实测试输出、派生索引哈希和未完成的游戏/跨重启验证；保留所有既有未提交改动，不执行 reset/checkout/部署/提交。
