# 当前工作状态

更新时间：2026-09-01

## 总目标

建立可追溯的原版 / SVE / RomRas NPC 资料库，并让 Rasmodia 的模型上下文真正使用经过验证的原文、背景事实和语气证据。

## 已完成

- 2026-09-01 修复快速测试启动器误拒绝当前 worktree 的路径问题：安全校验现在只对白名单形式的 `仓库名.worktrees -> 仓库名\\.worktrees` 父级 Junction 放行，目标目录、嵌套链接和不可信依赖 Junction 仍保持拒绝。先新增回归用例，修复前实际为 `39` 通过、`1` 失败，修复后快速 profile 回归为 `40` 通过、`0` 失败；SMAPI 全量测试为 `174` 通过、`0` 失败。当前构建 DLL 与隔离 `Mods-AI-FastTest` 部署 DLL SHA-256 均为 `1E4AEFECEC3A89120401E73F22B24DDE9E6BC0A0D2BB3CB33E7CA7742500C8D5`，SMAPI PID `38716` 的日志已确认从该隔离目录加载 `Stardew AI NPC`、Rasmodia、Content Patcher、CMCT 和 GMCM；尚未完成进入独立存档后的 F8、动态对白和聊天菜单帧率实测。路径修复已提交为 `e6793e5` 并推送到 GitHub `main`。

- 2026-09-01 使用“高好感度与语气变化”新规则，通过百炼 Qwen 云端重跑固定质量评测：`23/23` 案例成功、`69/69` 轮成功、`0` 错误、`0` 失败轮，自动全轮通过 `11/23`；相比上一批 `7/23` 有提升。结果工件为 `artifacts/character-quality-eval/20260901-high-stage-voice-cloud`，共发起 `80` 次真实请求，输入 `298637`、输出 `1509`、合计 `300146` Token，当前未配置单价所以费用估算为 `null`。按角色为 Rasmodia `3/4`、Sophia `4/4`、Shane `3/4`、Sebastian `3/4`、Alex `4/4`，另含 Caroline、Marnie、Linus 各 1 例；关系阶段为 acquaintance `5`、friend `10`、close `7`、married `1`，婚后案例仍未自动通过。结果中的失败主要是 `missing_expected_evidence`（3 例），没有格式噪声标签；自动分数仍不能替代人工角色判断，需在浏览器查看完整多轮回复。`5678/api/quality/results` 已返回该新批次，`/health` 仍为 `provider=cloud`，本轮未启动游戏、未部署 DLL。

- 2026-09-01 完成 Qoder 会员与项目接入评估：官方资料确认个人会员 Credits 用于 Qoder IDE/CLI/Agent/Quest 等产品，Qoder 内配置百炼自定义模型时费用仍由百炼账户直接结算；Qoder Cloud Agents 虽有独立 API，但采用 PAT/SAT + Agent/Environment/Session/Event 协议，不是当前 Bridge 的 Chat Completions 直连替代。当前实时 5678 `/health` 返回 `provider=cloud`，云端模型为 `qwen-plus-character`；建议会员用于代码审查、测试和离线评测辅助，暂不增加 Qoder Provider。详细来源与边界见 `docs/report-Qoder会员与Stardew-AI-NPC项目接入评估-2026-09-01.md`，未读取账户凭据、未发起 Qoder API 请求、未修改游戏或 Bridge 运行配置。

- 2026-09-01 继续完成上一轮质量回归的收尾核验：白名单修改后重新运行 Bridge 全量测试，实际为 `487 passed, 1 warning`；当前 worktree 的 SMAPI C# 全量测试为 `174 passed, 0 failed`，`git diff --check` 无差异错误。重启 5678 后包装器为 PowerShell PID `40972`、实际监听 Python PID `38628`，父子命令行均指向当前 `story-memory` worktree；`/health` 返回 `provider=cloud`，`/test` 返回 `data-ui-shell=v4`，`/api/quality/results` 正确读取 `20260901-friendship-voice-retry-cloud`（23 个案例、69 轮、95 次真实请求、输入 `344473` / 输出 `1874` / 合计 `346347` Token）。在当前浏览器的测试例浏览页逐项检查了最新批次：Caroline、Marnie、Linus 的关系与背景场景已有可读样本，Shane 的冷淡收口已进入样例，但 Alex 仍有动作旁白，Shane/Marnie 等案例仍有连续性或格式噪声；自动全轮通过为 `7/23`，所以角色质量仍未达到稳定满意。SMAPI 测试只生成了工作树 Debug DLL（SHA-256 `685DA3854A463CCE62417C6E8688A5A4DE892DB9D1257FE21ECCD069C2C43608`），快速测试目录仍为旧哈希 `D5E68E542E79B3AA4E58B98ED628DF36BBF6B82C8C86B3FCB466C32DE9A357E0`；本轮未部署 DLL、未启动游戏，不能据此声称游戏已加载最终版本。

- 2026-08-31 修复游戏实际好感度字典的类型兼容缺口：核对当前 Stardew Valley DLL 后确认 `Farmer.friendshipData` 是不实现非泛型 `IDictionary`、但提供字符串键 `ContainsKey` / `TryGetValue` 的 `NetStringDictionary`。新增共享 `FriendshipDataAccessor`，同时兼容旧非泛型字典、游戏泛型字典和字符串索引器，并接入游戏内目标筛选与上下文采集；新增回归测试先以“类型不存在”红灯，随后定向测试 `3/3`、SMAPI 全量测试 `174/174`。本轮只构建了工作树 Debug DLL，未部署、未启动游戏，因此仍需实机确认 F8 能选中 Caroline、Marnie、Willy 等非恋爱 NPC。

- 2026-08-31 完成“所有有好感度 NPC 可对话”这一轮覆盖：游戏内 F8 不再固定查找恋爱角色，而是从当前地点实时筛选 `player.friendshipData` 中存在记录的 NPC，优先鼠标交互目标，否则选择最近目标；没有符合条件的 NPC 时只记录明确警告并安全退出。网页 `/api/npcs` 与单页工作台也不按恋爱资格裁剪，当前返回 `97` 个目录项；按原版 + 当前 SVE 的 41 个可建立友谊 NPC 名单核对，`41/41` 存在、缺失 `0`。实际用 `Caroline`、`Marnie`、`Willy` 分别调用 Fake 对话接口均返回 `provider=fake`、`fallback=false`；`Marnie` 上下文预览含原文语气证据、牧场事实和 Shane 关系。当前索引为 schema `2`、`112 profiles`、`4,939 styleSamples`、`4,939 speechEvidence`、`10 knowledgeFacts`、`8 knownCharacters`，SHA-256 为 `71A95038DF92505A01F52742817CFFF829CC84E71EF69234631D962A79D71980`。Bridge 全量回归实际为 `474 passed, 1 warning`；SMAPI C# 全量回归实际为 `171 passed, 0 failed`。5678 当前监听进程 PID `44348`，`/health` 返回 `provider=cloud`，`/api/quality/cases` 返回 `17` 例，`/api/quality/results` 返回 `20260831-cloud-followup` 的 `15` 条脱敏结果，`/test` 返回 `data-ui-shell=v4`。本轮未启动游戏、未构建或部署 DLL，因此游戏内跨重启历史和真实存档中的 NPC 目标选择仍未做实机验证；本条确认的是代码、接口和单元测试覆盖，不把 97 个目录项表述成已经逐个在游戏里点开验证。

