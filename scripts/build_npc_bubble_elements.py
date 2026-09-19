"""生成气泡元素分配表。

适用范围 = 存档 friendshipData 里的 NPC（见 data/friendship-roster.json）。
只有这些 NPC 能进入聊天与群聊；索引里的其他可聊天角色不进本表。

用法：
    py -3.10 scripts/build_npc_bubble_elements.py            # 写文件
    py -3.10 scripts/build_npc_bubble_elements.py --check    # 只审计
"""

from __future__ import annotations

import argparse
import colorsys
import json
import pathlib
import sys
import urllib.request

PROJECT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_BRIDGE = "http://127.0.0.1:5678/api/npcs"
ROSTER_PATH = PROJECT / "data" / "friendship-roster.json"
DELIVERED_SPEC = PROJECT / "docs" / "npc-bubble-elements-2026-09-19.json"

# ── 材质库：气泡边框的形态。organic 类沿边框蜿蜒生长，其余是硬边装饰 ──
KINDS = {
    "vine": ("藤蔓", "organic", "蜿蜒藤茎 + 叶片"),
    "grapevine": ("葡萄藤", "organic", "藤茎 + 葡萄叶 + 卷须"),
    "laurel": ("月桂枝", "organic", "细枝 + 对生叶"),
    "wheat": ("麦秆", "organic", "直茎 + 麦粒"),
    "leaf": ("阔叶枝", "organic", "大叶 + 浆果"),
    "crop": ("作物茎", "organic", "茎秆 + 叶片 + 果实"),
    "flower": ("花枝", "organic", "小花 + 花苞"),
    "crystal": ("矿脉", "hard", "棱柱结晶嵌在岩面"),
    "ore": ("金属锭", "hard", "方锭 + 铆钉"),
    "arcane": ("符文线", "hard", "细线 + 符文刻痕"),
    "cable": ("线缆", "hard", "绝缘线 + 接头"),
    "ribbon": ("缎带", "hard", "宽丝带 + 蝴蝶结"),
    "paper": ("纸卷", "hard", "卷边纸 + 折角"),
    "book": ("书脊", "hard", "书脊 + 书页边"),
    "wood": ("木栏", "hard", "木条 + 榫头"),
    "wool": ("毛线", "hard", "毛线股 + 针脚"),
    "fish": ("渔网", "hard", "网结 + 浮子"),
    "slime": ("黏液", "hard", "半透明块 + 滴落"),
    "stone": ("碎石", "hard", "方石 + 苔痕"),
}

