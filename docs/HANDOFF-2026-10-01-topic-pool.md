# 交接 · 星露谷话题池（story-memory worktree）

> 写给下一个会话。读完这份就能接手，不需要回看旧对话。
> 落档时间：2026-10-01。作者：上一个 DSH 会话。

---

## 〇、一句话现状

**「补其他角色素材」这件事已经做完了**（数据层、面覆盖层都做完，有测试守着）。
真正没解决的只剩一个：**每轮 prompt 只暴露 12 条话题，相邻轮次重叠 91.9%** —— 用户
「话题少了、想要多一个数量级」的感受来自这里，**不来自数据不足**。

本次会话新增的净产出是一批**诊断结论**和**一次已回滚的错误**（见 §5，务必看）。
除交接文档外**没有新的代码提交**。

---

## 一、环境（照抄即可）

```powershell
$wt = 'E:\workspace\projects\stardew-ai-npc.worktrees\story-memory'
$py = 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe'

$env:PYTHONIOENCODING = 'utf-8'          # 不设会在打印中文/✓ 时崩 GBK
$env:PYTHONPATH = "$wt;$wt\bridge\src;$wt\scripts"
Set-Location $wt
```

- Python **3.10.8**，PATH 里没有 `python` / `python3` / `pytest`，必须用上面的全路径。
- 前端在 worktree `story-memory`，分支 `codex/story-memory`，**领先约 246 个提交、一个都没 push**。
- 主库 `E:\workspace\projects\stardew-ai-npc` **落后**，别在那儿改。

### 基线测试（改任何东西后必跑）

```powershell
& $py -B -m pytest bridge/tests -q -p no:cacheprovider --tb=line
```

- HEAD 基线：**4390 passed / 约 200 s**。
- 4481 个用例只需 190 s，不用后台跑，等得起。

### git（每条命令都要带 safe.directory）

```powershell
& git -c safe.directory=$wt -C $wt status --porcelain
& git -c safe.directory=$wt -C $wt diff --stat
& git -c safe.directory=$wt -C $wt log --oneline -8
```

提交用：`-c user.name=dsh -c user.email=dsh@local`，`-F <文件> --no-verify`。
**永远不要 `git config --global`。**

---

## 二、已落地的提交（都已提交，别再动）

| commit | 内容 |
|---|---|
| `e4914cb` | Alex 扩到 11 条 —— **用户明确说「接受 11 条，别改坏了」，Alex 已冻结，永不重开** |
| `fc2b45e` | prompts.py + test_prompts.py（话题窗口相关） |
| `a7ca447` | `rasmodia.json`：Wizard/Rasmodia 的 `preferredTopics` 6 → 44 |
| `124052c` | （见 git log） |
| `6768a28` | `character_quality_eval.py`，4603 行 |
| `f68fb51` / `7a2bddf` | （见 git log） |
| `d01bec9` | **A2 rotation 代码**：`_topic_window_for_turn` + `_PREFERRED_TOPICS_LIMIT` |
| `dedcd06` | （见 git log） |
| `a17cd45` | 长度放宽：`_LENGTH_RETRY_THRESHOLD = 68`（删掉 `_LENGTH_RETRY_RATIO`） |
| `abed6f5` | 两个长度探针脚本 |
| `84490cc` | `docs/STATE.md` 346 → 401 行 |

hub 仓库：`a8f86a9`、`5ba3f90`、`47fb354`。

---

## 三、本次会话确认的关键事实（新会话不必重新验证）

### 3.1 官方审计脚本给出了权威口径

`scripts/probe_preferred_topics_audit.py`（仓库自带，**调真实函数**，比我临时写的统计权威）：

```powershell
& $py -B scripts\probe_preferred_topics_audit.py --gaps
```

输出：

```
_PREFERRED_TOPICS_LIMIT = 12   roleGuidance 截断线 = 240
含 {topicPool} 的模板表：['Alex','Elliott','Harvey','Sam','Sebastian','Shane','Sophia','Wizard']

角色数：50   总条数（可见）：597
缺口（3 条）：
  Wizard    缺 1 条  (rasmodia.json)
  Rasmodia  缺 1 条  (rasmodia.json)   ← 与 Wizard 是同一个 profile
  Alex      缺 1 条  (vanilla.json)    ← 冻结
```

**597 = 47×12 + 11×3**，即 50 个角色里 **47 个可见池已经满了**。

