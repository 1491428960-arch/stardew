"""线上群聊“自然接话流”（multi_turn）的独立云端批次运行器。

设计约束：

- 只通过本地 Bridge 的 ``/api/dialogue/group`` 发起请求；脚本自身不读取、不输出
  任何凭据，云端密钥仍由 Bridge 管理。
- 默认是 dry-run：必须显式传入 ``--confirm-cloud`` 才会真正联网，避免误消耗 Token。
- 批次目录必须不存在；已存在直接拒绝，历史工件（v1/v2/v3）不会被覆盖。
- 自然接话流允许“有人不发言”，因此 ``allParticipantsReplied`` 只作为观察项记录，
  不作为批次失败条件；真正的硬检查是频道、Provider、fallback、错误和发言人白名单。
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ENDPOINT = "http://127.0.0.1:5678"
DEFAULT_BATCH_NAME = "20260918-group-dialogue-cloud-v4-natural-flow-cases"
GROUP_PATH = "/api/dialogue/group"
ARTIFACT_ROOT = (
    Path(__file__).resolve().parents[1] / "artifacts" / "character-quality-eval"
)

_SCENE: dict[str, Any] = {
    "season": "spring",
    "date": "春 8 日",
    "weather": "sunny",
    "time": 1900,
    "location": "远程消息",
}


def _case(
    case_id: str,
    message: str,
    participants: Sequence[str],
    active_speaker: str,
    turn_count: int,
    focus: str,
) -> dict[str, Any]:
    return {
        "caseId": case_id,
        "message": message,
        "participants": [
            {"npcId": name, "displayName": name} for name in participants
        ],
        "activeSpeakerNpcId": active_speaker,
        "turnCount": turn_count,
        "focus": focus,
        "gameState": deepcopy(_SCENE),
        "recentFacts": [],
    }


_GROUP_CASES: tuple[dict[str, Any], ...] = (
    _case(
        "natural-group-shane-harvey-sleep",
        "我最近总是睡不好，你们有什么建议？",
        ["Shane", "Harvey"],
        "Shane",
        3,
        "同一 NPC 是否愿意补第二句；Harvey 是插话还是等 Shane 说完。",
    ),
    _case(
        "natural-group-sebastian-elliott-creative",
        "你们会怎么处理一个写不出来、但又不想删掉的想法？",
        ["Sebastian", "Elliott"],
        "Elliott",
        3,
        "Sebastian 的短句与 Elliott 的铺陈是否形成真实来回，而不是各说一段。",
    ),
    _case(
        "natural-group-sophia-emily-vineyard",
        "我昨天路过葡萄园，那些颜色让我有点走神。",
        ["Sophia", "Emily"],
        "Sophia",
        3,
        "Sophia 是否跳拍追问、Emily 是否用灵感接住，并出现话题递给玩家。",
    ),
    _case(
        "natural-group-abigail-sebastian-sophia-playlist",
        "我想做一份晚上的歌单，你们会放什么？",
        ["Abigail", "Sebastian", "Sophia"],
        "Sebastian",
        4,
        "三人名单里是否出现有人不发言、有人插话，而不是整齐轮流。",
    ),
    _case(
        "natural-group-wizard-elliott-harvey-records",
        "我在整理一份旧记录，有些地方对不上。",
        ["Wizard", "Elliott", "Harvey"],
        "Wizard",
        4,
        "Wizard 的判断口吻是否先接住问题，另两人是否只在自己有话时说。",
    ),
)


def group_batch_cases() -> list[dict[str, Any]]:
    """返回案例定义的独立副本，调用方修改不会影响后续批次。"""

    return deepcopy(list(_GROUP_CASES))


def build_request_payload(case: Mapping[str, Any]) -> dict[str, Any]:
    """构造 ``/api/dialogue/group`` 的请求体；不包含任何内部标记字段。"""

    payload: dict[str, Any] = {
        "provider": "cloud",
        "strategy": "multi_turn",
        "channel": "remote",
        "message": case["message"],
        "participants": deepcopy(list(case["participants"])),
        "activeSpeakerNpcId": case["activeSpeakerNpcId"],
        "turnCount": case["turnCount"],
    }
    if case.get("gameState"):
        payload["gameState"] = deepcopy(case["gameState"])
    if case.get("recentFacts"):
        payload["recentFacts"] = deepcopy(list(case["recentFacts"]))
    return payload


def _roster_ids(participants: Sequence[Any]) -> list[str]:
    ids: list[str] = []
    for item in participants:
        if isinstance(item, Mapping):
            value = item.get("npcId") or item.get("npc_id")
        else:
            value = item
        if value:
            ids.append(str(value))
    return ids


def _case_checks(
    request: Mapping[str, Any],
    response: Mapping[str, Any],
) -> dict[str, Any]:
    roster = _roster_ids(request.get("participants") or [])
    turns = response.get("turns") or []
    speakers = [
        str(turn.get("speakerNpcId"))
        for turn in turns
        if isinstance(turn, Mapping) and turn.get("speakerNpcId")
    ]
    return {
        "remoteChannel": response.get("channel") == "remote",
        "providerCloud": response.get("provider") == "cloud",
        "noFallback": response.get("fallback") is False,
        "noProviderErrors": not (response.get("providerErrors") or []),
        "allParticipantsReplied": set(speakers) == set(roster),
        "speakersInRoster": all(speaker in roster for speaker in speakers),
        "speakers": speakers,
    }


def _case_status(response: Mapping[str, Any]) -> str:
    """只有拿到真实可用的对白才算成功：Provider 失败、fallback 和空对白都算错误。"""

    if response.get("providerErrors"):
        return "error"
    if response.get("fallback"):
        return "error"
    if not (response.get("turns") or []):
        return "error"
    return "ok"


def _is_successful(record: Mapping[str, Any]) -> bool:
    if record.get("status") != "ok":
        return False
    return _case_status(record.get("response") or {}) == "ok"


def _consecutive_same_speaker_turns(speakers: Sequence[str]) -> int:
    return sum(
        1
        for previous, current in zip(speakers, speakers[1:])
        if previous == current
    )


def _sum_usage(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    totals = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
    for record in records:
        response = record.get("response") or {}
        usage = response.get("usage") or {}
        for key in totals:
            value = usage.get(key)
            if isinstance(value, int):
                totals[key] += value
    return totals


def summarize(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """汇总批次级证据；自然流信号与硬性协议检查分开统计。"""

    successful = [item for item in records if _is_successful(item)]
    checks = [
        item.get("checks")
        or _case_checks(item.get("request") or {}, item.get("response") or {})
        for item in records
    ]
    turns_total = 0
    turns_per_case: dict[str, int] = {}
    consecutive = 0
    addressed = 0
    silent_participants: list[str] = []
    silent_cases = 0
    provider_calls = 0
    for item, check in zip(records, checks):
        case_id = str(item.get("caseId"))
        response = item.get("response") or {}
        turns = response.get("turns") or []
        speakers = [str(turn.get("speakerNpcId")) for turn in turns if isinstance(turn, Mapping)]
        turns_total += len(turns)
        turns_per_case[case_id] = len(turns)
        consecutive += _consecutive_same_speaker_turns(speakers)
        addressed += sum(
            1
            for turn in turns
            if isinstance(turn, Mapping) and turn.get("addressedTo")
        )
        roster = _roster_ids((item.get("request") or {}).get("participants") or [])
        silent = [npc for npc in roster if npc not in set(speakers)]
        if silent:
            silent_cases += 1
            silent_participants.extend(npc for npc in silent if npc not in silent_participants)
        calls = response.get("providerCalls")
        if isinstance(calls, int):
            provider_calls += calls
    return {
        "schemaVersion": 1,
        "runStatus": "valid" if len(successful) == len(records) else "partial",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "endpoint": GROUP_PATH,
        "provider": "cloud",
        "channel": "remote",
        "strategy": "multi_turn",
        "caseCount": len(records),
        "successfulCases": len(successful),
        "failedCases": len(records) - len(successful),
        "providerCalls": provider_calls,
        "turnsTotal": turns_total,
        "turnsPerCase": turns_per_case,
        "consecutiveSameSpeakerTurns": consecutive,
        "addressedTurns": addressed,
        "silentParticipantCases": silent_cases,
        "silentParticipants": silent_participants,
        "allRemote": all(check["remoteChannel"] for check in checks),
        "allCloud": all(check["providerCloud"] for check in checks),
        "allNoFallback": all(check["noFallback"] for check in checks),
        "allNoProviderErrors": all(check["noProviderErrors"] for check in checks),
        "allSpeakersInRoster": all(check["speakersInRoster"] for check in checks),
        "allParticipantsReplied": all(
            check["allParticipantsReplied"] for check in checks
        ),
        "usage": _sum_usage(records),
    }


def _post_group_request(
    endpoint: str,
    payload: Mapping[str, Any],
    case: Mapping[str, Any],
) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint.rstrip("/") + GROUP_PATH,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def run_batch(
    *,
    cases: Sequence[Mapping[str, Any]],
    endpoint: str,
    output_dir: Path,
    confirm_cloud: bool,
    request_fn: Callable[[str, Mapping[str, Any], Mapping[str, Any]], dict[str, Any]]
    | None = None,
    max_total_tokens: int | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """执行批次并写出 ``cases.json`` / ``summary.json``。

    目录已存在或未确认云端授权时立即失败，不会发出任何请求。
    """

    emit = log or (lambda message: None)
    target = Path(output_dir)
    if target.exists():
        raise FileExistsError(f"批次目录已存在，拒绝覆盖：{target}")
    if not confirm_cloud:
        raise PermissionError(
            "未确认云端授权：需要显式 --confirm-cloud 才会发起真实 Provider 请求"
        )
    send = request_fn or _post_group_request

    records: list[dict[str, Any]] = []
    spent = 0
    budget_stop: str | None = None
    for case in cases:
        payload = build_request_payload(case)
        case_id = str(case["caseId"])
        emit(f"[请求] {case_id} · {len(payload['participants'])} 人 · 最多 {payload['turnCount']} 回合")
        try:
            response = send(endpoint, payload, case)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            records.append(
                {
                    "caseId": case_id,
                    "request": payload,
                    "response": None,
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            emit(f"[失败] {case_id} · {type(exc).__name__}: {exc}")
            continue
        checks = _case_checks(payload, response)
        status = _case_status(response)
        records.append(
            {
                "caseId": case_id,
                "request": payload,
                "response": response,
                "status": status,
                "checks": checks,
            }
        )
        turns = response.get("turns") or []
        usage = response.get("usage") or {}
        spent += int(usage.get("totalTokens") or 0)
        if status != "ok":
            reason = "；".join(str(item) for item in response.get("providerErrors") or []) or "空对白"
            emit(f"[失败] {case_id} · {reason}")
        else:
            emit(
                f"[完成] {case_id} · {len(turns)} 回合 · "
                f"发言人 {'、'.join(str(turn.get('speakerNpcId')) for turn in turns)} · "
                f"{usage.get('totalTokens')} tokens"
            )
        if max_total_tokens is not None and spent >= max_total_tokens:
            budget_stop = "max_total_tokens"
            emit(f"[预算] 已达上限 {max_total_tokens} tokens，停止后续案例")
            break

    summary = summarize(records)
    summary["budgetStop"] = budget_stop
    target.mkdir(parents=True, exist_ok=False)
    (target / "cases.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (target / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    emit(f"[写出] {target}")
    return {"summary": summary, "records": records, "outputDir": str(target)}


def build_plan(
    *,
    cases: Sequence[Mapping[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    """dry-run 计划：只描述将要发送什么，不联网、不写盘。"""

    return {
        "outputDir": str(output_dir),
        "outputDirExists": Path(output_dir).exists(),
        "requestCount": len(cases),
        "budgetHint": "单次 multi_turn 调用按 v3 实测约 0.3k～1k tokens 估算",
        "cases": [
            {
                "caseId": case["caseId"],
                "participants": _roster_ids(case["participants"]),
                "activeSpeakerNpcId": case["activeSpeakerNpcId"],
                "turnCount": case["turnCount"],
                "message": case["message"],
                "focus": case.get("focus", ""),
            }
            for case in cases
        ],
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="线上群聊自然接话流（multi_turn）云端批次运行器（默认 dry-run）",
    )
    parser.add_argument("--batch", default=DEFAULT_BATCH_NAME, help="批次目录名")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="本地 Bridge 地址")
    parser.add_argument(
        "--output-root",
        default=str(ARTIFACT_ROOT),
        help="批次根目录（默认 artifacts/character-quality-eval）",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=None,
        help="只运行指定 caseId，可重复；省略则运行全部案例",
    )
    parser.add_argument(
        "--max-total-tokens",
        type=int,
        default=None,
        help="累计 Token 上限，达到后停止后续案例",
    )
    parser.add_argument(
        "--turn-count",
        type=int,
        default=None,
        help=(
            "覆盖所有案例的回合上限（1-4）。用于单变量对照，例如复现游戏内"
            "未显式传 turnCount 时的默认预算（Bridge 默认 2）。"
        ),
    )
    parser.add_argument(
        "--confirm-cloud",
        action="store_true",
        help="确认消耗 Token 并发起真实云端请求；不加则只打印计划",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    cases = group_batch_cases()
    if args.turn_count is not None:
        if args.turn_count < 1 or args.turn_count > 4:
            print("--turn-count 必须在 1 到 4 之间。")
            return 2
        for case in cases:
            case["turnCount"] = args.turn_count
    if args.case:
        selected = set(args.case)
        unknown = selected - {case["caseId"] for case in cases}
        if unknown:
            print(f"未知 caseId：{'、'.join(sorted(unknown))}")
            return 2
        cases = [case for case in cases if case["caseId"] in selected]
    output_dir = Path(args.output_root) / args.batch

    if not args.confirm_cloud:
        print(json.dumps(build_plan(cases=cases, output_dir=output_dir), ensure_ascii=False, indent=2))
        print("\n当前是 dry-run：未发起任何请求。确认后加 --confirm-cloud 重跑。")
        return 0

    result = run_batch(
        cases=cases,
        endpoint=args.endpoint,
        output_dir=output_dir,
        confirm_cloud=True,
        max_total_tokens=args.max_total_tokens,
        log=print,
    )
    summary = result["summary"]
    print(
        f"\n批次完成：{summary['successfulCases']}/{summary['caseCount']} 案例 · "
        f"{summary['turnsTotal']} 回合 · {summary['usage']['totalTokens']} tokens · "
        f"沉默参与者案例 {summary['silentParticipantCases']} 个 · "
        f"同人连续回合 {summary['consecutiveSameSpeakerTurns']} 次"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
