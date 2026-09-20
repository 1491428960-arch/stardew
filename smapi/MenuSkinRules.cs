using Microsoft.Xna.Framework;

namespace StardewAI.NPC;

/// <summary>
/// 三个聊天界面（F8 私聊、F9 群聊、群聊中心）共用的**外壳**设计令牌与几何。
///
/// 2026-09-20「外壳重构」：在浏览器侧定稿的对照稿是
/// <c>bridge/src/stardew_ai_bridge/ui_preview_redesign_page.py</c>，本类是它在 C# 侧的落点，
/// 每个数值都跟着设计稿里的同名常量（页面里的 <c>SKIN.*</c>），便于逐条核对。
///
/// 视觉基准是气泡：「实底 + 深色描边 + 装饰轮廓」。外壳照同一套结构重排——
/// 一块暖色纸面（面板）→ 内嵌一层凹陷纸面（内容区）→ 卡片与按钮浮在凹陷之上，
/// 三层走 <c>Maps\MenuTiles</c> 的**同一个源矩形**（<c>(0,256,60,60)</c>，20px 九宫格），
/// 只靠 tint 分档。
///
/// ⚠ tint 是乘法：<c>最终色 = 纹理色 × tint ÷ 255</c>，只能让颜色变暗，
/// 所以层级只能「向下分档」：面板白 tint（最亮）→ 凹槽暗一档 → 卡片/按钮回到白 tint。
/// 面板填充实测 <c>#ffc576</c>、描边 <c>#b14e05</c>。
///
/// 本类只放**常量与纯几何**（可单元测试）；真正落到 <c>SpriteBatch</c> 的绘制在
/// <see cref="MenuSkinDrawing"/>。
/// </summary>
public static class MenuSkinRules
{
    // ── 三层底色与两档按钮 tint（设计稿 SKIN.panel / inset / card / btn*）────────

    /// <summary>面板底色：白 tint，三层里最亮的一档，最先画。</summary>
    public static readonly Color PanelTint = Color.White;

    /// <summary>内容区凹槽 tint：纹理填充 <c>#ffc576</c> × 本值 → <c>#e8b068</c>，比面板暗一档。</summary>
    public static readonly Color InsetTint = new(232, 228, 224);

    /// <summary>卡片 tint：与面板同色。卡片之所以能「浮起来」靠的是底下的凹槽，不是自己换色。</summary>
    public static readonly Color CardTint = Color.White;

    /// <summary>主按钮 tint（发送／接受／关闭）。</summary>
    public static readonly Color PrimaryButtonTint = Color.White;

    /// <summary>
    /// 次按钮 tint（找话题／物品／结束／重试／稍后／忽略）。
    /// 改前 F8 的四个按钮是四种几乎分不清的淡色（实测 <c>e9b566</c>／<c>edaa69</c>／
    /// <c>e9b16a</c>／<c>f5ab62</c>），彼此差异小到读不出含义，只留下「脏」；
    /// 收敛成两档之后「发送」自然突出，其余退到后面。
    /// </summary>
    public static readonly Color SecondaryButtonTint = new(238, 226, 208);

    // ── 文字两档（设计稿 SKIN.ink / inkSoft）─────────────────────────────────

    /// <summary>主文字色。</summary>
    public static readonly Color Ink = Color.Black;

    /// <summary>
    /// 次级文字色。收敛到 <see cref="Color.DimGray"/>：改前混用
    /// <c>DarkSlateGray</c>(47,79,79) 偏青，压在暖橙底上会发灰发脏。
    /// 注意 <c>DimGray</c> 在原版里是**禁用态**的语言（<see cref="MenuButtonDrawing"/> 的
    /// <c>enabled ? Color.Black : Color.DimGray</c>），所以它只用于说明性文字，
    /// 不用于按钮标签——次按钮靠底色暗一档退后，标签仍是 <see cref="Ink"/>。
    /// </summary>
    public static readonly Color InkSoft = Color.DimGray;

    /// <summary>标题带下方那条发丝分隔线。</summary>
    public static readonly Color RuleColor = new Color(150, 96, 48) * 0.55f;

    /// <summary>
    /// 整屏遮罩强度。三个界面统一：改前 F8 是 <c>0.42f</c>、F9 与群聊中心**完全没有**遮罩，
    /// 这层差异是「三个界面不像一家人」里最容易被忽略的一条。
    /// </summary>
    public const float ScrimAlpha = 0.28f;

    // ── 标题带（设计稿 titleBand，三个界面共用一套）──────────────────────────

    /// <summary>强调色竖条相对 header 左上角的偏移（横纵相同）。</summary>
    public const int TitleBarInset = 12;

    /// <summary>强调色竖条尺寸。</summary>
    public const int TitleBarWidth = 4;
    public const int TitleBarHeight = 20;

    /// <summary>竖条与标题之间的间距。</summary>
    public const int TitleTextGap = 12;

    /// <summary>标题与右侧状态字之间的间距。</summary>
    public const int StatusTextGap = 16;

    /// <summary>标题相对竖条顶的纵向微调（设计稿 <c>barY - 3</c>）。</summary>
    public const int TitleTextOffsetY = -3;

