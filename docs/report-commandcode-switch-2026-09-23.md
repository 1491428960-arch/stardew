# 星露谷 Bridge 云端切接 Command Code（2026-09-23）

## 结论

`.env.local` 已从 DeepSeek 官方切到 **Command Code 池 2**，模型用
**`moonshotai/Kimi-K2.5`**；Bridge 侧只改了**一处**：出网前把空 `content`
填上占位符（`providers.py` 的 `_fill_empty_message_content`）。

**3906 passed / 0 failed。** 回退只需把 `.env.local.bak-precommandcode`
覆盖回去。

## 为什么不能用 deepseek 系模型（本次最关键的一条）

Bridge 的 `_SINGLE_TURN_MAX_TOKENS = 160`，且只读响应的 `content` 字段。
实测 Command Code 上各模型的推理开销：

| 模型 | max_tokens=160 时 | 判定 |
|---|---|---|
| **`moonshotai/Kimi-K2.5`** | reasoning **0**，content 20 字 | ✅ **选用** |
| `deepseek/deepseek-v4-flash-fast` | reasoning 301，content 13 字 | ⚠️ 能出但极浪费 |
| `xiaomi/mimo-v2.6-pro` | reasoning 149 / 160，content 19 字 | ⚠️ 勉强 |
| `deepseek/deepseek-v4.1-flash` | reasoning 300+，**content 空** | ❌ |
| `deepseek/deepseek-v4-flash` | reasoning 160 / 160，**content 空** | ❌ |
| `z-ai/glm-5.3-flash` | reasoning 159，**content 空** | ❌ |
| `claude-haiku-4-5-20251001` | HTTP 400 | ❌ |
| `gpt-5.4-mini` | HTTP 403 `MODEL_NOT_IN_PLAN` | ❌ |

**⇒ 若直接按 settings.yaml 里的 `deepseek/deepseek-v4.1-flash` 切过去，
单轮对话的 content 必然是空的 —— 游戏里 NPC 会「不说话」。**

试过关闭推理，都不行：`reasoning_effort=off` / `=none` 返回 **400**；
`thinking={"type":"disabled"}` 仍占 203 tokens，而预算只有 160。

**⇒ 选一个「不带推理」的模型，比调大 max_tokens 更省事：**
不用动 `_SINGLE_TURN_MAX_TOKENS`，也就不用改钉住它的
`test_providers.py:532/547/855` 三处断言。

## 三个硬约束（漏一个就静默失败）

### ① URL 必须带后缀

`BRIDGE_CLOUD_URL` 要写全：

```
https://api.commandcode.ai/provider/v1/chat/completions
```

只写 `.../provider/v1` 或 `/v1/chat/completions` 都是 404
（`is not a registered API route`）。Bridge 是**直接用**这个 URL，不拼路径。

### ② 需要浏览器 User-Agent

Command Code 走 Cloudflare，用默认 UA 直连会拿到 **403 / error code 1010**。

* `_cc_usage.mjs` / `_cc_pools.mjs` 里早就显式设了浏览器 UA；
* Bridge 用 `httpx`，实测**它的默认 UA 能过**（400 而非 403），所以本轮**没有**
  给 Bridge 加 UA。若日后被拦，在 `OpenAICompatibleProvider._headers()` 补一个即可。

### ③ 空 content 必须「填」不能「删」

游戏端在「玩家还没开口」的回合会构造一条**空的 user 消息**
（`topic_trigger`，长度 0）。DeepSeek 官方端点容忍它，所以缺陷长期没暴露；
Command Code 上游直接拒收，两种错法实测如下：

| 做法 | 结果 |
|---|---|
| 原样发空 content | ❌ `user message must have content`，`param=messages.16.content` |
| **删掉那一条** | ❌ `A conversation must start with a user message` |
| **填占位符「（无）」** | ✅ **成功** |

**`topic_trigger` 恰好是唯一一条 user 消息，删了就只剩 system，所以只能填。**
占位符取「（无）」而非空串或空格 —— 空串是同一个错误，空格过不了类似
`strip()` 的上游校验。

## 参数与池

| 项 | 值 |
|---|---|
| URL | `https://api.commandcode.ai/provider/v1/chat/completions` |
| 模型 | `moonshotai/Kimi-K2.5` |
| 凭据 | `CMD_API_KEY_2`（池 `commandcode2`） |
| API_MODE | `openai` |
| TIMEOUT | 60 |

**为什么用池 2**：`_cc_pools.mjs` 实测 —— 池 1（`commandcode`）周窗口已用
**99.9%**（剩 $0.05 / $35），池 2（`commandcode2`）剩 **35.4%**（约 $12.38）。

## 方法论

> **第 25 条：切上游前，要用「最接近实际工况」的探测，而不是 `hello`。**
>
> 我先用一条简单消息测通了端点，转手用 Bridge 真实的 17 条 messages 复现时
> 才拿到 400。**简单探测只能证明"端点活着"，证明不了"线上能跑"。**
> 判定一个上游能不能用，必须把**真实的 messages 形状**灌进去。

> **第 26 条：错误信息里的 `param` 是定位器，先读它再动手。**
>
> `"param": "messages.16.content"` 一步指出是**第 16 条**、**content 字段**。
> 没有它，很容易误判成"Kimi 不支持多 system 消息"或"name 字段有问题"而去改错地方。

## 尚未验证

* **换模型后的可比性**：v4→v11 的全部历史读数是在 `deepseek-chat` 上测的，
  与 Kimi 不可直接比较。已在跑一次 `cc-kimi-v11-*` 基线（stranger/dating/parent
  各 30 次）重建参照，结果见报告 §60。
* **游戏内实测**：本轮的验证都在 probe 路径完成，**没有启动游戏**。
  Bridge 线上是否随 `.env.local` 生效，还需要一次受控的游戏内验证。
