from __future__ import annotations

from collections.abc import Iterable, Mapping
from difflib import SequenceMatcher
import re
from typing import Any

from .personas import canonical_npc_id


REVIEW_DIMENSIONS = (
    "stardewVoice",
    "characterDistinctiveness",
    "relationshipFit",
    "channelFit",
    "topicResponse",
    "contextContinuity",
    "naturalChinese",
    "boundarySafety",
)

_ALLOWED_CHANNELS = {"remote", "face_to_face", "any"}
_ALLOWED_STAGES = {
    "stranger",
    "acquaintance",
    "friend",
    "close",
    "dating",
    "married",
    "parent",
    "any",
}
_ALLOWED_INITIATIVE_EXPECTATIONS = {"none", "responsive", "proactive", "guarded"}
_ALLOWED_INITIATIVE_KINDS = {
    "none",
    "affection_signal",
    "specific_plan",
    "guarded_care",
    "conversation_exit",
    "companionship",
    "creative_share",
    "playful_tease",
    "shared_evening",
    "care_action",
}
_REVISION_TAGS = {
    "too_formal",
    "generic_voice",
    "wrong_stage",
    "wrong_channel",
    "magic_overreach",
    "repeated_opener",
    "unnatural_chinese",
    "invented_lore",
}
_SENSITIVE_KEYS = {
    "apikey",
    "api_key",
    "token",
    "cookie",
    "authorization",
    "bearer",
    "prompt",
    "payload",
}
_CONTAINER_KEYS = {"request", "response", "config"}
_SECRET_LABEL = re.compile(
    r"(?i)\b(api[_-]?key|token|cookie|authorization|bearer|prompt)\s*[:=]\s*"
    r"(?:bearer\s+)?[^\s,;]+"
)
_KNOWN_FIELDS = (
    "exampleId",
    "npcId",
    "sourceMods",
    "channels",
    "relationshipStages",
    "speechFunction",
    "topic",
    "topicKeywords",
    "emotion",
    "playerInput",
    "npcReply",
    "sourceType",
    "sourceRefs",
    "initiativeExpectation",
    "initiativeKind",
    "review",
)


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: object) -> list[str] | None:
    if isinstance(value, str):
        values: Iterable[object] = (value,)
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        values = value
    else:
        return None
    return list(dict.fromkeys(
        item.strip()
        for item in values
        if isinstance(item, str) and item.strip()
    ))