### 3.2 `_PREFERRED_TOPICS_LIMIT = 12` 是被 240 字倒逼出来的

- 定义：`prompts.py:3216`。消费点：`prompts.py:3244`（`_topic_window_for_turn`）、
  `prompts.py:3285`、`prompts.py:3305`（`_compact_voice_style` 字段表）。
- `stage_policy.py` 的 `_compact_conversation_lead` 有 `GUIDANCE_LIMIT = 240` 的
  **静默截断**：超了不报错、也不红测试。
- 8 个 conversationLead 角色（Alex/Elliott/Harvey/Sam/Sebastian/Shane/Sophia/Wizard）
  的 roleGuidance 里塞 `{topicPool}`，**Alex 正好 240 字，顶格**。
- ⇒ 12 条 × ~20 字 ≈ 240 字。**提高全局 limit 会先把这 8 个角色截断。**
- 另外 36 个角色走 `persona_core` 路径（`prompts.py:1810`
  `_identity_voice_style["preferredTopics"]`），**不受 240 字直接限制**。

### 3.3 rotation 是真实生效的，但对「模型看到多少」帮助有限

`_topic_window_for_turn(value, turn_index)`（`prompts.py:3216` 附近）：

```python
size = _PREFERRED_TOPICS_LIMIT
if len(items) <= size: return items          # 池 ≤ 12 时原样返回，rotation 是静默 no-op
start = int(turn_index) % len(items)
return [items[(start + step) % len(items)] for step in range(size)]
```

**实测仿真结果**（`_sim.py`，用真实函数）：

| 指标 | 值 |
|---|---|
| 平均邻轮重叠 | **11.0 / 12 条 = 91.9%** |
| 20 轮内去重后看到的话题 | 1154 / 1374 条（84%） |
| 单轮可见 | 恒为 12 条 |

⇒ **每一轮模型只看到 12 条，其中 11 条与上一轮相同。** 这是「话题少了」的机制。

### 3.4 面覆盖也已做完

- `test_topic_slot_rotation.py:1261` `BELOW_THREE_FACET_ROLES = frozenset({"Marlon"})`。
- 第 5 批注释原文：Marlon「**不是"还没做"，是做不了**」（6 个面的 own 命中全 0）。
- 该文件 L1254 还记着：Birdie 已按用户口径**删除**（`SocialTab=HiddenAlways`）。
- **不要再挖 Marlon 的语料。**

### 3.5 `_pick` 的筛选顺序（`stage_policy.py:1420`）

```python
def _pick(allow_used, *, skip_spoken=True, rotated=True):
    for topic in (scan if rotated else topics):
        facet = _facet_of_topic(topic)
        if not facet or facet == banned: continue     # 无面 / 被禁的面 直接跳过
        if skip_spoken and topic in spoken: continue
        if not allowed_used and facet in used: continue
        return topic, facet
    return "", ""
```

三级降级：`_pick(allow_used=False)` → `_pick(allow_used=True)` → `_pick(allow_used=True, skip_spoken=False)`。
⇒ **无面素材会被跳过**，所以「窗口里有足够多有面素材」是硬要求，
由 `test_every_role_keeps_enough_faceted_material_in_every_window`（L1186）守着。

---

## 四、用户口径（原话，别再违反）

- 「主要是要**自然一点，像真实对话，也要像这个人该说的话**」（第 7 批的起因）
- 「完全没有魔法词这人感觉缺点味道，**降低频率就行**」
- 「日常闲聊时也该偶尔冒一点**魔法味**才对，改吧」⇒ 日常保留**恰好 1 条**魔法话题
- 「alex 接受 11 条吧，他是做得比较好的，**别改坏了**」
- 「23 的话改测试该改就改，在错误的测试标准下修改白干活的事情我们干过不少了」
  ⇒ **授权更新陈旧断言**，但仅限「断言确实错了」，不是「改不动就改测试」
- 「别惦记那个什么 10.1 了，用就是，不够了我再充个号」⇒ **成本不是约束**
- 「**长短不是 prompt 可以控制的，这个更像模型的固有秉性**，你觉得呢」

  实测反驳：A2 是**运行时重试**而非 prompt，且稳定地把「超 68 字」从 ~27% 压到 9%。
  但 `character_quality_eval.py` **没有任何长度判据**，所以 A2 对 eval 分数贡献为 0，
  只影响玩家看到的回复长度。这是产品取舍，不是技术问题。

