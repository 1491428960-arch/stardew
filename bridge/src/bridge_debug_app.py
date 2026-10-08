"""临时调试包装：把对话请求与回复落盘，方便会话外实时查看。

两件事：
  1. **所有** `/api/dialogue/*` 的请求体 + 回复正文 → dialogue-live.jsonl
  2. 校验失败（422）的请求体                → bridge422.log

动机：游戏端的「回看档案」只在**退游戏存档时**才写盘，正在进行的对话拿不到；
而 SMAPI 日志只记 `provider=/fallback=` 元数据，从不记正文。要排查「单场之内
跑题」，就必须在 Bridge 这一层把一问一答原样抄一份。

⚠ 实现方式经过两次修正：
  1. `@app.exception_handler(...)` 装饰器 —— 静默无效，连 print 都不出；
  2. `app.add_exception_handler(...)`  —— 注册成功但从不被调用，
     说明 `RequestValidationError` 没冒到 `ExceptionMiddleware`。

所以最终改用**纯 ASGI 中间件**：直接旁观 `http.response.start` 里的状态码，
并缓冲 `http.response.body` 拿回复正文；完全不依赖异常传播。
它**不消费**请求体（只是在 `receive` 上做旁路记录）。

它不修改项目源码。用完即弃。

启动：
    uvicorn bridge_debug_app:application --app-dir E:\\workspace\\.scratch \
        --host 127.0.0.1 --port 5678
"""

from __future__ import annotations

import datetime
import json
import sys
import traceback
from pathlib import Path

BRIDGE_SRC = (
    r"E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src"
)
SCRATCH = Path(r"E:\workspace\.scratch")
LOG_PATH = SCRATCH / "bridge422.log"
CHAT_LOG_PATH = SCRATCH / "dialogue-live.jsonl"
# 被 guard 判死的**原文**。`response` 里只有最终回复，看不到中间态；
# 而「括号是整条还是夹在句子里」决定了能不能安全剥离，必须看实物。
REJECT_LOG_PATH = SCRATCH / "guard-reject.jsonl"

# 这些字段每次都是几百条、与「跑题」无关，落盘时丢掉以免淹掉真正要看的上下文。
NOISY_KEYS = ("completedEventIds",)

sys.path.insert(0, BRIDGE_SRC)

from stardew_ai_bridge.app import app as _bridge_app  # noqa: E402

print("[debug-app] 已导入真 Bridge", flush=True)


def _trim_request(body: str) -> object:
    """把请求体解成对象并去掉噪音字段；解不开就原样存字符串。"""
    try:
        payload = json.loads(body)
    except Exception:  # noqa: BLE001
        return {"_unparsed": body}
    if not isinstance(payload, dict):
        return payload
    game_state = payload.get("gameState")
    for noisy in NOISY_KEYS:
        payload.pop(noisy, None)
        if isinstance(game_state, dict):
            removed = game_state.pop(noisy, None)
            if removed is not None:
                game_state[f"{noisy}Count"] = len(removed)
    return payload


