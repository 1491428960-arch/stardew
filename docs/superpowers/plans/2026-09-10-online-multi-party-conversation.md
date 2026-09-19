# 线上多人对话实验实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans`（内联执行）逐任务实现。用阶段检查点跟踪进度；本项目禁止创建 Git commit，计划中的提交步骤全部省略。

**目标：** 在不改变现有单 NPC 聊天和线下 `face_to_face` 链路的前提下，新增一个仅支持 `remote` 的多人对话实验室，让同一组参与者可以用三种生成策略获得可比较的结果：独立并行回复、单发言人轮流回复、一次请求生成多轮回复。

**架构：** 新增独立的 `GroupConversationService` 作为线上多人会话编排层。请求固定包含参与者、公开历史、当前发言人和策略；服务端始终控制参与者名单与发言边界，模型只生成当前策略要求的对白。三种策略共用 ProviderRouter、PersonaStore、PromptBuilder 和统一响应统计，不改现有 `/api/dialogue/test` 单 NPC 协议。第一阶段只提供 Bridge API 和 `/test/group` 实验页面，暂不接入 SMAPI 线下菜单。

**技术栈：** Python 3.10、FastAPI、Pydantic v2、现有 ProviderRouter/OpenAI-compatible Provider、现有 Dialogue Lab HTML 模板、pytest。

---

## 范围与策略定义

策略名称固定为：

- `fanout`：对每个参与 NPC 独立调用一次 Provider；每个回复都只代表该 NPC，不把其他 NPC 的回复放进同一轮上下文。
- `turn_based`：每轮只调用一次 Provider，由请求中的 `activeSpeakerNpcId` 指定当前 NPC；服务端不允许模型改变发言人。
- `multi_turn`：一次 Provider 调用要求模型返回 2～4 条结构化连续对白；服务端校验每条 `speakerNpcId` 都属于参与者，并拒绝未知发言人、重复越界角色和空内容。

统一限制：

- `channel` 只接受 `remote`；传入 `face_to_face` 返回 422，避免提前污染线下生命周期。
- 参与者数量为 2～3 名 NPC；首版不把玩家算进 NPC 参与者数量。
- 所有历史默认 `public`，首版不实现私聊、旁白、动态入场和离场。
- 服务端控制参与者名单、当前发言人、轮数和最大历史；模型不能添加 NPC、改变关系数值、改变日程或让其他 NPC 代言。
- 三种策略返回统一的 `turns`、`providerCalls`、`providerErrors`、`fallbackCount`、`latencyMs` 和聚合 `usage`，便于官方 Gemini 可用后做同口径 A/B。

### 任务 1：定义多人会话数据契约

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/models.py`
- 测试：`bridge/tests/test_group_conversation.py`

- [ ] **步骤 1：编写失败测试**

在测试文件中增加以下最小契约测试：

```python
def test_group_request_accepts_remote_participants_and_public_history() -> None:
    request = GroupDialogueRequest.model_validate(
        {
            "message": "你们最近都在忙什么？",
            "provider": "fake",
            "strategy": "turn_based",
            "channel": "remote",
            "participants": [
                {"npcId": "Abigail", "displayName": "Abigail"},
                {"npcId": "Emily", "displayName": "Emily"},
            ],
            "activeSpeakerNpcId": "Abigail",
            "history": [
                {
                    "speakerType": "player",
                    "speakerId": "player",
                    "content": "晚上好。",
                    "visibility": "public",
                }
            ],
        }
    )

    assert request.channel == "remote"
    assert [item.npc_id for item in request.participants] == ["Abigail", "Emily"]
    assert request.history[0].speaker_id == "player"