- 2026-08-31 重启后继续执行当前角色质量回归：先确认 `5678` 页面来自当前 `story-memory` 工作树，再用百炼 Qwen 云端重跑固定五角色 × 三案例（共 15 案例、45 轮）。结果工件为 `artifacts/character-quality-eval/20260831-cloud-followup`：`15/15` 案例成功、`45/45` 轮成功、`0` 错误、`0` fallback，自动全轮通过 `3/15`；因格式/续聊锚点防护产生总计 `55` 次真实请求。用量为输入 `190581`、输出 `998`、合计 `191579` Token，当前未配置单价所以费用估算为 `null`。抽查显示云端 Qwen 的 Shane 冷淡边界、Sebastian 摩托车/代码话题较自然，但 Sophia 的酒/上一批、Alex 的邀约等续聊仍会丢具体锚点；不能据此宣称角色质量已达标。全量 Bridge 回归实际为 `464 passed in 34.22s`；`/health` 返回 `provider=cloud`，`/api/quality/results` 已读取该批次 15 条结果。已将 `/test` 重新置于 Codex 面板；本机浏览器自动控制插件缺失 `browser-client.mjs`，因此未把点击级浏览器操作记为已完成。未启动游戏、未构建或部署 DLL。

- 2026-08-31 修复 Bridge 健康接口按 local 可用性误报 provider 的问题：现在按路由器默认选择报告 `cloud`/`local`，自动模式仍按可用上游选择，未配置上游时保持 `fake`。测试先捕获真实红灯，再完成最小修复；定向健康测试 `2 passed`，Bridge 全量回归 `427 passed, 1 warning`。新增质量评测和本地基准工件路径稳定化：仓库内索引写为相对路径，仓库外只保留 `external/<文件名>`，避免工作树绝对路径和历史 `.worktrees` 目录名继续进入新工件。相关定向测试 `14 passed`；未重写历史工件，未启动游戏、未构建或部署 DLL。

- 2026-08-30 完成单次对话用量统计闭环：`/api/dialogue/test` 现在转发 Provider usage；格式噪声重试时会累计同一轮内所有真实上游请求的输入、输出和总 Token，不把本地安全 fallback 计入上游用量；Dialogue Lab 聊天诊断区和本地会话恢复会显示/保存本次用量，固定质量评测页继续显示整批 Token 与已配置费用估算。TDD 先捕获重试只返回最后一次用量的红灯，定向回归为 `92 passed`，Bridge 全量回归为 `372 passed in 9.18s`。5678 已重启到当前 worktree：包装器 PID `31276`、实际监听 Python PID `34396`；`/health` 返回 `{"status":"ok","provider":"local"}`，`/test/chat` 返回 `200`、`data-ui-shell="v4"`、包含用量诊断和会话保存逻辑。真实本地请求返回 `provider=local`、`fallback=false`、`inputTokens=1496`、`outputTokens=17`、`totalTokens=1513`。本轮未发起付费云端请求、未启动游戏、未构建或部署 DLL；游戏端历史跨 SMAPI/游戏重启持久化仍未完成。

- 2026-08-30 使用百炼 Qwen API 重跑五角色固定质量评测：新工件 `artifacts/character-quality-eval/20260830-215347-api-qwen-round` 共 15/15 成功、0 错误、0 fallback、自动评分 12/15；按角色为 Wizard/Rasmodia 2/3、Sophia 2/3、Shane 2/3、Sebastian 3/3、Alex 3/3。5678 的 `/api/quality/results` 已读取该批次并返回 15 条 `provider=cloud` 结果，测试例浏览页可查看实际回复。未通过项是 Wizard 续聊、Sophia 当面续聊和 Shane 续聊，均属于续聊证据未稳定带回，不是 API 或 Provider 失败；结果未写回角色资料库。

- 2026-08-30 固化“默认使用 API”行为：Dialogue Lab 默认选中“云端（显式，当前配置）”；Bridge 在请求未指定 `provider` 且云端已配置时默认走云端 Provider，`自动` 仍保留为手动选择的 `local → cloud → fallback` 路由；测试中的 Fake 请求均改为显式 `provider=fake`，避免误用本机凭据。最新完整 Bridge 回归为 `360 passed in 7.35s`；56 个 Python 文件不落盘语法编译通过，`git diff --check` 通过。实时 5678 `/health` 返回 `200`，`/test` 返回 `200`、`data-ui-shell=v4` 且云端选项默认选中；一条未指定 `provider` 的真实请求返回 `provider=cloud`、`fallback=false` 和非空回复。本轮未启动游戏、未构建或部署 DLL。

- 2026-08-30 同步云端模式页面文案：将仍显示 Terra 的 Provider 选项改为“云端（显式，当前配置）”，避免与当前百炼 Qwen 配置混淆；README 同步更新当前用法，历史 Terra 评测记录保留。页面契约先捕获 `1 failed`，改动后为 `1 passed`；重启后的 5678 `/health` 返回 `200`、`provider=local`，`/test` 返回 `200`、`data-ui-shell=v4` 和新文案。最终 Bridge 全量回归为 `358 passed in 6.39s`，不落盘语法编译为 48 个文件通过，最新最小云端请求仍返回 `provider=cloud`、`fallback=false`、非空回复。本轮未启动游戏、未构建或部署 DLL。

- 2026-08-30 修复百炼 Qwen 显式云端模式的配置语义：`BRIDGE_CLOUD_ENABLED=false` 现在只关闭自动路由，不再阻止已配置 URL 的显式 `provider=cloud` 请求创建云端 Provider。TDD 先捕获 `1 failed`，修复后定向测试为 `1 passed`；Bridge 全量回归为 `358 passed in 7.16s`，48 个 Python 文件不落盘语法编译通过，`git diff --check` 通过。重启当前 worktree Bridge 后，`5678/health` 返回 `{"status":"ok","provider":"local"}`；一条最小 Qwen 请求和 Wizard/Rasmodia、Sophia、Shane、Sebastian、Alex 各一条代表样本均返回 `provider=cloud`、`fallback=false`、非空回复，单条延迟约 1.0–1.5 秒。浏览器自动点击仍受本机内核资产路径错误阻碍，已将当前 `/test` 重新置于 Codex 面板；本轮未批量生成质量评测工件、未启动游戏、未构建或部署 DLL。

