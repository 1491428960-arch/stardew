"""批次 2：专有名词提升为**常驻事实**（2026-09-21）。

用户实测：群聊里 Alex 说自己养了只叫「小黑」的狗。事实对（Alex 正典确有狗
Dusty）、专名错（官方中文译名是「小灰」）。

真因不是模型幻觉，是**结构性取不到**：

* `speechEvidence[:4]` 是**切片不是选择**。Alex 的素材池有 211 条，含「小灰」的
  8 条（去重 6 条）排在深处 —— 专有名词天生与多数玩家输入不相关，按位置切片
  **永远轮不到它**；
* 那 8 条全是 `event_dialogue`，还受 `completedEventIds` 门控；
* 常驻通道 `knowledgeFacts`（Alex 只有 1 条身份事实）和 `knownCharacters`
  （只有 Haley 一条关系）都**不装"角色有什么"**。

所以修法不是加大切片长度，而是把专有名词放进一条**不参与排序**的通道：
`knowledgeFacts` 里标 `alwaysOn: true` 的条目单独成组（`alwaysKnownFacts`），
与"普通闲聊只注入 1 条"的门控**互不占名额**。

本文件钉四件事：

1. 数据侧确实有这些事实（Alex 的狗是用户点名的正解）；
2. `alwaysOn` 标记能穿过**全部五处**白名单/切片 —— 这是本批次最容易假通过的地方：
   任何一处漏掉，数据"写进去了"而行为一点没变（见
   `test_always_on_marker_survives_every_layer`）；
3. 常驻事实**不会挤掉**原有的那条身份事实；
4. persona 里标了 `alwaysOn` 的事实必须已经同步进**索引**（真机读的是索引，
   不是 persona 文件）—— 这条是"改了数据但忘了同步"的回归闸。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PERSONAS_DIR = ROOT / "data" / "personas"
INDEX_PATH = (
    ROOT / "data" / "generated"
    / "vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
)

# 用户点名的正解：名字必须是「小灰」，不是模型先验里的「小黑」。
ALEX_DOG_NAME = "小灰"


def _persona_facts() -> list[tuple[str, str, dict]]:
    rows: list[tuple[str, str, dict]] = []
    for path in sorted(PERSONAS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for npc_id, profile in (payload.get("personas") or {}).items():
            if not isinstance(profile, dict):
                continue
            for fact in profile.get("knowledgeFacts") or []:
                if isinstance(fact, dict):
                    rows.append((path.name, npc_id, fact))
    return rows


def _index() -> dict:
    return json.loads(INDEX_PATH.read_text(encoding="utf-8-sig"))


@pytest.fixture()
def shipped_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """把 `ContextBuilder` 的索引显式换成**真机索引**。

    ⚠ 不能靠 `BRIDGE_PROFILE_INDEX` 环境变量：`scripts/verify_project.ps1` 不设它，
    于是测试进程读的是 `data/generated/profile-index.json`（1.4 MB 那份兜底索引），
    里面既没有 SVE 的人物事实、也没有本批次新增的常驻事实。
    靠环境变量的写法会"本地绿、verify 红"—— 本批次实际踩过一次。
    （`scripts/start_bridge.ps1:22-27` 才是指定真机索引的那一处。）
    """

    if not INDEX_PATH.is_file():
        pytest.skip("真机索引不在（data/generated 被 .gitignore 排除）")

    from stardew_ai_bridge import app as app_module
    from stardew_ai_bridge.profile_index import ProfileIndexStore

    monkeypatch.setattr(
        app_module.context_builder,
        "profile_index",
        ProfileIndexStore(INDEX_PATH),
    )


# --- 1. 数据侧 ----------------------------------------------------------------


def test_alex_knows_his_dog_is_called_xiaohui() -> None:
    """「Alex 有一条叫小灰的狗」必须在常驻事实里，且名字逐字是「小灰」。"""

    facts = [
        fact
        for _, npc_id, fact in _persona_facts()
        if npc_id == "Alex" and fact.get("alwaysOn") is True
    ]

    assert facts, "Alex 没有任何 alwaysOn 事实"
    dog = [fact for fact in facts if ALEX_DOG_NAME in str(fact.get("summary"))]
    assert dog, "Alex 的常驻事实里没有提到「小灰」"
    assert dog[0]["knowledgeScope"] == "canon_confirmed"
    assert str(dog[0].get("factId")).strip(), "常驻事实必须有 factId"
    # 反例闸：模型先验里的错名不得被写进数据
    assert "小黑" not in json.dumps(dog, ensure_ascii=False)


@pytest.mark.parametrize(
    ("npc_id", "proper_noun"),
    [
        ("Alex", "小灰"),
        ("Alex", "祖父母"),
        ("Shane", "查理"),
        ("Victor", "杜威"),
        ("Lance", "姜岛"),
    ],
)
def test_第一批常驻事实都在数据里(npc_id: str, proper_noun: str) -> None:
    hits = [
        fact
        for _, owner, fact in _persona_facts()
        if owner == npc_id
        and fact.get("alwaysOn") is True
        and proper_noun in str(fact.get("summary"))
    ]

    assert hits, f"{npc_id} 的常驻事实里没有「{proper_noun}」"


def test_every_always_on_fact_is_well_formed() -> None:
    """常驻事实要有稳定的 id、可读的 summary 和来源，否则不进 prompt 也罢。"""

    bad: list[str] = []
    for path_name, npc_id, fact in _persona_facts():
        if fact.get("alwaysOn") is not True:
            continue
        if not str(fact.get("factId") or "").strip():
            bad.append(f"{path_name}:{npc_id}: 缺 factId")
        if len(str(fact.get("summary") or "").strip()) < 8:
            bad.append(f"{path_name}:{npc_id}:{fact.get('factId')}: summary 太短")
        if not fact.get("sourceRefs"):
            bad.append(f"{path_name}:{npc_id}:{fact.get('factId')}: 缺 sourceRefs")

    assert bad == []


# --- 2. 五层白名单/切片都得放过 alwaysOn --------------------------------------


def test_always_on_marker_survives_every_layer() -> None:
    """`alwaysOn` 必须穿过**五处**：任何一处漏掉，"数据写了"等于"行为没变"。

    1. `profile_index._normalise_knowledge_fact`（persona → 索引的归一化）
    2. `profile_index.ProfileIndex._FACT_FIELDS`（索引 → 访问器的字段白名单）
    3. `prompts._compact_knowledge_fact`（访问器 → 安全上下文的字段白名单）
    4. `prompts` 的 compact 切片 `knowledgeFacts[:1]`（**夹在中间那一刀**）
    5. `prompts` 的 `knowledge_facts` 卡（分栏 + 常驻名额）
    """

    from stardew_ai_bridge.profile_index import ProfileIndexStore, _normalise_knowledge_fact
    from stardew_ai_bridge.prompts import _compact_knowledge_fact

    raw = {
        "factId": "demo-dog",
        "summary": "养了一条叫「小灰」的狗。",
        "knowledgeScope": "canon_confirmed",
        "confidence": "high",
        "sourceRefs": ["Characters/Dialogue/Demo"],
        "alwaysOn": True,
    }

    # ① persona → 索引
    normalised = _normalise_knowledge_fact(
        raw, fact_id="demo-dog", npc_id="Demo", source_mod="vanilla",
        summary=raw["summary"], scope="canon_confirmed",
    )
    assert normalised.get("alwaysOn") is True

    # ② 索引 → 访问器（字段白名单是类属性，直接查表，避免构造整个索引）
    assert "alwaysOn" in ProfileIndexStore._FACT_FIELDS

    # ③ 访问器 → 安全上下文
    assert _compact_knowledge_fact(normalised).get("alwaysOn") is True


def test_always_on_facts_bypass_the_single_fact_gate_in_the_live_path(
    shipped_index: None,
) -> None:
    """线上（compact + 日常寒暄）路径：常驻事实进 prompt，且不占普通名额。"""

    from stardew_ai_bridge.app import _build_context

    body = {
        "npcId": "Alex", "message": "你好呀", "intent": "chat", "provider": "fake",
        "compactPrompt": True, "channel": "face_to_face",
        "sourceMods": ["vanilla", "female-bachelors"],
        "history": [],
        "gameState": {
            "npcId": "Alex", "displayName": "Alex", "location": "Town",
            "season": "spring", "date": "25", "weather": "clear", "time": 1200,
            "friendship": 1500, "friendshipHearts": 6, "relationship": "friend",
        },
    }

    _, messages = _build_context(body)
    card = next(
        json.loads(m["content"]) for m in messages if m["name"] == "knowledge_facts"
    )

    assert card.get("alwaysKnownFacts"), "常驻事实没进 prompt（五处里有一处漏了）"
    assert any(
        ALEX_DOG_NAME in str(fact.get("summary"))
        for fact in card["alwaysKnownFacts"]
    )
    assert card.get("alwaysKnownInstruction")
    # 普通名额仍是 1 条 —— 常驻事实**没有**挤占它
    assert len(card["knowledgeFacts"]) == 1
    assert "职业运动员" in str(card["knowledgeFacts"][0]["summary"])


def test_ordinary_facts_still_obey_the_gate(shipped_index: None) -> None:
    """没有标 alwaysOn 的角色不受影响：日常寒暄仍只给 1 条普通事实。"""

    from stardew_ai_bridge.app import _build_context

    body = {
        "npcId": "Sophia", "message": "你好呀", "intent": "chat", "provider": "fake",
        "compactPrompt": True, "channel": "face_to_face",
        "sourceMods": ["vanilla", "SVE", "FlashShifter.StardewValleyExpandedCP"],
        "history": [],
        "gameState": {
            "npcId": "Sophia", "displayName": "Sophia", "location": "Town",
            "season": "spring", "date": "25", "weather": "clear", "time": 1200,
            "friendship": 1500, "friendshipHearts": 6, "relationship": "friend",
        },
    }

    _, messages = _build_context(body)
    card = next(
        json.loads(m["content"]) for m in messages if m["name"] == "knowledge_facts"
    )

    assert len(card["knowledgeFacts"]) == 1
    assert "alwaysKnownFacts" not in card


# --- 3. 索引同步闸 ------------------------------------------------------------


def test_persona_always_on_facts_reach_the_shipped_index() -> None:
    """真机读的是索引，不是 persona 文件。

    只改 `data/personas/*.json` 而忘了同步索引，表现是"数据明明写进去了、
    游戏里一点变化没有"—— 这条把那种假完成挡在测试里。
    同步方式见 `.tmp/sync-always-on-facts.py`（幂等，带备份）。
    """

    if not INDEX_PATH.is_file():
        pytest.skip("真机索引不在（data/generated 被 .gitignore 排除），跳过同步闸")

    payload = _index()
    shipped = {
        (str(fact.get("npcId")), str(fact.get("factId"))): fact
        for fact in payload.get("knowledgeFacts") or []
        if isinstance(fact, dict)
    }

    missing: list[str] = []
    for _, npc_id, fact in _persona_facts():
        if fact.get("alwaysOn") is not True:
            continue
        fact_id = str(fact.get("factId"))
        entry = shipped.get((npc_id, fact_id))
        if entry is None:
            missing.append(f"{npc_id}:{fact_id} 不在索引里")
        elif entry.get("alwaysOn") is not True:
            missing.append(f"{npc_id}:{fact_id} 在索引里但没有 alwaysOn 标记")
        elif str(entry.get("summary")) != str(fact.get("summary")):
            missing.append(f"{npc_id}:{fact_id} 的 summary 与 persona 不一致")

    assert missing == [], "索引未同步：\n" + "\n".join(missing)
