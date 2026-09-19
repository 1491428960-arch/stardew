# 复数恋爱与婚姻世界观实现计划

> **面向 AI 代理的工作者：** 使用 subagent-driven-development（独立任务）或 executing-plans（内联执行）逐任务实现。用复选框跟踪整体状态；每个生产行为变更都先保留失败测试，再做最小实现和定向验证。

**目标：** 在不破坏现有角色、记忆和 Gemini/Qwen 路由的前提下，为主角与多个 NPC 恋爱、结婚、协商和产生嫉妒建立“客观关系事实与 NPC 视角分离”的第一阶段运行模型。

**架构：** Python Bridge 提供关系事实、NPC 视角、阶段接受度、单人调解和嫉妒恢复的纯函数及安全 Prompt 投影；SMAPI 以现有 StoryStateEnvelope 为持久化边界，只把当前 NPC 可以看到的关系快照送入 Bridge。婚姻公开事件可以更新社区视角，普通恋爱和单个 NPC 的接受结果只更新对应视角，不实现多人会议、NPC 之间自动恋爱或全局复杂关系图。

**技术栈：** Python 3.10、Pydantic、FastAPI、pytest；C#/.NET 6、System.Text.Json、xUnit、现有 SMAPI StoryStateStore/BridgeClient；质量验证使用 Fake Provider 小批次、独立 Gemini 工件目录、Bridge 全量回归和 SMAPI 单元测试。

---

## 文件清单与职责

开始定义任务前锁定以下文件边界。已有未提交修改全部属于用户工作，不重置、不清理、不覆盖；下面的修改只能在现有差异上追加必要字段和测试。

**新增：**

- bridge/src/stardew_ai_bridge/relationship_world.py：关系事实、视角可见性、公开婚姻事件、接受度、单人调解、嫉妒与恢复的 Python 领域函数；不读 Key，不访问游戏或 Provider。
- bridge/tests/test_relationship_world.py：上述领域函数的红绿测试，包括婚姻公开、恋爱局部知情、视角隔离、调解隔离和嫉妒恢复。
- bridge/src/stardew_ai_bridge/relationship_world_cases.py：五个目标角色的脱敏多轮质量案例，固定使用 CharacterQualityCase/CharacterQualityTurn，不保存未来模型回复。

**修改：**

- bridge/src/stardew_ai_bridge/models.py：增加 RelationshipFact、RelationshipView、MediationState、JealousyState、RelationshipWorldContext 及请求字段 relationshipWorld。
- bridge/src/stardew_ai_bridge/app.py：允许安全的 relationshipWorld 进入上下文预览和对话请求；保留现有字段白名单、Provider 路由和 fallback 行为。
- bridge/src/stardew_ai_bridge/prompts.py：调用关系领域投影，只把当前 NPC 的已知/怀疑/未知状态、自己的接受度、单人调解和近期嫉妒投影到 Prompt；禁止把客观全量关系表送给模型。
- bridge/src/stardew_ai_bridge/stage_policy.py：为五个目标角色加入关系协商和嫉妒的角色化指导，并把关系阶段限制为“影响可谈程度”，不把阶段变成强制接受开关。
- bridge/src/stardew_ai_bridge/guard.py：让显式拒绝、需要空间、自然收口和暂时无法接受继续走安全收口，不因为缺少浪漫表达触发重试。
- bridge/src/stardew_ai_bridge/character_quality_eval.py：注册 relationship-world 套件，构造案例 payload，保存关系诊断的脱敏字段。
- scripts/run_character_quality_eval.py：接入关系视角、调解和嫉妒的自动筛选字段，保持既有五套套件顺序、字段和旧工件兼容。
- bridge/tests/test_models.py：新增 Pydantic 请求字段和未知字段拒绝测试；若该文件在实现开始时仍不存在，则创建它，不改动已有测试文件语义。
- bridge/tests/test_prompts.py、bridge/tests/test_stage_policy.py、bridge/tests/test_guard.py：增加关系视角、阶段协商、角色差异和边界重试回归。
- bridge/tests/test_character_quality_eval.py、bridge/tests/test_run_character_quality_eval.py、bridge/tests/test_external_dialogue_lab.py：增加质量套件契约、结果字段和 API 目录回归。
- smapi/StoryStateModels.cs：扩展现有故事状态模型，增加关系视角、调解和嫉妒记录；在已有关系边上补充开始时间和婚礼公开事件信息。
- smapi/StoryStateValidation.cs、smapi/StoryStateSerializer.cs：验证并安全加载新增记录，保持旧 schema 的兼容行为和未知/损坏记录的 fail-closed 处理。
- smapi/StoryStateStore.cs：增加单个 NPC 的关系快照、婚礼公开、直接披露、调解结果、嫉妒记录和恢复方法；每个方法都只修改其允许的 NPC 视角。
- smapi/ConversationModels.cs、smapi/ConversationService.cs、smapi/BridgeClient.cs：把当前 NPC 的关系快照加入 Bridge 请求，禁止向 Bridge 发送全量关系状态。
- smapi/tests/StoryStateSerializerTests.cs、smapi/tests/StoryStateValidationTests.cs、smapi/tests/StoryStateStoreTests.cs、smapi/tests/BridgeClientTests.cs、smapi/tests/ConversationServiceTests.cs：覆盖 JSON、持久化隔离和请求序列化。
- docs/active-work.md：实现和验证完成后记录代码测试、Bridge 运行态、质量评测和游戏未验证边界。

**隔离工件：**

- artifacts/character-quality-eval/20260905-gemini37-flash-relationship-world-smoke/
- artifacts/character-quality-eval/20260905-gemini37-flash-relationship-world-full/
- artifacts/character-quality-eval/20260905-gemini37-flash-relationship-world-full-v2/

这三个目录只能保存本轮新的脱敏结果；`full` 保留按原计划 300000 Token 预算提前停止的不完整批次，`full-v2` 是为完成 15 例/45 轮而增加预算后的完整批次；不得覆盖已有五套 Gemini 工件、旧 transcript、角色资料库或 .env.*。

