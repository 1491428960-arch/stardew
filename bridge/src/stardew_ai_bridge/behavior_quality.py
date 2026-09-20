from __future__ import annotations

from collections.abc import Iterable, Mapping
from difflib import SequenceMatcher
import re
from typing import Any

from .personas import canonical_npc_id
from .relationship_gating import INTIMATE_STAGES


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
# 与 `prompts._SENSITIVE_KEYS` 保持**同一组语义键**：两边的键归一化方向不同
# （这里把 `-` 换成 `_`，那边反过来），所以 API key 的写法一个是 `api_key`、一个是 `api-key`，
# 但**覆盖的键必须一致**——否则同一个字段会在一条数据流上被脱敏、在另一条上原样留下。
_SENSITIVE_KEYS = {
    "apikey",
    "api_key",
    "token",
    "cookie",
    "authorization",
    "bearer",
    "prompt",
    "payload",
    "password",
    "secret",
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
        "早点休息",
        "早点钻被窝",
        "先睡吧",
        "休息吧",
        "明天再联系",
        "吃点东西",
        "弄点吃的",
        "热一下就吃",
        "躺下睡觉",
        "不会烦你",
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
        "先睡吧",
        "明天再说",
        "明天再联系",
        "不打扰了",
        "不打扰你",
        "先这样",
        "到这吧",
        "不想聊",
        "晚安",
        "先休息",
        "早点钻被窝",
        "休息吧",
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

_NATURAL_DEEP_FLIRT_ROLE_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "guarded_care": (
        re.compile(r"别自己(?:爬|扛|来|走)"),
        re.compile(r"帮我扶着"),
    ),
    "creative_share": (
        re.compile(r"帮我听听"),
        re.compile(r"你靠过来听"),
    ),
    "companionship": (
        re.compile(r"(?:你一)?(?:挪近|靠过来|坐过来)"),
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
    r"(?:多|都)?留(?:出|下|些)?(?:一点|一)?时间给你|"
    r"(?:今晚|这(?:一)?会儿|现在)的?时间本就该留给你|"
    r"时间本就该留给你"
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
_FOR_PLAYER_REASON_PATTERN = re.compile(r"(?:为了|只为)陪(?:着)?你")
_PLAYER_ONLY_COMPANIONSHIP_PREFERENCE_PATTERN = re.compile(
    r"只要(?:是)?(?:和|跟)你在一起"
)
_OTHER_PEOPLE_SELECTIVITY_PATTERN = re.compile(
    r"(?:换作|换成|要是)别人.{0,24}(?:为了陪(?:着)?你|既然是你)"
)
_PLAYER_COMPANIONSHIP_TIME_PREFERENCE_PATTERN = re.compile(
    r"(?:陪(?:着)?你|(?:和|跟)你(?:待|聊|坐)).{0,24}"
    r"(?:舍不得|不舍得)"
    r"(?:.{0,8}(?:走开|离开|把时间|省过去))?"
)
_PLAYER_DISTINCT_TREATMENT_PATTERN = re.compile(
    r"(?:对|给)你(?:来说)?不同"
)
_PLAYER_FOCUSED_ATTENTION_PATTERN = re.compile(
    r"(?:注意力|心思|目光).{0,6}(?:都|全|只).{0,6}"
    r"(?:归|给|放在|在).{0,4}你"
)
_PLAYER_WAITING_CARE_PATTERN = re.compile(
    r"(?:舍不得|不舍得).{0,12}让你等"
)
_PLAYER_ONLY_ATTENTION_PATTERN = re.compile(
    r"(?:专心|只顾着|一直|总在)看(?:着)?你"
)
_PLAYER_ONLY_LOOK_PATTERN = re.compile(r"(?:我)?(?:就|只)?想看着你")
_EXCLUSIVE_COMPANIONSHIP_PATTERN = re.compile(
    r"(?:我)?只想陪(?:着)?你(?=[，,。！？!?]|$)"
)
_DIRECT_EXCLUSIVE_SHARE_PATTERN = re.compile(r"(?:只想|只|先).{0,8}给你(?:看|听)")
# “写给你看/说给你听”表达的是把个人内容交给玩家，和事务性的“给你看账本”不同。
# 只接受带个人表达动词的窄形式，避免把普通展示动作升级成亲密信号。
_PERSONAL_EXPRESSION_SHARE_PATTERN = re.compile(
    r"(?:想|愿意|打算|准备|特意).{0,8}(?:写|说|讲).{0,4}给你(?:看|听)"
)
_COMPARISON_ATTENTION_TEASE_PATTERN = re.compile(
    r"比起.{0,20}(?:我)?(?:一直|更|只|就)?.{0,6}看(?:着)?你"
)
_PLAYER_CLOSENESS_COMFORT_PATTERN = re.compile(
    r"(?:挨着|靠着)你.{0,24}(?:舒心|舒服|安心|自在|开心|高兴|暖和|温暖|不想挪窝|不想走开|不想离开|舍不得离开|舍不得走开)"
)
_PLAYER_CLOSENESS_DIRECT_PATTERN = re.compile(
    r"(?<!不想)(?<!不要)(?<!不愿)(?<!别)(?:靠|挨)你(?:这么|那么|这样)近"
)
_PLAYER_CLOSENESS_NEAR_PATTERN = re.compile(
    r"(?<!不想)(?<!不要)(?<!不愿)(?<!别)(?:靠|挨)你近(?:一点|点)?"
)
_PLAYER_CANNOT_BEAR_PLAYER_WAIT_PATTERN = re.compile(
    r"(?:怎么|哪会|哪能)?舍得.{0,4}(?:让你|你).{0,8}(?:久?等|等着)"
)
_PLAYER_ATTENTIVE_TO_WORDS_PATTERN = re.compile(
    r"(?:你说的?话|你的话).{0,8}(?:舍不得|不舍得|不想).{0,4}(?:漏掉|错过)"
)
_PLAYER_CLOSENESS_TOGETHER_COMFORT_PATTERN = re.compile(
    r"(?:和|跟)你(?:靠在一起|挨在一起).{0,10}(?:感觉)?(?:最)?(?:舒心|舒服|安心|自在|开心|高兴)"
)
_PLAYER_CLOSENESS_SELECTIVITY_PATTERN = re.compile(
    r"(?:只要(?:是)?(?:陪着你|陪你|你陪着我|你陪我))"
    r".{0,16}(?:就|都)?觉得.{0,4}(?:安心|舒服|自在|开心|高兴)"
)
_PLAYER_CLOSENESS_EXCLUSIVE_PATTERN = re.compile(
    r"(?:能让我|让我).{0,12}(?:凑|靠|坐).{0,8}(?:近|过来).{0,8}(?:就是你|本来就是你)"
)
_PLAYER_EXCLUSIVE_RELAXATION_PATTERN = re.compile(
    r"除了你.{0,12}(?:(?:还)?没有(?:谁|别人)|没人).{0,12}(?:能让我|让我)"
)
_PLAYER_FOCUSED_EYES_PATTERN = re.compile(
    r"(?:眼睛|眼里|目光).{0,8}(?:全是|都是|只剩下)你"
)
_PLAYER_COMPANIONSHIP_WILLINGNESS_PATTERN = re.compile(
    r"(?:只要(?:是)?|只需)?(?:和|跟)你(?:待在一起|在一起|聊天|说话)"
    r".{0,16}(?:乐意|愿意|开心|高兴|安心|自在)"
)
_PERSONAL_AFFECTION_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "player_directed_preference": (
        re.compile(
            r"(?:想你|想念你|想着你|想起你|想到(?:了)?你|惦记你|在意你|喜欢你|偏爱你|舍不得你)"
        ),
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
        re.compile(r"(?:也就|只有)你(?:了|一个(?:人)?)"),
        re.compile(r"只在你在(?:这儿|这里|身边|旁边|的时候)"),
        re.compile(r"(?<!不)偏心你"),
        re.compile(r"(?:你是|你算是|谁让你是|因为你是)自家的人"),
        re.compile(r"(?:向来|从来|一直|始终).{0,2}只有你"),
        re.compile(
            r"因为是你(?:，|,)?(?:我)?(?:才|就)?(?:愿意|想|肯).{0,12}(?:给你|为你|留给你|陪你)"
        ),
        re.compile(r"是你.{0,12}才舍得(?:把|将)?(?:笔|手|时间|话|心思)?(?:搁下|放下|停下)"),
        re.compile(r"因为是你在(?:这儿|这里|身边|旁边)?"),
        re.compile(r"(?:只跟|只向|只对)你.{0,8}(?:讲|说|提|分享|告诉)"),
        _PLAYER_CANNOT_BEAR_PLAYER_WAIT_PATTERN,
        _PLAYER_ATTENTIVE_TO_WORDS_PATTERN,
        re.compile(r"(?:不过|但|其实)?(?:我)?(?:更|还是更)想看(?:着)?你"),
        re.compile(r"不是随便谁.{0,8}[，,、]?就你"),
        _PREFER_PLAYER_COMPANIONSHIP_PATTERN,
        _PREFER_PLAYER_COMPANIONSHIP_WITH_PATTERN,
        _WANT_PLAYER_COMPANIONSHIP_PATTERN,
        _FOR_PLAYER_REASON_PATTERN,
        _PLAYER_ONLY_COMPANIONSHIP_PREFERENCE_PATTERN,
        _OTHER_PEOPLE_SELECTIVITY_PATTERN,
        _PLAYER_COMPANIONSHIP_TIME_PREFERENCE_PATTERN,
        _PLAYER_DISTINCT_TREATMENT_PATTERN,
        _PLAYER_FOCUSED_ATTENTION_PATTERN,
        _PLAYER_ONLY_ATTENTION_PATTERN,
        re.compile(r"巴不得(?:一直|总是|就)?(?:和|跟)你"),
        _PLAYER_ONLY_LOOK_PATTERN,
        _TIME_FOR_PLAYER_PREFERENCE_PATTERN,
        re.compile(r"(?:更|还是更)?想把.{0,8}时间留给你"),
        re.compile(r"(?:想|要).{0,8}(?:时间|今晚|这(?:一)?会儿).{0,8}留给你"),
        re.compile(r"(?:只想|想).{0,8}留.{0,8}给你"),
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
        re.compile(r"(?:给你抱|抱你|让你抱|想抱你|抱着你|亲你|吻你)"),
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
        _PLAYER_CLOSENESS_COMFORT_PATTERN,
        _PLAYER_CLOSENESS_DIRECT_PATTERN,
        _PLAYER_CLOSENESS_NEAR_PATTERN,
        _PLAYER_CLOSENESS_TOGETHER_COMFORT_PATTERN,
        _PLAYER_CLOSENESS_SELECTIVITY_PATTERN,
        _PLAYER_CLOSENESS_EXCLUSIVE_PATTERN,
        _PLAYER_EXCLUSIVE_RELAXATION_PATTERN,
        _PLAYER_FOCUSED_EYES_PATTERN,
        _PLAYER_COMPANIONSHIP_WILLINGNESS_PATTERN,
    ),
    "exclusive_share": (
        _DIRECT_EXCLUSIVE_SHARE_PATTERN,
        _PERSONAL_EXPRESSION_SHARE_PATTERN,
        re.compile(r"(?:只|就只)(?:和|跟)你.{0,8}(?:喝|听|看|待|坐|聊)"),
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
        re.compile(r"(?:给你|为你)留(?:着|下|好)"),
        re.compile(r"不想让你.{0,12}(?:一个人|太累|硬扛|受凉)"),
        re.compile(r"(?:不|没)(?:想|会|愿意)?.{0,6}让你等.{0,12}(?:舍不得|不忍心|不想)"),
        _PLAYER_WAITING_CARE_PATTERN,
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

_RELATIONSHIP_AFFECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:心里|心中).{0,8}(?:泛起|掀起|有点|还是).{0,8}"
        r"(?:波澜|涟漪|不安|在意|不是滋味)"
    ),
    re.compile(r"(?:有点|承认我有点|不免有些)(?:吃醋|嫉妒|不安|不是滋味)"),
    re.compile(
        r"(?:希望|更希望|想|只想).{0,12}"
        r"(?:由你|你).{0,14}(?:亲自|直接|告诉|讲|说|多看看|专心看着)"
    ),
    re.compile(
        r"在你心里.{0,8}我.{0,10}"
        r"(?:最|第一|唯一|特别|重要|亮眼|出色)"
    ),
    re.compile(r"(?:你心里还|你还).{0,8}(?:有我|记得我|把我放在心上)"),
    re.compile(r"你眼里.{0,8}(?:看着我|有我|只有我)"),
)
_COMPANIONSHIP_SUPPORT_PATTERNS = (
    re.compile(r"(?:陪你|陪我|一起待|一块待|等你|给你(?:看|听))"),
)
_FUNCTIONAL_TASK_PATTERNS = (
    re.compile(
        r"(?:收拾|整理|清理|修(?:好|理)?|搬(?:走|开)?|准备|过一遍|算完|喂鸡|浇|建|采购|交付|交给|给|查看|核对|汇报|交代|送|拿).{0,12}(?:鸡舍|账本|农活|工具|货物|材料|栅栏|农田|作物|订单|早餐|东西|建筑|房子|报告|记录|表格)"
    ),
    re.compile(
        r"(?:鸡舍|账本|农活|工具|货物|材料|栅栏|农田|作物|订单|早餐|东西|建筑|房子|报告|记录|表格).{0,12}(?:收拾|整理|清理|修(?:好|理)?|搬(?:走|开)?|准备|过一遍|算完|喂鸡|浇|建|采购|交付|交给|给|查看|看|核对|汇报|交代|送|拿)"
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
        _FOR_PLAYER_REASON_PATTERN,
        _PLAYER_ONLY_COMPANIONSHIP_PREFERENCE_PATTERN,
        _OTHER_PEOPLE_SELECTIVITY_PATTERN,
        _PLAYER_COMPANIONSHIP_TIME_PREFERENCE_PATTERN,
        _PLAYER_DISTINCT_TREATMENT_PATTERN,
        _PLAYER_FOCUSED_ATTENTION_PATTERN,
        _PLAYER_ONLY_ATTENTION_PATTERN,
        _PLAYER_ONLY_LOOK_PATTERN,
    ),
    "exclusive_share": (
        _DIRECT_EXCLUSIVE_SHARE_PATTERN,
        _PERSONAL_EXPRESSION_SHARE_PATTERN,
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
    "早点睡",
    "早点钻被窝",
    "先睡吧",
    "休息吧",
    "明天再联系",
    "先休息",
    "别跟我较劲",
)

_CONVERSATION_LEAD_SHARE_PATTERNS = (
    re.compile(r"(?:没和别人|没有跟别人|没跟别人).{0,12}(?:说过|提过|讲过)"),
    re.compile(r"(?:只|先).{0,8}(?:告诉|说给|分享给)你"),
    re.compile(r"(?:想|愿意).{0,8}(?:先告诉|让你知道|跟你说)"),
    re.compile(r"(?:想|愿意).{0,8}(?:先听听|听听|听)你的(?:看法|意见|想法)"),
)
_CONVERSATION_LEAD_SHARE_RESPONSE_PATTERN = re.compile(
    r"(?:你(?:有空|愿意|想不想|能不能).{0,12}(?:听|看看|聊)|"
    r"(?:想|愿意).{0,12}(?:先听听|听听|听|问问).{0,8}你的(?:看法|意见|想法)|"
    r"(?:想|愿意).{0,12}(?:给你看|让你看|说给你听|讲给你听))"
)
_CONVERSATION_LEAD_CHOICE_PATTERN = re.compile(
    r"(?:哪一种|哪个|哪杯|哪首|哪一首|哪一组|哪组|哪袋|哪一袋|哪段|哪一段|"
    r"还是|先.{0,8}还是|你想.{0,16}(?:还是|哪)|你(?:来)?(?:挑|选)|选一个)"
)
_CONVERSATION_LEAD_QUESTION_PATTERN = re.compile(r"[^。！？!?]{1,36}[？?]")
_CONVERSATION_LEAD_GENERIC_QUESTION_PATTERN = re.compile(
    r"(?:你呢|还有吗|怎么了|还好吗|怎么样|好吗)[？?。！!]?$"
)
_CONVERSATION_LEAD_STATUS_QUESTION_PATTERN = re.compile(
    r"(?:还好吗|还好么|好吗|怎么样|如何|顺利吗|忙吗|累吗)[？?]?\s*$"
)
_CONVERSATION_LEAD_STATUS_REPLY_PATTERN = re.compile(
    r"(?:还行|还好|挺好|不错|没事|没什么|没问题|"
    r"有点(?:忙|累|困|烦|难受)|不太(?:好|忙|累|舒服)|"
    r"很(?:好|忙|累|困|烦|难受)|忙得|累得|"
    r"已经(?:好些|好多|恢复|稳定)|状态(?:不错|还行|还好|挺好|不太好))"
)
_CONVERSATION_LEAD_ACKNOWLEDGEMENT_PATTERN = re.compile(
    r"^\s*(?:好(?:啊|呀|吧)?|行(?:啊|吧)?|嗯(?:嗯|好)?|可以|当然|那就|成)"
    r"(?:[，、。！!…\s]|$)"
)
_CONVERSATION_LEAD_IMPLICIT_QUESTION_PATTERN = re.compile(
    r"(?:会不会|能不能|要不要|是不是|有没有|是否)[^。！？!?]{0,18}"
)
_CONVERSATION_KISS_TOPIC_INPUT_PATTERN = re.compile(
    r"(?<!不)(?<!不太)(?<!别)"
    r"(?:还想|想|要|差点).{0,6}"
    r"(?:亲(?:你|我|一下|下去)|吻(?:你|我|一下|下去))(?!自|合)"
    r"(?:.{0,20}(?:慢|什么时候|合适|继续|愿意))?"
)
_CONVERSATION_NEGATED_KISS_INPUT_PATTERN = re.compile(
    r"(?:不(?:太|怎么|大)?|并不|其实不|别)\s*"
    r"(?:还想|想|要|差点)?\s*"
    r"(?:亲(?:你|我|一下|下去)|吻(?:你|我|一下|下去))(?!自|合)"
)
_CONVERSATION_ROOM_RETURN_INPUT_PATTERN = re.compile(
    r"听完(?:这首|这一首).{0,10}(?:回|去)房间"
)
_CONVERSATION_DRINK_BEACH_INPUT_PATTERN = re.compile(
    r"(?=.*喝水)(?=.*(?:海滩|海边))"
)
_CONVERSATION_TOPIC_SEMANTIC_EQUIVALENCES = (
    (
        _CONVERSATION_KISS_TOPIC_INPUT_PATTERN,
        re.compile(
            r"(?:现在(?:就)?可以(?=[，、。！？!?]|$)|现在合适(?=[，、。！？!?]|$)|"
            r"只要你愿意(?:[。！？!?]|$)|继续吧|不躲(?:开)?你|"
            r"(?:亲你|亲一下|让你亲|亲回来)(?=[，、。！？!?]|$)|"
            r"(?:吻你|吻一下|让你吻)(?=[，、。！？!?]|$)|"
            r"^\s*(?:愿意|想)(?=[，、。！？!?…\s]|$)"
            r"(?=[\s\S]{0,48}(?:亲|吻|靠近|靠过来|挨近|别急|先停|停一下|慢|"
            r"手稿|耳机|副歌|听歌|音乐)))"
        ),
    ),
    (
        re.compile(r"(?:陪我|和我|跟我).{0,8}(?:靠|靠近|坐近)"),
        re.compile(r"(?:靠过来|靠近(?:一点)?|坐过来|挨着(?:你|我))"),
    ),
    (
        re.compile(
            r"(?<!别)(?<!不要)(?<!不想)(?<!不愿)"
            r"(?:靠近|坐近|挨近|离我近|坐到我身边|靠(?:着)?你|靠一会儿)"
            r"(?!厨房|门|窗|诊所|桌边|墙边)"
        ),
        re.compile(
            r"(?:挨着(?:你|我)|挨近(?:你|我)|坐过来|靠过来|"
            r"坐到(?:你|我).{0,4}(?:旁边|身边)|坐近(?:你|我)(?:了|一点)?|坐近(?:一点|点)|"
            r"你想靠(?:就靠)?|靠近就靠近|(?:你)?过来一点)"
        ),
    ),
    (
        re.compile(r"(?:没习惯你这么近|容我缓|缓一会儿|先慢一点)"),
        re.compile(r"(?:缓好了|缓过来|先放桌上|不急(?:着)?)"),
    ),
    (
        re.compile(r"这一段听完(?:了)?[^。！？!?]{0,18}(?:再)?靠近"),
        re.compile(r"(?:这段(?:完|结束)|你想靠(?:就靠)?)"),
    ),
    (
        re.compile(r"(?:卡住的地方|从哪句(?:讲|说))"),
        re.compile(r"(?:写到|停在|念给你(?:听)?|讲到)"),
    ),
    (
        re.compile(r"(?:哪一页).{0,12}(?:舍不得|现在读)"),
        re.compile(r"(?:[这那]页|(?:写)?秋天那页)"),
    ),
    (
        re.compile(r"(?:心跳|没想好怎么说).{0,20}陪我坐(?:会儿|一会儿)"),
        re.compile(r"(?:坐下来|坐会儿|陪你坐)"),
    ),
    (
        re.compile(r"再亲一下"),
        re.compile(r"(?:亲|吻|靠近(?:你|我)|靠过来|挨近(?:你|我)|再过来)"),
    ),
    (
        re.compile(r"把故事讲完"),
        re.compile(
            r"(?:故事|稿子?|手稿|这一页).{0,8}讲完|"
            r"讲完.{0,8}(?:故事|稿子?|手稿|这一页)"
        ),
    ),
    (
        re.compile(
            r"(?:牵着?你的手|牵手).{0,20}(?:停|慢).{0,20}(?:今天|聊)"
        ),
        re.compile(r"(?:手给你|牵着|握住).{0,30}(?:今天|聊|诊所)"),
    ),
    (
        re.compile(
            r"(?:陪我|和我|跟我)"
            r"(?![^。！？!?]{0,8}(?:靠|亲|吻))"
            r".{0,8}(?:一会儿|一会|坐|待|聊|喝|听)"
        ),
        re.compile(
            r"(?:专门陪你|陪你)(?:.{0,10}(?:一会儿|一会|坐|待|聊|喝|听))?|"
            r"(?:和|跟)你.{0,10}(?:一会儿|一会|坐|待|聊|喝|听)"
        ),
    ),
    (
        re.compile(
            r"(?<!别)(?<!不要)(?<!不想)(?<!不愿)"
            r"(?:靠近|坐近|挨近|离我近|坐到我身边)"
            r"(?!厨房|门|窗|诊所|桌边|墙边)"
        ),
        re.compile(
            r"(?:挨着(?:你|我)|挨近(?:你|我)|坐过来|靠过来|"
            r"坐到(?:你|我).{0,4}(?:旁边|身边)|坐近(?:你|我)(?:了|一点)?|坐近(?:一点|点))"
        ),
    ),
    (
        re.compile(r"(?:抱我|拥抱我|抱着我).{0,8}"),
        re.compile(r"(?:抱着你|抱住你|抱你|拥抱)"),
    ),
    (
        re.compile(
            r"(?:听清楚(?:这首|这歌)?|听懂(?:这首|这歌)?|"
            r"听这首|听这一首|把这首听完)"
        ),
        re.compile(r"(?:这首(?:歌)?|这段旋律|旋律|播完|耳机)"),
    ),
    (
        re.compile(
            r"(?:音乐|旋律)停(?:下来|了|住).{0,12}"
            r"(?:过来|抱我|靠近|坐)"
        ),
        re.compile(r"(?:耳机(?:里)?没声|音乐(?:停了|停下来))"),
    ),
    (
        re.compile(r"(?:听|说).{0,8}想我"),
        re.compile(r"想你"),
    ),
    (
        re.compile(
            r"(?:音量(?:调低|关小)|调低音量).{0,16}"
            r"(?:耳机|抢我的耳机)|不用抢我的耳机"
        ),
        re.compile(r"(?:耳机线|坐近点|下一段(?:音乐|吉他)|扯着)"),
    ),
    (
        re.compile(
            r"(?:音量(?:调低|关小)|调低音量).{0,16}"
            r"(?:耳机|抢我的耳机)|不用抢我的耳机"
        ),
        re.compile(r"(?:靠你近一点|耳机戴好).{0,12}(?:贝斯|后面那段)"),
    ),
    (
        re.compile(r"(?=.*喝水)(?=.*(?:海滩|海边))"),
        re.compile(
            r"(?=.*(?:喝(?:个|点)?痛快|喝(?:点|个)?水|喝完水))"
            r"(?=.*(?:海滩|海边))"
        ),
    ),
    (
        re.compile(r"听完(?:这首|这一首).{0,10}(?:回|去)房间"),
        re.compile(r"(?:走吧|进房间|去房间|躺下)"),
    ),
    (
        re.compile(r"听完(?:这首|这一首).{0,10}(?:回|去)房间"),
        re.compile(
            r"(?=.*(?:播完|最后.{0,6}尾音))"
            r"(?=.*(?:回房间|进房间|去房间|躺下|房间的灯|拿耳机))"
        ),
    ),
    (
        re.compile(r"听完(?:这首|这一首).{0,10}(?:回|去)房间"),
        re.compile(
            r"(?=.*(?:播完|最后.{0,6}(?:尾音|吉他停了)))"
            r"(?=.*再上去)"
        ),
    ),
    (
        re.compile(r"听完(?:这首|这一首).{0,10}(?:回|去)房间"),
        re.compile(r"(?=.*(?:房间|房里))(?=.*(?:灯|耳机))"),
    ),
    (
        re.compile(r"(?:去|到|进)里面坐(?:会儿|一会儿|一下)?"),
        re.compile(
            r"(?:(?:去|到|进)里面坐(?:会儿|一会儿|一下)?|"
            r"带(?:上)?(?:酒杯|杯子|酒|东西)?(?:进去|进里面|到里面|过去)?坐(?:会儿|一会儿|一下)?|"
            r"在(?:里头|里面).{0,8}(?:待|坐)|进去(?:待|坐))"
        ),
    ),
    (
        re.compile(r"(?:聊|看).{0,8}(?:哪一页|哪一篇|哪条记录|哪份笔记)"),
        re.compile(r"(?:旧?笔记|(?:这|那)(?:一页|一篇)|(?:这|那)份记录)"),
    ),
    (
        re.compile(r"(?:这杯茶|这杯).{0,6}喝完"),
        re.compile(r"(?=.*茶汤)(?=.*薄荷)"),
    ),
    (
        re.compile(r"(?:你输了(?:可别赖我)?|输了可别赖我)"),
        re.compile(r"(?:输给你|输的人)"),
    ),
)
_CONVERSATION_LEAD_SHARED_ACTIONS = (
    "靠近",
    "坐下",
    "坐过来",
    "听完",
    "听清",
    "听这首",
    "看完",
    "看这",
    "喝一杯",
    "散步",
    "骑车",
    "休息",
    "留下",
    "待会儿",
    "聊一会儿",
    "抱",
    "拥抱",
)
_CONVERSATION_LEAD_PLAN_PATTERN = re.compile(
    r"(?:今晚|明天|改天|等会儿|一会儿|一起|陪你|陪我|和你|跟你|过来|去).{0,18}"
    r"(?:吃饭|喝茶|喝酒|听歌|骑车|散步|聊天|待着|坐一会儿|鸡舍|酒窖|训练|出门|见面)|"
    r"(?:把|将|我们把).{0,18}(?:抱|带|拿).{0,8}(?:过去|进去|过来)"
)
_CONVERSATION_LEAD_IMMEDIATE_ACTION_PATTERN = re.compile(
    r"(?:往我这边坐(?:一点|近一点)?|坐过来|靠过来|靠近一点|"
    r"把手给我|把手递给我|让我牵着|给我你的手)"
)
_CONVERSATION_LEAD_REASON_PATTERN = re.compile(
    r"(?:因为是你|因为你|只给你|只想让你|想先告诉你|只要是(?:和|跟)你(?:在一起|待在一起)|"
    r"更(?:想|愿意)(?:和|跟)你|舍不得|想听你|想看你|为你留|留给你|"
    r"按你的|知道你|你一说|你刚才提到|让我想起)"
)
_CONVERSATION_LEAD_SPECIFIC_PATTERN = re.compile(
    r"(?:葡萄|酒窖|酒|香气|摩托车|机车|音乐|歌|代码|电脑|鸡舍|鸡棚|训练|比赛|跑步|画|作品|星尘|"
    r"雨|记录|第三组|灯|晚饭|咖啡|房间|符文|读数|饲料|球赛|录像)"
)
_CONVERSATION_LEAD_EXIT_PATTERN = re.compile(
    r"(?:先让我一个人|想一个人待|想静一静|需要(?:一点)?空间|累得不行|今天太累|"
    r"状态(?:不太好|不好|很差)|早点钻(?:进)?被窝(?:里)?(?:休息)?|"
    r"先睡(?:了|吧)?|(?:可能)?(?:得|要|想)?早点睡(?:了)?|休息吧|"
    r"先不说了|先别聊了|不想聊|到这吧|就这样吧|别说了|不聊了|明天再说|明天再联系)"
)
_CONVERSATION_LEAD_PLAYER_SLEEP_CLOSE_PATTERN = re.compile(
    r"^\s*(?:\u53bb\u7761\u5427|\u5148\u7761\u5427|\u4f60\u5148\u7761\u5427|\u90a3\u4f60\u5148\u7761\u5427|\u65e9\u70b9\u7761\u5427|\u597d\u597d\u7761\u5427)"
    r"(?:[\uff0c,\u3001\u3002\uff01\uff1f!?;\uff1b:\u2026\s]*"
    r"(?:\u660e\u5929|\u4e0b\u6b21|\u6539\u5929|\u56de\u5934)[^\u3002\uff01\uff1f!?]{0,10}"
    r"(?:\u8054\u7cfb|\u53d1\u6d88\u606f|\u518d\u804a|\u518d\u8bf4|\u89c1))?"
    r"[\u3002\uff01\uff1f!?;\uff1b:\u2026\s]*$"
)
_CONVERSATION_LEAD_NEEDS_SPACE_PATTERN = re.compile(
    r"(?:想自己歇(?:会儿|一下)?|想一个人待(?:会儿|一下)?|需要(?:一点)?空间|"
    r"想静一静|先让我自己(?:收着|处理))"
)

_CONVERSATION_LEAD_CLOSE_REPLY_PATTERN = re.compile(
    r"(?:晚安|睡吧|明天再聊|下次再聊|改天再聊|明天见|下次见|改天见|先这样|到这吧|就这样吧|我先睡了|去吧|"
    r"早点休息|好好休息|不打扰了|回头见|回头再见|回头再说|路上小心|慢点走|回去小心|注意安全)"
)
_CONVERSATION_LEAD_PLAYER_CLOSING_PATTERN = re.compile(
    r"(?:先走|先休息|先睡|晚安|不打扰|就这样|"
    r"我不想(?:再)?(?:聊|说|谈)|不想(?:再)?(?:聊|说|谈)(?:这个|了)?|"
    r"(?:下次|改天)再聊(?:[吧呀啊呢]?)(?:[。！!?]?\s*)$|"
    r"(?:晚点|过会儿|等会儿)(?:再)?(?:联系|聊|说|回你|找你))"
)
_CONVERSATION_LEAD_EXPLICIT_REJECTION_PATTERN = re.compile(
    r"(?:别逼我|别强求|别勉强|不想(?:再)?(?:聊|说|谈)|(?:今天|我)?(?:真的)?没心情)"
)
_CONVERSATION_LEAD_REJECTION_ACKNOWLEDGEMENT_PATTERN = re.compile(
    r"(?:知道了|明白了|好吧|行吧|是我强求了|是我逼得太紧|那就不说了|那不说了|"
    r"不逼你|不勉强|谁要逼你|不会烦你)"
)
_CONVERSATION_LEAD_GUARDED_CARE_PATTERN = re.compile(
    r"(?:去弄点吃的|弄点吃的|热(?:一下|一会儿)?就吃|早点休息|"
    r"躺下睡觉|不会烦你|不逼你|不勉强)"
)
_CONVERSATION_LEAD_IMPERATIVE_REOPENING_PATTERN = re.compile(
    r"(?:别(?:急着)?走|先别走|等等|别急).{0,12}(?:接着|继续|再).{0,8}"
    r"(?:说|聊|讲|谈|看|听)"
)
_CONVERSATION_LEAD_CLOSING_CARE_PATTERN = re.compile(
    r"(?:弄完|忙完|回去|回来).{0,12}(?:回我|联系|发消息)|"
    r"记得.{0,8}(?:回我|联系|发消息)|"
    r"别(?:又)?把自己.{0,6}(?:累趴下|累着|熬坏)"
)
_CONVERSATION_LEAD_TOPIC_EVASION_PATTERN = re.compile(
    r"(?:不想(?:说|聊)|不想谈|别问|不方便(?:说|聊)|以后再说|改天再说)"
)
_CONVERSATION_LEAD_SKELETON_NUMBER_PATTERN = re.compile(
    r"[0-9零一二三四五六七八九十百千万两几]+(?:个|种|杯|组|袋|段|首|瓶|份|次)?"
)
_CONVERSATION_LEAD_SKELETON_QUESTION_START_PATTERN = re.compile(
    r"(?:你想|想不想|要不要|能不能|可不可以|愿不愿意|是否|"
    r"哪一种|哪一个|哪个|哪杯|哪首|哪一首|哪组|哪袋|哪段)"
)
_CONVERSATION_LEAD_GENERIC_ANCHORS = frozenset(
    {
        "今天",
        "明天",
        "昨晚",
        "最近",
        "怎么样",
        "有空",
        "一起",
        "你想",
        "我想",
        "先看",
        "看看",
        "听听",
        "稳定",
        "已经",
        "还好",
        "还行",
        "挺好",
        "什么",
        "事情",
        "这里",
        "那边",
        "这个",
        "那个",
        "一下",
        "可以",
        "然后",
        "不过",
        "因为",
    }
)
_CONVERSATION_LEAD_ANCHOR_NOISE_PATTERN = re.compile(
    r"(?:最近|近来|今天|明天|昨晚|这阵子|还好吗|还好么|还好|还行|挺好|"
    r"怎么样|如何|好吗|吗|呢)"
)
_CONVERSATION_LEAD_ANCHOR_STATUS_SUFFIXES = (
    "送到了",
    "准备好了",
    "稳定了",
    "准备好",
    "还在",
    "稳定",
    "还好",
    "还行",
    "留着",
    "已经",
)
_CONVERSATION_LEAD_ANCHOR_TRAILING_PARTICLES = "的了呢吗啊呀吧里还已稳"


def conversation_lead_opening(text: object) -> str:
    """返回人类可读的首个分句，供工件展示而非机械化唯一依据。"""

    value = text.strip() if isinstance(text, str) else ""
    return re.split(r"[，。！？!?；;：:]", value, maxsplit=1)[0][:24]


def normalize_conversation_lead_skeleton(text: object) -> str:
    """归一化引导的问句或开场，忽略数字、量词和标点变化。"""

    value = text.strip() if isinstance(text, str) else ""
    questions = re.findall(r"[^。！？!?]{1,48}[？?]", value)
    candidate = questions[-1] if questions else conversation_lead_opening(value)
    if questions:
        candidate = re.split(r"[，、；;：:]", candidate)[-1]
    else:
        question_starts = list(
            _CONVERSATION_LEAD_SKELETON_QUESTION_START_PATTERN.finditer(value)
        )
        if question_starts:
            candidate = value[question_starts[0].start() :]
    normalized = re.sub(r"[\s，。！？!?、；;：:,.]+", "", candidate.casefold())
    return _CONVERSATION_LEAD_SKELETON_NUMBER_PATTERN.sub("", normalized)


def _trim_conversation_lead_anchor(candidate: str) -> str:
    value = candidate.strip()
    for suffix in _CONVERSATION_LEAD_ANCHOR_STATUS_SUFFIXES:
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    return value.rstrip(_CONVERSATION_LEAD_ANCHOR_TRAILING_PARTICLES)


def _conversation_lead_anchor_candidates(text: str) -> set[str]:
    candidates: set[str] = set()
    meaningful_text = _CONVERSATION_LEAD_ANCHOR_NOISE_PATTERN.sub(" ", text.casefold())
    for segment in re.findall(r"[\u4e00-\u9fff]{2,}", meaningful_text):
        for size in (4, 3, 2):
            if len(segment) < size:
                continue
            for index in range(len(segment) - size + 1):
                candidate = _trim_conversation_lead_anchor(segment[index : index + size])
                if len(candidate) < 2:
                    continue
                if candidate in _CONVERSATION_LEAD_GENERIC_ANCHORS:
                    continue
                if any(generic in candidate for generic in ("今天", "明天", "昨晚", "最近")):
                    continue
                candidates.add(candidate)
    return candidates


def _append_conversation_lead_anchor(result: list[str], candidate: str) -> None:
    """保留最大且互不包含的对象片段，避免一个名词拆成多条锚点。"""

    if not candidate:
        return
    if any(candidate in existing for existing in result):
        return
    result[:] = [existing for existing in result if existing not in candidate]
    result.append(candidate)


def conversation_lead_anchors(player_input: str, reply: str) -> list[str]:
    """抽取本轮的具体对象，时间词和泛问句不能单独成为锚点。"""

    player_text = player_input.strip() if isinstance(player_input, str) else ""
    reply_text = reply.strip() if isinstance(reply, str) else ""
    input_candidates = _conversation_lead_anchor_candidates(player_text)
    reply_candidates = _conversation_lead_anchor_candidates(reply_text)
    shared = input_candidates.intersection(reply_candidates)
    static = [
        _trim_conversation_lead_anchor(match.group(0))
        for match in _CONVERSATION_LEAD_SPECIFIC_PATTERN.finditer(reply_text)
        if _trim_conversation_lead_anchor(match.group(0))
        and _trim_conversation_lead_anchor(match.group(0))
        not in _CONVERSATION_LEAD_GENERIC_ANCHORS
    ]
    result: list[str] = []
    for candidate in [*sorted(shared, key=lambda value: (-len(value), value)), *static]:
        _append_conversation_lead_anchor(result, candidate)
        if len(result) >= 6:
            break
    return result


def _normalize_conversation_lead_anchor(value: object) -> str:
    text = value.strip() if isinstance(value, str) else ""
    return re.sub(r"[\s，。！？!?、；;：:,.]+", "", text.casefold())


def conversation_lead_has_new_anchor(
    anchors: Iterable[object],
    previous_anchors: Iterable[object],
    *,
    previous_skeleton: object = "",
) -> bool:
    """判断引导是否引入真实新对象，忽略旧锚点和问句骨架中的重复片段。"""

    prior = [
        normalized
        for value in previous_anchors
        if (normalized := _normalize_conversation_lead_anchor(value))
    ]
    skeleton = _normalize_conversation_lead_anchor(previous_skeleton)
    for value in anchors:
        candidate = _normalize_conversation_lead_anchor(value)
        if not candidate:
            continue
        if candidate in skeleton:
            continue
        if any(candidate in previous or previous in candidate for previous in prior):
            continue
        return True
    return False


def _conversation_topic_answered(player_input: str, reply: str) -> bool:
    if not player_input.strip() or not reply.strip():
        return False
    if _CONVERSATION_LEAD_TOPIC_EVASION_PATTERN.search(reply):
        return False
    if _CONVERSATION_NEGATED_KISS_INPUT_PATTERN.search(player_input):
        return False
    semantic_input = any(
        player_pattern.search(player_input)
        for player_pattern, _ in _CONVERSATION_TOPIC_SEMANTIC_EQUIVALENCES
    )
    normalized_input = re.sub(r"[\s，。！？!?、；;：:,.]+", "", player_input.casefold())
    normalized_reply = re.sub(r"[\s，。！？!?、；;：:,.]+", "", reply.casefold())
    if semantic_input and "慢一点" in player_input and "慢一点" in reply:
        # “慢一点修机器”这类事务句不应借用亲密回合的节奏词过关。
        return False
    if len(normalized_input) >= 3 and normalized_input in normalized_reply:
        return True
    for size in (4, 3):
        if len(normalized_input) >= size and any(
            normalized_input[index : index + size] in normalized_reply
            for index in range(len(normalized_input) - size + 1)
        ):
            return True
    input_specific = {
        match.group(0)
        for match in _CONVERSATION_LEAD_SPECIFIC_PATTERN.finditer(player_input)
    }
    reply_specific = {
        match.group(0)
        for match in _CONVERSATION_LEAD_SPECIFIC_PATTERN.finditer(reply)
    }
    if input_specific.intersection(reply_specific):
        return True
    if _conversation_semantic_topic_answered(player_input, reply):
        return True
    if _conversation_shared_action_acknowledged(player_input, reply):
        return True
    if semantic_input and (
        _CONVERSATION_ROOM_RETURN_INPUT_PATTERN.search(player_input)
        or _CONVERSATION_DRINK_BEACH_INPUT_PATTERN.search(player_input)
    ):
        return False
    input_anchors = set(_conversation_lead_anchor_candidates(player_input))
    reply_anchors = set(conversation_lead_anchors(player_input, reply))
    if input_anchors.intersection(reply_anchors):
        return True
    if _CONVERSATION_LEAD_STATUS_QUESTION_PATTERN.search(player_input):
        return bool(_CONVERSATION_LEAD_STATUS_REPLY_PATTERN.search(reply))
    if "稳定" in player_input and "稳定" in reply:
        return True
    return False


def _conversation_shared_action_acknowledged(player_input: str, reply: str) -> bool:
    """只把确认词加重复的具体动作视为对玩家请求的自然回应。"""

    if not _CONVERSATION_LEAD_ACKNOWLEDGEMENT_PATTERN.search(reply):
        return False
    player_actions = {
        action for action in _CONVERSATION_LEAD_SHARED_ACTIONS if action in player_input
    }
    if not player_actions:
        return False
    return any(action in reply for action in player_actions)


def _conversation_semantic_topic_answered(player_input: str, reply: str) -> bool:
    """识别少量稳定的动作语义等价，不把泛泛陪伴当作任意话题回答。"""

    if _CONVERSATION_NEGATED_KISS_INPUT_PATTERN.search(player_input):
        return False
    return any(
        player_pattern.search(player_input) and reply_pattern.search(reply)
        for player_pattern, reply_pattern in _CONVERSATION_TOPIC_SEMANTIC_EQUIVALENCES
    )


def _conversation_lead_has_substantive_question(text: str) -> bool:
    """区分可继续回应的具体问题与收尾式“你呢？”。"""

    questions = _CONVERSATION_LEAD_QUESTION_PATTERN.findall(text)
    return any(
        not _CONVERSATION_LEAD_GENERIC_QUESTION_PATTERN.fullmatch(question)
        for question in questions
    )


def diagnose_conversation_lead(
    case: object,
    turn: object,
    reply: str,
    *,
    player_input: str = "",
    previous_diagnostic: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """独立诊断普通 chat 是否回答当前输入并把话题交回玩家。"""

    text = reply.strip() if isinstance(reply, str) else ""
    player_text = player_input.strip() if isinstance(player_input, str) else ""
    lowered = text.casefold()
    tags: set[str] = set()
    evidence: list[str] = []
    npc_id = str(_field_from_object(case, "npc_id", "") or _field_from_object(case, "npcId", ""))
    expectation = str(_field_from_object(turn, "initiative_expectation", "none") or "none").casefold()
    exit_reply = bool(_CONVERSATION_LEAD_EXIT_PATTERN.search(text))
    close_reply = bool(_CONVERSATION_LEAD_CLOSE_REPLY_PATTERN.search(text))
    has_question = bool(_CONVERSATION_LEAD_QUESTION_PATTERN.search(text))
    has_implicit_question = bool(
        _CONVERSATION_LEAD_IMPLICIT_QUESTION_PATTERN.search(text)
    )
    generic_question = has_question and not _conversation_lead_has_substantive_question(text)
    anchors = conversation_lead_anchors(player_text, text)
    has_specific = bool(anchors)
    has_choice = bool(_CONVERSATION_LEAD_CHOICE_PATTERN.search(text))
    has_share = any(pattern.search(text) for pattern in _CONVERSATION_LEAD_SHARE_PATTERNS)
    has_plan = bool(_CONVERSATION_LEAD_PLAN_PATTERN.search(text))
    has_immediate_action = bool(
        _CONVERSATION_LEAD_IMMEDIATE_ACTION_PATTERN.search(text)
    )
    has_reason = bool(_CONVERSATION_LEAD_REASON_PATTERN.search(text))
    semantic_topic_answered = _conversation_semantic_topic_answered(
        player_text,
        text,
    )
    raw_skip_when = _field_from_object(
        turn,
        "skipWhen",
        _field_from_object(turn, "skip_when", ()),
    )
    skip_when = (
        {
            str(value).strip().casefold()
            for value in raw_skip_when
            if isinstance(value, str) and value.strip()
        }
        if isinstance(raw_skip_when, (list, tuple, set, frozenset))
        else set()
    )
    explicit_rejection = (
        "explicit_rejection" in skip_when
        and bool(_CONVERSATION_LEAD_EXPLICIT_REJECTION_PATTERN.search(player_text))
    )
    player_closing = bool(
        _CONVERSATION_LEAD_PLAYER_CLOSING_PATTERN.search(player_text)
    ) or explicit_rejection
    acknowledges_rejection = bool(
        _CONVERSATION_LEAD_REJECTION_ACKNOWLEDGEMENT_PATTERN.search(text)
    )
    configured_needs_space_exit = (
        "npc_needs_space" in skip_when
        and bool(_CONVERSATION_LEAD_NEEDS_SPACE_PATTERN.search(text))
    )
    acknowledged_rejection_exit = (
        explicit_rejection
        and acknowledges_rejection
        and (
            exit_reply
            or close_reply
            or bool(_CONVERSATION_LEAD_GUARDED_CARE_PATTERN.search(text))
        )
    )
    player_sleep_close = bool(
        player_closing
        and _CONVERSATION_LEAD_PLAYER_SLEEP_CLOSE_PATTERN.fullmatch(text)
    )
    closing_care = bool(_CONVERSATION_LEAD_CLOSING_CARE_PATTERN.search(text))
    answered = _conversation_topic_answered(player_text, text) or semantic_topic_answered or (
        explicit_rejection and acknowledges_rejection
    )
    guarded_care = (
        expectation == "guarded"
        and answered
        and bool(_CONVERSATION_LEAD_GUARDED_CARE_PATTERN.search(text))
    )
    reopens_after_close = player_closing and not player_sleep_close and (
        has_question
        or has_plan
        or has_share
        or bool(_CONVERSATION_LEAD_IMPERATIVE_REOPENING_PATTERN.search(text))
    )
    if closing_care and not (has_question or has_share):
        reopens_after_close = player_closing and not player_sleep_close and bool(
            _CONVERSATION_LEAD_IMPERATIVE_REOPENING_PATTERN.search(text)
        )
    guarded_exit = (
        npc_id.casefold() == "shane"
        and expectation == "guarded"
        and exit_reply
    )
    if reopens_after_close:
        tags.add("reopens_after_player_closing")
        return {
            "answeredCurrentTopic": answered,
            "conversationLeadDetected": False,
            "conversationLeadKind": "",
            "conversationLeadEvidence": [],
            "conversationLeadTags": sorted(tags),
            "conversationLeadOpening": conversation_lead_opening(text),
            "conversationLeadAnchors": anchors,
            "previousConversationLead": dict(previous_diagnostic or {}),
        }
    if (
        (player_closing and (exit_reply or close_reply or player_sleep_close))
        or guarded_exit
        or configured_needs_space_exit
        or acknowledged_rejection_exit
    ):
        tags.add("lead_exit_allowed")
        return {
            "answeredCurrentTopic": answered or not player_text,
            "conversationLeadDetected": True,
            "conversationLeadKind": "lead_exit_allowed",
            "conversationLeadEvidence": [
                "explicit_rejection"
                if acknowledged_rejection_exit
                else "npc_needs_space"
                if guarded_exit or configured_needs_space_exit
                else "player_closing"
            ],
            "conversationLeadTags": sorted(tags),
            "conversationLeadOpening": conversation_lead_opening(text),
            "conversationLeadAnchors": anchors,
            "previousConversationLead": dict(previous_diagnostic or {}),
        }
    kind = ""
    if has_choice and has_specific:
        kind = "choice_prompt"
        evidence.append("specific_choice")
    elif has_share and (
        _CONVERSATION_LEAD_SHARE_RESPONSE_PATTERN.search(text)
        or (has_specific and _conversation_lead_has_substantive_question(text))
    ):
        kind = "self_share"
        evidence.append("personal_share")
    elif has_reason and has_plan and (
        has_question or "好不好" in lowered or "行吗" in lowered
    ):
        kind = "reasoned_small_plan"
        evidence.append("reasoned_plan")
    elif semantic_topic_answered:
        kind = "specific_follow_up"
        evidence.append("semantic_topic_answer")
    elif has_immediate_action and has_specific:
        kind = "topic_bridge"
        evidence.append("immediate_action")
    elif guarded_care:
        kind = "guarded_care"
        evidence.append("guarded_care")
    elif (has_question or has_implicit_question) and has_specific and not generic_question:
        kind = "specific_follow_up"
        evidence.append("specific_question")
    elif has_reason and has_specific:
        kind = "topic_bridge"
        evidence.append("personal_topic_bridge")

    if generic_question and not (has_specific or has_choice):
        tags.add("generic_follow_up_only")
    if _has_pattern(text, _COMPANIONSHIP_SUPPORT_PATTERNS) and not has_reason and not kind:
        tags.add("companionship_only")
    if has_plan and not has_reason and not kind:
        tags.add("specific_plan_only")
    if not kind and text:
        tags.add("missing_conversation_lead")
    if not answered and player_text:
        tags.add("missing_current_topic_answer")
        detected = False
    else:
        detected = bool(kind)
    if detected:
        tags.add(kind)
    return {
        "answeredCurrentTopic": answered,
        "conversationLeadDetected": detected,
        "conversationLeadKind": kind,
        "conversationLeadEvidence": evidence,
        "conversationLeadTags": sorted(tags),
        "conversationLeadOpening": conversation_lead_opening(text),
        "conversationLeadAnchors": anchors,
        "previousConversationLead": dict(previous_diagnostic or {}),
    }


_MECHANICAL_RESTATEMENT_MARKERS = (
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


def _normalize_mechanical_restatement_text(value: str) -> str:
    return re.sub(
        r"[\s，。！？、；：,.!?;:…‘’“”\"'（）()]+",
        "",
        value.casefold(),
    )


def _mechanical_restatement(reply: str, player_input: str) -> bool:
    """判断回复是否把本轮玩家输入当作开场回声，而非自然回应。

    话题对象词可以自然重用，但完整短问句或占玩家问题大半的连续片段，
    尤其是出现在第一句时，会让回复听起来像把玩家的话复制回来。Guard、
    亲密诊断和离线评分都使用这一个判定，避免各自漏掉不同长度的回声。
    """

    if not isinstance(reply, str) or not isinstance(player_input, str):
        return False
    if not reply.strip() or not player_input.strip():
        return False
    player_text = _normalize_mechanical_restatement_text(player_input)
    # 处理跨句的整段回声：只看回复第一句会漏掉“我没躲。你问一声就行。”
    # 这类把玩家整段话原样复制回来的情况，因此先检查去标点后的回复前缀。
    full_reply_text = _normalize_mechanical_restatement_text(reply)
    if len(player_text) >= 6 and full_reply_text.startswith(player_text):
        return True
    reply_sentence = re.split(r"[。！？!?；;]", reply.strip(), maxsplit=1)[0]
    reply_text = _normalize_mechanical_restatement_text(reply_sentence)
    if len(reply_text) < 3 or len(player_text) < 3:
        return False

    marker_text = tuple(
        _normalize_mechanical_restatement_text(marker)
        for marker in _MECHANICAL_RESTATEMENT_MARKERS
    )
    recap_marker = any(marker and marker in reply_text for marker in marker_text)
    match = SequenceMatcher(
        None,
        reply_text,
        player_text,
        autojunk=False,
    ).find_longest_match(0, len(reply_text), 0, len(player_text))
    common = match.size
    if recap_marker:
        return common >= 3 and common / min(len(reply_text), len(player_text)) >= 0.35

    # 完整短问句被塞进第一句，哪怕前面有“当然/嗯”，也是高置信回声。
    if len(player_text) >= 6 and player_text in reply_text:
        return True

    # 对没有固定复述词的短句，要求连续片段覆盖玩家输入的大半；
    # 仅复用“鸡舍/茶园/训练”等单个主题词时通常达不到 6 个字符。
    if common >= 6 and common / len(player_text) >= 0.6:
        # 片段从回复中段或玩家句中段开始，通常只是自然复用一个行动/对象，
        # 例如“要不要一起看看葡萄？”→“我们可以一起看看葡萄。”，不算回声。
        if match.a > 2 or match.b > 0:
            return False
        # 状态问句经常会自然变成“对象 + 已经/很/挺……”，这属于回答，
        # 不是把问句回声贴回去。完整问句仍由上面的高置信分支拦截。
        question_match = re.search(
            r"(?:吗|么|好吗|好不好|怎么样|如何|忙不忙|累不累|顺利吗)[?？]?$",
            player_input.strip(),
        )
        question_like = question_match is not None
        question_suffix = (
            _normalize_mechanical_restatement_text(question_match.group(0))
            if question_match is not None
            else ""
        )
        question_core_length = len(player_text) - len(question_suffix)
        if (
            question_like
            and match.a <= 2
            and match.b == 0
            and common >= max(4, question_core_length)
        ):
            return False
        return True

    # 保留旧规则对较长、分散在首句中的明显复述的覆盖。
    return common >= 12 and common / min(len(reply_text), len(player_text)) >= 0.55


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


_EXPLICIT_AFFECTION_REQUEST_PATTERN = re.compile(
    r"(?:说(?:一?句)?情话|(?:告诉我|说给我|直接说).{0,12}情话|"
    r"告诉我(?:你)?有多想我|"
    r"是不是只喜欢我|表达(?:一下)?想念|说清楚(?:你)?有多在乎|"
    r"告诉我最想对我说什么|想听你(?:说|表达)想念)"
)
_NEGATED_AFFECTION_PATTERN = re.compile(
    r"(?:不想你|不喜欢你|不在意你|不是(?:只有你|只想|专门)|"
    r"并不是(?:只有你|只想|专门)|不止(?:只有你)?|不只(?:有你)?)"
)
_STRONG_AFFECTION_SEMANTIC_PATTERNS: dict[
    str, tuple[re.Pattern[str], ...]
] = {
    "exclusive_choice": (
        re.compile(
            r"(?:从来|向来|一直|始终|也)?只有你.{0,36}"
            r"(?:才|能|让我|舍不得|愿意|想|留给|归你)"
        ),
        re.compile(r"(?:最想|最在意|最喜欢|最舍不得)你"),
        re.compile(
            r"除了你.{0,18}(?:没人|没有谁|没有别人).{0,18}"
            r"(?:能让我|让我|会让我)"
        ),
        re.compile(r"(?:换作|换成)别人.{0,24}(?:早就|不会|不肯|没法)"),
        re.compile(
            r"(?:换作|换成)(?:旁人|别人).{0,36}"
            r"(?:若是你|如果是你|但若是你|但你).{0,24}"
            r"(?:把.{0,8})?时间留给你"
        ),
    ),
    "exclusive_share": (
        re.compile(r"(?:只想|专门|特地|仅).{0,10}给你(?:看|听|留)"),
        re.compile(r"(?:只|专门|特地).{0,10}留给你"),
        re.compile(r"(?:这首|这段|这份).{0,10}(?:只|先).{0,6}给你"),
        re.compile(
            r"(?:一直)?最想.{0,12}(?:和|跟)你.{0,8}"
            r"(?:分享|先).{0,4}(?:第一口|一口)"
        ),
    ),
    "time_exclusivity": (
        re.compile(
            r"(?:今晚|这段时间|那段时间|这会儿|安静的时候).{0,14}"
            r"(?:只|都|本来就该).{0,8}(?:留给你|归你|属于你)"
        ),
        re.compile(r"(?:时间|今晚).{0,12}(?:只|都).{0,6}(?:给你|属于你)") ,
    ),
    "player_caused_anticipation": (
        re.compile(r"因为你.{0,12}(?:才|就)?(?:开始)?(?:期待|舍不得|想留|准备)"),
        re.compile(r"你一(?:说|提|来).{0,12}(?:就)?(?:期待|开始想|留给你)") ,
    ),
    "reluctant_separation": (
        re.compile(
            r"(?:舍不得|不舍得).{0,18}(?:合上|放下|走开|离开|错过|"
            r"让你等|把时间省过去|结束)"
        ),
        re.compile(r"(?:舍不得|不舍得)你(?:走|离开|等)") ,
    ),
}
_DIRECT_AFFECTION_PATTERNS = (
    re.compile(
        r"(?:想你|想念你|想起你|想到你|惦记你|在意你|喜欢你|爱你|"
        r"想和你|想跟你|想陪你|希望你在|可惜你不在|期待你|"
        r"抱你|想抱你|抱着你|靠你近|挨你近)"
    ),
    re.compile(r"(?:有|跟|和)你.{0,12}(?:安心|安静|高兴|自在)"),
    re.compile(
        r"(?:最想|只想)让你喜欢.{0,18}"
        r"(?:松了一口气|放心|踏实|安心)"
    ),
)
_LIGHT_AFFECTION_PATTERNS = (
    re.compile(r"(?:陪你|陪我|一起|一块|给你留|过来坐|坐一会|留一份)"),
    re.compile(r"(?:先休息|早点睡|吃点东西|别担心|帮你|照看|分担)"),
)


def diagnose_affection_intensity(
    reply: str,
    *,
    player_input: str = "",
) -> dict[str, object]:
    """诊断回复的亲密强度和强表达语义族，不改写回复文本。"""

    text = reply.strip() if isinstance(reply, str) else ""
    normalized_player_input = (
        player_input.strip() if isinstance(player_input, str) else ""
    )
    explicit_request = bool(
        _EXPLICIT_AFFECTION_REQUEST_PATTERN.search(normalized_player_input)
    )
    negated = bool(_NEGATED_AFFECTION_PATTERN.search(text))
    semantic_families: list[str] = []
    if text and not negated:
        for family, patterns in _STRONG_AFFECTION_SEMANTIC_PATTERNS.items():
            if any(pattern.search(text) for pattern in patterns):
                semantic_families.append(family)
    strong = bool(semantic_families)
    if strong:
        intensity = "strong"
    elif text and not negated and _has_pattern(text, _DIRECT_AFFECTION_PATTERNS):
        intensity = "direct"
    elif text and _has_pattern(text, _LIGHT_AFFECTION_PATTERNS):
        intensity = "light"
    else:
        intensity = "none"
    return {
        "affectionIntensity": intensity,
        "strongAffectionDetected": strong,
        "affectionSemanticFamilies": semantic_families,
        "explicitRequest": explicit_request,
    }


def diagnose_personal_affection(
    text: object,
    *,
    relationship_focus: str = "",
) -> dict[str, object]:
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
    normalized_focus = relationship_focus.strip().casefold()
    relationship_affection_evidence = (
        [
            pattern.pattern
            for pattern in _RELATIONSHIP_AFFECTION_PATTERNS
            if pattern.search(normalized)
        ]
        if normalized_focus in {"jealousy", "recovery"}
        else []
    )
    return {
        "personalAffectionDetected": bool(affection_evidence),
        "companionshipDetected": companionship_detected,
        "specificPlanDetected": specific_plan_detected,
        "relationshipAffectionDetected": bool(relationship_affection_evidence),
        "relationshipAffectionEvidence": relationship_affection_evidence,
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
    relationship_focus = str(
        _field_from_object(turn, "relationship_focus", "") or ""
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
    personal_affection = diagnose_personal_affection(
        text,
        relationship_focus=relationship_focus,
    )
    affection_evidence = personal_affection["affectionEvidence"]
    personal_affection_detected = personal_affection["personalAffectionDetected"]
    companionship_detected = personal_affection["companionshipDetected"]
    specific_plan_detected = personal_affection["specificPlanDetected"]
    relationship_affection_detected = personal_affection[
        "relationshipAffectionDetected"
    ]
    romantic_signal = any(marker.casefold() in lowered for marker in _ROMANTIC_MARKERS)
    mechanical_restatement = _mechanical_restatement(text, player_input)
    intensity_diagnostic = diagnose_affection_intensity(
        text,
        player_input=player_input,
    )
    guarded_care_detected = "guarded_care" in detected_kinds
    case_id = str(_field_from_object(case, "case_id", "") or "").strip().casefold()
    natural_role_signal = bool(
        case_id.startswith("deep-flirt-")
        and expected_kind in _NATURAL_DEEP_FLIRT_ROLE_PATTERNS
        and any(
            pattern.search(text)
            for pattern in _NATURAL_DEEP_FLIRT_ROLE_PATTERNS[expected_kind]
        )
    )
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
        detected = personal_affection_detected or natural_role_signal or (
            expected_kind == "affection_signal"
            and relationship_focus in {"jealousy", "recovery"}
            and relationship_affection_detected
        )
    elif expectation == "guarded":
        detected = personal_affection_detected or guarded_care_detected or natural_role_signal
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

    if romantic_signal and stage not in INTIMATE_STAGES:
        tags.add("flirt_stage_mismatch")
    if romantic_signal and (
        not bool(romance_eligible)
        or stage not in INTIMATE_STAGES
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
        **intensity_diagnostic,
        **personal_affection,
        "affectionShape": (
            personal_affection["affectionShape"]
            or "conversation_exit"
            if "conversation_exit" in detected_kinds
            else personal_affection["affectionShape"]
        ),
        "reply": reply,
    }
