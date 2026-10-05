"""一键体检 —— 把 2026-09-28 建立的检查全部跑一遍，末尾给一段可粘贴的结论。

**零云端请求、只读**。每个子检查都调用既有脚本/模块，本文件不重复实现逻辑，
避免「两处各写一份、慢慢走偏」。

跑法（必须三个 PYTHONPATH 条目）：

    $w = 'E:\\workspace\\projects\\stardew-ai-npc\\.worktrees\\story-memory'
    $env:PYTHONPATH = "$w;$w\\bridge\\src;$w\\scripts"
    python "$w\\scripts\\health_check.py"

子检查失败不会中断其余检查 —— 体检的价值在于**一次看全**，不是第一条就退出。
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "bridge" / "src"))
sys.path.insert(0, str(WT / "scripts"))

PY = sys.executable

#: ⚠ 子进程必须显式给环境：不设 `PYTHONIOENCODING` 时，脚本里的中文提示会按
#: 系统默认编码（GBK）写出，本文件的 `encoding="utf-8"` 读回来就是乱码，
#: 于是所有 `re.search` 静默失配 —— 实测覆盖率会从 64% 假报成 18%、
#: 静态扫描会从 4 组假报成 0 组。**这就是「工具报的数先问它看得见多少」。**
ENV = {
    **os.environ,
    "PYTHONIOENCODING": "utf-8",
    "PYTHONPATH": os.pathsep.join(
        [str(WT), str(WT / "bridge" / "src"), str(WT / "scripts")]
    ),
}
RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    mark = "OK  " if ok else "FAIL"
    print(f"[{mark}] {name} —— {detail}")


def quiet(func, *args, **kwargs) -> str:
    """跑一个函数并吞掉它的 stdout，返回捕获到的文本。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        func(*args, **kwargs)
    return buf.getvalue()


# --- 1. 台账与实时 prompt 的缺口（三条路径 × 7 档） --------------------------
try:
    import check_prompt_consistency as chk

    out = quiet(chk.diff_against_scope, list(chk.STAGES))
    m = re.search(r"合计\s*(\d+)\s*组待铺开", out)
    gaps = int(m.group(1)) if m else -1
    record(
        "台账缺口（3 条路径 × 7 档）",
        gaps == 0,
        f"{gaps} 组" if gaps >= 0 else "输出无法解析",
    )
except Exception as exc:  # noqa: BLE001
    record("台账缺口", False, f"异常: {exc!r}")

# --- 2. 台账自身的回归自测 ---------------------------------------------------
try:
    out = subprocess.run(
        [PY, str(WT / "scripts" / "constraint_scope.py")],
        capture_output=True, text=True, encoding="utf-8", timeout=180, env=ENV,
    ).stdout or ""
    ok = "判出 2 条冲突" in out and "当前状态无冲突" in out
    record("台账回归自测", ok, "收束前 2 条 / 当前 0 条" if ok else "断言未同时满足")
except Exception as exc:  # noqa: BLE001
    record("台账回归自测", False, f"异常: {exc!r}")

# --- 3. 抽取覆盖率（工具「看得见多少」） -------------------------------------
try:
    out = subprocess.run(
        [PY, str(WT / "scripts" / "probe_extraction_blindspot.py")],
        capture_output=True, text=True, encoding="utf-8", timeout=300, env=ENV,
    ).stdout or ""
    total = re.search(r"含数量片段总数\s*:\s*(\d+)", out)
    # ⚠「抽取器抓到」**每个阶段打一行累计值**（16 / 29 / 43 / 58），
    #   取第一个会得到 stranger 阶段的局部数字 —— 这正是本文件第一版假报
    #   「18%」的原因。必须取**汇总行**（行首「抓到 : N」）。
    caught_all = re.findall(r"^\s*抓到\s*:\s*(\d+)", out, re.M)
    caught_n = caught_all[-1] if caught_all else None
    lenmiss = re.search(r"漏（长度原因）\s*:\s*(\d+)", out)
    if total and caught_n:
        pct = int(caught_n) / max(1, int(total.group(1)))
        # ⚠ 不设「覆盖率必须 ≥ X」的阈值：这个数字取决于正则宽严，
        #   收紧正则换准确度是**有意**的取舍（2026-09-28：69% → 64%，
        #   降的全是指示词/动作短语类假阳性）。这里只报数字。
        record(
            "抽取覆盖率",
            lenmiss is None or int(lenmiss.group(1)) == 0,
            f"{caught_n}/{total.group(1)} = {pct:.0%}"
            f"（因长度原因漏 {lenmiss.group(1) if lenmiss else '?'}）",
        )
    else:
        record("抽取覆盖率", False, "输出无法解析")
