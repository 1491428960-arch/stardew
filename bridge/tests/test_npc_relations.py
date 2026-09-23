"""NPC↔NPC 关系表的解析测试。

关系图的权威来源是游戏数据 `Data/Characters.json` 的 `FriendsAndFamily`。
它的 value 有两种形态：

1. 本地化引用 —— `[LocalizedText Strings\\Characters:Relative_Nephew]`，
   指向 `Strings/Characters.<locale>.json`，所以亲属关系能精确落到中文；
2. **空串** —— 原版这个字段的语义是「朋友和家人」，空串表示关系密切但
   不是亲属（Gus 的 `{"Emily": "", "Pam": ""}` 就是），只是没细分是哪一种。

2026-09-24 的实机背景：索菲亚提到格斯时说「就是、就是有点怕打扰到他」，
而 SVE 事件对白里 Gus 对她说的是 "Anything for a close family friend!" ——
关系事实从来没进过她的素材。这一层就是把关系事实变成可注入的数据。
"""

from __future__ import annotations

from stardew_ai_bridge.npc_relations import (
    build_relations,
    fill_reciprocal_relations,
    merge_relations,
    relation_key,
    resolve_relation_term,
)


def test_localized_reference_is_parsed_into_its_key() -> None:
    assert (
        relation_key(r"[LocalizedText Strings\Characters:Relative_Nephew]")
        == "Relative_Nephew"
    )


def test_a_plain_string_has_no_relation_key() -> None:
    assert relation_key("") is None
    assert relation_key("随便一句人话") is None


def test_relative_reference_resolves_to_the_localized_term() -> None:
    assert (
        resolve_relation_term(
            r"[LocalizedText Strings\Characters:Relative_Nephew]",
            {"Relative_Nephew": "外甥"},
        )
        == "外甥"
    )


def test_empty_value_means_a_close_non_relative() -> None:
    """空串不是「没数据」，是「朋友／家人里没细分的那一类」。"""

    assert resolve_relation_term("", {}) == "熟人"


def test_unknown_relative_key_falls_back_to_a_generic_word() -> None:
    """引用解出来了、词表里却没有 —— 至少要说清是亲属，不能降级成「熟人」。"""

    assert (
        resolve_relation_term(
            r"[LocalizedText Strings\Characters:Relative_CousinInLaw]",
            {},
        )
        == "亲戚"
    )


def test_term_survives_a_blank_localized_value() -> None:
    """词表里该键存在但是空串，同样按「缺失」处理。"""

    assert (
        resolve_relation_term(
            r"[LocalizedText Strings\Characters:Relative_Niece]",
            {"Relative_Niece": "   "},
        )
        == "亲戚"
    )


def test_build_relations_reads_relatives_and_plain_friends() -> None:
    characters = {
        "Marnie": {
            "FriendsAndFamily": {
                "Shane": r"[LocalizedText Strings\Characters:Relative_Nephew]",
                "Lewis": "",
            }
        },
        "Gus": {"FriendsAndFamily": {"Emily": "", "Pam": ""}},
    }

    relations = build_relations(characters, {"Relative_Nephew": "外甥"})

    assert relations["Marnie"] == [
        {"npc": "Shane", "term": "外甥"},
        {"npc": "Lewis", "term": "熟人"},
    ]
    assert relations["Gus"] == [
        {"npc": "Emily", "term": "熟人"},
        {"npc": "Pam", "term": "熟人"},
    ]


def test_build_relations_skips_characters_without_the_field() -> None:
    """没有 `FriendsAndFamily` 的角色不进结果 —— 空白不等于「没有关系」。"""

    characters = {
        "Sophia": {"DisplayName": "Sophia"},
        "Gus": {"FriendsAndFamily": {"Emily": ""}},
    }

    relations = build_relations(characters, {})

    assert "Sophia" not in relations
    assert list(relations) == ["Gus"]


def test_build_relations_tolerates_an_empty_family_map() -> None:
    """`FriendsAndFamily` 是空字典时不能凭空造出一个空列表。"""

    relations = build_relations({"Sophia": {"FriendsAndFamily": {}}}, {})

    assert relations == {}


def test_merge_lets_curated_relations_win_over_generated_ones() -> None:
    """手工策展的关系带事件对白证据，比从 `FriendsAndFamily` 推的更有信息量。"""

    generated = {"Sophia": [{"npc": "Gus", "term": "熟人"}]}
    extras = {
        "Sophia": [
            {
                "npc": "Gus",
                "term": "亲密的家庭朋友",
                "evidence": "SVE i18n zh.json: Sophia.4hearts.HowAreYou.07",
            }
        ]
    }

    assert merge_relations(generated, extras)["Sophia"] == [
        {
            "npc": "Gus",
            "term": "亲密的家庭朋友",
            "evidence": "SVE i18n zh.json: Sophia.4hearts.HowAreYou.07",
        }
    ]


