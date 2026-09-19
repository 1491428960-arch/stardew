"""本地 DeepSeek Key 输入窗口。

只供当前工作树临时配置使用：Key 不打印、不回显、不写入脚本或日志。
"""

from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT / ".env.local"
CONFIG = {
    "BRIDGE_CLOUD_URL": "https://api.deepseek.com/chat/completions",
    "BRIDGE_CLOUD_MODEL": "deepseek-chat",
    "BRIDGE_CLOUD_ENABLED": "true",
    "BRIDGE_CLOUD_ONLY": "true",
    "BRIDGE_CLOUD_TIMEOUT": "45",
}


def update_env(key_value: str) -> None:
    if not ENV_FILE.is_file():
        raise RuntimeError("当前项目缺少 .env.local")
    if not key_value or "\n" in key_value or "\r" in key_value:
        raise ValueError("Key 不能为空，且不能包含换行")
    try:
        key_value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(
            "请输入原始 DeepSeek Key：不能带中文、富文本符号、引号或说明文字"
        ) from exc

    original = ENV_FILE.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    updates = {"BRIDGE_CLOUD_API_KEY": key_value, **CONFIG}
    output: list[str] = []
    seen: set[str] = set()

    for line in lines:
        match = re.match(r"^\s*([A-Z0-9_]+)\s*=", line)
        name = match.group(1) if match else None
        if name in updates:
            if name not in seen:
                output.append(f"{name}={updates[name]}\n")
                seen.add(name)
        else:
            output.append(line)

    if output and not output[-1].endswith("\n"):
        output[-1] += "\n"
    for name, value in updates.items():
        if name not in seen:
            output.append(f"{name}={value}\n")

    ENV_FILE.write_text("".join(output), encoding="utf-8", newline="")


def main() -> None:
    root = tk.Tk()
    root.title("DeepSeek 配置输入")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    frame = tk.Frame(root, padx=22, pady=18)
    frame.pack()
    tk.Label(
        frame,
        text="为 story-memory 配置 DeepSeek 官方 API",
        font=("Microsoft YaHei UI", 11, "bold"),
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
    tk.Label(
        frame,
        text="只写入当前项目 .env.local，不显示或回显 Key；请粘贴原始 ASCII Key。",
        fg="#555",
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 14))
    tk.Label(frame, text="API Key：").grid(row=2, column=0, sticky="e", padx=(0, 8))
    entry = tk.Entry(frame, width=56, show="•", relief="solid")
    entry.grid(row=2, column=1, sticky="w")
    tk.Label(
        frame,
        text="官方地址：api.deepseek.com/chat/completions",
        fg="#555",
    ).grid(row=3, column=1, sticky="w", pady=(8, 0))
    tk.Label(
        frame,
        text="模型：deepseek-chat（先做最小真实请求核验）",
        fg="#555",
    ).grid(row=4, column=1, sticky="w")
    status = tk.Label(frame, text="", fg="#b00020")
    status.grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 4))
    buttons = tk.Frame(frame)
    buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(6, 0))

    def cancel() -> None:
        root.destroy()

    def save() -> None:
        try:
            update_env(entry.get().strip())
        except Exception as exc:  # pragma: no cover - only local UI error path
            status.config(text=str(exc))
            entry.focus_set()
            return
        entry.delete(0, tk.END)
        entry.config(state="disabled")
        status.config(text="已保存。Key 内容不会显示；可以关闭此窗口。", fg="#146c2e")
        save_button.config(state="disabled")
        root.after(900, root.destroy)

    tk.Button(buttons, text="取消", width=10, command=cancel).pack(
        side="right", padx=(8, 0)
    )
    save_button = tk.Button(
        buttons,
        text="保存并关闭",
        width=12,
        command=save,
        default="active",
    )
    save_button.pack(side="right")
    entry.focus_set()
    root.bind("<Return>", lambda _event: save())
    root.bind("<Escape>", lambda _event: cancel())
    root.mainloop()


if __name__ == "__main__":
    main()