## 任务 1：建立 Python 关系领域模型和可见性规则

**文件：**

- 创建：bridge/src/stardew_ai_bridge/relationship_world.py
- 创建：bridge/tests/test_relationship_world.py
- 修改：bridge/src/stardew_ai_bridge/models.py
- 创建或修改：bridge/tests/test_models.py

- [x] **步骤 1：先写关系领域红灯测试**

在 test_relationship_world.py 先固定以下接口和行为：

~~~python
from stardew_ai_bridge.relationship_world import (
    apply_public_relationship_event,
    disclose_relationship,
    project_relationship_context,
    recover_jealousy,
    resolve_mediation,
)


def test_public_wedding_makes_marriage_known_but_private_dating_stays_local() -> None:
    world = {
        "objectiveRelationships": [
            {"npcId": "Sophia", "relationType": "dating"},
            {
                "npcId": "Sebastian",
                "relationType": "married",
                "publicEventId": "wedding:sebastian",
                "publicOn": "Spring 14",
            },
        ],
        "views": [
            {"ownerNpcId": "Alex", "subjectNpcId": "Sophia", "relationType": "dating", "visibility": "unknown", "source": "none"},
            {"ownerNpcId": "Alex", "subjectNpcId": "Sebastian", "relationType": "married", "visibility": "unknown", "source": "none"},
        ],
    }

    updated = apply_public_relationship_event(world, "wedding:sebastian")
    alex = project_relationship_context("Alex", updated)
    by_subject = {item["subjectNpcId"]: item for item in alex["knowledge"]}

    assert by_subject["Sebastian"]["visibility"] == "known"
    assert by_subject["Sophia"]["visibility"] == "unknown"


def test_direct_disclosure_changes_only_the_current_npc_view() -> None:
    world = {
        "objectiveRelationships": [{"npcId": "Sophia", "relationType": "dating"}],
        "views": [
            {"ownerNpcId": "Wizard", "subjectNpcId": "Sophia", "relationType": "dating", "visibility": "suspected", "source": "rumor"},
            {"ownerNpcId": "Alex", "subjectNpcId": "Sophia", "relationType": "dating", "visibility": "unknown", "source": "none"},
        ],
    }

    updated = disclose_relationship(world, viewer_npc_id="Wizard", subject_npc_id="Sophia")

    assert project_relationship_context("Wizard", updated)["knowledge"][0]["visibility"] == "known"
    assert project_relationship_context("Alex", updated)["knowledge"][0]["visibility"] == "unknown"


def test_mediation_result_is_scoped_to_one_npc_and_does_not_remove_future_jealousy() -> None:
    world = {
        "acceptanceByNpc": {"Sophia": "not_ready", "Alex": "conditional"},
        "mediationByNpc": {"Sophia": {"status": "active", "outcome": None}},
        "jealousyByNpc": {
            "Sophia": {
                "active": True,
                "trigger": "time",
                "intensity": "light",
                "need": "固定的独处时间",
            },
        },
    }

    updated = resolve_mediation(world, "Sophia", "accepted")

    assert updated["acceptanceByNpc"]["Sophia"] == "accepted"
    assert updated["acceptanceByNpc"]["Alex"] == "conditional"
    assert updated["jealousyByNpc"]["Sophia"]["active"] is True


def test_jealousy_recovery_requires_a_concrete_response() -> None:
    jealousy = {
        "active": True,
        "trigger": "broken_promise",
        "intensity": "moderate",
        "need": "解释并履约",
    }

    assert recover_jealousy(jealousy, "generic_romantic_line")["active"] is True
    assert recover_jealousy(jealousy, "acknowledge_and_explain")["active"] is False
~~~

测试同时覆盖：没有 publicEventId 的普通恋爱不公开；普通活动只能产生 suspected；客观关系列表不等于 NPC 可见列表；错误推断被澄清后只修正视角，不改写客观事实。

- [x] **步骤 2：运行红灯测试，确认接口尚未存在**

运行：

~~~powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_relationship_world.py bridge/tests/test_models.py -q
~~~

预期：因 relationship_world 模块、关系请求模型和字段尚未实现而失败；失败必须集中在本任务新增的符号或字段，不允许用失败的旧测试代替红灯证据。

- [x] **步骤 3：增加最小 Pydantic 类型和纯函数实现**

在 models.py 定义固定字段：

~~~python
class RelationshipFact(ApiModel):
    npc_id: str = Field(alias="npcId", min_length=1, max_length=100)
    relation_type: Literal["dating", "engaged", "married"] = Field(alias="relationType")
    started_on: str | None = Field(default=None, alias="startedOn", max_length=100)
    public_event_id: str | None = Field(default=None, alias="publicEventId", max_length=160)
    public_on: str | None = Field(default=None, alias="publicOn", max_length=100)


class RelationshipView(ApiModel):
    owner_npc_id: str = Field(alias="ownerNpcId", min_length=1, max_length=100)
    subject_npc_id: str = Field(alias="subjectNpcId", min_length=1, max_length=100)
    relation_type: Literal["dating", "engaged", "married"] = Field(alias="relationType")
    visibility: Literal["known", "suspected", "unknown"]
    source: Literal["none", "observation", "rumor", "direct_question", "player_statement", "wedding"]
    observed_on: str | None = Field(default=None, alias="observedOn", max_length=100)
    evidence: str | None = Field(default=None, max_length=240)


class MediationState(ApiModel):
    status: Literal["none", "offered", "active", "resolved"] = "none"
    outcome: Literal["accepted", "conditional", "not_ready"] | None = None
    next_step: str | None = Field(default=None, alias="nextStep", max_length=240)


class JealousyState(ApiModel):
    active: bool = False
    trigger: Literal["time", "companionship", "broken_promise", "comparison", "affection_imbalance"] | None = None
    intensity: Literal["light", "moderate", "high"] | None = None
    need: str | None = Field(default=None, max_length=240)
    last_resolved_trigger: str | None = Field(default=None, alias="lastResolvedTrigger", max_length=80)


