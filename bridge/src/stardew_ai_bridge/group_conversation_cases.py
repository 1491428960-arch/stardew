"""线上多人对话的固定比较案例。

案例只保存可公开发送给多人接口的场景、参与者、历史和玩家输入。
``group_case_catalog`` 每次返回独立副本，真实 Provider 请求由调用方发起，
导入本模块不会联网，也不会读取运行时认证信息。
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy


_STRATEGIES = {"fanout", "turn_based", "multi_turn"}


_GROUP_CASES: tuple[dict[str, object], ...] = (
    {
        "caseId": "group-abigail-emily-daily",
        "provider": "cloud",
        "channel": "remote",
        "message": "你们最近都在忙什么？",
        "participants": [
            {"npcId": "Abigail", "displayName": "Abigail"},
            {"npcId": "Emily", "displayName": "Emily"},
        ],
        "activeSpeakerNpcId": "Abigail",
        "history": [
            {
                "speakerType": "player",
                "speakerId": "player",
                "content": "Abigail，你最近还在练琴吗？",
                "addressedTo": ["Abigail"],
                "visibility": "public",
            },
            {
                "speakerType": "npc",
                "speakerId": "Abigail",
                "content": "晚上会练一会儿。",
                "addressedTo": [],
                "visibility": "public",
            },
            {
                "speakerType": "player",
                "speakerId": "player",
                "content": "晚上好，最近镇上都挺安静。",
                "addressedTo": [],
                "visibility": "public",
            },
        ],
        "turnCount": 2,
        "gameState": {
            "season": "spring",
            "date": "春 8 日",
            "weather": "sunny",
            "time": 1900,
            "location": "远程消息",
        },
    },
    {
        "caseId": "group-alex-sebastian-relationship",
        "provider": "cloud",
        "channel": "remote",
        "message": "我想和 Sophia 交往，你们怎么看？",
        "participants": [
            {
                "npcId": "Alex",
                "displayName": "Alex",
                "sourceMods": ["vanilla", "female-bachelors"],
            },
            {
                "npcId": "Sebastian",
                "displayName": "Sebastian",
                "sourceMods": ["vanilla", "female-bachelors"],
            },
        ],
        "activeSpeakerNpcId": "Alex",
        "history": [
            {
                "speakerType": "player",
                "speakerId": "player",
                "content": "我不想把这件事藏起来。",
                "addressedTo": [],
                "visibility": "public",
            }
        ],
        "turnCount": 2,
        "relationshipWorld": {
            "objectiveRelationships": [
                {"npcId": "Sophia", "relationType": "dating"}
            ],
            "views": [],
        },
        "gameState": {
            "season": "summer",
            "date": "夏 14 日",
            "weather": "sunny",
            "time": 1830,
            "location": "远程消息",
        },
    },
    {
        "caseId": "group-wizard-sophia-research",
        "provider": "cloud",
        "channel": "remote",
        "message": "第三组的读数稳定了吗？",
        "participants": [
            {
                "npcId": "Wizard",
                "displayName": "Rasmodia",
                "sourceMods": ["Romanceable Rasmodius"],
            },
            {
                "npcId": "Sophia",
                "displayName": "Sophia",
                "sourceMods": ["Stardew Valley Expanded"],
            },
        ],
        "activeSpeakerNpcId": "Wizard",
        "history": [
            {
                "speakerType": "npc",
                "speakerId": "Wizard",
                "content": "第三组还需要观察。",
                "addressedTo": ["player"],
                "visibility": "public",
            },
            {
                "speakerType": "player",
                "speakerId": "player",
                "content": "那就先把读数记下来。",
                "addressedTo": [],
                "visibility": "public",
            },
        ],
        "turnCount": 2,
        "gameState": {
            "season": "fall",
            "date": "秋 3 日",
            "weather": "rain",
            "time": 2100,
            "location": "远程消息",
        },
    },
    {
        "caseId": "group-three-roster-boundary",
        "provider": "cloud",
        "channel": "remote",
        "message": "这条消息只发给你们三个，别让其他人替你们回答。",
        "participants": [
            {"npcId": "Abigail", "displayName": "Abigail"},
            {"npcId": "Emily", "displayName": "Emily"},
            {"npcId": "Wizard", "displayName": "Rasmodia"},
        ],
        "activeSpeakerNpcId": "Emily",
        "history": [],
        "turnCount": 3,
        "gameState": {
            "season": "winter",
            "date": "冬 20 日",
            "weather": "snow",
            "time": 1600,
            "location": "远程消息",
        },
    },
)


def group_case_catalog() -> list[dict[str, object]]:
    """返回不带共享可变引用的固定案例目录。"""

    return deepcopy(list(_GROUP_CASES))


def comparable_group_payload(
    case: Mapping[str, object],
    strategy: str,
) -> dict[str, object]:
    """构造同一案例的 API 请求，只切换多人生成策略。

    ``caseId`` 是本地目录元数据，不属于 API 请求字段，因此会被移除；
    调用方应在外层用目录中的 ``caseId`` 关联结果。
    """

    if strategy not in _STRATEGIES:
        raise ValueError(f"不支持的多人策略: {strategy}")
    payload = deepcopy(dict(case))
    payload.pop("caseId", None)
    payload["strategy"] = strategy
    return payload