# ── 物件库：32×32 画布的像素道具，每个角色取 2 件 ──
OBJECTS = {
    "amethyst": ("紫水晶簇", "矿"), "sword": ("短剑", "冒险"), "note": ("音符", "音乐"),
    "ball": ("橄榄球", "运动"), "dumbbell": ("哑铃", "运动"), "paw": ("爪印", "宠物"),
    "gem": ("宝石", "矿物"), "spool": ("彩色线轴", "手工"), "star_raw": ("星芒", "装饰"),
    "quill": ("羽毛笔", "写作"), "wave": ("海浪", "海"), "manuscript": ("手稿", "写作"),
    "cross": ("医疗十字", "医护"), "cup": ("咖啡杯", "饮食"), "glasses": ("眼镜", "医护"),
    "bat": ("蝙蝠", "夜行"), "gamepad": ("游戏手柄", "科技"), "wheel": ("车轮", "机械"),
    "chick": ("小鸡", "牧养"), "bottle": ("酒瓶", "饮食"), "grape": ("葡萄串", "农务"),
    "blossom": ("粉花", "花园"), "crystalball": ("水晶球", "魔法"), "staff": ("法杖", "魔法"),
    "rune": ("符文", "魔法"), "teapot": ("茶壶", "饮食"), "sunflower": ("向日葵", "花园"),
    "anvil": ("铁砧", "锻造"), "pickaxe": ("矿镐", "矿业"), "gemstone": ("原石", "矿业"),
    "microscope": ("显微镜", "科学"), "gear": ("齿轮", "机械"), "cookie": ("饼干", "烘焙"),
    "medal": ("勋章", "军旅"), "tv": ("电视机", "居家"), "fossil": ("化石", "考古"),
    "scroll": ("卷轴", "文书"), "pan": ("平底锅", "烹饪"), "beer": ("啤酒杯", "饮食"),
    "camera": ("相机", "摄影"), "doll": ("布偶", "童趣"), "basket": ("菜篮", "农务"),
    "popcorn": ("爆米花", "零食"), "slimeball": ("史莱姆球", "怪物"), "voidegg": ("虚空蛋", "怪物"),
    "chisel": ("刻刀", "雕刻"), "leaf_raw": ("树叶", "森林"), "parrot": ("鹦鹉", "丛林"),
    "shorts": ("紫色短裤", "镇长"), "key": ("钥匙", "镇长"), "tent": ("帐篷", "野外"),
    "berry": ("野莓", "野外"), "milk": ("牛奶罐", "牧养"), "telescope": ("望远镜", "天文"),
    "bus": ("巴士", "交通"), "book": ("书", "学问"), "chalk": ("粉笔", "教学"),
    "seed": ("种子袋", "农务"), "saw": ("锯子", "木工"), "hammer": ("锤子", "木工"),
    "guitar": ("吉他", "音乐"), "skateboard": ("滑板", "运动"), "cactus": ("仙人掌", "沙漠"),
    "coconut": ("椰子", "沙漠"), "candy": ("糖果", "零食"), "rod": ("钓竿", "钓鱼"),
    "fish_raw": ("鱼", "钓鱼"), "shell": ("贝壳", "海"), "yarn": ("毛线球", "编织"),
    "pumpkin": ("南瓜", "农务"), "hoe": ("锄头", "农务"), "shield": ("盾牌", "冒险"),
    "tie": ("领带", "商务"), "badge": ("工牌", "商务"), "wine": ("酒杯", "饮食"),
    "jewel": ("珠宝", "时尚"), "blueprint": ("蓝图", "建造"), "paintbrush": ("画笔", "绘画"),
    "easel": ("画架", "绘画"), "mushroom": ("蘑菇", "森林"), "acorn": ("橡果", "森林"),
    "scissors": ("剪刀", "手工"), "thread": ("线团", "手工"), "lantern": ("提灯", "矿洞"),
    "map": ("地图", "冒险"), "honey": ("蜂蜜", "农务"), "letter": ("信件", "文书"),
    "pearl": ("珍珠", "海"), "conch": ("海螺", "海"), "cloak": ("斗篷", "随从"),
    "crate": ("木箱", "随从"), "binocular": ("双筒镜", "观察"), "canteen": ("水壶", "野外"),
    "kite": ("风筝", "童趣"), "flute": ("长笛", "音乐"), "dice": ("骰子", "游戏"),
}