class RelationshipWorldContext(ApiModel):
    objective_relationships: list[RelationshipFact] = Field(default_factory=list, alias="objectiveRelationships", max_length=20)
    views: list[RelationshipView] = Field(default_factory=list, max_length=80)
    acceptance_by_npc: dict[str, Literal["accepted", "conditional", "not_ready"]] = Field(default_factory=dict, alias="acceptanceByNpc", max_length=20)
    mediation_by_npc: dict[str, MediationState] = Field(default_factory=dict, alias="mediationByNpc", max_length=20)
    jealousy_by_npc: dict[str, JealousyState] = Field(default_factory=dict, alias="jealousyByNpc", max_length=20)
~~~

DialogueTestRequest 增加 relationship_world: RelationshipWorldContext | None = Field(default=None, alias="relationshipWorld")。relationship_world.py 只接受 Mapping/模型转出的字典，按以下顺序实现：先复制输入；公开事件只把匹配婚姻事实更新为 known；直接披露只更新指定 ownerNpcId；投影时只保留当前 viewer 的 view、当前 NPC 自己的关系和带公开事件的婚姻事实；不返回其他 NPC 的接受度、调解或嫉妒。

resolve_mediation 只更新 acceptanceByNpc[npc_id]、对应调解状态和对应嫉妒历史；recover_jealousy 只接受 acknowledge_and_explain、keep_promise、offer_time、give_space 这类具体动作，普通浪漫句不清除嫉妒。

- [x] **步骤 4：运行关系领域绿灯和模型边界测试**

运行：

~~~powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_relationship_world.py bridge/tests/test_models.py -q
~~~

预期：关系公开/局部知情/视角隔离/调解隔离/嫉妒恢复全部通过；模型拒绝未知顶层字段、拒绝未知可见性、拒绝空 NPC ID；不读取 .env.*，不发出 Provider 请求。

## 任务 2：把关系状态接入 SMAPI 持久化和当前 NPC 快照

**文件：**

- 修改：smapi/StoryStateModels.cs
- 修改：smapi/StoryStateValidation.cs
- 修改：smapi/StoryStateSerializer.cs
- 修改：smapi/StoryStateStore.cs
- 修改：smapi/tests/StoryStateSerializerTests.cs
- 修改：smapi/tests/StoryStateValidationTests.cs
- 修改：smapi/tests/StoryStateStoreTests.cs

- [x] **步骤 1：先写 C# 红灯测试**

追加以下契约测试：

~~~csharp
[Fact]
public void Serialize_and_load_preserves_relationship_views_mediation_and_jealousy()
{
    var expected = StoryStateEnvelope.Empty with
    {
        Relationships = new[]
        {
            new RelationshipEdgeRecord
            {
                FromNpcId = "player",
                ToNpcId = "Sophia",
                RelationType = "married",
                StartedOn = "Spring 10",
                PublicEventId = "wedding:sophia",
                PublicOn = "Spring 10",
            },
        },
        RelationshipViews = new[]
        {
            new RelationshipViewRecord
            {
                OwnerNpcId = "Alex",
                SubjectNpcId = "Sophia",
                RelationType = "married",
                Visibility = "known",
                Source = "wedding",
            },
        },
        Mediations = new[]
        {
            new RelationshipMediationRecord
            {
                NpcId = "Alex",
                Status = "resolved",
                Outcome = "conditional",
            },
        },
        Jealousies = new[]
        {
            new RelationshipJealousyRecord
            {
                NpcId = "Alex",
                Active = true,
                Trigger = "time",
                Intensity = "light",
                Need = "固定的相处时间",
            },
        },
    };

    var loaded = StoryStateSerializer.Load(StoryStateSerializer.Serialize(expected));

    Assert.Equal("wedding:sophia", Assert.Single(loaded.State.Relationships).PublicEventId);
    Assert.Equal("known", Assert.Single(loaded.State.RelationshipViews).Visibility);
    Assert.Equal("conditional", Assert.Single(loaded.State.Mediations).Outcome);
    Assert.True(Assert.Single(loaded.State.Jealousies).Active);
}

[Fact]
public void RelationshipSnapshotFor_returns_only_the_current_npcs_view()
{
    var store = new StoryStateStore();
    store.Replace(StoryStateEnvelope.Empty with
    {
        Relationships = new[]
        {
            new RelationshipEdgeRecord { FromNpcId = "player", ToNpcId = "Sophia", RelationType = "dating" },
            new RelationshipEdgeRecord { FromNpcId = "player", ToNpcId = "Alex", RelationType = "married", PublicEventId = "wedding:alex" },
        },
        RelationshipViews = new[]
        {
            new RelationshipViewRecord { OwnerNpcId = "Sophia", SubjectNpcId = "Alex", RelationType = "married", Visibility = "known", Source = "wedding" },
            new RelationshipViewRecord { OwnerNpcId = "Sebastian", SubjectNpcId = "Alex", RelationType = "married", Visibility = "unknown", Source = "none" },
        },
    });

    var snapshot = store.RelationshipSnapshotFor("Sophia");

    Assert.Contains(snapshot.Views, view => view.OwnerNpcId == "Sophia");
    Assert.DoesNotContain(snapshot.Views, view => view.OwnerNpcId == "Sebastian");
    Assert.DoesNotContain(snapshot.ObjectiveRelationships, relation => relation.ToNpcId == "Alex" && relation.RelationType == "married");
}
~~~

另加验证：普通恋爱事实没有 PublicEventId 时不会为其他 NPC 自动生成 known 视角；婚礼公开只能更新已登记的婚姻事实；空 owner、空 subject、非法 Visibility、非法调解结果和非法嫉妒强度都被 StoryStateValidation 拒绝或跳过并产生 warning。

- [x] **步骤 2：运行 C# 红灯测试**

运行：

~~~powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~StoryStateSerializerTests|FullyQualifiedName~StoryStateValidationTests|FullyQualifiedName~StoryStateStoreTests" -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
~~~

预期：编译或测试因新增模型、Envelope 字段和 Store 快照方法不存在而失败；不启动 Stardew Valley，不部署 DLL。

- [x] **步骤 3：实现最小持久化记录和隔离快照**