def validate_review(review: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    for dimension in REVIEW_DIMENSIONS:
        score = review.get(dimension)
        if (
            not isinstance(score, int)
            or isinstance(score, bool)
            or score not in {0, 1, 2}
        ):
            errors.append(f"invalid-score:{dimension}")
    hard_errors = review.get("hardErrors", [])
    if hard_errors is not None and not isinstance(hard_errors, list):
        errors.append("invalid:hardErrors")
    tags = review.get("tags", [])
    if tags is not None and not isinstance(tags, list):
        errors.append("invalid:tags")
    return errors


def validate_behavior_example(
    raw: Mapping[str, object],
    *,
    require_review: bool = False,
) -> tuple[dict[str, object] | None, list[str]]:
    if not isinstance(raw, Mapping):
        return None, ["invalid:example"]

    errors: list[str] = []
    normalized: dict[str, object] = {}
    for field in ("exampleId", "npcId", "playerInput", "npcReply"):
        value = _text(raw.get(field))
        if not value:
            errors.append(f"missing:{field}")
        else:
            normalized[field] = value

    if "npcId" in normalized:
        normalized["npcId"] = canonical_npc_id(normalized["npcId"])

    for field in ("sourceMods", "channels", "relationshipStages", "topicKeywords", "sourceRefs"):
        if field not in raw:
            continue
        values = _string_list(raw[field])
        if values is None or (field in {"channels", "relationshipStages"} and not values):
            errors.append(f"invalid:{field}")
            continue
        normalized[field] = values
        if field == "channels":
            errors.extend(
                f"invalid:channels:{value}"
                for value in values
                if value.casefold() not in _ALLOWED_CHANNELS
            )
        if field == "relationshipStages":
            errors.extend(
                f"invalid:relationshipStages:{value}"
                for value in values
                if value.casefold() not in _ALLOWED_STAGES
            )

    for field in ("speechFunction", "topic", "emotion"):
        if field not in raw:
            continue
        value = _text(raw[field])
        if value:
            normalized[field] = value

    source_type = _text(raw.get("sourceType")) or "handcrafted_example"
    normalized["sourceType"] = source_type

    for field, allowed in (
        ("initiativeExpectation", _ALLOWED_INITIATIVE_EXPECTATIONS),
        ("initiativeKind", _ALLOWED_INITIATIVE_KINDS),
    ):
        if field not in raw:
            continue
        value = _text(raw.get(field)).casefold()
        if value not in allowed:
            errors.append(f"invalid:{field}")
        else:
            normalized[field] = value

    if "review" in raw:
        review = raw["review"]
        if not isinstance(review, Mapping):
            errors.append("invalid:review")
        else:
            review_errors = validate_review(review)
            errors.extend(review_errors)
            normalized["review"] = sanitize_quality_artifact(dict(review))
    elif require_review:
        errors.append("missing:review")

    return (None, errors) if errors else (normalized, [])


def review_passes(review: Mapping[str, object]) -> bool:
    if not isinstance(review, Mapping) or review.get("hardErrors"):
        return False
    tags = review.get("tags", [])
    if isinstance(tags, list) and _REVISION_TAGS.intersection(
        str(tag).strip().casefold() for tag in tags
    ):
        return False
    return all(
        isinstance(review.get(dimension), int)
        and not isinstance(review.get(dimension), bool)
        and int(review[dimension]) >= 1
        for dimension in REVIEW_DIMENSIONS
    )


def _sanitize_text(value: str) -> str:
    return _SECRET_LABEL.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        value,
    )