except Exception as exc:  # noqa: BLE001
    record("抽取覆盖率", False, f"异常: {exc!r}")

# --- 4. persona 静态扫描（含未启用配置） -------------------------------------try:
    out = subprocess.run(
        [PY, str(WT / "scripts" / "probe_persona_static_conflicts.py")],
        capture_output=True, text=True, encoding="utf-8", timeout=300, env=ENV,
    ).stdout or ""
    # ⚠ 输出措辞是「同量多值」，**不是**「取值多于一种」——锚错了一直报 0。
    m = re.search(r"扫描了\s*(\d+)\s*个 persona 定义[，,]\s*(\d+)\s*组", out)
    record(
        "persona 静态扫描",
        m is not None,
        f"{m.group(1)} 个 persona，{m.group(2)} 组同量多值（⚠ 只摊开、不判冲突）"
        if m
        else "输出无法解析",
    )
except Exception as exc:  # noqa: BLE001
    record("persona 静态扫描", False, f"异常: {exc!r}")

# --- 5. 反向验证：台账里的条目是否真的存在 -----------------------------------
# ⚠ 只报数字、**不判失败**：台账的 `text` 字段语义不纯 —— 多数存原文，
#   少数存**注释**（如「（同一条招牌动作，也出现在这张卡里）」）或与原文有
#   格式差异（`maxActions: 1` vs JSON 里的 `"maxActions": 1`）。这两类都会
#   被判成「找不到」，属于**已知噪音**，所以这里不下结论、留给人读。
try:
    out = subprocess.run(
        [PY, str(WT / "scripts" / "probe_ledger_reverse.py")],
        capture_output=True, text=True, encoding="utf-8", timeout=600, env=ENV,
    ).stdout or ""
    m = re.search(r"完全找不到\s*(\d+)\s*条[，,]\s*部分找不到\s*(\d+)\s*条", out)
    record(
        "台账反向验证",
        True,
        f"完全找不到 {m.group(1)} 条 / 部分 {m.group(2)} 条"
        f"（⚠ 含 text=注释 与格式差异的已知噪音，须人读）"
        if m
        else "输出无法解析",
    )
except Exception as exc:  # noqa: BLE001
    record("台账反向验证", False, f"异常: {exc!r}")

# --- 6. 输出侧遵守率（**报告性指标，不判失败**） -----------------------------
# 2026-09-28 晚新增。这是「**模型是否照做**」的唯一入口，与上面全部
# 「prompt 内部是否自洽」的检查**正交** —— 那侧已做尽（缺口 0），这侧才刚开始。
#
# ⚠ **只报告、不判失败**：43.8% 超限是**现状**，不是缺陷。
# 把它做成红灯只会让人习惯性忽略红灯；真正要看的是**趋势**。
try:
    out = subprocess.run(
        [PY, str(WT / "scripts" / "probe_length_compliance.py")],
        capture_output=True, text=True, encoding="utf-8", timeout=600, env=ENV,
    ).stdout or ""
    m = re.search(
        r"【全部】n=\s*(\d+)\s+中位=\s*([\d.]+).*?超(\d+)字=\s*\d+\(\s*([\d.]+)%\)",
        out,
    )
    if m:
        record(
            "输出侧遵守率",
            True,
            f"n={m.group(1)} 中位={m.group(2)} 字，超 {m.group(3)} 字上限 {m.group(4)}%"
            f"（⚠ 报告性，不判失败 —— 重试机制**不查长度**，超长直接放行）",
        )
    else:
        record("输出侧遵守率", True, "输出无法解析（本项不判失败）")
except Exception as exc:  # noqa: BLE001
    record("输出侧遵守率", True, f"异常: {exc!r}（本项不判失败）")

