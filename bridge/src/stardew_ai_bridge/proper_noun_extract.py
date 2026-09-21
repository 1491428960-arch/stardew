"""专有名词 → 常驻事实：候选提取与证据包（批次 2 的工具化，2026-09-21）。

## 为什么需要它

样本进 prompt 是**按位置切片**的（`speechEvidence[:4]`、`knowledgeFacts[:1]`），
专有名词天生与多数玩家输入不相关，**结构性永远选不中**：

* Alex 的「小灰」在全库有 8 条语料（去重 6 条），排在他 211 条素材的深处；
* 那 8 条全是 `event_dialogue`，还受 `completedEventIds` 门控；
* 常驻通道里没有宠物信息，模型只好用先验补一个近邻色名「小黑」。

所以"资料里有"不等于"模型拿得到"——判据必须是**常驻事实通道里有没有**。
本模块把"哪些专有名词值得提升"从手工判断变成可复现的提取 + 审阅流程。

## 怎么用

```bash
# 1) 出候选表（按本地出现次数排序）
PYTHONPATH=bridge/src python -m stardew_ai_bridge.proper_noun_extract --top 60

# 2) 出证据包（每个候选附该角色语料里全部命中的原句）
PYTHONPATH=bridge/src python -m stardew_ai_bridge.proper_noun_extract \
    --evidence .tmp/proper-noun-evidence.md --evidence-npcs "Alex,Shane,Victor"

# 3) 人工审阅证据包 → 在 data/personas/*.json 里写 knowledgeFacts 并标 alwaysOn: true
# 4) 同步进索引（真机读的是索引，不是 persona 文件）
#    见脚本注释里的 sync 步骤说明
```

## 判据（不依赖分词器）

1. **本地复现**：该 n-gram 在同角色语料里出现 ≥3 条（专名会反复出现）；
2. **高度集中**：单角色命中 / 全库命中 ≥0.7（通用词散在全库，专名集中在少数角色）；
3. **全库低频**：全库 ≤25 条（专名不是高频词）；
4. **边界干净**：首尾字不是功能字 —— 砍掉「诉皮埃尔」「比盖尔不」这类切碎的噪声；
5. **邻字多样**：左邻或右邻字符种类 ≥2 —— 砍掉「演出大获」（右邻永远是「成」，
   它其实是「演出大获成功」的碎片）。

另有**呼语/命名句式**扫描作为补漏：n-gram 判据会漏掉被上下文词盖住的真名 ——
Shane 的蓝母鸡「查理」就被同句的「母鸡」抢了锚点，靠这一路才捞回来。

## 精度定位（重要）

这是**粗筛器，不是判决器**：403 条候选里绝大多数是噪声（「这首歌」「印象深刻」），
有结构信号（宠物／家人／地名）的约 54 条。**最终提升必须由人审阅证据包决定** ——
把"别再手工一条条写"理解成"全自动写"，就会把「Sam 演出」这种碎片写进人物事实。
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

CJK = r"\u4e00-\u9fa5"

# 功能字：专名的首尾字不会是它们。中间不管。
FUNCTION_CHARS = frozenset(
    "的了是在和与不很就也都要会能我你他她它们这那有到从对向跟把被给让而但只还再又更最没别"
    "请谢该想说讲问来去做用次个些么什吧呢啊呀哦嗯吗上下里外过完着得地"
)
PET_WORDS = ("狗", "猫", "宠物", "马", "鹦鹉", "小鸡", "兔", "抚摸", "听话", "喂")
FAMILY_WORDS = (
    "妈妈", "爸爸", "母亲", "父亲", "儿子", "女儿", "哥哥", "姐姐", "弟弟", "妹妹",
    "爷爷", "奶奶", "外公", "外婆", "叔叔", "阿姨", "姑妈", "舅舅", "家人", "妻子",
    "丈夫", "老婆", "老公", "祖父", "祖母",
)
PLACE_SUFFIX = ("镇", "村", "山", "森林", "谷", "岛", "城", "湖", "河", "湾", "沙漠", "农场", "矿井")
NGRAM_SIZES = (2, 3, 4, 5)
MIN_LOCAL = 3
MIN_CONCENTRATION = 0.7
MAX_GLOBAL = 25

VOCATIVE_RE = re.compile(rf"(?:^|[，。！？…\s])([{CJK}]{{2,3}})(?=[，。！？…\s“”]|$)")
NAMED_RE = re.compile(rf"叫(?:作|做)?([{CJK}]{{2,3}})")
DENY_VOCATIVE = frozenset(
    "你好 谢谢 抱歉 再见 当然 其实 只是 就是 还有 大家 你们 我们 他们 真的 不是 没有 可以 应该"
    "知道 觉得 想要 需要 喜欢 今天 明天 昨天 现在 这个 那个 什么 怎么 时候 地方 事情 东西".split()
)


def default_index_path() -> Path:
    """真机索引 —— 与 `scripts/start_bridge.ps1:22-27` 指定的那一份一致。

    ⚠ 用错索引会把角色读成兜底值（`personas.py` 的 `_DEFAULT_VOICE_STYLE`），
    得出完全错误的结论。这里是**同一份**文件的唯一来源。
    """

    project_root = Path(__file__).resolve().parents[3]
    return (
        project_root / "data" / "generated"
        / "vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
    )


def clean_boundary(candidate: str) -> bool:
    return bool(candidate) and (
        candidate[0] not in FUNCTION_CHARS and candidate[-1] not in FUNCTION_CHARS
    )


def anchor_kind(joined: str, candidate: str) -> str:
    """给候选贴一个语境标签（只用于分类，不作为准入条件）。

    Alex 的 5 条「小灰」语料里只有 1 条同时出现「抚摸」，句级共现根本盖不住，
    所以锚点不能当准入门槛 —— 真正的准入是上面那五条统计判据。
    """

    for match in re.finditer(re.escape(candidate), joined):
        window = joined[max(0, match.start() - 14) : match.end() + 14]
        if any(word in window for word in PET_WORDS):
            return "pet"
        if any(word in window for word in FAMILY_WORDS):
            return "family"
    if candidate.endswith(PLACE_SUFFIX):
        return "place"
    if re.search(rf"叫{candidate}", joined):
        return "named"
    return "?"


def _ngrams(text: str):
    for chunk in re.findall(rf"[{CJK}]+", text):
        for size in NGRAM_SIZES:
            for index in range(len(chunk) - size + 1):
                yield chunk[index : index + size]


def load_corpus(index_path: str | Path) -> dict[str, list[str]]:
    """按角色收集语料，**先去重**：索引里同一句原文会重复出现多次。"""

    payload = json.loads(Path(index_path).read_text(encoding="utf-8-sig"))
    by_npc: dict[str, list[str]] = collections.defaultdict(list)
    for item in payload.get("speechEvidence") or []:
        npc_id = item.get("npcId")
        text = str(item.get("text") or "")
        if npc_id and text:
            by_npc[npc_id].append(text)
    return {npc: sorted(set(texts)) for npc, texts in by_npc.items()}


def extract_candidates(by_npc: dict[str, list[str]]) -> list[dict[str, Any]]:
    """五道判据的候选提取；返回按角色分组的候选（含命中原文）。"""

    global_count: collections.Counter = collections.Counter()
    for texts in by_npc.values():
        for text in texts:
            for gram in set(_ngrams(text)):
                global_count[gram] += 1

    rows: list[dict[str, Any]] = []
    for npc_id, texts in by_npc.items():
        local: collections.Counter = collections.Counter()
        left: dict[str, set[str]] = collections.defaultdict(set)
        right: dict[str, set[str]] = collections.defaultdict(set)
        for text in texts:
            for chunk in re.findall(rf"[{CJK}]+", text):
                for size in NGRAM_SIZES:
                    for index in range(len(chunk) - size + 1):
                        gram = chunk[index : index + size]
                        local[gram] += 1
                        left[gram].add(chunk[index - 1] if index > 0 else "^")
                        end = index + size
                        right[gram].add(chunk[end] if end < len(chunk) else "$")
        joined = "\n".join(texts)
        for gram, count in local.items():
            if count < MIN_LOCAL:
                continue
            total = global_count[gram]
            if total > MAX_GLOBAL:
                continue
            if total and count / total < MIN_CONCENTRATION:
                continue
            if not clean_boundary(gram):
                continue
            if len(left[gram]) < 2 and len(right[gram]) < 2:
                continue
            rows.append(
                {
                    "npcId": npc_id,
                    "candidate": gram,
                    "localCount": count,
                    "globalCount": total,
                    "concentration": round(count / total, 3) if total else 0.0,
                    "leftVariety": len(left[gram]),
                    "rightVariety": len(right[gram]),
                    "anchor": anchor_kind(joined, gram),
                    "source": "ngram",
                    "texts": [text for text in texts if gram in text],
                }
            )

    # 同一处只留最长的候选（「演出大获成功」优先于「演出大获」）
    rows.sort(key=lambda row: (row["npcId"], -len(row["candidate"]), -row["localCount"]))
    kept: list[dict[str, Any]] = []
    seen: dict[str, list[str]] = collections.defaultdict(list)
    for row in rows:
        npc_id, candidate = row["npcId"], row["candidate"]
        if any(candidate in longer for longer in seen[npc_id]):
            continue
        seen[npc_id].append(candidate)
        kept.append(row)
    return kept


def extract_vocatives(by_npc: dict[str, list[str]]) -> list[dict[str, Any]]:
    """呼语/命名句式补漏：捞回被上下文词盖住的真名（如 Shane 的「查理」）。"""

    hits: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    for npc_id, texts in by_npc.items():
        for text in texts:
            for pattern in (VOCATIVE_RE, NAMED_RE):
                for match in pattern.finditer(text):
                    name = match.group(1)
                    if name in DENY_VOCATIVE or not clean_boundary(name):
                        continue
                    hits[(npc_id, name)].append(text)
    rows = [
        {
            "npcId": npc_id,
            "candidate": name,
            "localCount": len(texts),
            "anchor": "vocative",
            "source": "vocative/named",
            "texts": texts[:6],
        }
        for (npc_id, name), texts in hits.items()
        if len(texts) >= 2
    ]
    rows.sort(key=lambda row: (row["npcId"], -row["localCount"]))
    return rows


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="提取角色语料里的专有名词候选（供提升为 knowledgeFacts）",
    )
    parser.add_argument("--index", default="", help="资料索引路径（默认用真机索引）")
    parser.add_argument("--top", type=int, default=50, help="打印前 N 条")
    parser.add_argument("--json", default="", help="把候选表写成 JSON")
    parser.add_argument("--evidence", default="", help="把证据包写成 Markdown")
    parser.add_argument(
        "--evidence-npcs",
        default="",
        help="证据包只列这些角色（逗号分隔）；默认列全部有结构信号的角色",
    )
    parser.add_argument(
        "--sync-index",
        default="",
        help="把 persona 里标了 alwaysOn 的事实同步进这个索引（默认只预览）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="与 --sync-index 一起用时真正写入（会先自动备份）",
    )
    return parser


# --- 数据 → 索引的同步 --------------------------------------------------------
#
# 为什么需要单独一步：prompt 侧的 `knowledge_facts` 读的是**索引**
# （`ProfileIndexStore.knowledge_facts()`），不是 `data/personas/*.json`。
# 只改 persona 而忘了同步，表现是"数据明明写进去了、游戏里一点变化没有"。
#
# 刻意**不重新生成整个索引**（那需要游戏目录/解包目录等外部输入）：
# 按 `(npcId, factId)` 合并，新增缺失条目、补 `alwaysOn` 标记，其余原样不动。
_PERSONA_FILES = ("vanilla.json", "sve.json", "female-bachelors.json", "rasmodia.json")


def persona_always_on_facts(persona_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """从 persona 文件收集所有常驻事实，附上它所在的 mod 名。"""

    found: dict[tuple[str, str], dict[str, Any]] = {}
    for name in _PERSONA_FILES:
        path = persona_dir / name
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        mod = str(data.get("mod") or "").strip()
        for npc_id, profile in (data.get("personas") or {}).items():
            if not isinstance(profile, dict):
                continue
            for fact in profile.get("knowledgeFacts") or []:
                if not isinstance(fact, dict) or fact.get("alwaysOn") is not True:
                    continue
                fact_id = str(fact.get("factId") or "").strip()
                if fact_id:
                    found[(npc_id, fact_id)] = {**fact, "_personaMod": mod}
    return found


def sync_index(index_path: Path, persona_dir: Path, *, apply: bool) -> int:
    """把 persona 的常驻事实同步进索引；返回进程退出码。"""

    payload = json.loads(index_path.read_text(encoding="utf-8-sig"))
    facts: list[dict[str, Any]] = list(payload.get("knowledgeFacts") or [])
    by_key = {
        (str(fact.get("npcId")), str(fact.get("factId"))): fact
        for fact in facts
        if isinstance(fact, dict)
    }
    mod_by_npc = {
        str(fact.get("npcId")): str(fact.get("sourceMod") or "")
        for fact in facts
        if isinstance(fact, dict)
    }

    want = persona_always_on_facts(persona_dir)
    added: list[dict[str, Any]] = []
    marked: list[dict[str, Any]] = []
    for (npc_id, fact_id), fact in sorted(want.items()):
        existing = by_key.get((npc_id, fact_id))
        if existing is None:
            entry = {
                "factId": fact_id,
                "npcId": npc_id,
                "sourceMod": mod_by_npc.get(npc_id) or fact.get("_personaMod") or "",
                "summary": str(fact.get("summary") or ""),
                "knowledgeScope": str(fact.get("knowledgeScope") or "canon_confirmed"),
                "confidence": str(fact.get("confidence") or "high"),
                "sourceRefs": list(fact.get("sourceRefs") or []),
                "alwaysOn": True,
            }
            facts.append(entry)
            added.append(entry)
        elif existing.get("alwaysOn") is not True:
            existing["alwaysOn"] = True
            marked.append(existing)

    print("persona 里的常驻事实：%d 条" % len(want))
    print("索引原有事实：%d 条" % len(by_key))
    print("新增：%d 条" % len(added))
    for entry in added:
        print("   + %-8s %-26s %s" % (entry["npcId"], entry["factId"],
                                      entry["summary"][:44]))
    print("补标记：%d 条" % len(marked))
    for entry in marked:
        print("   ~ %-8s %-26s" % (entry["npcId"], entry["factId"]))

    if not added and not marked:
        print("\n索引已是最新，无需改动。")
        return 0
    if not apply:
        print("\n（预览模式，未写入。加 --apply 生效。）")
        return 0

    backup = index_path.with_suffix(index_path.suffix + ".bak-before-alwayson")
    shutil.copy2(index_path, backup)
    payload["knowledgeFacts"] = facts
    # 格式与生成器保持一致：`json.dumps(indent=2, ensure_ascii=False)` + 结尾换行
    # （实测原文件字符数与该写法只差结尾那 1 个 `\n`）。
    index_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("\n已写入：%s" % index_path)
    print("备份：%s" % backup)
    print("索引事实总数：%d 条（其中常驻 %d 条）"
          % (len(facts), sum(1 for fact in facts if fact.get("alwaysOn"))))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.sync_index:
        return sync_index(
            Path(args.sync_index),
            Path(__file__).resolve().parents[3] / "data" / "personas",
            apply=args.apply,
        )

    index_path = Path(args.index) if args.index else default_index_path()
    if not index_path.is_file():
        print(f"索引不存在：{index_path}", file=sys.stderr)
        return 2

    by_npc = load_corpus(index_path)
    candidates = extract_candidates(by_npc)
    total_texts = sum(len(texts) for texts in by_npc.values())

    print("=" * 112)
    print("索引：%s" % index_path.name)
    print("语料 %d 条 / %d 个角色（按角色去重后）" % (total_texts, len(by_npc)))
    print("判据：本地≥%d、集中度≥%.1f、全库≤%d、边界干净、邻字多样"
          % (MIN_LOCAL, MIN_CONCENTRATION, MAX_GLOBAL))
    print("=" * 112)
    print("%-11s %-12s %-4s %-4s %-6s %-6s %-9s %s"
          % ("角色", "候选", "本地", "全库", "集中度", "邻字", "语境", "示例"))
    print("-" * 112)
    for row in sorted(candidates, key=lambda r: (-r["localCount"], r["npcId"]))[: args.top]:
        print("%-11s %-12s %-4d %-4d %-6.2f %-6s %-9s %s"
              % (row["npcId"], row["candidate"], row["localCount"], row["globalCount"],
                 row["concentration"],
                 "%d/%d" % (row["leftVariety"], row["rightVariety"]),
                 row["anchor"], row["texts"][0][:34]))
    print()
    per_npc = collections.Counter(row["npcId"] for row in candidates)
    by_anchor = collections.Counter(row["anchor"] for row in candidates)
    print("候选 %d 条，覆盖 %d 个角色；按语境 %s"
          % (len(candidates), len(per_npc), dict(by_anchor)))
    print("有结构信号（宠物/家人/地名/命名）的候选：%d 条 / %d 个角色"
          % (sum(count for anchor, count in by_anchor.items() if anchor != "?"),
             len({row["npcId"] for row in candidates if row["anchor"] != "?"})))

    if args.json:
        slim = [{k: v for k, v in row.items() if k != "texts"} for row in candidates]
        Path(args.json).write_text(
            json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("已写出候选：%s" % args.json)

    if args.evidence:
        npcs = [name for name in args.evidence_npcs.split(",") if name] or sorted(
            {row["npcId"] for row in candidates if row["anchor"] != "?"}
        )
        vocatives: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for row in extract_vocatives(by_npc):
            vocatives[row["npcId"]].append(row)
        lines = [
            "# 专有名词候选证据包",
            "",
            "> 由 `python -m stardew_ai_bridge.proper_noun_extract --evidence` 生成。",
            "> 每条候选附**该角色语料里全部命中的原句**（去重），供人工判定是否提升为常驻事实。",
            "> 判定通过后写进 `data/personas/*.json` 的 `knowledgeFacts` 并标 `alwaysOn: true`，",
            "> 再同步进索引（真机读的是索引）。",
            "",
        ]
        for npc_id in npcs:
            lines.append(f"## {npc_id}")
            lines.append("")
            for row in [r for r in candidates if r["npcId"] == npc_id]:
                lines.append(
                    f"### `{row['candidate']}` — n-gram 命中 {row['localCount']} 条"
                    f"（全库 {row['globalCount']}，集中度 {row['concentration']}，"
                    f"语境 {row['anchor']}）"
                )
                for text in row["texts"][:8]:
                    lines.append(f"- {text[:100]}")
                lines.append("")
            for row in vocatives.get(npc_id, [])[:20]:
                lines.append(f"### 呼语/命名：`{row['candidate']}` — {row['localCount']} 条")
                for text in row["texts"][:6]:
                    lines.append(f"- {text[:100]}")
                lines.append("")
        Path(args.evidence).write_text("\n".join(lines), encoding="utf-8")
        print("已写出证据包：%s（%d 个角色）" % (args.evidence, len(npcs)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