---

## 五、⚠️ 本次会话犯的错误（新会话务必先看这段）

### 5.1 我把「第 7 批还原的原话」又改回了名词短语 —— 已回滚

**经过**：我扫出 45 条「像台词的长条目」，判定为「台词混入污染落点池」，
写了脚本把其中 41 条改写成名词短语。改完跑全量测试，**9 个用例失败**：

```
FAILED test_restored_material_is_the_original_line_and_keeps_its_facet[Emily/Dwarf/Jas/Kent/Robin/Vincent/Abigail]
FAILED test_every_role_keeps_enough_faceted_material_in_every_window
FAILED test_roles_lifted_to_five_facets_are_recorded
```

**真相**：`test_topic_slot_rotation.py:1371-1418` 有一整段设计文档 ——
**第 7 批（2026-09-23）专门把「为绕开词表而改写的字面」还原成原话**，
理由是用户那句「要像这个人该说的话」，而且
**「原话才是最像这个人说的话的那个版本」**。

常量 `RESTORED_TO_THE_ORIGINAL_LINE` 逐条钉住 8 条还原素材，判据是
`_facet_of_topic` 回测「预期面没变才还原，变了就保留」。两类要分开：

- **A 类 = 当初只为绕开词表** ⇒ 还原；
- **B 类 = 原话里的副面词会抢走主面**（`雾在毯子里看电视` 带「下雨」漂到天气面、
  Clint 的「铁匠」漂到工作面）⇒ **保留改写**，那是有意设计。

**教训**：**改数据前先读守着它的测试。** 这个仓库的设计文档就写在测试注释里，
我跳过了这一步，按「看起来像脏数据」直接动手。上次的 4390 passed 正是在守这条线。

**已执行**：`git checkout -- data/personas/{vanilla,sve,female-bachelors}.json`，
`git diff` 已确认为空。**数据完好，无需再做任何补救。**

### 5.2 两个脚本 bug（都已修，但同类错误要小心）

1. **布尔判断写反**导致角色区间识别 0 个，脚本却在结尾打印「全部命中」——
   **什么都没做却报告成功的失败模式**。修法：两阶段（先全部匹配 → 断言通过 → 才落盘）。
2. MISS 判定按文件独立报，导致「某条只在 `female-bachelors.json` 里」被误报为未命中。
   修法：按 `(角色, 原句)` **全局**判定。

### 5.3 一条原则

**改 persona JSON 时必须按行定向替换，不要 `json.dumps` 重写整个文件。**
`vanilla.json` 有 8030 行、CRLF 换行、10 空格数组缩进；
整体重排会让 diff 爆炸、且容易弄丢 CRLF。

正确的读写模式：

```python
raw = p.read_bytes().decode("utf-8")
nl = "\r\n" if "\r\n" in raw else "\n"
lines = raw.split(nl)
# …改 lines[i]…
p.write_bytes(nl.join(lines).encode("utf-8"))
```

---

## 六、下一步的三个选项（都还没做，等用户定）

### 选项 A：让 limit 按角色区分（治本，改动大）

- 8 个 conversationLead 角色维持 12 条（240 字预算）；
- 其余 36 个角色走 `persona_core` 路径，可放宽到 18~24 条。
- 要改 `_topic_window_for_turn` / `_preferred_topics_for_prompt` 接受每角色 limit，
  并改 `test_preferred_topics_fit_the_prompt_limit`（L906 硬断言 `== 12`）。
- **注意**：`_preferred_topics_for_prompt` 的 docstring 要求「池子点名的类别，
  `persona_core` 里必须看得见」是**单向包含**（`{topicPool}` ⊆ persona_core），
  所以两部分用不同 limit 是允许的。

### 选项 B：加大窗口前进步长（一行改动，见效快）

```python
# 现在：start = int(turn_index) % len(items)          → 邻轮重叠 11/12
# 改成：start = (int(turn_index) * K) % len(items)    → K=4 时重叠降到 8/12
```

- 优点：一行，不动数据、不动 240 字预算。
- 代价：违反 `_topic_window_for_turn` docstring 的原始意图
  （「窗口每轮前进 1 条……话题池缓慢轮换，读起来不突兀」），
  需要用户确认能接受「话题跳变」。

