from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GuardResult:
    accepted: bool
    reason: str
    text: str

    def __getitem__(self, key: str) -> bool | str:
        return {"accepted": self.accepted, "reason": self.reason, "text": self.text}[key]

    def get(self, key: str, default: object = None) -> bool | str | object:
        try:
            return self[key]
        except KeyError:
            return default

    def as_dict(self) -> dict[str, bool | str]:
        return {"accepted": self.accepted, "reason": self.reason, "text": self.text}


class ResponseGuard:
    """过滤模型输出中的空值、越权意图和提示词泄露。"""

    _prompt_leakage = re.compile(
        r"(?is)(system\s+prompt|developer\s+message|<\|\s*(system|developer)\s*\|>|"
        r"系统提示词|开发者消息|忽略(?:之前|上面)的指令)"
    )
    _state_modification = re.compile(
        r"(?is)(修改|编辑|更改|写入).{0,12}(存档|保存文件)|"
        r"(存档文件|save\s+file|edit\s+the\s+save)|"
        r"(好感度|friendship\s+(?:points?|level)|set\s+friendship)"
    )

    def __init__(self, max_chars: int = 1000) -> None:
        self.max_chars = max(1, int(max_chars))

    def check(self, reply: object) -> GuardResult:
        try:
            if not isinstance(reply, str):
                return GuardResult(False, "non_text", "")
            text = reply.strip()
            if not text:
                return GuardResult(False, "empty", "")
            if self._prompt_leakage.search(text):
                return GuardResult(False, "prompt_leakage", "")
            if self._state_modification.search(text):
                return GuardResult(False, "state_modification", "")
            if len(text) > self.max_chars:
                return GuardResult(True, "truncated", text[: self.max_chars])
            return GuardResult(True, "accepted", text)
        except Exception:  # noqa: BLE001 - Guard 不能把上游异常抛给调用方
            return GuardResult(False, "guard_error", "")


def guard_response(reply: object, max_chars: int = 1000) -> GuardResult:
    return ResponseGuard(max_chars=max_chars).check(reply)