# --- 7. 评测集阶段覆盖（快，报告性） -----------------------------------------
# ⭐ 2026-09-28 晚新增。起因：扫全部 artifact（213 个 case）发现
# **stranger 与 parent 两个阶段一个 case 都没有**，而限定在「初识阶段」的
# 约束有 12 条 ⇒ **拿现有样本根本验不了**（我曾因此得到一个无意义的 8.8%）。
#
# ✅ **2026-10-05 更新：当初这个空白已经补上了** —— 09-30 那批往
#    `_BASE_CASES` 补了 stranger / parent 各 5 个之后又扩过，实测现在
#    **stranger 8/8、parent 8/8**（跑过 / 并集），两档都有样本且都跑过。
#    ⚠ 本项**仍然保留**：它是**会复发**的盲区（每加一批 case 都可能引入新空白），
#    不是一次性任务。真正的卡点已经转移到「阶段 × 话题」配对，见下方第 5 条。
#
# ⚠ **只报告、不判失败**：样本空白是**评测集现状**，不是代码缺陷。
# 但它是**会复发**的盲区 —— 每次新增评测 case 都可能引入新的阶段空白，
# 所以放进巡检，让它每次都被看见。
try:
    import json as _json

    _STAGES = ("stranger", "acquaintance", "friend", "close", "dating", "married", "parent")
    _cov: dict[str, int] = {s: 0 for s in _STAGES}
    _art = WT / "artifacts" / "character-quality-eval"
    _seen: set[str] = set()
    if _art.exists():
        for _run in _art.iterdir():
            _f = _run / "results.jsonl"
            if not (_run.is_dir() and _f.exists()):
                continue
            try:
                _txt = _f.read_text(encoding="utf-8")
            except OSError:
                continue
            for _line in _txt.splitlines():
                _line = _line.strip()
                if not _line:
                    continue
                try:
                    _cid = str(_json.loads(_line).get("caseId") or "")
                except Exception:  # noqa: BLE001
                    continue
                if _cid in _seen:
                    continue
                _seen.add(_cid)
                _hit = next((s for s in _STAGES if s in _cid), None)
                if _hit:
                    _cov[_hit] += 1
    _empty = [s for s, n in _cov.items() if n == 0]
    _thin = [f"{s}={_cov[s]}" for s, n in _cov.items() if 0 < n <= 5]

    # ⚠⚠ **两列一起看，但第二列必须查对源头**（2026-09-28 我查错过**两次**）：
    #   · 第一列 = artifact（**跑过的**）
    #   · 第二列 = 云端评测**全部 suite 的并集**（**可跑的**）← 这一列才对应实验
    #     ⚠ 坑一：**不是** `data/personas/behavior-quality-scenarios.json` ——
    #       那是**本地行为样本生成器**（`generate_behavior_examples.py`，
    #       `--provider local`）的输入，与云端评测**无关**。
    #     ⚠ 坑二：**不能只看 `DEFAULT_CASES`**（只有 47 个）——
    #       artifact 里 married 跑过 **59** 个，比 default 还多，
    #       说明 case 来自**多个 suite**。只看 default 会低估一半以上。
    _avail: dict[str, int] = {}
    try:
        import sys as _sys

        _src = str(WT / "bridge" / "src")
        if _src not in _sys.path:
            _sys.path.insert(0, _src)
        from stardew_ai_bridge.character_quality_eval import (  # noqa: PLC0415
            QUALITY_SUITE_IDS as _QS,
            quality_cases_for_suite as _qcf,
        )

        _seen_stage: dict[str, str] = {}
        for _s in _QS:
            for _c in _qcf(_s):
                _st = getattr(_c, "relationship_stage", None)
                if _st:
                    _seen_stage[_c.case_id] = str(_st)
        for _st in _seen_stage.values():
            _avail[_st] = _avail.get(_st, 0) + 1
    except Exception:  # noqa: BLE001
        _avail = {}

    _detail = f"{len(_seen)} 个 case（跑过的）；" + " ".join(
        f"{s}={_cov[s]}/{_avail.get(s, 0)}" for s in _STAGES
    )
    _detail += "　（格式：**跑过的 / 全部 suite 并集里的**）"
    if _empty:
        _none = [s for s in _empty if _avail.get(s, 0) == 0]
        _has = [s for s in _empty if _avail.get(s, 0) > 0]
        if _none:
            _detail += (
                f"　⚠⚠ **{', '.join(_none)} 两边都空**"
                "（云端 case 集里**也没有**）⇒ 要用得**新写 case**"
            )
        if _has:
            _detail += (
                f"　✅ **{', '.join(_has)} 没跑过但 case 集里有** ⇒ 跑全，但 ⚠ **跑全也未必够**（还要看话题对不对，见第 ⑤ 层）"
            )
    if _thin:
        _detail += f"　⚠ 跑过的样本极少：{', '.join(_thin)}"
    if not _empty and not _thin:
        _detail += "　（各阶段均有可用样本）"
    record("评测集阶段覆盖", True, _detail + "（⚠ 报告性，不判失败）")
except Exception as exc:  # noqa: BLE001
    record("评测集阶段覆盖", True, f"异常: {exc!r}（本项不判失败）")

# --- 8. 全量测试（慢，用 --fast 跳过） ---------------------------------------
if "--fast" not in sys.argv:
    try:
        proc = subprocess.run(
            [PY, "-m", "pytest", str(WT / "bridge" / "tests"), "-q", "--no-header"],
            capture_output=True, text=True, encoding="utf-8", timeout=900, env=ENV,
        )
        tail = (proc.stdout or "").strip().splitlines()
        last = tail[-1] if tail else "(无输出)"
        record("全量测试", proc.returncode == 0, last)
    except Exception as exc:  # noqa: BLE001
        record("全量测试", False, f"异常: {exc!r}")
