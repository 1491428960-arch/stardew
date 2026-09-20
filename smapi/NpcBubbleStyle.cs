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
    string Tone,
    int FrameRow,
    string FrameKind,
    Color FrameLine,
    Color FrameHighlight,
    Color FrameLeaf,
    Color FrameLeafHi)
{
    /// <summary>图标图集的单元格边长。</summary>
    public const int CellSize = 24;

    /// <summary>装饰零件图集的单元格边长。</summary>
    public const int FrameCellSize = 32;

    /// <summary>角色图标图集，由 ModEntry 启动时注入；缺失时退回纯配色绘制。</summary>
    public static Texture2D? Sheet { get; set; }

    /// <summary>装饰零件图集（细节造型 + 两个大物件），同样由 ModEntry 注入。</summary>
    public static Texture2D? FrameSheet { get; set; }

    /// <summary>该角色在图集中的单元格。</summary>
    public Rectangle SheetSource =>
        new(SheetIndex * CellSize, 0, CellSize, CellSize);

    /// <summary>装饰零件单元格：0 = 细节造型，1/2 = 大物件。</summary>
    public Rectangle FrameSource(int column) =>
        new(column * FrameCellSize, FrameRow * FrameCellSize, FrameCellSize, FrameCellSize);

    private static readonly IReadOnlyDictionary<string, NpcBubbleStyle> Styles =
        new Dictionary<string, NpcBubbleStyle>(StringComparer.OrdinalIgnoreCase)
{
        ["Abigail"] = new NpcBubbleStyle(0, new Color(66, 60, 253), new Color(131, 94, 212), new Color(176, 146, 242), "好奇 · 直觉", 0, "crystal", new Color(118, 86, 164), new Color(195, 160, 237), new Color(142, 115, 189), new Color(214, 183, 242)),
        ["Alex"] = new NpcBubbleStyle(1, new Color(88, 54, 81), new Color(212, 104, 94), new Color(242, 154, 146), "直球 · 行动派", 1, "laurel", new Color(158, 100, 76), new Color(232, 181, 124), new Color(182, 151, 84), new Color(234, 212, 149)),
        ["Emily"] = new NpcBubbleStyle(2, new Color(35, 118, 181), new Color(94, 212, 192), new Color(146, 242, 226), "温柔 · 灵感", 2, "ribbon", new Color(67, 127, 137), new Color(178, 233, 222), new Color(175, 110, 171), new Color(227, 173, 219)),
        ["Elliott"] = new NpcBubbleStyle(3, new Color(110, 107, 102), new Color(212, 157, 94), new Color(242, 197, 146), "铺陈 · 诗意", 3, "paper", new Color(167, 119, 80), new Color(229, 197, 152), new Color(194, 153, 110), new Color(240, 220, 180)),
        ["Harvey"] = new NpcBubbleStyle(4, new Color(43, 142, 114), new Color(94, 212, 106), new Color(146, 242, 156), "稳重 · 照料", 4, "vine", new Color(107, 134, 94), new Color(191, 211, 156), new Color(113, 151, 100), new Color(197, 217, 170)),
        ["Sebastian"] = new NpcBubbleStyle(5, new Color(35, 54, 202), new Color(94, 104, 212), new Color(146, 154, 242), "克制 · 短句", 5, "cable", new Color(89, 99, 142), new Color(183, 178, 223), new Color(114, 118, 174), new Color(189, 187, 231)),
        ["Shane"] = new NpcBubbleStyle(6, new Color(44, 118, 253), new Color(94, 173, 212), new Color(146, 210, 242), "疲惫 · 嘴硬", 6, "wheat", new Color(139, 118, 84), new Color(230, 197, 139), new Color(186, 158, 102), new Color(240, 216, 162)),
        ["Sophia"] = new NpcBubbleStyle(7, new Color(106, 58, 195), new Color(212, 94, 173), new Color(242, 146, 210), "轻快 · 跳脱", 7, "grapevine", new Color(119, 150, 88), new Color(198, 213, 152), new Color(126, 164, 102), new Color(201, 220, 161)),
        ["Wizard"] = new NpcBubbleStyle(8, new Color(78, 47, 202), new Color(188, 94, 212), new Color(222, 146, 242), "神秘 · 判断", 8, "arcane", new Color(147, 97, 174), new Color(217, 176, 237), new Color(180, 140, 87), new Color(235, 209, 158)),
        ["Lewis"] = new NpcBubbleStyle(9, new Color(40, 50, 211), new Color(100, 94, 212), new Color(151, 146, 242), "体面 · 镇长", 9, "paper", new Color(100, 94, 212), new Color(202, 178, 240), new Color(112, 106, 231), new Color(190, 187, 241)),
        ["Robin"] = new NpcBubbleStyle(10, new Color(92, 80, 86), new Color(212, 144, 94), new Color(242, 186, 146), "爽利 · 木工", 10, "wood", new Color(212, 144, 94), new Color(240, 225, 178), new Color(231, 158, 106), new Color(241, 210, 187)),
        ["Pierre"] = new NpcBubbleStyle(11, new Color(65, 161, 114), new Color(119, 212, 94), new Color(166, 242, 146), "精明 · 营生", 11, "crop", new Color(119, 212, 94), new Color(178, 240, 185), new Color(133, 231, 106), new Color(199, 241, 187)),
        ["Gus"] = new NpcBubbleStyle(12, new Color(120, 157, 114), new Color(212, 206, 94), new Color(242, 237, 146), "热络 · 掌勺", 12, "crop", new Color(212, 206, 94), new Color(223, 240, 178), new Color(231, 225, 106), new Color(241, 239, 187)),
        ["Sam"] = new NpcBubbleStyle(13, new Color(31, 65, 176), new Color(94, 138, 212), new Color(146, 182, 242), "随性 · 音乐", 13, "cable", new Color(94, 138, 212), new Color(178, 180, 240), new Color(106, 153, 231), new Color(187, 207, 241)),
        ["Haley"] = new NpcBubbleStyle(14, new Color(109, 161, 114), new Color(193, 212, 94), new Color(226, 242, 146), "明艳 · 爱美", 14, "ribbon", new Color(193, 212, 94), new Color(210, 240, 178), new Color(211, 231, 106), new Color(233, 241, 187)),
        ["Willy"] = new NpcBubbleStyle(15, new Color(31, 98, 176), new Color(94, 202, 212), new Color(146, 234, 242), "老练 · 钓鱼", 15, "fish", new Color(94, 202, 212), new Color(178, 214, 240), new Color(106, 220, 231), new Color(187, 237, 241)),
        ["Leah"] = new NpcBubbleStyle(16, new Color(36, 103, 72), new Color(107, 212, 94), new Color(156, 242, 146), "自在 · 雕刻", 16, "leaf", new Color(107, 212, 94), new Color(178, 240, 192), new Color(119, 231, 106), new Color(193, 241, 187)),
        ["Andy"] = new NpcBubbleStyle(17, new Color(120, 137, 114), new Color(212, 182, 94), new Color(242, 217, 146), "固执 · 务农", 17, "crop", new Color(212, 182, 94), new Color(236, 240, 178), new Color(231, 198, 106), new Color(241, 227, 187)),
        ["Caroline"] = new NpcBubbleStyle(18, new Color(45, 103, 72), new Color(132, 212, 94), new Color(176, 242, 146), "温和 · 园艺", 18, "flower", new Color(132, 212, 94), new Color(178, 240, 179), new Color(146, 231, 106), new Color(204, 241, 187)),
        ["Demetrius"] = new NpcBubbleStyle(19, new Color(37, 107, 211), new Color(94, 188, 212), new Color(146, 222, 242), "严谨 · 研究", 19, "book", new Color(94, 188, 212), new Color(178, 206, 240), new Color(106, 205, 231), new Color(187, 230, 241)),
        ["Linus"] = new NpcBubbleStyle(20, new Color(49, 161, 114), new Color(94, 212, 94), new Color(147, 242, 146), "淡泊 · 野外", 20, "leaf", new Color(94, 212, 94), new Color(178, 240, 198), new Color(107, 231, 106), new Color(188, 241, 187)),
        ["Marnie"] = new NpcBubbleStyle(21, new Color(75, 103, 72), new Color(206, 212, 94), new Color(236, 242, 146), "热心 · 牧养", 21, "wool", new Color(206, 212, 94), new Color(216, 240, 178), new Color(224, 231, 106), new Color(238, 241, 187)),
        ["Clint"] = new NpcBubbleStyle(22, new Color(77, 61, 72), new Color(212, 130, 94), new Color(242, 176, 146), "沉默 · 锻造", 22, "ore", new Color(212, 130, 94), new Color(240, 218, 178), new Color(231, 144, 106), new Color(241, 204, 187)),
        ["Penny"] = new NpcBubbleStyle(23, new Color(77, 42, 102), new Color(212, 94, 128), new Color(242, 146, 174), "温柔 · 教学", 23, "book", new Color(212, 94, 128), new Color(240, 180, 178), new Color(231, 106, 142), new Color(241, 187, 203)),
        ["Victor"] = new NpcBubbleStyle(24, new Color(54, 58, 243), new Color(116, 94, 212), new Color(164, 146, 242), "内敛 · 设计", 24, "paper", new Color(116, 94, 212), new Color(210, 178, 240), new Color(129, 106, 231), new Color(197, 187, 241)),
        ["Olivia"] = new NpcBubbleStyle(25, new Color(120, 66, 253), new Color(212, 94, 194), new Color(242, 146, 227), "矜贵 · 品味", 25, "ribbon", new Color(212, 94, 194), new Color(240, 178, 210), new Color(231, 106, 211), new Color(241, 187, 233)),
        ["Vincent"] = new NpcBubbleStyle(26, new Color(77, 42, 128), new Color(212, 94, 158), new Color(242, 146, 198), "活泼 · 童言", 26, "flower", new Color(212, 94, 158), new Color(240, 178, 191), new Color(231, 106, 174), new Color(241, 187, 216)),
        ["Jas"] = new NpcBubbleStyle(27, new Color(105, 58, 243), new Color(210, 94, 212), new Color(239, 146, 242), "安静 · 童真", 27, "flower", new Color(210, 94, 212), new Color(240, 178, 221), new Color(228, 106, 231), new Color(240, 187, 241)),
        ["Jodi"] = new NpcBubbleStyle(28, new Color(106, 58, 104), new Color(212, 94, 99), new Color(242, 146, 150), "操持 · 家常", 28, "crop", new Color(212, 94, 99), new Color(240, 196, 178), new Color(231, 106, 111), new Color(241, 187, 190)),
        ["Marlon"] = new NpcBubbleStyle(29, new Color(37, 123, 144), new Color(94, 212, 149), new Color(146, 242, 191), "硬派 · 探险", 29, "ore", new Color(94, 212, 149), new Color(178, 240, 228), new Color(106, 231, 164), new Color(187, 241, 212)),
        ["Maru"] = new NpcBubbleStyle(30, new Color(49, 111, 255), new Color(94, 150, 212), new Color(146, 191, 242), "灵巧 · 发明", 30, "cable", new Color(94, 150, 212), new Color(178, 187, 240), new Color(106, 165, 231), new Color(187, 213, 241)),
        ["Evelyn"] = new NpcBubbleStyle(31, new Color(120, 66, 141), new Color(212, 94, 114), new Color(242, 146, 162), "慈祥 · 烘焙", 31, "wool", new Color(212, 94, 114), new Color(240, 188, 178), new Color(231, 106, 127), new Color(241, 187, 196)),
        ["George"] = new NpcBubbleStyle(32, new Color(31, 103, 102), new Color(94, 212, 127), new Color(146, 242, 173), "固执 · 老兵", 32, "wood", new Color(94, 212, 127), new Color(178, 240, 216), new Color(106, 231, 141), new Color(187, 241, 203)),
        ["Pam"] = new NpcBubbleStyle(33, new Color(77, 81, 72), new Color(212, 169, 94), new Color(242, 207, 146), "豪爽 · 直来直去", 33, "cable", new Color(212, 169, 94), new Color(240, 239, 178), new Color(231, 186, 106), new Color(241, 222, 187)),
        ["Mermaid"] = new NpcBubbleStyle(34, new Color(49, 161, 255), new Color(94, 212, 207), new Color(146, 242, 238), "悠远 · 海", 34, "fish", new Color(94, 212, 207), new Color(178, 222, 240), new Color(106, 231, 226), new Color(187, 241, 239)),
        ["Claire"] = new NpcBubbleStyle(35, new Color(120, 85, 114), new Color(212, 117, 94), new Color(242, 165, 146), "疲惫 · 打工", 35, "crop", new Color(212, 117, 94), new Color(240, 211, 178), new Color(231, 130, 106), new Color(241, 198, 187)),
        ["Martin"] = new NpcBubbleStyle(36, new Color(55, 103, 72), new Color(156, 212, 94), new Color(196, 242, 146), "青涩 · 打工", 36, "paper", new Color(156, 212, 94), new Color(190, 240, 178), new Color(172, 231, 106), new Color(216, 241, 187)),
        ["Dwarf"] = new NpcBubbleStyle(37, new Color(77, 94, 72), new Color(212, 194, 94), new Color(242, 227, 146), "直率 · 交易", 37, "stone", new Color(212, 194, 94), new Color(229, 240, 178), new Color(231, 212, 106), new Color(241, 233, 187)),
        ["Morris"] = new NpcBubbleStyle(38, new Color(31, 77, 176), new Color(94, 161, 212), new Color(146, 200, 242), "圆滑 · 商务", 38, "paper", new Color(94, 161, 212), new Color(178, 193, 240), new Color(106, 177, 231), new Color(187, 218, 241)),
        ["Gunther"] = new NpcBubbleStyle(39, new Color(65, 103, 72), new Color(181, 212, 94), new Color(216, 242, 146), "博学 · 收藏", 39, "book", new Color(181, 212, 94), new Color(203, 240, 178), new Color(198, 231, 106), new Color(227, 241, 187)),
        ["Sandy"] = new NpcBubbleStyle(40, new Color(94, 161, 114), new Color(169, 212, 94), new Color(206, 242, 146), "慵懒 · 沙漠", 40, "flower", new Color(169, 212, 94), new Color(197, 240, 178), new Color(185, 231, 106), new Color(221, 241, 187)),
        ["Susan"] = new NpcBubbleStyle(41, new Color(80, 161, 114), new Color(144, 212, 94), new Color(186, 242, 146), "干练 · 经营", 41, "crop", new Color(144, 212, 94), new Color(183, 240, 178), new Color(159, 231, 106), new Color(210, 241, 187)),
        ["Krobus"] = new NpcBubbleStyle(42, new Color(56, 42, 176), new Color(160, 94, 212), new Color(199, 146, 242), "谨慎 · 暗影", 42, "slime", new Color(160, 94, 212), new Color(234, 178, 240), new Color(176, 106, 231), new Color(217, 187, 241)),
        ["Kent"] = new NpcBubbleStyle(43, new Color(43, 142, 192), new Color(94, 212, 171), new Color(146, 242, 208), "沉重 · 军旅", 43, "wood", new Color(94, 212, 171), new Color(178, 240, 239), new Color(106, 231, 187), new Color(187, 241, 222)),
        ["Henchman"] = new NpcBubbleStyle(44, new Color(49, 84, 255), new Color(94, 115, 212), new Color(146, 163, 242), "寡言 · 随从", 44, "ore", new Color(94, 115, 212), new Color(187, 178, 240), new Color(106, 128, 231), new Color(187, 197, 241)),
        ["Scarlett"] = new NpcBubbleStyle(45, new Color(120, 66, 181), new Color(212, 94, 143), new Color(242, 146, 186), "利落 · 裁缝", 45, "ribbon", new Color(212, 94, 143), new Color(240, 178, 183), new Color(231, 106, 158), new Color(241, 187, 210)),
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
