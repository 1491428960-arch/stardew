using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

namespace StardewAI.NPC;

/// <summary>
/// 角色气泡视觉样式；数据由 <c>scripts/export_npc_bubble_assets.py</c> 从
/// bridge 侧的 <c>npc_bubble_elements.py</c> 生成，请勿手改。
/// 图集见 assets/npc_bubbles.png（每格 24×24，横向排列）。
/// </summary>
public sealed record NpcBubbleStyle(
    int SheetIndex,
    Color Bubble,
    Color Border,
    Color Accent,
    string Tone)
{
    /// <summary>图集单元格边长。</summary>
    public const int CellSize = 24;

    /// <summary>角色图标图集，由 ModEntry 启动时注入；缺失时退回纯配色绘制。</summary>
    public static Texture2D? Sheet { get; set; }

    /// <summary>该角色在图集中的单元格。</summary>
    public Rectangle SheetSource =>
        new(SheetIndex * CellSize, 0, CellSize, CellSize);

    private static readonly IReadOnlyDictionary<string, NpcBubbleStyle> Styles =
        new Dictionary<string, NpcBubbleStyle>(StringComparer.OrdinalIgnoreCase)
{
        ["Abigail"] = new NpcBubbleStyle(0, new Color(65, 44, 109), new Color(131, 94, 212), new Color(176, 146, 242), "好奇 · 直觉"),
        ["Alex"] = new NpcBubbleStyle(1, new Color(87, 40, 35), new Color(212, 104, 94), new Color(242, 154, 146), "直球 · 行动派"),
        ["Emily"] = new NpcBubbleStyle(2, new Color(35, 87, 78), new Color(94, 212, 192), new Color(146, 242, 226), "温柔 · 灵感"),
        ["Elliott"] = new NpcBubbleStyle(3, new Color(109, 79, 44), new Color(212, 157, 94), new Color(242, 197, 146), "铺陈 · 诗意"),
        ["Harvey"] = new NpcBubbleStyle(4, new Color(43, 105, 49), new Color(94, 212, 106), new Color(146, 242, 156), "稳重 · 照料"),
        ["Sebastian"] = new NpcBubbleStyle(5, new Color(35, 40, 87), new Color(94, 104, 212), new Color(146, 154, 242), "克制 · 短句"),
        ["Shane"] = new NpcBubbleStyle(6, new Color(44, 87, 109), new Color(94, 173, 212), new Color(146, 210, 242), "疲惫 · 嘴硬"),
        ["Sophia"] = new NpcBubbleStyle(7, new Color(105, 43, 84), new Color(212, 94, 173), new Color(242, 146, 210), "轻快 · 跳脱"),
        ["Wizard"] = new NpcBubbleStyle(8, new Color(77, 35, 87), new Color(188, 94, 212), new Color(222, 146, 242), "神秘 · 判断"),
        ["Lewis"] = new NpcBubbleStyle(9, new Color(40, 37, 91), new Color(100, 94, 212), new Color(151, 146, 242), "体面 · 镇长"),
        ["Robin"] = new NpcBubbleStyle(10, new Color(91, 59, 37), new Color(212, 144, 94), new Color(242, 186, 146), "爽利 · 木工"),
        ["Pierre"] = new NpcBubbleStyle(11, new Color(64, 119, 49), new Color(119, 212, 94), new Color(166, 242, 146), "精明 · 营生"),
        ["Gus"] = new NpcBubbleStyle(12, new Color(119, 116, 49), new Color(212, 206, 94), new Color(242, 237, 146), "热络 · 掌勺"),
        ["Sam"] = new NpcBubbleStyle(13, new Color(31, 48, 76), new Color(94, 138, 212), new Color(146, 182, 242), "随性 · 音乐"),
        ["Haley"] = new NpcBubbleStyle(14, new Color(108, 119, 49), new Color(193, 212, 94), new Color(226, 242, 146), "明艳 · 爱美"),
        ["Willy"] = new NpcBubbleStyle(15, new Color(31, 72, 76), new Color(94, 202, 212), new Color(146, 234, 242), "老练 · 钓鱼"),
        ["Leah"] = new NpcBubbleStyle(16, new Color(36, 76, 31), new Color(107, 212, 94), new Color(156, 242, 146), "自在 · 雕刻"),
        ["Andy"] = new NpcBubbleStyle(17, new Color(119, 101, 49), new Color(212, 182, 94), new Color(242, 217, 146), "固执 · 务农"),
        ["Caroline"] = new NpcBubbleStyle(18, new Color(45, 76, 31), new Color(132, 212, 94), new Color(176, 242, 146), "温和 · 园艺"),
        ["Demetrius"] = new NpcBubbleStyle(19, new Color(37, 79, 91), new Color(94, 188, 212), new Color(146, 222, 242), "严谨 · 研究"),
        ["Linus"] = new NpcBubbleStyle(20, new Color(49, 119, 49), new Color(94, 212, 94), new Color(147, 242, 146), "淡泊 · 野外"),
        ["Marnie"] = new NpcBubbleStyle(21, new Color(74, 76, 31), new Color(206, 212, 94), new Color(236, 242, 146), "热心 · 牧养"),
        ["Clint"] = new NpcBubbleStyle(22, new Color(76, 45, 31), new Color(212, 130, 94), new Color(242, 176, 146), "沉默 · 锻造"),
        ["Penny"] = new NpcBubbleStyle(23, new Color(76, 31, 44), new Color(212, 94, 128), new Color(242, 146, 174), "温柔 · 教学"),
        ["Victor"] = new NpcBubbleStyle(24, new Color(54, 43, 105), new Color(116, 94, 212), new Color(164, 146, 242), "内敛 · 设计"),
        ["Olivia"] = new NpcBubbleStyle(25, new Color(119, 49, 109), new Color(212, 94, 194), new Color(242, 146, 227), "矜贵 · 品味"),
        ["Vincent"] = new NpcBubbleStyle(26, new Color(76, 31, 55), new Color(212, 94, 158), new Color(242, 146, 198), "活泼 · 童言"),
        ["Jas"] = new NpcBubbleStyle(27, new Color(104, 43, 105), new Color(210, 94, 212), new Color(239, 146, 242), "安静 · 童真"),
        ["Jodi"] = new NpcBubbleStyle(28, new Color(105, 43, 45), new Color(212, 94, 99), new Color(242, 146, 150), "操持 · 家常"),
        ["Marlon"] = new NpcBubbleStyle(29, new Color(37, 91, 62), new Color(94, 212, 149), new Color(146, 242, 191), "硬派 · 探险"),
        ["Maru"] = new NpcBubbleStyle(30, new Color(49, 82, 119), new Color(94, 150, 212), new Color(146, 191, 242), "灵巧 · 发明"),
        ["Evelyn"] = new NpcBubbleStyle(31, new Color(119, 49, 61), new Color(212, 94, 114), new Color(242, 146, 162), "慈祥 · 烘焙"),
        ["George"] = new NpcBubbleStyle(32, new Color(31, 76, 44), new Color(94, 212, 127), new Color(146, 242, 173), "固执 · 老兵"),
        ["Pam"] = new NpcBubbleStyle(33, new Color(76, 60, 31), new Color(212, 169, 94), new Color(242, 207, 146), "豪爽 · 直来直去"),
        ["Mermaid"] = new NpcBubbleStyle(34, new Color(49, 119, 117), new Color(94, 212, 207), new Color(146, 242, 238), "悠远 · 海"),
        ["Claire"] = new NpcBubbleStyle(35, new Color(119, 63, 49), new Color(212, 117, 94), new Color(242, 165, 146), "疲惫 · 打工"),
        ["Martin"] = new NpcBubbleStyle(36, new Color(55, 76, 31), new Color(156, 212, 94), new Color(196, 242, 146), "青涩 · 打工"),
        ["Dwarf"] = new NpcBubbleStyle(37, new Color(76, 69, 31), new Color(212, 194, 94), new Color(242, 227, 146), "直率 · 交易"),
        ["Morris"] = new NpcBubbleStyle(38, new Color(31, 57, 76), new Color(94, 161, 212), new Color(146, 200, 242), "圆滑 · 商务"),
        ["Gunther"] = new NpcBubbleStyle(39, new Color(64, 76, 31), new Color(181, 212, 94), new Color(216, 242, 146), "博学 · 收藏"),
        ["Sandy"] = new NpcBubbleStyle(40, new Color(93, 119, 49), new Color(169, 212, 94), new Color(206, 242, 146), "慵懒 · 沙漠"),
        ["Susan"] = new NpcBubbleStyle(41, new Color(79, 119, 49), new Color(144, 212, 94), new Color(186, 242, 146), "干练 · 经营"),
        ["Krobus"] = new NpcBubbleStyle(42, new Color(56, 31, 76), new Color(160, 94, 212), new Color(199, 146, 242), "谨慎 · 暗影"),
        ["Kent"] = new NpcBubbleStyle(43, new Color(43, 105, 83), new Color(94, 212, 171), new Color(146, 242, 208), "沉重 · 军旅"),
        ["Henchman"] = new NpcBubbleStyle(44, new Color(49, 62, 119), new Color(94, 115, 212), new Color(146, 163, 242), "寡言 · 随从"),
        ["Scarlett"] = new NpcBubbleStyle(45, new Color(119, 49, 78), new Color(212, 94, 143), new Color(242, 146, 186), "利落 · 裁缝"),
        };

    private static readonly IReadOnlyDictionary<string, string> Aliases =
        new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
{
        ["GuntherSilvian"] = "Gunther",
        ["MarlonFay"] = "Marlon",
        ["MermaidLantana"] = "Mermaid",
        ["MorrisTod"] = "Morris",
        ["SVE_Henchman"] = "Henchman",
        };

    /// <summary>未知角色回落到中性样式，绝不抛异常打断绘制。</summary>
    public static NpcBubbleStyle? For(string? npcId)
    {
        if (string.IsNullOrWhiteSpace(npcId))
        {
            return null;
        }

        var key = npcId.Trim();
        if (Aliases.TryGetValue(key, out var canonical))
        {
            key = canonical;
        }

        return Styles.TryGetValue(key, out var style) ? style : null;
    }
}