    /// <summary>状态字相对竖条顶的纵向微调（设计稿 <c>barY - 1</c>）。</summary>
    public const int StatusTextOffsetY = -1;

    /// <summary>发丝分隔线距 header 左右各内缩的距离。</summary>
    public const int RuleInset = 12;

    /// <summary>发丝分隔线距 header 底边的距离。</summary>
    public const int RuleBottomOffset = 14;

    /// <summary>发丝分隔线高度。</summary>
    public const int RuleHeight = 2;

    /// <summary>强调色竖条。</summary>
    public static Rectangle TitleBar(Rectangle header) => new(
        header.X + TitleBarInset,
        header.Y + TitleBarInset,
        TitleBarWidth,
        TitleBarHeight);

    /// <summary>标题文字的左上角。</summary>
    public static Vector2 TitleTextPosition(Rectangle header) => new(
        header.X + TitleBarInset + TitleTextGap,
        header.Y + TitleBarInset + TitleTextOffsetY);

    /// <summary>状态文字的左上角；<paramref name="titleWidth"/> 由字体实测宽度传入。</summary>
    public static Vector2 StatusTextPosition(Rectangle header, float titleWidth) => new(
        header.X + TitleBarInset + TitleTextGap + (float)Math.Ceiling(titleWidth) + StatusTextGap,
        header.Y + TitleBarInset + StatusTextOffsetY);

    /// <summary>标题带底部的发丝分隔线。</summary>
    public static Rectangle TitleRule(Rectangle header) => new(
        header.X + RuleInset,
        header.Bottom - RuleBottomOffset,
        Math.Max(1, header.Width - (RuleInset * 2)),
        RuleHeight);

    // ── 输入框（设计稿 textBoxDesign）───────────────────────────────────────

    /// <summary>
    /// 输入框**绘制**矩形的高度：48 = <c>LooseSprites\textBox</c> 贴图高度。
    ///
    /// ⚠ 这是「输入框下面那条深色带」的真因与修法（2026-09-20 现场确认）：
    /// <c>TextBox.Draw</c> 把这个 192×48 的贴图当**横向三片**用，三次 <c>Draw</c> 的
    /// **源矩形高度写的是 <c>Height</c> 而不是 48**。于是
    /// <c>H ≤ 48</c> 时逐行 1:1 采样；<c>H &gt; 48</c> 时多出来的采样点被 GPU clamp 到
    /// 贴图最后一行 <c>(57,54,65,66)</c>——那是 26% 的冷灰阴影，铺满整个下半部，
    /// 再与暖橙面板相乘，就是实测的米褐色 <c>rgb(190,140,93)</c>。
    /// 设成 48 即 1:1 采样，那条带自然消失，而 48 正是原版为这套素材设计的框高。
    ///
    /// 点击判定**不受影响**：三个界面都用 <c>layout.InputBox.Contains</c>，
    /// 与这里的绘制矩形相互独立（见 <see cref="InputBoxVisual"/>）。
    /// </summary>
    public const int InputBoxHeight = 48;

    /// <summary>输入框在输入区凹槽内左右各内缩的距离。</summary>
    public const int InputBoxHorizontalInset = 12;

    /// <summary>
    /// 输入框**绘制**宽度的防呆下限。⚠ 它不是布局下限，两边差着一档：
    ///
    /// 布局下限写在 <c>ChatLayoutRules.Calculate</c> 与 <c>GroupDialogueLayoutRules.Calculate</c>
    /// 的 <c>Math.Max(120, …)</c>，两处都是 <b>120</b>；<see cref="InputBoxVisual"/> 再左右各缩
    /// <see cref="InputBoxHorizontalInset"/>，于是视觉宽 ≥ 120 − 24 = <b>96</b>，
    /// 也就是说 <c>Math.Max(80, …)</c> 里的 80 在现有几何下<b>取不到</b>，是条不可达的防呆分支。
    ///
    /// 保留它只为将来有人把布局下限调低时不至于画出一个畸形的框。
    /// ⚠ 不要为了「消除死分支」去改布局下限：120 同时决定 <c>layout.InputBox</c> 的宽度，
    /// 而三个界面的命中判定用的就是 <c>layout.InputBox</c>，改它会动点击区域。
    /// </summary>
    public const int InputBoxMinimumWidth = 80;

    /// <summary>
    /// 输入框的**视觉**矩形：在输入区（<paramref name="inputBox"/>，即 <c>layout.InputBox</c>）
    /// 内左右各缩 <see cref="InputBoxHorizontalInset"/>、纵向居中、高固定
    /// <see cref="InputBoxHeight"/>。
    ///
    /// 只影响 <c>TextBox</c> 自己画出来的样子（框、光标、文字），
    /// **不参与任何命中判定**——命中判定一律继续用 <c>layout.InputBox</c>。
    /// </summary>
    public static Rectangle InputBoxVisual(Rectangle inputBox) => new(
        inputBox.X + InputBoxHorizontalInset,
        inputBox.Y + ((inputBox.Height - InputBoxHeight) / 2),
        Math.Max(InputBoxMinimumWidth, inputBox.Width - (InputBoxHorizontalInset * 2)),
        InputBoxHeight);