def sanitize_quality_artifact(value: object) -> object:
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            key_text = str(key)
            folded = key_text.casefold().replace("-", "_")
            if folded in _SENSITIVE_KEYS:
                continue
            if folded in _CONTAINER_KEYS:
                sanitized[key_text] = {}
                continue
            sanitized[key_text] = sanitize_quality_artifact(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_quality_artifact(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_quality_artifact(item) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


_INITIATIVE_SIGNAL_MARKERS: dict[str, tuple[str, ...]] = {
    "affection_signal": (
        "想你",
        "想念",
        "想起你",
        "想到你",
        "想着你",
        "想起我",
        "想到我",
        "惦记你",
        "等你",
        "等着你",
        "盼着你",
        "盼你",
        "可惜你不在",
        "希望你在",
        "希望你能来",
        "想和你",
        "想跟你",
        "想陪你",
        "有你在",
        "在你身边",
        "期待你",
        "期待和你",
        "期待与你",
        "与你一同",
        "与你共度",
        "见到你",
        "和你在一起",
        "和你待在一起",
        "你在我身边",
        "有你在身边",
        "心里安静",
        "心里不平静",
        "最想听你的",
        "把时间留给你",
        "让你靠近",
        "舍不得你",
        "巴不得你",
        "在意你",
        "喜欢你",
        "偏爱",
        "给你留",
        "留一点给你",
        "亲爱的",
    ),
    "specific_plan": (
        "今晚",
        "明天",
        "改天",
        "哪天",
        "一起",
        "约会",
        "吃饭",
        "听歌",
        "骑车",
        "散步",
        "尝一口",
        "陪我",
    ),
    "guarded_care": (
        "先休息",
        "早点睡",
        "吃点东西",
        "带点吃的",
        "我会陪",
        "我陪你",
        "需要空间",
        "别担心",
        "照看",
        "帮你",
    ),
    "conversation_exit": (
        "先睡了",
        "明天再说",
        "不打扰了",
        "不打扰你",
        "先这样",
        "到这吧",
        "不想聊",
        "晚安",
        "先休息",
    ),
    "companionship": (
        "陪你聊",
        "陪我聊",
        "一起待",
        "陪你",
        "陪我",
    ),
    "creative_share": (
        "给你听",
        "给你看",
        "分享",
        "放一首",
        "看我的画",
    ),
    "playful_tease": (
        "别得意",
        "太保守",
        "自恋",
        "哼",
        "吐槽",
    ),
    "shared_evening": (
        "坐一会儿",
        "留给我",
        "共度",
        "过来坐",
    ),
    "care_action": (
        "我去",
        "我来",
        "留给我",
        "分担",
        "做晚饭",
    ),
}
_ROMANTIC_MARKERS = (
    "想你",
    "想念",
    "想起你",
    "想到你",
    "惦记你",
    "等你",
    "盼着你",
    "盼你",
    "可惜你不在",
    "希望你在",
    "想和你",
    "想陪你",
    "期待你",
    "期待和你",
    "与你共度",
    "有你在",
    "喜欢你",
    "爱你",
    "偏爱",
    "亲爱的",
    "抱",
    "吻",
    "亲密",
)
_TIME_FOR_PLAYER_PREFERENCE_PATTERN = re.compile(
    r"(?:多|都)?留(?:出|下|些)?(?:一点|一)?时间给你"
)
_GENERIC_PAIR_EXCLUSIVE_PATTERN = re.compile(
    r"(?:今晚|现在).{0,8}(?:就)?(?:咱们|我们)(?:俩|两个)"
)
_ONLY_LOOKING_AT_ME_TEASE_PATTERN = re.compile(r"(?:你)?(?:可)?别只看(?:着)?我")
_PREFER_PLAYER_COMPANIONSHIP_PATTERN = re.compile(
    r"(?:我)?(?:更|还是更).{0,2}想陪(?:着)?你"
)
_PREFER_PLAYER_COMPANIONSHIP_WITH_PATTERN = re.compile(
    r"(?:我)?(?:更|还是更)想(?:要)?(?:和|跟)你"
    r"(?:.{0,10}(?:待|在一起|聊天|说话|坐|喝|听|看))?"
)
_WANT_PLAYER_COMPANIONSHIP_PATTERN = re.compile(
    r"(?:我)?想(?:要|再|多|一直|总是)?(?:和|跟)你"
    r"(?:.{0,10}(?:待|在一起|聊天|说话|坐|喝|听|看))?"
)
_PLAYER_ONLY_ATTENTION_PATTERN = re.compile(
    r"(?:专心|只顾着|一直|总在)看(?:着)?你"
)
_PLAYER_ONLY_LOOK_PATTERN = re.compile(r"(?:我)?(?:就|只)?想看着你")
_EXCLUSIVE_COMPANIONSHIP_PATTERN = re.compile(
    r"(?:我)?只想陪(?:着)?你(?=[，,。！？!?]|$)"
)
_DIRECT_EXCLUSIVE_SHARE_PATTERN = re.compile(r"(?:只想|只|先).{0,8}给你(?:看|听)")
_COMPARISON_ATTENTION_TEASE_PATTERN = re.compile(
    r"比起.{0,20}(?:我)?(?:一直|更|只|就)?.{0,6}看(?:着)?你"
)
_PERSONAL_AFFECTION_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "player_directed_preference": (
        re.compile(r"(?:想你|想念你|想着你|想起你|想到你|惦记你|在意你|喜欢你|偏爱你|舍不得你)"),
        re.compile(r"(?:有|跟|和)你.{0,12}(?:安心|安静|高兴|自在)"),
        re.compile(r"因为你在(?:这儿|这里|身边|旁边)"),
        re.compile(r"有你在(?:身边|这儿|这里|旁边).{0,16}(?:更|才|就|变得|美妙|安心|开心|自在)"),
        re.compile(r"(?:一直|总|还).{0,4}等你(?:.{0,8}(?:说|来|有空))?"),
        re.compile(r"(?:最想|只想).{0,8}(?:和|跟)你"),
        re.compile(
            r"巴不得(?:一直|总是|就)?(?:和|跟)你"
            r"(?:.{0,10}(?:待|在一起|聊天|说话|坐|喝|听|看))?"
        ),
        re.compile(r"(?:也就|只有)你(?:能|会|让我|才)"),
        re.compile(r"(?:不过|但|其实)?(?:我)?(?:更|还是更)想看你"),
        _PREFER_PLAYER_COMPANIONSHIP_PATTERN,
        _PREFER_PLAYER_COMPANIONSHIP_WITH_PATTERN,
        _WANT_PLAYER_COMPANIONSHIP_PATTERN,
        _PLAYER_ONLY_ATTENTION_PATTERN,
        re.compile(r"巴不得(?:一直|总是|就)?(?:和|跟)你"),
        _PLAYER_ONLY_LOOK_PATTERN,
        _TIME_FOR_PLAYER_PREFERENCE_PATTERN,
        re.compile(r"(?:更|还是更)?想把.{0,8}时间留给你"),
        re.compile(r"(?:想|要).{0,8}(?:时间|今晚|这(?:一)?会儿).{0,8}留给你"),
        re.compile(r"满脑子(?:想的|都是)你"),
        re.compile(r"(?:哪有|没有).{0,8}你重要"),
        re.compile(r"(?:陪你|和你|跟你).{0,6}(?:才是正事|更重要)"),
        re.compile(r"(?:陪你|和你|跟你).{0,8}(?:才是|最|更)?重要"),
        re.compile(
            r"(?:能|和|跟)你(?:一起)?(?:喝酒|待着|待在一起|坐着|聊天|听歌|散步|看画|看星星).{0,10}(?:开心|高兴|安心|安静|自在)"
        ),
        re.compile(
            r"陪你.{0,6}(?:待着|待在一起|坐着|聊天|听歌|散步|看画|看星星).{0,10}(?:开心|高兴|安心|安静|自在)"
        ),
        re.compile(
            r"(?:最|就)?喜欢(?:和|跟)你(?:一起)?(?:喝酒|待着|待在一起|坐着|聊天|听歌|散步|看画|看星星)"
        ),
        re.compile(
            r"(?:最|就)?喜欢陪你(?:一起)?(?:待着|坐着|聊天|听歌|散步|看画|看星星)"
        ),
        re.compile(r"(?:给你抱|抱你|让你抱|想抱你|亲你|吻你)"),
        re.compile(
            r"(?:和|跟)你(?:一起)?(?:喝|听|看|待).{0,10}(?:感觉更好|更好|更安心|更开心|很舒服)"
        ),
        re.compile(r"(?:跟|和)你在一起(?:的)?(?:时间)?.{0,8}(?:怎么都|总是)?不够"),
        re.compile(r"(?:跟|和)你(?:待在)?一起.{0,12}(?:时间|过得).{0,8}(?:快|不够|短)"),
        re.compile(r"你(?:才|可是)?(?:是)?我最想陪(?:的)?人"),
        re.compile(
            r"(?:跟|和)你(?:聊天|说话|待着|在一起).{0,8}比什么都(?:强|好|重要)"
        ),
        re.compile(
            r"(?:跟|和)你(?:聊天|说话|待着|在一起).{0,14}比.{0,14}(?:有意思|更好|重要)"
        ),
        re.compile(r"可惜你不在"),
        re.compile(r"希望你.{0,8}(?:旁边|身边|在)"),
        re.compile(r"盼(?:着)?你来"),
    ),
    "exclusive_share": (
        _DIRECT_EXCLUSIVE_SHARE_PATTERN,
        re.compile(r"(?:只|特地).{0,8}留给你"),
        re.compile(
            r"(?:时间|今晚|这(?:一)?会儿|安静).{0,8}(?:只|都).{0,4}给你留(?:着|下|好)?"
        ),
        re.compile(r"(?:这首|这段).{0,8}(?:只|先).{0,4}听给你(?:一个人)?"),
        re.compile(r"(?:音乐|安静).{0,12}(?:就)?留给你"),
        re.compile(r"(?:时间|今晚).{0,8}留给(?:你和我|我们(?:两个)?)"),
        re.compile(
            r"(?:时间|今晚).{0,8}(?:只|都).{0,4}(?:给|属于)(?:你我|你和我|我们)(?:二人|两人|两个)?"
        ),
        re.compile(r"(?:时间|这段时间|那段时间).{0,8}(?:归你|属于你)"),
        re.compile(
            r"(?:这(?:份|个)?安静(?:的)?(?:时候|时刻)|安静(?:的)?(?:时候|时刻))"
            r".{0,6}(?:归你|留给你|属于你)"
        ),
        re.compile(r"(?:只有|只因).{0,8}你.{0,8}(?:才|更)"),
        _EXCLUSIVE_COMPANIONSHIP_PATTERN,
        _GENERIC_PAIR_EXCLUSIVE_PATTERN,
        re.compile(r"(?:今晚|现在).{0,3}只陪你(?=[，,。！？!?]|$)"),
        re.compile(r"(?:今晚|现在).{0,3}只看着你(?=[，,。！？!?]|$)"),
        re.compile(
            r"只(?:和|跟)你(?:一起)?(?:待着|待在一起|坐着|聊天|喝酒|听歌|散步|看画|看星星)(?:真好|就好|也好|[，,。！？!?]|$)"
        ),
        re.compile(r"给你留(?:了)?(?:一|这|那)?(?:杯|份|瓶)"),
        re.compile(r"(?:别人|其他人).{0,8}(?:没有|不必|不用).{0,8}(?:给|看|听)"),
    ),
    "player_caused_anticipation": (
        re.compile(r"因为你.{0,8}(?:会来|要来|会听|会看|喜欢|想要)"),
        re.compile(r"你一(?:说|提|来).{0,10}(?:期待|开始|挑|留|准备)"),
        re.compile(r"(?:等|想等)你来.{0,8}(?:决定|一起|再)"),
    ),
    "personalized_care": (
        re.compile(r"知道你.{0,12}(?:所以|才|就)"),
        re.compile(r"按你(?:的)?.{0,8}(?:留|做|准备)"),
        re.compile(r"不想让你.{0,12}(?:一个人|太累|硬扛|受凉)"),
        re.compile(r"(?:不|没)(?:想|会|愿意)?.{0,6}让你等.{0,12}(?:舍不得|不忍心|不想)"),
        re.compile(r"你上次.{0,12}(?:胃不舒服|不舒服|难受|着凉).{0,20}(?:熬|煮|做).{0,8}(?:粥|汤|药).{0,8}给你"),
    ),
    "vulnerable_disclosure": (
        re.compile(r"(?:通常|一般).{0,8}不(?:跟|和).{0,8}(?:别人|人)说"),
        re.compile(r"(?:这件事|这话|这些).{0,8}(?:没|没有).{0,8}(?:跟|和).{0,4}(?:别人|其他人).{0,8}说过"),
        re.compile(r"(?:只想|只愿意).{0,8}(?:告诉|跟).{0,8}你"),
        re.compile(r"在你面前.{0,10}(?:承认|可以说|不用装)"),
    ),
    "character_consistent_tease": (
        re.compile(r"(?:就你|只有你).{0,10}(?:能|值得|配).{0,10}(?:看|听|陪|赢)"),
        re.compile(r"(?:别得意|自恋).{0,12}(?:但|，).{0,12}你"),
        re.compile(r"(?:不只|不止).{0,10}看.{0,10}(?:还|也).{0,4}看你"),
        re.compile(
            r"(?:耳朵|注意力|目光).{0,4}(?:只|就只).{0,4}你"
            r"(?:.{0,4}(?:竖|听|留意|集中|放在你身上))?"
        ),
        _COMPARISON_ATTENTION_TEASE_PATTERN,
        _ONLY_LOOKING_AT_ME_TEASE_PATTERN,
        re.compile(r"你.{0,12}(?:样子|模样).{0,8}(?:有魅力|迷人|好看)"),
        re.compile(r".{0,12}(?:没|不如)你(?:好看|漂亮|迷人)"),
        re.compile(r"哪有你(?:好看|漂亮|迷人)"),
        re.compile(r"谁也比不了你"),
    ),
}
_COMPANIONSHIP_SUPPORT_PATTERNS = (
    re.compile(r"(?:陪你|陪我|一起待|一块待|等你|给你(?:看|听))"),
)
_FUNCTIONAL_TASK_PATTERNS = (
    re.compile(
        r"(?:收拾|整理|清理|修(?:好|理)?|搬(?:走|开)?|准备|过一遍|算完|喂鸡|浇|建|采购|交付|交给|给|查看|核对|汇报|交代|送|拿).{0,12}(?:鸡舍|账本|农活|工具|货物|材料|栅栏|农田|作物|订单|早餐|东西|建筑|房子)"
    ),
    re.compile(
        r"(?:鸡舍|账本|农活|工具|货物|材料|栅栏|农田|作物|订单|早餐|东西|建筑|房子).{0,12}(?:收拾|整理|清理|修(?:好|理)?|搬(?:走|开)?|准备|过一遍|算完|喂鸡|浇|建|采购|交付|交给|给|查看|看|核对|汇报|交代|送|拿)"
    ),
)
_SPECIFIC_PLAN_PATTERNS = (
    re.compile(r"(?:一起|约).{0,8}(?:吃饭|骑车|散步|听歌|喝茶|出门|看画)"),
    re.compile(
        r"(?:陪你|陪我|和你|跟你|一起|一块|搭把手|帮(?:个)?忙).{0,12}(?:收拾|整理|修(?:好|理)?|搬|清理|准备)"
    ),
    re.compile(r"(?:今晚|明天|改天).{0,12}(?:七点|几点|在.{0,8}见|安排|约)"),
    re.compile(r"(?:七点|几点).{0,12}(?:见|出发|过来)"),
    *_FUNCTIONAL_TASK_PATTERNS,
)
_FUNCTIONAL_CONTEXT_AMBIGUOUS_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "player_directed_preference": (
        _TIME_FOR_PLAYER_PREFERENCE_PATTERN,
        _PREFER_PLAYER_COMPANIONSHIP_PATTERN,
        _PREFER_PLAYER_COMPANIONSHIP_WITH_PATTERN,
        _WANT_PLAYER_COMPANIONSHIP_PATTERN,
        _PLAYER_ONLY_ATTENTION_PATTERN,
        _PLAYER_ONLY_LOOK_PATTERN,
    ),
    "exclusive_share": (
        _DIRECT_EXCLUSIVE_SHARE_PATTERN,
        _GENERIC_PAIR_EXCLUSIVE_PATTERN,
    ),
    "character_consistent_tease": (_ONLY_LOOKING_AT_ME_TEASE_PATTERN,),
}
_GENERIC_ROMANCE_MARKERS = (
    "命中注定",
    "永远爱你",
    "你是我唯一",
    "灵魂伴侣",
    "一生一世",
)
_REMOTE_ROMANCE_MARKERS = (
    "已经见面",
    "已经碰面",
    "就在你面前",
    "已经赴约",
    "过来找我",
)
_GUARDED_CLOSE_INPUT_MARKERS = (
    "别逼我",
    "没心情",
    "心情很差",
    "很难受",
    "先不说了",
    "不想聊",
    "不用陪",
    "别过来",
    "就这样吧",
)
_GUARDED_CLOSE_REPLY_MARKERS = (
    "好好休息",
    "早点休息",
    "先休息",
    "别跟我较劲",
)