- ✅ **2026-10-01 已采纳并落地**：`prompts.py` 新增模块级 `_TOPIC_WINDOW_STEP = 4`，
  `start = (int(turn_index) * _TOPIC_WINDOW_STEP) % len(items)`，docstring 一并改写。
  佐证：全量回归 **4390 passed**（与基线一致）；端到端实测邻轮共享 8/12、每轮新进
  4 条、30 轮覆盖率 100%；**240 字截断经全轮次实测零越线**（8 个 conversationLead
  角色 × 所有轮次 × 4 个 stage，Sebastian 峰值仍为 240，与 K=1 一致）。
  回退方式：把该常量改回 1。

  ⚠ 用户口径：跳变指的是**跨轮**（相邻两轮的候选池差异变大），不是单轮之内 ——
  窗口是按 `turn_index` 算一次的快照，单轮内不可能跳。K 只改变多轮节奏，
  不改变单轮可见条数（恒为 12）。

### 选项 C：按「面」轮换而非按「条」轮换（最贴合机制，改动最大）

- 每轮窗口固定覆盖若干生活面，而不是机械滑动 12 条。
- 与 `_pick` 的 `facet` 过滤逻辑天然契合，但等于重写窗口函数。

**建议**：先问用户能否接受话题跳变，能则 **B**（成本最低、立刻可验证）；
不能则 **A**。C 留到 A/B 都不够时再谈。

---

## 七、红线（不可越）

- **绝不碰**真实 `Mods` DLL、真实存档、persona DB。
- **绝不启动**游戏 / SMAPI。
- 云端请求必须落在**新建的 artifact 目录**里。
- **绝不动** `E:\workspace\projects\stardew-ai-npc`（主库落后），只在 worktree 干活。
- **绝不提交**这两个未跟踪备份：
  `data/personas/rasmodia.json-bak-20260928-sentence-count`、
  `data/personas/vanilla.json-bak-20260928-responseRules0`。
  工作区里还有约 86 个 9/30 之前就存在的未提交项，**不要顺手提交**。
- hub 仓库只 stage **本次任务碰过的文件**。
- DSH 运维：**绝不在会话里跑** `Restart-Service -Name DeepSeekHarness -Force`，
  要用 `E:\workspace\hub\scripts\restart-dsh.ps1`。

---

## 八、可复用的 scratch 工具（都在 `E:\workspace\.scratch\stardew-night\`）

| 文件 | 用途 |
|---|---|
| `_sim.py` | 窗口轮换仿真（邻轮重叠率、20 轮覆盖面） |
| `_audit.py` / `_audit2.py` | 全 44 角色池质量审计（重复/台词/污染） |
| `_persona_scan.py` | 读 `personas[*].voiceStyle.preferredTopics`（注意**嵌套在 voiceStyle 下**） |
| `_cleanlist.py` | 导出清洗清单 → `CLEANUP-LIST.md` |
| `_rewrite2.py` / `_rewrite3.py` | 按行定向替换的**两阶段安全模板**（可复用这个骨架） |
| `_verify.py` | JSON 有效性 + CRLF + 抽查 |
| `_run_control_noa2.py` | A2 开关对照驱动（把 `_LENGTH_RETRY_THRESHOLD` 改 999，`finally` 还原） |
| `_a2_compare.py` / `_a2_diff.py` | A2 三次运行的统计与逐 case 对比 |