- 2026-08-30 Terra 批量评测已按用户明确授权执行：15 个固定场景均未成功返回，结果工件 `artifacts/character-quality-eval/20260830-160148` 记录为 `15 errors / 0 successful`，错误类型为 `ProviderError`；进一步的单条对话请求返回 `HTTP 429`，脱敏错误信息为“没有剩余额度”，而同一 key 的模型列表请求返回 `200` 且可见 `gpt-5.6-terra`。结论是当前 OpenAI API 组织没有可用 credits，不是 key 为空或项目提示词故障；未继续盲目重试，也没有 Terra 成功对话工件可供浏览器查看。

- 2026-08-30 增加项目级 `.env.local` 自动配置：Bridge 应用初始化和角色质量评测入口都会读取被 Git 忽略的本机配置，只允许现有 `BRIDGE_*` 配置键，进程环境变量优先，未知变量不会加载；定向回归 `25 passed`，Bridge 全量回归 `357 passed in 5.73s`，纯内存语法编译和 `git diff --check` 均通过。用户已填写本机 `.env.local`，脱敏检查确认 Terra URL、模型和非空 key 均已配置；重启后的 5678 包装器 PID `34364`、实际监听 Python PID `8720`，`/health` 返回 `{"status":"ok","provider":"local"}`，`/test` 返回 `200` 且为当前 UI。`BRIDGE_CLOUD_ENABLED=false` 下自动模式仍走本地 Qwen，显式选择云端 Terra 时使用该配置；本轮未发起云端生成请求，也未读取或写入真实 key 内容。

- 2026-08-30 接通显式云端评测路径：`DialogueTestRequest` 支持 `auto/local/cloud/fake`，ProviderRouter 的显式 `cloud` 会绕过本地 Provider；`/test/chat` 新增“云端 Terra（显式）”并把选择传给 API；`scripts/run_character_quality_eval.py` 新增 `--provider cloud`，从 `BRIDGE_CLOUD_*` 环境变量构造 OpenAI-compatible Provider，默认本地 Qwen 行为不变；案例浏览页按实际结果动态标注本地、云端或 Fake 批次来源。TDD 红灯实际捕获 5 个缺口，定向回归为 `105 passed`，Bridge 全量回归为 `356 passed in 5.72s`，纯内存 Python 编译检查通过，`git diff --check` 无差异错误。5678 已重启为当前 worktree 进程（最新包装器 PID `35932`、Python PID `17220`），`/health` 返回 `provider=local`，`/test` 与 `/test/chat` 均包含 cloud 选项和最新显示逻辑。API 账号已由用户本机验证可见 `gpt-5.6-terra`；当时尚未从本地评测进程实际发起 Terra 生成请求，配置自动加载已在后续条目补上。本轮未启动游戏、未构建或部署 DLL。

- 2026-08-30 为下一轮 Terra/Qwen 同条件对照建立当前控制组：使用最新中文联合索引、当前 `ContextBuilder`/`PromptBuilder`、固定 15 个质量案例、隔离 Ollama `qwen3.5:9b` 和干净案例历史重跑，结果为 `15 successful / 0 errors / 14 passed`，耗时约 16.5 秒；结果保存于 `artifacts/character-quality-eval/20260830-qwen-control-before-terra`。当前 5678 `/health` 返回 `status=ok`、`provider=local`；本机未配置 `BRIDGE_CLOUD_*` Terra 端点或凭据，因此尚未生成 Terra 结果，不能宣称已完成 A/B。Bridge 全量回归实际为 `350 passed in 5.83s`，`git diff --check` 通过；本轮未启动游戏、未构建或部署 DLL。

- 2026-08-30 修复 Alex 测试效果与原始对白参照页滚动回归：补充 Alex 的“行动派”核心标签，保留七个关系阶段和分阶段行为示例；按既有参数重建中文联合索引，Alex 行为示例进入当前派生索引。原始对白页确认 `grid → section → list` 的可压缩滚动链和窄屏页面滚动规则。定向回归实际为 `116 passed`，Bridge 全量回归实际为 `350 passed in 5.68s`。重启目标 Bridge 时同时替换包装器和 5678 Python 子进程；当前 `/health` 返回 `status=ok`、`provider=local`，`/raw` 返回 `data-ui-shell="v4"` 且包含滚动规则，Alex `POST /api/context/preview` 返回核心标签、`stranger` 阶段和匹配行为示例。已将 `http://127.0.0.1:5678/test` 重新置于 Codex 面板；浏览器自动控制因本机内核资产路径错误未完成截图级点击验收。本轮未启动游戏、未构建或部署 DLL。

- 2026-08-30 将最新本地质量评测结果接入测试例浏览页：新增脱敏结果读取模块和 `GET /api/quality/results`，按 `caseId` 将最新 `artifacts/character-quality-eval` 批次与 15 个测试定义合并；案例详情现在显示本轮实际模型回复、Provider、延迟、Fallback、自动评分和 `format_noise` 提示，结果接口不会返回完整 prompt、API key 或 Token。TDD 先得到结果模块缺失的收集错误，页面接入测试随后保留 1 个预期缺口，最终定向回归为 `58 passed`，Bridge 全量回归为 `346 passed in 7.30s`。重启后的 Bridge 包装器 PID `36392`、实际监听 5678 的 Python PID `35108` 均为本轮新进程；`/health` 返回 `{"status":"ok","provider":"local"}`，`/api/quality/results` 返回批次 `20260830-guard-markdown`、15 条结果，`/test` 返回 `200` 且包含结果渲染标记。已将当前 `/test` 重新打开到 Codex 面板；内置浏览器自动连接仍因本机内核资产路径错误无法完成截图级验收。本轮未启动游戏、未构建或部署 DLL。