def test_merge_keeps_generated_entries_the_extras_do_not_cover() -> None:
    generated = {"Marnie": [{"npc": "Shane", "term": "外甥"}]}
    extras = {"Sophia": [{"npc": "Gus", "term": "亲密的家庭朋友", "evidence": "x"}]}

    merged = merge_relations(generated, extras)

    assert merged["Marnie"] == [{"npc": "Shane", "term": "外甥"}]
    assert merged["Sophia"][0]["npc"] == "Gus"


def test_merge_orders_entries_by_npc_name() -> None:
    """输出要稳定：同一份输入永远得到同一个顺序，报告与 diff 才好读。"""

    generated = {
        "Gus": [
            {"npc": "Pam", "term": "熟人"},
            {"npc": "Emily", "term": "熟人"},
        ]
    }

    merged = merge_relations(generated, {})

    assert [entry["npc"] for entry in merged["Gus"]] == ["Emily", "Pam"]


def test_reciprocal_fills_a_one_sided_parent_link() -> None:
    """原版常常只声明一个方向：Abigail 那边写了妈妈，Caroline 这边是空的。

    实测 `Caroline → Abigail` 在 `Data/Characters.json` 里就是空串，
    直接按「非亲属」处理会得到「熟人」——那是错的。
    """

    relations = {
        "Abigail": [{"npc": "Caroline", "term": "妈妈"}],
        "Caroline": [{"npc": "Abigail", "term": "熟人"}],
    }
    characters = {
        "Abigail": {"Gender": "Female"},
        "Caroline": {"Gender": "Female"},
    }
    strings = {"Relative_Mom": "妈妈", "Relative_Daughter": "女儿"}

    filled = fill_reciprocal_relations(relations, characters, strings)

    assert filled["Caroline"] == [{"npc": "Abigail", "term": "女儿"}]
    assert filled["Abigail"] == [{"npc": "Caroline", "term": "妈妈"}]


def test_reciprocal_picks_the_word_by_the_subject_gender() -> None:
    """「妈妈」的反向是儿子还是女儿，取决于正向那一方本人。"""

    relations = {
        "Maru": [{"npc": "Demetrius", "term": "爸爸"}],
        "Demetrius": [{"npc": "Maru", "term": "熟人"}],
    }
    characters = {"Maru": {"Gender": "Female"}, "Demetrius": {"Gender": "Male"}}
    strings = {"Relative_Dad": "爸爸", "Relative_Daughter": "女儿", "Relative_Son": "儿子"}

    filled = fill_reciprocal_relations(relations, characters, strings)

    assert filled["Demetrius"] == [{"npc": "Maru", "term": "女儿"}]


def test_reciprocal_never_overwrites_a_stated_term() -> None:
    """原版明确写过的措辞属于作者意图，哪怕读起来奇怪。

    `Pam → Penny` 在原版数据里就是 `Relative_LittleBabyGirl`（小女婴）——
    不合适，但那是数据，不该被我们改掉。
    """

    relations = {
        "Penny": [{"npc": "Pam", "term": "母亲"}],
        "Pam": [{"npc": "Penny", "term": "小女婴"}],
    }
    characters = {"Penny": {"Gender": "Female"}, "Pam": {"Gender": "Female"}}
    strings = {"Relative_Mother": "母亲", "Relative_Daughter": "女儿"}

    filled = fill_reciprocal_relations(relations, characters, strings)

    assert filled["Pam"] == [{"npc": "Penny", "term": "小女婴"}]


def test_reciprocal_leaves_plain_friendships_alone() -> None:
    """两边都是空串就是真·非亲属（朋友／同事），不能凭空推成亲戚。"""

    relations = {
        "Gus": [{"npc": "Pam", "term": "熟人"}],
        "Pam": [{"npc": "Gus", "term": "熟人"}],
    }

    filled = fill_reciprocal_relations(relations, {}, {})

    assert filled["Gus"] == [{"npc": "Pam", "term": "熟人"}]
    assert filled["Pam"] == [{"npc": "Gus", "term": "熟人"}]


def test_reciprocal_skips_relations_it_cannot_invert() -> None:
    """判不出长幼的（姐妹／兄弟）不做猜测，保持原样。"""

    relations = {
        "Haley": [{"npc": "Emily", "term": "姐姐"}],
        "Emily": [{"npc": "Haley", "term": "熟人"}],
    }
    characters = {"Haley": {"Gender": "Female"}, "Emily": {"Gender": "Female"}}
    strings = {"Relative_Sister": "姐姐"}

    filled = fill_reciprocal_relations(relations, characters, strings)

    assert filled["Emily"] == [{"npc": "Haley", "term": "熟人"}]