还有一批更早的（在 `E:\workspace\.scratch\`）：`mine_topics.mjs`（从游戏原文挖候选）、
`merge_topics.py` / `merge_wide.py`（入库）、`blacklist.txt`、`plan_wide.py`、`check_wide.py`。

**重点**：persona 文件里 `preferredTopics` **嵌套在 `voiceStyle` 下**，
不是顶层；`behavior-examples.json` / `behavior-quality-scenarios.json`
**不是** persona 文件（没有 `personas` 层）。

overlay 优先级：**female-bachelors > rasmodia > sve > vanilla**（列表整体替换，不合并）。
`female-bachelors.json` 里 Shane / Sebastian **必须与 vanilla 逐字节相同**。

---

## 九、A2 实验的完整结论（已闭环，不必重跑）

三次可比的全 66 case 运行（都是 `suite=default`、`compactPrompt=False`、
`dynamicPlayerInput=True`、`maxPlayerRetries=0`、`errors=0`）：

| 指标 | A2-ON | A2-OFF #1 | A2-OFF #2 |
|---|---|---|---|
| requests | 351 | 292 | 282 |
| totalTokens | 2,772,408 | 2,318,634 | 2,231,100 |
| passedTurns / 198 | 127 (64.1%) | 133 (67.2%) | 128 (64.6%) |
| passedCases / 66 | 24 | 27 | 25 |
| 超 68 字 | 18 (9.1%) | 64 (32.3%) | 45 (22.7%) |

**结论**：
1. **通过率差异是噪声** —— 组内差（2.6pp）> 组间差（1.8pp），A2-ON 的 64.1% 夹在两个
   A2-OFF 值中间。
2. 所有 warning 维度的差异**都是噪声**（`opening_retry: repeated` 是 14/23/7）。
3. **成本差是真的**：A2 多 **+22% requests/tokens**（组间 64 vs 组内 10）。
4. `character_quality_eval.py` **没有长度判据** ⇒ A2 对分数贡献为 0，
   唯一效果是玩家看到的回复更短。
5. ⇒ 这是**产品取舍**：简洁 vs +22% 云端成本。

一键评估成本 **约 $2.5–3**（不是早先记的 $0.6–0.7，那份估计错了约 4 倍）。
`docs/STATE.md` §七末 与 `~/.dsh/memory/commandcode-pools.md` 里**还留着旧的错误数字**，
下次改 STATE.md 时顺手修掉。

`docs/STATE.md` 另有两处已知陈旧：§七的成本数字、L336 的
「云端评测必须 `--economical`」（A2 那类运行**不能**加 `--economical`，
参考运行是 `compactPrompt=False`）。

---

## 十、接口速查

### 评测

```powershell
& $py -B scripts\run_character_quality_eval.py `
  --provider cloud --confirm-cloud `
  --endpoint $env:BRIDGE_CLOUD_URL --model $env:BRIDGE_CLOUD_MODEL `
  --suite default --output-dir artifacts/character-quality-eval/<新目录名>
```

- `--provider fake` 可跑通全流程（66 case / 198 turn / errors 0）**且不花钱**，先用它验证管道。
- `--provider local` 不可用（bridge 没起，5678 无监听）。
- 合法 suite 尺寸：`default` 66、`topic-start-intimacy` 50、`topic-start-adaptive` 50、
  `affection-pacing` 32、`relationship-world` 32、`topic-start-event-impact` 14、
  `relationship-stage-gating` 14、`conversation-lead` 8、`deep-flirt` 8、`deep-flirt-intimate` 8。
- 任何 `errors > 0` 或 `usage.totalTokens == 0` 的运行**判为无效**。
- 判 judge 类评测看**逐轮通过数**，不要看 `casePassRate`。

### 凭据

`$env:USERPROFILE\.dsh\.credentials.yaml` 里有三把 key：
`DEEPSEEK_API_KEY`、`CMD_API_KEY`（池 1，`.env.local` 用的就是它）、
`CMD_API_KEY_2`（池 2）、`CMD_API_KEY_3`（池 3）。

- `config.py:71` 的 `load_local_env()` 有 `if name not in _LOCAL_ENV_KEYS or name in os.environ: continue`
  ⇒ **已存在的进程环境变量会覆盖 `.env.local`**（逐名判断），
  所以换池只需 `$env:BRIDGE_CLOUD_API_KEY = ...`，**不用改文件**。
- 查账：`node E:\workspace\hub\scripts\_cc_usage.mjs`（`$env:CC_KEY_NAME` 选池）、
  `_cc_pools.mjs`、`_cc_split.mjs`。
- **`credits.monthlyCredits` 才是真剩余额度**；`/alpha/usage/summary` 的 `totalCost`
  是**累计**，不是剩余。usage 统计**滞后 3–5 分钟**，别读太早。
- 直接打 `/alpha/usage/summary` 需要带
  `Authorization: Bearer <key>`、`x-command-code-version: 1.0.0`、
  `x-cli-environment: production` 和浏览器 `User-Agent`（否则 Cloudflare 1010）。
- **绝不要打印凭据值。**

---

## 十一、给新会话的第一句话建议

> 读 `docs/HANDOFF-2026-10-01-topic-pool.md`（或本文件）与 `docs/STATE.md`，
> 跑一次基线测试确认 4390 passed，然后问用户选 §6 的 A / B / C 哪个方向。
> **不要**再挖角色语料，**不要**动 Alex，**不要**把原话改回名词短语。