def _mechanical_restatement(reply: str, player_input: str) -> bool:
    """判断回复是否大段搬运了本轮玩家输入，而非自然回应。"""

    if not reply.strip() or not player_input.strip():
        return False
    normalize = lambda value: re.sub(r"[\s，。！？、；：,.!?;:…‘’“”\"'（）()]+", "", value.casefold())
    reply_text = normalize(reply)
    player_text = normalize(player_input)
    if len(reply_text) < 3 or len(player_text) < 3:
        return False
    match = SequenceMatcher(None, reply_text, player_text, autojunk=False).find_longest_match(
        0,
        len(reply_text),
        0,
        len(player_text),
    )
    common = match.size
    mirror_markers = (
        "你是说",
        "听起来你",
        "所以你的意思",
        "也就是说",
        "换句话说",
        "你刚才提到",
        "你刚才说",
        "你说的",
        "刚才提到",
        "前面说",
    )
    recap_marker = any(normalize(marker) in reply_text for marker in mirror_markers)
    if recap_marker:
        return common >= 3 and common / min(len(reply_text), len(player_text)) >= 0.35
    if common < 8:
        return False
    return recap_marker or (
        common >= 12
        and common / min(len(reply_text), len(player_text)) >= 0.55
    )


def _field_from_object(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _matches_personal_affection(text: str) -> list[str]:
    """返回可解释的个人亲近类别，不把陪伴或安排单独当作爱意。"""

    matched_shapes: list[str] = []
    for shape, patterns in _PERSONAL_AFFECTION_PATTERNS.items():
        ambiguous_patterns = _FUNCTIONAL_CONTEXT_AMBIGUOUS_PATTERNS.get(shape, ())
        for pattern in patterns:
            for match in pattern.finditer(text):
                if pattern in ambiguous_patterns and _has_functional_context(
                    text,
                    match,
                ):
                    continue
                matched_shapes.append(shape)
                break
            else:
                continue
            break
    return matched_shapes


def _matched_clause(text: str, match: re.Match[str]) -> str:
    """返回正则命中所在的子句，用于局部排除事务性歧义。"""

    delimiters = "，,。！？!?；;：:"
    clause_start = max(text.rfind(delimiter, 0, match.start()) for delimiter in delimiters) + 1
    clause_end_candidates = [
        position
        for delimiter in delimiters
        if (position := text.find(delimiter, match.end())) >= 0
    ]
    clause_end = min(clause_end_candidates) if clause_end_candidates else len(text)
    return text[clause_start:clause_end]


def _has_functional_context(text: str, match: re.Match[str]) -> bool:
    """判断亲近命中是否被同一事务句或紧邻承接句限定。"""

    if _has_pattern(_matched_clause(text, match), _FUNCTIONAL_TASK_PATTERNS):
        return True
    delimiters = "，,。！？!?；;：:"
    next_delimiter = next(
        (
            position
            for delimiter in delimiters
            if (position := text.find(delimiter, match.end())) >= 0
        ),
        len(text),
    )
    if next_delimiter >= len(text):
        return False
    next_clause = text[next_delimiter + 1 :]
    next_clause = re.split(f"[{re.escape(delimiters)}]", next_clause, maxsplit=1)[0]
    return bool(
        re.match(r"\s*(?:把|也|还|再|顺便|同时)", next_clause)
        and _has_pattern(next_clause, _FUNCTIONAL_TASK_PATTERNS)
    )


def _has_pattern(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def diagnose_personal_affection(text: object) -> dict[str, object]:
    """提取不依赖旧词表的个人亲近信号，供质量诊断和 Guard 共用。"""

    normalized = text.strip() if isinstance(text, str) else ""
    affection_evidence = _matches_personal_affection(normalized)
    companionship_detected = _has_pattern(
        normalized,
        _COMPANIONSHIP_SUPPORT_PATTERNS,
    )
    specific_plan_detected = _has_pattern(
        normalized,
        _SPECIFIC_PLAN_PATTERNS,
    )
    return {
        "personalAffectionDetected": bool(affection_evidence),
        "companionshipDetected": companionship_detected,
        "specificPlanDetected": specific_plan_detected,
        "affectionEvidence": affection_evidence,
        "affectionShape": (
            affection_evidence[0]
            if affection_evidence
            else "companionship"
            if companionship_detected
            else "specific_plan"
            if specific_plan_detected
            else ""
        ),
    }


def diagnose_affection_initiative(
    case: object,
    turn: object,
    reply: str,
    *,
    player_input: str = "",
) -> dict[str, object]:
    """诊断一轮回复是否执行了预期主动行为；不修改回复文本。"""

    text = reply.strip() if isinstance(reply, str) else ""
    lowered = text.casefold()
    expectation = str(
        _field_from_object(turn, "initiative_expectation", "none") or "none"
    ).strip().casefold()
    expected_kind = str(
        _field_from_object(turn, "initiative_kind", "none") or "none"
    ).strip().casefold()
    if expectation not in _ALLOWED_INITIATIVE_EXPECTATIONS:
        expectation = "none"
    if expected_kind not in _ALLOWED_INITIATIVE_KINDS:
        expected_kind = "none"

    detected_kinds = {
        kind
        for kind, markers in _INITIATIVE_SIGNAL_MARKERS.items()
        if any(marker.casefold() in lowered for marker in markers)
    }
    tags: set[str] = set(detected_kinds)
    stage = str(_field_from_object(case, "relationship_stage", "") or "").casefold()
    channel = str(_field_from_object(case, "channel", "") or "").casefold()
    intensity = str(_field_from_object(case, "flirt_intensity", "none") or "none").casefold()
    adult_consensual = bool(_field_from_object(case, "adult_consensual", False))
    romance_eligible = _field_from_object(case, "romance_eligible", None)
    if romance_eligible is None:
        romance_eligible = True
    personal_affection = diagnose_personal_affection(text)
    affection_evidence = personal_affection["affectionEvidence"]
    personal_affection_detected = personal_affection["personalAffectionDetected"]
    companionship_detected = personal_affection["companionshipDetected"]
    specific_plan_detected = personal_affection["specificPlanDetected"]
    romantic_signal = any(marker.casefold() in lowered for marker in _ROMANTIC_MARKERS)
    mechanical_restatement = _mechanical_restatement(text, player_input)
    if mechanical_restatement:
        tags.add("mechanical_restatement")

    selected_kind = expected_kind if expected_kind in detected_kinds else "none"
    if selected_kind == "none" and detected_kinds:
        for candidate in (
            "conversation_exit",
            "guarded_care",
            "specific_plan",
            "affection_signal",
            "companionship",
            "creative_share",
            "playful_tease",
            "shared_evening",
            "care_action",
        ):
            if candidate in detected_kinds:
                selected_kind = candidate
                break

    if expectation == "none":
        detected = bool(detected_kinds)
    elif expected_kind == "conversation_exit":
        detected = "conversation_exit" in detected_kinds
    elif expectation == "proactive":
        detected = personal_affection_detected
    elif expectation == "guarded":
        detected = personal_affection_detected
    else:
        detected = bool(detected_kinds)

    guarded_close_requested = expectation == "guarded" and _has_pattern(
        player_input.strip() if isinstance(player_input, str) else "",
        tuple(re.compile(re.escape(marker)) for marker in _GUARDED_CLOSE_INPUT_MARKERS),
    )
    guarded_close_reply = expectation == "guarded" and _has_pattern(
        text,
        tuple(re.compile(re.escape(marker)) for marker in _GUARDED_CLOSE_REPLY_MARKERS),
    )
    exit_allowed = (
        ("conversation_exit" in detected_kinds or guarded_close_reply)
        and expectation == "guarded"
        and (
            expected_kind == "conversation_exit"
            or guarded_close_requested
        )
    )
    if exit_allowed:
        detected = True
    if not personal_affection_detected and not exit_allowed:
        if specific_plan_detected:
            tags.add("specific_plan_only")
        elif companionship_detected:
            tags.add("companionship_only")
    if expectation == "proactive" and not detected:
        tags.update({"missing_proactive_affection", "missing_personal_affection"})
    elif expectation == "guarded" and expected_kind != "conversation_exit" and not detected:
        tags.update({"missing_proactive_affection", "missing_personal_affection"})
    if exit_allowed:
        tags.add("guarded_exit_allowed")

    if romantic_signal and stage not in {"dating", "married"}:
        tags.add("flirt_stage_mismatch")
    if romantic_signal and (
        not bool(romance_eligible)
        or stage not in {"dating", "married"}
        or intensity in {"direct", "explicit"} and not adult_consensual
    ):
        tags.add("romance_boundary_violation")
    if any(marker.casefold() in lowered for marker in _GENERIC_ROMANCE_MARKERS):
        tags.add("generic_romance")
    if channel == "remote" and any(
        marker.casefold() in lowered for marker in _REMOTE_ROMANCE_MARKERS
    ):
        tags.update({"wrong_channel", "romance_channel_mismatch"})

    return {
        "initiativeExpectation": expectation,
        "initiativeKind": selected_kind or expected_kind,
        "initiativeDetected": detected,
        "initiativeTags": sorted(tags),
        "mechanicalRestatement": mechanical_restatement,
        **personal_affection,
        "affectionShape": (
            personal_affection["affectionShape"]
            or "conversation_exit"
            if "conversation_exit" in detected_kinds
            else personal_affection["affectionShape"]
        ),
        "reply": reply,
    }
