"""roleGuidance 与 persona 措辞必须是「对象导向」，不是「过程导向」（2026-09-21）。

背景（用户实测索菲亚）：「刚把最后一层**罩光**放到窗边」——「罩光」是绘画工序
术语，很生僻，而索菲亚的定位是轻快口语：她 311 条原文对话里绘画相关词只有 4 处
（两处还是「画眼线」），`varnish` / 罩光 / 清漆 **0 命中**。

诊断出的上游不是语料，是**指令本身**：
`_CONVERSATION_LEAD_ROLE_GUIDANCE["Sophia"]` 当时写着
「可以从葡萄品种、**发酵过程或绘画过程**选一个具体细节」——
模型被要求讲「过程」，而「过程」在模型先验里就是工序名（罩光、罩染、打底）。

本文件钉住改写后的口径：**要求仍然具体，但落在一道工序上的写法不许回来。**

2026-09-21 二轮（同一天，用户实测「总是谈画」）：索菲亚那条又从「对象导向」推进到
「**跨语义簇的落点池 + 同一类最多连续两次**」——一轮那次的四个落点（葡萄／酒窖／
画笔／画里的具体东西）仍全在酿造 + 绘画这一簇里，模型照样连着几轮不换。

2026-09-21 三轮：落点池从**硬编码四个类别**改成 `{topicPool}` 占位符 + 由
`preferredTopics` 渲染（同源，见 `test_stage_policy.py`）。于是本文件的断言也分两层：
模板层只钉「不讲过程」与「有轮换上限 + 有占位符」，**跨簇改由渲染结果断言**
（`test_rendered_sophia_guidance_spans_semantic_clusters`）——只读模板会永远失败，
只读数据源又验不到渲染。

2026-09-21 四轮（用户指出歧义）：「同一类最多连续两次」这句**自带一个出口**，
二轮想压的那两面因此没压住。它同时引入**两个层级**（同一类 = 生活面，
同一个 = 落点），而**最松读法**（画 → 画 → 酒）在字面上就算"换了"——模型把画
换成酒即可交差。改成**动作式**：「连着两轮谈酿造或绘画，第三轮就换到镇上的事或
她自己的近况」，单层、点名两个簇、给出出口。模板层断言随之改成钉这一句
（`test_sophia_rotation_rule_is_action_shaped`），并加闸防止层级词回来。

本文件的"不讲过程"闸保持不变，跨簇与轮换上限另见
`test_stage_policy.py::test_sophia_conversation_lead_guidance_bridges_cellar_and_creative_topics`。

刻意**不**禁用「过程」两个字本身：`female-bachelors.json` 里 Shane 的
avoid「把恢复过程说成已经彻底解决」是在**禁止**把过程说死，方向相反。
判据只抓「从／说／讲／落到 … 过程」这种**生成指令**形态。
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

from stardew_ai_bridge.stage_policy import (
    _CONVERSATION_LEAD_ROLE_GUIDANCE,
    _ROLE_OVERRIDES,
    _facet_of_topic,
    build_stage_policy,
)

ROOT = Path(__file__).resolve().parents[2]

_PROCESS_DIRECTIVE = re.compile(r"(从|说|讲|落到|挑)[^。；]{0,24}过程")

# "架上绘画"那一组词（含工序名）。刻意**不含**单字「画」：
# 索菲亚语料里真实有「我今天早上画了眼线」（化妆），那是她的原话，不是缺陷。
_PAINTING_NOUNS = re.compile(r"绘画|画画|画布|画架|画笔|画作|画框|颜料|罩光|罩染|打底")


def _sophia_preferred_topics() -> list[str]:
    """索菲亚数据源里的偏好主题 —— 落点池的唯一数据源（与 stage_policy 同源）。"""

    for path in sorted((ROOT / "data" / "personas").glob("*.json")):
        for npc, profile in _persona_profiles(path):
            if npc != "Sophia":
                continue
            voice_style = profile.get("voiceStyle")
            topics = (
                voice_style.get("preferredTopics")
                if isinstance(voice_style, dict)
                else None
            )
            if topics:
                return [str(topic) for topic in topics]
    raise AssertionError("data/personas 里找不到索菲亚的 preferredTopics")


def test_sophia_guidance_lands_on_objects_not_on_a_process() -> None:
    text = _CONVERSATION_LEAD_ROLE_GUIDANCE["Sophia"]

    assert "绘画过程" not in text
    assert "发酵过程" not in text
    assert _PROCESS_DIRECTIVE.search(text) is None
    # 2026-09-21 二轮：落点池从「同一个语义簇里的四个词」改成「跨簇 + 轮换上限」。
    # 三轮：模板里的四个类别换成 `{topicPool}` 占位符，由调用方从 `preferredTopics`
    # 渲染进来 —— 模板层只钉得住「有上限、有占位符」，「四类都在」见下一条。
    # 四轮：上限句式改成动作式，歧义闸见
    # `test_sophia_rotation_rule_is_action_shaped`。
    # 五轮：触发条件从"连着两轮"收紧到"上一轮"，与新 `variationRule` 的
    # 「不允许连续两轮同面」对齐（旧写法字面允许连着两轮 = 一松一紧取最松）。
    # 2026-09-24：被压的两个簇里「绘画」换成「角色扮演」（SVE 查证：她的创作面是
    # 角色扮演／缝纫，不是画画）。**规则形状一个字没动，只换词**。
    assert "谈过酿造或角色扮演" in text
    assert "{topicPool}" in text


def test_sophia_rotation_rule_is_action_shaped() -> None:
    """轮换规则要写「做什么」，不再是「别超过几类」（2026-09-21 四轮）。

    旧写法「同一类最多连续两次——酒和画算同一类生活面，连着两轮说同一个就该换」
    同时出现"同一类"与"同一个"两个层级，最松读法（画 → 画 → 酒）字面上满足
    "换了"，等于给"总是谈画"留了一条换成酒的出口。动作式写法只有一个层级：
    点名被压的两个簇，并明确下一轮去哪里。

    2026-09-21 五轮：触发条件再收紧一轮 —— 旧句写「连着两轮……第三轮就换」，
    字面**允许连着两轮**，而 `variationRule` 的新上限是「不允许连续两轮同面」。
    两句并排又是一松一紧，模型会挑松的那个读。改成「谈过……下一轮就换」。

    2026-09-24：两个簇的名字由「酿造 / 绘画」改成「酿造 / **角色扮演**」。
    形状（单层、点名两个簇、出口写死）仍然一字不动。
    """

    text = _CONVERSATION_LEAD_ROLE_GUIDANCE["Sophia"]

    assert "谈过酿造或角色扮演" in text
    assert "下一轮就换到镇上的事或她自己的近况" in text
    # 层级词与旧句式不得回来——它们正是那个出口
    assert "同一类" not in text
    assert "生活面" not in text
    assert "连着两轮说同一个" not in text
    # 五轮删掉的更松上限
    assert "第三轮就换" not in text


def test_rendered_sophia_guidance_spans_semantic_clusters() -> None:
    """占位符必须被渲染成数据源里的**全部**类别，一个都不许漏。

    三轮把落点池改成「模板 + 数据源」之后，「跨簇」不再是模板的属性，而是
    **渲染结果**的属性。数据源第 4 类「安全感与新开始」在 `preferredTopics`
    limit=3 的时代进不了 prompt，落点池却点名了它 —— 那正是这次要堵的错位
    （要求落 A，而 A 恰好是被截断的那一类）。
    """

    topics = _sophia_preferred_topics()
    guidance = build_stage_policy("Sophia", "dating", preferred_topics=topics)[
        "conversationLead"
    ]["roleGuidance"]

    assert "{topicPool}" not in guidance
    assert all(topic in guidance for topic in topics)
    # 显式点名两个**非酿造非绘画**的方向：这是「总是谈画」的解药。
    # 2026-09-21 六轮（批次 4b）：这两条素材本身已从抽象元类目
    # （「小镇日常」「安全感与新开始」）改写成可落座的具体物，断言跟着换词。
    # 2026-09-25：素材由 7 条补到 12 条 / 9 面全覆盖，写法同时压短（10 字/条 → 约 6 字/条），
    # 渲染 230/240 —— `roleGuidance` 的 240 字截断线仍然卡着，**不压短就装不下 12 条**
    # （不压短是 268 字，超 28 字会被静默截断）。断言跟着换到新词。
    # 2026-10-01：`roleGuidance` 改用独立上限 `_ROLE_GUIDANCE_LIMIT`（240 → 320）。
    # 上面那次"压短"是为挤进当时的口径，现在余量够了 —— 素材库扩容不必再靠压字腾空间。
    assert "镇上的新鲜事" in guidance
    assert "海边的咸风" in guidance


def test_no_role_guidance_asks_the_model_to_narrate_a_process() -> None:
    """回归闸：任何角色的 roleGuidance 都不该要求模型「讲过程」。"""

    offenders = {
        role: _PROCESS_DIRECTIVE.search(text).group(0)
        for role, text in _CONVERSATION_LEAD_ROLE_GUIDANCE.items()
        if _PROCESS_DIRECTIVE.search(text)
    }

    assert offenders == {}


def _persona_profiles(path: Path) -> list[tuple[str, dict]]:
    """人设文件是 ``{mod, sourceMods, personas: {npc: profile}}``。

    直接遍历顶层会走到 ``mod`` / ``sourceMods`` 这两个包装键上，
    一个角色都扫不到——那是**假通过**，所以这里显式下钻。
    """

    data = json.loads(path.read_text(encoding="utf-8"))
    personas = data.get("personas") if isinstance(data, dict) else None
    if not isinstance(personas, dict):
        return []
    return [(key, value) for key, value in personas.items() if isinstance(value, dict)]


def test_persona_voice_styles_have_no_process_directives() -> None:
    """全量人设回归：voiceStyle 里不再有「讲过程」这种生成指令。"""

    offenders: list[str] = []
    for path in sorted((ROOT / "data" / "personas").glob("*.json")):
        for npc, profile in _persona_profiles(path):
            voice = profile.get("voiceStyle")
            if not isinstance(voice, dict):
                continue
            for field in ("responseRules", "sentencePattern", "signatureMoves"):
                for item in voice.get(field) or []:
                    if isinstance(item, str) and _PROCESS_DIRECTIVE.search(item):
                        offenders.append(f"{path.name}:{npc}.{field}: {item[:50]}")

    assert offenders == []


@pytest.mark.parametrize(
    ("npc", "old", "new"),
    [
        ("Penny", "谈教学时说具体的学习过程", "谈教学时说具体的课堂小事"),
    ],
)
def test_penny_teaching_rule_points_at_classroom_objects(
    npc: str,
    old: str,
    new: str,
) -> None:
    """同一原则的第二处：Penny「说具体的学习过程」→「说具体的课堂小事」。"""

    data = json.loads(
        (ROOT / "data" / "personas" / "vanilla.json").read_text(encoding="utf-8")
    )
    rules = data["personas"][npc]["voiceStyle"]["responseRules"]
    joined = "；".join(rules)

    assert new in joined
    assert old not in joined


def test_sophia_persona_stops_claiming_she_paints() -> None:
    """SVE 查证：她的创作面是**角色扮演／缝纫**，不是画画（2026-09-24）。

    起因是收尾体检（`docs/report-overnight-dialogue-2026-09-23.md` §5.4）：
    `signatureMoves` 写「谈到酿造、**绘画**」、`preferredTopics` 写
    「画布上还没画完的那一块」，而她那 265 条语料里含"画"的只有「画了眼线」
    （化妆）和「你看动画吗」（动漫）。体检当时**没查 SVE 的非对白资源**，
    本轮补查了 `[CP] Stardew Valley Expanded` 的资产／事件／邮件／地图：

    - **没有画具、没有画室、没有画作相关事件。** 她家 55 条可查看物
      （`SophiaHouse.1~56`）里没有画架／画布／画，唯一沾"油漆"的是
      `SophiaHouse.18`「很多**布料和油漆**」—— 与缝纫材料并列的手工耗材。
    - **她自己的原话里创作＝角色扮演 + 缝纫**：`CharacterDialogue.136`
      「我在计划我的下一个角色扮演」、`.144`「艾米丽有一台很好的缝纫机」、
      `.166`「艾米丽正在缝制一套华丽的服装」、`Marriage.004`「她设计了一个新的缝纫图案」、
      `10hearts.01`「这是我的《草原王者大冒险》角色扮演！我为了做这个忙了一段时间」。
      家里是「一本旧的手工艺品手册」（`SophiaParentsRoom.4`）、
      《服装设计指南——角色扮演的应用》（`SophiaHouse.15`）。
    - 唯一沾"艺术"的是 `CharacterDialogue.174`「**艺术瓶颈**，被我打破了」
      （英文 "Artist's block, no more!"）—— 指她那个没点名的"项目"，
      **不等于架上绘画**；另有 `NightMarket.001`「我可能会买幅画」，是**买**画。
    - `Furniture.json` 里的 `Prismatic Painting` 之类是 SVE 通用家具目录的
      墙面装饰，不属于她。

    因此本轮按"移除／替换"处理：**人设与指令两侧**一共 13 处「绘画」全部换成
    角色扮演／缝纫／手工／布料 —— 人设 9 处（`sve.json`）＋ `stage_policy.py` 4 处
    （`_ROLE_OVERRIDES["Sophia"]["acquaintance"/"friend"]` 3 处、
    `_CONVERSATION_LEAD_ROLE_GUIDANCE["Sophia"]` 1 处）。
    其中 `preferredTopics` 那条仍落**同一个生活面**（「工作或手艺」——`布料` 与
    `缝纫` 本来就在该面词表里，`_LIFE_FACET_PATTERNS` 第 467 行），面覆盖不变。

    ⚠ **本条的真正目的**：这个仓库反复出现过"同一 bug 只修一处"（人设改了、指令
    没改，或反过来）。所以这一条**同时扫两侧**——人设（`sve.json`）与指令
    （`stage_policy.py` 的两个 Sophia 专用 dict）。任何一侧回退成"绘画"都会红。
    """

    data = json.loads(
        (ROOT / "data" / "personas" / "sve.json").read_text(encoding="utf-8")
    )
    sophia = data["personas"]["Sophia"]

    flat: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str):
            flat.append(node)

    walk(sophia)
    joined = "\n".join(flat)

    # 钉的是"架上绘画"那一组词，不是单字「画」——「画了眼线」是她语料里
    # 真实存在的一条（化妆），不该被这条闸挡住。
    offenders = [
        f"sve.json:{line}"
        for line in flat
        if _PAINTING_NOUNS.search(line)
    ]

    # 指令侧：这两处都在 prompt 里（`stage_execution_card` 与 `final_role_voice_contract`），
    # 只修人设不修这里就是这个 bug 的另一半。
    policy_texts = {
        "stage_policy._CONVERSATION_LEAD_ROLE_GUIDANCE['Sophia']":
            _CONVERSATION_LEAD_ROLE_GUIDANCE["Sophia"],
        "stage_policy._ROLE_OVERRIDES['Sophia']":
            json.dumps(_ROLE_OVERRIDES["Sophia"], ensure_ascii=False),
    }
    for label, text in policy_texts.items():
        for match in _PAINTING_NOUNS.finditer(text):
            start = max(0, match.start() - 30)
            end = min(len(text), match.end() + 30)
            offenders.append(f"{label}:…{text[start:end]}…")

    assert offenders == [], offenders

    # 换上去的方向要有原话支撑，不能只是把"画"删掉留一个空洞。
    assert "角色扮演" in joined
    assert "缝" in joined
    assert "角色扮演" in policy_texts[
        "stage_policy._CONVERSATION_LEAD_ROLE_GUIDANCE['Sophia']"
    ]
    assert "角色扮演" in policy_texts["stage_policy._ROLE_OVERRIDES['Sophia']"]
    # 原话支撑的具体物仍要在池里 —— 删掉"画"之后不能只留一片空洞。
    # ⚠ 本条原先的注释写「第 2 条必须仍在「工作或手艺」面上」，那是**错的**：
    #   实测 `_facet_of_topic("格斯做菜时那股香味")` = 「吃喝」（"菜"命中吃喝词表），
    #   从来不是工作面。断言真正在验的是"有原话支撑的吃喝向具体物还在"。
    #   2026-09-25 素材压短后该条为「格斯做的菜」，面归属不变（吃喝）。
    #   工作面本身也没丢：`手工房的布料` / `蓝月亮的年份` 两条都落在该面。
    assert "格斯做的菜" in sophia["voiceStyle"]["preferredTopics"]
    assert _facet_of_topic("手工房的布料") == "工作或手艺"


def test_sophia_rendered_prompt_has_no_painting_words() -> None:
    """行为层的同一道闸：**渲染出来的 prompt** 里不许再有"架上绘画"。

    上一条钉的是源码字面量（`sve.json` / `stage_policy.py`）。2026-09-24 扫全库时
    又找出**第 5 处**：`prompts.py` 的 `_build_turn_plan` 里有一条 Sophia 专用的
    自然开场指令写着「命中葡萄园、**绘画**或其他喜欢的话题时…」（只在
    `compact=False` 的评测／实验室路径生效，游戏端走通用分支）。

    教训是"同一 bug 只修一处"：字面量分散在三个文件里，靠人工 grep 一定会漏。
    这一条改成**渲染真实 prompt 再扫** —— 少一处就红，不依赖谁记得住有哪几处。
    """

    from stardew_ai_bridge.prompts import PromptBuilder

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "dating": "喜欢或被夸时可以先热烈回应，连说两句后害羞地改口",
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "topicSeed": "收工时发现一小串葡萄裂开了",
            "topicKeywords": ["葡萄", "收工"],
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")

    offenders: list[str] = []
    for message in messages:
        content = message.get("content", "")
        for match in _PAINTING_NOUNS.finditer(content):
            start = max(0, match.start() - 40)
            end = min(len(content), match.end() + 40)
            offenders.append(f"[{message.get('name')}] …{content[start:end]}…")

    assert offenders == [], offenders
    # 反向确认这条路径真的渲染出了 Sophia 的专用指令（否则上面的空断言是假通过）。
    turn_plan = next(
        json.loads(message["content"])
        for message in messages
        if message.get("name") == "turn_plan"
    )
    assert "口头冲动" in turn_plan["instruction"]
    assert "角色扮演" in turn_plan["instruction"]


def test_no_sophia_quality_case_still_has_her_painting() -> None:
    """第四道闸：**全部评测案例**里，这两位角色的字段一个字都不许再提"架上绘画"。

    为什么必须单独一条：前三条闸盯的是**线上**（人设 / `stage_policy` / turn-plan），
    而**评测案例是第四层**——它们不进游戏，却会进评测 prompt。
    只改前三层的话，"我们后面跑的验证会是在测一个她会画画的版本"。

    覆盖两位（都给过证据、都拍板改过）：

    - **Sophia**：SVE 查证她不做架上绘画（无画具/画室/画作事件；家里那句是
      「很多布料和油漆」，油漆是手工材料）。她的创作面是**角色扮演 + 缝纫**。
    - **Elliott**：他是**写作者**（230 条语料：写 22 / 书 25 / 小说 16 / 诗 6 / 创作 9），
      全库含「画」只有 **2 处，且都是他夸 Leah 的画**；英文原版里
      `manuscript`/`draft`/`sketch`/`paint`/`studio` 也都是 0，
      76 条事件台词同样 0。案例原本给的「画室 / 海面速写 / 那幅画」不是他的设定。

    ⚠ **刻意不覆盖的**：Elliott 案例里的「**稿子 / 手稿**」**保持原样**——
    那是**同义说法缺口**（他确实是写作者，只是 230 条里没用「稿」这个字），
    属于"三类假阳性"的第 ③ 类，不是"替他加设定"。
    `case_id`（含 `elliott-close-studio` 与三处 `*painting`）按用户口径保留原名。

    这一条**刻意收单字「画」**（前三条闸不收，因为「画了眼线」是 Sophia 的真实原话）。
    2026-09-24 实测教训：我第一遍扫案例时正则不含单字「画」，
    于是漏掉了 `pacing-sophia-vineyard-evening` 里的「**画室**／**新画**」——
    正是用户提醒过的那个坑。只在 `画了眼线` 这一处开例外。
    """

    from stardew_ai_bridge.character_quality_eval import (
        QUALITY_SUITE_IDS,
        quality_cases_for_suite,
    )

    watched = {"Sophia", "Elliott"}
    pattern = re.compile(r"画(?!了眼线)|速写|写生|paint\w*|easel|canvas|sketch\w*")

    def strings(node: object, path: str):
        if isinstance(node, str):
            yield path, node
        elif dataclasses.is_dataclass(node) and not isinstance(node, type):
            # ⚠ 2026-09-24 补这个分支之前，本闸**从来没扫过 `case.turns`** ——
            # `_materialize_quality_turns` 把 follow-up 轮次放进 `turns` 字段，
            # 而它是 `CharacterQualityTurn` 的元组；下面原先只有 str/list/tuple/dict
            # 三支，dataclass 落空、被静默跳过。于是 `elliott-daily` 的
            # turn-2「一页海景**速写**，纸边还沾着沙。」在两轮修正里都漏了过去
            # （`速写` 明明在 pattern 里）。同型教训本项目记过一次：
            # **tuple 里的非字符串元素会静默返回空**。
            for field in dataclasses.fields(node):
                yield from strings(
                    getattr(node, field.name, None), f"{path}.{field.name}"
                )
        elif isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                yield from strings(item, f"{path}[{index}]")
        elif isinstance(node, dict):
            for key, value in node.items():
                yield from strings(value, f"{path}.{key}")

    checked_cases = 0
    offenders: list[str] = []
    for suite in QUALITY_SUITE_IDS:
        for case in quality_cases_for_suite(suite):
            if _text_field(case, "npc_id") not in watched:
                continue
            checked_cases += 1
            for name, value in _dataclass_values(case):
                # `case_id` **刻意排除**：它是历史标识符，被测试与历史 artifacts 钉着，
                # 改名会断基线。用户 2026-09-24 拍板"保留原名、只改内容"，
                # 所以这些 case_id 是**预期存在**的。
                if name == "case_id":
                    continue
                for path, text in strings(value, name):
                    if pattern.search(text):
                        offenders.append(f"{suite}/{case.case_id} {path} = {text[:90]}")

    # 反向确认真的扫到了案例（否则空断言是假通过）。
    assert checked_cases >= 12, checked_cases
    assert offenders == [], offenders


def _text_field(case: object, name: str) -> str:
    value = getattr(case, name, "")
    return value if isinstance(value, str) else ""


def _dataclass_values(case: object):
    import dataclasses

    for field in dataclasses.fields(case):
        yield field.name, getattr(case, field.name, None)


def test_harvey_and_victor_keep_their_existing_object_focus() -> None:
    """核查记录：这两个角色**本来就**是对象导向，本轮刻意没动。

    Harvey 在 roleGuidance 里已经有「专业信息必须说得日常、简短」；
    Victor 的人设写的是「落到材料、结构或实际用途」+「用复杂术语掩盖没有回答
    玩家的问题」——两者都不需要改，这条测试防止有人"顺手"把它们改掉。
    """

    harvey = _CONVERSATION_LEAD_ROLE_GUIDANCE["Harvey"]
    assert "专业信息必须说得日常、简短" in harvey

    sve = json.loads(
        (ROOT / "data" / "personas" / "sve.json").read_text(encoding="utf-8")
    )
    victor = sve["personas"]["Victor"]["voiceStyle"]
    assert any("材料" in rule and "结构" in rule for rule in victor["responseRules"])
    assert any("复杂术语" in rule for rule in victor["avoid"])