else:
    record("全量测试", True, "已跳过（--fast）")

# --- 汇总 -------------------------------------------------------------------
bad = [name for name, ok, _ in RESULTS if not ok]
print()
print("=" * 78)
if bad:
    print(f"体检未通过：{len(bad)} 项 —— {', '.join(bad)}")
else:
    print(f"体检通过：{len(RESULTS)} 项全绿。")
print("=" * 78)
print()
print("⚠ 六条边界（别把上面的绿读成「没有问题」）：")
print("  1. 台账只覆盖**上/下界类的数值约束**；指代/描述性数量词（「任何一个」")
print("     「这一项」）**有意排除**。")
print("  2. 覆盖率不是 100% ⇒ 台账能在**该覆盖范围内**说「已登记的冲突都查得出」，")
print("     但**不能**说「没有别的冲突」。")
print("  3. persona 静态扫描只**摊开取值**；真冲突与分层防御在取值这一层长得一样，")
print("     区别只在**粒度**与**测试是否钉住**，判断仍须人做。")
print("  4. **输出侧遵守率是报告项、不是通过项** —— 约一半输出超上限是**现状**。")
print("     它指向的修法在**输出侧**（重试判据或后处理），")
print("     与上面全部「prompt 内部」的台账工作**正交**，别混在一起读。")
print("  5. ⚠⚠ **「评测集阶段覆盖」是比上面四条都更上游的一类盲区** ——")
print("     前四条说的都是「**查不到**」（抽取漏、结构不表达），")
print("     这一条说的是「**没样本可查**」。")
print("     📌 **历史**：2026-09-28 首次加这条时，stranger / parent 两个阶段")
print("       **一个 case 都没有** —— 「抽取做得再全，没有样本也验不了」。")
print("     ✅ **现状（2026-10-05 实测）**：两档**都已补齐、而且都跑过** ——")
print("       stranger **8/8**、parent **8/8**。⇒ 当初那个空白**已经不在了**。")
print("     ⚠⚠ 但**这条巡检不要退休**：它是**会复发**的盲区，每加一批 case")
print("       都可能引入新的阶段空白，留着继续看。")
print("     ⚠⚠ **「初识」= `stranger`，不是 `acquaintance`**（实测：那条约束")
print("       只出现在 `stranger` 的卡里）⇒ 口径别混：台账里带阶段限定的只有 3 条，")
print("       按片段扫是 **stranger 9 条 / acquaintance 3 条**。")
print("     ⚠ 第二列是**云端评测全部 suite 的并集**（现在是 **274** 个 case，")
print("       这个数会涨，**别抄**）—— **不是**")
print("       `data/personas/behavior-quality-scenarios.json`：")
print("       那是**本地行为样本生成器**的输入，与云端评测**无关**（我查错过）。")
print("     ⇒ ⚠⚠ 但**别急着说「阶段有 case 就能测」** —— 还有第 ⑤ 层：")
print("       **阶段对了，话题不对**。现测（并集 274）：")
print("       `close × 动作`(4 条)、`stranger × 反问`(2)、`stranger × 换题`(1)、")
print("       `close × 换题`(1)、`close × 反问`(1) —— **阶段有样本、话题没有**")
print("       ⇒ 这几条**跑全也测不到**。")
print("       查它：`python scripts/probe_topic_alignment.py`")
print("     ⇒ 要做任何按阶段的实验，先看这一行，别拿错阶段的样本去测")
print("       （2026-09-28 我曾拿全阶段样本测「初识阶段不得邀约」，")
print("        得到的 8.8% **测的不是那条约束**）。")
print("  6. ⚠⚠ **「写进数据、到不了 prompt」是最容易忽略的一类** ——")
print("     角色数据里的 `responseRules` **到达率只有 50%**：")
print("     每个角色写 4 条、只有 2 条进 prompt")
print("     （`voice_actions[:3]` 截断；`signatureMoves` 为空时")
print("      `sentencePattern` 先占掉 2 槽）。")
print("     ⚠ 台账**结构上看不见**它 —— 那些规则根本没进 prompt，")
print("       既不会报缺失、也不会报冲突，**一切显示正常**。")
print("     ⇒ 对「字数话语权只有 1/6」是**又一条独立佐证**：")
print("       卡层 1/6 × 数据层 50% ⇒ 实际话语权比 1/6 更低。")
print("     ⇒ 查它：`python scripts/probe_response_rules_reach.py`")
print("     ⇒ 完整漏斗（五道闸）：`python scripts/probe_length_constraint_decay.py`")