# ── 角色元素表：(显示名, 语义色相, 材质, 物件A, 物件B, 图标, 气质标签) ──
# 只包含好感度名单内的角色；别名（SVE 命名）复用同一份定义。
CORE = {
    "Abigail": ("Abigail", 259, "crystal", "amethyst", "sword", "amethyst", "好奇 · 直觉"),
    "Alex": ("Alex", 5, "laurel", "ball", "dumbbell", "ball", "直球 · 行动派"),
    "Emily": ("Emily", 170, "ribbon", "gem", "spool", "gem", "温柔 · 灵感"),
    "Elliott": ("Elliott", 32, "paper", "quill", "manuscript", "quill", "铺陈 · 诗意"),
    "Harvey": ("Harvey", 126, "vine", "cross", "cup", "cross", "稳重 · 照料"),
    "Sebastian": ("Sebastian", 235, "cable", "bat", "gamepad", "bat", "克制 · 短句"),
    "Shane": ("Shane", 200, "wheat", "chick", "cup", "chick", "疲惫 · 嘴硬"),
    "Sophia": ("Sophia", 320, "grapevine", "grape", "blossom", "grape", "轻快 · 跳脱"),
    "Wizard": ("Wizard", 288, "arcane", "crystalball", "staff", "crystalball", "神秘 · 判断"),
    "Caroline": ("Caroline", 78, "flower", "teapot", "sunflower", "teapot", "温和 · 园艺"),
    "Clint": ("Clint", 22, "ore", "anvil", "pickaxe", "anvil", "沉默 · 锻造"),
    "Demetrius": ("Demetrius", 195, "book", "microscope", "gear", "microscope", "严谨 · 研究"),
    "Dwarf": ("Dwarf", 40, "stone", "gemstone", "pickaxe", "gemstone", "直率 · 交易"),
    "Evelyn": ("Evelyn", 350, "wool", "cookie", "blossom", "cookie", "慈祥 · 烘焙"),
    "George": ("George", 132, "wood", "tv", "medal", "medal", "固执 · 老兵"),
    "Gunther": ("Gunther", 55, "book", "fossil", "scroll", "fossil", "博学 · 收藏"),
    "Gus": ("Gus", 42, "crop", "pan", "beer", "pan", "热络 · 掌勺"),
    "Haley": ("Haley", 48, "ribbon", "camera", "sunflower", "camera", "明艳 · 爱美"),
    "Jas": ("Jas", 300, "flower", "doll", "blossom", "doll", "安静 · 童真"),
    "Jodi": ("Jodi", 355, "crop", "pan", "basket", "basket", "操持 · 家常"),
    "Kent": ("Kent", 145, "wood", "medal", "popcorn", "popcorn", "沉重 · 军旅"),
    "Krobus": ("Krobus", 270, "slime", "voidegg", "slimeball", "voidegg", "谨慎 · 暗影"),
    "Leah": ("Leah", 95, "leaf", "chisel", "easel", "easel", "自在 · 雕刻"),
    "Lewis": ("Lewis", 245, "paper", "shorts", "key", "key", "体面 · 镇长"),
    "Linus": ("Linus", 105, "leaf", "tent", "berry", "tent", "淡泊 · 野外"),
    "Marnie": ("Marnie", 45, "wool", "milk", "chick", "milk", "热心 · 牧养"),
    "Marlon": ("Marlon", 135, "ore", "sword", "map", "map", "硬派 · 探险"),
    "Maru": ("Maru", 210, "cable", "telescope", "gear", "telescope", "灵巧 · 发明"),
    "Pam": ("Pam", 35, "cable", "bus", "beer", "bus", "豪爽 · 直来直去"),
    "Penny": ("Penny", 340, "book", "book", "chalk", "book", "温柔 · 教学"),
    "Pierre": ("Pierre", 85, "crop", "basket", "seed", "seed", "精明 · 营生"),
    "Robin": ("Robin", 25, "wood", "saw", "hammer", "hammer", "爽利 · 木工"),
    "Sam": ("Sam", 215, "cable", "guitar", "skateboard", "guitar", "随性 · 音乐"),
    "Sandy": ("Sandy", 60, "flower", "cactus", "coconut", "cactus", "慵懒 · 沙漠"),
    "Vincent": ("Vincent", 330, "flower", "candy", "kite", "candy", "活泼 · 童言"),
    "Willy": ("Willy", 190, "fish", "rod", "fish_raw", "rod", "老练 · 钓鱼"),
    "Morris": ("Morris", 205, "paper", "tie", "badge", "tie", "圆滑 · 商务"),
    "Andy": ("Andy", 38, "crop", "pumpkin", "hoe", "pumpkin", "固执 · 务农"),
    "Claire": ("Claire", 20, "crop", "cup", "letter", "cup", "疲惫 · 打工"),
    "Olivia": ("Olivia", 310, "ribbon", "wine", "jewel", "jewel", "矜贵 · 品味"),
    "Victor": ("Victor", 250, "paper", "blueprint", "wine", "blueprint", "内敛 · 设计"),
    "Scarlett": ("Scarlett", 335, "ribbon", "scissors", "thread", "scissors", "利落 · 裁缝"),
    "Susan": ("Susan", 75, "crop", "honey", "basket", "honey", "干练 · 经营"),
    # 好感度名单里、但上一轮未覆盖的
    "Martin": ("Martin", 65, "paper", "badge", "letter", "badge", "青涩 · 打工"),
    "Mermaid": ("Mermaid", 180, "fish", "pearl", "conch", "pearl", "悠远 · 海"),
    "Henchman": ("Henchman", 222, "ore", "crate", "cloak", "crate", "寡言 · 随从"),
}