    // ── F9 群聊：提示行与消息区（设计稿 §「提示行」）─────────────────────────

    /// <summary>提示放不进 header 时，消息区（凹槽与气泡区）要减去的可用高度。</summary>
    public const int HintFallbackReserve = 30;

    /// <summary>消息区可用高度的下限。</summary>
    public const int MessageAreaMinimumHeight = 60;

    /// <summary>header 右侧判断「放得下提示」时，参与者条两端预留的间距。</summary>
    public const int HeaderHintPadding = 24;

    /// <summary>
    /// header 右侧还剩多少宽度可以放提示：参与者条宽度 − 名单宽度 −
    /// <see cref="HeaderHintPadding"/>（设计稿的 <c>headerHintSpace</c>）。
    /// </summary>
    public static float HeaderHintSpace(int participantStripWidth, float namesWidth) =>
        participantStripWidth - namesWidth - HeaderHintPadding;

    /// <summary>
    /// 提示能否放进 header 右侧。短提示（正常态）放得下就走 header，
    /// 于是气泡区**零损失**；只有放不下的长提示（<c>"无可用回复(fb=… n=… spk=[…])"</c>
    /// 那种排障串）才回落到消息区下方、占用 <see cref="HintFallbackReserve"/> 的高度。
    /// </summary>
    public static bool HintFitsHeader(int participantStripWidth, float namesWidth, float hintWidth) =>
        hintWidth <= HeaderHintSpace(participantStripWidth, namesWidth);

    /// <summary>
    /// 提示是否必须占用消息区下方那一行（= 「放不下 header」）。
    ///
    /// ⚠ 与设计稿页面的一处**有意差异**：页面的判定是
    /// <c>s.hint &amp;&amp; measure(hint) &lt;= headerHintSpace</c>，空提示算「不在 header」，
    /// 于是气泡区也减 30px。页面上的示例提示恒为非空，看不到这个分支；
    /// 但游戏里群聊**成功收到回复后 hint 会被清空**（<c>GroupDialogueMenu</c> 的
    /// <c>hint = string.Empty</c>），也就是正常对话中提示大部分时间是空的——
    /// 照搬页面公式会白白少掉 30px 气泡区。<b>没有提示就没有可放的东西，
    /// 自然不占地方</b>：空提示按「不进底部留白」处理，气泡区满额。
    /// </summary>
    public static bool HintNeedsBottomRow(
        bool hasHint,
        int participantStripWidth,
        float namesWidth,
        float hintWidth) =>
        hasHint && !HintFitsHeader(participantStripWidth, namesWidth, hintWidth);

    /// <summary>
    /// 气泡区的实际可用高度。改前提示行固定画在 <c>messageArea.Bottom - 28</c>，
    /// 与最后一条气泡共用同一块高度，气泡一多就叠在一起；分开之后提示行的位置稳定，
    /// 气泡也不会被它压住。
    ///
    /// 正常视口下逐值等于设计稿的 <c>max(60, area.h - 30)</c>；
    /// 外面再套一层「不超过消息区本身」只为极端退化视口收口（消息区比 60 还矮时，
    /// 凹槽会被画到消息区外面去），不影响任何正常分辨率。
    /// </summary>
    public static int MessageBubbleAreaHeight(int messageAreaHeight, bool hintInHeader) =>
        hintInHeader
            ? messageAreaHeight
            : Math.Min(
                messageAreaHeight,
                Math.Max(MessageAreaMinimumHeight, messageAreaHeight - HintFallbackReserve));

    // ── 群聊中心：标题带与邀约列表凹槽（设计稿 renderHub）────────────────────

    /// <summary>群聊中心标题带的固定高度（设计稿里写死的 74，与 <c>listTop</c> 同值）。</summary>
    public const int HubTitleBandHeight = 74;

    /// <summary>邀约列表凹槽距面板左右各内缩的距离。</summary>
    public const int HubListMargin = 24;

    /// <summary>邀约列表凹槽顶边相对面板顶边的偏移。</summary>
    public const int HubListTopOffset = 74;

    /// <summary>邀约列表凹槽底边距关闭按钮顶边的距离。</summary>
    public const int HubListBottomGap = 44;

    /// <summary>邀约列表凹槽的最小高度。</summary>
    public const int HubListMinimumHeight = 40;

    /// <summary>邀约卡第二行文字的纵向偏移（并把原来的第三行并进这一行）。</summary>
    public const int HubCardSecondRowOffset = 44;

    /// <summary>
    /// 邀约列表凹槽：卡片浮在它上面，靠底色分档分层（卡片自身的 tint 不动）。
    /// </summary>
    public static Rectangle HubListArea(Rectangle panel, Rectangle closeButton)
    {
        var top = panel.Y + HubListTopOffset;
        var bottom = closeButton.Y - HubListBottomGap;
        return new Rectangle(
            panel.X + HubListMargin,
            top,
            Math.Max(1, panel.Width - (HubListMargin * 2)),
            Math.Max(HubListMinimumHeight, bottom - top));
    }
}
