"""批次 2 工具链测试：专有名词候选提取 + persona→索引同步（2026-09-21）。

这个模块把"哪些专有名词值得提升为常驻事实"从手工判断变成可复现流程，
所以它自己也要有闸。三条最要紧的：

1. **索引路径必须与 `scripts/start_bridge.ps1` 一致** —— 用错索引会把角色读成
   兜底值（`_DEFAULT_VOICE_STYLE`），得出完全错误的结论。这条是本批次诊断阶段
   实际踩过的坑，值得钉死。
2. 五道判据的**边界行为**：边界字干净、邻字多样、集中度、全库低频，
   各自都要有正反例（否则"判据"只是注释）。
3. 同步必须**幂等**，且只碰 `alwaysOn` 那批事实。

测试刻意用**夹具语料**而不是真机索引：14.9 MB 的索引不适合每个用例都读，
而且判据的正确性与具体语料无关。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from stardew_ai_bridge.proper_noun_extract import (
    default_index_path,
    extract_candidates,
    extract_vocatives,
    load_corpus,
    persona_always_on_facts,
    sync_index,
)

ROOT = Path(__file__).resolve().parents[2]


# --- 1. 索引路径一致性 --------------------------------------------------------


def test_default_index_matches_the_one_the_bridge_actually_loads() -> None:
    """⚠ 诊断阶段的核心坑：真机索引是 `start_bridge.ps1:22-27` 指定的那一份。

    默认索引（`profile-index.json`）里角色会走兜底 voiceStyle，用它做审计会得出
    「角色没有素材」这种完全错误的结论。工具默认必须用**真机那一份**。
    """

    script = (ROOT / "scripts" / "start_bridge.ps1").read_text(encoding="utf-8")
    match = re.search(
        r"vanilla-sve-rasmodia-profile-index-zh-CN[.\w-]*\.json", script
    )

    assert match, "start_bridge.ps1 里找不到真机索引文件名（路径改了就更新这条测试）"
    assert default_index_path().name == match.group(0)


def test_default_index_lives_under_data_generated() -> None:
    assert default_index_path().parent.name == "generated"
    assert default_index_path().parent.parent.name == "data"


# --- 2. 判据的边界行为 --------------------------------------------------------


def _corpus_index(tmp_path: Path, by_npc: dict[str, list[str]]) -> Path:
    evidence = [
        {"npcId": npc, "text": text}
        for npc, texts in by_npc.items()
        for text in texts
    ]
    path = tmp_path / "index.json"
    path.write_text(
        json.dumps({"schemaVersion": 2, "speechEvidence": evidence}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def test_duplicate_lines_are_not_counted_as_high_frequency(tmp_path: Path) -> None:
    """索引里同一句原文会重复出现；不去重会把"复制粘贴"读成"高频"。"""

    by_npc = load_corpus(_corpus_index(tmp_path, {"Alex": ["真听话，小灰。"] * 5}))

    assert by_npc["Alex"] == ["真听话，小灰。"]


def test_concentrated_repeated_name_is_extracted(tmp_path: Path) -> None:
    """正例：集中 + 复现 + 边界干净 + 邻字多样 ⇒ 抽出来。"""

    by_npc = {
        "Alex": [
            "真听话，小灰。",
            "哦……我在和小灰说话。",
            "快看小灰怎么吃烤牛排的。",
            "嘿。你在抚摸小灰。",
        ],
        "Emily": ["今天天气不错。", "我打算去镇上买点种子。", "海边风挺大的。"],
    }

    candidates = extract_candidates(by_npc)
    names = {row["candidate"] for row in candidates if row["npcId"] == "Alex"}

    assert "小灰" in names


def test_shared_vocabulary_is_not_extracted(tmp_path: Path) -> None:
    """反例：跨角色通用的说法不该被当成某人的专名。"""

    shared = ["今天天气不错。", "我去镇上买东西。", "海边风还挺大的。"]
    by_npc = {"Alex": shared, "Emily": shared, "Shane": shared}

    candidates = extract_candidates(by_npc)

    assert [row for row in candidates if row["localCount"] >= 3 and row["concentration"] < 0.7] == []


def test_fragment_inside_a_longer_phrase_is_dropped() -> None:
    """反例：邻字单一 ⇒ 是更长短语的碎片（「演出大获」总是接「成功」）。"""

    by_npc = {
        "Sam": [f"演出大获成功！第{i}次了。" for i in range(4)],
        "Emily": ["我去镇上买种子。", "海边风很大。", "今天天气不错。"],
    }

    candidates = extract_candidates(by_npc)
    kept = {row["candidate"] for row in candidates if row["npcId"] == "Sam"}

    assert "演出大获" not in kept
    assert "演出大获成" not in kept


def test_function_char_boundaries_are_rejected() -> None:
    """反例：首尾是功能字的切碎噪声（「诉皮埃尔」「比盖尔不」）不该进候选。"""

    by_npc = {
        "Caroline": [
            "我想倾诉皮埃尔的事。",
            "我想倾诉皮埃尔的事。",
            "我想倾诉皮埃尔的事。",
            "阿比盖尔不是我认识的那个人。",
        ],
        "Emily": ["我去镇上买种子。", "海边风很大。", "今天天气不错。"],
    }

    candidates = extract_candidates(by_npc)
    kept = {row["candidate"] for row in candidates if row["npcId"] == "Caroline"}

    assert "诉皮埃尔" not in kept
    assert "比盖尔不" not in kept


def test_vocative_scan_recovers_names_hidden_by_context_words() -> None:
    """呼语补漏：n-gram 判据会漏掉被上下文词盖住的真名。

    Shane 的蓝母鸡「查理」就是被同句的「母鸡」抢了锚点 —— 只靠 n-gram 抽不到。
    """

    by_npc = {
        "Shane": [
            "嘿，查理。",
            "……你懂的，查理……你和其他母鸡从今往后会帮助我昂首向前……",
            "查理过得很好。",
        ],
        "Emily": ["我去镇上买种子。", "海边风很大。"],
    }

    names = {row["candidate"] for row in extract_vocatives(by_npc)}

    assert "查理" in names


# --- 3. persona → 索引同步 ----------------------------------------------------


def _persona_dir(tmp_path: Path, facts: list[dict]) -> Path:
    directory = tmp_path / "personas"
    directory.mkdir()
    (directory / "vanilla.json").write_text(
        json.dumps(
            {"mod": "vanilla", "personas": {"Alex": {"knowledgeFacts": facts}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return directory


def _index_file(tmp_path: Path, facts: list[dict]) -> Path:
    path = tmp_path / "index.json"
    path.write_text(
        json.dumps({"schemaVersion": 2, "knowledgeFacts": facts}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def test_persona_scan_collects_only_always_on_facts(tmp_path: Path) -> None:
    directory = _persona_dir(
        tmp_path,
        [
            {"factId": "alex-football-dream", "summary": "身份事实"},
            {"factId": "alex-dog-dusty", "summary": "养了一条叫「小灰」的狗。",
             "alwaysOn": True, "sourceRefs": ["Characters/Dialogue/Alex"]},
        ],
    )

    found = persona_always_on_facts(directory)

    assert set(found) == {("Alex", "alex-dog-dusty")}


def test_sync_adds_missing_fact_with_the_same_source_mod(tmp_path: Path) -> None:
    directory = _persona_dir(
        tmp_path,
        [
            {"factId": "alex-football-dream", "summary": "身份事实"},
            {"factId": "alex-dog-dusty", "summary": "养了一条叫「小灰」的狗。",
             "alwaysOn": True, "sourceRefs": ["Characters/Dialogue/Alex"]},
        ],
    )
    index = _index_file(
        tmp_path,
        [{"factId": "alex-football-dream", "npcId": "Alex", "sourceMod": "vanilla",
          "summary": "身份事实"}],
    )

    assert sync_index(index, directory, apply=True) == 0
    payload = json.loads(index.read_text(encoding="utf-8"))

    added = [f for f in payload["knowledgeFacts"] if f["factId"] == "alex-dog-dusty"]
    assert len(added) == 1
    assert added[0]["alwaysOn"] is True
    assert added[0]["sourceMod"] == "vanilla"


def test_sync_is_idempotent_and_leaves_a_backup(tmp_path: Path) -> None:
    directory = _persona_dir(
        tmp_path,
        [{"factId": "alex-dog-dusty", "summary": "养了一条叫「小灰」的狗。",
          "alwaysOn": True, "sourceRefs": ["Characters/Dialogue/Alex"]}],
    )
    index = _index_file(tmp_path, [{"factId": "x", "npcId": "Emily", "summary": "无关"}])

    sync_index(index, directory, apply=True)
    first = index.read_text(encoding="utf-8")
    sync_index(index, directory, apply=True)
    second = index.read_text(encoding="utf-8")

    assert first == second, "第二次同步改动了文件，说明不幂等"
    assert list(tmp_path.glob("index.json.bak-before-alwayson")), "没有留下备份"


def test_sync_preview_does_not_write(tmp_path: Path) -> None:
    directory = _persona_dir(
        tmp_path,
        [{"factId": "alex-dog-dusty", "summary": "养了一条叫「小灰」的狗。",
          "alwaysOn": True, "sourceRefs": ["Characters/Dialogue/Alex"]}],
    )
    index = _index_file(tmp_path, [])
    before = index.read_text(encoding="utf-8")

    sync_index(index, directory, apply=False)

    assert index.read_text(encoding="utf-8") == before


@pytest.mark.skipif(
    not default_index_path().is_file(),
    reason="真机索引不在（data/generated 被 .gitignore 排除）",
)
def test_shipped_index_is_already_synced(tmp_path: Path) -> None:
    """交付状态闸：真机索引已经是同步过的（同步是幂等操作）。"""

    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = sync_index(
            default_index_path(),
            ROOT / "data" / "personas",
            apply=False,
        )

    assert code == 0
    assert "索引已是最新，无需改动。" in buffer.getvalue()