在 StoryStateModels.cs 增加 RelationshipViewRecord、RelationshipMediationRecord、RelationshipJealousyRecord，字段名固定为 ownerNpcId、subjectNpcId、relationType、visibility、source、npcId、status、outcome、active、trigger、intensity、need；在 RelationshipEdgeRecord 增加 startedOn、publicEventId、publicOn。StoryStateEnvelope 增加 relationshipViews、mediations、jealousies，schema 版本仍为 1，因为这些字段对旧 JSON 是可选的。

在 StoryStateStore 实现以下接口：

~~~csharp
public sealed record RelationshipWorldSnapshot(
    string ViewerNpcId,
    IReadOnlyList<RelationshipEdgeRecord> ObjectiveRelationships,
    IReadOnlyList<RelationshipViewRecord> Views,
    RelationshipMediationRecord? Mediation,
    RelationshipJealousyRecord? Jealousy);

public RelationshipWorldSnapshot RelationshipSnapshotFor(string npcId);
public void RecordPublicWedding(string subjectNpcId, string eventId, string gameDate);
public void DiscloseRelationship(string viewerNpcId, string subjectNpcId, string relationType);
public void ResolveMediation(string npcId, string outcome, string? nextStep = null);
public void RecordJealousy(string npcId, string trigger, string intensity, string need);
public void RecoverJealousy(string npcId, string responseAction);
~~~

RelationshipSnapshotFor 只返回：当前 NPC 自己的 player -> npcId 关系边、带有效婚礼公开字段的社区事实、OwnerNpcId 等于当前 NPC 的关系视角、当前 NPC 自己的调解和嫉妒状态。它绝不返回其他 NPC 的私有视角、接受结果或调解过程。RecordPublicWedding 仅对 relationType=married 且 event ID 非空的事实建立/更新公开视角；DiscloseRelationship 只更新指定 viewer；ResolveMediation、RecordJealousy、RecoverJealousy 只按 NPC ID 更新一条记录。

验证函数沿用现有 StoryStateValidation.Validate(MemoryRecord) 的风格，不因为嫉妒或 not_ready 把状态标成错误；只对缺少身份、非法枚举和超长字段 fail closed。

- [x] **步骤 4：运行 C# 绿灯和旧状态兼容测试**

运行同一条定向 dotnet test 命令。

预期：新增测试和已有故事状态测试全部通过；旧的只含 memories、storyEvents、knowledge、relationships 的 schema 1 JSON 仍可读取；不会写入用户存档或正式 Mod 目录。

## 任务 3：把当前 NPC 关系快照接入 Bridge 请求和 Prompt 上下文

**文件：**

- 修改：smapi/ConversationModels.cs
- 修改：smapi/ConversationService.cs
- 修改：smapi/BridgeClient.cs
- 修改：bridge/src/stardew_ai_bridge/models.py
- 修改：bridge/src/stardew_ai_bridge/app.py
- 修改：bridge/src/stardew_ai_bridge/prompts.py
- 修改：smapi/tests/BridgeClientTests.cs
- 修改：smapi/tests/ConversationServiceTests.cs
- 修改：bridge/tests/test_external_dialogue_lab.py
- 修改：bridge/tests/test_prompts.py

- [x] **步骤 1：先写跨语言请求和 Prompt 红灯测试**

Python 侧追加：

~~~python
def test_relationship_world_is_accepted_by_dialogue_request_and_context_preview() -> None:
    request = DialogueTestRequest.model_validate(
        {
            "npcId": "Alex",
            "message": "你听说我和 Sophia 在约会了吗？",
            "relationshipWorld": {
                "objectiveRelationships": [
                    {"npcId": "Sophia", "relationType": "dating"},
                    {"npcId": "Sebastian", "relationType": "married", "publicEventId": "wedding:sebastian", "publicOn": "Spring 14"},
                ],
                "views": [
                    {"ownerNpcId": "Alex", "subjectNpcId": "Sophia", "relationType": "dating", "visibility": "suspected", "source": "rumor"},
                    {"ownerNpcId": "Alex", "subjectNpcId": "Sebastian", "relationType": "married", "visibility": "known", "source": "wedding"},
                ],
            },
        }
    )

    assert request.relationship_world is not None
    assert request.relationship_world.views[0].visibility == "suspected"


def test_prompt_projects_current_view_without_leaking_objective_relationship_table() -> None:
    context = ContextBuilder().build(
        {
            "npcId": "Alex",
            "relationshipWorld": {
                "objectiveRelationships": [
                    {"npcId": "Sophia", "relationType": "dating"},
                    {"npcId": "Sebastian", "relationType": "married", "publicEventId": "wedding:sebastian"},
                ],
                "views": [
                    {"ownerNpcId": "Alex", "subjectNpcId": "Sophia", "relationType": "dating", "visibility": "unknown", "source": "none"},
                    {"ownerNpcId": "Alex", "subjectNpcId": "Sebastian", "relationType": "married", "visibility": "known", "source": "wedding"},
                ],
            },
        }
    )
    prompt = PromptBuilder().build(context, "你知道 Sebastian 的婚礼吗？")
    text = "\n".join(message["content"] for message in prompt)

    assert "Sebastian" in text
    assert "Sophia" in text
    assert "objectiveRelationships" not in text
    assert '"visibility": "unknown"' in text
~~~

C# 侧在 BridgeClientTests 验证 JSON 请求含 relationshipWorld 且只含当前 NPC 快照；在 ConversationServiceTests 验证传输层收到的 ConversationRequest.RelationshipWorld 来自 StoryStateStore.RelationshipSnapshotFor，Fake transport 不会收到全量 state。

- [x] **步骤 2：运行定向红灯测试**

运行：

~~~powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_prompts.py bridge/tests/test_external_dialogue_lab.py bridge/tests/test_models.py -k 'relationship or world or context' -q
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~BridgeClientTests|FullyQualifiedName~ConversationServiceTests" -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
~~~

预期：Python 缺少请求字段/上下文投影，C# 缺少 ConversationRequest 字段或 Bridge JSON 属性而失败。