- 2026-08-30 修复 Bridge 输出格式防护的三类漏检：`ResponseGuard` 现在会拦截单星号、删除线和行首引用，并保留已有的加粗、反引号、标题和列表检测。TDD 先得到 `3 failed, 16 passed`，实现后 `bridge/tests/test_guard.py` 为 `19 passed`；Bridge 全量回归为 `342 passed in 5.73s`。补充启动契约测试先得到 `41 passed, 1 failed`，确认 `scripts/start_bridge.ps1` 缺少 UTF-8 BOM 后修复，`scripts/test_start_ai_npc_test.ps1` 为 `42 passed, 0 failed`，快速测试脚本回归为 `39 passed, 0 failed`，`git diff --check` 无差异错误。重启后的 Bridge 包装器 PID `14656`、实际监听 5678 的 Python PID `9560` 均为本轮新进程，父子关系已核对；`/health` 返回 `status=ok`、`provider=local`，`/test`、`/test/chat`、`/raw` 均为 `200` 且包含 `data-ui-shell="v4"`。使用中文联合索引和隔离 Ollama `qwen3.5:9b` 重跑固定 15 例，结果为 `15 successful / 0 errors / 13 passed`；剩余 Sophia、Alex 各 1 例是重试后仍有 Markdown 噪声，现已正确标记 `format_noise`，不再误计为通过。工件为 `artifacts/character-quality-eval/20260830-guard-markdown`。本轮未启动游戏、未构建或部署 DLL。

- 2026-08-30 在共享格式重试之后继续收紧 Prompt：新增“天气、时间和地点是当前场景的硬事实，但不要为了显得贴合而硬塞”、续聊优先满足 `historyAnchors`、同一句避免无必要重复名词等约束。新增测试先得到 `2 failed`，压缩提示词以保持原有 `<4000` 字符预算后，相关 Prompt 测试为 `56 passed`，Bridge 全量回归为 `339 passed in 5.51s`。使用相同中文联合索引和隔离 Ollama `qwen3.5:9b` 重跑 15 例，结果仍为 `15 successful / 0 errors / 13 passed`：Rasmodia `3/3`、Sophia `2/3`、Shane `3/3`、Sebastian `2/3`、Alex `3/3`。与上一轮相比 Shane 续聊已带回“饲料”对象；剩余失败是 Sophia、Sebastian 各 1 条重试后仍有 Markdown 噪声，属于格式失败，不等同于角色资料失败。新工件为 `artifacts/character-quality-eval/20260830-scene-hard-anchors`，未覆盖既有结果。重启后的 Bridge 包装器 PID `32068`、实际监听 5678 的 Python PID `30264`；`/health` 返回 `{"status":"ok","provider":"local"}`。当前 5678 的 Shane 续聊真实请求返回 `provider=local`、`fallback=false` 且明确提到“饲料”；Sebastian 雨天真实请求返回 `provider=local`、`fallback=false`，内容未否定雨天。内置浏览器连接仍因本机内核资产路径错误无法截图级验收，已将 `/test` 重新排入 Codex 面板；本轮未启动游戏、未部署 DLL。

- 2026-08-30 在上一轮统一工作台基础上，将固定质量评测的输出处理与真实 Bridge 对齐：新增共享 `retry_for_format_noise`，Bridge 与 `scripts/run_character_quality_eval.py` 共用同一次格式重试规则；评测新增持续格式噪声失败标记，避免模型在重试后仍输出 Markdown 时被误计为通过。TDD 先得到格式重试缺口 `1 failed`、持续噪声判定缺口 `1 failed`，实现后定向回归为 `38 passed`，Bridge 全量回归为 `338 passed in 5.78s`。使用当前中文联合索引和隔离 Ollama `qwen3.5:9b` 重跑五角色×三场景，结果为 `15 successful / 0 errors / 13 passed`：Rasmodia `3/3`、Sophia `3/3`、Shane `2/3`、Sebastian `2/3`、Alex `3/3`；失败项分别为 Shane 续聊未带回“饲料”对象、Sebastian 重试后仍有 Markdown 噪声。新工件为 `artifacts/character-quality-eval/20260830-bridge-format-guard`，未覆盖旧工件。重启后的 Bridge 包装器 PID `13140`、实际监听 5678 的 Python PID `6164`；`/health` 返回 `{"status":"ok","provider":"local"}`，`/test` 为 `200`、`data-ui-shell="v4"`，15 个测试例可取；真实 Rasmodia 续聊请求为 `provider=local`、`fallback=false`、无警告。内置浏览器连接仍因本机内核资产路径错误无法截图级验收，已将 `/test` 重新排入 Codex 面板；本轮未启动游戏、未部署 DLL。

- 2026-08-30 修正统一工作台的视图选择器：此前部分共享 CSS 使用不存在的 `#view-cases` / `#view-chat` / `#view-raw`，现统一改为匹配真实的 `data-workspace-view` 属性。测试例浏览视图的导航、详情、场景条件、预置历史、覆盖面板和按钮字号提升到与聊天/原文页相同的阅读级别，并保留 1050px、700px 两档响应式布局。新增定向契约测试先得到 `2 failed` 和 `1 failed`，实现后为 `3 passed`；Bridge 全量回归为 `336 passed in 5.76s`。重启后包装器 PID `13692`、实际监听 `5678` 的 Python PID `32368` 均已加载当前代码；三个路由均为 `200`、`data-ui-shell="v4"`，实际请求仍为 `provider=local` 且无 fallback。未启动游戏、未部署 DLL。

- 2026-08-30 重新启动目标 worktree 的 Bridge 后，确认之前浏览器看到的 `data-ui-shell="v3"` 来自旧运行进程；包装器 PID `32784` 与实际监听 `5678` 的 Python PID `34488` 均已替换。当前 `/health` 返回 `{"status":"ok","provider":"local"}`，`/test` 返回同一份 `data-ui-shell="v4"` 单页工作台，包含 1 个共享上下文条、1 个工作台导航和 3 个内部视图。Bridge 全量回归为 `333 passed in 5.40s`。

- 2026-08-30 在统一工作台对应的本地 Bridge 配置上重跑五角色 × 三场景固定评测：`15 successful / 0 errors / 15 passed`，使用中文联合索引和隔离 `qwen3.5:9b`，总耗时约 9.2 秒。结果保存于 `artifacts/character-quality-eval/20260830-integrated-workspace-followup`，未覆盖旧工件。五个角色各 3/3 通过；其中 5 条回复出现 `**加粗**` 格式噪声，自动评分不能代替人工角色判断，下一轮继续处理输出格式和活人感。未启动游戏、未部署 DLL。

- 2026-08-30 将 Dialogue Lab 真正收敛为单页工作台：`/test`、`/test/chat`、`/raw` 现在返回同一份文档，案例浏览、单次聊天和原始对白是内部三视图；工作台导航通过 `showWorkspaceView()` 切换，不再因功能区点击发生页面跳转，旧路由只负责选择首次视图。为避免合并三段脚本后的 ID 冲突，原文参照选择器改为 `raw-npc-select` / `raw-npc-buttons`，聊天会话、案例、原文能力均保留。新增一体化路由、唯一 DOM ID、内部导航和多脚本语法测试；定向回归为 `57 passed in 1.54s`，Bridge 全量为 `307 passed in 5.32s`。重启后包装器 PID `19608`、实际监听 5678 的 Python PID `34592` 均为新进程；三个路由均返回 `200`、同一工作台标记和对应默认视图。内置浏览器连接仍因内核资产路径缺失无法完成截图级检查，已将 `/test` 重新置于 Codex 面板；本轮未启动游戏、未部署 DLL。