@pytest.mark.parametrize(
    "patch",
    [
        {"channel": "face_to_face"},
        {"participants": [{"npcId": "Abigail"}]},
        {"participants": [{"npcId": "A"}, {"npcId": "B"}, {"npcId": "C"}, {"npcId": "D"}]},
        {"strategy": "unknown"},
    ],
)
def test_group_request_rejects_unsupported_shape(patch: dict[str, object]) -> None:
    payload = {
        "message": "测试",
        "provider": "fake",
        "strategy": "fanout",
        "channel": "remote",
        "participants": [
            {"npcId": "Abigail"},
            {"npcId": "Emily"},
        ],
    }
    payload.update(patch)

    with pytest.raises(ValidationError):
        GroupDialogueRequest.model_validate(payload)
```

- [ ] **步骤 2：运行测试确认红灯**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_group_conversation.py
```

预期：FAIL，原因是 `GroupDialogueRequest`、参与者模型和历史模型尚不存在；不要把导入路径错误当成功能红灯。

- [ ] **步骤 3：实现最小契约**

在 `models.py` 中新增 `GroupParticipant`、`GroupHistoryItem`、`GroupDialogueRequest`、`GroupTurn` 和 `GroupDialogueResponse`。字段使用现有 alias 风格：`npcId`、`displayName`、`speakerType`、`speakerId`、`activeSpeakerNpcId`、`providerCalls`、`providerErrors`、`fallbackCount`、`latencyMs`。

`GroupParticipant` 除了 `npcId` 和 `displayName` 外，还携带该 NPC 自己的 `gameState`；`GroupDialogueRequest` 的 `gameState` 是所有参与者共享的线上场景快照，`recentFacts` 和 `relationshipWorld` 也是公开上下文。这样每个 NPC 仍能保留独立关系阶段，而三种策略使用完全相同的季节、地点、时间和关系世界。

`GroupDialogueRequest` 的核心定义保持如下边界：

```python
strategy: Literal["fanout", "turn_based", "multi_turn"]
channel: Literal["remote"] = "remote"
participants: list[GroupParticipant] = Field(min_length=2, max_length=3)
active_speaker_npc_id: str | None = Field(default=None, alias="activeSpeakerNpcId")
history: list[GroupHistoryItem] = Field(default_factory=list, max_length=40)
turn_count: int = Field(default=2, alias="turnCount", ge=1, le=4)
game_state: NpcGameState | None = Field(default=None, alias="gameState")
recent_facts: list[str] = Field(default_factory=list, alias="recentFacts", max_length=50)
relationship_world: RelationshipWorldContext | None = Field(default=None, alias="relationshipWorld")
```

模型校验还必须保证：NPC ID 不重复、`activeSpeakerNpcId` 若存在必须属于参与者、历史 `visibility` 只能是 `public`、历史 `speakerType` 只能是 `player` 或 `npc`、NPC 历史发言人必须属于参与者。

- [ ] **步骤 4：运行契约测试确认绿灯**

运行同一条 pytest 命令，预期：全部通过。

### 任务 2：构建共享多人 Prompt 与 Provider 调用适配

**文件：**

- 创建：`bridge/src/stardew_ai_bridge/group_conversation.py`
- 修改：`bridge/src/stardew_ai_bridge/models.py`
- 修改：`bridge/src/stardew_ai_bridge/providers.py`
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
- 测试：`bridge/tests/test_group_conversation.py`
- 测试：`bridge/tests/test_prompts.py`

- [ ] **步骤 1：编写失败测试**

增加以下行为测试：

```python
def test_group_prompt_marks_roster_and_forbids_speaking_for_other_npcs() -> None:
    prompt = build_group_prompt(
        active_npc_id="Abigail",
        participants=["Abigail", "Emily"],
        public_history=[],
        player_message="你们谁更喜欢夜市？",
        strategy="turn_based",
    )
    rendered = json.dumps(prompt, ensure_ascii=False)

    assert "Abigail" in rendered
    assert "Emily" in rendered
    assert "只能说 Abigail 自己的话" in rendered
    assert "不能替 Emily 发言" in rendered
    assert "channel=remote" in rendered


def test_group_response_parser_rejects_unknown_speaker() -> None:
    with pytest.raises(GroupResponseError, match="未知发言人"):
        parse_multi_turn_reply(
            '{"turns":[{"speakerNpcId":"Lewis","content":"不在名单里"}]}',
            participant_ids={"Abigail", "Emily"},
        )
```