- [x] **步骤 3：实现请求接线和安全投影**

DialogueTestRequest 使用别名 relationshipWorld，app.py 的 _DIALOGUE_FIELDS 增加 relationshipWorld；_build_context 把经过 Pydantic 校验的结构传给 ContextBuilder。preview_context 只返回 relationshipWorld 的投影，不返回 objectiveRelationships 原始列表。

ContextBuilder.build 调用 project_relationship_context(str(npc_id), raw_relationship_world)，上下文只新增一个 relationshipWorld 键，形状固定为：

~~~python
{
    "policy": {
        "pluralRelationshipsLegal": True,
        "localMonogamyDefault": True,
        "truthfulDisclosureRequired": True,
    },
    "knowledge": [],
    "acceptance": "conditional",
    "mediation": {"status": "active"},
    "jealousy": {"active": True, "trigger": "time", "intensity": "light"},
}
~~~

PromptBuilder 的 safe_context_data 只复制该投影中的有限字符串、枚举、布尔值和不超过 8 条视角项；删除/忽略 objectiveRelationships、apiKey、authorization、cookie、prompt 等键。Prompt 中明确写出：法律允许不等于 NPC 必须接受；未知信息不可当成事实；已婚公开、普通恋爱局部知情；主角被直接问到时如实回答。

SMAPI 在 ConversationModels.cs 的 ConversationRequest 和 BridgeDialogueRequest 增加 RelationshipWorldSnapshot? RelationshipWorld；ConversationService 为每次发送从 StoryStateStore.RelationshipSnapshotFor(state.NpcId) 读取快照；BridgeClient 原有公共 SendAsync 增加可选快照参数，并在接口适配器中透传。快照序列化前再按当前 NPC 过滤一次，避免调用方误传全量状态。

- [x] **步骤 4：运行跨语言绿灯和脱敏扫描**

运行：

~~~powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_prompts.py bridge/tests/test_external_dialogue_lab.py bridge/tests/test_models.py -k 'relationship or world or context' -q
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~BridgeClientTests|FullyQualifiedName~ConversationServiceTests" -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
~~~

预期：请求和 Prompt 定向回归通过；对测试输出和新增 JSON 工件运行：

~~~powershell
rg -n -i 'api[_-]?key|authorization|cookie|bearer|sk-[A-Za-z0-9]' bridge/tests smapi/tests --glob '*.py' --glob '*.cs'
~~~

仅允许命中既有测试中的脱敏字段名断言，不允许出现真实凭据、完整请求头或完整 Prompt。

## 任务 4：加入关系阶段、五角色协商指导和单人调解状态机

**文件：**

- 修改：bridge/src/stardew_ai_bridge/relationship_world.py
- 修改：bridge/src/stardew_ai_bridge/stage_policy.py
- 修改：bridge/tests/test_relationship_world.py
- 修改：bridge/tests/test_stage_policy.py
- 修改：smapi/StoryStateStore.cs
- 修改：smapi/tests/StoryStateStoreTests.cs

- [x] **步骤 1：先写阶段与调解红灯测试**

追加以下测试：

~~~python
def test_stage_changes_discussion_readiness_but_not_acceptance_result() -> None:
    stranger = relationship_discussion_policy("Alex", "acquaintance")
    close = relationship_discussion_policy("Alex", "close")

    assert stranger["canDiscuss"] is True
    assert stranger["readiness"] == "limited"
    assert close["readiness"] == "open_to_negotiation"
    assert "acceptance" not in stranger or stranger["acceptance"] == "unset"


def test_mediation_is_one_to_one_and_can_end_not_ready() -> None:
    world = {"acceptanceByNpc": {"Sophia": "conditional", "Alex": "accepted"}}
    updated = resolve_mediation(world, "Sophia", "not_ready", next_step="先保留独处空间")

    assert updated["acceptanceByNpc"] == {"Sophia": "not_ready", "Alex": "accepted"}
    assert updated["mediationByNpc"]["Sophia"]["outcome"] == "not_ready"


def test_role_policy_keeps_jealousy_role_specific() -> None:
    assert "承诺" in relationship_discussion_policy("Wizard", "dating")["roleGuidance"]
    assert "空间" in relationship_discussion_policy("Shane", "dating")["roleGuidance"]
    assert "音乐" in relationship_discussion_policy("Sebastian", "dating")["roleGuidance"]
    assert "行动" in relationship_discussion_policy("Alex", "dating")["roleGuidance"]
~~~

同时在 C# Store 测试中验证 ResolveMediation("Sophia", "accepted") 不改变 Alex，RecordJealousy 不覆盖接受度，RecoverJealousy 只在具体回应动作下清理当前 NPC。

- [x] **步骤 2：运行红灯测试**

运行：

~~~powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_relationship_world.py bridge/tests/test_stage_policy.py -k 'stage or mediation or role or jealousy' -q
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~StoryStateStoreTests -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
~~~

预期：新阶段策略键、单人调解接口和 Store 状态更新尚未存在而失败。

- [x] **步骤 3：实现阶段策略和状态转移**

relationship_discussion_policy(npc_id, relationship_stage) 固定返回：

~~~python
{
    "canDiscuss": True,
    "readiness": "limited" | "values_only" | "open_to_negotiation" | "shared_life_negotiation",
    "acceptanceStates": ["accepted", "conditional", "not_ready"],
    "roleGuidance": "...",
    "jealousyFocus": ["time", "companionship", "broken_promise", "comparison", "affection_imbalance"],
}
~~~

阶段映射为：stranger/acquaintance -> limited、friend -> values_only、close/dating -> open_to_negotiation、married/parent -> shared_life_negotiation。它不生成默认接受结果。角色指导固定保留：Wizard 的承诺/时间/共同生活安排，Sophia 的不安/陪伴/生活细节，Shane 的嘴硬/低落/要空间，Sebastian 的少话/音乐/独处，Alex 的竞争式打趣/行动邀约。