- 2026-08-30 按角色质量队列使用当前中文联合索引和隔离 Ollama `qwen3.5:9b` 重跑 15 个固定场景：`15 successful / 0 errors / 7 passed`；按角色为 Wizard/Rasmodia `1/3`、Sophia `1/3`、Shane `1/3`、Sebastian `3/3`、Alex `1/3`。结果保存于 `artifacts/character-quality-eval/20260830-integrated-ui-followup`。本轮结果说明 Sebastian 的现有约束较稳定，但其他角色仍有期望证据未命中，不能把自动分数当成人工角色质量达标；未修改模型、未把生成结果写回角色示例。

- 2026-08-30 完成 Dialogue Lab 三页 UI 统一：`/test`、`/test/chat`、`/raw` 现在共享版本化 `data-ui-shell="v1"`、米白/森林绿主题、工作台顶栏、三项导航和当前页高亮；保留测试例浏览、单次聊天会话、原始对白筛选等既有功能。共享主题通过 `dialogue_lab_page.py` 的 `_with_shared_ui` 注入，避免重复维护三套主题；700px 以下改为可访问的单列滚动布局。新增页面契约测试先得到 `1 failed`，实现后定向页面/API 回归为 `55 passed in 1.39s`，Bridge 全量测试为 `305 passed in 5.22s`，三页内嵌 JavaScript 均 `node --check exit=0`。重启后包装器 PID `29000`、实际监听 5678 的 Python PID `10672` 均为本轮新进程；`/health` 返回 `status=ok`、`provider=local`，三个页面均返回 `200` 且包含全部共享壳层标记。内置浏览器自动控制仍因运行时内核资产路径异常无法完成截图级检查，已将 `/test` 重新请求到当前 Codex 面板；本轮未启动游戏、未部署 DLL。

- 2026-08-30 完成 `/test` 测试例浏览器原型的代码回归：默认页展示现有 15 个脱敏质量测试例，保留 `/test/chat` 单次聊天入口；案例目录按五个固定角色、日常状态、远程/当面渠道和上下文续聊分类，并展示关系阶段、预置历史、期望词与禁止词。新增嵌入 JavaScript 语法回归测试，先复现 `renderCaseDetail()` 的模板字符串错误，再修复缺失反引号和 Python 三引号导致的嵌套引号问题；页面/API 定向测试实际为 `53 passed in 1.44s`，Bridge 全量测试实际为 `303 passed in 7.15s`，三段嵌入脚本静态检查均为 `exit=0`。目标 Bridge 已重启，包装器 PID `27412`、5678 实际监听子进程 PID `33336` 均为本轮新进程；`/health` 返回 `provider=local`，`/api/quality/cases` 返回 `schemaVersion=1`、15 例，`/test`、`/test/chat` 均为 `200` 且页面标记正确。已请求将 `http://127.0.0.1:5678/test` 打开到当前 Codex 面板；内置浏览器自动控制因运行时内核资产路径异常仍未完成点击和截图级验证，本轮未启动游戏、未部署 DLL。

- 2026-08-29 浏览器实测复核：在当前 `http://127.0.0.1:5678/test` 重新载入干净批次，五个固定角色各完成 3 轮连续当面聊天，共 30 条消息；15 次真实请求全部为 `provider=local`、`fallback=false`，浏览器重新加载后 Rasmodia 的 3 轮记录可见。初识（0 心）下 Shane 已表现为“挺忙的 / 我不累，不用你操心 / 行，别杵在那儿了”的短促冷淡边界；但 Rasmodia 仍出现“躯壳”等不自然措辞，Sophia 仍有葡萄藤内容机械回扣，说明通用阶段策略已进入运行链路但角色质量尚未达到满意标准。浏览器自动点击控制因 Codex 浏览器运行时临时内核路径异常未完成，页面渲染读取和当前网页展示已完成；本轮未启动游戏。

- 2026-08-29 总回归复核：Bridge 全量测试实际为 `294 passed in 7.10s`；SMAPI 全量测试实际为 `168 passed, 0 failed`。`5678/health` 实际返回 `status=ok`、`provider=local`，`/test` 返回 HTTP `200` 且包含固定五角色按钮；`git diff --check` 退出码为 `0`。本轮未启动游戏、未部署 DLL；当前构建 DLL SHA-256 为 `08D9E0E19D6826780ACAAA4F60C5DE1E6F1A5B02B8106FD06086275B1107990A`，快速测试目录仍为 `D5E68E542E79B3AA4E58B98ED628DF36BBF6B82C8C86B3FCB466C32DE9A357E0`，Stardrop 完整 profile 仍为旧哈希 `05169C0A30FCD9EAE9BE446CC160A08BDF3F79F999024E20F92570C0C9F1D2EA`；游戏端历史跨 SMAPI/游戏重启持久化仍未完成。

- 2026-08-29 新增测试网站“原始对白参照”：`GET /api/dialogue/raw?npcId=...` 返回当前 canonical NPC 的全部已解析对白、来源文件、`sourceKey`、来源 Mod 和关系条件；`/test` 右侧显示规则筛选的 8 条置顶代表对白及可按文本/来源/条件筛选的完整列表，原文不会进入模型请求。补充页面、API、NPC 切换和来源保留测试；代表区回归曾发现 `pamHouseUpgrade` 被误当普通对白，已纳入特殊触发分类并让代表区复用过滤规则。Bridge 全量测试实际为 `294 passed in 6.98s`；重启后 `5678/health` 返回 `200`、`provider=local`，Sophia 实际返回 `148` 条原文且置顶 8 条不含 `pamHouseUpgrade`，浏览器已验证切换角色后面板显示正确。置顶样本是可解释的参照，不是人工最终标准；游戏端历史跨重启持久化仍未完成。

- 2026-08-29 完成远程/当面聊天渠道约束：`prompts.py` 会把 `remote` 明确限定为手机或线上聊天，禁止写成已经见面、走过来或当面发生；把 `face_to_face` 明确限定为当前同地点的当面聊天，禁止写成发消息或线上约定。`/test` 增加“当面聊天 / 远程（手机/线上）”选择，并将当前渠道写入请求。新增回归测试先得到 `1 failed`，实现后为 `1 passed`；Bridge 全量测试实际为 `274 passed`，网页渠道测试随后为 `2 passed`。重启后的包装器与 Uvicorn 子进程均加载了新代码，`5678/health` 返回 `200`、`provider=local`，真实远程邀约请求没有生成已经赴约的动作，真实当面请求保持为当面语境。使用本地 `qwen3.5:9b` 重跑固定 15 场景，结果为 `15 successful / 0 errors / 10 passed`；按渠道为远程 `6/6`、当面 `4/9`。新工件为 `artifacts/character-quality-eval/20260829-channel-constraints-9b`。当面场景剩余失败主要是 Sophia、Shane、Sebastian 的期望事实词命中不足，不能据此宣称角色质量已经满意。游戏端历史跨 SMAPI/游戏重启持久化仍未完成，也未启动游戏。