- [ ] **步骤 2：运行测试确认红灯**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_group_conversation.py bridge/tests/test_prompts.py -k 'group_prompt or multi_turn_reply'
```

预期：FAIL，原因是共享 Prompt 构造器和多轮结构化回复解析器尚不存在。

- [ ] **步骤 3：实现共享 Prompt 与解析器**

`group_conversation.py` 提供以下接口：

```python
def build_group_prompt(
    *,
    active_npc_id: str,
    participants: list[GroupParticipant],
    shared_game_state: NpcGameState | None,
    relationship_world: RelationshipWorldContext | None,
    recent_facts: list[str],
    public_history: list[dict[str, object]],
    player_message: str,
    strategy: str,
) -> list[dict[str, str]]: ...

def parse_multi_turn_reply(
    reply: str,
    *,
    participant_ids: set[str],
    expected_turn_count: int,
) -> list[GroupTurn]: ...
```

共享 Prompt 必须明确：当前是公开线上群聊；当前请求的 NPC 身份；参与者白名单；公开历史；不能替其他 NPC 发言；不能让名单外 NPC 加入；不能写成已经线下见面；不能改变日程、库存、好感度或关系状态。`multi_turn` 额外要求只输出 JSON 对象 `{"turns":[...]}`，解析失败不得把原始 JSON 当作对白展示。

对 Provider 的适配只复用现有 `ProviderRouter.generate(request, messages=...)`，不新建第二套 HTTP 客户端。为让 Fake Provider 能用于本地结构测试，给 `DialogueTestRequest` 增加可选的内部字段 `groupStrategy` 和 `groupParticipantIds`；Fake Provider 对 `multi_turn` 返回固定、合法的演示 JSON，云端 Provider 仍只接收正常的 messages。

- [ ] **步骤 4：运行 Prompt 与解析器测试确认绿灯**

运行同一条 pytest 命令，预期：新增测试与原有 Prompt 测试全部通过。

### 任务 3：实现三种线上策略编排

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/group_conversation.py`
- 测试：`bridge/tests/test_group_conversation.py`

- [ ] **步骤 1：编写失败测试**

使用一个记录调用次数和请求 NPC ID 的真实测试 Provider，覆盖：

```python
def test_fanout_calls_each_participant_once_and_returns_all_public_turns() -> None: ...

def test_turn_based_calls_only_active_speaker_once() -> None: ...

def test_multi_turn_uses_one_call_and_validates_each_returned_speaker() -> None: ...

def test_provider_error_returns_group_error_without_partial_fake_success() -> None: ...
```

断言分别为：`fanout.provider_calls == 2`、`turn_based.provider_calls == 1`、`multi_turn.provider_calls == 1`；`turn_based` 只有当前发言人；Provider 异常时 `providerErrors` 增加、`fallbackCount` 正确，不能把未生成的 NPC 标记成成功回复。

- [ ] **步骤 2：运行测试确认红灯**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_group_conversation.py -k 'fanout or turn_based or multi_turn or provider_error'
```

预期：FAIL，原因是策略服务尚不存在。

- [ ] **步骤 3：实现最小策略服务**

新增：

```python
class GroupConversationService:
    def generate(self, request: GroupDialogueRequest) -> GroupDialogueResponse: ...
```

实现要求：

- `fanout` 按参与者顺序逐个构造单 NPC 请求，但每次只将公开历史和玩家输入传给当前 NPC；每个参与者独立计为一次 Provider call。
- `turn_based` 由 `activeSpeakerNpcId` 或参与者第一项确定唯一发言人；缺失时服务端补齐，不接受模型返回的发言人覆盖。
- `multi_turn` 只调用一次 Provider，解析并校验 `turns`；返回的每个发言人必须属于参与者，最多返回 `turnCount` 条，少于 1 条视为 ProviderError。
- 每个策略统一统计 `providerCalls`、`providerErrors`、`fallbackCount`、总延迟和可用 usage；不记录 Authorization、Key 或完整请求 payload。
- Provider 失败时返回安全的结构化错误结果，不自动切换到本地 Qwen；`provider=cloud` 失败时保持 cloud-only 语义。
- 公开历史只保存成功返回的对白，失败结果不能污染下一次会话。

- [ ] **步骤 4：运行策略测试确认绿灯**

运行策略测试命令，预期：全部通过；再运行 Bridge 全量测试，预期没有既有测试回归。

### 任务 4：增加线上多人 API

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/app.py`
- 测试：`bridge/tests/test_group_conversation.py`
- 测试：`bridge/tests/test_api.py`

