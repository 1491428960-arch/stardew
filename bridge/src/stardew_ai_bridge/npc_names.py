"""语料里出现过的拉丁 NPC 名（一律小写），**只给 `guard` 用**。

## 它是干什么的

`guard.ResponseGuard._allowed_english` 拿它判断「模型是不是输出了外语」：
中文回复里出现名单之外的连续三字母以上拉丁词，就判 `english` 并**重发一次请求**。

原名单只有 42 项，而语料里真实出现过的纯字母 `npcId` 有 **142 个** —— 于是
「Leo」「Sandy」「Marlon」这类合法角色名一出现在中文对白里就被判成 `english`，
`retry_for_format_noise` **真的重发一次请求**，而那次重试没有意义（名字本来就
该在那儿）。实测 `winter-11-willy` 单轮 7599 token，是正常值的 1.9 倍。

原名单 42 项**全是角色名**，说明「放行专名」是当初就想清楚的；这里只是把它按
语料补齐，没有改变方向。

## ⚠ 不要把它给 `reply_scrub` —— 两处是**故意不同源**的

2026-09-27 我一度以为这是「两处名单漏了同步」，把 `reply_scrub._KEEP_LATIN`
也接了过来。`test_api.py::test_fake_dialogue_returns_structured_response`
立刻变红，而**它是对的**：

| | 判什么 | 宽窄 |
|---|---|---|
| `guard._allowed_english` | 这个词算不算「模型输出外语」 | **宽** —— 放行角色名，免得白重试 |
| `reply_scrub._KEEP_LATIN` | 这个词**能不能给玩家看** | **窄** —— 中文台词里露英文**角色名**就是错的 |

两者是**配合**工作的：`Rasmodia` 这类 mod 英文标识在 guard 那边不触发重试
（重试也没用，它本来就是那个词），但到 `reply_scrub` 必须被擦掉 ——
玩家在游戏里看到的是中文显示名。接成同源等于把后者那道防线拆了。

### 2026-09-28 补充：窄名单里其实有两类，别搞混

「窄」指的是**角色名**。**品牌／作品名是另一类** —— 原版中文自己就保留它们，
而删掉是**静默损坏**：输出通顺、没有告警，没人会发现语义被改了：

```
我在 Joja 上班。  ->  我在上班。        # 在 Joja 工作 ≠ 在上班
我今天去了 Joja。  ->  我今天去了。      # 句子直接残缺
```

判据同样是**语料而不是感觉**：扫 32126 条原版中文文本，夹在中文里的拉丁词
一共只有 11 个，`Joja` 一家 **401 次**（`scan_keep_latin.py`）。
其中 10 个已加进 `_KEEP_LATIN`（排除碎片 `oja` 与单字符 `D`）。

⚠ **方向仍与 guard 相反，不要把 `_allowed_english` 接过来**：
它放行的是**角色名**（142 个语料 `npcId`），而角色名恰恰是必须擦掉的那一类。
「品牌名放行」不等于「英文整体放行」——
`test_reply_scrub.py` 里「我昨天在 Joja 碰到 Shane 了」那条用例就是钉这个边界的。

## 名单怎么来

不靠手写，脚本扫 corpus 全部 `npcId`（要求整体是 `[A-Za-z]{3,}`）求出来的，
另加几个通用词。**手写必然漏** —— 第一次补齐时我就抄丢了原本已在名单里的
`claire` 和 `leah`。
`bridge/tests/test_guard.py::test_allowed_english_covers_every_corpus_npc_id`
拿语料求差守着这一点，加名字请顺手跑它。

## 为什么垫成独立模块而不是内联进 `guard`

与 `reply_scrub` 无关，纯粹是为了让它可被单独引用和测试，顺便让
`guard.py` 少 150 行数据。

**只排除了 `marriagedialogue`** —— 那是语料里的已知脏数据（键被当成了说话人），
不是一个 NPC。
"""

from __future__ import annotations

ALLOWED_LATIN = frozenset(
    {
        # —— 通用词，不是人名 ——
        "ai",
        "joja",
        "jojamart",
        "npc",
        "rasmodia",
        "sve",
        # —— 原版角色 ——
        "abigail",
        "alex",
        "andy",
        "bouncer",
        "caroline",
        "clint",
        "curator",
        "demetrius",
        "dwarf",
        "elliott",
        "emily",
        "evelyn",
        "george",
        "gil",
        "governor",
        "grandpa",
        "gunther",
        "gus",
        "haley",
        "harvey",
        "jas",
        "jodi",
        "kent",
        "krobus",
        "leo",
        "lewis",
        "linus",
        "marlon",
        "maru",
        "marnie",
        "mermaid",
        "morris",
        "mrqi",
        "pam",
        "penny",
        "pierre",
        "professorsnail",
        "robin",
        "sam",
        "sandy",
        "sebastian",
        "shane",
        "vincent",
        "willy",
        "wizard",
        # —— SVE 与其他 mod 角色 ——
        "aguar",
        "alecto",
        "alesia",
        "apples",
        "axel",
        "ayeisha",
        "bear",
        "bianka",
        "birdie",
        "brianna",
        "brock",
        "brooklyn",
        "camilla",
        "cassandra",
        "charliechicken",
        "chloe",
        "claire",
        "clothestherapycharacters",
        "cordelia",
        "daia",
        "daisy",
        "dianna",
        "drake",
        "dusty",
        "dwarfroommate",
        "edmund",
        "emin",
        "esmeralda",
        "eugene",
        "fisher",
        "freya",
        "gabbi",
        "gabriel",
        "gale",
        "gertrude",
        "gunthersilvian",
        "hanksve",
        "highlandsdwarf",
        "isaac",
        "jace",
        "jade",
        "jadu",
        "jascute",
        "jasper",
        "jio",
        "jojapetstoreemployee",
        "jolyne",
        "juliet",
        "juna",
        "junaroommate",
        "junimo",
        "katarynalk",
        "kenneth",
        "kiwi",
        "laarni",
        "lance",
        "leah",
        "leomainland",
        "lola",
        "lucikiel",
        "lunna",
        "maddie",
        "mainstagecosplayer",
        "marlonfay",
        "martin",
        "misterginger",
        "monacute",
        "morgan",
        "morristod",
        "oddi",
        "olivia",
        "parrotboy",
        "peaches",
        "rainy",
        "raphael",
        "reenus",
        "salvador",
        "sawyer",
        "scarlett",
        "scarlettfake",
        "silba",
        "silly",
        "sophia",
        "sophiajpksprite",
        "suki",
        "susan",
        "treyvon",
        "tristancute",
        "tristanlk",
        "victor",
        "wellwick",
        "witch",
        "witchcute",
        "zinnia",
        "zoey",
        "zoomiedoggoowner",
    }
)