- 2026-08-28 补完角色扮演模型社区路线核验：通过 SillyTavern 官方 API 说明、Hugging Face 模型页和 OpenRouter 公开模型页确认，Euryale、Stheno、Aion-RP、Aion-3.0-Mini、Cydonia 等确实属于公开使用的角色/创作模型家族；其中 Euryale、Aion-3.0-Mini、Cydonia 的 OpenRouter 页面可见 SillyTavern 流量代理。已明确区分“公开使用信号”与“质量排行榜”，并确认没有可靠证据证明某个模型对中文 Stardew NPC 一定最好。项目建议仍为：`qwen-plus-character` 做中文角色专用首测，Euryale 或 Aion-3.0-Mini 做社区角色模型对照，本地 `qwen3.5:9b` 保持默认；本轮未使用云端密钥、未发送项目资料、未切换模型。

- 2026-08-28 完成隔离浏览器中的五角色真实本地模型复核：在 `http://127.0.0.1:5679/test` 使用 `qwen3.5:9b`，固定按钮分别切换 `Rasmodia / Wizard`、`Sophia`、`Shane`、`Sebastian`、`Alex`；每个角色切换后先显示独立空记录，随后完成 3 轮连续对话（每个角色 6 条消息），追问均承接上一轮的葡萄藤、鸡舍、摩托车、跑步或研究数据等细节。逐个切回核对均为 6 条记录；刷新页面后 Rasmodia 的 6 条记录仍恢复。五个角色请求均显示 `provider=local`、无 fallback。`5679` 与用户原有的 `5678` 均实际返回 `/health` `200`、`provider=local`；临时会话 API 返回 `version,messages,history,lastDiagnostics`，共 30 条消息，未发现 `apiKey/token/prompt`。本轮 Bridge 全量测试使用 Python 3.10 实际为 `251 passed in 6.38s`。截图验收显示五角色按钮、Rasmodia 记录和诊断卡片均正常；游戏端历史跨 SMAPI/游戏重启仍未实现，未启动游戏。

- 2026-08-28 排查并修复 Bridge 重启后无法监听 5678 的启动故障：原启动脚本只判断 Codex 内置 Python 文件存在，但该 Python 缺少 `fastapi`/`uvicorn`；现在两个启动入口都会探测 Python 版本与完整运行依赖，并从本机 Python 安装目录选择可运行解释器。TDD 回归先得到 `36 passed / 5 failed`，修复后为 `41 passed / 0 failed`；Bridge 全量测试实际为 `218 passed`。真实启动后包装器仍在运行、Uvicorn 实际绑定 5678，`/health` 返回 `200`、`provider=local`，`/test` 返回 `200`；Ollama 最小请求返回 `200`，首次加载约 7.9 秒。恢复后的五个真实请求均为 `provider=local`、`fallback=false`，耗时约 2.8–4.1 秒（首次完整 Rasmodia 请求约 11.9 秒）。本轮仍只验证网页/Bridge 链路，未启动游戏，也未把旧网页会话中的 fallback 记录当作新模型结果。

- 2026-08-27 完成本轮五角色口语风格收紧：Wizard/Rasmodia 统一为 canonical `Wizard`，保留 Romanceable Rasmodius 的显示名与语气覆盖；Prompt 增加口语长度、避免机械拼接开场/收尾、避免书面化总结，以及日常输入不把地点/语料主题自动升级为话题的约束；对应全量 Bridge 测试实际为 `205 passed, 1 warning`。
- 2026-08-27 复核角色行为示例落盘：重建默认中文联合索引后实际为 `94 profiles / 7,108 styleSamples / 7,108 speechEvidence / 40 behaviorExamples / 4 knowledgeFacts / 65 warnings`；`behaviorExamples` 为 Wizard、Sophia、Shane、Sebastian、Alex 各 8 条，Wizard/Rasmodia 仍只有 canonical `Wizard`。本轮 Bridge 全量测试实际为 `213 passed, 1 warning`；重启后的 `5678` 服务 `/health` 返回 `200`、`provider=local`，五个 `/api/context/preview` 均返回匹配主题的行为示例。
  本轮使用新的临时评测会话文件和 60 秒本地模型超时完成干净浏览器样本，五个角色均由 `local` 返回：Rasmodia `52.6s`、Sophia `49.4s`、Shane `44.5s`、Sebastian `43.1s`、Alex `53.1s`；实际回复分别体现克制研究、葡萄酿造、鸡舍行动、低情绪短答和外向行动。评测会话 API 聚合核对为 `version=1`、10 条消息、五个角色各 2 条，未包含 `apiKey/token/prompt`。浏览器刷新后的逐个可视化点击在本轮被内置浏览器安全策略拦截，因此不把它记为已完成的可视化刷新证据；原有用户会话文件未删除或覆盖。