def _append(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class DialogueRecorder:
    """旁观 ASGI 消息流：记对话正文，并单独记 422 的请求体。"""

    def __init__(self, asgi_app) -> None:
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.asgi_app(scope, receive, send)
            return

        path = scope.get("path") or ""
        watched = path.startswith("/api/dialogue/")

        chunks: list[bytes] = []
        state: dict[str, object] = {"status": None, "body": []}

        async def recording_receive():
            message = await receive()
            if message.get("type") == "http.request":
                chunk = message.get("body", b"")
                if chunk:
                    chunks.append(chunk)
            return message

        async def recording_send(message):
            kind = message.get("type")
            if kind == "http.response.start":
                state["status"] = message.get("status")
            elif kind == "http.response.body" and watched:
                state["body"].append(message.get("body", b""))
            await send(message)

        await self.asgi_app(scope, recording_receive, recording_send)

        status = state["status"]
        if status is None:
            return

        try:
            request_text = b"".join(chunks).decode("utf-8", "replace")

            if status == 422:
                _append(
                    LOG_PATH,
                    {
                        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                        "path": path,
                        # 实机那条请求体是 9166 字节，原先截到 8000 会把
                        # relationshipWorld 尾部整段切掉——而元凶可能在尾部。
                        "body": request_text,
                    },
                )
                print(f"[debug-app] 422 → {path}（{len(request_text)} 字节）", flush=True)

            if watched:
                response_text = b"".join(state["body"]).decode("utf-8", "replace")
                try:
                    response_obj = json.loads(response_text)
                except Exception:  # noqa: BLE001
                    response_obj = response_text[:2000]

                _append(
                    CHAT_LOG_PATH,
                    {
                        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                        "path": path,
                        "status": status,
                        "request": _trim_request(request_text),
                        "response": response_obj,
                    },
                )
                reply = ""
                if isinstance(response_obj, dict):
                    reply = str(response_obj.get("reply") or "")
                print(
                    f"[debug-app] 对话 {status} → {path}"
                    f"  reply={reply[:60]!r}",
                    flush=True,
                )
        except Exception:  # noqa: BLE001
            # 诊断路径绝不静默吞异常——上一版就是因此白等了一轮。
            print("[debug-app] 记录失败：\n" + traceback.format_exc(), flush=True)


application = DialogueRecorder(_bridge_app)
print("[debug-app] ASGI 记录中间件已挂载（对话正文 + 422）", flush=True)


# --------------------------------------------------------------------------
# 抓被 guard 判死的原文（2026-10-07）
#
# 动机：`response` 里只有**最终**回复，看不到中间态。要判断括号旁白能不能像引号
# 那样「剥壳保内容」，就必须知道括号是**整条包裹**还是**夹在句子里**——
# 前者剥了会掏空回复（兜底回复正是这种形态，绝不能剥），后者剥了只是去掉动作描写。
#
# 做法是 patch 类属性，不改项目源码：app.py 里的 `ResponseGuard` 实例走类方法查找，
# 所以这里替掉 `ResponseGuard.check` 对已有实例同样生效。
# --------------------------------------------------------------------------
try:
    from stardew_ai_bridge import guard as _guard_mod  # noqa: E402

    _orig_check = _guard_mod.ResponseGuard.check

    def _logging_check(self, reply, *, channel=None):
        # 2026-10-07 修正：`ResponseGuard.check` 增加了仅关键字参数 `channel`
        # （渠道门控，见 guard.py `_action_mode_active`）。wrapper 若不透传，
        # app.py 的 `check(reply, channel=...)` 会 TypeError —— 整条对话 500。
        result = _orig_check(self, reply, channel=channel)
        try:
            if isinstance(reply, str) and reply.strip():
                pattern = _guard_mod.ResponseGuard._stage_direction
                spans = [m.group(0) for m in pattern.finditer(reply)]
                if spans:
                    stripped = pattern.sub("", reply)
                    stripped = " ".join(stripped.split())
                    _append(
                        REJECT_LOG_PATH,
                        {
                            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                            "accepted": getattr(result, "accepted", None),
                            "reason": getattr(result, "reason", None),
                            "raw": reply,
                            "raw_len": len(reply),
                            "spans": spans,
                            "stripped": stripped,
                            "stripped_len": len(stripped),
                            # True 表示整条就是括号旁白，剥完什么都不剩 —— 这种绝不能剥。
                            "whole_wrapped": not stripped,
                        },
                    )
        except Exception:  # noqa: BLE001
            print("[debug-app] guard 记录失败：\n" + traceback.format_exc(), flush=True)
        return result

    _guard_mod.ResponseGuard.check = _logging_check
    print("[debug-app] 已挂 guard 原文探针 → guard-reject.jsonl", flush=True)
except Exception:  # noqa: BLE001
    print("[debug-app] guard 探针挂载失败：\n" + traceback.format_exc(), flush=True)


# --------------------------------------------------------------------------
# 抓「重试前的长度」（2026-10-07）
#
# 动机：`over_length` 判定发生在 **重试之前**，而 `dialogue-live.jsonl` 里只有
# **重试之后**的最终文本。B（允许动作旁白）上线后 over_length 从 23% 涨到 88%，
# 但按最终文本算「超 68 字」只有 18.75% —— 两者对不上。要决定是否放宽
# `_LENGTH_RETRY_THRESHOLD`，就必须先量到**首答**的真实长度分布，
# 否则动那个数字就是拍脑袋（那正是 `_LENGTH_RETRY_THRESHOLD_BY_STAGE` 注释里
# 明确写过「不要顺手放宽」的做法）。
#
# 挂点：`reply_exceeds_dialogue_length` 只在 guard.py **模块内**被调用
# （L1501、L1742），app.py 只导入了 `ResponseGuard` 与 `retry_for_format_noise`，
# 所以在模块上替换属性即可覆盖全部调用点。
#
# L1742 是「判 over_length」那一处，L1501 是 retry 循环内的另一处；
# 同一个物理请求里 `current.reply` 会被查多次，按 ts + chars 序列即可读出
# 「首答多长、重试后多长」。
# --------------------------------------------------------------------------
LENGTH_LOG_PATH = SCRATCH / "length-probe.jsonl"
try:
    from stardew_ai_bridge import guard as _len_guard  # noqa: E402

    _orig_exceeds = _len_guard.reply_exceeds_dialogue_length

    def _logging_exceeds(text, stage=None, *, channel=None):
        # 2026-10-07 修正：`reply_exceeds_dialogue_length` 也加了 channel
        # （渠道门控的连带改动）。不透传则 guard.py 的调用点直接 TypeError。
        verdict = _orig_exceeds(text, stage=stage, channel=channel)
        try:
            if isinstance(text, str):
                _append(
                    LENGTH_LOG_PATH,
                    {
                        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                        "stage": stage,
                        "limit": _len_guard._length_retry_threshold(stage),
                        "chars": len(text),
                        "over": bool(verdict),
                        "text": text,
                    },
                )
        except Exception:  # noqa: BLE001
            print(
                "[debug-app] 长度探针记录失败：\n" + traceback.format_exc(),
                flush=True,
            )
        return verdict

    _len_guard.reply_exceeds_dialogue_length = _logging_exceeds
    print("[debug-app] 已挂长度探针 → length-probe.jsonl", flush=True)
except Exception:  # noqa: BLE001
    print("[debug-app] 长度探针挂载失败：\n" + traceback.format_exc(), flush=True)


# --------------------------------------------------------------------------
# 抓「重试丢掉的那一版」（2026-10-08）
#
# 动机：实机里 Shane 对「（抱住不让她走）」回了「……鸡又不会跑。」——
# 玩家给了一个身体动作，NPC **一个动作都没回**，只把「看鸡」这个借口拆了。
# 而同一轮的 warning 是 `response_opening_retry: repeated`，说明**第一版被整条换掉了**。
# 要判断到底是「模型根本没生成动作」还是「重试把带动作的那版扔了」，
# 必须看到被丢弃的原文 —— 两条路的修法完全不同。
#
# 挂点：`retry_for_format_noise` 的判定链（guard.py 约 L1702 起）是一串
# `elif issue is None and <判定函数>(prompt, current.reply)`。每个判定函数都拿得到
# `current.reply`，**返回真就意味着这一版要被丢掉**。所以在模块上把这些判定函数
# 各包一层，返回真时把原文抄下来。循环内的调用走模块级名字查找，patch 有效。
#
# ⚠ 不改任何判据，只旁路记录。
# --------------------------------------------------------------------------
RETRY_DROP_PATH = SCRATCH / "retry-drop.jsonl"
_RETRY_DECISIONS = (
    "missing_opening_grounding",
    "_has_repeated_opening",
    "_missing_history_anchor",
    "_missing_required_term",
    "_missing_proactive_affection",
    "_repeats_conversation_lead",
    "_repeats_personal_affection_shape",
    "_is_mirror_restatement",
    "_violates_final_role_voice_schedule",
    "_violates_event_gate",
    "_reopens_after_player_close",
)
try:
    from stardew_ai_bridge import guard as _drop_guard  # noqa: E402

    def _make_drop_wrapper(fn, name):
        def wrapper(*args, **kwargs):
            verdict = fn(*args, **kwargs)
            try:
                if verdict:
                    text = next(
                        (a for a in args if isinstance(a, str) and a.strip()), ""
                    )
                    if text:
                        pattern = _drop_guard.ResponseGuard._stage_direction
                        _append(
                            RETRY_DROP_PATH,
                            {
                                "ts": datetime.datetime.now().isoformat(
                                    timespec="seconds"
                                ),
                                "decision": name,
                                "chars": len(text),
                                "has_action": bool(pattern.search(text)),
                                "reply": text,
                            },
                        )
            except Exception:  # noqa: BLE001
                print(
                    "[debug-app] 重试丢弃记录失败：\n" + traceback.format_exc(),
                    flush=True,
                )
            return verdict

        wrapper.__name__ = name
        wrapper.__doc__ = getattr(fn, "__doc__", None)
        return wrapper

    _drop_patched = []
    for _name in _RETRY_DECISIONS:
        _orig_decision = getattr(_drop_guard, _name, None)
        if _orig_decision is None or not callable(_orig_decision):
            continue
        setattr(_drop_guard, _name, _make_drop_wrapper(_orig_decision, _name))
        _drop_patched.append(_name)
    print(
        "[debug-app] 已挂重试丢弃探针 → retry-drop.jsonl"
        "（%d/%d 个判定点）" % (len(_drop_patched), len(_RETRY_DECISIONS)),
        flush=True,
    )
except Exception:  # noqa: BLE001
    print("[debug-app] 重试丢弃探针挂载失败：\n" + traceback.format_exc(), flush=True)


# --------------------------------------------------------------------------
# 抓「群聊解析失败时的模型原文」（2026-10-08）
#
# 动机：实机按 F9 接受邀约后，**开场那次**（message 为空）群聊返回
#     providerErrors = ['multi_turn 回复不是有效 JSON；重试后仍失败：…']
#     providerCalls = 2,  turns = []
# 于是 SMAPI 判 `turnCount=0`，界面显示「无可用回复」，NPC 一个都不开口。
# 而**非开场**（玩家先打一句）时，同样的 JSON 契约（group_conversation.py L292）
# 却正常返回 turns —— 所以问题不在「prompt 没要求 JSON」。
#
# 要区分三条完全不同的病因，必须看到原文：
#   a. 模型压根没吐 JSON（吐了纯对白）
#   b. 吐了 JSON 但被 ``` 围栏包住
#   c. 吐了「旁白 + JSON」，json.loads 直接失败
# 三者修法不同，**不能靠猜** —— 这个项目已经因为猜错方向返工过两次。
#
# 挂点：`GroupConversationService._multi_turn_turns` 内的局部 `parse()` 按
# **模块级名字**调用 `parse_multi_turn_payload`（group_conversation.py L1044），
# 走的是 globals 查找，因此在模块上替换属性即可覆盖全部调用点（含重试那次）。
#
# ⚠ 不改解析逻辑、不改重试策略、不加宽容解析，只在**失败时**旁路记录原文。
# --------------------------------------------------------------------------
GROUP_PARSE_LOG_PATH = SCRATCH / "group-parse-fail.jsonl"
try:
    from stardew_ai_bridge import group_conversation as _gc  # noqa: E402

    _orig_group_parse = _gc.parse_multi_turn_payload

    def _logging_group_parse(reply, *, participant_ids=(), expected_turn_count=0):
        try:
            return _orig_group_parse(
                reply,
                participant_ids=participant_ids,
                expected_turn_count=expected_turn_count,
            )
        except Exception as exc:  # noqa: BLE001
            try:
                text = reply if isinstance(reply, str) else repr(reply)
                try:
                    ids = list(participant_ids)
                except TypeError:
                    ids = []
                _append(
                    GROUP_PARSE_LOG_PATH,
                    {
                        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                        "error": str(exc),
                        "expected_turn_count": expected_turn_count,
                        "participant_ids": ids,
                        "raw_len": len(text),
                        "has_fence": "```" in text,
                        "json_starts_at": text.find("{"),
                        "raw": text,
                    },
                )
            except Exception:  # noqa: BLE001
                print(
                    "[debug-app] 群聊解析失败记录出错：\n" + traceback.format_exc(),
                    flush=True,
                )
            raise

    _gc.parse_multi_turn_payload = _logging_group_parse
    print("[debug-app] 已挂群聊解析失败探针 → group-parse-fail.jsonl", flush=True)
except Exception:  # noqa: BLE001
    print("[debug-app] 群聊解析探针挂载失败：\n" + traceback.format_exc(), flush=True)