resolve_mediation 仅更新参与 NPC；调解状态依次为 offered -> active -> resolved，结果只能是 accepted、conditional、not_ready。not_ready 不等价于反派、Provider 错误或关系自动终止。record_jealousy 的触发器只能来自时间、陪伴、失约、比较、亲密失衡；recover_jealousy 需要承认、解释、履约、安排时间或给空间，并保留 lastResolvedTrigger 供下一轮避免重复首次发现。

- [x] **步骤 4：运行阶段、调解和旧行为绿灯**

运行：

~~~powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_relationship_world.py bridge/tests/test_stage_policy.py -k 'stage or mediation or role or jealousy' -q
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~StoryStateStoreTests -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
~~~

预期：新增和既有 stage policy/story state 测试通过；每个调解结果只影响一个 NPC；后续嫉妒仍可出现，不被 accepted 永久屏蔽。

## 任务 5：把关系边界写入 Prompt，并封住错误浪漫重试

**文件：**

- 修改：bridge/src/stardew_ai_bridge/prompts.py
- 修改：bridge/src/stardew_ai_bridge/guard.py
- 修改：bridge/tests/test_prompts.py
- 修改：bridge/tests/test_guard.py

- [x] **步骤 1：先写 Prompt/Guard 红灯测试**

追加以下回归：

~~~python
def test_prompt_distinguishes_policy_acceptance_from_personal_acceptance_and_jealousy() -> None:
    messages = PromptBuilder().build(
        ContextBuilder().build(
            {
                "npcId": "Sophia",
                "relationshipStage": "dating",
                "relationshipWorld": {
                    "views": [
                        {"ownerNpcId": "Sophia", "subjectNpcId": "Alex", "relationType": "dating", "visibility": "suspected", "source": "observation"},
                    ],
                    "acceptanceByNpc": {"Sophia": "conditional"},
                    "mediationByNpc": {"Sophia": {"status": "resolved", "outcome": "conditional", "nextStep": "固定周末独处"}},
                    "jealousyByNpc": {"Sophia": {"active": True, "trigger": "time", "intensity": "light", "need": "不要连续失约"}},
                },
            }
        ),
        "我昨晚陪 Alex 训练，你是不是有点在意？",
    )
    text = "\n".join(message["content"] for message in messages)

    assert "法律允许" in text
    assert "个人可以拒绝或暂缓" in text
    assert "suspected" in text
    assert "不要把嫉妒写成否定政策" in text
    assert "不要自动知道其他 NPC 的私密关系" in text


def test_space_request_and_natural_closing_do_not_request_romantic_retry() -> None:
    assert should_retry_for_relationship_boundary(
        "Shane",
        "我今天没心情，先让我一个人待会儿。",
        "知道了，我先不打扰你。",
    ) is False
    assert should_retry_for_relationship_boundary(
        "Shane",
        "我先睡了，晚安。",
        "晚安，明天再聊。",
    ) is False
~~~

负例还必须包含：Alex 不知情时不能说出 Sophia 的婚姻；普通酒窖共同活动不能直接断言结婚；Sebastian 普通听歌靠近不能自动升级拥抱；Wizard 的协商不能覆盖其他角色的接受度。

- [x] **步骤 2：运行红灯测试**

运行：

~~~powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_prompts.py bridge/tests/test_guard.py -k 'relationship or jealousy or mediation or space or closing' -q
~~~

预期：Prompt 尚未包含关系卡片或测试使用的边界判断函数而失败。

- [x] **步骤 3：实现关系 Prompt 卡和边界判断**

在 prompts.py 增加 _compact_relationship_world 和 _build_relationship_world_card：

- policy 只投影三个布尔/短语：法律允许、地方一夫一妻默认、被直接问到需如实回答；
- knowledge 最多 8 条，每条仅保留 subjectNpcId、relationType、visibility、source 和短证据；
- 只投影当前 NPC 的 acceptance、mediation、jealousy；
- 忽略 objectiveRelationships、其他 NPC 的接受度、其他 NPC 的调解和完整历史；
- 婚礼公开关系可以显示为 known，普通恋爱未被当前 NPC 得知则显示 unknown 或不出现；
- suspected 只允许不确定表达，不得当作客观事实。

卡片正文必须表达以下优先级：

~~~text
先回答玩家当前话题，再使用当前 NPC 自己已知或合理怀疑的关系信息；
法律承认复数关系不等于这个 NPC 必须接受；嫉妒针对时间、陪伴、承诺和比较，
不是对政策本身的道德审判；直接被问到时如实回答；明确拒绝、需要空间或自然收口时只收口，
不因为缺少浪漫表达重试；调解结果只代表当前 NPC；不要替其他伴侣发言。
~~~

guard.py 增加 should_retry_for_relationship_boundary(npc_id, player_input, reply)；它复用现有 Shane 低落、收口和 guarded_exit_allowed 标记，只在回复明确处理当前边界时阻断浪漫/亲密重试，不把 not_ready 或嫉妒本身当成格式错误。保留现有 ResponseGuard 的敏感字段和 Provider 错误行为。

- [x] **步骤 4：运行 Prompt、Guard 和全部既有行为绿灯**

运行：

~~~powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_prompts.py bridge/tests/test_guard.py bridge/tests/test_behavior_quality.py bridge/tests/test_stage_policy.py -q
~~~

预期：关系卡片和边界回归通过；既有 affection/conversation-lead/Shane/Sebastian/渠道/敏感字段测试不回归；输出中不包含 Key、Cookie、完整 Prompt 或其他 NPC 私有状态。

## 任务 6：建立关系世界观多轮质量套件并接入结果层

**文件：**

- 创建：bridge/src/stardew_ai_bridge/relationship_world_cases.py
- 修改：bridge/src/stardew_ai_bridge/character_quality_eval.py
- 修改：scripts/run_character_quality_eval.py
- 修改：bridge/tests/test_character_quality_eval.py
- 修改：bridge/tests/test_run_character_quality_eval.py
- 修改：bridge/tests/test_external_dialogue_lab.py

- [x] **步骤 1：先写质量套件红灯测试**

追加：