- 2026-08-27 重建 `vanilla-sve-rasmodia-profile-index-zh-CN.json`，实际输出为 `94 profiles / 7,108 styleSamples / 7,108 speechEvidence / 4 knowledgeFacts / 65 warnings`；核对确认 `Wizard` 是唯一 canonical 语料键，独立 `Rasmodia` profile/voiceCard 不再生成。
- 2026-08-27 重启目标 worktree 的 Bridge 包装器与 5678 Python 子进程；`GET /health` 实际返回 `{"status":"ok","provider":"local"}`，`GET /test` 实际包含合并按钮与 Alex。浏览器端用本地 `qwen3.5:9b` 完成五角色连续小样本，刷新后记录仍恢复：`Rasmodia / Wizard 138`、`Sophia 68`、`Shane 68`、`Sebastian 76`、`Alex 16`。本轮只验证网页/Bridge 角色风格，未启动游戏，也未实现游戏端 `BridgeClient.historyByNpc` 跨重启持久化。
- 完成 SVE CP 与 Romanceable Rasmodius SVE 的本机来源确认；
- 完成 Content Patcher i18n 语言回退与 `resolvedText` 解析；
- 完成动态 i18n 候选集保留，避免把随机/季节/事件分支伪装成唯一台词；
- 使用官方 XNB 解包工具补齐原版 `Characters/Dialogue`（624 个语言文件），并校验全量 vanilla + SVE 联合 index；
- 生成并校验 SVE corpus、SVE profile index、原版（`zh-CN`）+ SVE + RomRas 联合 index；原版其他语言只保留在本地审计工件，不混入中文模型上下文；
- 主中文索引当前为 94 profiles / 7,108 style samples / 7,108 speech evidence；带 1 条运行时校验样本的检查索引为 7,109，已确认运行时样本优先且没有未解析 i18n 模板。
- 完成运行时动态对白 JSONL 记录格式、去重和索引接入，并用 Claire 婚后分支完成 1 条小样本验证；
- SMAPI 原版 `DialogueBox` 观测器与日志导入器已接通；检索层过滤未解析模板，并优先使用 `runtime_dialogue` 样本；
- 运行时导入器已增加保守归属：仅在 NPC、`sourceKey`、已解析文本三者唯一命中 corpus 时补回 `sourceMod/sourcePath`，歧义样本保持 `runtime.unattributed`；
- 完成 Wizard/Rasmodia 首轮来源分层：中文原版 24 条、SVE 131 条、Parrot.RomRas 720 条；语气特征和关系阶段边界已写入报告，等待真实动态样本做最终复核；
- Python 测试 160 passed，SMAPI 测试 168 passed；新增 `FrameRateSampler`、`TaskResultPump`、`ChatTextLayoutRules` 和 `ChatScrollRules` 单元测试覆盖窗口计数、FPS 计算、参数校验、后台请求结果由游戏主循环轮询、长回复换行和边界截断、多条长气泡时优先保留最新消息，以及滚动位置夹紧和方向移动。SMAPI Debug DLL 已成功构建，构建与 profile DLL SHA-256 均为 `D5E68E542E79B3AA4E58B98ED628DF36BBF6B82C8C86B3FCB466C32DE9A357E0`。
- 快速测试启动器补上 UTF-8 BOM 后，Windows PowerShell 回归测试 39 passed；`Mods-AI-FastTest` 已同步 Rasmodia 依赖、主循环轮询聊天修复、文本布局修复和聊天滚动修复，profile DLL 与构建 DLL SHA-256 均为 `D5E68E542E79B3AA4E58B98ED628DF36BBF6B82C8C86B3FCB466C32DE9A357E0`，并已重启游戏加载该 DLL。
- 游戏外素材预览工具测试 4 passed；使用 `-p no:cacheprovider` 后 Bridge 全量测试 160 passed，避免工作树 `.pytest_cache` 权限告警影响退出判断。
- 新增本地浏览器 NPC 对话实验室：`/test` 已升级为宽屏三栏布局，支持 NPC/来源 Mod/关系阶段/时间地点/好感度编辑、自动/Fake Provider 切换、连续多轮历史、主动找话题、诊断信息、上下文摘要、脱敏请求预览、清空会话和 JSON 导出；新增页面契约测试 3 passed。真实 Bridge HTTP 检查返回 `/health` 200、`/test` 200、15 个 NPC，连续两轮 Fake 演示成功承接“已聊过 2 条消息”；浏览器截图已完成视觉检查。
- 网页端会话持久化已改为本机 JSON：页面通过同源 `/api/dialogue/session` 读写，默认保存到 `%TEMP%\StardewAI.NPC\dialogue-lab-session.json`，也可用 `BRIDGE_DIALOGUE_SESSION_PATH` 覆盖；保存内容仅包括 `version`、`messages`、`history` 和脱敏 `lastDiagnostics`，不使用浏览器 `localStorage`，不保存 `lastPayload`、API key、Token、完整 prompt 或敏感请求字段。损坏文件会备份为 `.corrupt*` 后恢复空会话，写入使用临时文件原子替换；成功回复后保存，初始化时恢复，清空时删除本地文件。页面定向测试 `21 passed, 1 warning`，Bridge 全量测试 `193 passed, 1 warning`；浏览器已验证重启 Bridge 后仍有五个角色各 60 条记录，刷新后 Rasmodia 记录仍恢复。该能力只解决网页实验室会话，不等同于游戏端 `BridgeClient.historyByNpc` 跨重启持久化。
- 修复网页实验室快捷切换误回退到 API 字母序前五名的问题：评测按钮固定为 `Rasmodia / Wizard`、`Sophia`、`Shane`、`Sebastian`、`Alex`，并按当前 canonical `npcId` 隔离记录；没有当前角色记录时显示明确空状态。针对内置浏览器窄窗口又改为紧凑三栏布局，避免场景面板被压缩导致按钮不可见；页面定向测试和浏览器逐个切换验证已在后续角色风格回归中更新。
- 网页端真实对话已接通：`start_bridge.ps1` 与 `start_ai_npc_test.ps1` 默认注入隔离 Ollama（`http://127.0.0.1:11435/api/chat`、`qwen3.5:9b`、`api_mode=ollama`），环境变量仍可覆盖；入口脚本回归测试 36 passed，Bridge 全量测试 157 passed。重启 Bridge 后 `/health` 报告 `provider=local`，`POST /api/dialogue/test` 返回 `fallback=false` 的真实中文模型回复；内置浏览器 `/test` 已完成一次端到端发送验证。
- Bridge 资料索引接线已修复：新增 `BRIDGE_PROFILE_INDEX` 配置，两个启动入口在文件存在时默认加载已解析的 `vanilla-sve-rasmodia-profile-index-zh-CN.json`，保留旧 `profile-index.json` 作为回退；索引路径解析和启动脚本回归测试通过，重启后的 `/api/context/preview` 已返回 8 条风格证据，证明新索引已进入运行进程。由于完整索引使本机冷启动超过原 5 秒默认值，local Provider 默认超时同步提高到 15 秒，并用真实请求验证不再 fallback。
- 本地模型基准现已与 Bridge 使用同一份解析索引：`benchmark_local_models.py` 支持 `--profile-index`，默认读取 `BRIDGE_PROFILE_INDEX` 或中文联合索引，并同时携带 SMAPI UniqueID 以匹配 SVE/RomRas 证据；160 项 Python 回归通过。修正“Mod 专属证据被 vanilla 挤掉”后，使用隔离 Ollama `11435` 真实重跑 7 个 Rasmodia 场景：4B 为 5/7、0 错误、平均 2.81 秒，9B 为 7/7、0 错误、平均 4.39 秒；流式指标约为 4B 94.77 tok/s、9B 63.68 tok/s。结果保存于 `artifacts/model-benchmark-resolved-20260826.json`，文件明确记录了 `vanilla-sve-rasmodia-profile-index-zh-CN.json`，SHA-256 为 `C62E048FB1491BD6DCC43708FA5A1E0B07F9BA8B3C135EB803E135529C5A1379`。
- 新增 `OllamaNativeProvider` 和 `BRIDGE_LOCAL_API_MODE=ollama` 配置，原生 `/api/chat` 固定发送 `stream:false`、`think:false`；Bridge 全量测试回归 142 passed。
- 新增 Rasmodia 固定上下文评测用例（初识、SVE、朋友、亲近、Roommate/婚后、同日续聊、未触发事件边界）及 `scripts/benchmark_local_models.py`，用于统一比较本机模型；评测默认要求期望证据词至少命中 1 项，并拦截未触发事件的矛盾完成断言。
- Ollama 0.32.15 已安装到用户程序目录；本项目使用的隔离服务通过 `OLLAMA_MODELS=D:\OllamaModels` 运行，C 盘默认模型目录当前为 0 字节；`qwen3.5:4b` 与 `qwen3.5:9b` 均已完成下载并通过隔离服务加载验证，9B 本轮实际驻留约 5.49 GB。
- `qwen3.5:4b` 已完成真实 Rasmodia 基准：7 个固定场景全部返回、0 错误，按最新证据词/边界规则 6/7 通过，平均延迟约 2.56 秒；`qwen3.5:9b` 完成同一套场景，7/7 通过、0 错误，平均约 3.72 秒。9B 在同日续聊场景明确保留了咖啡细节，4B 该轮只用“它”承接而未命中证据词。原文和评分分别保存到 `artifacts/model-benchmark-qwen3.5-4b.json` / `artifacts/model-benchmark-qwen3.5-9b.json`，SHA-256 分别为 `D6AED9289F16042C1BF4C993892B72984E3F76BC4C7EE4314F6B8C3EE013CDCF` / `A1F688AEAFDB1AF927ED079F1F40FF673C373E2BDA3DB03373D2449D24CFEB6F`。
- 流式性能工件已完成：4B/9B 均为 7/7、0 错误；排除首个冷启动请求后，4B 首段内容延迟约 321 ms、约 96.68 tok/s，9B 约 420 ms、64.22 tok/s。首次加载约 4.38 s/7.11 s。工件分别为 `artifacts/model-stream-metrics-qwen3.5-4b.json` / `artifacts/model-stream-metrics-qwen3.5-9b.json`。
- 本地模型选型报告已回写 4B/9B 实测结果、隔离 Ollama 服务地址和两份模型工件 SHA-256，避免继续使用“尚未启动真实 Ollama”的旧结论。
- 新增可选游戏内帧率诊断：`EnablePerformanceDiagnostics=true` 时按 5 秒窗口记录 `[StardewAI.Perf] windowMs=...; renderedFrames=...; fps=...`，默认关闭，不改变普通运行路径；采样器已通过单元测试。
- 已在隔离 FastTest 标题/菜单画面完成一轮并行采样：4B、9B 请求期间均保持 60 FPS，响应均为 `provider=local` 且未 fallback；原始请求耗时和场景限制保存于 `artifacts/game-parallel-model-performance-20260826.json`。这不是最终农场聊天结论，仍需进入存档后采样。
- XNB 临时工具与 `Content (unpacked)` 已从游戏目录移除；当前 `SMAPI-latest.txt` 尚未出现 `StardewAI.RuntimeDialogueSample` 标记，因此真实运行时样本仍待下一次游戏会话采集。