- [ ] **步骤 1：编写失败测试**

增加 API 测试：

```python
def test_group_dialogue_endpoint_returns_strategy_metrics(client: TestClient) -> None:
    response = client.post(
        "/api/dialogue/group",
        json={
            "message": "你们最近都在忙什么？",
            "provider": "fake",
            "strategy": "turn_based",
            "channel": "remote",
            "participants": [
                {"npcId": "Abigail", "displayName": "Abigail"},
                {"npcId": "Emily", "displayName": "Emily"},
            ],
            "activeSpeakerNpcId": "Abigail",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["strategy"] == "turn_based"
    assert body["providerCalls"] == 1
    assert body["turns"][0]["speakerNpcId"] == "Abigail"
    assert body["channel"] == "remote"
```

- [ ] **步骤 2：运行测试确认红灯**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_group_conversation.py bridge/tests/test_api.py -k 'group_dialogue'
```

预期：FAIL，原因是 `/api/dialogue/group` 路由尚不存在。

- [ ] **步骤 3：实现 API 路由**

在 `app.py` 初始化 `GroupConversationService`，增加：

```python
@app.post("/api/dialogue/group", response_model=GroupDialogueResponse)
def group_dialogue(payload: dict[str, object]) -> GroupDialogueResponse:
    request = _validate_group_dialogue_request(payload)
    return group_conversation_service.generate(request)
```

路由只保留多人允许字段，拒绝未知 Provider、线下 channel、空消息、重复 NPC ID 和名单外的 `activeSpeakerNpcId`。响应要暴露策略和可比较统计，但不暴露 Prompt 原文、Authorization、Key 或完整请求。

- [ ] **步骤 4：运行 API 测试确认绿灯**

运行新增 API 测试和现有 API 测试，预期全部通过。

### 任务 5：增加独立线上多人实验页面

**文件：**

- 创建：`bridge/src/stardew_ai_bridge/group_dialogue_lab_page.py`
- 修改：`bridge/src/stardew_ai_bridge/app.py`
- 修改：`bridge/src/stardew_ai_bridge/dialogue_lab_page.py`
- 测试：`bridge/tests/test_external_dialogue_lab.py`

- [ ] **步骤 1：编写失败测试**

断言 `GET /test/group` 返回一个独立实验页面，页面必须包含：参与者选择、三种策略选择、`remote` 固定提示、Provider 选择、公开历史区域、发送按钮、调用次数/错误/fallback/延迟/usage 指标，以及三个策略并排比较入口。

- [ ] **步骤 2：运行测试确认红灯**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_external_dialogue_lab.py -k 'group'
```

预期：FAIL，原因是 `/test/group` 路由和页面不存在。

- [ ] **步骤 3：实现最小实验页面**

页面使用独立模板，不重写现有单次聊天页面。页面行为固定为：

- 默认选择 Abigail + Emily，默认 `turn_based` 和 `fake`，明确标注 Fake 是本地演示，不是真实 AI；
- 支持一次只跑一个策略，也支持“同一输入跑三种策略”按钮；
- 三种策略必须复用同一参与者、同一玩家输入、同一公开历史、同一 `provider`，结果分别显示，不混写历史；
- 只有用户点击发送后才请求 API；
- `cloud` 模式下显示 provider、fallback、errors、calls、latency、usage，失败时显示诊断但不把 fallback 当成成功对白；
- 页面不持久化 Key，不显示请求 Authorization，不把完整 payload 放入 DOM。