~~~python
def test_relationship_world_suite_covers_five_roles_and_view_states() -> None:
    cases = quality_eval.quality_cases_for_suite("relationship-world")

    assert len(cases) == 15
    assert {case.npc_id for case in cases} == {"Wizard", "Sophia", "Shane", "Sebastian", "Alex"}
    assert all(len(case.dialogue_turns()) == 3 for case in cases)
    assert {case.channel for case in cases} == {"remote", "face_to_face"}
    assert {case.relationship_stage for case in cases} >= {"friend", "close", "dating", "married"}
    assert {turn.relationship_focus for case in cases for turn in case.dialogue_turns()} >= {
        "unknown_view", "suspected_view", "direct_disclosure", "jealousy", "mediation", "recovery"
    }


def test_relationship_world_catalog_does_not_expose_objective_relationships() -> None:
    catalog = quality_eval.quality_case_catalog("relationship-world")

    assert len(catalog) == 15
    assert all("objectiveRelationships" not in item for item in catalog)


def test_eval_cli_parses_relationship_world_suite() -> None:
    module = _load_eval_module()

    args = module._parse_args(["--suite", "relationship-world", "--limit", "5"])

    assert args.suite == "relationship-world"
    assert args.limit == 5
~~~

为 CharacterQualityTurn 增加 relationship_focus: str = ""，只作为内部评分标签；quality_case_catalog 不把它和客观关系表返回到网页目录。

- [x] **步骤 2：运行套件红灯测试**

运行：

~~~powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_character_quality_eval.py bridge/tests/test_run_character_quality_eval.py bridge/tests/test_external_dialogue_lab.py -k 'relationship_world or relationship-world' -q
~~~

预期：套件模块、CLI 选择、turn 元数据和目录约束尚未存在而失败。

- [x] **步骤 3：创建 15 例、五角色各三例的脱敏案例**

在 relationship_world_cases.py 固定每个角色三例：

1. view-gap：另一段普通恋爱分别处于 unknown/suspected；第三轮允许主角直接说明，验证不全知和诚实回答。
2. mediation：角色在 dating 或 married 阶段得知新伴侣，三轮依次表达边界、单人协商、accepted/conditional/not_ready 中的一种结果；不代表其他 NPC。
3. jealousy-recovery：婚姻已公开或恋爱已知，因时间、陪伴、失约、比较或亲密失衡产生轻微嫉妒，第三轮以解释、履约、安排时间或给空间恢复。

五个角色固定差异：Wizard 使用承诺和时间以及共同生活安排；Sophia 使用陪伴和具体生活细节；Shane 至少一例低落并需要空间；Sebastian 至少一例音乐/独处且没有自动拥抱；Alex 使用竞争式打趣或行动邀约。至少 5 例 remote、至少 5 例 face_to_face、至少 5 例含历史，婚礼公开至少 3 例，普通恋爱未同步至少 5 例。

每个案例的 relationship_world 只包含本例所需的脱敏事实和当前 NPC 视角；不把完整关系图写入 profile-index 或角色资料库。案例的 expected_terms/forbidden_terms 检查当前话题、未知信息、具体需求和角色差异，不要求每个角色说出“嫉妒”一词。

- [x] **步骤 4：注册套件并接入脱敏结果字段**

在 character_quality_eval.py：

- QUALITY_SUITE_IDS 在现有五个 ID 之后追加 relationship-world；
- quality_cases_for_suite("relationship-world") 惰性导入 relationship_world_cases()；
- CharacterQualityCase 增加 relationship_world，构造每轮请求时写入 relationshipWorld；
- 每轮保存 relationshipVisibility、relationshipAcceptance、mediationStatus、jealousyTrigger、jealousyActive，这些只来自案例输入和安全诊断，不写入完整请求；
- 旧套件不添加空的关系字段，旧 summary 和已有工件的 JSON 结构继续兼容；
- validate_quality_cases 检查关系阶段、可见性和焦点值，禁止 romanceEligible=False 案例要求强亲密表达。

在 run_character_quality_eval.py：

- 不改现有五套的默认顺序和默认参数；
- 先按原有单轮评分，再按 relationship_focus 汇总 unknown_view_misread、suspected_as_fact、public_wedding_visibility、mediation_scope_leak、jealousy_recovery_missing、role_voice_flattened 标签；
- 只在 relationship-world 记录 relationshipWorld 相关结果字段；
- ProviderError、fallback、嫉妒、not_ready 和需要空间都不标为格式错误。

- [x] **步骤 5：运行套件绿灯和 Fake Provider 2 例小批次**

运行：

~~~powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_character_quality_eval.py bridge/tests/test_run_character_quality_eval.py bridge/tests/test_external_dialogue_lab.py -k 'relationship_world or relationship-world or quality_case_catalog' -q
py -3.10 scripts/run_character_quality_eval.py --provider fake --suite relationship-world --limit 2 --economical --output-dir artifacts/character-quality-eval/20260905-relationship-world-fake-smoke
~~~

预期：15 例目录契约通过；Fake 小批次只创建新目录，至少返回两个案例的关系诊断字段，不写正式资料库，不覆盖已有 Gemini 工件。

## 任务 7：定向回归、Bridge/SMAPI 全量验证和分层 Gemini 评测

**文件：**

- 修改：docs/active-work.md
- 创建：artifacts/character-quality-eval/20260905-gemini37-flash-relationship-world-smoke/
- 创建：artifacts/character-quality-eval/20260905-gemini37-flash-relationship-world-full/

- [x] **步骤 1：运行实现后的 Python 定向回归**

运行：

~~~powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_relationship_world.py bridge/tests/test_models.py bridge/tests/test_prompts.py bridge/tests/test_guard.py bridge/tests/test_stage_policy.py bridge/tests/test_character_quality_eval.py bridge/tests/test_run_character_quality_eval.py bridge/tests/test_external_dialogue_lab.py -q
~~~

预期：新增关系领域、请求校验、Prompt/Guard、阶段调解、质量套件和 API 目录全部通过；已有 conversation-lead、affection-pacing、自然中文和 provider 测试不能被跳过。

- [x] **步骤 2：运行 Bridge 全量与静态验证**

运行：