## 当前队列

1. 在实际存档、聊天菜单打开的并行场景测量 9B/4B 的帧率影响（标题/菜单基线已完成，首段延迟和生成速度也已完成独立流式测量）；
2. 对刚完成的解析索引基准结果做人工复核，并按需要再补一轮 4B/9B Rasmodia 用例，重点检查角色一致性与事实边界；
3. 在下一次正常游戏运行中采集第一批真实动态分支，运行导入器的 `--corpus` 归属流程，核对 `sourceKey` 与 corpus 候选的映射；
4. 用真实运行时样本复核 Wizard/Rasmodia 的动态分支、sourceKey 映射和关系阶段边界；
5. 完成资料库和运行时 Mod 的整体回归、构建与部署核验。

## 下一步操作（真实动态样本）

启动前检查已完成：`Mods-AI-FastTest` 存在，profile DLL SHA-256 与构建 DLL 一致（`D5E68E542E79B3AA4E58B98ED628DF36BBF6B82C8C86B3FCB466C32DE9A357E0`），当前 `SMAPI-latest.txt` 尚无运行时样本标记。

下一次游戏会话按以下顺序执行：

1. 使用 `scripts/start_fast_test.ps1 -IncludeRasmodia -Launch` 启动独立 profile；
2. 进入独立测试存档，分别让 Wizard/Rasmodia 打开一次原版对白，再结束游戏；
3. 运行 `scripts/import_smapi_runtime_samples.py --log <SMAPI-latest.txt> --corpus data/generated/sve-dialogue-corpus.json --output artifacts/corpus/runtime-dialogue-samples.jsonl`；
4. 以 `--runtime-samples artifacts/corpus/runtime-dialogue-samples.jsonl --vanilla-locale zh-CN` 重建检查索引，核对 `sourceKey`、`sourceMod` 归属和关系阶段过滤。

## 当前停止条件

队列中的资料采集、动态分支处理、Rasmodia 回归和最终验证全部完成，或遇到需要用户决定的真实外部阻塞。完成一个阶段后必须继续下一个阶段，并在汇报中明确下一步。

- 2026-09-01 完成高好感案例与表达变化卡这一轮：案例浏览页新增“高好感、初识、熟悉、朋友、亲近、恋爱、婚后、育儿”筛选，列表显示关系阶段和好感度心数，覆盖面板显示高好感案例数；详情页增加表达变化提示，旧批次没有质量字段时明确显示“未检测”。新增 `dialogue_style_quality.py` 纯函数，只检测重复语气词与重复开场，不改写回复；Prompt 在真实历史之后、当前玩家输入之前增加 `voice_variation` 卡，语气词改为可选并禁止连续重复；评测脚本为每轮写入脱敏 `styleQuality`，结果接口仅保留安全标签、计数和短开场。定向回归实际为 `189 passed`，Bridge 全量回归实际为 `496 passed in 13.60s`。重启 5678 后 `/health` 返回 `200`、`provider=cloud`，`/test` 返回 `200` 且包含阶段筛选、高好感覆盖计数和质量提示标记，`/api/quality/cases` 仍为 23 例（`close=7`、`married=1`）。本轮未发起云端生成、未修改旧评测工件、未启动游戏、未部署 DLL；内置浏览器连接仍因内核资产路径异常未能完成点击/截图级验证，已用 HTTP 页面和嵌入 JavaScript 语法测试确认服务端页面有效。