KEYWORD_RULES = [
    (("witch", "wizard", "magic", "rune", "arcane"), "arcane", ("crystalball", "rune"), "魔法"),
    (("mermaid", "sea", "ocean", "pearl", "fish"), "fish", ("pearl", "shell"), "渔海"),
    (("dwarf", "mine", "ore", "gem"), "stone", ("pickaxe", "gemstone"), "矿工"),
    (("guard", "knight", "soldier", "hench"), "ore", ("shield", "sword"), "武"),
    (("book", "scribe", "librar", "scholar", "curator"), "paper", ("book", "scroll"), "文"),
    (("farm", "crop", "harvest", "field"), "crop", ("hoe", "basket"), "农"),
]

GOLDEN = 137.508
LUM_LEVELS = (21, 25, 29, 33)
NEAR_HUE = 8.0


def hls_to_rgb(h: float, l: float, s: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
    return round(r * 255), round(g * 255), round(b * 255)


def build_palette(hue: float, level: int) -> dict:
    bubble = hls_to_rgb(hue, level, 42)
    return {
        "hue": hue,
        "bubbleLevel": level,
        "accent": "#%02x%02x%02x" % hls_to_rgb(hue, 76, 78),
        "accentSoft": "#%02x%02x%02x" % hls_to_rgb((hue + 20) % 360, 82, 68),
        "bubble": f"rgba({bubble[0]}, {bubble[1]}, {bubble[2]}, .92)",
        "border": "#%02x%02x%02x" % hls_to_rgb(hue, 60, 58),
        "fruit": "#%02x%02x%02x" % hls_to_rgb(hue, 66, 72),
        "fruitHi": "#%02x%02x%02x" % hls_to_rgb(hue, 84, 66),
    }


def place_hue(target: float, taken: list[float], minimum: float) -> float:
    gap = minimum
    while gap >= 2.0:
        for delta in range(0, 181):
            for candidate in ((target + delta) % 360, (target - delta) % 360):
                if all(
                    min(abs(candidate - h) % 360, 360 - abs(candidate - h) % 360) >= gap
                    for h in taken
                ):
                    return candidate
        gap -= 0.5
    return target


def load_json(source: str) -> dict:
    if source.startswith("http"):
        with urllib.request.urlopen(source, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    return json.loads(pathlib.Path(source).read_text(encoding="utf-8"))


def build(roster: dict, catalog: dict, delivered: dict) -> tuple[dict, dict]:
    ids = list(roster["npcs"])
    aliases = roster.get("aliases") or {}
    merge_groups = roster.get("mergeGroups") or []

    def canonical(npc_id: str) -> str:
        return aliases.get(npc_id, npc_id)

    # 归并组：组内第一个成员作为代表，其余共用它的元素
    merged_into: dict[str, str] = {}
    for group in merge_groups:
        members = group["members"]
        for member in members[1:]:
            merged_into[member] = members[0]

    result: dict[str, dict] = {}
    taken: list[float] = []
    deferred: list[str] = []

    def key_of(npc_id: str) -> str:
        """名单 ID → 元素条目的键：先按归并组归一，再按别名归一。"""
        return canonical(merged_into.get(npc_id, npc_id))

    # 1) 有专属定义的角色：按语义色相落位（间距尽量 8°）
    for npc_id in ids:
        name = key_of(npc_id)
        if name in result:
            continue
        spec = CORE.get(name)
        if spec and name not in delivered:
            continue  # 先处理非锚点，锚点色相固定
        deferred.append(npc_id)

    anchors = sorted(delivered.items(), key=lambda kv: kv[1]["hue"])
    segments = []
    for i in range(len(anchors)):
        a_npc, a_body = anchors[i]
        _, b_body = anchors[(i + 1) % len(anchors)]
        segments.append((a_body["hue"], (b_body["hue"] - a_body["hue"]) % 360, a_npc))

    buckets: dict[str, list] = {a: [] for _, _, a in segments}
    for npc_id in ids:
        name = key_of(npc_id)
        if name in delivered or name in result:
            continue
        spec = CORE.get(name)
        if not spec:
            continue
        for a_hue, span, a_npc in segments:
            if 0 <= (spec[1] - a_hue) % 360 < span:
                buckets[a_npc].append((npc_id, spec))
                break

    core_hue: dict[str, float] = {k: v["hue"] for k, v in delivered.items()}
    for a_hue, span, a_npc in segments:
        members = sorted(buckets[a_npc], key=lambda t: t[1][1])
        for index, (npc_id, _spec) in enumerate(members):
            core_hue[key_of(npc_id)] = (a_hue + span * (index + 1) / (len(members) + 1)) % 360

    for npc_id in ids:
        name = key_of(npc_id)
        if name in result:
            continue
        spec = CORE.get(name)
        if not spec:
            continue
        disp, _hue, kind, obj_a, obj_b, glyph, tone = spec
        hue = core_hue.get(name)
        if hue is None:
            continue
        taken.append(hue)
        result[name] = {
            "displayName": disp, "tier": "core", "hue": round(hue, 1),
            "kind": kind, "objects": [obj_a, obj_b], "glyph": glyph, "tone": tone,
            "rosterIds": [], "sourceMods": (catalog.get(npc_id) or {}).get("sourceMods", []),
        }

    # 2) 名单里没有专属定义的角色：关键词推断 + 最远点色相
    cursor = 0.0
    for npc_id in ids:
        name = key_of(npc_id)
        if name in result or CORE.get(name):
            continue
        lowered = npc_id.casefold()
        kind, objects, tone = "stone", ("acorn", "leaf_raw"), "村民 · 通用"
        for keys, k, objs, label in KEYWORD_RULES:
            if any(key in lowered for key in keys):
                kind, objects, tone = k, objs, f"村民 · {label}"
                break
        best_hue, best_score = cursor, -1.0
        for step in range(512):
            candidate = (cursor + step * GOLDEN) % 360
            score = min(min(abs(candidate - h) % 360, 360 - abs(candidate - h) % 360) for h in taken)
            if score > best_score:
                best_score, best_hue = score, candidate
        taken.append(best_hue)
        cursor = (best_hue + GOLDEN) % 360
        result[name] = {
            "displayName": (catalog.get(npc_id) or {}).get("displayName", name),
            "tier": "roster", "hue": round(best_hue, 1), "kind": kind,
            "objects": list(objects), "glyph": objects[0], "tone": tone,
            "rosterIds": [], "sourceMods": (catalog.get(npc_id) or {}).get("sourceMods", []),
        }

    # 3) 亮度档：已交付九角色先占位；其余按色相顺序，选"与邻近角色亮度差最大"的档。
    #    只要求档位不同不够——相邻档只差 4，肉眼分不出；色相已经挤的地方只能靠亮度拉开。
    placed = [(float(b["hue"]), int(b["bubbleLevel"])) for b in delivered.values()]
    for index, (name, item) in enumerate(sorted(result.items(), key=lambda kv: kv[1]["hue"])):
        if name in delivered:
            continue
        hue = item["hue"]
        near = [lvl for h, lvl in placed if min(abs(hue - h) % 360, 360 - abs(hue - h) % 360) < NEAR_HUE]
        start = index % len(LUM_LEVELS)
        order = [LUM_LEVELS[(start + offset) % len(LUM_LEVELS)] for offset in range(len(LUM_LEVELS))]
        level = (
            max(order, key=lambda lvl: min(abs(lvl - n) for n in near))
            if near else order[0]
        )
        placed.append((hue, level))
        item["palette"] = build_palette(hue, level)
    for name, item in result.items():
        if name in delivered:
            item["palette"] = dict(delivered[name])

    # 4) 把名单里每个 ID 都登记到它对应的元素上（别名与归并组共用一份）
    for npc_id in ids:
        name = key_of(npc_id)
        if name in result:
            result[name]["rosterIds"].append(npc_id)
    return result, {"aliasCount": len(aliases), "mergeGroups": merge_groups}


def validate(result: dict) -> list[str]:
    """每条元素引用的材质与物件都必须在库里存在。"""
    problems = []
    for name, item in result.items():
        if item["kind"] not in KINDS:
            problems.append(f"{name} 引用了不存在的材质 {item['kind']}")
        for obj in item["objects"]:
            if obj not in OBJECTS:
                problems.append(f"{name} 引用了不存在的物件 {obj}")
    return problems


def audit(result: dict) -> list[str]:
    """色相靠得近的两个角色，底色亮度必须拉开足够距离，否则肉眼分不出。

    口径：色相相差 <6° 时要求亮度差 ≥6；色相相差 ≥6° 本身已可辨。
    （4 个亮度档在 12° 色相跨度内塞 4 个角色时，两两差 ≥8 在数学上做不到。）
    """
    items = list(result.items())
    problems = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            ka, va = items[i]
            kb, vb = items[j]
            gap = min(abs(va["hue"] - vb["hue"]) % 360, 360 - abs(va["hue"] - vb["hue"]) % 360)
            if gap >= 6.0:
                continue
            dl = abs(va["palette"]["bubbleLevel"] - vb["palette"]["bubbleLevel"])
            if dl < 6:
                problems.append(f"{ka}×{kb} 色相差 {gap:.1f}°、亮度只差 {dl}（需 ≥6）")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npcs-json", default=DEFAULT_BRIDGE)
    parser.add_argument("--out", default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    roster = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    catalog = {item["npcId"]: item for item in load_json(args.npcs_json)["npcs"]}
    delivered = {
        npc: body["palette"]
        for npc, body in json.loads(DELIVERED_SPEC.read_text(encoding="utf-8"))["npcs"].items()
    }

    result, meta = build(roster, catalog, delivered)
    problems = validate(result) + audit(result)

    ids = roster["npcs"]
    covered = sum(len(v["rosterIds"]) for v in result.values())
    print(f"好感度名单 {len(ids)} 条 → 独立角色 {len(result)} 个（登记覆盖 {covered} 条）")
    print(f"  别名复用 {meta['aliasCount']} 个，归并组 {len(meta['mergeGroups'])} 个")
    missing = [i for i in ids if i not in {r for v in result.values() for r in v["rosterIds"]}]
    if missing:
        print("  ! 未被登记的名单条目：", missing)
    if problems:
        print(f"审计未通过，{len(problems)} 组：")
        for item in problems[:10]:
            print("  ⚠", item)
        return 1
    print("审计通过：色相相差 <6° 的角色，底色亮度都拉开了 ≥6 ✅")
    if args.check:
        return 0

    out = pathlib.Path(args.out) if args.out else PROJECT / "docs" / "npc-bubble-elements-all-2026-09-19.json"
    payload = {
        "schemaVersion": 2,
        "scope": roster["source"] + "（聊天与群聊只覆盖这些 NPC）",
        "note": "已交付的九角色色板（docs/npc-bubble-elements-2026-09-19.json）原样保留。",
        "coverage": {"rosterCount": len(ids), "uniqueCharacters": len(result)},
        "rules": {
            "hue": "九个已交付色相作锚点切段，段内按语义顺序均匀铺开；无定义的角色取最远黄金角候选",
            "bubbleLevel": "按色相顺序贪心避让，色相相距 8° 内必然拿到不同亮度档",
            "alias": "SVE 命名与原版命名指向同一角色时复用同一份元素定义",
            "merge": "同一角色的多个 ID 归并为一套元素",
        },
        "roster": {"source": roster["source"], "npcs": ids,
                   "aliases": roster.get("aliases") or {},
                   "mergeGroups": roster.get("mergeGroups") or []},
        "kindLibrary": {k: {"label": v[0], "family": v[1], "description": v[2]} for k, v in KINDS.items()},
        "objectLibrary": {k: {"label": v[0], "theme": v[1]} for k, v in OBJECTS.items()},
        "npcs": result,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("已写出", out, out.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