在现有工作台导航中增加“多人实验”入口，但保留 `/test`、`/test/chat` 和 `/raw` 原有行为。

- [ ] **步骤 4：运行页面测试确认绿灯**

运行页面定向测试、`node --check`（若页面内含脚本）和 Bridge 全量测试。

### 任务 6：增加同口径比较样例与离线验收

**文件：**

- 创建：`bridge/src/stardew_ai_bridge/group_conversation_cases.py`
- 修改：`bridge/tests/test_group_conversation.py`
- 修改：`docs/active-work.md`

- [ ] **步骤 1：编写失败测试**

增加固定线上实验案例，至少覆盖：

- Abigail + Emily 的普通日常群聊；
- Alex + Sebastian 的玩家与他人交往不安场景；
- Wizard + Sophia 的远程研究话题；
- 参与者历史中包含一个明确点名和一个未点名内容；
- Provider 错误、空回复、未知 speaker 和 `face_to_face` 拒绝。

断言每个案例对三种策略都可构造同一请求，并且比较结果包含策略名、参与者、调用次数、错误、fallback、延迟和 usage 字段。

- [ ] **步骤 2：运行测试确认红灯**

运行新增案例测试，预期因案例目录和统一比较函数不存在而失败。

- [ ] **步骤 3：实现案例目录与比较函数**

新增只读案例目录，案例只保存 NPC ID、显示名、参与者、关系阶段、远程场景和玩家输入，不保存任何密钥或运行时认证信息。提供：

```python
def group_case_catalog() -> list[dict[str, object]]: ...

def comparable_group_payload(case: Mapping[str, object], strategy: str) -> dict[str, object]: ...
```

比较函数只改变 `strategy`，不改变参与者、输入、历史或场景；每次真实云端比较由调用方决定 Provider，不在导入模块时发请求。

- [ ] **步骤 4：运行离线验收**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_group_conversation.py bridge/tests/test_api.py bridge/tests/test_external_dialogue_lab.py
py -3.10 -B -m compileall -q bridge/src scripts
git diff --check
```

预期：多人定向测试全部通过，既有 Bridge 全量回归无失败，Python 编译和空白检查退出码为 `0`。不启动 Bridge，不发起 Gemini 请求。

### 任务 7：官方 Gemini 可用后的真实比较门槛

这一任务只记录验收顺序，不在当前账号条件未确认时执行：

1. 脱敏检查现有官方 `.env.local`，只确认 Key 非空和长度，不打印内容。
2. 使用现有 Bridge 启动脚本重载 `127.0.0.1:5678`，确认监听 PID 属于当前工作树。
3. 先用一个 `turn_based` 请求验证 HTTP 状态、完整 `reply`、`provider`、`fallback=false`、延迟和 usage。
4. 同一案例、同一参与者、同一输入分别跑 `fanout`、`turn_based`、`multi_turn`；每种策略使用独立实验结果目录，不覆盖历史工件。
5. 不把 Fake、fallback、ProviderError 或缺少 usage 的结果作为 Gemini 成功样本。
6. 报告每种策略的：案例数、Provider calls、错误、fallback、重试、Token、延迟、输出完整性和人工质量检查。
7. 重点人工检查：角色是否只说自己的话、是否互相接得住、是否出现抢话/复读/突然加入角色、线上表达是否误写成线下见面、是否违反关系世界边界。

## 计划自检

- 三种策略均有独立定义、契约、实现、Fake 测试和 API 统计字段。
- 单 NPC API、线下 `face_to_face` API 和现有页面不被多人功能替换；多人路由只接受 `remote`。
- Provider 错误、fallback、空回复、未知发言人和越界角色都有明确测试任务。
- 真实 Gemini 比较被放在离线实现和 Fake 验收之后，没有把健康检查或 Fake 结果当成云端成功。
- 没有任务要求读取、打印、提交或保存任何 Key、Token、Cookie 或完整 Authorization Header。