~~~powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests -q
py -3.10 -m compileall -q bridge/src scripts
git diff --check
~~~

记录实际测试数量、耗时、退出码和既有换行提示；不能把单个定向测试通过表述成全量完成。

- [x] **步骤 3：运行 SMAPI 全量单元测试，不启动游戏**

运行：

~~~powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false -p:BundleExtraAssemblies=Game
~~~

预期：C# 故事状态、Bridge 请求、ConversationService 和既有测试全部通过；EnableModDeploy=false、EnableModZip=false 只做测试，不复制 DLL，不启动 Stardew Valley。

- [x] **步骤 4：先用 Gemini 跑 5 例/15 轮隔离冒烟**

使用当前已经配置的 cloud Provider 和现有本机环境读取路径，不在命令行、日志、计划或工件里输出 Key；不重新创建或修改 Key。命令：

~~~powershell
$env:PYTHONPATH='bridge\src'; py -3.10 scripts/run_character_quality_eval.py --provider cloud --suite relationship-world --limit 5 --economical --dynamic-player-input --max-requests 45 --max-total-tokens 100000 --output-dir artifacts/character-quality-eval/20260905-gemini37-flash-relationship-world-smoke
~~~

先检查五个角色各至少一例，人工只看脱敏回复和摘要：未知信息是否保持不知情、怀疑是否使用不确定说法、婚礼是否公开、调解是否只谈当前 NPC、嫉妒是否落到时间/陪伴/承诺、Shane 是否允许空间、Sebastian 是否保持音乐/独处、Alex 是否保持行动感。Provider 429 或超时只记录为链路状态，不作为角色质量负例。

- [x] **步骤 5：冒烟契约稳定后运行 15 例/45 轮完整批次**

使用全新目录和明确预算：

~~~powershell
$env:PYTHONPATH='bridge\src'; py -3.10 scripts/run_character_quality_eval.py --provider cloud --suite relationship-world --dynamic-player-input --max-requests 135 --max-total-tokens 300000 --output-dir artifacts/character-quality-eval/20260905-gemini37-flash-relationship-world-full
~~~

总结必须分开报告：案例/轮次返回率、ProviderError、fallback、请求数、重试、Token、延迟；自动关系标签统计；五角色人工对白观察。不得因为自动通过率或返回成功就宣称 Gemini 可以全面替代 Qwen，也不得把质量评测结果写回角色资料库。

- [x] **步骤 6：扫描新工件、进程和工作树边界**

运行：

~~~powershell
rg -n -i 'api[_-]?key|authorization|cookie|bearer|sk-[A-Za-z0-9]' artifacts/character-quality-eval/20260905-relationship-world-fake-smoke artifacts/character-quality-eval/20260905-gemini37-flash-relationship-world-smoke artifacts/character-quality-eval/20260905-gemini37-flash-relationship-world-full --glob '*.json' --glob '*.jsonl'
git status --short --branch
Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'Stardew|SMAPI' } | Select-Object ProcessId,Name,CommandLine
~~~

预期：工件扫描无真实敏感命中；工作树只增加本计划、实现代码、测试和本轮独立工件；没有游戏或 SMAPI 进程；不清理用户原有 .tmp-pytest、旧工件或未提交修改。

## 任务 8：活动记录、最终一致性检查和交付边界

**文件：**

- 修改：docs/active-work.md

- [x] **步骤 1：更新活动记录**

记录以下四类事实并使用实际输出替换描述：

1. Python 关系领域、Prompt/Guard、质量套件定向测试和 Bridge 全量测试；
2. C# 故事状态、Bridge 请求和 SMAPI 全量单元测试；
3. Fake/Gemini 工件的返回率、自动标签和人工抽查结论；
4. 未启动游戏、未部署 DLL、未修改正式 Mods/存档/角色资料库、未读写或输出 Key 的边界。

不要把“婚礼公开”写成已完成游戏内验证；只能写成领域测试、序列化测试、Bridge 请求测试或真实游戏未验证中的对应证据。

- [x] **步骤 2：执行规格覆盖度检查**

逐条核对规格 2026-09-05-multi-relationship-world-design.md：战争政策与地方传统、客观事实、known/suspected/unknown、间接消息、婚姻公开、恋爱局部知情、阶段接受度、accepted/conditional/not_ready、一对一调解、嫉妒触发与恢复、五角色差异、禁止全局同步、禁止全知、禁止多人会议、质量案例和四类测试均必须能在本计划某任务中指出实现文件和验证命令。

- [x] **步骤 3：执行计划自检和工作树检查**

运行：

~~~powershell
$patterns = @('TO'+'DO', '待'+'定', '后续'+'实现', '添加'+'适当', '类似'+'任务', '上述'+'代码')
Select-String -Path docs/superpowers/plans/2026-09-05-multi-relationship-world-design.md -Pattern $patterns
git diff --check
git status --short --branch
~~~

预期：占位符扫描无命中；git diff --check 仅可能报告工作树既有的换行提示，不产生空白错误；不提交 Git commit。

## 计划自检

- 规格中的每条成功标准都有明确模块：关系规则在 relationship_world.py/StoryStateStore，视角隔离在 project_relationship_context/RelationshipSnapshotFor，对话边界在 prompts.py/guard.py，质量验收在 relationship_world_cases.py/结果层。
- accepted、conditional、not_ready 始终是当前 NPC 的状态，不会覆盖其他 NPC；嫉妒是可恢复但可复发的情绪状态，不是 Provider 错误。
- 婚礼公开通过显式 publicEventId 更新社区视角；普通恋爱不因客观存在自动全局同步；suspected 不会升级为事实。
- 五个角色各有角色指导和独立场景；没有把“嫉妒”做成统一台词模板，也没有把人工判断交给单一自动分数。
- 旧五套质量评测、已有 Gemini 工件、Qwen qwen3.5:9b 回退、正式 Mods、存档、角色资料库和 Key 都在计划边界之外保持不变。
- 计划中的每个生产行为变更都先有可执行红灯测试；每个全量阶段都有实际命令；没有游戏启动步骤和没有秘密输出步骤。
